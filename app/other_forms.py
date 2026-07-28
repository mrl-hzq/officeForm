from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, current_app, jsonify, request
from werkzeug.utils import secure_filename

from .auth import require_auth, require_admin

bp = Blueprint("other_forms", __name__)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".txt", ".csv",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip",
}


def _others_dir() -> Path:
    folder = current_app.config["OTHERS_DIR"]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _serialize_file(path: Path) -> dict:
    stat = path.stat()
    return {
        "id": path.name,
        "name": path.stem.replace("_", " "),
        "fileName": path.name,
        "url": f"/others/{quote(path.name)}",
        "size": stat.st_size,
        "updatedAt": int(stat.st_mtime),
    }


def _list_other_forms() -> list[dict]:
    folder = _others_dir()
    return [
        _serialize_file(path)
        for path in sorted(folder.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    ]


def _safe_existing_path(file_name: str) -> Path:
    safe_name = Path(file_name).name
    if not safe_name or safe_name != file_name:
        raise ValueError("Invalid file name.")
    path = (_others_dir() / safe_name).resolve()
    if path.parent != _others_dir().resolve():
        raise ValueError("Invalid file path.")
    return path


@bp.get("/api/others")
@require_auth
def other_forms():
    return jsonify({"forms": _list_other_forms()})


@bp.post("/api/admin/others")
@require_admin
def upload_other_form():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "A file is required."}), 400

    safe_name = secure_filename(uploaded.filename)
    if not safe_name:
        return jsonify({"error": "Invalid file name."}), 400

    if Path(safe_name).suffix.lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Unsupported file type."}), 400

    target = (_others_dir() / safe_name).resolve()
    if target.parent != _others_dir().resolve():
        return jsonify({"error": "Invalid file path."}), 400

    uploaded.save(target)
    return jsonify({"form": _serialize_file(target), "forms": _list_other_forms()}), 201


@bp.delete("/api/admin/others/<path:file_name>")
@require_admin
def delete_other_form(file_name: str):
    try:
        target = _safe_existing_path(file_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    if not target.exists() or not target.is_file():
        return jsonify({"error": "Form not found."}), 404

    if target.suffix.lower() not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Only managed forms can be deleted."}), 400

    target.unlink()
    return jsonify({"deleted": file_name, "forms": _list_other_forms()})
