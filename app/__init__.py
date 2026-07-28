from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PUBLIC_DIR = ROOT / "public"
GENERATED_DIR = ROOT / "generated"
FORM_ORI_DIR = ROOT / "formOri"
OTHERS_DIR = ROOT / "others"


def _loadj(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return val
    return val or {}


def _iso(val):
    if val is None:
        return ""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    return str(val)


def _regenerate_pdf(filename: str) -> None:
    from .db import query_one
    from . import pdf_service

    pdf_file_name = Path(filename).name
    row = query_one(
        "SELECT * FROM submissions WHERE pdf_file_name = %s",
        (pdf_file_name,)
    )
    if not row:
        return

    snapshot = _loadj(row.get("worker_snapshot"))
    worker = {
        "name": snapshot.get("name", ""),
        "workerId": snapshot.get("workerId", ""),
        "designation": snapshot.get("designation", ""),
        "department": snapshot.get("department", ""),
        "houseTel": snapshot.get("houseTel", ""),
        "otherTel": snapshot.get("otherTel", ""),
        "evaluatorName": snapshot.get("evaluatorName", ""),
    }

    form_type = row.get("form_type")
    pdf_path = GENERATED_DIR / filename
    wb_name = row.get("workbook_file_name")
    workbook_path = GENERATED_DIR / "workbooks" / wb_name if wb_name else GENERATED_DIR / "workbooks" / pdf_file_name.replace(".pdf", ".xls")

    try:
        if form_type in ("AL", "EL"):
            pdf_service.generate_al(
                template_path=FORM_ORI_DIR / "Leave Application Form.xls",
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                worker=worker,
                start_iso=_iso(row.get("start_date")),
                end_iso=_iso(row.get("end_date")),
                duration_days=row.get("duration_days", 1),
                leave_type=row.get("leave_type", "annual"),
                reason=row.get("reason", ""),
                leave_summary=_loadj(row.get("leave_summary")),
                application_iso=_iso(row.get("application_date")),
                half_day_period=row.get("half_day_period"),
            )
        elif form_type == "MC":
            pdf_service.generate_mc(
                template_path=FORM_ORI_DIR / "MC FORM .xls",
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                worker=worker,
                start_iso=_iso(row.get("start_date")),
                end_iso=_iso(row.get("end_date")),
                duration_days=row.get("duration_days", 1),
                sickness_reason=row.get("reason", ""),
                application_iso=_iso(row.get("application_date")),
            )
        elif form_type == "KPI":
            kd = _loadj(row.get("kpi_data"))
            from .utils import parse_year_month, format_kpi_month_label
            ml = format_kpi_month_label(parse_year_month(row.get("kpi_month"), "kpiMonth")) if row.get("kpi_month") else ""
            pdf_service.generate_kpi(
                template_path=FORM_ORI_DIR / "Borang Penilaian Prestasi (Non Leader).xlsx",
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                worker=worker,
                evaluator_name=kd.get("evaluatorName", ""),
                month_label=ml,
                task_list=kd.get("taskList", ""),
                scores=kd.get("scores", {}),
                comments=kd.get("comments", {}),
                summary_options=kd.get("summaryOptions", {}),
                worker_feedback=kd.get("workerFeedback", ""),
                training_needs=kd.get("trainingNeeds", ""),
                evaluator_feedback=kd.get("evaluatorFeedback", ""),
                application_date=_iso(row.get("application_date")),
            )
        elif form_type == "EXP":
            ed = _loadj(row.get("kpi_data"))
            from .utils import parse_year_month, format_month_range_label
            ms = parse_year_month(ed.get("claimMonth", ""), "claimMonth") if ed.get("claimMonth") else None
            me = parse_year_month(ed.get("claimMonthEnd", ""), "claimMonthEnd") if ed.get("claimMonthEnd") else None
            ml = format_month_range_label(ms, me, upper=True) if ms else ""
            pdf_service.generate_expense(
                template_path=FORM_ORI_DIR / "expenses claim form baru.xlsx",
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                worker=worker,
                supervisor_name=ed.get("supervisorName", ""),
                site=ed.get("site", ""),
                month_label=ml,
                items=ed.get("items", []),
                advances=float(ed.get("advances", 0)),
            )
        elif form_type == "OT":
            od = _loadj(row.get("kpi_data"))
            from .utils import parse_year_month, format_month_range_label
            ms = parse_year_month(od.get("claimMonth", ""), "claimMonth") if od.get("claimMonth") else None
            me = parse_year_month(od.get("claimMonthEnd", ""), "claimMonthEnd") if od.get("claimMonthEnd") else None
            ml = format_month_range_label(ms, me) if ms else ""
            pdf_service.generate_ot(
                template_path=FORM_ORI_DIR / "OT Form latest.xls",
                workbook_path=workbook_path,
                pdf_path=pdf_path,
                worker=worker,
                month_label=ml,
                items=od.get("items", []),
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("PDF regeneration failed for %s: %s", filename, exc)


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
        if filename.startswith("pdfs/") and not (GENERATED_DIR / filename).exists():
            _regenerate_pdf(filename)
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
