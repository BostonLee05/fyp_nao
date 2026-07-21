import threading
import time


class FallRecovery(threading.Thread):
    def __init__(self, session):
        super(FallRecovery, self).__init__()
        self.daemon = True  # Allows thread to close automatically when main program exits
        self.motion = session.service("ALMotion")
        self.posture = session.service("ALRobotPosture")
        self.tts = session.service("ALTextToSpeech")
        self.running = False

    def run(self):
        """Runs concurrently in the background."""
        self.running = True
        print("[FallRecovery] Daemon started. Monitoring posture in background...")

        while self.running:
            try:
                # Check current posture family
                current_family = self.posture.getPostureFamily()

                if current_family in ["LyingBelly", "LyingBack"]:
                    print(f"[FallRecovery] Fall detected! Posture: {current_family}")
                    self.tts.say("Oops! I have fallen down. Give me a second to stand back up.")

                    self.motion.wakeUp()
                    success = self.posture.goToPosture("StandInit", 0.6)

                    if success:
                        print("[FallRecovery] Fall recovered successfully!")
                        self.tts.say("I am back on my feet and ready to go.")
                    else:
                        print("[FallRecovery] Recovery failed.")
                        self.tts.say("I could not stand up. Please check my joints.")

            except Exception as e:
                print(f"[FallRecovery] Error during monitor loop: {e}")

            time.sleep(1.0)

    def stop(self):
        """Stops the monitoring loop gracefully."""
        self.running = False