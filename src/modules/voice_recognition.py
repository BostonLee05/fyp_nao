import sys
import threading
from threading import Timer

class VoiceRecognition(object):
    def __init__(self, session, speaker):
        self.session = session
        self.speaker = speaker

        self.memory = self.session.service("ALMemory")
        self.leds = self.session.service("ALLeds")

        # Check if running in Virtual Mode
        self.is_virtual = self.speaker.is_virtual
        try:
            self.asr = self.session.service("ALSpeechRecognition")
        except Exception:
            self.asr = None
            print("[Voice] Virtual NAO detected.")

        self.service_name = "VoiceRecognitionModule"
        self.is_listening = False
        self.wake_words = ["hey nao", "hey now", "hi nao", "hey know"]
        self.commands = {}
        self.state = "WAITING_FOR_WAKE"
        self.timeout_timer = None
        self.subscriber = None

    def register_command(self, phrase, callback_function):
        """Register a command keyword and its corresponding function."""
        self.commands[phrase.lower()] = callback_function
        print(f"[Voice] Registered command: '{phrase}'")

    def start(self):
        """Starts the speech recognition service."""
        if not self.commands:
            print("[WARN] No commands registered!")

        self.subscriber = self.memory.subscriber("WordRecognized")
        self.subscriber.signal.connect(self._on_word_recognized)
        self._set_wake_mode()
        self.is_listening = True
        print("[Voice] Listening active. Say 'Hey Nao' to activate commands.")

    def _set_wake_mode(self):
        self.state = "WAITING_FOR_WAKE"

        if self.asr:
            try:
                self.asr.pause(True)
                self.asr.setLanguage("English")
                self.asr.setVocabulary(self.wake_words, True)
                self.asr.pause(False)
            except Exception:
                pass

        try:
            self.leds.fadeRGB("FaceLeds", 0x0000FF, 0.2)
        except Exception:
            pass

    def _set_command_mode(self):
        """State 2: Listen for commands."""
        self.state = "WAITING_FOR_COMMAND"
        print("\n[Voice State] ---> WAITING_FOR_COMMAND")

        if self.asr:
            try:
                cmd_vocabulary = list(self.commands.keys()) + ["cancel", "exit"]
                self.asr.pause(True)
                self.asr.setVocabulary(cmd_vocabulary, True)
            except Exception:
                pass

        try:
            self.leds.fadeRGB("FaceLeds", 0x00FF00, 0.2)
        except Exception:
            pass

        # Speaks 'Yes?' without blocking
        self.speaker.speak("Yes?")

        if self.asr:
            try:
                self.asr.pause(False)
            except Exception:
                pass

        # 10 second window to hear command
        if self.timeout_timer:
            self.timeout_timer.cancel()
        self.timeout_timer = Timer(10.0, self._on_command_timeout)
        self.timeout_timer.start()

    def _on_command_timeout(self):
        """Triggered if user doesn't give a command within 10s."""
        if self.state == "WAITING_FOR_COMMAND":
            print("[Voice] Command timeout reached.")
            self.speaker.speak("Oops! I didn't hear a command.")
            self._set_wake_mode()

    def _on_word_recognized(self, value):
        """Callback triggered whenever NAO detects speech."""
        if not value or len(value) < 2:
            return

        phrase = value[0].lower().replace("<...>", "").strip()
        confidence = value[1]

        print(f"[Voice Debug] [{self.state}] Detected: '{phrase}' (Confidence: {confidence:.2f})")

        threshold = 0.35 if self.state == "WAITING_FOR_COMMAND" else 0.45
        if confidence < threshold:
            return

        # STATE 1: Waiting for 'Hey Nao'
        if self.state == "WAITING_FOR_WAKE":
            if any(w in phrase for w in self.wake_words):
                print("[Voice] Wake word detected!")
                self._set_command_mode()

        # STATE 2: Waiting for Command
        elif self.state == "WAITING_FOR_COMMAND":
            # Ignore NAO's own 'yes' audio picked up by mic
            if phrase == "yes":
                return

            matched_command = None
            for cmd in self.commands:
                if cmd in phrase:
                    matched_command = cmd
                    break

            if matched_command:
                if self.timeout_timer:
                    self.timeout_timer.cancel()

                print(f"[Voice] Executing command: '{matched_command}'")

                try:
                    self.leds.fadeRGB("FaceLeds", 0xFFFFFF, 0.1)
                except Exception:
                    pass

                try:
                    self.commands[matched_command]()
                except Exception as e:
                    print(f"[Voice] Callback execution error: {e}")

                self._set_wake_mode()

            elif "cancel" in phrase:
                if self.timeout_timer:
                    self.timeout_timer.cancel()
                self.speaker.speak("Command cancelled.")
                self._set_wake_mode()

            elif "exit" in phrase:
                if self.timeout_timer:
                    self.timeout_timer.cancel()
                self.speaker.speak("Goodbye!")
                self._set_wake_mode()

    def stop(self):
        """Cleanup resources."""
        if self.timeout_timer:
            self.timeout_timer.cancel()

        if self.is_listening:
            if self.asr:
                try:
                    self.asr.unsubscribe(self.service_name)
                except Exception:
                    pass
            try:
                self.leds.reset("FaceLeds")
            except Exception:
                pass
            self.is_listening = False
            print("[Voice] Unsubscribed speech recognition service.")