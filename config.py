"""
config.py — App-wide constants, categories, tags, and theme colors.
"""

from pathlib import Path

# ── App meta ──────────────────────────────────────────────────────────────────
APP_NAME    = "PIXEL ATTIC"
VERSION     = "1.0.0"
APP_DIR     = Path.home() / ".pixelattic"
LIBRARY_FILE= APP_DIR / "library.json"
THUMBS_DIR  = APP_DIR / "thumbs"

# ── Apply custom paths from bootstrap (paths.json) ───────────────────────
# This runs at import time so all modules see the correct paths.
def _apply_bootstrap_paths():
    global APP_DIR, LIBRARY_FILE, THUMBS_DIR
    _bp_file = Path.home() / ".pixelattic" / "paths.json"
    try:
        if _bp_file.exists():
            import json as _j
            bp = _j.loads(_bp_file.read_text(encoding="utf-8"))
            _lib  = (bp.get("library")  or "").strip()
            _th   = (bp.get("thumbs")   or "").strip()
            if _lib:  LIBRARY_FILE = Path(_lib)
            if _th:   THUMBS_DIR   = Path(_th)
    except Exception as _e:
        print(f"[Config] bootstrap path error: {_e}")

_apply_bootstrap_paths()
THUMB_W, THUMB_H = 200, 150

# ── File types ────────────────────────────────────────────────────────────────
VFX_EXTENSIONS = {
    # Video containers
    "video": [
        ".mov", ".mp4", ".avi", ".mxf", ".mkv", ".wmv", ".webm",
        ".m4v", ".flv", ".f4v", ".mpg", ".mpeg", ".m2v", ".m2ts",
        ".mts", ".ts", ".vob", ".3gp", ".3g2",
        # RAW camera / high-end
        ".r3d",   # RED
        ".braw",  # Blackmagic RAW
        ".ari",   # ARRI
        ".mxf",   # broadcast/cinema wrapper (also above, deduped)
        ".dng",   # Adobe DNG video (DJI, etc)
        ".crm",   # Canon RAW Movie
        ".nef",   # Nikon video
    ],
    # Note: .exr/.dpx/.hdr/.tif are in "image" above.
    # file_type="sequence" is set only by Asset.from_sequence().
    # Still images
    "image": [
        ".png",
        ".jpg", ".jpeg",
        ".tga",          # Targa — common alpha channel format
        ".bmp",
        ".psd",          # Photoshop
        ".psb",          # Photo
        ".tif", ".tiff",  # TIFF
        ".exr",   # OpenEXR (single frame)
        ".dpx",   # DPX (single frame)
        ".hdr",   # Radiance HDRshop Large
        ".gif",
        ".webp",
        ".dng",          # Adobe DNG still (RAW)
        ".cr2", ".cr3",  # Canon RAW
        ".nef", ".nrw",  # Nikon RAW
        ".arw", ".srf",  # Sony RAW
        ".orf",          # Olympus RAW
        ".rw2",          # Panasonic RAW
        ".raf",          # Fuji RAW
        ".raw",          # Generic RAW
        ".heic", ".heif",# Apple HEIC
        ".jp2", ".jpx",  # JPEG 2000
        ".ico",
        ".svg",
    ],
}

# Flat list of all extensions (lowercase, with dot)
ALL_EXT = sorted({e for exts in VFX_EXTENSIONS.values() for e in exts})

# Extension → file_type lookup
EXT_TO_TYPE: dict[str, str] = {
    ext: ftype
    for ftype, exts in VFX_EXTENSIONS.items()
    for ext in exts
}

# Human-readable format label (ext without dot, uppercase)
def ext_label(ext: str) -> str:
    return ext.lstrip(".").upper()

# ── Categories ────────────────────────────────────────────────────────────────
BASE_CATEGORIES = [
    "All", "Fire", "Smoke", "Explosions", "Particles",
    "Mattes", "Transitions", "Atmospherics", "Liquids",
    "Distortion", "Lens FX", "Grunge", "Blood & Gore",
    "Magic & Energy", "Misc",
]

CATEGORY_ICONS = {
    "All":            "●",
    "Fire":           "◆",
    "Smoke":          "◇",
    "Explosions":     "◆",
    "Particles":      "·",
    "Mattes":         "▪",
    "Transitions":    "»",
    "Atmospherics":   "○",
    "Liquids":        "~",
    "Distortion":     "◇",
    "Lens FX":        "◎",
    "Grunge":         "▪",
    "Blood & Gore":   "×",
    "Magic & Energy": "◆",
    "Misc":           "·",
}

