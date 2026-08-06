from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

from flask import current_app
import pypdf


def _prepare_print_pdf(pdf_path: Path, remove_pages: list[int] | None = None) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    """Remove specified 1-indexed pages from PDF if needed before sending to printer.

    Returns (path_to_print, temp_dir_to_cleanup).
    """
    if not remove_pages:
        return pdf_path, None

    try:
        reader = pypdf.PdfReader(str(pdf_path))
        total_pages = len(reader.pages)
        pages_to_keep = [
            page for idx, page in enumerate(reader.pages, start=1)
            if idx not in remove_pages
        ]

        if 0 < len(pages_to_keep) < total_pages:
            writer = pypdf.PdfWriter()
            for page in pages_to_keep:
                writer.add_page(page)

            temp_dir = tempfile.TemporaryDirectory(prefix="officeform_print_")
            temp_pdf_path = Path(temp_dir.name) / pdf_path.name
            with open(temp_pdf_path, "wb") as f:
                writer.write(f)
            return temp_pdf_path, temp_dir
    except Exception as exc:
        if current_app:
            current_app.logger.warning("Failed to remove pages %s from PDF %s: %s", remove_pages, pdf_path, exc)

    return pdf_path, None


def _build_pjl_stream(pdf_bytes: bytes, duplex: str | None = None, color_mode: str | None = None) -> bytes:
    """Wrap raw PDF bytes with PJL header and footer if duplex or color mode is specified."""
    has_duplex = bool(duplex and duplex.lower() not in ("off", "none", "false"))
    has_color_mode = bool(color_mode)

    if not has_duplex and not has_color_mode:
        return pdf_bytes

    pjl_lines = ["\x1b%-12345X@PJL"]

    if has_duplex:
        pjl_lines.append("@PJL SET DUPLEX = ON")
        mode = duplex.lower().replace("_", "-")
        if mode in ("short-edge", "short"):
            pjl_lines.append("@PJL SET BINDING = SHORTEDGE")
        elif mode in ("long-edge", "long"):
            pjl_lines.append("@PJL SET BINDING = LONGEDGE")

    if has_color_mode:
        cmode = color_mode.lower()
        if cmode in ("grayscale", "monochrome", "bw", "gray"):
            pjl_lines.append("@PJL SET RENDERMODE = GRAYSCALE")
            pjl_lines.append("@PJL SET COLORMODE = MONOCHROME")
        elif cmode == "color":
            pjl_lines.append("@PJL SET RENDERMODE = COLOR")
            pjl_lines.append("@PJL SET COLORMODE = COLOR")

    pjl_lines.append("@PJL ENTER LANGUAGE = PDF\n")

    header = "\n".join(pjl_lines).encode("ascii")
    footer = b"\n\x1b%-12345X@PJL\n@PJL EOJ\n\x1b%-12345X\n"

    return header + pdf_bytes + footer


def send_to_printer(
    pdf_path: str | Path,
    *,
    duplex: str | None = None,
    remove_pages: list[int] | None = None,
    color_mode: str | None = None,
) -> tuple[bool, str]:
    """Send a PDF file directly to the configured network/office printer.

    Args:
        pdf_path: Path to the PDF file.
        duplex: Optional duplex mode, e.g. 'short-edge', 'long-edge', 'off'.
        remove_pages: Optional list of 1-indexed page numbers to remove before printing.
        color_mode: Optional color mode, e.g. 'grayscale', 'color'.

    Returns:
        tuple[bool, str]: (success, status_message)
    """
    cfg = current_app.config

    if not cfg.get("PRINTER_ENABLED", True):
        return False, "Printing is currently disabled in system configuration."

    orig_path = Path(pdf_path)
    if not orig_path.is_file() or orig_path.stat().st_size == 0:
        return False, f"PDF file not found or empty at {orig_path}"

    host = cfg.get("PRINTER_HOST", "192.168.5.115")
    port = int(cfg.get("PRINTER_PORT", 9100))
    printer_name = cfg.get("PRINTER_NAME", "RICOH MP C2004ex PCL 6")
    method = cfg.get("PRINTER_METHOD", "auto").lower()
    timeout = int(cfg.get("PRINTER_TIMEOUT", 10))

    path, temp_dir = _prepare_print_pdf(orig_path, remove_pages=remove_pages)

    try:
        # 1. Try RAW TCP Socket Direct Streaming (Port 9100)
        if method in ("socket", "auto"):
            try:
                current_app.logger.info(
                    "Sending PDF %s (duplex=%s, remove_pages=%s, color_mode=%s) to printer socket %s:%d...",
                    path.name, duplex, remove_pages, color_mode, host, port
                )
                pdf_data = path.read_bytes()
                payload = _build_pjl_stream(pdf_data, duplex=duplex, color_mode=color_mode)

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(timeout)
                    s.connect((host, port))
                    s.sendall(payload)

                mode_desc = f" [{color_mode.upper()}]" if color_mode else ""
                msg = f"Successfully sent PDF{mode_desc} to {printer_name} ({host}:{port})."
                current_app.logger.info(msg)
                return True, msg
            except (socket.timeout, socket.error, OSError) as err:
                err_msg = f"Failed to connect to printer socket {host}:{port}: {err}"
                current_app.logger.warning(err_msg)
                if method == "socket":
                    return False, err_msg

        # 2. Try Command-line Print Fallback
        if method in ("command", "auto"):
            # Linux / Docker lpr fallback
            lpr_bin = shutil.which("lpr")
            if lpr_bin:
                try:
                    cmd = [lpr_bin, "-H", f"{host}:{port}"]
                    if duplex and duplex.lower() not in ("off", "none", "false"):
                        mode = duplex.lower().replace("_", "-")
                        if mode in ("short-edge", "short"):
                            cmd.extend(["-o", "sides=two-sided-short-edge"])
                        elif mode in ("long-edge", "long"):
                            cmd.extend(["-o", "sides=two-sided-long-edge"])
                    if color_mode and color_mode.lower() in ("grayscale", "monochrome", "bw", "gray"):
                        cmd.extend(["-o", "ColorModel=Gray"])
                    elif color_mode and color_mode.lower() == "color":
                        cmd.extend(["-o", "ColorModel=Color"])
                    cmd.append(str(path))
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                    if res.returncode == 0:
                        msg = f"Sent PDF to {printer_name} via lpr."
                        current_app.logger.info(msg)
                        return True, msg
                    current_app.logger.warning("lpr failed: %s", res.stderr)
                except Exception as ex:
                    current_app.logger.warning("lpr execution error: %s", ex)

            # LibreOffice headless print fallback
            soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
            if soffice_bin:
                try:
                    cmd = [soffice_bin, "--headless", "--pt", printer_name, str(path)]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 2)
                    if res.returncode == 0:
                        msg = f"Sent PDF to {printer_name} via LibreOffice."
                        current_app.logger.info(msg)
                        return True, msg
                    current_app.logger.warning("LibreOffice print failed: %s", res.stderr)
                except Exception as ex:
                    current_app.logger.warning("LibreOffice print execution error: %s", ex)

        return False, f"Could not reach printer {printer_name} ({host}:{port}). Please check printer power and network connection."
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()
