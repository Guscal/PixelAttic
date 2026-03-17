"""
icons.py — Icon path resolver for Pixel Attic.
Icons live in icons/ folder next to the scripts.
"""
import sys
from pathlib import Path

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    _BASE = Path(sys._MEIPASS)
else:
    _BASE = Path(__file__).resolve().parent

_ICON_DIR = _BASE / "icons"
_cache: dict = {}


def icon_path(name: str) -> str:
    if name in _cache:
        return _cache[name]
    p = str(_ICON_DIR / name)
    _cache[name] = p
    return p


def icon_exists(name: str) -> bool:
    return (_ICON_DIR / name).exists()


def icon_dir() -> Path:
    return _ICON_DIR
