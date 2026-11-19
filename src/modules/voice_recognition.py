import os
import re
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import requests
from dotenv import load_dotenv

from faster_whisper import WhisperModel

from modules.gemini_service import GeminiService
from modules.nao_audio_transfer import NAOAudioTransfer

try:
    from silero_vad import get_speech_timestamps, load_silero_vad
    import torch
except ImportError:
    get_speech_timestamps = None
    load_silero_vad = None
    torch = None

load_dotenv()

class VoiceRecognition:
    SEARCH_RESULT_LIMIT = 3
    RECORDING_CHUNK_DURATION = 0.25
    SPEECH_END_SILENCE_DURATION = 0.75
    SPEECH_START_TIMEOUT = 8.0
    MAX_RECORDING_DURATION = 20.0
    DEFAULT_RECORDING_DURATION = 4.0
    """ Commands Structure """
    SEARCH_COMMAND_RE = re.compile(
        r"\b(?:find me|find|search for|search|give me|show me)\s+"
        r"(?P<kind>videos?|websites?|sites?|images?|pictures?|photos?|"
        r"news|articles?|web\s*pages?|webpages?)\s+"
        r"(?:about|on|for)\s+"
        r"(?P<query>.+)",
        re.IGNORECASE,
    )
    """ Web Search Structure """
    SIMPLE_SEARCH_COMMAND_RE = re.compile(
        r"\b(?:find me|find|search for|search|look up|google)\s+"
        r"(?P<query>.+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        session=None,
        speaker=None,
        gemini_service=None,
        use_gemini=True,
        frame_provider=None,
        state_manager=None,
    ):
        self.session = session
        self.speaker = speaker
        self.use_gemini = use_gemini
        self.gemini_service = gemini_service
        self.frame_provider = frame_provider
        self.state_manager = state_manager
        self.brave_search_api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        self.recording_lock = threading.Lock()
        self._vad_load_lock = threading.Lock()
        self._vad_load_attempted = False
        self.vad_model = None
        self.vad_enabled = all(
            helper is not None
            for helper in (get_speech_timestamps, load_silero_vad, torch)
        )

        module_dir = Path(__file__).resolve().parent

        # Temp audio path for real NAO recording
        self.nao_audio_path = "/home/nao/nao_speech.wav"
        self.temp_audio_path = str(Path(tempfile.gettempdir()) / "nao_speech.wav")

        if self.vad_enabled:
            print("[VoiceRecognition] Silero VAD enabled; loading model during startup...")
            self._ensure_vad_model()
        else:
            print(
                "[VoiceRecognition] Silero VAD unavailable; Try install it with: python -m pip install silero-vad. "
            )

        # Initialize Whisper Model
        print("[VoiceRecognition] Initializing Whisper model...")
        # CUDA may be unavailable even when faster-whisper itself imports
        # successfully (for example, when cuBLAS DLLs are missing). CPU INT8
        # is slower but reliable for short NAO utterances.
        self.model = WhisperModel("base", device="cpu", compute_type="int8")

        # Initialize NAO Audio Recorder proxy if session exists
        self.audio_recorder = None
        self.file_manager = None
        if self.session and self.session.isConnected():
            try:
                self.audio_recorder = self.session.service("ALAudioRecorder")
                self.file_manager = self.session.service("ALFileManager")

                print("[VoiceRecognition] ALAudioRecorder connected.")
                print("[VoiceRecognition] ALFileManager connected.")

                try:
                    meta_object = self.file_manager.metaObject()
                    if hasattr(meta_object, "methodNames"):
                        methods = list(meta_object.methodNames())
                    elif isinstance(meta_object, dict):
                        raw_methods = (
                            meta_object.get("methods") or meta_object.get("method") or []
                        )
                        if isinstance(raw_methods, dict):
                            methods = list(raw_methods.keys())
                        else:
                            methods = [
                                method.get("name")
                                if isinstance(method, dict) and "name" in method
                                else str(method)
                                for method in raw_methods
                            ]
                    else:
                        methods = []

                    if methods:
                        print("[VoiceRecognition] ALFileManager methods:", methods)
                except Exception as e:
                    print(
                        f"[VoiceRecognition Warning] "
                        f"Could not inspect ALFileManager: {e}"
                    )
            except Exception as e:
                print(f"[VoiceRecognition Warning] Could not initialize NAO audio/file services: {e}")

        if self.use_gemini and self.gemini_service is None:
            try:
                self.gemini_service = GeminiService()
            except Exception as e:
                self.gemini_service = None
                print(f"[VoiceRecognition Warning] Gemini Service did not initialize: {e}")

        self.audio_transfer = NAOAudioTransfer(
            audio_recorder=self.audio_recorder,
            file_manager=self.file_manager,
            remote_path=self.nao_audio_path,
            local_path=self.temp_audio_path,
        )

    @staticmethod
    def _log_performance(stage, started_at):
        print(f"[Performance] {stage}: {time.perf_counter() - started_at:.3f}s")

    def _ensure_vad_model(self):
        """Load Silero once, while retaining a safe no-VAD fallback."""
        if not self.vad_enabled or self.vad_model is not None:
            return self.vad_model

        with self._vad_load_lock:
            if self.vad_model is not None or self._vad_load_attempted:
                return self.vad_model

            self._vad_load_attempted = True
            started_at = time.perf_counter()
            try:
                # Silero's TorchScript model calls torch.jit.load(), which
                # PyTorch does not support on Python 3.14+. Use the bundled
                # ONNX model there instead; it has the same VAD interface and
                # avoids the warning and the impending TorchScript failure.
                use_onnx = sys.version_info >= (3, 14)
                self.vad_model = load_silero_vad(onnx=use_onnx)
                if self.vad_model is None:
                    raise RuntimeError("load_silero_vad returned no model")
                self._log_performance("Silero VAD initialization", started_at)
                backend = "ONNX" if use_onnx else "TorchScript"
                print(f"[VoiceRecognition] Silero VAD model loaded ({backend}).")
            except Exception as e:
                self.vad_enabled = False
                self.vad_model = None
                self._log_performance("Silero VAD initialization", started_at)
                print(
                    f"[VoiceRecognition Warning] Silero VAD could not be loaded; "
                    f"using full audio without VAD: {e}"
                )
        return self.vad_model

    def listen_once_async(self, duration=None, on_complete=None):
        """Starts one recording/transcription pass in the background."""
        if self.recording_lock.locked():
            print("[VoiceRecognition] Recording already in progress. Ignoring trigger.")
            return False

        def _worker():
            try:
                self.listen_once(duration=duration)
            finally:
                if on_complete:
                    on_complete()

        threading.Thread(target=_worker, daemon=True).start()
        return True

    def listen_once(self, duration=None):
        if not self.recording_lock.acquire(blocking=False):
            print("[VoiceRecognition] Recording already in progress. Skipping.")
            return ""

        interaction_started_at = time.perf_counter()
        try:
            print("[VoiceRecognition] Waiting for speech to start...")
            self._set_status("Recording")

            if self.audio_recorder:
                print("[VoiceRecognition] Using NAO ALAudioRecorder.")
                recording_started_at = time.perf_counter()
                try:
                    # ALAudioRecorder is file-based, so capture one complete
                    # utterance instead of repeatedly restarting it for tiny
                    # chunks.
                    capture_duration = (
                        duration
                        if duration is not None
                        else self.DEFAULT_RECORDING_DURATION
                    )
                    print(
                        f"[VoiceRecognition] Recording fixed utterance "
                        f"({capture_duration:.1f}s)."
                    )
                    audio_file = self.audio_transfer.record_from_nao(
                        capture_duration
                    )
                finally:
                    self._log_performance("Audio acquisition", recording_started_at)
            else:
                print(
                    "[VoiceRecognition Warning] ALAudioRecorder unavailable; "
                    "real NAO recording cannot start."
                )
                audio_file = None

            print(f"[VoiceRecognition] Audio file: {audio_file}")

            if audio_file and os.path.exists(audio_file):
                print("[VoiceRecognition] Starting transcription...")
                self._set_status("Transcribing")

                text = self._transcribe(audio_file)

                print(f"[VoiceRecognition] Transcription: '{text}'")

                if text:
                    self._set_status("Processing command")
                    if self.speaker:
                        self.speaker.speak("I'm thinking.", animated=False)
                    routing_started_at = time.perf_counter()
                    try:
                        result = self._on_speech_recognized(text)
                    finally:
                        self._log_performance(
                            "Command parsing and routing", routing_started_at
                        )
                    self._record_result(text, result)
                    self._set_status("Command completed")
                    self._set_status("Ready/listening again")
                else:
                    self._record_result(
                        "",
                        {
                            "action": "Unknown",
                            "response": "No speech was recognized.",
                            "status": "Error",
                        },
                    )
                    self._set_status("Ready/listening again")

                return text

            print("[VoiceRecognition] No audio file available.")
            self._set_status("Error", "No audio file available.")
            return ""
        except Exception as e:
            self._set_status("Error", str(e))
            raise

        finally:
            self._log_performance("Total interaction", interaction_started_at)
            self.recording_lock.release()

    def _speech_detected(self, audio_path):
        """Return whether a short audio chunk contains speech."""
        if not self.vad_enabled:
            return False

        if self._ensure_vad_model() is None:
            return False

        audio = self._read_audio_for_vad(audio_path)
        timestamps = get_speech_timestamps(
            audio,
            self.vad_model,
            sampling_rate=16000,
            threshold=0.25,
            min_speech_duration_ms=80,
            min_silence_duration_ms=80,
            speech_pad_ms=0,
            return_seconds=False,
        )
        if timestamps:
            return True

        # NAO recordings can be quieter than Silero's usual input. Treat a
        # modest non-zero signal as speech so quiet utterances are not lost.
        rms = float(torch.sqrt(torch.mean(audio * audio))) if audio.numel() else 0.0
        peak = float(torch.max(torch.abs(audio))) if audio.numel() else 0.0
        return rms >= 0.008 or peak >= 0.08

    def _transcribe(self, audio_path):
        """Converts audio file to text using faster-whisper."""
        vad_started_at = time.perf_counter()
        try:
            speech_audio_path = self._extract_speech_audio(audio_path)
        finally:
            self._log_performance("VAD processing", vad_started_at)
        if not speech_audio_path:
            print("[VoiceRecognition] Silero VAD found no speech.")
            return ""

        transcription_started_at = time.perf_counter()
        try:
            # Pass decoded audio to faster-whisper instead of a filename.
            # This avoids a PyAV compatibility issue where av.open() does not
            # accept faster-whisper's metadata_errors argument.
            audio = self._read_audio_for_whisper(speech_audio_path)
            segments, _ = self.model.transcribe(
                audio,
                beam_size=5,
                task="translate",
            )
            return "".join([segment.text for segment in segments]).strip()
        except Exception as e:
            print(f"[VoiceRecognition Error] Transcription failed: {e}")
            return ""
        finally:
            self._log_performance("Whisper transcription", transcription_started_at)
            if speech_audio_path != audio_path:
                try:
                    os.remove(speech_audio_path)
                except OSError:
                    pass

    @staticmethod
    def _read_audio_for_whisper(audio_path):
        """Read a PCM WAV into the float32 format expected by Whisper."""
        with wave.open(audio_path, "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw_audio = wav_file.readframes(wav_file.getnframes())

        if sample_width == 1:
            audio = np.frombuffer(raw_audio, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0
        elif sample_width == 3:
            raw = np.frombuffer(raw_audio, dtype=np.uint8).reshape(-1, 3)
            values = (
                raw[:, 0].astype(np.int32)
                | (raw[:, 1].astype(np.int32) << 8)
                | (raw[:, 2].astype(np.int32) << 16)
            )
            values[values & 0x800000 != 0] -= 1 << 24
            audio = values.astype(np.float32) / 8388608.0
        elif sample_width == 4:
            audio = np.frombuffer(raw_audio, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if sample_rate != 16000:
            raise ValueError(f"Expected 16 kHz WAV for Whisper, received {sample_rate} Hz")
        return np.ascontiguousarray(audio, dtype=np.float32)

    def _extract_speech_audio(self, audio_path):
        """Trim silence from a recording with Silero VAD before Whisper runs."""
        if not self.vad_enabled:
            return audio_path

        try:
            if self._ensure_vad_model() is None:
                return audio_path

            audio = self._read_audio_for_vad(audio_path)
            timestamps = get_speech_timestamps(
                audio,
                self.vad_model,
                sampling_rate=16000,
                threshold=0.25,
                min_speech_duration_ms=120,
                min_silence_duration_ms=120,
                speech_pad_ms=250,
                return_seconds=False,
            )

            if not timestamps:
                # Let Whisper inspect the complete recording. This is safer
                # than discarding a valid but quiet utterance.
                return audio_path

            speech_chunks = [
                audio[int(timestamp["start"]):int(timestamp["end"])]
                for timestamp in timestamps
            ]
            speech_audio = torch.cat(speech_chunks).detach().cpu().numpy()
            speech_audio = np.clip(speech_audio, -1.0, 1.0)
            pcm_audio = (speech_audio * 32767).astype(np.int16)

            trimmed_path = str(
                Path(tempfile.gettempdir())
                / f"nao_speech_trimmed_{threading.get_ident()}.wav"
            )
            with wave.open(trimmed_path, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(pcm_audio.tobytes())

            print(
                f"[VoiceRecognition] Silero VAD kept {len(pcm_audio) / 16000:.2f}s "
                "of speech from the recording."
            )
            return trimmed_path
        except Exception as e:
            print(f"[VoiceRecognition Warning] Silero VAD failed; using full recording: {e}")
            return audio_path

    @staticmethod
    def _read_audio_for_vad(audio_path):
        """Decode NAO's PCM WAV without torchaudio or torchcodec."""
        with wave.open(audio_path, "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            raw_audio = wav_file.readframes(wav_file.getnframes())

        if sample_width == 1:
            audio = np.frombuffer(raw_audio, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0
        elif sample_width == 3:
            raw = np.frombuffer(raw_audio, dtype=np.uint8).reshape(-1, 3)
            values = (
                raw[:, 0].astype(np.int32)
                | (raw[:, 1].astype(np.int32) << 8)
                | (raw[:, 2].astype(np.int32) << 16)
            )
            values[values & 0x800000 != 0] -= 1 << 24
            audio = values.astype(np.float32) / 8388608.0
        elif sample_width == 4:
            audio = np.frombuffer(raw_audio, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        if sample_rate != 16000:
            raise ValueError(f"Expected 16 kHz WAV for VAD, received {sample_rate} Hz")
        return torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))

    def _capture_camera_frame(self):
        if cv2 is None:
            return None

        try:
            frame = None

            if self.frame_provider is not None:
                frame = self.frame_provider()
            elif self.session and self.session.isConnected() and np is not None:
                video = self.session.service("ALVideoDevice")
                client_name = f"VoiceRecognitionVision_{threading.get_ident()}"
                client_name = video.subscribeCamera(
                    client_name,0,2,11,5,
                )
                try:
                    image = video.getImageRemote(client_name)
                finally:
                    try:
                        video.unsubscribe(client_name)
                    except Exception:
                        pass

                if image is None:
                    return None

                width = int(image[0])
                height = int(image[1])
                image_data = image[6]
                frame = np.frombuffer(image_data, dtype=np.uint8).reshape(
                    (height, width, 3)
                )
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            if frame is None:
                return None

            ok, buffer = cv2.imencode(".jpg", frame)
            if not ok:
                return None

            return buffer.tobytes()
        except Exception as e:
            print(f"[VoiceRecognition Warning] Camera frame capture failed: {e}")
            return None

    """ COMMAND HANDLING"""
    def _on_speech_recognized(self, text):
        """Triggers actions when speech is detected."""
        print(f"\n[VoiceRecognition] Heard: \"{text}\"")

        if not text:
            return {
                "action": "Unknown",
                "response": "No command was recognized.",
                "status": "Error",
            }

        # Simple keyword matching stays first so fixed classroom commands are fast
        # and keep working without Gemini.
        keyword_result = self._handle_keyword_command(text)
        if keyword_result:
            return keyword_result

        if self.gemini_service and self.use_gemini:
            image = self._capture_camera_frame()

            prompt = text
            if image is not None:
                prompt = (
                    "Use the attached NAO camera image if it helps answer the question. "
                    "Reply in English only. "
                    f"User said: {text}"
                )

            gemini_started_at = time.perf_counter()
            try:
                response = self.gemini_service.ask(prompt, image=image)
            finally:
                self._log_performance("Gemini response", gemini_started_at)
            if response:
                print(f"[VoiceRecognition] Gemini: \"{response}\"")
                if self.speaker:
                    self.speaker.speak(response)
                return {
                    "action": "Gemini",
                    "response": response,
                    "status": "Completed",
                }

        response = "I did not understand that command."
        if self.speaker:
            self.speaker.speak(response)
        return {
            "action": "Unknown",
            "response": response,
            "status": "Completed",
        }

    def _handle_keyword_command(self, text):
        """Handles fixed voice commands with simple keyword matching."""
        normalized_text = text.lower()
        compact_text = normalized_text.replace(" ", "")

        search_result = self._handle_search_command(text)
        if search_result:
            return search_result

        if not self.speaker:
            return None

        if self._contains_command(
            normalized_text,
            compact_text,
            [
                "attendance mode",
                "start attendance",
                "begin attendance",
                "take attendance",
                "mark attendance",
                "record attendance",
            ],
        ):
            response = "Attendance Mode Activating..."
            self.speaker.speak(response)
            return {
                "action": "Attendance",
                "response": response,
                "status": "Completed",
            }

        if "hello" in normalized_text:
            response = "Hello, this is from pre-built keyword..."
            self.speaker.speak(response)
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if self._contains_command(normalized_text, compact_text, ["stand up", "standup"]):
            response = "Standing up."
            self._go_to_posture("StandInit")
            self.speaker.speak(response)
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if self._contains_command(normalized_text, compact_text, ["sit down", "sitdown"]):
            response = "Sitting down."
            self.speaker.speak(response, animated=False)
            self._go_to_posture("Sit")
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if self._contains_command(normalized_text, compact_text, ["wake up", "wakeup"]):
            response = "Waking up."
            self._wake_up()
            self.speaker.speak(response)
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if "rest" in normalized_text:
            response = "Going to rest mode."
            self.speaker.speak(response, animated=False)
            self._rest()
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if "crouch" in normalized_text:
            response = "Crouching."
            self.speaker.speak(response, animated=False)
            self._go_to_posture("Crouch")
            return {
                "action": "Robot",
                "response": response,
                "status": "Completed",
            }

        if (
            "camera" in normalized_text
            or "vision" in normalized_text
            or "classroom" in normalized_text
            or "what do you see" in normalized_text
        ):
            return None

        return None

    def _handle_search_command(self, text):
        search_request = self._parse_search_command(text)
        if not search_request:
            return False

        kind, query = search_request
        search_started_at = time.perf_counter()
        try:
            results = self._brave_search(
                kind, query, limit=self.SEARCH_RESULT_LIMIT
            )
        finally:
            self._log_performance("Web search execution", search_started_at)

        if not results:
            message = f"I could not find relevant {kind} about {query}."
            print(f"[VoiceRecognition] {message}")
            if self.speaker:
                self.speaker.speak(message)
            return {
                "action": "Web Search",
                "response": message,
                "status": "Completed",
                "recommendations": [],
            }

        noun = {
            "videos": "videos",
            "images": "images",
            "news": "news articles",
        }.get(kind, "websites")
        lines = [
            f"{index}. {noun.title()} title: {result['title']}"
            for index, result in enumerate(results, start=1)
        ]
        response = "\n".join(lines)
        spoken_response = f"Search result about {query} found."

        print(f"[VoiceRecognition] Brave {kind} results for '{query}':\n{response}")
        if self.speaker:
            self.speaker.speak(spoken_response)
        return {
            "action": "Web Search",
            "response": spoken_response,
            "status": "Completed",
            "recommendations": results,
        }

    """Identifies the requested search category"""
    def _parse_search_command(self, text):
        text = " ".join(text.strip().split())

        match = self.SEARCH_COMMAND_RE.search(text)
        if not match:
            match = self.SIMPLE_SEARCH_COMMAND_RE.search(text)
            if not match:
                return None

            query = match.group("query").strip(" .?!")
            if not query:
                return None

            lowered_query = query.lower()
            if lowered_query.startswith(("video ", "videos ")):
                kind = "videos"
            elif lowered_query.startswith(("image ", "images ", "picture ", "pictures ", "photo ", "photos ")):
                kind = "images"
            elif lowered_query.startswith(("news ", "article ", "articles ")):
                kind = "news"
            else:
                kind = "websites"
            query = re.sub(
                r"^(?:videos?|websites?|sites?|images?|pictures?|photos?|news|articles?)\s+"
                r"(?:about|on|for)?\s*",
                "",
                query,
                flags=re.IGNORECASE,
            )
            if not query:
                return None
            return kind, query

        kind = match.group("kind").lower().replace(" ", "")
        query = match.group("query").strip(" .?!")
        if not query:
            return None

        if kind.startswith("video"):
            return "videos", query
        if kind.startswith(("image", "picture", "photo")):
            return "images", query
        if kind.startswith(("news", "article")):
            return "news", query
        return "websites", query

    """Search Brave's web or video endpoint."""
    def _brave_search(self, kind, query, limit=3):

        if not self.brave_search_api_key:
            message = (
                "Brave Search is not configured. Add BRAVE_SEARCH_API_KEY to .env."
            )
            print(f"[VoiceRecognition Warning] {message}")

            if self.speaker:
                self.speaker.speak(message)
            return []

        endpoint = {
            "videos": "videos",
            "images": "images",
            "news": "news",
        }.get(kind, "web")

        search_query = f"site:youtube.com {query}" if kind == "videos" else query

        try:
            response = requests.get(
                f"https://api.search.brave.com/res/v1/{endpoint}/search",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.brave_search_api_key,
                },
                params={
                    "q": search_query,
                    "count": limit * 3 if kind == "videos" else limit,
                    "country": "ALL",
                    "search_lang": "en",
                    "safesearch": "moderate",
                },
                timeout=20,
            )

            response.raise_for_status()
            payload = response.json()

            raw_results = (
                payload.get("web", {}).get("results", [])

                if kind == "websites"
                else payload.get("results", [])
            )

            results = []
            for item in raw_results:
                title = item.get("title")
                url = item.get("url")
                parsed_url = urlparse(str(url))
                hostname = parsed_url.netloc.lower().split(":", 1)[0].rstrip(".")

                """Validates results format, if not matches then skip result"""
                if (
                    not title #must have title
                    or parsed_url.scheme not in {"http", "https"} #URL is http/https
                    or not parsed_url.netloc #Valid Hostname
                ):
                    continue
                if kind == "videos" and not (
                    hostname == "youtu.be"
                    or hostname == "youtube.com"
                    or hostname.endswith(".youtube.com")
                ):
                    continue

                thumbnail = item.get("thumbnail")
                if isinstance(thumbnail, dict):
                    thumbnail = thumbnail.get("src") or thumbnail.get("original")

                """Thumbnail backups"""
                thumbnail_url = urlparse(str(thumbnail)) if thumbnail else None # Check valid URL
                if not thumbnail_url or thumbnail_url.scheme not in {"http", "https"} or not thumbnail_url.netloc: #Generates a replacement\

                    video_id = ""
                    if hostname.endswith("youtube.com"):
                        video_id = parse_qs(parsed_url.query).get("v", [""])[0]
                    elif hostname == "youtu.be":
                        video_id = parsed_url.path.strip("/").split("/")[0]

                    if video_id:
                        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" #Generates a general website thumbnail png
                    else:
                        thumbnail = (
                            "https://www.google.com/s2/favicons?"
                            f"domain={parsed_url.netloc}&sz=128"
                        )

                """Store the final results"""
                results.append(
                    {
                        "title": title,
                        "url": url,
                        "thumbnail": thumbnail,
                    }
                )

            return results[:limit]
        except (requests.RequestException, ValueError) as error:
            print(f"[VoiceRecognition Error] Brave search failed: {error}")
            return []

    def _set_status(self, status, error=""):
        if self.state_manager:
            self.state_manager.set_status(status, error=error)

    def _record_result(self, text, result):
        if not self.state_manager:
            return

        result = result or {}
        self.state_manager.record_command(
            command=text,
            action=result.get("action", "Unknown"),
            result=result.get("response", ""),
            status=result.get("status", "Completed"),
            recommendations=result.get("recommendations"),
        )

    def _contains_command(self, normalized_text, compact_text, phrases):
        for phrase in phrases:
            if " " in phrase:
                if phrase in normalized_text:
                    return True
            elif phrase in compact_text:
                return True
        return False

    def _get_nao_service(self, name):
        try:
            if self.session and self.session.isConnected():
                return self.session.service(name)
        except Exception as e:
            print(f"[VoiceRecognition Warning] Could not get {name}: {e}")
        return None

    def _wake_up(self):
        motion = self._get_nao_service("ALMotion")
        if not motion:
            print("[VoiceRecognition] ALMotion unavailable; wake up skipped.")
            return

        action_started_at = time.perf_counter()
        try:
            motion.wakeUp()
        except Exception as e:
            print(f"[VoiceRecognition Error] Wake up command failed: {e}")
        finally:
            self._log_performance("Robot action (wake up)", action_started_at)

    def _rest(self):
        motion = self._get_nao_service("ALMotion")
        if not motion:
            print("[VoiceRecognition] ALMotion unavailable; rest skipped.")
            return

        action_started_at = time.perf_counter()
        try:
            motion.rest()
        except Exception as e:
            print(f"[VoiceRecognition Error] Rest command failed: {e}")
        finally:
            self._log_performance("Robot action (rest)", action_started_at)

    def _go_to_posture(self, posture_name, speed=0.6):
        posture = self._get_nao_service("ALRobotPosture")
        if not posture:
            print(
                f"[VoiceRecognition] ALRobotPosture unavailable; "
                f"{posture_name} skipped."
            )
            return

        self._wake_up()

        action_started_at = time.perf_counter()
        try:
            success = posture.goToPosture(posture_name, speed)
            if not success:
                print(
                    f"[VoiceRecognition Warning] "
                    f"Posture command {posture_name} was not completed."
                )
        except Exception as e:
            print(
                f"[VoiceRecognition Error] "
                f"Posture command {posture_name} failed: {e}"
            )
        finally:
            self._log_performance(
                f"Robot action (posture {posture_name})", action_started_at
            )
