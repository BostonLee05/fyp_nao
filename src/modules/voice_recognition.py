import os
import re
import tempfile
import threading
import warnings
from pathlib import Path
import cv2
import numpy as np

from faster_whisper import WhisperModel

from modules.gemini_service import GeminiService
from modules.nao_audio_transfer import NAOAudioTransfer

warnings.filterwarnings(
    "ignore",
    message=r".*duckduckgo_search.*renamed to.*ddgs.*",
    category=RuntimeWarning,
)

try:
    from ddgs import DDGS as DDGSBackend
except ImportError:
    DDGSBackend = None

try:
    from duckduckgo_search import DDGS as DuckDuckGoSearchBackend
except ImportError:
    DuckDuckGoSearchBackend = None

class VoiceRecognition:
    SEARCH_RESULT_LIMIT = 3
    SEARCH_COMMAND_RE = re.compile(
        r"\b(?:find me|find|search for|search|give me|show me)\s+"
        r"(?P<kind>videos?|websites?|sites?|web\s*pages?|webpages?)\s+"
        r"(?:about|on|for)\s+"
        r"(?P<query>.+)",
        re.IGNORECASE,
    )

    def __init__(
        self,
        session=None,
        speaker=None,
        use_test_audio=True,
        gemini_service=None,
        use_gemini=True,
        frame_provider=None,
    ):
        self.session = session
        self.speaker = speaker
        self.use_test_audio = use_test_audio
        self.use_gemini = use_gemini
        self.gemini_service = gemini_service
        self.frame_provider = frame_provider
        self.recording_lock = threading.Lock()

        module_dir = Path(__file__).resolve().parent

        # Temp audio path for real NAO recording
        self.nao_audio_path = "/home/nao/nao_speech.wav"
        self.temp_audio_path = str(Path(tempfile.gettempdir()) / "nao_speech.wav")

        # Test fallback path for offline mode
        self.test_audio_path = str(module_dir / "nao_test.wav")

        # Initialize Whisper Model
        print("[VoiceRecognition] Initializing Whisper model...")
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
            test_audio_path=self.test_audio_path,
            use_test_audio=self.use_test_audio,
        )

    def listen_once_async(self, duration=4, on_complete=None):
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

    def listen_once(self, duration=4):
        if not self.recording_lock.acquire(blocking=False):
            print("[VoiceRecognition] Recording already in progress. Skipping.")
            return ""

        try:
            print(f"[VoiceRecognition] Starting one-shot recording ({duration}s)...")

            if self.audio_recorder:
                print("[VoiceRecognition] Using NAO ALAudioRecorder.")
                audio_file = self.audio_transfer.record_from_nao(duration=duration)
            else:
                print("[VoiceRecognition] Using test audio.")
                audio_file = self.audio_transfer.get_test_audio()

            print(f"[VoiceRecognition] Audio file: {audio_file}")

            if audio_file and os.path.exists(audio_file):
                print("[VoiceRecognition] Starting transcription...")

                text = self._transcribe(audio_file)

                print(f"[VoiceRecognition] Transcription: '{text}'")

                if text:
                    self._on_speech_recognized(text)

                return text

            print("[VoiceRecognition] No audio file available.")
            return ""

        finally:
            self.recording_lock.release()

    def _transcribe(self, audio_path):
        """Converts audio file to text using faster-whisper."""
        try:
            segments, _ = self.model.transcribe(
                audio_path,
                beam_size=5,
                task="translate",
            )
            transcription = "".join([segment.text for segment in segments]).strip()
            return transcription
        except Exception as e:
            print(f"[VoiceRecognition Error] Transcription failed: {e}")
            return ""

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
                    client_name,
                    0,
                    2,
                    11,
                    5,
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

    def _on_speech_recognized(self, text):
        """Triggers actions when speech is detected."""
        print(f"\n[VoiceRecognition] Heard: \"{text}\"")

        if not text:
            return

        # Simple keyword matching stays first so fixed classroom commands are fast
        # and keep working without Gemini.
        if self._handle_keyword_command(text):
            return

        if self.speaker and self.gemini_service and self.use_gemini:
            image = self._capture_camera_frame()

            prompt = text
            if image is not None:
                prompt = (
                    "Use the attached NAO camera image if it helps answer the question. "
                    "Reply in English only. "
                    f"User said: {text}"
                )

            response = self.gemini_service.ask(prompt, image=image)
            if response:
                print(f"[VoiceRecognition] Gemini: \"{response}\"")
                self.speaker.speak(response)

    def _handle_keyword_command(self, text):
        """Handles fixed voice commands with simple keyword matching."""
        normalized_text = text.lower()
        compact_text = normalized_text.replace(" ", "")

        if self._handle_search_command(text):
            return True

        if not self.speaker:
            return False

        if "attendance mode" in normalized_text:
            self.speaker.speak("Attendance Mode Activating...")
            return True

        if "hello" in normalized_text:
            self.speaker.speak("Hello, this is from pre-built keyword...")
            return True

        if self._contains_command(normalized_text, compact_text, ["stand up", "standup"]):
            self.speaker.speak("Standing up.")
            self._go_to_posture("StandInit")
            return True

        if self._contains_command(normalized_text, compact_text, ["sit down", "sitdown"]):
            self.speaker.speak("Sitting down.")
            self._go_to_posture("Sit")
            return True

        if self._contains_command(normalized_text, compact_text, ["wake up", "wakeup"]):
            self.speaker.speak("Waking up.")
            self._wake_up()
            return True

        if "rest" in normalized_text:
            self.speaker.speak("Going to rest mode.")
            self._rest()
            return True

        if "crouch" in normalized_text:
            self.speaker.speak("Crouching.")
            self._go_to_posture("Crouch")
            return True

        return False

    def _handle_search_command(self, text):
        search_request = self._parse_search_command(text)
        if not search_request:
            return False

        kind, query = search_request
        results = self._duckduckgo_search(kind, query, limit=self.SEARCH_RESULT_LIMIT)

        if not results:
            message = f"I could not find {kind} about {query}."
            print(f"[VoiceRecognition] {message}")
            if self.speaker:
                self.speaker.speak(message)
            return True

        noun = "Video" if kind == "videos" else "Website"
        lines = [
            f"{index}. {noun} Title : {result['title']} : {result['url']}"
            for index, result in enumerate(results, start=1)
        ]
        response = "\n".join(lines)

        print(f"[VoiceRecognition] DuckDuckGo {kind} results for '{query}':\n{response}")
        if self.speaker:
            self.speaker.speak(response)
        return True

    def _parse_search_command(self, text):
        text = " ".join(text.strip().split())
        match = self.SEARCH_COMMAND_RE.search(text)
        if not match:
            return None

        kind = match.group("kind").lower().replace(" ", "")
        query = match.group("query").strip(" .?!")
        if not query:
            return None

        if kind.startswith("video"):
            return "videos", query
        return "websites", query

    def _duckduckgo_search(self, kind, query, limit=3):
        backends = self._get_search_backends(kind)
        if not backends:
            message = (
                "DuckDuckGo search is not installed. "
                "Install it with: python -m pip install ddgs duckduckgo-search"
            )
            print(f"[VoiceRecognition Warning] {message}")
            if self.speaker:
                self.speaker.speak(message)
            return []

        last_error = None
        for backend in backends:
            results, error = self._search_with_backend(backend, kind, query, limit)
            if results:
                return results
            if error:
                last_error = error

        if kind == "videos":
            fallback_results = self._video_text_search_fallback(query, limit)
            if fallback_results:
                return fallback_results

        if last_error:
            print(f"[VoiceRecognition Error] DuckDuckGo search failed: {last_error}")
        return []

    def _get_search_backends(self, kind):
        if kind == "videos" and DDGSBackend is not None:
            candidates = [DDGSBackend]
        elif kind == "videos":
            candidates = [DuckDuckGoSearchBackend]
        else:
            candidates = [DDGSBackend, DuckDuckGoSearchBackend]

        backends = []
        for backend in candidates:
            if backend is not None and backend not in backends:
                backends.append(backend)
        return backends

    def _search_with_backend(self, backend, kind, query, limit):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with backend() as ddgs:
                    if kind == "videos":
                        raw_results = ddgs.videos(
                            query,
                            region="wt-wt",
                            safesearch="moderate",
                            max_results=limit,
                        )
                    else:
                        raw_results = ddgs.text(
                            query,
                            region="wt-wt",
                            safesearch="moderate",
                            max_results=limit,
                        )

                    return self._normalize_search_results(raw_results, limit=limit), None
        except Exception as e:
            return [], e

    def _video_text_search_fallback(self, query, limit):
        video_query = f"site:youtube.com/watch {query}"
        for backend in self._get_search_backends("websites"):
            results, _ = self._search_with_backend(
                backend,
                "websites",
                video_query,
                limit,
            )
            if results:
                return results
        return []

    def _normalize_search_results(self, raw_results, limit=3):
        results = []
        for item in raw_results or []:
            title = item.get("title") or item.get("heading")
            url = item.get("href") or item.get("url") or item.get("content")
            if not title or not url:
                continue

            results.append({"title": title, "url": url})
            if len(results) >= limit:
                break

        return results

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

        try:
            motion.wakeUp()
        except Exception as e:
            print(f"[VoiceRecognition Error] Wake up command failed: {e}")

    def _rest(self):
        motion = self._get_nao_service("ALMotion")
        if not motion:
            print("[VoiceRecognition] ALMotion unavailable; rest skipped.")
            return

        try:
            motion.rest()
        except Exception as e:
            print(f"[VoiceRecognition Error] Rest command failed: {e}")

    def _go_to_posture(self, posture_name, speed=0.6):
        posture = self._get_nao_service("ALRobotPosture")
        if not posture:
            print(
                f"[VoiceRecognition] ALRobotPosture unavailable; "
                f"{posture_name} skipped."
            )
            return

        self._wake_up()

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
