import queue
import sys
import threading
import pyttsx3


class Speaker:
    def __init__(self, session, force_virtual=None):
        self.session = session

        # Determine virtual status
        if force_virtual is True:
            self.is_virtual = True
        else:
            try:
                if self.session and self.session.isConnected():
                    # Check for real robot service availability
                    self.session.service("ALSpeechRecognition")
                    self.is_virtual = False
                else:
                    self.is_virtual = True
            except Exception:
                self.is_virtual = True

        if self.is_virtual:
            self.speech_queue = queue.Queue()
            threading.Thread(
                target=self._laptop_tts_worker, daemon=True
            ).start()

    def _get_tts_service(self):
        """Dynamically retrieves an active TTS service proxy over the current session."""
        if not self.session:
            return None
        try:
            if self.session.isConnected():
                try:
                    return self.session.service("ALAnimatedSpeech")
                except Exception:
                    return self.session.service("ALTextToSpeech")
        except Exception:
            pass
        return None

    def _laptop_tts_worker(self):
        if sys.platform.startswith("win"):
            import ctypes

            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

        while True:
            text = self.speech_queue.get()
            try:
                engine = pyttsx3.init()
                engine.setProperty("rate", 160)
                engine.say(str(text))
                engine.runAndWait()
                del engine
            except Exception as e:
                print(f"[Speaker Error] pyttsx3 failed: {e}")
            finally:
                self.speech_queue.task_done()

    def speak(self, text):
        if self.is_virtual:
            self.speech_queue.put(text)

            def _virtual_bubble():
                try:
                    tts = self._get_tts_service()
                    if tts:
                        tts.say(str(text))
                except Exception as e:
                    print(f"[Speaker Error] Virtual speech bubble failed: {e}")

            threading.Thread(target=_virtual_bubble, daemon=True).start()

        else:
            def _nao_say():
                try:
                    print(f"[Speaker] Trying to speak: '{text}'")

                    if not self.session:
                        print("[Speaker] ERROR: session is None")
                        return

                    print(
                        f"[Speaker] Session connected: "
                        f"{self.session.isConnected()}"
                    )

                    tts = self._get_tts_service()

                    if not tts:
                        print("[Speaker] ERROR: TTS service unavailable")
                        return

                    print("[Speaker] TTS service obtained.")

                    tts.say(str(text))

                    print("[Speaker] Speech completed.")

                except Exception as e:
                    print(f"[Speaker Error] NAOqi TTS failed: {e}")

            threading.Thread(
                target=_nao_say,
                daemon=True
            ).start()