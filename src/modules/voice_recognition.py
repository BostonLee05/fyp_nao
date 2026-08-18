import os
import tempfile
import threading
from pathlib import Path
from faster_whisper import WhisperModel

from modules.gemini_service import GeminiService
from modules.nao_audio_transfer import NAOAudioTransfer

class VoiceRecognition:
    def __init__(
        self,
        session=None,
        speaker=None,
        use_test_audio=True,
        gemini_service=None,
        use_gemini=True,
    ):
        self.session = session
        self.speaker = speaker
        self.use_test_audio = use_test_audio
        self.use_gemini = use_gemini
        self.gemini_service = gemini_service
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
                    print(
                        "[VoiceRecognition] ALFileManager methods:",
                        self.file_manager.metaObject().methodNames()
                    )
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
            segments, _ = self.model.transcribe(audio_path, beam_size=5)
            transcription = "".join([segment.text for segment in segments]).strip()
            return transcription
        except Exception as e:
            print(f"[VoiceRecognition Error] Transcription failed: {e}")
            return ""

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
            response = self.gemini_service.ask(text)
            if response:
                print(f"[VoiceRecognition] Gemini: \"{response}\"")
                self.speaker.speak(response)

    def _handle_keyword_command(self, text):
        """Handles fixed voice commands with simple keyword matching."""
        if not self.speaker:
            return False

        normalized_text = text.lower()

        if "attendance mode" in normalized_text:
            self.speaker.speak("Attendance Mode Activating...")
            return True

        if "hello" in normalized_text:
            self.speaker.speak("Hello, this is from pre-built keyword...")
            return True

        return False
