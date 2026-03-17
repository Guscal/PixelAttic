"""
database.py — Asset data model + JSON persistence.
"""
import json, uuid, shutil, hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple

from config import LIBRARY_FILE, APP_DIR

BACKUP_FILE = APP_DIR / "library.backup.json"

# ── Probe timeout (seconds) — used by ffprobe calls during import ─────────
# Increase if you work with large files on slow network drives.
PROBE_TIMEOUT = 15

# Apply backup custom path from bootstrap
def _apply_backup_bootstrap():
    global BACKUP_FILE
    _bp_file = Path.home() / ".pixelattic" / "paths.json"
    try:
        if _bp_file.exists():
            import json as _j
            bp = _j.loads(_bp_file.read_text(encoding="utf-8"))
            _bk = (bp.get("backup") or "").strip()
            if _bk: BACKUP_FILE = Path(_bk)
    except Exception: pass

_apply_backup_bootstrap()

def _get_ffprobe() -> str:
    """Get ffprobe path: derive from configured ffmpeg, then fallback to PATH."""
    import shutil
    from pathlib import Path as _P

    # Try to get the user-configured ffmpeg from preview module
    try:
        import preview as _prev
        ff = _prev.FFMPEG
        if ff:
            ff_path = _P(ff)
            for name in ("ffprobe.exe", "ffprobe"):
                candidate = ff_path.parent / name
                if candidate.exists():
                    return str(candidate)
    except Exception:
        pass

    # Fallback: PATH
    found = shutil.which("ffprobe")
    if found:
        return found

    # Common locations
    for c in [
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
        r"C:\Tools\ffmpeg\bin\ffprobe.exe",
    ]:
        if _P(c).exists():
            return c
    return None

@dataclass

