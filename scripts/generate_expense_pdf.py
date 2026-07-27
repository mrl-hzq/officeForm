from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from scripts.libreoffice_export import run_calc_pdf_export

MILEAGE_RATES = {
    "car": 0.87,
    "motorcycle": 0.60,
}
FIRST_ITEM_ROW = 16
LAST_ITEM_ROW = 28
ITEM_ROW_HEIGHT = 39
EXPENSE_PRINT_AREA = "$B$1:$Q$45"
FIRST_TABLE_ROW = 15
LAST_TABLE_ROW = LAST_ITEM_ROW
MILEAGE_AMOUNT_COLUMN = "G"
MILEAGE_NUMBER_FORMAT = "#,##0.00"

EXPENSE_COLUMN_CELLS = {
    "date": "B",
    "description": "C",
    "project": "E",
    "totalKm": "F",
    "parking": "H",
    "toll": "I",
    "hotel": "J",
    "flight": "K",
    "medical": "L",
    "phone": "M",
    "entertainment": "N",
    "travelAllowance": "O",
    "misc": "P",
}
PRINT_COLUMNS_TO_CENTER = ("B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P")
DESCRIPTION_COLUMNS = {"C", "D"}
TOTAL_COLUMNS = {"Q"}


def _as_excel_date(value: str | date) -> datetime:
    if isinstance(value, date):
        parsed = value
    else:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    return datetime(parsed.year, parsed.month, parsed.day)


def _set_merged_value(worksheet, address: str, value: object) -> None:
    worksheet.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": "" if value is None else str(value),
        "numberFormat": "@",
    })


def _set_date_value(worksheet, address: str, value: str | date) -> None:
    worksheet.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": _as_excel_date(value).strftime("%d/%m/%Y"),
        "numberFormat": "@",
    })


def _set_number_value(worksheet, address: str, value: object) -> None:
    worksheet.append({
        "kind": "cell",
        "sheet": 0,
        "address": address,
        "value": value if value not in (None, "") else 0,
        "valueType": "number",
    })


def _clear_item_rows(worksheet) -> None:
    for row_index in range(FIRST_ITEM_ROW, LAST_ITEM_ROW + 1):
        for column in ("B", "C", "E", "F", "H", "I", "J", "K", "L", "M", "N", "O", "P"):
            _set_merged_value(worksheet, f"{column}{row_index}", "")
        worksheet.append({
            "kind": "cell",
            "sheet": 0,
            "address": f"G{row_index}",
            "value": f"=F{row_index}*{MILEAGE_RATES['car']}",
            "valueType": "formula",
        })
        worksheet.append({
            "kind": "cell",
            "sheet": 0,
            "address": f"Q{row_index}",
            "value": f"=SUM(G{row_index}:P{row_index})",
            "valueType": "formula",
        })


def _center_print_area_cells(worksheet) -> None:
    for row_index in range(FIRST_TABLE_ROW, LAST_TABLE_ROW + 1):
        for column in (*PRINT_COLUMNS_TO_CENTER, *TOTAL_COLUMNS):
            if column in DESCRIPTION_COLUMNS:
                alignment = "left"
            elif column in TOTAL_COLUMNS:
                alignment = None
            else:
                alignment = "center"
            action = {
                "kind": "range_align",
                "sheet": 0,
                "range": f"{column}{row_index}",
                "verticalAlignment": "center",
            }
            if alignment:
                action["alignment"] = alignment
            worksheet.append(action)

    for row_index in range(FIRST_ITEM_ROW, LAST_ITEM_ROW + 1):
        _format_mileage_item_cell(worksheet, row_index)


def _standardize_item_rows(worksheet) -> None:
    worksheet.append({
        "kind": "row_height",
        "sheet": 0,
        "start": FIRST_ITEM_ROW,
        "end": LAST_ITEM_ROW,
        "height": ITEM_ROW_HEIGHT,
    })


def _format_mileage_item_cell(worksheet, row_index: int) -> None:
    worksheet.append({
        "kind": "range_align",
        "sheet": 0,
        "range": f"{MILEAGE_AMOUNT_COLUMN}{row_index}",
        "alignment": "center",
        "verticalAlignment": "center",
    })
    worksheet.append({
        "kind": "cell_format",
        "sheet": 0,
        "address": f"{MILEAGE_AMOUNT_COLUMN}{row_index}",
        "numberFormat": MILEAGE_NUMBER_FORMAT,
        "alignment": "center",
        "verticalAlignment": "center",
    })


