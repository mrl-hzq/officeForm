from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from scripts.libreoffice_export import run_calc_pdf_export


def _as_excel_date_text(value: str | date) -> str:
    if isinstance(value, date):
        parsed = value
    else:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return parsed.strftime("%d-%b-%Y")


def _set_merged_value(worksheet, address: str, value: object) -> None:
    worksheet.append({
        "kind": "cell",
        "sheet": "leave",
        "address": address,
        "value": "" if value is None else str(value),
        "numberFormat": "@",
    })


def _set_merged_date_text(worksheet, address: str, value: str | date) -> None:
    worksheet.append({
        "kind": "cell",
        "sheet": "leave",
        "address": address,
        "value": _as_excel_date_text(value),
        "numberFormat": "@",
    })


def generate_mc_pdf(
    *,
    template_path: str | Path,
    working_workbook_path: str | Path,
    output_pdf_path: str | Path,
    worker_name: str,
    worker_id: str,
    designation: str,
    house_tel: str = "",
    other_tel: str = "",
    start_date: str,
    end_date: str,
    duration_days: int,
    sickness_reason: str,
    application_date: str,
) -> None:
    template_path = Path(template_path).resolve()
    working_workbook_path = Path(working_workbook_path).resolve()
    output_pdf_path = Path(output_pdf_path).resolve()

    actions: list[dict] = []

    _set_merged_value(actions, "L15", worker_name)
    _set_merged_value(actions, "L17", worker_id)
    _set_merged_value(actions, "L19", designation)
    _set_merged_value(actions, "L21", house_tel)
    _set_merged_value(actions, "AF21", other_tel)

    _set_merged_value(actions, "L23", duration_days)
    _set_merged_date_text(actions, "R25", start_date)
    _set_merged_date_text(actions, "AG25", end_date)
    _set_merged_value(actions, "A30", sickness_reason)

    app_date = datetime.strptime(application_date, "%Y-%m-%d").date()
    _set_merged_value(actions, "A40", app_date.day)
    _set_merged_value(actions, "E40", app_date.month)
    _set_merged_value(actions, "I40", app_date.year)

    run_calc_pdf_export(
        template_path=template_path,
        working_workbook_path=working_workbook_path,
        output_pdf_path=output_pdf_path,
        actions=actions,
    )