class Asset:
    id:           str
    name:         str
    path:         str
    category:     str
    tags:         list
    notes:        str
    date_added:   str
    file_type:    str
    format:       str
    thumb_path:   Optional[str]
    width:        Optional[int]   = None
    height:       Optional[int]   = None
    fps:          Optional[float] = None
    frame_count:  Optional[int]   = None
    duration_s:   Optional[float] = None
    file_size_mb: Optional[float] = None
    collections:  list            = field(default_factory=list)
    content_hash:   Optional[str]   = None  # xxhash/sha256 of first 4MB for dup detection

    # Extended technical metadata (extracted via ffprobe on import)
    codec:          Optional[str]   = None  # e.g. 'h264', 'prores', 'exr'
    bit_depth:      Optional[int]   = None  # e.g. 8, 10, 12, 16, 32
    color_space:    Optional[str]   = None  # e.g. 'sRGB', 'ACEScg', 'Rec.709'
    audio_codec:    Optional[str]   = None  # e.g. 'aac', 'pcm_s24le'
    audio_channels: Optional[int]   = None  # 1=mono, 2=stereo, 6=5.1

    # User curation
    starred:        bool            = False
    rating:         int             = 0     # 0=unrated, 1-5 stars
    linked_ids:     list            = field(default_factory=list)  # related asset IDs (versions)

    @property
    def display_res(self) -> str:
        """Short label used for pills and tags — e.g. '4K', 'HD'."""
        if self.width and self.height:
            if self.width >= 7680: return "8K"
            if self.width >= 6144: return "6K"
            if self.width >= 3840: return "4K"
            if self.width >= 2048: return "2K"
            if self.width >= 1920: return "HD"
            return f"{self.width}×{self.height}"
        return "—"

    @property
    def detail_res(self) -> str:
        """Full resolution for detail view — e.g. '4K (3840×2160)'."""
        if self.width and self.height:
            dims = f"{self.width}×{self.height}"
            if self.width >= 7680: return f"8K ({dims})"
            if self.width >= 6144: return f"6K ({dims})"
            if self.width >= 3840: return f"4K ({dims})"
            if self.width >= 2048: return f"2K ({dims})"
            if self.width >= 1920: return f"HD ({dims})"
            return dims
        return "—"

    @property
    def duration_str(self) -> str:
        if self.duration_s:  return f"{self.duration_s:.1f}s"
        if self.frame_count: return f"{self.frame_count}f"
        return "—"

    def matches(self, search: str, category: str, active_tags: list) -> bool:
        s = search.strip().lower()
        if s and s not in self.name.lower() and s not in (self.notes or "").lower():
            return False
        if category != "All" and self.category != category:
            return False
        if active_tags and not all(t in self.tags for t in active_tags):
            return False
        return True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Asset":
        # Strip unknown fields for forward/backward compat (e.g. old 'rating')
        known = {f.name for f in cls.__dataclass_fields__.values()}
        clean = {k: v for k, v in d.items() if k in known}
        # Ensure collections is a list
        if "collections" not in clean:
            clean["collections"] = []
        return cls(**clean)

    @classmethod
    def from_path(cls, path: Path, category: str = "Misc") -> "Asset":
        from config import EXT_TO_TYPE, ext_label

        # ── Validate file ─────────────────────────────────────────────────
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {path}")
        try:
            # Verify read access (open + read 1 byte)
            with open(path, "rb") as _f:
                _f.read(1)
        except PermissionError:
            raise PermissionError(f"Cannot read file (permission denied): {path}")
        except OSError as e:
            raise OSError(f"Cannot access file: {path} — {e}")

        ext       = path.suffix.lower()
        file_type = EXT_TO_TYPE.get(ext, "image")
        fmt       = ext_label(ext)

        try:    size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        except: size_mb = None

        # Detect zero-byte files early
        if size_mb is not None and size_mb == 0:
            raise ValueError(f"Empty file (0 bytes): {path}")

        width = height = None
        try:
            from PIL import Image as PILImage
            if file_type in ("image", "sequence") and ext not in (".psd", ".psb"):
                with PILImage.open(path) as im:
                    width, height = im.size
        except: pass

        fps = frame_count = duration_s = None
        codec = bit_depth = color_space = audio_codec = audio_channels = None

        # ── HDR/EXR/DPX images: PIL can't read these, use ffprobe ────────────
        _HDR_EXTS = {".exr", ".dpx", ".hdr", ".pic", ".cin", ".sxr"}
        if file_type == "image" and ext in _HDR_EXTS:
            try:
                import shutil as _sh, subprocess as _sp, json as _js
                ffprobe = _get_ffprobe()
                if ffprobe:
                    _r = _sp.run(
                        [ffprobe, "-v", "quiet", "-print_format", "json",
                         "-show_streams", str(path)],
                        capture_output=True, timeout=PROBE_TIMEOUT)
                    if _r.returncode == 0:
                        _data = _js.loads(_r.stdout)
                        _vs = next((s for s in _data.get("streams", [])
                                    if s.get("codec_type") == "video"), None)
                        if _vs:
                            width  = _vs.get("width")  or width
                            height = _vs.get("height") or height
                            codec  = _vs.get("codec_name")  # e.g. "exr", "dpx"

                            # Bit depth from bits_per_raw_sample or pix_fmt
                            _bps = _vs.get("bits_per_raw_sample")
                            if _bps and str(_bps).isdigit() and int(_bps) > 0:
                                bit_depth = int(_bps)
                            else:
                                _pf = _vs.get("pix_fmt", "")
                                if   "f32" in _pf or "32" in _pf: bit_depth = 32
                                elif "f16" in _pf or "16" in _pf: bit_depth = 16
                                elif "12"  in _pf:                 bit_depth = 12
                                elif "10"  in _pf:                 bit_depth = 10
                                elif _pf:                          bit_depth = 8

                            # Color space / transfer
                            _ct = _vs.get("color_transfer", "")
                            _cp = _vs.get("color_primaries", "")
                            _cs = _vs.get("color_space", "")
                            if _ct == "linear" or "f32" in _vs.get("pix_fmt","") or "f16" in _vs.get("pix_fmt",""):
                                color_space = "Linear"
                            elif _cp or _cs:
                                _cs_map = {
                                    "bt709": "Rec.709", "bt2020": "Rec.2020",
                                    "bt470bg": "Rec.601", "smpte170m": "Rec.601",
                                    "smpte431": "DCI-P3", "smpte432": "DCI-P3",
                                }
                                color_space = _cs_map.get(_cp or _cs,
                                    (_cp or _cs).upper() if (_cp or _cs) else None)
            except Exception:
                pass

        # ── Video: probe with ffprobe/ffmpeg ─────────────────────────────
        if file_type in ("video", "sequence"):
            try:
                import shutil as _sh, subprocess as _sp, json as _js, re as _re
                ffprobe = _get_ffprobe()
                if ffprobe:
                    probe_cmd = [
                        ffprobe, "-v", "quiet",
                        "-print_format", "json",
                        "-show_streams", "-show_format",
                        str(path)
                    ]
                    r = _sp.run(probe_cmd, capture_output=True, timeout=PROBE_TIMEOUT)
                    if r.returncode == 0:
                        data = _js.loads(r.stdout)
                        vstream = next((s for s in data.get("streams", [])
                                        if s.get("codec_type") == "video"), None)
                        if vstream:
                            width  = vstream.get("width")  or width
                            height = vstream.get("height") or height
                            # FPS from r_frame_rate or avg_frame_rate
                            for fps_key in ("r_frame_rate", "avg_frame_rate"):
                                fstr = vstream.get(fps_key, "")
                                if "/" in fstr:
                                    n, d = fstr.split("/")
                                    if int(d) > 0:
                                        fps = round(int(n) / int(d), 3)
                                        break
                            fc = vstream.get("nb_frames")
                            if fc and str(fc).isdigit():
                                frame_count = int(fc)
                            dur = (vstream.get("duration") or
                                   data.get("format", {}).get("duration"))
                            if dur:
                                duration_s = float(dur)
                                if not frame_count and fps:
                                    frame_count = int(duration_s * fps)

                            # ── Extended metadata ──────────────────────
                            codec = vstream.get("codec_name")

                            # Bit depth: explicit field first, else from pix_fmt
                            _bps = vstream.get("bits_per_raw_sample")
                            if _bps and str(_bps).isdigit() and int(_bps) > 0:
                                bit_depth = int(_bps)
                            else:
                                _pf = vstream.get("pix_fmt", "")
                                if   "12" in _pf: bit_depth = 12
                                elif "10" in _pf: bit_depth = 10
                                elif "16" in _pf: bit_depth = 16
                                elif "32" in _pf: bit_depth = 32
                                elif _pf:          bit_depth = 8

                            # Color space / primaries
                            _cs = (vstream.get("color_space") or
                                   vstream.get("color_primaries") or "")
                            _cs_map = {
                                "bt709": "Rec.709",   "bt2020": "Rec.2020",
                                "bt470bg": "Rec.601",  "smpte170m": "Rec.601",
                                "smpte431": "DCI-P3",  "smpte432": "DCI-P3",
                            }
                            color_space = _cs_map.get(_cs, _cs.upper() if _cs else None)

                            # Audio stream
                            astream = next((s for s in data.get("streams", [])
                                            if s.get("codec_type") == "audio"), None)
                            if astream:
                                audio_codec    = astream.get("codec_name")
                                audio_channels = astream.get("channels")
            except Exception as _e:
                pass  # ffprobe unavailable — leave None

        auto_tags = [fmt]
        if width:
            if   width >= 7680: auto_tags.append("8K")
            elif width >= 3840: auto_tags.append("4K")
            elif width >= 2048: auto_tags.append("2K")
            elif width >= 1920: auto_tags.append("HD")

        return cls(
            id           = str(uuid.uuid4()),
            name         = path.stem,
            path         = str(path),
            category     = category,
            tags         = auto_tags,
            notes        = "",
            date_added   = datetime.now().strftime("%Y-%m-%d"),
            file_type    = file_type,
            format       = fmt,
            thumb_path   = None,
            width        = width,
            height       = height,
            fps          = fps,
            frame_count     = frame_count,
            duration_s      = duration_s,
            file_size_mb    = size_mb,
            codec           = codec,
            bit_depth       = bit_depth,
            color_space     = color_space,
            audio_codec     = audio_codec,
            audio_channels  = audio_channels,
        )

    @classmethod
    def from_sequence(cls, seq, category: str = "Misc") -> "Asset":
        """Create an Asset from a SequenceGroup (multi-frame image sequence).

        seq.base_path is used as the canonical path.
        seq.all_files[0] is used for metadata / thumbnail purposes.
        """
        from config import EXT_TO_TYPE, ext_label

        # ── Validate first frame ──────────────────────────────────────────
        first = seq.all_files[0]
        if not first.exists():
            raise FileNotFoundError(f"First frame not found: {first}")
        try:
            with open(first, "rb") as _f:
                _f.read(1)
        except PermissionError:
            raise PermissionError(f"Cannot read sequence (permission denied): {first}")

        # Count how many frames are actually accessible
        _accessible = [p for p in seq.all_files if p.exists()]
        if len(_accessible) < len(seq.all_files):
            _missing = len(seq.all_files) - len(_accessible)
            # warn but don't block — partial sequences are common on network drives
            print(f"[Import] Sequence '{seq.name}': {_missing} of "
                  f"{len(seq.all_files)} frame(s) are missing/inaccessible")

        ext       = seq.ext
        file_type = "sequence"
        fmt       = ext_label(ext)

        try:    size_mb = round(sum(p.stat().st_size for p in _accessible) / (1024*1024), 2)
        except: size_mb = None

        width = height = None
        try:
            from PIL import Image as PILImage
            if ext not in (".psd", ".psb"):
                with PILImage.open(first) as im:
                    width, height = im.size
        except: pass

        frame_count = len(seq.all_files)
        fps         = None
        duration_s  = None
        codec       = None
        bit_depth   = None
        color_space = None
        audio_codec = None
        audio_channels = None

        # Try to read bit depth / color space from first EXR/DPX via ffprobe
        try:
            import shutil as _sh, subprocess as _sp, json as _js, os as _os
            ffprobe = _get_ffprobe()
            if ffprobe:
                r = _sp.run([ffprobe, "-v", "quiet", "-print_format", "json",
                             "-show_streams", str(first)],
                            capture_output=True, timeout=PROBE_TIMEOUT)
                if r.returncode == 0:
                    data = _js.loads(r.stdout)
                    vs = next((s for s in data.get("streams", [])
                               if s.get("codec_type") == "video"), None)
                    if vs:
                        codec = vs.get("codec_name")
                        width  = vs.get("width") or width
                        height = vs.get("height") or height
                        _bps = vs.get("bits_per_raw_sample")
                        if _bps and str(_bps).isdigit() and int(_bps) > 0:
                            bit_depth = int(_bps)
                        else:
                            _pf = vs.get("pix_fmt", "")
                            if   "32" in _pf: bit_depth = 32
                            elif "16" in _pf: bit_depth = 16
                            elif "12" in _pf: bit_depth = 12
                            elif "10" in _pf: bit_depth = 10
                            elif _pf:         bit_depth = 8
                        _cs = (vs.get("color_space") or vs.get("color_primaries") or "")
                        _cs_map = {"bt709":"Rec.709","bt2020":"Rec.2020",
                                   "bt470bg":"Rec.601","smpte170m":"Rec.601",
                                   "smpte431":"DCI-P3","smpte432":"DCI-P3"}
                        color_space = _cs_map.get(_cs, _cs.upper() if _cs else None)
        except Exception:
            pass

        auto_tags = [fmt]
        if width:
            if   width >= 7680: auto_tags.append("8K")
            elif width >= 3840: auto_tags.append("4K")
            elif width >= 2048: auto_tags.append("2K")
            elif width >= 1920: auto_tags.append("HD")
        auto_tags.append(f"{frame_count}f")

        return cls(
            id           = str(uuid.uuid4()),
            name         = seq.name,
            path         = str(seq.base_path),
            category     = category,
            tags         = auto_tags,
            notes        = "",
            date_added   = datetime.now().strftime("%Y-%m-%d"),
            file_type    = "sequence",
            format       = fmt,
            thumb_path   = None,
            width        = width,
            height       = height,
            fps          = fps,
            frame_count  = frame_count,
            duration_s   = duration_s,
            file_size_mb = size_mb,
            codec        = codec,
            bit_depth    = bit_depth,
            color_space  = color_space,
            audio_codec  = None,
            audio_channels = None,
        )