def _right_align_summary_cells(worksheet) -> None:
    for cell_range in ("O30:P30", "O31:P31", "N32:P32", "Q30:Q32"):
        worksheet.append({
            "kind": "range_align",
            "sheet": 0,
            "range": cell_range,
            "alignment": "right",
            "verticalAlignment": "center",
        })


def _restore_total_formulas(worksheet) -> None:
    worksheet.append({"kind": "cell", "sheet": 0, "address": "F29", "value": "=SUM(F16:F28)", "valueType": "formula"})
    worksheet.append({"kind": "cell", "sheet": 0, "address": "G29", "value": "=SUM(G16:G28)", "valueType": "formula"})
    for column in ("H", "I", "J", "K", "L", "M", "N", "O", "P"):
        worksheet.append({"kind": "cell", "sheet": 0, "address": f"{column}29", "value": f"=SUM({column}16:{column}28)", "valueType": "formula"})
    worksheet.append({"kind": "cell", "sheet": 0, "address": "Q29", "value": "=SUM(G29:P29)", "valueType": "formula"})
    worksheet.append({"kind": "cell", "sheet": 0, "address": "Q30", "value": "=SUM(Q16:Q28)", "valueType": "formula"})
    worksheet.append({"kind": "cell", "sheet": 0, "address": "Q32", "value": "=SUM(Q30-Q31)", "valueType": "formula"})


def _configure_single_page_export(worksheet) -> None:
    worksheet.append({
        "kind": "page_setup",
        "sheet": 0,
        "printArea": EXPENSE_PRINT_AREA.replace("$", ""),
        "landscape": True,
        "fitToPagesWide": 1,
        "fitToPagesTall": 1,
        "centerHorizontally": True,
        "centerVertically": False,
    })


def generate_expense_pdf(
    *,
    template_path: str | Path,
    working_workbook_path: str | Path,
    output_pdf_path: str | Path,
    worker_name: str,
    worker_id: str,
    department: str,
    supervisor_name: str,
    site: str,
    month_label: str,
    items: list[dict],
    advances: float = 0,
) -> None:
    template_path = Path(template_path).resolve()
    working_workbook_path = Path(working_workbook_path).resolve()
    output_pdf_path = Path(output_pdf_path).resolve()

    actions: list[dict] = []

    _set_merged_value(actions, "D9", worker_name)
    _set_merged_value(actions, "D10", worker_id)
    _set_merged_value(actions, "D11", department)
    _set_merged_value(actions, "D12", supervisor_name)
    _set_merged_value(actions, "Q9", site)
    _set_merged_value(actions, "Q12", month_label)

    _clear_item_rows(actions)
    for item_index, item in enumerate(items[:13], start=FIRST_ITEM_ROW):
        _set_date_value(actions, f"{EXPENSE_COLUMN_CELLS['date']}{item_index}", item["date"])
        _set_merged_value(actions, f"{EXPENSE_COLUMN_CELLS['description']}{item_index}", item.get("description", ""))
        _set_merged_value(actions, f"{EXPENSE_COLUMN_CELLS['project']}{item_index}", item.get("project", ""))
        for field_key, column in EXPENSE_COLUMN_CELLS.items():
            if field_key in {"date", "description", "project"}:
                continue
            _set_number_value(actions, f"{column}{item_index}", item.get(field_key, 0))
        mileage_rate = MILEAGE_RATES.get(item.get("transportMode", "car"), MILEAGE_RATES["car"])
        actions.append({
            "kind": "cell",
            "sheet": 0,
            "address": f"G{item_index}",
            "value": f"=F{item_index}*{mileage_rate}",
            "valueType": "formula",
            "numberFormat": MILEAGE_NUMBER_FORMAT,
            "alignment": "center",
        })

    _restore_total_formulas(actions)
    _set_number_value(actions, "Q31", advances)
    _center_print_area_cells(actions)
    _right_align_summary_cells(actions)
    _standardize_item_rows(actions)
    _configure_single_page_export(actions)

    run_calc_pdf_export(
        template_path=template_path,
        working_workbook_path=working_workbook_path,
        output_pdf_path=output_pdf_path,
        actions=actions,
    )
