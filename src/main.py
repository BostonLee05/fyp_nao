"""
main.py
Flask entry point for the NAO Smart Classroom Monitoring System.
"""

import sys

from flask import Flask, render_template, request, jsonify

from speaker import Speaker
from modules.fall_recovery import FallRecovery
from modules.voice_recognition import VoiceRecognition
from modules.wake_audio import WakeAudio
from modules.gemini_service import GeminiService
from interated_monitoring import monitor

from nao_api import get_nao_manager
import config

from routes.home import home_bp
from routes.robot import robot_bp
from routes.vision import vision_bp
from routes.attendance import attendance_bp
from routes.subjects import subjects_bp
from routes.behaviour import behaviour_bp
from routes.reports import reports_bp
from routes.settings import settings_bp

app = Flask(__name__)

nao_manager = get_nao_manager()

robot_manager = None
speaker = None
fall = None
voice = None
wake_audio = None
gemini = None

# ---------------------------------------------------
# Robot Initialization
# ---------------------------------------------------

def initialize_robot():
    global robot_manager, speaker, fall, voice, wake_audio, gemini

    robot_manager = get_nao_manager()
    session = None

    try:
        robot_manager.connect(config.ROBOT_IP, config.ROBOT_PORT)
        session = robot_manager.get_session()
    except Exception as e:
        print(f"\n[System Warning] Could not connect to NAO ({e}).")
        print("[System Warning] Running server in Web-Only Mode (Robot hardware offline).\n")

    # Initialize Gemini Service regardless of robot status
    gemini = GeminiService()
    print(
        f"[System] Gemini Service status: "
        f"{'Ready' if getattr(gemini, 'client', None) else 'No API Key'}"
    )

    if session:
        speaker = Speaker(session)

        try:
            # 1. Start Fall Recovery
            fall = FallRecovery(session, speaker)
            fall.start()
        except Exception as e:
            print(f"[System Warning] Fall Recovery did not start: {e}")

        try:
            # 2. Prepare Voice Recognition for wake-word-triggered recording
            voice = VoiceRecognition(session, speaker, gemini_service=gemini)
            voice = VoiceRecognition(
                session,
                speaker,
                gemini_service=gemini,
                frame_provider=monitor.get_frame,
            )
        except Exception as e:
            print(f"[System Warning] Voice Recognition did not start: {e}")

        if voice:
            try:
                # 3. Start NAOqi wake-word recognition
                wake_audio = WakeAudio(session, speaker, voice)
                wake_audio.start()
            except Exception as e:
                print(f"[System Warning] Wake Audio did not start: {e}")

        print("\n[System] Robot module initialization finished.")

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

        if wake_audio:
            wake_audio.stop()

        if fall:
            fall.stop()

        if nao_manager.is_connected():
            nao_manager.disconnect()


        print("[System] Closed successfully.")