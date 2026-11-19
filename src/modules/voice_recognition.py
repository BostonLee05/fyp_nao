import os
import re
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np
import requests
from dotenv import load_dotenv

from faster_whisper import WhisperModel

from modules.gemini_service import GeminiService
from modules.nao_audio_transfer import NAOAudioTransfer
from database import execute_readonly_query, get_voice_commands, list_database_schema

load_dotenv()

class VoiceRecognitionService:
    """Record speech, convert it to text, and handle voice commands."""
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
        self.transcription_lock = threading.Lock()
        self._processed_recording_ids = set()
        self._processed_recording_ids_lock = threading.Lock()
        self.last_transcription_metrics = {}
        module_dir = Path(__file__).resolve().parent

        # Temp audio path for real NAO recording
        self.nao_audio_path = "/home/nao/nao_speech.wav"
        self.temp_audio_path = str(Path(tempfile.gettempdir()) / "nao_speech.wav")

        # Initialize Whisper model once for this service.
        print("[VoiceRecognition] Initializing Whisper model...")
        cpu_threads = max(1, min(4, (os.cpu_count() or 2) - 1))
        self.model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
            cpu_threads=cpu_threads,
            num_workers=1,
        )
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
                    audio_file = self._record_audio(duration)
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
            total_seconds = time.perf_counter() - interaction_started_at
            self._log_performance("Total interaction", interaction_started_at)
            if self.state_manager:
                metrics = dict(getattr(self.audio_transfer, "last_metrics", {}) or {})
                metrics.update(
                    dict(getattr(self, "last_transcription_metrics", {}) or {})
                )
                metrics.update({
                    "total_interaction_seconds": total_seconds,
                    "completed_wall": time.time(),
                })
                self.state_manager.record_performance(metrics)
            self.recording_lock.release()

    def _record_audio(self, max_duration=None):
        """Capture one fixed-duration utterance for predictable demos."""
        capture_duration = max_duration or self.DEFAULT_RECORDING_DURATION
        print(f"[VoiceRecognition] Recording fixed utterance ({capture_duration:.1f}s).")
        return self.audio_transfer.record_from_nao(capture_duration)

    def _transcribe(self, audio_path):
        """Converts audio file to text using faster-whisper VAD."""
        transcription_started_at = time.perf_counter()
        try:
            validation = self.audio_transfer.validate_wav(audio_path)
            if not validation["valid"]:
                print(
                    "[VoiceRecognition Warning] Invalid WAV skipped: %s"
                    % validation["error"]
                )
                return ""

            if not self.transcription_lock.acquire(blocking=False):
                print("[VoiceRecognition] Transcription already in progress. Skipping.")
                return ""

            try:
                segments, info = self.model.transcribe(
                    audio_path,
                    beam_size=1,
                    best_of=1,
                    temperature=0,
                    task="transcribe",
                    vad_filter=True,
                    vad_parameters={
                        "min_silence_duration_ms": 250,
                        "speech_pad_ms": 250,
                    },
                )
                text = "".join([segment.text for segment in segments]).strip()
                if hasattr(info, "language"):
                    print(
                        "[VoiceRecognition] Whisper language=%s probability=%.2f"
                        % (
                            info.language,
                            getattr(info, "language_probability", 0.0),
                        )
                    )
                return text
            finally:
                self.transcription_lock.release()
        except Exception as e:
            print(f"[VoiceRecognition Error] Transcription failed: {e}")
            return ""
        finally:
            transcription_seconds = time.perf_counter() - transcription_started_at
            self.last_transcription_metrics = {
                "vad_processing_seconds": 0.0,
                "whisper_transcription_seconds": transcription_seconds,
                "recording_to_transcription_seconds": transcription_seconds,
                "transcription_completion_wall": time.time(),
            }
            self._log_performance("Whisper transcription", transcription_started_at)

    def process_uploaded_audio_async(self, audio_path, recording_id=None):
        """Processes an optional Flask upload in one de-duplicated background task."""
        recording_id = recording_id or os.path.basename(audio_path)
        with self._processed_recording_ids_lock:
            if recording_id in self._processed_recording_ids:
                print(
                    "[VoiceRecognition] Duplicate upload ignored: %s" % recording_id
                )
                return False
            self._processed_recording_ids.add(recording_id)

        def _worker():
            try:
                text = self._transcribe(audio_path)
                print(
                    "[VoiceRecognition] Uploaded recording %s transcription: '%s'"
                    % (recording_id, text)
                )
                if text:
                    self._set_status("Processing command")
                    result = self._on_speech_recognized(text)
                    self._record_result(text, result)
            except Exception as error:
                print(
                    "[VoiceRecognition Error] Upload processing failed for %s: %s"
                    % (recording_id, error)
                )
                self._set_status("Error", str(error))
            finally:
                self._set_status("Ready/listening again")

        threading.Thread(
            target=_worker,
            name="voice-upload-" + str(recording_id),
            daemon=True,
        ).start()
        return True

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

        database_result = self._handle_database_question(text)
        if database_result:
            return database_result

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
        """Handles commands configured in voice_commands/voice_triggers."""
        normalized_text = text.lower()
        compact_text = normalized_text.replace(" ", "")

        search_result = self._handle_search_command(text)
        if search_result:
            return search_result

        try:
            commands = get_voice_commands()
        except Exception as error:
            print(f"[VoiceRecognition Warning] Could not load database commands: {error}")
            commands = []

        # Longest phrases win, preventing a generic trigger such as "rest"
        # from stealing a more specific user-defined command.
        matches = []
        for command in commands:
            for phrase in command.get("triggers", []) or []:
                phrase = " ".join(str(phrase).lower().split())
                if self._contains_command(normalized_text, compact_text, [phrase]):
                    matches.append((len(phrase), command))
                    break
        if matches:
            return self._execute_database_command(max(matches, key=lambda item: item[0])[1])

        if (
            "camera" in normalized_text
            or "vision" in normalized_text
            or "classroom" in normalized_text
            or "what do you see" in normalized_text
        ):
            return None

        return None

    def _execute_database_command(self, command):
        action = str(command.get("action", "robot")).lower()
        response = command.get("response", "Done.")
        if action == "stand_up":
            self._go_to_posture("StandInit")
        elif action == "sit_down":
            self._go_to_posture("Sit")
        elif action == "wake_up":
            self._wake_up()
        elif action == "rest":
            self._rest()
        elif action == "crouch":
            self._go_to_posture("Crouch")
        if self.speaker:
            self.speaker.speak(response, animated=action not in {"sit_down", "rest"})
        return {"action": action, "response": response, "status": "Completed"}

    def _handle_database_question(self, text):
        """Answer a data question using a Gemini-generated, read-only SELECT."""
        if not (self.gemini_service and self.use_gemini):
            return None
        try:
            schema = list_database_schema()
            sql = self.gemini_service.generate_sql(text, schema)
            if not sql:
                return None
            rows = execute_readonly_query(sql)
            prompt = (
                "Answer the user's classroom database question in one or two short sentences. "
                "Use only the query results below; if there are no rows, say no matching records were found.\n"
                f"Question: {text}\nQuery results: {rows}"
            )
            response = self.gemini_service.ask(prompt)
            if not response:
                return None
            if self.speaker:
                self.speaker.speak(response)
            return {"action": "Database Query", "response": response, "status": "Completed"}
        except Exception as error:
            print(f"[VoiceRecognition] Database question skipped: {error}")
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
