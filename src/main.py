"""
main.py
Flask entry point for the NAO Smart Classroom Monitoring System.
"""

import sys

from flask import Flask, render_template, request, jsonify

from speaker import Speaker
from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition
from modules.gemini_service import GeminiService

from nao_api import get_nao_manager
from config import ROBOT_IP, ROBOT_PORT

from routes.home import home_bp
from routes.robot import robot_bp
from routes.vision import vision_bp
from routes.attendance import attendance_bp
from routes.subjects import subjects_bp
from routes.behaviour import behaviour_bp
from routes.reports import reports_bp
from routes.settings import settings_bp

app = Flask(__name__)

session = None
nao_manager = get_nao_manager()

speaker = None
fall = None
voice = None
gemini = None


# ---------------------------------------------------
# Robot Commands
# ---------------------------------------------------

def say_hello():
    speaker.speak("Hello there! I'm Great!")


def sit_down():
    try:
        posture = session.service("ALRobotPosture")
        current_posture = posture.getPosture()

        print(f"[Posture] Current posture: {current_posture}")

        if current_posture in ["Sit"]:
            print("[Posture] Robot is already sitted. Skipping task.")
            speaker.speak("I am already in siting posture.")
            return

        print("[Posture] Changing posture to 'Sit'...")
        speaker.speak("Sitting down.")

        success = posture.goToPosture("Sit", 0.5)

        if success:
            print("[Posture] Robot successfully sit.")
        else:
            print("[Posture] Failed to reach sitting posture.")
            speaker.speak("I couldn't sit down.")

    except Exception as e:
        print(f"[Posture Error] {e}")
        speaker.speak(
            "Sorry, I encountered an error trying to sit down."
        )


def stand_up():
    try:
        posture = session.service("ALRobotPosture")
        current_posture = posture.getPosture()

        print(f"[Posture] Current posture: {current_posture}")

        if current_posture in ["StandInit", "Stand"]:
            print("[Posture] Robot is already standing. Skipping task.")
            speaker.speak("I am already standing.")
            return

        print("[Posture] Changing posture to 'StandInit'...")
        speaker.speak("Standing up.")

        success = posture.goToPosture("StandInit", 0.5)

        if success:
            print("[Posture] Robot successfully stood up.")
        else:
            print("[Posture] Failed to reach standing posture.")
            speaker.speak("I couldn't stand up.")

    except Exception as e:
        print(f"[Posture Error] {e}")
        speaker.speak(
            "Sorry, I encountered an error trying to stand up."
        )


# ---------------------------------------------------
# Robot Initialization
# ---------------------------------------------------

def initialize_robot():
    global session, speaker, fall, voice, gemini

    try:
        print(
            f"Connecting to NAO at: "
            f"tcp://{ROBOT_IP}:{ROBOT_PORT}"
        )

        # Use the shared NAOManager connection
        nao_manager.connect(
            ROBOT_IP,
            ROBOT_PORT
        )

        # IMPORTANT:
        # Get the same qi.Session used by NAOManager.
        session = nao_manager.get_session()

        print("Successfully connected.")

    except Exception as e:
        print(
            f"Failed to connect to NAO at: "
            f"tcp://{ROBOT_IP}:{ROBOT_PORT}\n"
            f"Error: {e}"
        )
        sys.exit(1)

    speaker = Speaker(session)

    gemini = GeminiService()

    print(
        f"[System] Gemini Service status: "
        f"{'Ready' if gemini.client else 'No API Key'}"
    )

    # 1. Start Fall Recovery
    fall = FallRecovery(session, speaker)
    fall.start()

    # 2. Start Voice Recognition
    voice = VoiceRecognition(session, speaker)

    voice.register_command("hello", say_hello)
    voice.register_command("sit down", sit_down)
    voice.register_command("stand up", stand_up)

    voice.start()

    print(
        "\n[System] All robot modules initialized "
        "and running continuously."
    )


# ---------------------------------------------------
# Flask Blueprints
# ---------------------------------------------------

app.register_blueprint(home_bp)
app.register_blueprint(robot_bp)
app.register_blueprint(vision_bp)
app.register_blueprint(attendance_bp)
app.register_blueprint(subjects_bp)
app.register_blueprint(behaviour_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(settings_bp)


# ---------------------------------------------------
# Basic Flask Routes
# ---------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/say", methods=["POST"])
def say_something():
    data = request.get_json()
    text = data.get("text", "")

    try:
        speaker.speak(str(text))

        return jsonify({
            "status": "success",
            "message": "NAO spoke."
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Failed to speak: {e}"
        })


# ---------------------------------------------------
# Application Entry Point
# ---------------------------------------------------

if __name__ == "__main__":
    initialize_robot()

    print(
        "[System] Launching web server. "
        "Press Ctrl+C to stop."
    )

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False
        )

    except KeyboardInterrupt:
        pass

    finally:
        print("\n[System] Shutting down services...")

        if fall:
            fall.stop()

        if voice:
            voice.stop()

        if nao_manager.is_connected():
            nao_manager.disconnect()

        print("[System] Closed successfully.")