import os
import tempfile
import time
import threading
from pathlib import Path
from faster_whisper import WhisperModel
from modules.gemini_service import GeminiService

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
        self.temp_audio_path = str(Path(tempfile.gettempdir()) / "nao_speech.wav")

        # Test fallback path for offline mode
        self.test_audio_path = str(module_dir / "nao_test.wav")

        # Initialize Whisper Model
        print("[VoiceRecognition] Initializing Whisper model...")
        self.model = WhisperModel("base", device="cpu", compute_type="int8")

        # Initialize NAO Audio Recorder proxy if session exists
        self.audio_recorder = None
        if self.session and self.session.isConnected():
            try:
                self.audio_recorder = self.session.service("ALAudioRecorder")
            except Exception as e:
                print(f"[VoiceRecognition Warning] Could not get ALAudioRecorder service: {e}")

        if self.use_gemini and self.gemini_service is None:
            try:
                self.gemini_service = GeminiService()
            except Exception as e:
                self.gemini_service = None
                print(f"[VoiceRecognition Warning] Gemini Service did not initialize: {e}")

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
        """Records one audio window and transcribes it."""
        if not self.recording_lock.acquire(blocking=False):
            print("[VoiceRecognition] Recording already in progress. Skipping.")
            return ""

        try:
            if self.audio_recorder:
                # --- REAL NAO MODE ---
                audio_file = self._record_from_nao(duration=duration)
            else:
                # --- OFFLINE / TEST MODE ---
                audio_file = self._get_test_audio()

            if audio_file and os.path.exists(audio_file):
                text = self._transcribe(audio_file)
                if text:
                    self._on_speech_recognized(text)
                return text

            return ""
        finally:
            self.recording_lock.release()

    def _record_from_nao(self, duration=4):
        """Records audio from NAO's microphones into a temporary WAV file."""
        try:
            # Channels: [Left, Right, Front, Rear] -> [0, 0, 1, 0] uses front mic
            self.audio_recorder.startMicrophonesRecording(
                self.temp_audio_path, "wav", 16000, [0, 0, 1, 0]
            )
            time.sleep(duration)
            self.audio_recorder.stopMicrophonesRecording()
            return self.temp_audio_path
        except Exception as e:
            print(f"[VoiceRecognition Error] Failed to record from NAO: {e}")
            return None

    def _get_test_audio(self):
        """Simulates recording by using your local test file."""
        if not self.use_test_audio:
            print("[VoiceRecognition] No audio recorder available. Skipping test WAV fallback.")
            return None

        if os.path.exists(self.test_audio_path):
            return self.test_audio_path
        else:
            print(f"[VoiceRecognition] '{self.test_audio_path}' not found. Skipping offline iteration.")
            return None

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
