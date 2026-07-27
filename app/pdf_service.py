from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _remove_excel_temp_siblings(workbook_path) -> None:
    workbook_path = Path(workbook_path).resolve()
    for temp_path in workbook_path.parent.glob(f"{workbook_path.stem}~*.tmp"):
        try:
            if temp_path.is_file():
                temp_path.unlink()
        except OSError:
            pass


def generate_al(*, template_path, workbook_path, pdf_path, worker, start_iso, end_iso,
                duration_days, leave_type, reason, leave_summary, application_iso):
    from scripts.generate_al_pdf import generate_al_pdf

    try:
        generate_al_pdf(
            template_path=template_path,
            working_workbook_path=workbook_path,
            output_pdf_path=pdf_path,
            worker_name=worker.get("name", ""),
            worker_id=worker.get("workerId", ""),
            designation=worker.get("designation", ""),
            house_tel=worker.get("houseTel", ""),
            other_tel=worker.get("otherTel", ""),
            start_date=start_iso,
            end_date=end_iso,
            duration_days=duration_days,
            leave_type=leave_type,
            reason=reason,
            leave_entitlement=int(leave_summary["entitlement"]),
            leave_taken=int(leave_summary["takenToDate"]),
            leave_balance=int(leave_summary["balanceAfter"]),
            application_date=application_iso,
        )
    finally:
        _remove_excel_temp_siblings(workbook_path)


def generate_mc(*, template_path, workbook_path, pdf_path, worker, start_iso, end_iso,
                duration_days, sickness_reason, application_iso):
    from scripts.generate_mc_pdf import generate_mc_pdf

    try:
        generate_mc_pdf(
            template_path=template_path,
            working_workbook_path=workbook_path,
            output_pdf_path=pdf_path,
            worker_name=worker.get("name", ""),
            worker_id=worker.get("workerId", ""),
            designation=worker.get("designation", ""),
            house_tel=worker.get("houseTel", ""),
            other_tel=worker.get("otherTel", ""),
            start_date=start_iso,
            end_date=end_iso,
            duration_days=duration_days,
            sickness_reason=sickness_reason,
            application_date=application_iso,
        )
    finally:
        _remove_excel_temp_siblings(workbook_path)


def generate_kpi(*, template_path, workbook_path, pdf_path, worker, evaluator_name,
                 month_label, task_list, scores, comments, summary_options,
                 worker_feedback, training_needs, evaluator_feedback, application_date):
    from scripts.generate_kpi_pdf import generate_kpi_pdf

    try:
        generate_kpi_pdf(
            template_path=template_path,
            working_workbook_path=workbook_path,
            output_pdf_path=pdf_path,
            worker_name=worker.get("name", ""),
            worker_id=worker.get("workerId", ""),
            designation=worker.get("designation", ""),
            department=worker.get("department", ""),
            evaluator_name=evaluator_name,
            month_label=month_label,
            task_list=task_list,
            scores=scores,
            comments=comments,
            summary_options=summary_options,
            worker_feedback=worker_feedback,
            training_needs=training_needs,
            evaluator_feedback=evaluator_feedback,
            application_date=application_date,
        )
    finally:
        _remove_excel_temp_siblings(workbook_path)


def generate_ot(*, template_path, workbook_path, pdf_path, worker, month_label, items):
    from scripts.generate_ot_pdf import generate_ot_pdf

    try:
        generate_ot_pdf(
            template_path=template_path,
            working_workbook_path=workbook_path,
            output_pdf_path=pdf_path,
            worker_name=worker.get("name", ""),
            worker_id=worker.get("workerId", ""),
            month_label=month_label,
            items=items,
        )
    finally:
        _remove_excel_temp_siblings(workbook_path)


def generate_expense(*, template_path, workbook_path, pdf_path, worker,
                     supervisor_name, site, month_label, items, advances):
    from scripts.generate_expense_pdf import generate_expense_pdf

    try:
        generate_expense_pdf(
            template_path=template_path,
            working_workbook_path=workbook_path,
            output_pdf_path=pdf_path,
            worker_name=worker.get("name", ""),
            worker_id=worker.get("workerId", ""),
            department=worker.get("department", ""),
            supervisor_name=supervisor_name,
            site=site,
            month_label=month_label,
            items=items,
            advances=advances,
        )
    finally:
        _remove_excel_temp_siblings(workbook_path)
