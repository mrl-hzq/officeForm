from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

from scripts.libreoffice_export import run_calc_pdf_export

BLACK = 0


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


def _set_shape_text(worksheet, shape_name: str, value: object) -> None:
    worksheet.append({
        "kind": "shape_text",
        "sheet": "leave",
        "name": shape_name,
        "value": "" if value is None else str(value),
        "alignment": "center",
    })


def _set_or_create_value_shape(
    worksheet,
    *,
    shape_name: str,
    template_shape_name: str,
    top_left_cell: str,
    value: object,
) -> None:
    worksheet.append({
        "kind": "clone_shape_text",
        "sheet": "leave",
        "name": shape_name,
        "templateName": template_shape_name,
        "topLeftCell": top_left_cell,
        "value": "" if value is None else str(value),
        "alignment": "center",
    })


def generate_al_pdf(
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
    duration_days: float,
    leave_type: str = "annual",
    reason: str = "Annual Leave",
    leave_entitlement: float = 0,
    leave_taken: float = 0,
    leave_balance: float = 0,
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
    _set_merged_date_text(actions, "R24", start_date)
    _set_merged_date_text(actions, "AG24", end_date)

    reason_cells = {
        "annual": "Z28",
        "unpaid": "Z30",
        "emergency": "Z32",
        "other": "Z34",
    }
    for cell_address in reason_cells.values():
        _set_merged_value(actions, cell_address, "")
    _set_merged_value(actions, reason_cells.get(leave_type, "Z28"), reason)

    _set_or_create_value_shape(
        actions,
        shape_name="Leave Entitlement Value",
        template_shape_name="Rectangle 17",
        top_left_cell="P37",
        value=leave_entitlement,
    )
    _set_or_create_value_shape(
        actions,
        shape_name="Leave Applied Value",
        template_shape_name="Rectangle 17",
        top_left_cell="P41",
        value=duration_days,
    )
    _set_shape_text(actions, "Rectangle 16", leave_taken)
    _set_shape_text(actions, "Rectangle 15", leave_balance)

    app_date = datetime.strptime(application_date, "%Y-%m-%d").date()
    _set_merged_value(actions, "A54", app_date.day)
    _set_merged_value(actions, "E54", app_date.month)
    _set_merged_value(actions, "I54", app_date.year)

    run_calc_pdf_export(
        template_path=template_path,
        working_workbook_path=working_workbook_path,
        output_pdf_path=output_pdf_path,
        actions=actions,
    )
