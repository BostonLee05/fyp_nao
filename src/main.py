import sys
import qi

from modules.fall_recovery import FallRecovery

ip = "192.168.0.102"
port = 9559

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

if __name__ == "__main__":
    main()