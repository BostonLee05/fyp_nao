import os
import time
from pathlib import Path

class NAOAudioTransfer:
    """Handles NAO audio capture, download, and local test-audio fallback."""

    def __init__(
        self,
        audio_recorder=None,
        file_manager=None,
        remote_path="/home/nao/nao_speech.wav",
        local_path=None,
        test_audio_path=None,
        use_test_audio=True,
    ):
        self.audio_recorder = audio_recorder
        self.file_manager = file_manager
        self.remote_path = remote_path
        self.local_path = local_path
        self.test_audio_path = test_audio_path
        self.use_test_audio = use_test_audio

    def record_from_nao(self, duration=4):
        """Records audio on NAO and downloads it to the local machine."""
        if not self.audio_recorder:
            print("[NAOAudioTransfer Warning] No ALAudioRecorder available.")
            return None

        try:
            print(f"[NAOAudioTransfer] Recording on NAO: {self.remote_path}")
            self.audio_recorder.startMicrophonesRecording(
                self.remote_path, "wav", 16000, [0, 0, 1, 0]
            )

            print(f"[NAOAudioTransfer] Recording for {duration} seconds...")
            time.sleep(duration)

            self.audio_recorder.stopMicrophonesRecording()
            print("[NAOAudioTransfer] NAO recording stopped.")

            return self.download()
        except Exception as e:
            print(f"[NAOAudioTransfer Error] Failed to record from NAO: {e}")
            return None

    def get_test_audio(self):
        """Returns the local test WAV if offline fallback is enabled."""
        if not self.use_test_audio:
            print("[NAOAudioTransfer] Test audio fallback disabled.")
            return None

        if self.test_audio_path and os.path.exists(self.test_audio_path):
            return self.test_audio_path

        print(
            f"[NAOAudioTransfer] '{self.test_audio_path}' not found. "
            "Skipping offline fallback."
        )
        return None

    def download(self):
        if not self.file_manager:
            print("[NAOAudioTransfer Warning] No ALFileManager available.")
            return None

        try:
            Path(self.local_path).parent.mkdir(parents=True, exist_ok=True)

            if hasattr(self.file_manager, "getFile"):
                self.file_manager.getFile(self.remote_path, self.local_path)
            elif hasattr(self.file_manager, "copyFileFromRobot"):
                self.file_manager.copyFileFromRobot(self.remote_path, self.local_path)
            elif hasattr(self.file_manager, "copy"):
                self.file_manager.copy(self.remote_path, self.local_path)
            else:
                raise AttributeError(
                    "No supported file transfer method found on ALFileManager."
                )

            if os.path.exists(self.local_path):
                print(f"[NAOAudioTransfer] Downloaded audio to {self.local_path}")
                self.cleanup_remote_audio()
                return self.local_path

            print(
                "[NAOAudioTransfer Warning] "
                f"Transfer completed but local file was not found: {self.local_path}"
            )
            return None

        except Exception as e:
            print(f"[NAOAudioTransfer Error] Could not download NAO audio: {e}")
            return None

    def cleanup_remote_audio(self):
        """Removes the remote WAV from NAO after a successful download."""
        if not self.file_manager:
            return

        try:
            if hasattr(self.file_manager, "removeFile"):
                self.file_manager.removeFile(self.remote_path)
                print(f"[NAOAudioTransfer] Removed remote audio {self.remote_path}")
            elif hasattr(self.file_manager, "deleteFile"):
                self.file_manager.deleteFile(self.remote_path)
                print(f"[NAOAudioTransfer] Removed remote audio {self.remote_path}")
        except Exception as e:
            print(f"[NAOAudioTransfer Warning] Could not remove remote audio: {e}")
