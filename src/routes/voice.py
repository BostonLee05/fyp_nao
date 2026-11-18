import os
import tempfile
import uuid

from flask import Blueprint, jsonify, render_template, request

from modules.robot_services import robot_services

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
