import queue
import sys
import threading
import pyttsx3


class Speaker(object):
    """Centralized, thread-safe speech module for Virtual and Real NAO."""

    def __init__(self, session, force_virtual=None):
        self.session = session
        self.tts = self.session.service("ALTextToSpeech")

        # Detect Virtual NAOqi
        if force_virtual is not None:
            self.is_virtual = force_virtual
        else:
            try:
                self.session.service("ALSpeechRecognition")
                self.is_virtual = False
            except Exception:
                self.is_virtual = True

        if self.is_virtual:
            print(
                "[Speaker] Virtual NAO detected: Laptop speaker audio active."
            )
            self.speech_queue = queue.Queue()
            self.worker_thread = threading.Thread(
                target=self._laptop_tts_worker, daemon=True
            )
            self.worker_thread.start()
        else:
            print("[Speaker] Real NAO detected: Hardware speakers active.")

    def _laptop_tts_worker(self):
        """Single worker thread processing laptop speech sequentially."""
        # Initialize COM on Windows background thread to prevent sapi5 locks
        if sys.platform.startswith("win"):
            try:
                import ctypes

                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

        # Initialize pyttsx3 engine ONCE for the worker thread lifetime
        engine = None
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 160)
        except Exception as e:
            print(f"[Speaker Error] Could not initialize pyttsx3: {e}")

        while True:
            text = self.speech_queue.get()
            if text is None:
                break

            if engine:
                try:
                    engine.say(str(text))
                    engine.runAndWait()
                except Exception as e:
                    print(f"[Speaker Error] Laptop TTS failed: {e}")
                    # Re-initialize engine if COM pipe broke
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("rate", 160)
                        engine.say(str(text))
                        engine.runAndWait()
                    except Exception:
                        pass

            self.speech_queue.task_done()

    def speak(self, text):
        """Non-blocking speech trigger: works across all modules."""

        # 1. Trigger NAOqi speech bubble / real robot hardware speaker
        def _nao_say():
            try:
                self.tts.say(str(text))
            except Exception as e:
                print(f"[Speaker Error] NAOqi TTS failed: {e}")

        threading.Thread(target=_nao_say, daemon=True).start()

        # 2. Add to laptop audio queue if running in Virtual Mode
        if self.is_virtual:
            self.speech_queue.put(text)