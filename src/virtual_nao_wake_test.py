import argparse
import os
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import qi

from modules.voice_recognition import VoiceRecognition
from modules.wake_audio import WakeAudio
from speaker import Speaker


TOPIC_CONTENT = """topic: ~wake_audio_virtual_test()
language: enu
u:(["hey nao" "hey now" "hi now" "hello nao" "hello now"]) $WakeAudio/WakeWord=$Dialog/LastInput
"""


class VirtualNAOAudioTransfer:
    """Virtual replacement for NAOAudioTransfer using this computer."""

    def __init__(
        self,
        local_path=None,
        test_audio_path=None,
        mode="mic",
        sample_rate=16000,
        channels=1,
    ):
        self.local_path = local_path or str(
            Path(tempfile.gettempdir()) / "virtual_nao_speech.wav"
        )
        self.test_audio_path = test_audio_path
        self.mode = mode
        self.sample_rate = sample_rate
        self.channels = channels

    def record_from_nao(self, duration=4):
        """Keeps the production method name, but records from the laptop mic."""
        if self.mode == "test":
            return self.get_test_audio()

        if self.mode == "type":
            return self._typed_audio_marker()

        print("[VirtualNAOAudioTransfer] Recording from laptop microphone.")
        try:
            return self._record_microphone(duration)
        except Exception as e:
            print(f"[VirtualNAOAudioTransfer Warning] Microphone recording failed: {e}")
            print("[VirtualNAOAudioTransfer] Falling back to typed speech.")
            return self._typed_audio_marker()

    def get_test_audio(self):
        if self.test_audio_path and os.path.exists(self.test_audio_path):
            print(f"[VirtualNAOAudioTransfer] Using test audio: {self.test_audio_path}")
            return self.test_audio_path

        print(
            f"[VirtualNAOAudioTransfer] Test audio not found: {self.test_audio_path}"
        )
        return self._typed_audio_marker()

    def download(self):
        """No-op virtual equivalent of downloading audio from NAO."""
        if os.path.exists(self.local_path):
            return self.local_path
        return None

    def cleanup_remote_audio(self):
        """No remote robot file exists in virtual mode."""
        return None

    def _record_microphone(self, duration):
        import numpy as np
        import sounddevice as sd

        duration = max(1, int(duration))
        Path(self.local_path).parent.mkdir(parents=True, exist_ok=True)

        print(f"[VirtualNAOAudioTransfer] Speak now for {duration} seconds...")
        recording = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )
        sd.wait()

        pcm = np.clip(recording, -1.0, 1.0)
        pcm = (pcm * 32767).astype(np.int16)

        with wave.open(self.local_path, "wb") as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(pcm.tobytes())

        print(f"[VirtualNAOAudioTransfer] Saved local audio: {self.local_path}")
        return self.local_path

    def _typed_audio_marker(self):
        # The virtual voice recognizer treats this marker as "ask for typed input".
        return "__typed_virtual_speech__"


class VirtualVoiceRecognition(VoiceRecognition):
    """VoiceRecognition wired to virtual audio capture for local testing."""

    def __init__(
        self,
        session=None,
        speaker=None,
        mode="mic",
        duration=4,
        use_gemini=True,
        frame_provider=None,
    ):
        self.virtual_mode = mode
        self.default_duration = duration
        module_dir = Path(__file__).resolve().parent / "modules"
        test_audio_path = str(module_dir / "nao_test.wav")

        super().__init__(
            session=session,
            speaker=speaker,
            use_test_audio=(mode == "test"),
            use_gemini=use_gemini,
            frame_provider=frame_provider,
        )

        self.audio_recorder = True
        self.file_manager = None
        self.audio_transfer = VirtualNAOAudioTransfer(
            local_path=self.temp_audio_path,
            test_audio_path=test_audio_path,
            mode=mode,
        )

    def listen_once(self, duration=None):
        duration = duration or self.default_duration
        if not self.recording_lock.acquire(blocking=False):
            print("[VirtualVoiceRecognition] Recording already in progress. Skipping.")
            return ""

        try:
            print(f"[VirtualVoiceRecognition] Listening once ({self.virtual_mode}).")
            audio_file = self.audio_transfer.record_from_nao(duration=duration)

            if audio_file == "__typed_virtual_speech__":
                text = input("[VirtualVoiceRecognition] Type what you said: ").strip()
            elif audio_file and os.path.exists(audio_file):
                print(f"[VirtualVoiceRecognition] Audio file: {audio_file}")
                text = self._transcribe(audio_file)
            else:
                print("[VirtualVoiceRecognition] No audio file available.")
                return ""

            print(f"[VirtualVoiceRecognition] Transcription: '{text}'")
            if text:
                self._on_speech_recognized(text)
            return text
        finally:
            self.recording_lock.release()


