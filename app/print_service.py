from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

from flask import current_app


def send_to_printer(pdf_path: str | Path) -> tuple[bool, str]:
    """Send a PDF file directly to the configured network/office printer.

    Returns:
        tuple[bool, str]: (success, status_message)
    """
    cfg = current_app.config

    if not cfg.get("PRINTER_ENABLED", True):
        return False, "Printing is currently disabled in system configuration."

    path = Path(pdf_path)
    if not path.is_file() or path.stat().st_size == 0:
        return False, f"PDF file not found or empty at {path}"

    host = cfg.get("PRINTER_HOST", "192.168.5.115")
    port = int(cfg.get("PRINTER_PORT", 9100))
    printer_name = cfg.get("PRINTER_NAME", "RICOH MP C2004ex PCL 6")
    method = cfg.get("PRINTER_METHOD", "auto").lower()
    timeout = int(cfg.get("PRINTER_TIMEOUT", 10))

    # 1. Try RAW TCP Socket Direct Streaming (Port 9100)
    if method in ("socket", "auto"):
        try:
            current_app.logger.info(
                "Sending PDF %s to printer socket %s:%d...", path.name, host, port
            )
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(timeout)
                s.connect((host, port))
                with open(path, "rb") as f:
                    while chunk := f.read(65536):
                        s.sendall(chunk)

            msg = f"Successfully sent PDF to {printer_name} ({host}:{port})."
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
                cmd = [lpr_bin, "-H", f"{host}:{port}", str(path)]
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
