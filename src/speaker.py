import queue
import sys
import threading
import time
import pyttsx3


class Speaker:
    """Speak through NAO with body-language animation when available.

    ``ALAnimatedSpeech`` understands NAOqi animation tags embedded in the
    sentence.  We keep the laptop fallback plain because pyttsx3 should never
    try to pronounce those tags.
    """

    DEFAULT_GESTURE = "animations/Stand/Gestures/Explain_1"

    def __init__(self, session, force_virtual=None, state_manager=None):
        self.session = session
        self.state_manager = state_manager
        self._speech_lock = threading.Lock()
        self._active_speeches = 0

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

    def _get_speech_service(self, animated=True):
        """Dynamically retrieves an active TTS service proxy over the current session."""
        if not self.session:
            return None, False
        try:
            if self.session.isConnected():
                if not animated:
                    return self.session.service("ALTextToSpeech"), False
                try:
                    animated = self.session.service("ALAnimatedSpeech")
                    try:
                        animated.setBodyLanguageMode("contextual")
                    except Exception:
                        # Older NAOqi versions may not expose this optional
                        # setting even though animated speech is available.
                        pass
                    return animated, True
                except Exception:
                    return self.session.service("ALTextToSpeech"), False
        except Exception:
            pass
        return None, False

    def _prepare_gesture_pose(self):
        """Wake NAO and put it in the standing pose required by Stand gestures."""
        if not self.session:
            return

        try:
            motion = self.session.service("ALMotion")
            motion.wakeUp()
        except Exception as e:
            print(f"[Speaker Warning] Could not wake NAO for gesture speech: {e}")

        try:
            posture = self.session.service("ALRobotPosture")
            posture.goToPosture("StandInit", 0.6)
        except Exception as e:
            print(f"[Speaker Warning] Could not prepare StandInit pose: {e}")

    def set_animation_enabled(self, enabled):
        """Change speech animation preference and rest immediately when disabled."""
        if self.state_manager is not None:
            self.state_manager.set_animation_enabled(enabled)
        if not enabled:
            self.rest()

    def rest(self):
        """Safely return NAO to its resting posture."""
        if not self.session:
            return
        try:
            motion = self.session.service("ALMotion")
            motion.rest()
            print("[Speaker] NAO returned to rest posture.")
        except Exception as e:
            print(f"[Speaker Warning] Could not put NAO into rest posture: {e}")

    def _set_speaking(self, speaking):
        if self.state_manager is not None:
            try:
                self.state_manager.set_speaking(speaking)
            except Exception as e:
                print(f"[Speaker Warning] Could not update speaking state: {e}")

    def _speech_started(self):
        with self._speech_lock:
            self._active_speeches += 1
            if self._active_speeches == 1:
                self._set_speaking(True)

    def _speech_finished(self):
        with self._speech_lock:
            self._active_speeches = max(0, self._active_speeches - 1)
            if self._active_speeches == 0:
                self._set_speaking(False)

    def _animated_text(self, text):
        # Start a short, natural hand gesture while the sentence is spoken.
        # The tag is interpreted by ALAnimatedSpeech and is not sent to the
        # laptop TTS fallback.
        clean_text = str(text).replace("^", "")
        return f"^start({self.DEFAULT_GESTURE}) {clean_text}"

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
                self._speech_finished()
                self.speech_queue.task_done()

    def speak(self, text, animated=None):
        if animated is None:
            animated = (
                self.state_manager.is_animation_enabled()
                if self.state_manager is not None
                else False
            )
        if self.is_virtual:
            self._speech_started()
            self.speech_queue.put(text)

            def _virtual_bubble():
                try:
                    tts, animated_available = self._get_speech_service(animated=animated)
                    if tts:
                        speech_text = (
                            self._animated_text(text)
                            if animated_available
                            else str(text)
                        )
                        tts.say(speech_text)
                except Exception as e:
                    print(f"[Speaker Error] Virtual speech bubble failed: {e}")

            threading.Thread(target=_virtual_bubble, daemon=True).start()

        else:
            def _nao_say():
                self._speech_started()
                try:
                    print(f"[Speaker] Trying to speak: '{text}'")

                    if not self.session:
                        print("[Speaker] ERROR: session is None")
                        return

                    print(
                        f"[Speaker] Session connected: "
                        f"{self.session.isConnected()}"
                    )

                    tts, animated_available = self._get_speech_service(animated=animated)

                    if not tts:
                        print("[Speaker] ERROR: TTS service unavailable")
                        return

                    print("[Speaker] TTS service obtained.")

                    if animated_available:
                        self._prepare_gesture_pose()

                    speech_text = (
                        self._animated_text(text)
                        if animated_available
                        else str(text)
                    )
                    tts_started_at = time.perf_counter()
                    print(
                        f"[Speaker] Using {'ALAnimatedSpeech' if animated_available else 'ALTextToSpeech'}"
                    )
                    tts.say(speech_text)
                    print(
                        f"[Performance] Text-to-speech response (NAO): "
                        f"{time.perf_counter() - tts_started_at:.3f}s"
                    )

                    print("[Speaker] Speech completed.")

                except Exception as e:
                    print(f"[Speaker Error] NAOqi TTS failed: {e}")
                finally:
                    self._speech_finished()

            threading.Thread(
                target=_nao_say,
                daemon=True
            ).start()
