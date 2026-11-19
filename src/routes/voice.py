import os
import tempfile
import uuid

from flask import Blueprint, jsonify, render_template, request

from modules.robot_services import robot_services

from modules.voice_state import voice_state
from database import (
    add_voice_command,
    add_voice_wake_phrase,
    delete_voice_command,
    get_voice_commands,
    get_voice_wake_phrases,
)


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


@voice_bp.route("/commands", methods=["GET"])
def voice_commands():
    """List database-backed commands and all of their trigger phrases."""
    try:
        return jsonify({
            "success": True,
            "commands": get_voice_commands(request.args.get("search", "").strip() or None),
        })
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@voice_bp.route("/commands/<int:command_id>", methods=["DELETE"])
def remove_voice_command(command_id):
    try:
        if not delete_voice_command(command_id):
            return jsonify({"success": False, "error": "Command not found"}), 404
        return jsonify({"success": True})
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@voice_bp.route("/commands", methods=["POST"])
def create_voice_command():
    """Create/update a command; phrases may contain any number of triggers."""
    data = request.get_json(silent=True) or {}
    phrases = data.get("phrases", data.get("triggers", []))
    if isinstance(phrases, str):
        phrases = [phrases]
    try:
        command_id = add_voice_command(
            data.get("command_key", ""),
            data.get("action", "robot"),
            data.get("response", "Done."),
            phrases,
        )
        return jsonify({"success": True, "command_id": command_id}), 201
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except Exception as error:
        return jsonify({"success": False, "error": str(error)}), 500


@voice_bp.route("/wake-phrases", methods=["GET", "POST"])
def voice_wake_phrases():
    if request.method == "GET":
        return jsonify({"success": True, "phrases": get_voice_wake_phrases()})
    data = request.get_json(silent=True) or {}
    phrases = data.get("phrases", data.get("phrase", []))
    if isinstance(phrases, str):
        phrases = [phrases]
    try:
        ids = [add_voice_wake_phrase(phrase) for phrase in phrases]
        return jsonify({"success": True, "wake_phrase_ids": ids}), 201
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400


@voice_bp.route("/recommendations")
def voice_recommendations():
    snapshot = voice_state.snapshot()
    return jsonify({
        "success": True,
        "recommendations": snapshot["recommendations"],
        "recommendation_token": snapshot["recommendation_token"],
    })


@voice_bp.route("/upload", methods=["POST"])
def upload_audio():
    """Optional TCP/HTTP-style WAV upload alternative for the local transfer path."""
    audio_file = request.files.get("audio")
    if audio_file is None:
        return jsonify({
            "success": False,
            "error": "Missing audio file",
        }), 400

    recording_id = (
        request.form.get("recording_id")
        or request.headers.get("X-Recording-ID")
        or "nao-" + uuid.uuid4().hex
    )
    safe_id = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in recording_id
    )
    upload_path = os.path.join(
        tempfile.gettempdir(),
        "nao_voice_" + safe_id + ".wav",
    )

    try:
        audio_file.save(upload_path)
        size = os.path.getsize(upload_path)
        if size < 44:
            os.remove(upload_path)
            return jsonify({
                "success": False,
                "recording_id": safe_id,
                "error": "Incomplete WAV file",
            }), 400

        service = robot_services.voice_recognition_service
        if service is None:
            os.remove(upload_path)
            return jsonify({
                "success": False,
                "recording_id": safe_id,
                "error": "Voice recognition service unavailable",
            }), 503

        accepted = service.process_uploaded_audio_async(
            upload_path,
            recording_id=safe_id,
        )
        return jsonify({
            "success": True,
            "accepted": accepted,
            "recording_id": safe_id,
            "bytes": size,
        }), 202
    except Exception as error:
        return jsonify({
            "success": False,
            "recording_id": safe_id,
            "error": str(error),
        }), 500
