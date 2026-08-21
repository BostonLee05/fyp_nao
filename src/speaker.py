import queue
import sys
import threading
import pyttsx3


class Speaker:
    def __init__(self, session, force_virtual=None):
        self.tts = None

        if session:
            try:
                # Primary attempt using ALAnimatedSpeech for gesture-driven TTS
                self.tts = session.service("ALAnimatedSpeech")
            except Exception:
                try:
                    # Fallback to standard ALTextToSpeech if animated speech isn't loaded
                    self.tts = session.service("ALTextToSpeech")
                except Exception:
                    self.tts = None
        self.session = session

        # Determine virtual status
        if force_virtual is True:
            self.is_virtual = True
        else:
            try:
                # Check for real robot service availability
                session.service("ALSpeechRecognition")
                self.is_virtual = False
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
        """Non-blocking speech trigger across all environments."""
        if self.is_virtual:
            # 1. Trigger laptop audio via pyttsx3
            self.speech_queue.put(text)

            # 2. Trigger NAOqi speech bubble on the virtual robot avatar
            if self.tts:

                def _virtual_bubble():
                    try:
                        self.tts.say(str(text))
                    except Exception as e:
                        print(
                            f"[Speaker Error] Virtual speech bubble failed: {e}"
                        )
            def _virtual_bubble():
                try:
                    tts = self._get_tts_service()
                    if tts:
                        tts.say(str(text))
                except Exception as e:
                    print(f"[Speaker Error] Virtual speech bubble failed: {e}")

                threading.Thread(target=_virtual_bubble, daemon=True).start()
            threading.Thread(target=_virtual_bubble, daemon=True).start()

        else:
            # For Real NAO: spawn a background thread for animated speech
            def _nao_say():
                try:
                    if self.tts:
                        self.tts.say(str(text))
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

            threading.Thread(target=_nao_say, daemon=True).start()
            threading.Thread(
                target=_nao_say,
                daemon=True
            ).start()
