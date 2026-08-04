from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.awt import Point, Size


def _property(name: str, value):
    prop = PropertyValue()
    prop.Name = name
    prop.Value = value
    return prop


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_office(port: int, profile_dir: Path):
    office_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not office_bin:
        raise RuntimeError("LibreOffice executable not found in PATH.")

    accept = f"socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
    profile_url = uno.systemPathToFileUrl(str(profile_dir))
    return subprocess.Popen(
        [
            office_bin,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nofirststartwizard",
            "--norestore",
            f"-env:UserInstallation={profile_url}",
            f"--accept={accept}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _connect(port: int):
    local_ctx = uno.getComponentContext()
    resolver = local_ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver",
        local_ctx,
    )
    url = f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
    deadline = time.time() + 30
    last_error = None
    while time.time() < deadline:
        try:
            ctx = resolver.resolve(url)
            return ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError(f"Could not connect to LibreOffice: {last_error}")


def _get_sheet(document, sheet_ref):
    sheets = document.Sheets
    if isinstance(sheet_ref, int):
        return sheets.getByIndex(sheet_ref)
    return sheets.getByName(str(sheet_ref))


def _target_cell(sheet, address: str):
    target = sheet.getCellRangeByName(address)
    try:
        return target.getCellByPosition(0, 0)
    except Exception:
        return target


def _locale():
    value = uno.createUnoStruct("com.sun.star.lang.Locale")
    value.Language = "en"
    value.Country = "US"
    return value


def _number_format_key(document, format_code: str) -> int:
    formats = document.NumberFormats
    locale = _locale()
    key = formats.queryKey(format_code, locale, True)
    if key == -1:
        key = formats.addNew(format_code, locale)
    return key


def _set_number_format(document, cell, format_code: str | None) -> None:
    if not format_code:
        return
    try:
        cell.NumberFormat = _number_format_key(document, format_code)
    except Exception:
        pass


def _set_center(cell) -> None:
    try:
        cell.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "CENTER")
    except Exception:
        pass


def _set_right(cell) -> None:
    try:
        cell.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "RIGHT")
    except Exception:
        pass


def _set_left(cell) -> None:
    try:
        cell.HoriJustify = uno.Enum("com.sun.star.table.CellHoriJustify", "LEFT")
    except Exception:
        pass


def _set_vertical_center(cell) -> None:
    try:
        cell.VertJustify = uno.Enum("com.sun.star.table.CellVertJustify", "CENTER")
    except Exception:
        pass


def _set_alignment(cell, alignment: str | None) -> None:
    if alignment == "center":
        _set_center(cell)
    elif alignment == "right":
        _set_right(cell)
    elif alignment == "left":
        _set_left(cell)


def _set_vertical_alignment(cell, alignment: str | None) -> None:
    if alignment == "center":
        _set_vertical_center(cell)


def _set_shape_alignment(shape, alignment: str | None) -> None:
    if alignment != "center":
        return
    try:
        shape.TextHorizontalAdjust = uno.Enum(
            "com.sun.star.drawing.TextHorizontalAdjust",
            "CENTER",
        )
    except Exception:
        pass
    try:
        cursor = shape.Text.createTextCursor()
        cursor.ParaAdjust = uno.Enum("com.sun.star.style.ParagraphAdjust", "CENTER")
    except Exception:
        pass


def _points_to_hmm(points: float) -> int:
    return int(round(float(points) * 35.2778))


def _set_row_height(sheet, action: dict) -> None:
    height = action.get("height")
    if height is None:
        return
    start = int(action.get("start", action.get("row", 1)))
    end = int(action.get("end", start))
    height_hmm = _points_to_hmm(float(height))
    for row_index in range(start, end + 1):
        try:
            row = sheet.Rows.getByIndex(row_index - 1)
            try:
                row.IsOptimal = False
            except Exception:
                pass
            row.Height = height_hmm
        except Exception:
            pass


def _set_page_property(page_style, name: str, value) -> None:
    try:
        setattr(page_style, name, value)
    except Exception:
        pass


def _configure_page(document, sheet, action: dict) -> None:
    print_area = action.get("printArea")
    if print_area:
        range_address = sheet.getCellRangeByName(print_area).RangeAddress
        sheet.setPrintAreas((range_address,))

    try:
        page_style_name = sheet.PageStyle
        page_styles = document.StyleFamilies.getByName("PageStyles")
        page_style = page_styles.getByName(page_style_name)
    except Exception:
        return

    if action.get("landscape"):
        _set_page_property(page_style, "IsLandscape", True)
    if action.get("centerHorizontally") is not None:
        _set_page_property(page_style, "CenterHorizontally", bool(action["centerHorizontally"]))
    if action.get("centerVertically") is not None:
        _set_page_property(page_style, "CenterVertically", bool(action["centerVertically"]))
    if action.get("fitToPagesWide") is not None:
        _set_page_property(page_style, "ScaleToPagesX", int(action["fitToPagesWide"]))
    if action.get("fitToPagesTall") is not None:
        _set_page_property(page_style, "ScaleToPagesY", int(action["fitToPagesTall"]))
    if action.get("scaleToPages") is not None:
        _set_page_property(page_style, "ScaleToPages", int(action["scaleToPages"]))
    if action.get("marginPoints") is not None:
        margin = int(float(action["marginPoints"]) * 35.2778)
        for prop_name in ("LeftMargin", "RightMargin", "TopMargin", "BottomMargin"):
            _set_page_property(page_style, prop_name, margin)


