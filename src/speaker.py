# speaker.py

import queue
import sys
import threading
import pyttsx3

class Speaker:
    def __init__(self, session=None, force_virtual=None):
        self.tts = None
        self.session = session

        if self.session:
            try:
                self.tts = self.session.service("ALTextToSpeech")
            except Exception:
                self.tts = None

        if force_virtual is True:
            self.is_virtual = True
        else:
            try:
                self.session.service("ALSpeechRecognition")
                self.is_virtual = False
            except Exception:
                self.is_virtual = True

        if self.is_virtual:
            self.speech_queue = queue.Queue()
            threading.Thread(target=self._laptop_tts_worker, daemon=True).start()

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
        """Non-blocking speech output."""
        if not text:
            return

        if self.is_virtual:
            self.speech_queue.put(text)
            if self.tts:
                def _virtual_bubble():
                    try:
                        self.tts.say(str(text))
                    except Exception as e:
                        print(f"[Speaker Error] Speech bubble failed: {e}")
                threading.Thread(target=_virtual_bubble, daemon=True).start()
        else:
            def _nao_say():
                try:
                    if self.tts:
                        self.tts.say(str(text))
                except Exception as e:
                    print(f"[Speaker Error] NAOqi TTS failed: {e}")
            threading.Thread(target=_nao_say, daemon=True).start()