"""
settings.py — Persistent user preferences for Pixel Attic.
Saved to ~/.pixelattic/settings.json
"""

import json
from pathlib import Path
from dataclasses import dataclass, asdict

SETTINGS_FILE = Path.home() / ".pixelattic" / "settings.json"

# ── Bootstrap path overrides ──────────────────────────────────────────────────
# paths.json lives in a FIXED location and stores custom paths for all
# other files (including settings.json itself). Solves the chicken-and-egg.
_BOOTSTRAP_FILE = Path.home() / ".pixelattic" / "paths.json"
_BOOTSTRAP_DEFAULTS = {
    "settings": str(SETTINGS_FILE),
    "library":  "",
    "backup":   "",
    "thumbs":   "",
    "proxies":  "",
}

def _read_bootstrap() -> dict:
    try:
        if _BOOTSTRAP_FILE.exists():
            import json as _j
            return {**_BOOTSTRAP_DEFAULTS, **_j.loads(_BOOTSTRAP_FILE.read_text())}
    except Exception:
        pass
    return dict(_BOOTSTRAP_DEFAULTS)

def _write_bootstrap(paths: dict):
    try:
        import json as _j
        _BOOTSTRAP_FILE.parent.mkdir(parents=True, exist_ok=True)
        _BOOTSTRAP_FILE.write_text(_j.dumps(paths, indent=2))
    except Exception as e:
        print(f"[Settings] bootstrap write error: {e}")

def get_effective_settings_file() -> Path:
    bp = _read_bootstrap()
    custom = bp.get("settings", "").strip()
    return Path(custom) if custom and custom != str(SETTINGS_FILE) else SETTINGS_FILE

# ── Preset Themes ─────────────────────────────────────────────────────────────
# Each theme defines bg, bg2, panel, border, text, text_dim, accent colors
THEMES: dict[str, dict] = {
    "Dark Industrial": {
        "bg":          ( 10,  10,  18),
        "bg2":         ( 13,  13,  22),
        "panel":       (  9,   9,  16),
        "panel2":      ( 14,  14,  24),
        "border":      ( 30,  30,  50),
        "border_lt":   ( 40,  40,  65),
        "text":        (226, 232, 240),
        "text_med":    (148, 163, 184),
        "text_dim":    ( 71,  85, 105),
        "text_faint":  ( 36,  42,  58),
        "hover":       ( 20,  20,  34),
        "selected":    ( 28,  28,  48),
    },
    "Darker Void": {
        "bg":          (  5,   5,  10),
        "bg2":         (  8,   8,  14),
        "panel":       (  4,   4,   8),
        "panel2":      (  9,   9,  15),
        "border":      ( 20,  20,  35),
        "border_lt":   ( 28,  28,  48),
        "text":        (210, 220, 235),
        "text_med":    (130, 145, 165),
        "text_dim":    ( 55,  68,  90),
        "text_faint":  ( 28,  34,  48),
        "hover":       ( 14,  14,  26),
        "selected":    ( 20,  20,  38),
    },
    "Slate Blue": {
        "bg":          ( 12,  14,  24),
        "bg2":         ( 16,  18,  30),
        "panel":       ( 10,  12,  22),
        "panel2":      ( 16,  19,  32),
        "border":      ( 32,  38,  65),
        "border_lt":   ( 45,  52,  82),
        "text":        (220, 228, 245),
        "text_med":    (140, 155, 190),
        "text_dim":    ( 68,  80, 115),
        "text_faint":  ( 34,  40,  62),
        "hover":       ( 22,  26,  44),
        "selected":    ( 30,  36,  58),
    },
    "Charcoal": {
        "bg":          ( 18,  18,  18),
        "bg2":         ( 22,  22,  22),
        "panel":       ( 15,  15,  15),
        "panel2":      ( 22,  22,  22),
        "border":      ( 42,  42,  42),
        "border_lt":   ( 55,  55,  55),
        "text":        (230, 230, 230),
        "text_med":    (160, 160, 160),
        "text_dim":    ( 90,  90,  90),
        "text_faint":  ( 48,  48,  48),
        "hover":       ( 30,  30,  30),
        "selected":    ( 40,  40,  40),
    },
    "Forest": {
        "bg":          (  8,  14,  10),
        "bg2":         ( 10,  18,  13),
        "panel":       (  7,  12,   9),
        "panel2":      ( 11,  17,  13),
        "border":      ( 22,  40,  28),
        "border_lt":   ( 30,  55,  38),
        "text":        (210, 235, 215),
        "text_med":    (130, 175, 140),
        "text_dim":    ( 55,  90,  65),
        "text_faint":  ( 28,  46,  34),
        "hover":       ( 14,  24,  17),
        "selected":    ( 20,  34,  24),
    },
    "Nord": {
        "bg":          ( 46,  52,  64),
        "bg2":         ( 59,  66,  82),
        "panel":       ( 36,  41,  51),
        "panel2":      ( 52,  59,  74),
        "border":      ( 67,  76,  94),
        "border_lt":   ( 76,  86, 106),
        "text":        (236, 239, 244),
        "text_med":    (216, 222, 233),
        "text_dim":    (144, 157, 178),
        "text_faint":  ( 76,  86, 106),
        "hover":       ( 55,  62,  77),
        "selected":    ( 67,  76,  94),
    },
}

