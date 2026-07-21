import sys
from threading import Timer

class VoiceRecognition(object):

    def __init__(self, session):
        self.session = session

        self.asr = self.session.service("ALSpeechRecognition")
        self.memory = self.session.service("ALMemory")
        self.tts = self.session.service("ALTextToSpeech")
        self.leds = self.session.service("ALLeds")

        self.service_name = "VoiceRecognitionModule"
        self.is_listening = False

        # Wake Word and Command Storage
        self.wake_word = "heynao"
        self.commands = {}

        # Internal State Management
        self.state = "WAITING_FOR_WAKE"  # 'WAITING_FOR_WAKE' or 'WAITING_FOR_COMMAND'
        self.timeout_timer = None

    def register_command(self, phrase, callback_function):
        """Register a command keyword and its corresponding function."""
        self.commands[phrase.lower()] = callback_function
        print(f"[Voice] Registered command: '{phrase}'")

    def start(self):
        """Starts the speech recognition service."""
        if not self.commands:
            print("[WARN] No commands registered!")
            return

        # Connect ALMemory event
        self.subscriber = self.memory.subscriber("WordRecognized")
        self.subscriber.signal.connect(self._on_word_recognized)

        # Set initial mode to listen for Wake Word only
        self._set_wake_mode()

        self.asr.subscribe(self.service_name)
        self.is_listening = True
        print("[Voice] Listening... Say 'Hey Nao' to wake me up.")

    def _set_wake_mode(self):
        """State 1: Listen ONLY for 'Hey Nao'."""
        self.state = "WAITING_FOR_WAKE"

        self.asr.pause(True)
        self.asr.setLanguage("English")
        self.asr.setVocabulary([self.wake_word], True)  # Word spotting enabled

        # Set eye LEDs to Dim Blue (Standby Mode)
        self.leds.fadeRGB("FaceLeds", 0x0000FF, 0.2)
        self.asr.pause(False)

    def _set_command_mode(self):
        """State 2: Listen for registered commands."""
        self.state = "WAITING_FOR_COMMAND"

        cmd_vocabulary = list(self.commands.keys()) + ["cancel", "exit"]

        self.asr.pause(True)
        self.asr.setVocabulary(cmd_vocabulary, True)

        # Set eye LEDs to Bright Green (Active Listening)
        self.leds.fadeRGB("FaceLeds", 0x00FF00, 0.2)
        self.asr.pause(False)

        # Audio Feedback
        self.tts.say("Yes?")

        # Start a 6-second timeout timer in case the user doesn't say a command
        if self.timeout_timer:
            self.timeout_timer.cancel()
        self.timeout_timer = Timer(6.0, self._on_command_timeout)
        self.timeout_timer.start()

    def _on_command_timeout(self):
        """Triggered if user says 'Hey Nao' but doesn't give a command within 6s."""
        print("[Voice] Command timeout reached.")
        self.tts.say("Oops!. I didn't hear a command.")
        self._set_wake_mode()

    def _on_word_recognized(self, value):
        """Callback triggered whenever NAO detects speech."""
        if not value or len(value) < 2:
            return

        # Strip out NAOqi word-spotting markers (<...>) and trim whitespace
        phrase = value[0].lower().replace("<...>", "").strip()
        confidence = value[1]

        # Ignore low-confidence hits
        if confidence < 0.45:
            return

        print(
            f"[Voice] [{self.state}] Heard: '{phrase}' (Confidence: {confidence:.2f})"
        )

        # ----------------------------------------------------
        # STATE 1: Waiting for 'Hey Nao'
        # ----------------------------------------------------
        if self.state == "WAITING_FOR_WAKE":
            # Check if wake word is in the cleaned phrase
            if self.wake_word in phrase:
                print("[Voice] Wake word detected!")
                self._set_command_mode()

        # ----------------------------------------------------
        # STATE 2: Waiting for Command
        # ----------------------------------------------------
        elif self.state == "WAITING_FOR_COMMAND":
            # Cancel timer since user said something
            if self.timeout_timer:
                self.timeout_timer.cancel()

            # Check matching command keys
            matched_command = None
            for cmd in self.commands:
                if cmd in phrase:
                    matched_command = cmd
                    break

            if matched_command:
                self.asr.pause(True)
                # Change eyes to White while processing action
                self.leds.fadeRGB("FaceLeds", 0xFFFFFF, 0.1)

                # Execute registered callback function
                self.commands[matched_command]()

                # Return back to wake mode after action finishes
                self._set_wake_mode()

            elif "cancel" in phrase:
                self.tts.say("Cancelled.")
                self._set_wake_mode()

            elif "exit" in phrase:
                self.tts.say("Goodbye!")
                self.stop()
                sys.exit(0)

    def stop(self):
        """Cleanup resources."""
        if self.timeout_timer:
            self.timeout_timer.cancel()

        if self.is_listening:
            try:
                self.asr.unsubscribe(self.service_name)
                self.is_listening = False
                self.leds.reset("FaceLeds")
                print("[Voice] Unsubscribed speech recognition service.")
            except Exception as e:
                print(f"[Voice] Cleanup error: {e}")