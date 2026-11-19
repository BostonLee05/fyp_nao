import threading
import time

from database import get_voice_wake_phrases


class WakeAudio:
    """NAOqi wake-word listener using ALSpeechRecognition."""

    WAKE_PHRASES = ["hey nao", "hey now", "hi now", "hello now", "hello nao"]

    def __init__(
        self,
        session,
        speaker,
        voice_recognition,
        confidence_threshold=0.45,
        cooldown_seconds=3.0,
        state_manager=None,
    ):
        self.session = session
        self.speaker = speaker
        self.voice_recognition = voice_recognition
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state_manager = state_manager
        try:
            self.wake_phrases = get_voice_wake_phrases() or list(self.WAKE_PHRASES)
        except Exception as e:
            self.wake_phrases = list(self.WAKE_PHRASES)
            print(f"[WakeAudio Warning] Could not load wake phrases: {e}")

        self.memory = self.session.service("ALMemory")
        self.speech_recognition = None
        try:
            self.speech_recognition = self.session.service("ALSpeechRecognition")
        except Exception as e:
            print(
                "[WakeAudio Warning] ALSpeechRecognition unavailable. "
                f"Using ALMemory WordRecognized events only: {e}"
            )

        self.event_connections = []
        self.running = False
        self.last_triggered_at = 0.0
        self.lock = threading.RLock()

    def start(self):
        with self.lock:
            if self.running:
                return

            if self.speech_recognition:
                self._configure_vocabulary()
            self._subscribe_event("WordRecognized", self._on_word_recognized)
            self._subscribe_event("Dialog/LastInput", self._on_dialog_input)
            self._subscribe_event("WakeAudio/WakeWord", self._on_wake_event)
            if self.speech_recognition:
                self.speech_recognition.subscribe("WakeAudio")
            self.running = True
            self._set_status("Waiting for wake word")
            print("[WakeAudio] Listening for wake phrases. Call 'Hey Nao' to wake.")

    def stop(self):
        with self.lock:
            self.running = False

            if self.speech_recognition:
                try:
                    self.speech_recognition.unsubscribe("WakeAudio")
                except Exception:
                    pass

            for subscriber, connection in self.event_connections:
                try:
                    if hasattr(connection, "disconnect"):
                        connection.disconnect()
                    else:
                        subscriber.signal.disconnect(connection)
                except Exception:
                    pass

            self.event_connections = []
            self._set_status("Ready/listening again")
            print("[WakeAudio] Stopped.")

    def _subscribe_event(self, event_name, callback):
        try:
            subscriber = self.memory.subscriber(event_name)
            connection = subscriber.signal.connect(callback)
            self.event_connections.append((subscriber, connection))
        except Exception as e:
            print(f"[WakeAudio Warning] Could not subscribe to {event_name}: {e}")

    def _configure_vocabulary(self):
        if not self.speech_recognition:
            return

        try:
            self.speech_recognition.pause(True)
            try:
                self.speech_recognition.setLanguage("English")
            except Exception as e:
                print(f"[WakeAudio Warning] Could not set language: {e}")
            self.speech_recognition.setVocabulary(self.wake_phrases, False)
        finally:
            try:
                self.speech_recognition.pause(False)
            except Exception:
                pass

    def _on_word_recognized(self, value):
        if not self.running or not value or len(value) < 2:
            return
        """ Text Cleaning """
        phrase = str(value[0]).strip().lower()
        try:
            """ Confidence score """
            confidence = float(value[1])
        except (TypeError, ValueError):
            confidence = 0.0

        self._maybe_trigger_wake(phrase, confidence)

    def _on_dialog_input(self, value):
        if not self.running:
            return

        phrase = str(value).strip().lower()
        self._maybe_trigger_wake(phrase, 1.0)

    def _on_wake_event(self, value):
        if not self.running:
            return

        phrase = str(value).strip().lower()
        self._maybe_trigger_wake(phrase, 1.0)

    def _maybe_trigger_wake(self, phrase, confidence):
        if phrase not in self.wake_phrases:
            return

        if confidence < self.confidence_threshold:
            print(
                f"[WakeAudio] Ignored '{phrase}' with low confidence {confidence:.2f}."
            )
            return

        now = time.time()
        with self.lock:
            if now - self.last_triggered_at < self.cooldown_seconds:
                return
            self.last_triggered_at = now

        threading.Thread(
            target=self._handle_wake_phrase,
            args=(phrase, confidence),
            daemon=True,
        ).start()

    def _handle_wake_phrase(self, phrase, confidence):
        print(f"[WakeAudio] Wake phrase heard: '{phrase}' ({confidence:.2f})")
        self._set_status("Wake word detected")
        self._pause_wake_listening()

        try:
            if self.speaker:
                self.speaker.speak("Yes?")

            # Give the short reply a moment so it is less likely to be recorded.
            time.sleep(1.0)

            started = self.voice_recognition.listen_once_async(
                on_complete=self._resume_wake_listening,
            )
            if not started:
                self._resume_wake_listening()
        except Exception as e:
            print(f"[WakeAudio Error] Wake handling failed: {e}")
            self._set_status("Error", str(e))
            self._resume_wake_listening()

    def _pause_wake_listening(self):
        if not self.speech_recognition:
            return

        try:
            self.speech_recognition.unsubscribe("WakeAudio")
        except Exception:
            pass

    def _resume_wake_listening(self):
        if not self.running:
            return

        if not self.speech_recognition:
            self._set_status("Ready/listening again")
            print("[WakeAudio] Wake listening resumed.")
            return

        try:
            self.speech_recognition.subscribe("WakeAudio")
            self._set_status("Waiting for wake word")
            print("[WakeAudio] Wake listening resumed.")
        except Exception as e:
            self._set_status("Error", str(e))
            print(f"[WakeAudio Error] Could not resume wake listening: {e}")

    def _set_status(self, status, error=""):
        if self.state_manager:
            self.state_manager.set_status(status, error=error)
