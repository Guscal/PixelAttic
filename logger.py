"""
logger.py — Crash logging and application logging for Pixel Attic.

Writes to ~/.pixelattic/logs/  with rotating daily files.
On unhandled exception: writes full traceback + system info.
"""
import sys
import os
import logging
import traceback
import platform
from pathlib import Path
from datetime import datetime

# ── Log directory ─────────────────────────────────────────────────────────────
LOG_DIR = Path.home() / ".pixelattic" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Keep only last 10 log files
def _rotate_logs():
    logs = sorted(LOG_DIR.glob("pixelattic_*.log"))
    for old in logs[:-9]:
        try: old.unlink()
        except: pass

_rotate_logs()

# ── Logger setup ──────────────────────────────────────────────────────────────
_today      = datetime.now().strftime("%Y-%m-%d")
_log_file   = LOG_DIR / f"pixelattic_{_today}.log"

# Root logger
logger = logging.getLogger("pixelattic")
logger.setLevel(logging.DEBUG)

# File handler — full detail
_fh = logging.FileHandler(_log_file, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    datefmt="%H:%M:%S"
))
logger.addHandler(_fh)

# Console handler — only warnings+
_ch = logging.StreamHandler(sys.stdout)
_ch.setLevel(logging.WARNING)
_ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(_ch)

# Convenience shortcuts
log_info    = logger.info
log_warn    = logger.warning
log_error   = logger.error
log_debug   = logger.debug


# ── Crash handler ─────────────────────────────────────────────────────────────

def _write_crash_report(exc_type, exc_value, exc_tb):
    """Write a full crash report to a dedicated crash file."""
    crash_file = LOG_DIR / f"CRASH_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

    tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))

    try:
        import importlib.metadata as _im
        pyside_ver = _im.version("PySide2")
    except Exception:
        pyside_ver = "unknown"

    report = [
        "=" * 70,
        "  PIXEL ATTIC — CRASH REPORT",
        "=" * 70,
        f"  Time     : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"  OS       : {platform.platform()}",
        f"  Python   : {sys.version.split()[0]}",
        f"  PySide2  : {pyside_ver}",
        f"  Arch     : {platform.machine()}",
        "=" * 70,
        "",
        tb_str,
        "=" * 70,
        "",
        "  RECENT LOG ENTRIES:",
        "",
    ]

    # Append last 50 lines of today's log
    try:
        with open(_log_file, "r", encoding="utf-8") as f:
            recent = f.readlines()[-50:]
        report.extend(recent)
    except Exception:
        report.append("  (could not read log file)")

    report.append("=" * 70)

    with open(crash_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    # Also log to normal log
    logger.critical(f"UNHANDLED EXCEPTION — crash report: {crash_file}")
    logger.critical(tb_str)

    return crash_file


def install_crash_handler():
    """
    Install global exception handler.
    Shows a user-friendly dialog with crash file path, then exits.
    """
    def _handler(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return

        crash_file = _write_crash_report(exc_type, exc_value, exc_tb)

        # Try to show Qt dialog if app is running
        try:
            from PySide2.QtWidgets import QApplication, QMessageBox
            app = QApplication.instance()
            if app:
                msg = QMessageBox()
                msg.setWindowTitle("Pixel Attic — Unexpected Error")
                msg.setIcon(QMessageBox.Critical)
                msg.setText(
                    "<b>Pixel Attic crashed unexpectedly.</b><br><br>"
                    "A crash report has been saved to:<br>"
                    f"<code>{crash_file}</code><br><br>"
                    "Please report this file when contacting support."
                )
                msg.setDetailedText(
                    "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
                msg.exec_()
        except Exception:
            # Qt is gone — just print
            print(f"\n{'='*60}")
            print("PIXEL ATTIC CRASHED")
            print(f"Crash report: {crash_file}")
            print('='*60)

        sys.exit(1)

    sys.excepthook = _handler
    logger.info(f"Crash handler installed — log: {_log_file}")


def get_log_dir() -> Path:
    return LOG_DIR

def get_log_file() -> Path:
    return _log_file
