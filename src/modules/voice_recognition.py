import sys
import time
import threading
from PIL import Image
from threading import Timer
from modules.gemini_service import GeminiService
from speaker import Speaker

class VoiceRecognition(object):
    def __init__(self, session, speaker):
        self.session = session
        self.speaker = speaker
        self.gemini_service = GeminiService()

        self.memory = self.session.service("ALMemory")
        self.leds = self.session.service("ALLeds")

        # Check if running in Virtual Mode
        self.is_virtual = self.speaker.is_virtual
        try:
            self.asr = self.session.service("ALSpeechRecognition")
        except Exception:
            self.asr = None
            print("[Voice] Virtual NAO detected.")

        try:
            self.video_service = self.session.service("ALVideoDevice")
        except Exception:
            self.video_service = None
            print("[Voice WARN] ALVideoDevice service not available: %s")

        self.service_name = "VoiceRecognitionModule"
        self.is_listening = False

        self.wake_words = ["hey nao", "hey now", "hi nao", "hey know"]
        self.commands = {}
        self.state = "WAITING_FOR_WAKE"
        self.timeout_timer = None
        self.subscriber = None

    def _start_timeout_timer(self, duration=20.0):
        self._stop_timeout_timer()
        self.timeout_timer = Timer(duration, self._on_command_timeout)
        self.timeout_timer.start()

    def _stop_timeout_timer(self):
        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

    def register_command(self, phrase, callback_function):
        """Register a command keyword and its corresponding function."""
        self.commands[phrase.lower()] = callback_function
        print(f"[Voice] Registered command: '{phrase}'")

    def capture_frame(self):
        if not self.video_service or self.is_virtual:
            print("[Voice] Camera capture skipped (Virtual mode or missing ALVideoDevice).")
            return None

        try:
            # Parameters: Top camera (0), VGA 640x480 (2), RGB color space (11), 30 FPS
            client_name = self.video_service.subscribe("gemini_vision", 0, 2, 11, 30)

            try:
                nao_image = self.video_service.getImageRemote(client_name)
            finally:
                self.video_service.unsubscribe(client_name)

            if nao_image and len(nao_image) >= 7:
                width = nao_image[0]
                height = nao_image[1]
                array = nao_image[6]

                # Convert raw byte buffer into a PIL Image
                try:
                    img = Image.frombytes("RGB", (width, height), bytes(array))
                except (AttributeError, TypeError):
                    img = Image.fromstring("RGB", (width, height), str(bytearray(array)))
                return img
        except Exception as e:
            print("[Voice Error] Failed to capture camera frame: %s" % e)

        return None

    def start(self):
        """Starts the speech recognition service."""
        if not self.commands:
            print("[WARN] No commands registered!")

        if not self.asr:
            print("[Voice ERROR] ALSpeechRecognition is not available.")
            return

        try:
            # Subscribe the speech recognition service
            self.asr.subscribe(self.service_name)

            # Listen for recognized words
            self.subscriber = self.memory.subscriber("WordRecognized")
            self.subscriber.signal.connect(self._on_word_recognized)

            self._set_wake_mode()

            self.is_listening = True

            print(
                "[Voice] Listening active. "
                "Say 'Hey Nao' to activate commands."
            )

        except Exception as e:
            print(f"[Voice ERROR] Failed to start speech recognition: {e}")

    def _set_wake_mode(self):
        """Return to wake-word listening mode."""
        self._stop_timeout_timer()
        self.state = "WAITING_FOR_WAKE"

        if not self.asr:
            return

        try:
            self.asr.pause(True)

            self.asr.setLanguage("English")
            self.asr.setVocabulary(self.wake_words, True)

            self.asr.pause(False)

            print("[Voice] Wake mode restored. Say 'Hey Nao'.")

        except Exception as e:
            print(f"[Voice ERROR] Failed to restore wake mode: {e}")

            # Try to recover the speech recognition service
            try:
                self.asr.unsubscribe(self.service_name)
            except Exception:
                pass

            try:
                self.asr.subscribe(self.service_name)
                self.asr.pause(True)
                self.asr.setLanguage("English")
                self.asr.setVocabulary(self.wake_words, True)
                self.asr.pause(False)

                print("[Voice] Speech recognition restarted.")

            except Exception as restart_error:
                print(
                    f"[Voice ERROR] Could not restart speech recognition: "
                    f"{restart_error}"
                )

    def _set_command_mode(self, prompt=True):
        """State 2: Active chat mode waiting for commands/queries."""
        self._stop_timeout_timer()
        self.state = "WAITING_FOR_COMMAND"
        print("\n[Voice State] ---> WAITING_FOR_COMMAND")

        if self.asr:
            try:
                cmd_vocabulary = list(self.commands.keys()) + ["exit"]
                self.asr.pause(True)
                self.asr.setVocabulary(cmd_vocabulary, True)
            except Exception:
                pass

        try:
            self.leds.fadeRGB("FaceLeds", 0x0000FF, 0.2)  # Blue LEDs
        except Exception:
            pass

        # Speak "Yes?" only on the initial wake word trigger
        if prompt:
            self.speaker.speak("Yes?")

        if self.asr:
            try:
                self.asr.pause(False)
            except Exception:
                pass

        # Start 10s idle timer after speaking is done and mic is live
        self._start_timeout_timer(20.0)

    def _on_command_timeout(self):
        """Triggered if user is silent for 10s in WAITING_FOR_COMMAND state."""
        if self.state == "WAITING_FOR_COMMAND":
            print("[Voice] Command timeout reached.")
            self.speaker.speak("Oops! Command timeout. Call me again when you need me!")
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

        # STATE 1: Waiting for wake phrase ("Hey Nao")
        if self.state == "WAITING_FOR_WAKE":
            if any(w in phrase for w in self.wake_words):
                print("[Voice] Wake word detected!")
                self._set_command_mode(prompt=True)

        # STATE 2: Active Chat Loop
        elif self.state == "WAITING_FOR_COMMAND":

            # Ignore NAO's own prompt audio
            if phrase == "yes":
                return

            # Explicit Exit Command: Return to wake word state
            if "exit" in phrase:
                self._stop_timeout_timer()
                if self.asr:
                    try:
                        self.asr.pause(True)
                    except Exception:
                        pass
                self.speaker.speak("Goodbye!")
                self._set_wake_mode()
                return

            # Match registered Python commands
            matched_command = None
            for cmd in self.commands:
                if cmd in phrase:
                    matched_command = cmd
                    break

            if matched_command:
                self._stop_timeout_timer()

                print(f"[Voice] Executing command: '{matched_command}'")

                try:
                    self.leds.fadeRGB("FaceLeds", 0x00FF00, 0.2)  # Green LEDs
                except Exception:
                    pass

                try:
                    self.commands[matched_command]()
                except Exception as e:
                    print(f"[Voice] Callback execution error: {e}")

                # Stay in command mode & listen for the next interaction
                self._set_command_mode(prompt=False)

            # Continuous Gemini Chat Query
            else:
                query_prompt = phrase.replace("yes", "").strip()

                if not query_prompt:
                    return

                # Pause timer and ASR while Gemini processes and speaks
                self._stop_timeout_timer()
                self.state = "PROCESSING_GEMINI"

                if self.asr:
                    try:
                        self.asr.pause(True)
                    except Exception:
                        pass

                def handle_gemini_query():
                    print(f"[Voice -> Gemini] Processing query: '{query_prompt}'")

                    try:
                        self.leds.fadeRGB("FaceLeds", 0x00FF00, 0.2)  # Yellow LEDs
                    except Exception:
                        pass

                    # Check if user's phrase implies looking at something
                    vision_keywords = ["see", "look", "what is this", "what's this", "identify", "holding", "show"]
                    needs_vision = any(kw in query_prompt for kw in vision_keywords)

                    image_frame = None
                    if needs_vision:
                        self.speaker.speak("Let me have a look...")
                        image_frame = self.capture_frame()
                    else:
                        self.speaker.speak("I'm thinking...")

                    if self.gemini_service:
                        ai_reply = self.gemini_service.ask(query_prompt, image=image_frame)
                        print(f"[Gemini Response] {ai_reply}")
                        self.speaker.speak(ai_reply)
                    else:
                        print("[Voice Error] Failed to generate Gemini response.")

                    # Loop back to command mode: enable mic and start 10s timer NOW
                    self._set_command_mode(prompt=False)

                threading.Thread(target=handle_gemini_query).start()

    def stop(self):
        """Cleanup resources."""

        if self.timeout_timer:
            self.timeout_timer.cancel()
            self.timeout_timer = None

        if self.subscriber:
            try:
                self.subscriber.signal.disconnect(
                    self._on_word_recognized
                )
            except Exception:
                pass

            self.subscriber = None

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

        print("[Voice] Speech recognition stopped.")