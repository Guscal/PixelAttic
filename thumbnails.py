"""
thumbnails.py — Thumbnail generation, caching, and DPG texture loading.
"""

import hashlib
import math
import random
from pathlib import Path
from typing import Optional

from config import THUMBS_DIR, THUMB_W, THUMB_H

try:
    from PIL import Image, ImageDraw, ImageFilter
    PIL_OK = True
except ImportError:
    PIL_OK = False


def _get_thumb_size() -> tuple:
    """Get thumbnail dimensions from settings (with fallback to config defaults)."""
    try:
        from settings import Settings, THUMB_PRESETS
        s = Settings.load()
        return THUMB_PRESETS.get(
            getattr(s, 'thumbnail_resolution', 'medium'), (THUMB_W, THUMB_H))
    except Exception:
        return (THUMB_W, THUMB_H)

# ── Thumbnail cache ────────────────────────────────────────────────────────────

def thumb_cache_path(asset_id: str) -> Path:
    return THUMBS_DIR / f"{asset_id}.png"

def load_or_generate(asset) -> Optional[Path]:
    """
    Returns a Path to a thumbnail PNG.
    Priority:
      1. Already cached → return immediately
      2. Image file → open directly
      3. Video/sequence → extract middle frame via ffmpeg
      4. Last resort → simple dark placeholder (no procedural art)
    """
    cache = thumb_cache_path(asset.id)
    if cache.exists():
        # Validate: a real PNG/image thumbnail is at least 500 bytes.
        # Zero-byte or tiny files indicate a failed previous generation.
        try:
            _size = cache.stat().st_size
            if _size < 500:
                cache.unlink(missing_ok=True)
            else:
                return cache
        except Exception:
            pass  # stat failed — try to regenerate

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    src = Path(asset.path)
    tw, th = _get_thumb_size()

    # ── LDR image files (PIL-readable) ───────────────────────────────────────
    _LDR_EXTS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tiff", ".tif"}
    if PIL_OK and src.exists() and src.suffix.lower() in _LDR_EXTS:
        try:
            img = Image.open(src).convert("RGBA")
            img.thumbnail((tw, th), Image.LANCZOS)
            out = Image.new("RGBA", (tw, th), (10, 10, 18, 255))
            x = (tw - img.width)  // 2
            y = (th - img.height) // 2
            out.paste(img, (x, y))
            out.save(cache)
            return cache
        except Exception:
            pass

    # ── HDR / EXR / DPX single frames — convert via ffmpeg ───────────────────
    _HDR_EXTS = {".exr", ".dpx", ".hdr", ".pic", ".cin", ".sxr"}
    if src.exists() and src.suffix.lower() in _HDR_EXTS:
        if _ffmpeg_single_frame(src, cache):
            return cache

    # ── Video — extract middle frame via ffmpeg ──────────────────────────────
    if asset.file_type == "video" and src.exists():
        if _extract_middle_frame(src, cache, asset):
            return cache

    # ── Sequence — grab middle frame from sequence ───────────────────────────
    if asset.file_type == "sequence" and src.exists():
        if _extract_middle_frame(src, cache, asset):
            return cache

    # ── Minimal dark placeholder (no procedural art) ─────────────────────────
    if PIL_OK:
        try:
            img = Image.new("RGBA", (tw, th), (12, 12, 20, 255))
            draw = ImageDraw.Draw(img)
            # Format label in center
            label = asset.format or asset.file_type.upper() or "?"
            draw.text((tw // 2, th // 2), label,
                      fill=(50, 60, 80, 200), anchor="mm")
            img.save(cache)
            return cache
        except Exception:
            pass

    return None

def _ffmpeg_single_frame(src: Path, out: Path) -> bool:
    """Convert a single HDR/EXR/DPX frame to a tonemapped PNG thumbnail via ffmpeg."""
    tw, th = _get_thumb_size()
    try:
        import shutil, subprocess
        # Prefer the configured ffmpeg from preview module (user-set path)
        try:
            import preview as _prev
            ffmpeg = _prev.FFMPEG
        except Exception:
            ffmpeg = None
        if not ffmpeg:
            ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            for p in [r"C:\ffmpeg\bin\ffmpeg.exe",
                      r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
                if Path(p).exists():
                    ffmpeg = p
                    break
        if not ffmpeg:
            return False

        # Tonemap HDR→SDR with zscale + tonemap, then scale to thumbnail size
        vf = (
            f"zscale=t=linear:npl=100,format=gbrpf32le,"
            f"zscale=p=bt709,tonemap=hable,zscale=t=bt709:m=bt709:r=tv,"
            f"format=yuv420p,"
            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=0a0a12"
        )
        cmd = [ffmpeg, "-y", "-i", str(src), "-vf", vf, "-vframes", "1", str(out)]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=20)
        if result.returncode == 0 and out.exists():
            return True

        # Fallback: no tonemap, just scale (works for non-HDR EXR)
        vf2 = (
            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=0a0a12"
        )
        cmd2 = [ffmpeg, "-y", "-i", str(src), "-vf", vf2, "-vframes", "1", str(out)]
        result2 = subprocess.run(cmd2, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=20)
        return result2.returncode == 0 and out.exists()
    except Exception:
        return False

def _extract_middle_frame(src: Path, out: Path, asset) -> bool:
    """Extract the middle frame of a video/sequence using ffmpeg."""
    tw, th = _get_thumb_size()
    try:
        import shutil, subprocess
        # Prefer user-configured ffmpeg from preview module
        ffmpeg = None
        try:
            import preview as _prev
            ffmpeg = _prev.FFMPEG
        except Exception:
            pass
        if not ffmpeg:
            ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            for p in [r"C:\ffmpeg\bin\ffmpeg.exe",
                      r"C:\Program Files\ffmpeg\bin\ffmpeg.exe"]:
                if Path(p).exists():
                    ffmpeg = p
                    break
        if not ffmpeg:
            return False

        if asset.file_type == "video":
            # Get duration, seek to middle
            dur_cmd = [ffmpeg, "-i", str(src)]
            r = subprocess.run(dur_cmd, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL)
            import re
            m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr.decode(errors="replace"))
            seek = "00:00:02"  # fallback: 2s in
            if m:
                h, mn, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
                total = h*3600 + mn*60 + s
                mid   = total / 2
                seek  = f"{int(mid//3600):02d}:{int((mid%3600)//60):02d}:{mid%60:06.3f}"

            cmd = [ffmpeg, "-y", "-ss", seek, "-i", str(src),
                   "-vframes", "1",
                   "-vf", f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                          f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=0a0a12",
                   str(out)]
        else:
            # Sequence — grab middle frame
            import re as _re
            stem   = src.stem
            m2     = _re.match(r"^(.+?)(\d+)$", stem)
            if not m2:
                return False
            base, digits = m2.group(1), m2.group(2)
            n_dig  = len(digits)
            pattern = src.parent / f"{base}%0{n_dig}d{src.suffix}"
            start_n = int(digits)
            mid_n   = start_n + 12  # approx middle, good enough for thumb
            cmd = [ffmpeg, "-y",
                   "-start_number", str(start_n),
                   "-i", str(pattern),
                   "-vf", (
                       f"select=gte(n,{mid_n - start_n}),"
                       f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
                       f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=0a0a12"
                   ),
                   "-vframes", "1", str(out)]

        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=15)
        return result.returncode == 0 and out.exists()
    except Exception:
        return False

