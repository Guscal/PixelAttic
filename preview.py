"""
preview.py — FFmpeg-based preview generation for Pixel Attic.

Genera un "scrub strip" de N frames extraídos de un video o
de una secuencia de imágenes. El strip se guarda como:
    ~/.pixelattic/thumbs/{asset_id}_strip.png

El HoverScrubLabel widget reproduce el strip cuando el usuario
mueve el mouse sobre él.
"""
from __future__ import annotations

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import QLabel, QSizePolicy
from PySide2.QtGui     import QPixmap, QImage, QPainter
from PySide2.QtCore    import Qt, QPoint, QRect

from config import THUMBS_DIR


# ── FFmpeg detection ──────────────────────────────────────────────────────────

def ffmpeg_path() -> Optional[str]:
    """Return ffmpeg executable path if available, else None."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    # Common install locations on Windows
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Tools\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


FFMPEG = ffmpeg_path()

# ── Read configured ffmpeg path from settings at import time ─────────────────
# This runs before the App __init__, so the status bar sees the correct value
# immediately without waiting for _apply_ffmpeg().
def _load_ffmpeg_from_settings():
    global FFMPEG
    try:
        import json as _j
        _sf = Path.home() / ".pixelattic" / "settings.json"
        if _sf.exists():
            _data = _j.loads(_sf.read_text(encoding="utf-8"))
            _p = (_data.get("ffmpeg_path") or "").strip()
            if _p:
                _norm = str(Path(_p))
                if Path(_norm).exists():
                    FFMPEG = _norm
                    print(f"[Preview] ffmpeg from settings: {_norm}")
    except Exception as _e:
        print(f"[Preview] settings ffmpeg read error: {_e}")

_load_ffmpeg_from_settings()

N_FRAMES  = 8      # frames in scrub strip
THUMB_W   = 160    # width of each frame thumbnail
THUMB_H   = 90     # height (16:9 approx)


def set_proxy_dir(path: str):
    """Set a custom directory for proxy MP4 files."""
    global PROXY_DIR
    p = Path(path).expanduser() if path and path.strip() else None
    if p:
        try:
            p.mkdir(parents=True, exist_ok=True)
            PROXY_DIR = p
            print(f"[Preview] proxy dir: {PROXY_DIR}")
            return
        except Exception as e:
            print(f"[Preview] proxy dir error: {e}")
    PROXY_DIR = _DEFAULT_PROXY_DIR
    print(f"[Preview] proxy dir reset to default: {PROXY_DIR}")


def set_ffmpeg_path(path: str):
    """Override the ffmpeg path (called from app after settings load)."""
    global FFMPEG
    from pathlib import Path as _Path

    p = (path or "").strip()
    if p:
        # Normalize slashes: C:/ffmpeg/... → C:\ffmpeg\...
        normalized = str(_Path(p))
        if _Path(normalized).exists():
            FFMPEG = normalized
            print(f"[Preview] ffmpeg set to: {normalized}")
            return
        else:
            print(f"[Preview] ffmpeg path not found: {normalized}")

    # Blank or file not found — auto-detect
    FFMPEG = ffmpeg_path()
    if FFMPEG:
        print(f"[Preview] ffmpeg auto-detected: {FFMPEG}")
    else:
        print("[Preview] ffmpeg not found — scrub previews disabled")



# ── Proxy generation ──────────────────────────────────────────────────────────

_DEFAULT_PROXY_DIR = Path.home() / ".pixelattic" / "proxies"
PROXY_DIR = _DEFAULT_PROXY_DIR

# Apply proxy dir from bootstrap at import time
def _apply_proxy_bootstrap():
    global PROXY_DIR
    _bp_file = Path.home() / ".pixelattic" / "paths.json"
    try:
        if _bp_file.exists():
            import json as _j
            bp = _j.loads(_bp_file.read_text(encoding="utf-8"))
            _pr = (bp.get("proxies") or "").strip()
            if _pr: PROXY_DIR = Path(_pr)
    except Exception: pass

_apply_proxy_bootstrap()

def get_proxy_path(asset_id: str) -> Path:
    return PROXY_DIR / f"{asset_id}_proxy.mp4"


def generate_proxy(asset) -> Optional[Path]:
    """
    Transcode asset to a lightweight H.264 720p MP4 proxy.
    Works for videos AND image sequences (EXR, DPX, etc).
    Returns proxy path or None.
    """
    if FFMPEG is None:
        return None

    if asset.file_type == "image":
        return None  # single images don't need a proxy — thumbnail is enough

    proxy_path = get_proxy_path(asset.id)
    if proxy_path.exists():
        return proxy_path

    src = Path(asset.path)
    if not src.exists():
        return None

    PROXY_DIR.mkdir(parents=True, exist_ok=True)

    # Scale filter: use configured proxy resolution from settings
    try:
        from settings import Settings as _PS, proxy_scale_filter
        _res = _PS.load().proxy_resolution
        vf = proxy_scale_filter(_res)
    except Exception:
        vf = "scale='min(1280,iw)':trunc(ow/a/2)*2"

    if asset.file_type == "video":
        cmd = [
            FFMPEG, "-y", "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",           # no audio needed for VFX review
            str(proxy_path)
        ]
    elif asset.file_type == "sequence":
        # Detect frame pattern from asset path
        frame_path, fps = _sequence_pattern(src, asset)
        if frame_path is None:
            return None
        cmd = [
            FFMPEG, "-y",
            "-framerate", str(fps or 24),
            "-i", str(frame_path),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(proxy_path)
        ]
    else:
        return None

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=300   # 5 min max
        )
        if result.returncode == 0 and proxy_path.exists():
            return proxy_path
        else:
            err = result.stderr.decode(errors="replace")[-400:]
            print(f"[Proxy] ffmpeg error for {asset.name}:\n{err}")
            return None
    except subprocess.TimeoutExpired:
        print(f"[Proxy] timeout for {asset.name}")
        return None
    except Exception as e:
        print(f"[Proxy] {asset.name}: {e}")
        return None


def _sequence_pattern(src: Path, asset) -> tuple:
    """Return (pattern_path, fps) for an image sequence."""
    fps = getattr(asset, "fps", 24) or 24
    parent = src.parent
    stem   = src.stem
    suffix = src.suffix

    # Strip trailing digits to find base name
    import re
    m = re.match(r"^(.+?)([\d]+)$", stem)
    if not m:
        return None, fps

    base, digits = m.group(1), m.group(2)
    n_digits = len(digits)
    pattern = parent / f"{base}%0{n_digits}d{suffix}"
    return pattern, fps


def invalidate_proxy(asset_id: str):
    """Delete cached proxy so it gets regenerated next time."""
    import time as _time
    p = get_proxy_path(asset_id)
    if not p.exists():
        return
    # File may be locked by VLC — retry a few times after brief pause
    for attempt in range(4):
        try:
            p.unlink()
            return
        except PermissionError:
            if attempt < 3:
                _time.sleep(0.3)   # give VLC time to release the file
            else:
                # Rename instead — file will be orphaned but won't block
                try:
                    p.rename(p.with_suffix('.mp4.del'))
                except Exception:
                    pass   # last resort: leave it, not worth crashing over
        except Exception:
            return


# ── Strip generation ──────────────────────────────────────────────────────────

def get_strip_path(asset_id: str) -> Path:
    return THUMBS_DIR / f"{asset_id}_strip.png"


def generate_strip(asset) -> Optional[Path]:
    """
    Generate a scrub strip for a video or image sequence asset.
    Returns the path to the strip PNG, or None if not possible.
    """
    if FFMPEG is None:
        return None

    if asset.file_type == "image":
        return None  # single images don't need a scrub strip

    strip_path = get_strip_path(asset.id)
    if strip_path.exists():
        return strip_path

    src = Path(asset.path)
    if not src.exists():
        return None

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    if asset.file_type == "video":
        return _strip_from_video(src, strip_path, asset)
    elif asset.file_type == "sequence":
        return _strip_from_sequence(src, strip_path, asset)
    return None



def _stitch_strip_ffmpeg(frame_paths: list, out: Path):
    """Fallback: stitch frames with ffmpeg hstack filter (no PIL required)."""
    try:
        if not FFMPEG or not frame_paths:
            return
        n = len(frame_paths)
        inputs = []
        for fp in frame_paths:
            inputs += ["-i", str(fp)]
        filter_str = f"hstack=inputs={n}"
        cmd = [FFMPEG, "-y"] + inputs + ["-filter_complex", filter_str, str(out)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=20)
    except Exception as e:
        print(f"[Preview] ffmpeg stitch error: {e}")


def _strip_from_video(src: Path, out: Path, asset) -> Optional[Path]:
    """Extract N evenly-spaced frames from a video and stitch into a strip."""
    try:
        duration = asset.duration_s or _probe_duration(src)
        if not duration or duration < 0.1:
            return _strip_from_video_blind(src, out, asset)

        # Skip first and last 5% to avoid black intros/outros
        margin   = duration * 0.05
        start    = margin
        end      = duration - margin
        span     = max(end - start, 0.1)
        interval = span / N_FRAMES
        frame_paths = []

        for i in range(N_FRAMES):
            t     = start + i * interval
            fpath = THUMBS_DIR / f"_tmp_{asset.id}_{i}.png"
            # Put -ss AFTER -i for accurate frame decode (no black keyframe issue)
            # Trade-off: slightly slower, but correct frame every time
            cmd = [
                FFMPEG, "-i", str(src),
                "-ss", f"{t:.3f}",
                "-frames:v", "1",
                "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
                       f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:black",
                "-y", str(fpath)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=20)
            if result.returncode == 0 and fpath.exists() and fpath.stat().st_size > 500:
                frame_paths.append(fpath)

        if not frame_paths:
            return None

        try:
            _stitch_strip(frame_paths, out)
        finally:
            for fp in frame_paths:
                try: fp.unlink()
                except: pass
        return out if out.exists() else None

    except Exception as e:
        print(f"[Preview] Strip error for {src.name}: {e}")
        return None


def _strip_from_video_blind(src: Path, out: Path, asset) -> Optional[Path]:
    """Extract frames at fixed offsets without knowing video duration."""
    try:
        frame_paths = []
        # Start at 1s to skip black intros, use -ss after -i for accurate decode
        offsets = [1, 3, 6, 12, 24, 45, 70, 100]
        for i, t in enumerate(offsets[:N_FRAMES]):
            fpath = THUMBS_DIR / f"_tmp_{asset.id}_b{i}.png"
            cmd = [
                FFMPEG, "-i", str(src),
                "-ss", str(t),
                "-frames:v", "1",
                "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
                       f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:black",
                "-y", str(fpath)
            ]
            r = subprocess.run(cmd, capture_output=True, timeout=20)
            if r.returncode == 0 and fpath.exists() and fpath.stat().st_size > 500:
                frame_paths.append(fpath)
        if not frame_paths:
            return None
        try:
            _stitch_strip(frame_paths, out)
        finally:
            for fp in frame_paths:
                try: fp.unlink()
                except: pass
        return out if out.exists() else None
    except Exception as e:
        print(f"[Preview] Blind strip error for {src.name}: {e}")
        return None


def _strip_from_sequence(src: Path, out: Path, asset) -> Optional[Path]:
    """Pick N evenly-spaced frames from the sequence's own file list."""
    try:
        from config import SequenceGroup
        # Use the asset's known file list if available (set by from_sequence)
        all_files = getattr(asset, 'all_files', None)

        if all_files and len(all_files) >= 2:
            # Use the asset's own frame list — never scan the whole folder
            frames = sorted(all_files)
        else:
            # Legacy fallback: build frame list from sequence pattern in path
            frames = _discover_sequence_frames(src)
            if len(frames) < 2:
                return None

        step   = max(1, len(frames) // N_FRAMES)
        chosen = frames[::step][:N_FRAMES]
        frame_paths = []

        for i, fp in enumerate(chosen):
            tmp = THUMBS_DIR / f"_tmp_{asset.id}_seq_{i}.png"
            cmd = _tonemap_cmd(str(fp), str(tmp))
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            if result.returncode == 0 and tmp.exists():
                frame_paths.append(tmp)
            else:
                # Fallback without tonemap
                cmd2 = [FFMPEG, "-y", "-i", str(fp),
                        "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
                               f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:color=0a0a12",
                        str(tmp)]
                r2 = subprocess.run(cmd2, capture_output=True, timeout=15)
                if r2.returncode == 0 and tmp.exists():
                    frame_paths.append(tmp)

        if not frame_paths:
            return None

        try:
            _stitch_strip(frame_paths, out)
        finally:
            for fp in frame_paths:
                try: fp.unlink()
                except: pass
        return out if out.exists() else None

    except Exception as e:
        print(f"[Preview] Seq strip error: {e}")
        return None


def _discover_sequence_frames(src: Path) -> list:
    """Find sibling frames that belong to the same sequence as src."""
    import re
    stem = src.stem
    m = re.match(r'^(.*?)(\d+)$', stem)
    if not m:
        return [src]
    base, digits = m.group(1), m.group(2)
    n_dig = len(digits)
    pad_re = re.compile(rf'^{re.escape(base)}(\d{{{n_dig}}})$')
    frames = sorted(
        p for p in src.parent.iterdir()
        if p.suffix.lower() == src.suffix.lower()
        and pad_re.match(p.stem)
    )
    return frames if len(frames) >= 2 else [src]


def _tonemap_cmd(inp: str, out: str) -> list:
    """Build an ffmpeg command that tonemaps HDR to SDR for thumbnails."""
    vf = (
        f"zscale=t=linear:npl=100,format=gbrpf32le,"
        f"zscale=p=bt709,tonemap=hable,zscale=t=bt709:m=bt709:r=tv,"
        f"format=yuv420p,"
        f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
        f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:color=0a0a12"
    )
    return [FFMPEG, "-y", "-i", inp, "-vf", vf, "-vframes", "1", out]


def _stitch_strip(frame_paths: list, out: Path):
    """Stitch frames side-by-side into one wide PNG.
    Uses PIL (thread-safe). QPixmap/QPainter cannot be used in bg threads.
    """
    try:
        from PIL import Image as _PILImage
        total_w = THUMB_W * len(frame_paths)
        strip   = _PILImage.new("RGB", (total_w, THUMB_H), (0, 0, 0))
        for i, fp in enumerate(frame_paths):
            try:
                frame = _PILImage.open(str(fp)).convert("RGB")
                frame = frame.resize((THUMB_W, THUMB_H), _PILImage.LANCZOS)
                strip.paste(frame, (i * THUMB_W, 0))
            except Exception:
                pass  # blank tile for missing frame
        strip.save(str(out))
    except ImportError:
        # PIL not available — fall back to ffmpeg hstack filter
        _stitch_strip_ffmpeg(frame_paths, out)


def _probe_duration(src: Path) -> Optional[float]:
    """Use ffprobe to get video duration in seconds."""
    # Locate ffprobe: try PATH first, then derive from ffmpeg path safely
    ffprobe = shutil.which("ffprobe")
    if not ffprobe and FFMPEG:
        # Replace only the filename, not directory components
        ff_path = Path(FFMPEG)
        probe_name = ff_path.name.lower().replace("ffmpeg", "ffprobe")
        candidate = ff_path.parent / probe_name
        if candidate.exists():
            ffprobe = str(candidate)
    if not ffprobe:
        # Last resort: try same dir with explicit name
        if FFMPEG:
            for name in ("ffprobe.exe", "ffprobe"):
                c = Path(FFMPEG).parent / name
                if c.exists():
                    ffprobe = str(c)
                    break
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
            capture_output=True, text=True, timeout=8
        )
        val = result.stdout.strip()
        return float(val) if val else None
    except Exception:
        return None