class ConsoleWakeInput:
    """Lets typed wake phrases trigger the same ALMemory wake event."""

    def __init__(self, session, wake_audio):
        self.session = session
        self.wake_audio = wake_audio
        self.running = False
        self.thread = None
        self.memory = None
        try:
            self.memory = self.session.service("ALMemory")
        except Exception:
            self.memory = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        print("[VirtualWakeTest] Type a wake phrase here if virtual speech input is unavailable.")
        while self.running:
            try:
                text = input("> ").strip()
            except EOFError:
                return
            except KeyboardInterrupt:
                return

            if not text:
                continue
            if text.lower() in {"quit", "exit", "stop"}:
                self.running = False
                return

            phrase = text.lower()
            if self.memory:
                try:
                    self.memory.raiseEvent("WakeAudio/WakeWord", phrase)
                    self._wait_after_wake_phrase(phrase)
                    continue
                except Exception as e:
                    print(f"[VirtualWakeTest Warning] Could not raise wake event: {e}")

            self.wake_audio._maybe_trigger_wake(phrase, 1.0)
            self._wait_after_wake_phrase(phrase)

    def _wait_after_wake_phrase(self, phrase):
        if phrase not in self.wake_audio.WAKE_PHRASES:
            return

        voice = self.wake_audio.voice_recognition
        duration = getattr(voice, "default_duration", 4)
        time.sleep(float(duration) + 2.0)


def connect_session(url):
    session = qi.Session()
    session.connect(url)
    return session


def load_virtual_dialog(session):
    dialog = None
    topic_name = None
    dialog_subscribed = False

    try:
        dialog = session.service("ALDialog")
        dialog.setLanguage("English")
        topic_name = dialog.loadTopicContent(TOPIC_CONTENT)
        dialog.activateTopic(topic_name)
        dialog.subscribe("VirtualWakeTest")
        dialog_subscribed = True
        print(f"[VirtualWakeTest] Loaded dialog topic: {topic_name}")
    except Exception as e:
        print(f"[VirtualWakeTest Warning] Dialog topic was not loaded: {e}")

    return dialog, topic_name, dialog_subscribed


def unload_virtual_dialog(dialog, topic_name, dialog_subscribed):
    if not dialog:
        return

    try:
        if dialog_subscribed:
            dialog.unsubscribe("VirtualWakeTest")
    except Exception:
        pass

    try:
        if topic_name:
            dialog.deactivateTopic(topic_name)
    except Exception:
        pass

    try:
        if topic_name:
            dialog.unloadTopic(topic_name)
    except Exception:
        pass


def parse_args():
    parser = argparse.ArgumentParser(
        description="Virtual NAO wake-word and voice-recognition test."
    )
    parser.add_argument(
        "--url",
        default="tcp://127.0.0.1:9559",
        help="Virtual NAOqi session URL.",
    )
    parser.add_argument(
        "--mode",
        choices=("mic", "type", "test"),
        default="mic",
        help="Speech input after wake: laptop microphone, typed text, or modules/nao_test.wav.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=4,
        help="Laptop microphone recording duration in seconds.",
    )
    parser.add_argument(
        "--no-gemini",
        action="store_true",
        help="Disable Gemini and only test fixed keyword responses.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        session = connect_session(args.url)
    except Exception as e:
        print(f"[VirtualWakeTest] Could not connect to virtual NAOqi at {args.url}: {e}")
        sys.exit(1)

    dialog, topic_name, dialog_subscribed = load_virtual_dialog(session)
    console_input = None

    speaker = Speaker(session, force_virtual=True)
    voice = VirtualVoiceRecognition(
        session=session,
        speaker=speaker,
        mode=args.mode,
        duration=args.duration,
        use_gemini=not args.no_gemini,
        frame_provider=None,
    )
    wake_audio = WakeAudio(session, speaker, voice)
    wake_audio.start()

    console_input = ConsoleWakeInput(session, wake_audio)
    console_input.start()

    print("[VirtualWakeTest] Ready.")
    print("[VirtualWakeTest] Say/type: hey nao, hey now, hi now, hello nao, or hello now.")
    print("[VirtualWakeTest] After NAO says 'Yes?', speak into your laptop mic.")
    print("[VirtualWakeTest] Use --mode type if microphone capture is not available.")
    print("[VirtualWakeTest] Type quit/exit/stop or press Ctrl+C to stop.")

    try:
        while console_input.running:
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        if console_input:
            console_input.stop()
        wake_audio.stop()
        if hasattr(voice, "stop"):
            voice.stop()
        unload_virtual_dialog(dialog, topic_name, dialog_subscribed)

        try:
            session.close()
        except Exception:
            pass
        print("[VirtualWakeTest] Stopped.")


if __name__ == "__main__":
    main()