class Library:
    """JSON-backed asset library."""

    def __init__(self):
        self._assets:      dict = {}
        self._collections: dict = {}
        self._batch_mode:  bool = False
        self._save_dirty:  bool = False
        self._load()

    # ── Batch mode — defer save() until end_batch() ──────────────────────────

    def begin_batch(self):
        """Defer all save() calls until end_batch(). Use for bulk imports."""
        self._batch_mode = True

    def end_batch(self):
        """Flush deferred save and resume normal per-operation saving."""
        self._batch_mode = False
        self._write_to_disk()

    # ── Queries ───────────────────────────────────────────────────────────────

    def all_assets(self) -> list:
        return list(self._assets.values())

    def get(self, asset_id: str) -> Optional[Asset]:
        return self._assets.get(asset_id)

    def filtered(self, search: str = "", category: str = "All",
                 active_tags: list = None, sort_by: str = "name",
                 sort_reverse: bool = False) -> list:
        pool = [a for a in self._assets.values()
                if a.matches(search, category, active_tags or [])]
        key_fn = {
            "name": lambda a: a.name.lower(),
            "date": lambda a: a.date_added or "",
            "size": lambda a: a.file_size_mb or 0,
            "type": lambda a: (a.file_type or "", a.format or "", a.name.lower()),
            "rating": lambda a: (a.rating or 0, a.name.lower()),
        }.get(sort_by, lambda a: a.name.lower())
        return sorted(pool, key=key_fn, reverse=sort_reverse)

    def category_counts(self) -> dict:
        counts = {"All": len(self._assets)}
        for a in self._assets.values():
            counts[a.category] = counts.get(a.category, 0) + 1
        return counts

    def tag_counts(self, category: str = "All") -> dict:
        counts = {}
        for a in self._assets.values():
            if category != "All" and a.category != category:
                continue
            for t in a.tags:
                counts[t] = counts.get(t, 0) + 1
        return counts

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def add(self, asset: Asset):
        self._assets[asset.id] = asset
        self.save()

    def update(self, asset: Asset):
        self._assets[asset.id] = asset
        self.save()

    def remove(self, asset_id: str):
        self._assets.pop(asset_id, None)
        for ids in self._collections.values():
            if asset_id in ids:
                ids.remove(asset_id)
        self.save()

    # ── Demo ──────────────────────────────────────────────────────────────────

    def get_collections(self) -> dict:
        return dict(self._collections)

    def collection_assets(self, name: str) -> list:
        ids = self._collections.get(name, [])
        return [self._assets[i] for i in ids if i in self._assets]

    def collection_count(self, name: str) -> int:
        return len([i for i in self._collections.get(name, [])
                    if i in self._assets])

    def collections_for_asset(self, asset_id: str) -> list:
        return [n for n, ids in self._collections.items() if asset_id in ids]

    def create_collection(self, name: str) -> bool:
        if name in self._collections: return False
        self._collections[name] = []
        self.save(); return True

    def delete_collection(self, name: str):
        self._collections.pop(name, None); self.save()

    def rename_collection(self, old: str, new: str) -> bool:
        if old not in self._collections or new in self._collections:
            return False
        self._collections[new] = self._collections.pop(old)
        self.save(); return True

    def add_to_collection(self, name: str, asset_id: str):
        if name not in self._collections: self._collections[name] = []
        if asset_id not in self._collections[name]:
            self._collections[name].append(asset_id)
            self.save()

    def remove_from_collection(self, name: str, asset_id: str):
        if name in self._collections and asset_id in self._collections[name]:
            self._collections[name].remove(asset_id)
            self.save()

    # ── Asset versioning / linking ───────────────────────────────────────────

    def link_assets(self, id_a: str, id_b: str):
        """Link two assets as related versions. Bidirectional."""
        a, b = self._assets.get(id_a), self._assets.get(id_b)
        if not a or not b or id_a == id_b:
            return
        if id_b not in a.linked_ids:
            a.linked_ids.append(id_b)
        if id_a not in b.linked_ids:
            b.linked_ids.append(id_a)
        self.save()

    def unlink_assets(self, id_a: str, id_b: str):
        """Remove link between two assets."""
        a, b = self._assets.get(id_a), self._assets.get(id_b)
        if a and id_b in a.linked_ids:
            a.linked_ids.remove(id_b)
        if b and id_a in b.linked_ids:
            b.linked_ids.remove(id_a)
        self.save()

    def get_linked(self, asset_id: str) -> list:
        """Return list of Asset objects linked to the given asset."""
        a = self._assets.get(asset_id)
        if not a:
            return []
        return [self._assets[lid] for lid in a.linked_ids if lid in self._assets]

    # ── Persistence ───────────────────────────────────────────────────────────

    @staticmethod
    def verify_file(path: Path) -> Tuple[bool, str]:
        if not path.exists(): return False, "File not found"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "assets" not in data: return False, "Missing 'assets' key"
            return True, f"OK — {len(data['assets'])} assets"
        except Exception as e:
            return False, str(e)

    def backup(self) -> Tuple[bool, str]:
        try:
            shutil.copy2(LIBRARY_FILE, BACKUP_FILE)
            return True, f"Backup saved to {BACKUP_FILE}"
        except Exception as e:
            return False, str(e)

    def restore_from_backup(self) -> Tuple[bool, str]:
        ok, msg = self.verify_file(BACKUP_FILE)
        if not ok: return False, f"Backup invalid: {msg}"
        try:
            shutil.copy2(BACKUP_FILE, LIBRARY_FILE)
            return True, "Library restored from backup"
        except Exception as e:
            return False, str(e)

    def export_collection(self, name: str, out_path: Path):
        """Export a collection + all its assets to a JSON file for sharing."""
        ids    = self._collections.get(name, [])
        assets = [self._assets[i].to_dict() for i in ids if i in self._assets]
        data   = {
            "pixelattic_collection": True,
            "version":     "1.0",
            "name":        name,
            "exported_at": datetime.now().isoformat(),
            "asset_count": len(assets),
            "assets":      assets,
            "collection":  {name: ids},
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def import_collection(self, file_path: Path) -> tuple:
        """
        Import a collection from a .pixcol JSON file.
        Returns (imported_count, skipped_count, coll_name, error_msg).
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("pixelattic_collection"):
                return 0, 0, "", "Not a valid Pixel Attic collection file."
            coll_name = data.get("name", file_path.stem)
            # Make unique name if collision
            base = coll_name
            n = 1
            while coll_name in self._collections:
                coll_name = f"{base} ({n})"
                n += 1
            imported = skipped = 0
            new_ids = []
            for d in data.get("assets", []):
                try:
                    a = Asset.from_dict(d)
                    if a.id in self._assets:
                        skipped += 1
                    else:
                        self._assets[a.id] = a
                        imported += 1
                    new_ids.append(a.id)
                except Exception:
                    skipped += 1
            self._collections[coll_name] = new_ids
            self.save()
            return imported, skipped, coll_name, ""
        except Exception as e:
            return 0, 0, "", str(e)

    def _load(self):
        if not LIBRARY_FILE.exists():
            return   # fresh library — nothing to load
        ok, msg = self.verify_file(LIBRARY_FILE)
        if not ok:
            print(f"[Library] Corrupt: {msg}")
            restored, r_msg = self.restore_from_backup()
            print(f"[Library] Restore: {r_msg}")
            if not restored: return
            ok, msg = self.verify_file(LIBRARY_FILE)
            if not ok: return
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for d in data.get("assets", []):
                try:
                    a = Asset.from_dict(d)
                    self._assets[a.id] = a
                except Exception as e:
                    print(f"[Library] Skip asset: {e}")
            self._collections = data.get("collections", {})
            print(f"[Library] Loaded {len(self._assets)} assets")
        except Exception as e:
            print(f"[Library] Load error: {e}")

    # ── Duplicate detection ───────────────────────────────────────────────────

    @staticmethod
    def hash_file(path: str, sample_bytes: int = 4 * 1024 * 1024) -> Optional[str]:
        """Fast content hash: sha256 of first+middle+last sample_bytes/3 each.
        Returns hex string, or None on error."""
        try:
            import hashlib
            p = Path(path)
            if not p.exists():
                return None
            size = p.stat().st_size
            h = hashlib.sha256()
            chunk = max(1, sample_bytes // 3)
            with open(p, "rb") as f:
                # Start
                h.update(f.read(chunk))
                # Middle
                if size > chunk * 2:
                    f.seek(size // 2)
                    h.update(f.read(chunk))
                # End
                if size > chunk:
                    f.seek(max(0, size - chunk))
                    h.update(f.read(chunk))
            return h.hexdigest()[:16]   # 16 hex chars = 64-bit, collision-safe for libraries
        except Exception:
            return None

    def find_duplicates(self) -> list:
        """Return list of duplicate groups: each group is a list of Asset objects
        that share the same content hash (identical file content).
        Only groups of 2+ assets are returned."""
        from collections import defaultdict
        buckets: dict = defaultdict(list)
        for asset in self._assets.values():
            h = getattr(asset, "content_hash", None)
            if h:
                buckets[h].append(asset)
        return [group for group in buckets.values() if len(group) >= 2]

    def compute_missing_hashes(self, progress_cb=None) -> int:
        """Compute and store hashes for assets that don't have one yet.
        Returns count of newly hashed assets."""
        count = 0
        assets_needing_hash = [
            a for a in self._assets.values()
            if not getattr(a, "content_hash", None) and Path(a.path).exists()
        ]
        for i, asset in enumerate(assets_needing_hash):
            if progress_cb:
                progress_cb(i, len(assets_needing_hash))
            h = self.hash_file(asset.path)
            if h:
                asset.content_hash = h
                count += 1
        if count:
            self.save()
        return count

    def save(self):
        """Mark library as dirty. Actual disk write is deferred.
        Call save_now() or flush_if_dirty() for immediate write."""
        if self._batch_mode:
            return
        self._save_dirty = True

    def save_now(self):
        """Immediate write to disk — use on app shutdown."""
        self._write_to_disk()

    def flush_if_dirty(self):
        """Write to disk only if pending changes. Called by app timer."""
        if self._save_dirty:
            self._write_to_disk()

    def _write_to_disk(self):
        """Actual JSON serialization + write + backup."""
        self._save_dirty = False
        LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "assets":      [a.to_dict() for a in self._assets.values()],
                "collections": self._collections,
            }
            with open(LIBRARY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.copy2(LIBRARY_FILE, BACKUP_FILE)
        except Exception as e:
            print(f"[Library] Save error: {e}")

    # ── Demo seed data ────────────────────────────────────────────────────────
