import sys
import time
import qi

from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition

ip = "192.168.0.105"
port = 9559

# Example command callback
def handle_hello():
    print("Executing hello action!")

def main():
    connection_url = f"tcp://{ip}:{port}"
    session = qi.Session()

    try:
        print(f"Connecting to NAO at: {connection_url}")
        session.connect(connection_url)
        print("Successfully connected.")
    except Exception as e:
        print(f"Failed to connect to NAO at: {connection_url}")
        sys.exit(1)

    fall = FallRecovery(session)
    fall.run()

    voice = VoiceRecognition(session)

    # FIX 1: Register at least one command before starting
    voice.register_command("hello", handle_hello)

    voice.start()

    # FIX 2: Keep the main thread alive so event listeners remain active
    print("\n[System] Voice recognition running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[System] Stopping...")
        voice.stop()

if __name__ == "__main__":
    main()