import time

class FallRecovery:
    def __init__(self, session):
        self.motion = session.service("ALMotion")
        self.posture = session.service("ALRobotPosture")
        self.tts = session.service("ALTextToSpeech")

    def run(self):
        print("Fall Recovery Daemon is now monitoring the robot...")
        try:
            while True:
                # Check the general category of the robot's physical layout
                current_family = self.posture.getPostureFamily()

                # If NAO is detected lying down on the ground
                if current_family in ["LyingBelly", "LyingBack"]:
                    print(f"Fall detected! Current posture family: {current_family}")
                    self.tts.say("Oops! I have fallen down. Give me a second to stand back up.")

                    self.motion.wakeUp()

                    # Trigger the intelligent get-up sequence (blocking call)
                    success = self.posture.goToPosture("StandInit", 0.6)

                    if success:
                        print("Fall recovered!")
                        self.tts.say("I am back on my feet and ready to go.")
                    else:
                        print("Recovery failed.")
                        self.tts.say("I could not stand up. Please check my joints.")

                time.sleep(1.0)

        except KeyboardInterrupt:
            print("\nFall Recovery Daemon stopped by user.")