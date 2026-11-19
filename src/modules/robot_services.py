from integrated_monitoring import monitor
from speaker import Speaker

from modules.fall_recovery import FallRecovery
from modules.gemini_service import GeminiService
from modules.voice_recognition import VoiceRecognition
from modules.voice_state import voice_state
from modules.wake_audio import WakeAudio


class RobotServices:
    """Owns robot-adjacent background services used by Flask."""

    def __init__(self):
        self.speaker = None
        self.fall = None
        self.voice_recognition_service = None
        self.wake_audio = None
        self.gemini = None

    def ensure_gemini(self):
        if self.gemini is None:
            self.gemini = GeminiService()
            print(
                f"[System] Gemini Service status: "
                f"{'Ready' if getattr(self.gemini, 'client', None) else 'No API Key'}"
            )
        return self.gemini

    def start_for_session(self, session):
        self.ensure_gemini()

        if not session:
            voice_state.set_status("Error", "Robot session is not available.")
            return

        self.stop_robot_services()

        self.speaker = Speaker(session, state_manager=voice_state)

        try:
            self.fall = FallRecovery(session, self.speaker)
            self.fall.start()
        except Exception as e:
            self.fall = None
            print(f"[System Warning] Fall Recovery did not start: {e}")

        try:
            self.voice_recognition_service = VoiceRecognition(
                session,
                self.speaker,
                gemini_service=self.gemini,
                frame_provider=monitor.get_frame,
                state_manager=voice_state,
            )
        except Exception as e:
            self.voice_recognition_service = None
            voice_state.set_status("Error", f"Voice recognition did not start: {e}")
            print(f"[System Warning] Voice Recognition did not start: {e}")

        if self.voice_recognition_service:
            try:
                self.wake_audio = WakeAudio(
                    session,
                    self.speaker,
                    self.voice_recognition_service,
                    state_manager=voice_state,
                )
                self.wake_audio.start()
            except Exception as e:
                self.wake_audio = None
                voice_state.set_status("Error", f"Wake audio did not start: {e}")
                print(f"[System Warning] Wake Audio did not start: {e}")

    def stop_robot_services(self):
        if self.wake_audio:
            try:
                self.wake_audio.stop()
            except Exception as e:
                print(f"[System Warning] Wake Audio did not stop cleanly: {e}")

        if self.fall:
            try:
                self.fall.stop()
            except Exception as e:
                print(f"[System Warning] Fall Recovery did not stop cleanly: {e}")

        self.wake_audio = None
        self.voice_recognition_service = None
        self.fall = None
        self.speaker = None
        voice_state.set_speaking(False)
        voice_state.set_status("Ready/listening again")


robot_services = RobotServices()