# ── Accent Color Presets ───────────────────────────────────────────────────────
ACCENT_COLORS: dict[str, tuple] = {
    # Warm
    "Orange":     (249, 115,  22),
    "Amber":      (245, 158,  11),
    "Gold":       (251, 191,  36),
    "Red":        (248, 113, 113),
    "Rose":       (251,  71, 120),
    # Cool
    "Blue":       ( 96, 165, 250),
    "Indigo":     (129, 140, 248),
    "Cyan":       ( 34, 211, 238),
    "Teal":       ( 45, 212, 191),
    # Nature
    "Green":      ( 52, 211, 153),
    "Lime":       (163, 230,  53),
    "Nord Green": (163, 190, 140),
    # Pastel / vivid
    "Purple":     (167, 139, 250),
    "Violet":     (192, 132, 252),
    "Pink":       (244, 114, 182),
    # Neutral
    "Silver":     (148, 163, 184),
    "Slate":      (100, 116, 139),
}

# ── Card Size Presets ─────────────────────────────────────────────────────────
CARD_SIZES: dict[str, tuple] = {
    "Small":  (160, 160),   # (card_w, card_h)
    "Medium": (210, 200),
    "Large":  (270, 250),
    "X-Large": (340, 310),
}

# ── Settings Dataclass ────────────────────────────────────────────────────────
@dataclass
class Settings:
    # Library
    skip_duplicates:       bool = True     # skip files already in library on import

    # Appearance
    theme:        str = "Dark Industrial"
    accent_color: str = "Orange"
    card_size:    str = "Medium"     # DEFAULT on startup (toolbar changes are session-only)
    view_mode_default: str = "grid"  # default view on startup
    page_size:    int = 50           # assets per page (25/50/100)

    # Session state — restored on next launch
    sort_by:            str  = "name"    # name / date / size
    sort_reverse:       bool = False
    view_mode:          str  = "grid"    # grid / list
    time_display_mode:  str  = "frames"  # 'frames' or 'timecode'
    last_category:      str  = "All"     # restored on startup if enabled

    # Import defaults

    # Behavior
    confirm_before_delete: bool = True

    # Grid
    grid_show_filename:   bool = True
    grid_show_resolution: bool = True
    grid_show_tags:       bool = True

    # Font
    font_name: str = "Default"
    font_size: int = 14

    # Viewer apps (empty = use system default)
    viewer_video:    str = r"C:\Program Files\djv\bin\djv.exe"
    viewer_image:    str = ""
    viewer_sequence: str = r"C:\Program Files\djv\bin\djv.exe"

    # FFmpeg path (empty = auto-detect from PATH)
    ffmpeg_path:     str = ""

    # VLC path (directory containing libvlc.dll, empty = auto-detect)
    vlc_path:        str = ""
    proxy_dir:       str = ""   # empty = use default ~/.pixelattic/proxies
    # Custom storage paths (empty = use app defaults)
    custom_library_path: str = ""
    custom_thumbs_path:  str = ""
    custom_backup_path:  str = ""

    # Window state (saved on close, restored on open)
    window_x:         int  = 100
    window_y:         int  = 100
    window_w:         int  = 1440
    window_h:         int  = 900
    window_maximized: bool = False

    # Splitter positions (saved on close, restored on open)
    sidebar_width:    int  = 215
    detail_width:     int  = 320

    # Storage backend: 'json' (default) or 'sqlite'
    storage_backend:  str  = "sqlite"

    # Performance
    gpu_acceleration:      bool = False
    thumbnail_quality:     str  = "fast"   # "fast" (nearest-neighbor) or "smooth" (bilinear)
    lazy_thumbnails:       bool = True     # load thumbnails in background thread
    auto_generate_proxies: bool = True     # auto-generate proxy videos on import
    proxy_resolution:      str  = "720p"   # "480p", "720p", "1080p"
    scrub_frames:          int  = 8        # frames in hover scrub strip (4/8/12)
    max_memory_thumbs:     int  = 500      # max thumbnails kept in memory cache
    thumbnail_resolution:  str  = "medium" # "low" (160x120), "medium" (200x150), "high" (320x240)

    # Behavior
    restore_last_category: bool = True     # restore last active category on startup
    show_import_summary:   bool = True     # show error summary after import
    double_click_action:   str  = "open"   # "open" / "explorer" / "copy_path" / "nothing"

    # Custom categories (added by user, persisted here)
    custom_categories:      list = None
    hidden_base_categories: list = None  # base cats removed by user

    # Saved search presets
    saved_searches: list = None  # [{"name": str, "tokens": [{"kind": str, "value": str}, ...]}]

    def __post_init__(self):
        if self.custom_categories is None:
            self.custom_categories = []
        if self.hidden_base_categories is None:
            self.hidden_base_categories = []
        if self.saved_searches is None:
            self.saved_searches = []

    def save(self):
        SETTINGS_FILE.parent.mkdir(exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    @classmethod
    def load(cls) -> "Settings":
        if not SETTINGS_FILE.exists():
            s = cls()
            s.save()
            return s
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Only use keys that exist in the dataclass (forward compat)
            valid = {k: v for k, v in data.items()
                     if k in cls.__dataclass_fields__}
            s = cls(**valid)
            # Validate font — if it can't be confirmed as a real TTF/OTF, reset
            if s.font_name != "Default":
                from pathlib import Path as _Path
                VALID_MAGIC = {b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"}
                fonts_dir = _Path("C:/Windows/Fonts")
                font_ok = False
                for ext in ("*.ttf", "*.otf"):
                    for p in fonts_dir.glob(ext):
                        if p.stem == s.font_name:
                            try:
                                with open(p, "rb") as f2:
                                    if f2.read(4) in VALID_MAGIC:
                                        font_ok = True
                            except Exception:
                                pass
                            break
                if not font_ok:
                    print(f"[Settings] Font '{s.font_name}' invalid — resetting to Default")
                    s.font_name = "Default"
                    s.save()
            return s
        except Exception as e:
            print(f"[Settings] Load error: {e} — using defaults")
            return cls()

    def effective_accent(self) -> tuple:
        return ACCENT_COLORS.get(self.accent_color, ACCENT_COLORS["Orange"])

    def effective_theme(self) -> dict:
        return THEMES.get(self.theme, THEMES["Dark Industrial"])

    def effective_card_size(self) -> tuple:
        return CARD_SIZES.get(self.card_size, CARD_SIZES["Medium"])


# ── Proxy Resolution Presets ─────────────────────────────────────────────────
PROXY_RESOLUTIONS = {
    "480p":  (854,  480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
}

def proxy_scale_filter(res_key: str = "720p") -> str:
    """Return ffmpeg -vf scale filter for the given proxy resolution."""
    w, _ = PROXY_RESOLUTIONS.get(res_key, (1280, 720))
    return f"scale='min({w},iw)':trunc(ow/a/2)*2"


# ── Thumbnail Resolution Presets ─────────────────────────────────────────────
THUMB_PRESETS = {
    "low":    (160, 120),
    "medium": (200, 150),
    "high":   (320, 240),
}


# ── Contrast Utilities ───────────────────────────────────────────────────────

def luminance(r: int, g: int, b: int) -> float:
    """Relative luminance (0-1) per WCAG 2.0."""
    def _c(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * _c(r) + 0.7152 * _c(g) + 0.0722 * _c(b)


def text_color_for_bg(r: int, g: int, b: int) -> str:
    """Return 'rgb(...)' text color that contrasts with the given background.
    Light bg → dark text, dark bg → light text."""
    lum = luminance(r, g, b)
    if lum > 0.35:
        return "rgb(8,8,16)"       # dark text on light bg
    return "rgb(220,228,245)"      # light text on dark bg


def accent_text_color(accent_name: str) -> str:
    """Return text color that contrasts with the given accent color."""
    r, g, b = ACCENT_COLORS.get(accent_name, (249, 115, 22))
    return text_color_for_bg(r, g, b)