def _find_shape(sheet, shape_name: str):
    try:
        draw_page = sheet.DrawPage
    except Exception:
        return None
    for index in range(draw_page.Count):
        shape = draw_page.getByIndex(index)
        if getattr(shape, "Name", "") == shape_name:
            return shape
    return None


def _set_shape_text(sheet, action: dict) -> None:
    shape = _find_shape(sheet, action["name"])
    if not shape:
        return
    value = "" if action.get("value") is None else str(action.get("value"))
    try:
        shape.String = value
        _set_shape_alignment(shape, action.get("alignment"))
        try:
            shape.CharColor = 0
        except Exception:
            pass
    except Exception:
        try:
            shape.Text.setString(value)
            _set_shape_alignment(shape, action.get("alignment"))
            try:
                shape.Text.CharColor = 0
            except Exception:
                pass
        except Exception:
            return


def _clone_shape_text(document, sheet, action: dict) -> None:
    existing = _find_shape(sheet, action["name"])
    template = _find_shape(sheet, action["templateName"])
    if existing:
        shape = existing
    elif template:
        shape = document.createInstance("com.sun.star.drawing.TextShape")
        shape.Size = template.Size
        cell = sheet.getCellRangeByName(action["topLeftCell"])
        position = template.Position
        try:
            position = Point(template.Position.X, cell.Position.Y)
        except Exception:
            pass
        shape.Position = position
        try:
            shape.Name = action["name"]
        except Exception:
            pass
        draw_page = sheet.DrawPage
        draw_page.add(shape)
        for property_name in (
            "FillStyle",
            "FillColor",
            "FillTransparence",
            "LineStyle",
            "LineColor",
            "LineWidth",
            "TextHorizontalAdjust",
            "TextVerticalAdjust",
            "CharHeight",
            "CharWeight",
        ):
            try:
                setattr(shape, property_name, getattr(template, property_name))
            except Exception:
                pass
    else:
        return

    value = "" if action.get("value") is None else str(action.get("value"))
    try:
        shape.String = value
        _set_shape_alignment(shape, action.get("alignment"))
        shape.CharColor = 0
    except Exception:
        try:
            shape.Text.setString(value)
            _set_shape_alignment(shape, action.get("alignment"))
        except Exception:
            pass


def _apply_action(document, action: dict) -> None:
    kind = action["kind"]
    sheet = _get_sheet(document, action.get("sheet", 0))

    if kind == "cell":
        cell = _target_cell(sheet, action["address"])
        _set_number_format(document, cell, action.get("numberFormat"))
        if action.get("fontSize"):
            try:
                cell.CharHeight = float(action["fontSize"])
            except Exception:
                pass
        value = action.get("value")
        value_type = action.get("valueType", "string")
        if value_type == "formula":
            cell.Formula = "" if value is None else str(value)
        elif value_type == "number":
            cell.Value = 0 if value in (None, "") else float(value)
        else:
            cell.String = "" if value is None else str(value)
        _set_alignment(cell, action.get("alignment"))
        _set_vertical_alignment(cell, action.get("verticalAlignment"))
    elif kind == "cell_format":
        cell = _target_cell(sheet, action["address"])
        _set_number_format(document, cell, action.get("numberFormat"))
        if action.get("fontSize"):
            try:
                cell.CharHeight = float(action["fontSize"])
            except Exception:
                pass
        _set_alignment(cell, action.get("alignment"))
        _set_vertical_alignment(cell, action.get("verticalAlignment"))
    elif kind == "range_align":
        target = sheet.getCellRangeByName(action["range"])
        _set_alignment(target, action.get("alignment"))
        _set_vertical_alignment(target, action.get("verticalAlignment"))
    elif kind == "row_height":
        _set_row_height(sheet, action)
    elif kind == "shape_text":
        _set_shape_text(sheet, action)
    elif kind == "clone_shape_text":
        _clone_shape_text(document, sheet, action)
    elif kind == "page_setup":
        _configure_page(document, sheet, action)


def _load_document(desktop, workbook_path: Path):
    workbook_url = uno.systemPathToFileUrl(str(workbook_path))
    return desktop.loadComponentFromURL(
        workbook_url,
        "_blank",
        0,
        (
            _property("Hidden", True),
            _property("ReadOnly", False),
            _property("UpdateDocMode", 0),
        ),
    )


def _export_pdf(document, output_pdf_path: Path) -> None:
    pdf_url = uno.systemPathToFileUrl(str(output_pdf_path))
    document.storeToURL(
        pdf_url,
        (
            _property("FilterName", "calc_pdf_Export"),
            _property("Overwrite", True),
        ),
    )


def main(spec_path: str) -> int:
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    workbook_path = Path(spec["workbookPath"]).resolve()
    output_pdf_path = Path(spec["outputPdfPath"]).resolve()
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    profile_dir = Path(tempfile.mkdtemp(prefix="officeform-lo-"))
    port = _free_port()
    office = _start_office(port, profile_dir)
    document = None
    try:
        desktop = _connect(port)
        document = _load_document(desktop, workbook_path)
        if document is None:
            raise RuntimeError(f"LibreOffice could not open workbook: {workbook_path}")

        for action in spec.get("actions", []):
            _apply_action(document, action)

        try:
            document.calculateAll()
        except Exception:
            pass
        document.store()
        _export_pdf(document, output_pdf_path)
    finally:
        if document is not None:
            try:
                document.close(True)
            except Exception:
                document.dispose()
        office.terminate()
        try:
            office.wait(timeout=10)
        except subprocess.TimeoutExpired:
            office.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