def get_categories(custom: list = None, hidden: list = None) -> list:
    """Return full category list: base (minus hidden) + user-defined custom ones."""
    _hidden = set(hidden or [])
    cats = [c for c in BASE_CATEGORIES if c not in _hidden]
    for c in (custom or []):
        if c and c not in cats and c not in _hidden:
            cats.insert(-1, c)   # insert before Misc
    return cats

# Backward-compatible alias (without custom cats)
CATEGORIES = BASE_CATEGORIES

# ── Tags ──────────────────────────────────────────────────────────────────────
PRESET_TAGS = [
    # Resolution
    "8K", "4K", "2K", "HD",
    # Alpha
    "Alpha", "Pre-Mult", "Straight Alpha", "No Alpha",
    # Loop
    "Loop", "Seamless", "One-Shot",
    # Dynamic range
    "HDR", "SDR",
    # Format
    "EXR", "PNG", "MOV", "MP4", "DPX",
    # Tonality
    "Dark BG", "Bright", "Colored",
    # Motion speed
    "Slow", "Fast", "Still",
    # Blend mode hint
    "Overlay", "Screen", "Add", "Multiply",
    # License
    "Free", "Licensed", "Custom",
]

# ── Tag normalization ─────────────────────────────────────────────────────────
# Build a case-insensitive lookup from PRESET_TAGS once at import time
_PRESET_LOOKUP: dict[str, str] = {t.lower(): t for t in PRESET_TAGS}

def normalize_tag(tag: str) -> str:
    """Normalize a tag to standard casing.

    - Known presets keep their canonical casing (e.g. 'hdr' → 'HDR', 'alpha' → 'Alpha')
    - Unknown tags get Title Case (e.g. 'my cool tag' → 'My Cool Tag')
    Applied only when users *create* tags — auto-generated format/resolution tags
    already have correct casing from ext_label() / from_path().
    """
    s = tag.strip()
    if not s:
        return s
    canonical = _PRESET_LOOKUP.get(s.lower())
    if canonical:
        return canonical
    return s.title()

# Tag display colors (r, g, b) — used for colored pill badges
TAG_COLORS = {
    "8K":     (239,  68,  68),
    "4K":     (249, 115,  22),
    "2K":     (251, 146,  60),
    "HD":     (251, 191,  36),

    "Alpha":         (167, 139, 250),
    "Pre-Mult":      (139,  92, 246),
    "Straight Alpha":(124,  58, 237),
    "No Alpha":      ( 71,  85, 105),

    "Loop":     ( 52, 211, 153),
    "Seamless": (163, 230,  53),
    "One-Shot": (251, 146,  60),

    "HDR":  (251, 191,  36),
    "SDR":  (148, 163, 184),

    "EXR":  ( 96, 165, 250),
    "PNG":  (129, 140, 248),
    "MOV":  (244, 114, 182),
    "MP4":  (148, 163, 184),
    "DPX":  ( 45, 212, 191),

    "Dark BG":  ( 71,  85, 105),
    "Bright":   (253, 230, 138),
    "Colored":  (110, 231, 183),

    "Slow":  (125, 211, 252),
    "Fast":  (248, 113, 113),
    "Still": (100, 116, 139),

    "Overlay":  (192, 132, 252),
    "Screen":   (103, 232, 249),
    "Add":      (252, 211,  77),
    "Multiply": (134, 239, 172),

    "Free":     ( 74, 222, 128),
    "Licensed": (251, 146,  60),
    "Custom":   (148, 163, 184),
}

# ── Theme colors (Dear PyGui uses 0-255 RGBA) ─────────────────────────────────
C_BG          = ( 10,  10,  18, 255)
C_BG2         = ( 13,  13,  22, 255)
C_PANEL       = (  9,   9,  16, 255)
C_PANEL2      = ( 14,  14,  24, 255)
C_BORDER      = ( 30,  30,  50, 255)
C_BORDER_LT   = ( 40,  40,  65, 255)

C_TEXT        = (226, 232, 240, 255)
C_TEXT_MED    = (148, 163, 184, 255)
C_TEXT_DIM    = ( 71,  85, 105, 255)
C_TEXT_FAINT  = ( 36,  42,  58, 255)