def purge_placeholder_thumbnails(lib) -> int:
    """
    Delete cached thumbnails that are text placeholders (e.g. "MOV").
    Uses file size: real ffmpeg frames are always >6KB.
    A PIL-drawn text placeholder is always <3KB.
    Called once on startup when ffmpeg is available.
    """
    # Only run if ffmpeg is actually available — otherwise we'd just
    # regenerate another placeholder
    try:
        import preview as _prev
        if not _prev.FFMPEG:
            return 0
    except Exception:
        return 0

    purged = 0
    for asset in lib.all_assets():
        if asset.file_type not in ("video", "sequence"):
            continue
        cache = thumb_cache_path(asset.id)
        if not cache.exists():
            continue
        try:
            # Real frame thumbnail from ffmpeg: always > 6 KB
            # PIL text placeholder (dark bg + "MOV" text): always < 3 KB
            # Zero-byte or tiny files indicate a failed generation
            size_kb = cache.stat().st_size / 1024
            if size_kb < 6:
                cache.unlink(missing_ok=True)
                purged += 1
        except Exception:
            # stat/unlink failed — try to remove anyway
            try: cache.unlink(missing_ok=True); purged += 1
            except Exception: pass
    return purged

# ── Procedural thumbnail generation ──────────────────────────────────────────

def load_texture_data(path: Path) -> Optional[tuple[int, int, list[float]]]:
    """Load a PNG thumbnail and return (width, height, flat_rgba_floats) for DPG."""
    if not PIL_OK or not path or not path.exists():
        return None
    try:
        tw, th = _get_thumb_size()
        img = Image.open(path).convert("RGBA").resize((tw, th))
        pixels = list(img.getdata())
        flat = [v / 255.0 for px in pixels for v in px]
        return tw, th, flat
    except Exception as e:
        print(f"[Thumb] Load texture error: {e}")
        return None

def get_placeholder_texture() -> tuple[int, int, list[float]]:
    """Generate a minimal dark placeholder for missing thumbnails."""
    tw, th = _get_thumb_size()
    w, h = tw, th
    flat = []
    for y in range(h):
        for x in range(w):
            # Subtle grid
            grid = 0.06 if (x % 20 == 0 or y % 20 == 0) else 0.04
            flat += [grid, grid, grid + 0.01, 1.0]
    return w, h, flat
