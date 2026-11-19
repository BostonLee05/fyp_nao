from flask import Blueprint, jsonify, render_template, request

from database import add_voice_command, delete_voice_command, get_voice_commands
from modules.voice_state import voice_state


voice_bp = Blueprint("voice", __name__, url_prefix="/api/voice")
voice_page_bp = Blueprint("voice_page", __name__)


@voice_page_bp.route("/voice")
def voice_dashboard():
    return render_template(
        "voice.html",
        page_title="Voice Recognition",
    )


@voice_bp.route("/status")
def voice_status():
    return jsonify({
        "success": True,
        "voice": voice_state.snapshot(),
    })


@voice_bp.route("/history")
def voice_history():
    snapshot = voice_state.snapshot()
    return jsonify({
        "success": True,
        "history": snapshot["history"],
    })


@voice_bp.route("/recommendations")
def voice_recommendations():
    snapshot = voice_state.snapshot()
    return jsonify({
        "success": True,
        "recommendations": snapshot["recommendations"],
        "recommendation_token": snapshot["recommendation_token"],
    })


@voice_bp.route("/commands")
def voice_commands():
    try:
        commands = [dict(command) for command in get_voice_commands()]
        return jsonify({"success": True, "commands": commands})
    except Exception as e:
        return jsonify({
            "success": False,
            "commands": [],
            "message": f"Could not load predefined commands: {e}",
        }), 503


@voice_bp.route("/commands", methods=["POST"])
def create_voice_command():
    payload = request.get_json(silent=True) or {}

    try:
        command_id = add_voice_command(
            command_key=payload.get("command_key", ""),
            response=payload.get("response", ""),
            phrases=payload.get("phrases", []),
        )
        return jsonify({
            "success": True,
            "command_id": command_id,
            "commands": [dict(command) for command in get_voice_commands()],
        }), 201
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"Could not save voice command: {error}",
        }), 503


@voice_bp.route("/commands/<int:command_id>", methods=["DELETE"])
def remove_voice_command(command_id):
    try:
        if not delete_voice_command(command_id):
            return jsonify({
                "success": False,
                "message": "Voice command was not found.",
            }), 404

        return jsonify({
            "success": True,
            "commands": [dict(command) for command in get_voice_commands()],
        })
    except Exception as error:
        return jsonify({
            "success": False,
            "message": f"Could not delete voice command: {error}",
        }), 503
