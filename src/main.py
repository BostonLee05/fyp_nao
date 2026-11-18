"""
main.py
Flask entry point for the NAO Smart Classroom Monitoring System.
"""

import sys

from flask import Flask, request, jsonify
from flask_cors import CORS

from modules.robot_services import robot_services

from nao_api import get_nao_manager
from robot_session import robot_session
import config

from routes.home import home_bp
from routes.robot import robot_bp
from routes.vision import vision_bp
from routes.attendance import attendance_bp
from routes.subjects import subjects_bp
from routes.behaviour import behaviour_bp
from routes.reports import reports_bp
from routes.settings import settings_bp
from routes.voice import voice_bp, voice_page_bp

app = Flask(__name__)

CORS(app, resources={
    r"/api/*": {
        "origins": ["https://bostonlee05.github.io"]
    }
})

nao_manager = get_nao_manager()

robot_manager = None

# ---------------------------------------------------
# Robot Initialization
# ---------------------------------------------------

def initialize_robot():
    global robot_manager

    robot_manager = get_nao_manager()
    session = None

    try:
        robot_manager.connect(config.ROBOT_IP, config.ROBOT_PORT)
        session = robot_manager.get_session()
        robot_session.start_session(config.ROBOT_IP)
    except Exception as e:
        print(f"\n[System Warning] Could not connect to NAO ({e}).")
        print("[System Warning] Running server in Web-Only Mode (Robot hardware offline).\n")

    # Initialize Gemini Service regardless of robot status.
    robot_services.ensure_gemini()

    if session:
        robot_services.start_for_session(session)

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
app.register_blueprint(voice_bp)
app.register_blueprint(voice_page_bp)


# ---------------------------------------------------
# Basic Flask Routes
# ---------------------------------------------------

@app.route("/say", methods=["POST"])
def say_something():
    data = request.get_json()
    text = data.get("text", "")

    try:
        if not robot_services.speaker:
            return jsonify({
                "status": "error",
                "message": "Speaker is not available. Connect NAO first."
            }), 503

        robot_services.speaker.speak(str(text))

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

        robot_services.stop_robot_services()

        if nao_manager.is_connected():
            nao_manager.disconnect()

        print("[System] Closed successfully.")
