from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from scripts.libreoffice_export import run_calc_pdf_export

FIRST_ITEM_ROW = 29
ITEM_ROW_STEP = 3
MAX_ITEM_ROWS = 17
TOTAL_ROW = 80
OT_PRINT_AREA = "A1:AW104"

# Merged blocks per item row: A=date, F=day, G=time from, L=time to,
# Q=hours x1.5 (normal day), V=hours x2 (rest day), AA=hours x3 (public holiday),
# AF=description.
OT_RATE_COLUMNS = {
    "normal": "Q",
    "rest": "V",
    "holiday": "AA",
}


def _item_row(index: int) -> int:
    return FIRST_ITEM_ROW + index * ITEM_ROW_STEP


def _as_excel_date(value: str | date) -> datetime:
    if isinstance(value, date):
        parsed = value
    else:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime(parsed.year, parsed.month, parsed.day)


def _set_merged_value(actions, address: str, value: object) -> None:
    actions.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": "" if value is None else str(value),
        "numberFormat": "@",
    })


def _set_date_value(actions, address: str, value: str | date) -> None:
    actions.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": _as_excel_date(value).strftime("%d/%m/%Y"),
        "numberFormat": "@",
    })


def _set_number_value(actions, address: str, value: object) -> None:
    actions.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": value if value not in (None, "") else 0,
        "valueType": "number",
    })


def _clear_item_rows(actions) -> None:
    for index in range(MAX_ITEM_ROWS):
        row = _item_row(index)
        for column in ("A", "F", "G", "L", "Q", "V", "AA", "AF"):
            _set_merged_value(actions, f"{column}{row}", "")


def _write_totals(actions, items: list[dict]) -> None:
    for rate_type, column in OT_RATE_COLUMNS.items():
        total = round(sum(
            float(item.get("hours") or 0)
            for item in items
            if item.get("rateType") == rate_type
        ), 2)
        if total > 0:
            _set_number_value(actions, f"{column}{TOTAL_ROW}", total)
        else:
            _set_merged_value(actions, f"{column}{TOTAL_ROW}", "")


def _configure_single_page_export(actions) -> None:
    actions.append({
        "kind": "page_setup",
        "sheet": 0,
        "printArea": OT_PRINT_AREA,
        "landscape": False,
        "fitToPagesWide": 1,
        "fitToPagesTall": 1,
        "centerHorizontally": True,
        "centerVertically": False,
    })


def generate_ot_pdf(
    *,
    template_path: str | Path,
    working_workbook_path: str | Path,
    output_pdf_path: str | Path,
    worker_name: str,
    worker_id: str,
    month_label: str,
    items: list[dict],
) -> None:
    template_path = Path(template_path).resolve()
    working_workbook_path = Path(working_workbook_path).resolve()
    output_pdf_path = Path(output_pdf_path).resolve()

    actions: list[dict] = []

    _set_merged_value(actions, "G15", worker_name)
    _set_merged_value(actions, "G19", worker_id)
    _set_merged_value(actions, "AN15", month_label)

    _clear_item_rows(actions)
    for index, item in enumerate(items[:MAX_ITEM_ROWS]):
        row = _item_row(index)
        _set_date_value(actions, f"A{row}", item["date"])
        _set_merged_value(actions, f"F{row}", item.get("dayLabel", ""))
        _set_merged_value(actions, f"G{row}", item.get("timeFrom", ""))
        _set_merged_value(actions, f"L{row}", item.get("timeTo", ""))
        rate_column = OT_RATE_COLUMNS.get(item.get("rateType", "normal"), "Q")
        _set_number_value(actions, f"{rate_column}{row}", item.get("hours", 0))
        _set_merged_value(actions, f"AF{row}", item.get("description", ""))

    _write_totals(actions, items)
    _configure_single_page_export(actions)

    run_calc_pdf_export(
        template_path=template_path,
        working_workbook_path=working_workbook_path,
        output_pdf_path=output_pdf_path,
        actions=actions,
    )
