import threading
import time

class FallRecovery(threading.Thread):
    def __init__(self, session, speaker):
        super(FallRecovery, self).__init__()
        self.daemon = True
        self.session = session
        self.speaker = speaker

        self.motion = self.session.service("ALMotion")
        self.posture = self.session.service("ALRobotPosture")

        self.running = False
        self.is_recovering = False  # Lock to prevent multiple simultaneous triggers

    def run(self):
        self.running = True
        print("[FallRecovery] Daemon started. Monitoring posture in background...")

        fall_postures = ["LyingBelly", "LyingBack", "LyingLeft", "LyingRight", "Belly", "Back", "Lying"]

        while self.running:
            try:
                current_family = self.posture.getPostureFamily()

                if current_family in fall_postures and not self.is_recovering:
                    self.is_recovering = True
                    print(f"[FallRecovery] ALERT: Fall detected! Posture: {current_family}")

                    # killAll Running Tasks
                    try:
                        bm = self.session.service("ALBehaviorManager")
                        if bm.getRunningBehaviors():
                            print("[FallRecovery] Stopping active behaviors ...")
                            bm.stopAllBehaviors()
                    except Exception as e:
                        print(f"[FallRecovery] Error stopping behaviors: {e}")

                    try:
                        self.motion.killAll()
                    except Exception as e:
                        print(f"[FallRecovery] Error killing motions: {e}")

                    self.speaker.speak("Oops! I have fallen down. Stopping all movements to stand up.")

                    time.sleep(0.5)
                    self.motion.wakeUp()

                    # Attempt standing posture
                    success = self.posture.goToPosture("StandInit", 0.6)

                    if success:
                        print("[FallRecovery] Fall recovered successfully!")
                        self.speaker.speak("I am back on my feet and ready to go.")
                    else:
                        print("[FallRecovery] Recovery failed.")
                        self.speaker.speak("I could not stand up. Please check my joints.")

                    time.sleep(5.0)
                    self.is_recovering = False

            except Exception as e:
                print(f"[FallRecovery] Error: {e}")

            time.sleep(1.0)

    def stop(self):
        self.running = False
        self.is_recovering = False