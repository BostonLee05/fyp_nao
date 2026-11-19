import os
import re
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
import requests
from dotenv import load_dotenv
from datetime import datetime

from faster_whisper import WhisperModel

from database import get_all_classes, get_voice_commands
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
    CLASS_QUESTION_RE = re.compile(
        r"\b(class|classes|subject|subjects|course|courses|timetable|schedule|"
        r"semester|description|lesson|lessons)\b|\bwhat\s+(?:am\s+i|do\s+i)\s+"
        r"(?:have|taking)\b",
        re.IGNORECASE,
    )
    CURRENT_CLASS_RE = re.compile(
        r"\b(right now|currently|at the moment|what class|which class|"
        r"class am i in|lesson now)\b",
        re.IGNORECASE,
    )
    TIMETABLE_RE = re.compile(
        r"\b(timetable|schedule|all classes|my classes|classes do i have|"
        r"subjects do i have)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        session: Optional[Any] = None,
        speaker: Optional[Any] = None,
        gemini_service: Optional[GeminiService] = None,
        use_gemini: bool = True,
        frame_provider: Optional[Any] = None,
        state_manager: Optional[Any] = None,
    ) -> None:
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
        self.audio_recorder, self.file_manager = self._get_robot_audio_services()

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
        self.stop_event = threading.Event()

    def _get_robot_audio_services(self) -> Tuple[Optional[Any], Optional[Any]]:
        if not self.session or not self.session.isConnected():
            return None, None

        try:
            audio_recorder = self.session.service("ALAudioRecorder")
            file_manager = self.session.service("ALFileManager")
            print("[VoiceRecognition] ALAudioRecorder connected.")
            print("[VoiceRecognition] ALFileManager connected.")
            return audio_recorder, file_manager
        except Exception as error:
            print(
                "[VoiceRecognition Warning] Could not initialize "
                f"NAO audio/file services: {error}"
            )
            return None, None

    @staticmethod
    def _log_performance(stage: str, started_at: float) -> None:
        print(f"[Performance] {stage}: {time.perf_counter() - started_at:.3f}s")

    def _ensure_vad_model(self) -> Optional[Any]:
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

    def listen_once_async(
        self,
        duration: Optional[float] = None,
        on_complete: Optional[Callable[[], None]] = None,
    ) -> bool:
        """Starts one recording/transcription pass in the background."""
        if self.stop_event.is_set() or self.recording_lock.locked():
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

    def listen_once(self, duration: Optional[float] = None) -> str:
        if self.stop_event.is_set() or not self.recording_lock.acquire(blocking=False):
            print("[VoiceRecognition] Recording already in progress. Skipping.")
            return ""

        interaction_started_at = time.perf_counter()
        try:
            print("[VoiceRecognition] Waiting for speech to start...")
            self._set_status("Recording")

            if self.stop_event.is_set():
                return ""

            audio_file = self._capture_audio(duration)

            if self.stop_event.is_set():
                return ""

            print(f"[VoiceRecognition] Audio file: {audio_file}")

            if not audio_file or not os.path.exists(audio_file):
                return self._handle_missing_audio()

            return self._process_audio_file(audio_file)
        except Exception as e:
            self._set_status("Error", str(e))
            raise

        finally:
            self._log_performance("Total interaction", interaction_started_at)
            self.recording_lock.release()

    def stop(self) -> None:
        """Cancel future and active voice-recognition work."""
        self.stop_event.set()
        self.audio_transfer.stop()

    def _capture_audio(self, duration: Optional[float]) -> Optional[str]:
        if not self.audio_recorder:
            print(
                "[VoiceRecognition Warning] ALAudioRecorder unavailable; "
                "real NAO recording cannot start."
            )
            return None

        capture_duration = (
            duration if duration is not None else self.DEFAULT_RECORDING_DURATION
        )
        print("[VoiceRecognition] Using NAO ALAudioRecorder.")
        print(
            f"[VoiceRecognition] Recording fixed utterance "
            f"({capture_duration:.1f}s)."
        )
        started_at = time.perf_counter()
        try:
            return self.audio_transfer.record_from_nao(capture_duration)
        finally:
            self._log_performance("Audio acquisition", started_at)

    def _handle_missing_audio(self) -> str:
        print("[VoiceRecognition] No audio file available.")
        self._set_status("Error", "No audio file available.")
        return ""

    def _process_audio_file(self, audio_file: str) -> str:
        print("[VoiceRecognition] Starting transcription...")
        self._set_status("Transcribing")
        text = self._transcribe(audio_file)
        print(f"[VoiceRecognition] Transcription: '{text}'")

        if text:
            self._process_transcript(text)
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

    def _process_transcript(self, text: str) -> None:
        self._set_status("Processing command")
        if self.speaker:
            self.speaker.speak("I'm thinking.", animated=False)

        started_at = time.perf_counter()
        try:
            result = self._on_speech_recognized(text)
        finally:
            self._log_performance("Command parsing and routing", started_at)

        self._record_result(text, result)
        self._set_status("Command completed")
        self._set_status("Ready/listening again")

    def _transcribe(self, audio_path: str) -> str:
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
    def _read_audio_for_whisper(audio_path: str) -> np.ndarray:
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

    def _extract_speech_audio(self, audio_path: str) -> str:
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
    def _read_audio_for_vad(audio_path: str) -> Any:
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

    def _capture_camera_frame(self) -> Optional[bytes]:
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
    def _on_speech_recognized(self, text: str) -> Dict[str, Any]:
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

        class_context = self._build_class_context(text)

        if self.gemini_service and self.use_gemini:
            image = self._capture_camera_frame()

            prompt = text
            if class_context:
                prompt = class_context
            if image is not None:
                camera_prompt = (
                    "Use the attached NAO camera image if it helps answer the question. "
                    "Reply in English only. "
                    f"User said: {text}"
                )
                prompt = (
                    f"{class_context} {camera_prompt}"
                    if class_context
                    else camera_prompt
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

    def _build_class_context(self, text: str) -> Optional[str]:
        """Build a Gemini prompt only for questions about registered subjects."""
        try:
            classes = get_all_classes()
        except Exception as error:
            print(f"[VoiceRecognition Warning] Could not load classes: {error}")
            return None

        normalized = text.casefold()
        named_subject = any(
            token and token in normalized
            for item in classes
            for token in (
                str(item.get("class_code") or "").casefold(),
                str(item.get("class_name") or "").casefold(),
            )
        )
        if not self.CLASS_QUESTION_RE.search(text) and not named_subject:
            return None

        selected = self._select_class_context(text, classes)
        if not selected:
            selected = classes
        if not selected:
            subject_context = "There are no registered subjects in the database."
        else:
            subject_context = " ".join(self._format_class_context(item) for item in selected)

        return (
            "Registered subject context: "
            f"{subject_context} "
            f"Original voice question: {text} "
            "Answer the original question using this context. Reply in concise English "
            "and do not invent subject details that are not provided."
        )

    @classmethod
    def _select_class_context(
        cls, text: str, classes: List[Dict[str, Any]], now: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Select current, named, or timetable-wide subjects for a class question."""
        normalized = text.casefold()
        if cls.CURRENT_CLASS_RE.search(text):
            current_time = now or datetime.now()
            day = current_time.strftime("%A")
            time_value = current_time.strftime("%H:%M")
            current = [
                item for item in classes
                if day in (item.get("schedule_days") or [])
                and item.get("schedule_start")
                and item.get("schedule_end")
                and item["schedule_start"] <= time_value < item["schedule_end"]
            ]
            if current:
                return current

        if cls.TIMETABLE_RE.search(text):
            return classes

        named = []
        for item in classes:
            code = str(item.get("class_code") or "").casefold()
            name = str(item.get("class_name") or "").casefold()
            if (code and code in normalized) or (name and name in normalized):
                named.append(item)
        return named

    @staticmethod
    def _format_class_context(subject: Dict[str, Any]) -> str:
        days = subject.get("schedule_days") or []
        days_text = ", ".join(str(day) for day in days) or "not specified"
        return (
            f"Subject code: {subject.get('class_code') or 'not specified'}; "
            f"subject name: {subject.get('class_name') or 'not specified'}; "
            f"semester: {subject.get('semester') or 'not specified'}; "
            f"description: {subject.get('description') or 'not specified'}; "
            f"weekly start time: {subject.get('schedule_start') or 'not specified'}; "
            f"end time: {subject.get('schedule_end') or 'not specified'}; "
            f"class days: {days_text}."
        )

    def _handle_keyword_command(self, text: str) -> Optional[Dict[str, Any]]:
        """Handles configured voice commands stored in Supabase."""
        normalized_text = text.lower()
        compact_text = normalized_text.replace(" ", "")

        search_result = self._handle_search_command(text)
        if search_result:
            return search_result

        if not self.speaker:
            return None

        local_result = self._handle_local_command(
            normalized_text,
            compact_text,
        )
        if local_result:
            return local_result

        command = self._find_database_command(normalized_text, compact_text)
        if command:
            return self._execute_database_command(command)

        return None

    def _handle_local_command(
        self, normalized_text: str, compact_text: str
    ) -> Optional[Dict[str, Any]]:
        """Handle robot movement commands locally, independent of Supabase."""
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

        return None

    @staticmethod
    def _find_database_command(
        normalized_text: str, compact_text: str
    ) -> Optional[Dict[str, Any]]:
        """Return the first enabled Supabase command matching the transcript."""
        try:
            commands = get_voice_commands()
        except Exception as e:
            print(f"[VoiceRecognition Warning] Could not load voice commands: {e}")
            return None

        for command in commands:
            for phrase in command.get("triggers", []) or []:
                normalized_phrase = " ".join(str(phrase).lower().split())
                compact_phrase = normalized_phrase.replace(" ", "")
                if normalized_phrase in normalized_text or compact_phrase in compact_text:
                    return command
        return None

    def _execute_database_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute response-only commands loaded from Supabase."""
        command_key = command.get("command_key")
        response = command.get("response") or "Command completed."
        self.speaker.speak(response)
        return {
            "action": command.get("action") or command_key or "Voice command",
            "response": response,
            "status": "Completed",
        }

    def _handle_search_command(self, text: str) -> Optional[Dict[str, Any]]:
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
    def _parse_search_command(self, text: str) -> Optional[Tuple[str, str]]:
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
    def _brave_search(
        self, kind: str, query: str, limit: int = 3
    ) -> List[Dict[str, Any]]:

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
                result = self._normalize_search_result(item, kind)
                if result:
                    results.append(result)

            return results[:limit]
        except (requests.RequestException, ValueError) as error:
            print(f"[VoiceRecognition Error] Brave search failed: {error}")
            return []

    @staticmethod
    def _normalize_search_result(
        item: Dict[str, Any], kind: str
    ) -> Optional[Dict[str, Any]]:
        title = item.get("title")
        url = item.get("url")
        parsed_url = urlparse(str(url))
        hostname = parsed_url.netloc.lower().split(":", 1)[0].rstrip(".")

        if (
            not title
            or parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
        ):
            return None
        if kind == "videos" and not (
            hostname == "youtu.be"
            or hostname == "youtube.com"
            or hostname.endswith(".youtube.com")
        ):
            return None

        return {
            "title": title,
            "url": url,
            "thumbnail": VoiceRecognition._resolve_thumbnail(
                item.get("thumbnail"), parsed_url, hostname
            ),
        }

    @staticmethod
    def _resolve_thumbnail(
        thumbnail: Any, parsed_url: Any, hostname: str
    ) -> str:
        if isinstance(thumbnail, dict):
            thumbnail = thumbnail.get("src") or thumbnail.get("original")

        thumbnail_url = urlparse(str(thumbnail)) if thumbnail else None
        if thumbnail_url and thumbnail_url.scheme in {"http", "https"} and thumbnail_url.netloc:
            return str(thumbnail)

        video_id = ""
        if hostname.endswith("youtube.com"):
            video_id = parse_qs(parsed_url.query).get("v", [""])[0]
        elif hostname == "youtu.be":
            video_id = parsed_url.path.strip("/").split("/")[0]

        if video_id:
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return f"https://www.google.com/s2/favicons?domain={parsed_url.netloc}&sz=128"

    def _set_status(self, status: str, error: str = "") -> None:
        if self.state_manager:
            self.state_manager.set_status(status, error=error)

    def _record_result(self, text: str, result: Optional[Dict[str, Any]]) -> None:
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

    def _contains_command(
        self, normalized_text: str, compact_text: str, phrases: List[str]
    ) -> bool:
        for phrase in phrases:
            if " " in phrase:
                if phrase in normalized_text:
                    return True
            elif phrase in compact_text:
                return True
        return False

    def _get_nao_service(self, name: str) -> Optional[Any]:
        try:
            if self.session and self.session.isConnected():
                return self.session.service(name)
        except Exception as e:
            print(f"[VoiceRecognition Warning] Could not get {name}: {e}")
        return None

    def _wake_up(self) -> None:
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

    def _rest(self) -> None:
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

    def _go_to_posture(self, posture_name: str, speed: float = 0.6) -> None:
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