def invalidate_strip(asset_id: str):
    """Delete cached strip so it gets regenerated next time."""
    p = get_strip_path(asset_id)
    if p.exists():
        try: p.unlink()
        except: pass


# ── HoverScrubLabel ───────────────────────────────────────────────────────────

class HoverScrubLabel(QLabel):
    """
    Displays scrub strip — hover left/right to preview frames.
    Uses paintEvent so sizing is always correct regardless of when widget shows.
    """

    def __init__(self, strip_path, n_frames: int = N_FRAMES, parent=None):
        super().__init__(parent)
        path = Path(strip_path) if strip_path else None
        self._strip_pix = (QPixmap(str(path))
                           if path and path.exists() else QPixmap())
        self._n_frames  = n_frames
        self._hover_idx = -1          # -1 = show full strip
        self._frame_pix = QPixmap()   # current frame being displayed
        self.setFixedHeight(int(THUMB_H * 1.8))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: rgb(9,9,16); border-radius:3px;")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _get_frame(self, idx: int) -> QPixmap:
        """Extract frame idx from strip and scale to widget size."""
        if self._strip_pix.isNull():
            return QPixmap()
        fw = self._strip_pix.width() // self._n_frames
        fh = self._strip_pix.height()
        frame = self._strip_pix.copy(QRect(idx * fw, 0, fw, fh))
        return frame.scaled(self.width(), self.height(),
                            Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def paintEvent(self, event):
        from PySide2.QtGui import QPainter as _P, QColor as _C
        p = _P(self)
        p.setRenderHint(_P.Antialiasing)
        p.fillRect(self.rect(), _C(9, 9, 16))

        if self._strip_pix.isNull():
            p.setPen(_C(50, 60, 80))
            p.drawText(self.rect(), Qt.AlignCenter, "No preview")
            p.end()
            return

        if self._hover_idx >= 0:
            # Show single frame
            pix = self._get_frame(self._hover_idx)
        else:
            # Show contact-sheet strip scaled to widget width
            pix = self._strip_pix.scaled(
                self.width(), self.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if not pix.isNull():
            x = (self.width()  - pix.width())  // 2
            y = (self.height() - pix.height()) // 2
            p.drawPixmap(x, y, pix)

        # Scrub progress bar at bottom
        if self._hover_idx >= 0:
            frac = self._hover_idx / max(self._n_frames - 1, 1)
            bar_w = int(self.width() * frac)
            p.fillRect(0, self.height() - 3, bar_w, 3, _C(249, 115, 22, 200))
            p.fillRect(bar_w, self.height() - 3,
                       self.width() - bar_w, 3, _C(30, 30, 50))

        p.end()

    # ── Events ────────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        if self._strip_pix.isNull():
            return
        frac = event.x() / max(self.width(), 1)
        idx  = min(int(frac * self._n_frames), self._n_frames - 1)
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()

    def leaveEvent(self, event):
        self._hover_idx = -1
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()