C_ACCENT      = (249, 115,  22, 255)
C_ACCENT_DIM  = (249, 115,  22,  45)
C_ACCENT_MED  = (249, 115,  22, 120)

C_HOVER       = ( 20,  20,  34, 255)
C_SELECTED    = ( 28,  28,  48, 255)
C_SEL_BORDER  = (249, 115,  22, 200)

C_GREEN       = ( 52, 211, 153, 255)
C_RED         = (248, 113, 113, 255)
C_BLUE        = ( 96, 165, 250, 255)

GRID_CARD_W   = 220
GRID_CARD_H   = 210


# ── Sequence detection ────────────────────────────────────────────────────────

from dataclasses import dataclass as _dc
from pathlib import Path as _Path
from typing import List as _List
import re as _re

@_dc
class SequenceGroup:
    """Represents a detected image sequence (many files → one asset card).

    Attributes:
        base_path   First frame path (used as the asset path key).
        all_files   All frame paths, sorted.
        name        Human-readable sequence name  e.g. 'beauty_v01'
        frame_range (first_frame, last_frame)  e.g. (1001, 1088)
        padding     Detected zero-padding width   e.g. 4  → %04d
        ext         Common extension              e.g. '.exr'
    """
    base_path:   _Path
    all_files:   _List[_Path]
    name:        str
    frame_range: tuple
    padding:     int
    ext:         str

# Patterns to strip a trailing frame number from a stem.
# Order matters — more specific first.
_SEQ_PATTERNS = [
    # name.0001     name_0001     name-0001
    _re.compile(r'^(.*?)[._-](\d{2,9})$'),
    # name0001  (bare digits at end, at least 3 digits to avoid false positives)
    _re.compile(r'^(.*?)(\d{3,9})$'),
]


def _seq_key(stem: str):
    """Return (base_name, frame_number) if stem looks like a numbered frame, else None."""
    for pat in _SEQ_PATTERNS:
        m = pat.match(stem)
        if m:
            base, num_str = m.group(1), m.group(2)
            if base:  # don't accept pure-number filenames like "0001"
                return base, int(num_str), len(num_str)
    return None


def detect_sequences(paths: list) -> list:
    """Group a flat list of Path objects into sequences and lone files.

    Returns a list whose elements are either:
      - Path          — a single (non-sequence) file
      - SequenceGroup — a detected image/frame sequence
    """
    # Group by (parent_dir, extension, base_name)
    from collections import defaultdict
    groups: dict = defaultdict(list)  # key → [(frame_int, padding, path)]

    lone: list = []   # paths that don't parse as a frame

    # Video formats are never sequences — always keep as individual files
    VIDEO_EXTS = set(VFX_EXTENSIONS.get("video", []))

    for p in paths:
        if p.suffix.lower() in VIDEO_EXTS:
            lone.append(p)
            continue
        parsed = _seq_key(p.stem)
        if parsed is None:
            lone.append(p)
            continue
        base, frame_num, pad = parsed
        key = (str(p.parent), p.suffix.lower(), base)
        groups[key].append((frame_num, pad, p))

    result = []

    for (parent, ext, base), frames in groups.items():
        frames.sort(key=lambda x: x[0])

        # Need at least 2 frames to count as a sequence
        if len(frames) < 2:
            lone.append(frames[0][2])
            continue

        # Verify frames are roughly consecutive (allow gaps ≤ 10)
        nums = [f[0] for f in frames]
        span = nums[-1] - nums[0]
        if span > len(nums) * 10:
            # Too many gaps — probably unrelated files that share a prefix
            for _, _, p in frames:
                lone.append(p)
            continue

        all_paths = [f[2] for f in frames]
        padding   = frames[0][1]
        first_f   = frames[0][0]
        last_f    = frames[-1][0]
        seq_name  = base.rstrip('._- ')

        result.append(SequenceGroup(
            base_path   = all_paths[0],
            all_files   = all_paths,
            name        = seq_name,
            frame_range = (first_f, last_f),
            padding     = padding,
            ext         = ext,
        ))

    result.extend(lone)

    # Sort: sequences first, then singles, preserving original relative order
    result.sort(key=lambda x: (isinstance(x, _Path), str(x) if isinstance(x, _Path) else str(x.base_path)))
    return result
