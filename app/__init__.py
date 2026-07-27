from __future__ import annotations

import sys
from pathlib import Path
from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PUBLIC_DIR = ROOT / "public"
GENERATED_DIR = ROOT / "generated"
FORM_ORI_DIR = ROOT / "formOri"
OTHERS_DIR = ROOT / "others"


def create_app() -> Flask:
    # No static_folder — we serve frontend files manually to avoid
    # Flask's built-in static handler registering a catch-all /<path:filename>
    # route that would intercept POST requests to /api/* endpoints.
    app = Flask(__name__)

    from .config import Config
    app.config.from_object(Config)
    app.config["ROOT"] = ROOT
    app.config["PUBLIC_DIR"] = PUBLIC_DIR
    app.config["GENERATED_DIR"] = GENERATED_DIR
    app.config["FORM_ORI_DIR"] = FORM_ORI_DIR
    app.config["OTHERS_DIR"] = OTHERS_DIR
    app.config["PDF_DIR"] = GENERATED_DIR / "pdfs"
    app.config["WORKBOOK_DIR"] = GENERATED_DIR / "workbooks"

    from .db import close_db
    app.teardown_appcontext(close_db)

    # Ensure output directories exist
    app.config["PDF_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["WORKBOOK_DIR"].mkdir(parents=True, exist_ok=True)

    from .auth import bp as auth_bp
    from .workers import bp as workers_bp
    from .submissions import bp as submissions_bp
    from .other_forms import bp as other_forms_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(workers_bp)
    app.register_blueprint(submissions_bp)
    app.register_blueprint(other_forms_bp)

    @app.get("/")
    def index():
        return send_from_directory(PUBLIC_DIR, "index.html")

    @app.get("/generated/<path:filename>")
    def generated_file(filename: str):
        return send_from_directory(GENERATED_DIR, filename)

    @app.get("/others/<path:filename>")
    def others_file(filename: str):
        return send_from_directory(OTHERS_DIR, filename)

    # Serve known frontend static assets only (avoids catching /api/* routes)
    @app.get("/app.js")
    def js_file():
        return send_from_directory(PUBLIC_DIR, "app.js")

    @app.get("/styles.css")
    def css_file():
        return send_from_directory(PUBLIC_DIR, "styles.css")

    @app.get("/api/health")
    def health():
        from flask import jsonify
        return jsonify({"ok": True, "app": "office-form-pdf-system", "server": "flask"})

    @app.get("/api/forms")
    def forms():
        from flask import jsonify
        return jsonify({
            "forms": [
                {"id": "AL", "name": "AL and EL", "status": "ready"},
                {"id": "MC", "name": "MC", "status": "ready"},
                {"id": "KPI", "name": "KPI Form", "status": "ready"},
                {"id": "EXP", "name": "Expense Claim", "status": "ready"},
                {"id": "OT", "name": "Overtime Claim", "status": "ready"},
            ]
        })

    return app
