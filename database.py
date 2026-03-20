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
PROBE_TIMEOUT = 30

# Apply backup custom path from bootstrap
def _apply_backup_bootstrap():
    global BACKUP_FILE
    _bp_file = Path.home() / ".pixelattic" / "paths.json"
    try:
        if _bp_file.exists():
            import json as _j
            bp = _j.loads(_bp_file.read_text(encoding="utf-8"))
            _bk = (bp.get("backup") or "").strip()
            if _bk:
                p = Path(_bk)
                if p.suffix == ".json":
                    BACKUP_FILE = p
                elif p.suffix:
                    BACKUP_FILE = p.parent / "library.backup.json"
                else:
                    # Directory — append filename
                    BACKUP_FILE = p / "library.backup.json"
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


def _parse_exr_header(path) -> dict:
    """Parse OpenEXR header for bit depth, color space, renderer, and compression.
    
    Detects metadata from: V-Ray (vfb2_layers_json, vrayInfo/*),
    Arnold (arnold/*), Redshift (redshift/*), RenderMan (prman/*),
    Corona (corona/*), Cycles/Blender (cycles/*), Nuke (nuke/*),
    OIIO (oiio:ColorSpace), and standard EXR chromaticities.
    """
    import struct
    result = {}
    try:
        with open(str(path), "rb") as f:
            magic = f.read(4)
            if magic != b'\x76\x2f\x31\x01':
                return result
            f.read(4)  # version

            # Read all attributes
            attrs = {}       # name → (type_str, raw_bytes)
            str_attrs = {}   # name → decoded string (string-type only)
            while True:
                name = b''
                while True:
                    c = f.read(1)
                    if not c or c == b'\x00': break
                    name += c
                if not name: break
                typ = b''
                while True:
                    c = f.read(1)
                    if not c or c == b'\x00': break
                    typ += c
                size = struct.unpack('<I', f.read(4))[0]
                data = f.read(size)
                n = name.decode('ascii', errors='replace')
                t = typ.decode('ascii', errors='replace')
                attrs[n] = (t, data)
                # Decode string attrs for easy access
                if t == 'string' and data:
                    if len(data) >= 4:
                        slen = struct.unpack('<I', data[:4])[0]
                        # Validate: slen should match remaining data
                        if 0 < slen <= len(data) - 4 and slen < 65536:
                            # Standard EXR: 4-byte length prefix + chars
                            str_attrs[n] = data[4:4+slen].decode('utf-8', errors='replace').rstrip('\x00')
                        else:
                            # No length prefix — raw string (Houdini, some OIIO writers)
                            str_attrs[n] = data.decode('utf-8', errors='replace').rstrip('\x00')
                    else:
                        str_attrs[n] = data.decode('utf-8', errors='replace').rstrip('\x00')

        # ── dataWindow → width, height ────────────────────────────────────
        if 'dataWindow' in attrs:
            _, d = attrs['dataWindow']
            if len(d) >= 16:
                x1, y1, x2, y2 = struct.unpack('<iiii', d[:16])
                result['width']  = x2 - x1 + 1
                result['height'] = y2 - y1 + 1

        # ── channels → bit depth ──────────────────────────────────────────
        if 'channels' in attrs:
            _, d = attrs['channels']
            ch_types = []
            pos = 0
            while pos < len(d) - 1:
                try:
                    end = d.index(0, pos)
                except ValueError:
                    break
                pos = end + 1
                if pos + 16 > len(d): break
                ch_type = struct.unpack('<i', d[pos:pos+4])[0]
                ch_types.append(ch_type)
                pos += 16
            if ch_types:
                type_map = {0: 32, 1: 16, 2: 32}  # UINT=32, HALF=16, FLOAT=32
                depths = [type_map.get(t, 32) for t in ch_types]
                result['bit_depth'] = min(depths)

        # ── Compression ───────────────────────────────────────────────────
        _comp_map = {0:"none", 1:"rle", 2:"zips", 3:"zip", 4:"piz",
                     5:"pxr24", 6:"b44", 7:"b44a", 8:"dwaa", 9:"dwab"}
        if 'compression' in attrs:
            _, d = attrs['compression']
            if d:
                result['compression'] = _comp_map.get(d[0], f"unknown({d[0]})")

        # ── Detect renderer ───────────────────────────────────────────────
        renderer = None
        renderer_version = None

        # V-Ray: vrayInfo/*, vfb2_layers_json, exr/vfb2_layers_json
        _vray_keys = [k for k in str_attrs if k.startswith('vrayInfo') or 'vray' in k.lower()]
        if _vray_keys or any('vfb2' in k for k in str_attrs):
            renderer = "V-Ray"
            v = str_attrs.get('vrayInfo/vrayversion', str_attrs.get('vrayInfo/version', ''))
            if v: renderer_version = v

        # Arnold: arnold/*, ai:*
        elif any(k.startswith('arnold') or k.startswith('ai:') for k in str_attrs):
            renderer = "Arnold"
            v = str_attrs.get('arnold/version', str_attrs.get('ai:version', ''))
            if v: renderer_version = v

        # Redshift: redshift/*
        elif any(k.startswith('redshift') for k in str_attrs):
            renderer = "Redshift"
            v = str_attrs.get('redshift/version', '')
            if v: renderer_version = v

        # Corona: corona/*
        elif any(k.startswith('corona') for k in str_attrs):
            renderer = "Corona"
            v = str_attrs.get('corona/version', '')
            if v: renderer_version = v

        # RenderMan/Pixar: prman/*, PixarRender*
        elif any(k.startswith('prman') or k.startswith('Pixar') for k in str_attrs):
            renderer = "RenderMan"
            v = str_attrs.get('prman/version', '')
            if v: renderer_version = v

        # Cycles/Blender: cycles/*, blender/*
        elif any(k.startswith('cycles') or k.startswith('blender') for k in str_attrs):
            renderer = "Cycles"
            v = str_attrs.get('cycles/version', str_attrs.get('blender/version', ''))
            if v: renderer_version = v

        # Octane: octane/*
        elif any(k.startswith('octane') for k in str_attrs):
            renderer = "Octane"

        # Mantra (Houdini): mantra/*
        elif any(k.startswith('mantra') or k.startswith('karma') for k in str_attrs):
            renderer = "Karma" if any(k.startswith('karma') for k in str_attrs) else "Mantra"
            # Try to get version from any karma/mantra key value
            for k, v in str_attrs.items():
                if k.startswith('karma') or k.startswith('mantra'):
                    if any(c.isdigit() for c in v):
                        renderer_version = v
                        break

        # Guerilla: guerilla/*
        elif any(k.startswith('guerilla') for k in str_attrs):
            renderer = "Guerilla"

        # Nuke: nuke/*
        elif any(k.startswith('nuke') for k in str_attrs):
            renderer = "Nuke"
            v = str_attrs.get('nuke/version', '')
            if v: renderer_version = v

        # OIIO/generic Software attr
        elif 'Software' in str_attrs:
            sw = str_attrs['Software'].strip()
            if 'Arnold' in sw:     renderer = "Arnold"
            elif 'V-Ray' in sw:    renderer = "V-Ray"
            elif 'Blender' in sw:  renderer = "Cycles"
            elif 'Nuke' in sw:     renderer = "Nuke"
            elif 'Karma' in sw:
                renderer = "Karma"
                # Extract variant like "(xpu)" from "Karma (xpu) 20.5.684"
                import re as _re
                _km = _re.match(r'Karma\s*(\([^)]+\))?', sw)
                if _km and _km.group(1):
                    renderer = f"Karma {_km.group(1)}"
            elif 'Mantra' in sw:   renderer = "Mantra"
            elif 'Houdini' in sw:  renderer = "Houdini"
            elif 'Redshift' in sw: renderer = "Redshift"
            elif 'Corona' in sw:   renderer = "Corona"
            elif 'Octane' in sw:   renderer = "Octane"
            elif sw:               renderer = sw[:40]

        # ── Fallback: detect renderer from channel names ──────────────────
        if not renderer and 'channels' in attrs:
            _, d = attrs['channels']
            # Extract all channel names
            ch_names = []
            pos = 0
            while pos < len(d) - 1:
                try:
                    end = d.index(0, pos)
                except ValueError:
                    break
                ch_names.append(d[pos:end].decode('ascii', errors='replace'))
                pos = end + 1
                if pos + 16 > len(d): break
                pos += 16
            _ch_joined = ' '.join(ch_names).lower()

            # V-Ray: VRayLighting, VRayReflection, VRayGlobalIllumination, etc.
            if any('vray' in c.lower() for c in ch_names):
                renderer = "V-Ray"
            # Arnold: RGBA.beauty, crypto_asset, arnold_* channels
            elif any(c.startswith('arnold') or 'crypto_' in c.lower() for c in ch_names):
                renderer = "Arnold"
            # Redshift: rsID, rsNoise, rsObjectID, etc.
            elif any(c.lower().startswith('rs') and len(c) > 2 and c[2:3].isupper() for c in ch_names):
                renderer = "Redshift"
            # Corona: CGeometry, CShading, Corona* channels
            elif any(c.startswith('Corona') or (c.startswith('C') and len(c) > 1 and c[1:2].isupper() and 'corona' in _ch_joined) for c in ch_names):
                renderer = "Corona"
            # RenderMan: Ci, Oi, PxrSurface* channels
            elif any(c in ('Ci', 'Oi') or c.startswith('Pxr') for c in ch_names):
                renderer = "RenderMan"
            # Cycles: Combined, DiffDir, DiffInd, GlossDir, etc.
            elif any(c in ('Combined', 'DiffDir', 'DiffInd', 'GlossDir', 'GlossInd', 'TransDir') for c in ch_names):
                renderer = "Cycles"
            # Mantra/Karma: direct_diffuse, indirect_diffuse, direct_specular, etc.
            elif any(c in ('direct_diffuse', 'indirect_diffuse', 'direct_specular') for c in ch_names):
                renderer = "Mantra"
            # Octane: OctBeauty, OctDiffDir, etc.
            elif any(c.lower().startswith('oct') for c in ch_names):
                renderer = "Octane"

        # ── Fallback: detect renderer from ANY attribute key names ─────────
        if not renderer:
            _all_keys = ' '.join(list(str_attrs.keys()) + list(attrs.keys())).lower()
            if 'vray' in _all_keys or 'vfb' in _all_keys:
                renderer = "V-Ray"
            elif 'arnold' in _all_keys:
                renderer = "Arnold"
            elif 'redshift' in _all_keys:
                renderer = "Redshift"
            elif 'corona' in _all_keys:
                renderer = "Corona"
            elif 'renderman' in _all_keys or 'prman' in _all_keys:
                renderer = "RenderMan"
            elif 'cycles' in _all_keys or 'blender' in _all_keys:
                renderer = "Cycles"
            elif 'octane' in _all_keys:
                renderer = "Octane"
            elif 'karma' in _all_keys:
                renderer = "Karma"
            elif 'mantra' in _all_keys:
                renderer = "Mantra"

        if renderer:
            result['renderer'] = renderer
        if renderer_version:
            result['renderer_version'] = renderer_version

        # ── Detect color space ────────────────────────────────────────────
        color_space = None

        # 1. OIIO standard attribute (used by many tools)
        _oiio_cs = str_attrs.get('oiio:ColorSpace', str_attrs.get('exr/oiio:ColorSpace', ''))
        if _oiio_cs:
            _oiio_cs_lower = _oiio_cs.lower().strip()
            _cs_norm = {
                'linear': 'Linear', 'scene_linear': 'Linear',
                'lin_rec709': 'Linear Rec.709', 'lin_ap1': 'Linear ACEScg',
                'acescg': 'ACEScg', 'aces2065-1': 'ACES2065-1',
                'srgb': 'sRGB', 'srgb_texture': 'sRGB',
                'rec709': 'Rec.709', 'bt709': 'Rec.709',
                'rec2020': 'Rec.2020', 'bt2020': 'Rec.2020',
                'raw': 'Raw/Data', 'data': 'Raw/Data',
                'adobergb': 'Adobe RGB', 'p3-d65': 'DCI-P3',
            }
            color_space = _cs_norm.get(_oiio_cs_lower, _oiio_cs)

        # 2. V-Ray: vfb2_layers_json or exr/vfb2_layers_json
        if not color_space:
            _vfb_json = str_attrs.get('vfb2_layers_json',
                        str_attrs.get('exr/vfb2_layers_json', ''))
            if _vfb_json:
                try:
                    import json as _j
                    _vfb = _j.loads(_vfb_json)
                    # Walk the layer tree for ocio_colorspace
                    def _find_cs(obj):
                        if isinstance(obj, dict):
                            props = obj.get('properties', {})
                            ocio_cs = props.get('ocio_colorspace')
                            if ocio_cs is not None:
                                # 0 = scene_linear, 1 = sRGB, etc.
                                _vray_cs = {0: 'Linear', 1: 'sRGB', 2: 'Rec.709',
                                            3: 'ACEScg', 4: 'Raw'}
                                return _vray_cs.get(ocio_cs, f'OCIO #{ocio_cs}')
                            for sub in obj.get('sub-layers', []):
                                r = _find_cs(sub)
                                if r: return r
                        return None
                    cs = _find_cs(_vfb)
                    if cs: color_space = cs
                except Exception:
                    pass

        # 3. V-Ray: vrayInfo/colorSpace
        if not color_space:
            _vcs = str_attrs.get('vrayInfo/colorSpace', str_attrs.get('vrayInfo/color_space', ''))
            if _vcs:
                _vcs_map = {'linear': 'Linear', 'srgb': 'sRGB', 'raw': 'Raw'}
                color_space = _vcs_map.get(_vcs.lower().strip(), _vcs)

        # 4. Arnold: arnold/color_space or ai:color_space
        if not color_space:
            _acs = str_attrs.get('arnold/color_space', str_attrs.get('ai:color_space', ''))
            if _acs:
                color_space = _acs if _acs[0].isupper() else _acs.title()

        # 5. Redshift: redshift/colorSpace
        if not color_space:
            _rcs = str_attrs.get('redshift/colorSpace', str_attrs.get('redshift/color_space', ''))
            if _rcs:
                color_space = _rcs if _rcs[0].isupper() else _rcs.title()

        # 6. Corona: corona/colorSpace
        if not color_space:
            _ccs = str_attrs.get('corona/colorSpace', str_attrs.get('corona/color_space', ''))
            if _ccs:
                color_space = _ccs if _ccs[0].isupper() else _ccs.title()

        # 7. EXR chromaticities (standard OpenEXR attribute)
        if not color_space and 'chromaticities' in attrs:
            _, d = attrs['chromaticities']
            if len(d) >= 32:
                floats = struct.unpack('<8f', d[:32])
                rx, ry, gx, gy, bx, by, wx, wy = floats
                def _near(a, b, tol=0.02): return abs(a - b) < tol
                if (_near(rx, 0.64) and _near(ry, 0.33) and
                    _near(gx, 0.30) and _near(gy, 0.60) and
                    _near(bx, 0.15) and _near(by, 0.06)):
                    color_space = "Rec.709"
                elif (_near(rx, 0.713) and _near(ry, 0.293) and
                      _near(gx, 0.165) and _near(gy, 0.830)):
                    color_space = "ACEScg"
                elif (_near(rx, 0.708) and _near(ry, 0.292) and
                      _near(gx, 0.170) and _near(gy, 0.797)):
                    color_space = "ACES2065-1"
                elif (_near(rx, 0.680) and _near(ry, 0.320) and
                      _near(gx, 0.265) and _near(gy, 0.690)):
                    color_space = "Rec.2020"
                elif (_near(rx, 0.680) and _near(ry, 0.320) and
                      _near(gx, 0.265) and _near(gy, 0.690) and
                      _near(bx, 0.150) and _near(by, 0.060)):
                    color_space = "DCI-P3"
                else:
                    color_space = f"Custom ({rx:.2f},{ry:.2f})"

        if color_space:
            result['color_space'] = color_space

    except Exception:
        pass
    return result


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
    renderer:       Optional[str]   = None  # e.g. 'V-Ray', 'Arnold', 'Nuke'
    compression:    Optional[str]   = None  # e.g. 'zip', 'piz', 'dwaa'

    # User curation
    starred:        bool            = False
    rating:         int             = 0     # 0=unrated, 1-5 stars
    linked_ids:     list            = field(default_factory=list)  # version IDs (primary has all)
    version_of:     Optional[str]   = None  # if set, this is a hidden version of another asset

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
        renderer = exr_compression = None

        # ── EXR: parse header directly for accurate bit depth & color space ───
        if ext == ".exr" and path.exists():
            try:
                _exr = _parse_exr_header(path)
                if _exr:
                    width  = _exr.get("width")  or width
                    height = _exr.get("height") or height
                    codec  = "exr"
                    bit_depth       = _exr.get("bit_depth")
                    color_space     = _exr.get("color_space")
                    renderer        = _exr.get("renderer")
                    exr_compression = _exr.get("compression")
            except Exception:
                pass

        # ── HDR/DPX/other: use ffprobe (also EXR fallback if native parser missed) ─
        _HDR_EXTS = {".exr", ".dpx", ".hdr", ".pic", ".cin", ".sxr"}
        if file_type == "image" and ext in _HDR_EXTS and (bit_depth is None or width is None):
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
                            codec  = codec or _vs.get("codec_name")

                            # Bit depth (only if native parser didn't set it)
                            if bit_depth is None:
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

                            # Color space (only if native parser didn't set it)
                            if color_space is None:
                                _ct = _vs.get("color_transfer", "")
                                _cp = _vs.get("color_primaries", "")
                                _cs = _vs.get("color_space", "")
                                if _ct == "linear":
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
            renderer        = renderer,
            compression     = exr_compression,
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
        renderer    = None
        exr_compression = None

        # ── EXR sequences: parse first frame header for bit depth & color space
        if ext == ".exr" and first.exists():
            try:
                _exr = _parse_exr_header(first)
                if _exr:
                    width  = _exr.get("width")  or width
                    height = _exr.get("height") or height
                    codec  = "exr"
                    bit_depth       = _exr.get("bit_depth")
                    color_space     = _exr.get("color_space")
                    renderer        = _exr.get("renderer")
                    exr_compression = _exr.get("compression")
            except Exception:
                pass
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
            renderer     = renderer,
            compression  = exr_compression,
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

    # ── Asset versioning ────────────────────────────────────────────────────

    def link_as_version(self, primary_id: str, child_id: str):
        """Make child_id a hidden version of primary_id.
        Primary stays in grid, child disappears. Primary's linked_ids stores all versions."""
        primary = self._assets.get(primary_id)
        child   = self._assets.get(child_id)
        if not primary or not child or primary_id == child_id:
            return

        # If child was itself a primary with versions, absorb them
        for sub_id in list(child.linked_ids):
            sub = self._assets.get(sub_id)
            if sub:
                sub.version_of = primary_id
                if sub_id not in primary.linked_ids:
                    primary.linked_ids.append(sub_id)
        child.linked_ids.clear()

        # Link child → primary
        child.version_of = primary_id
        if child_id not in primary.linked_ids:
            primary.linked_ids.append(child_id)
        primary.version_of = None  # ensure primary stays primary
        self.save()

    def unlink_version(self, primary_id: str, child_id: str):
        """Restore a child version to an independent asset."""
        primary = self._assets.get(primary_id)
        child   = self._assets.get(child_id)
        if primary and child_id in primary.linked_ids:
            primary.linked_ids.remove(child_id)
        if child:
            child.version_of = None
        self.save()

    def get_versions(self, asset_id: str) -> list:
        """Return all versions sorted oldest→newest (V1=oldest, V(n)=newest)."""
        primary = self._assets.get(asset_id)
        if not primary:
            return []
        if primary.version_of:
            primary = self._assets.get(primary.version_of)
            if not primary:
                return []
        versions = [primary]
        for lid in primary.linked_ids:
            v = self._assets.get(lid)
            if v:
                versions.append(v)
        versions.sort(key=lambda a: a.date_added or "")
        return versions

    def get_version_primary(self, asset_id: str):
        """Get the primary asset for a version group. Returns self if already primary."""
        a = self._assets.get(asset_id)
        if not a:
            return None
        if a.version_of:
            return self._assets.get(a.version_of)
        return a

    def promote_version(self, old_primary_id: str, new_primary_id: str):
        """Swap which version is the primary (shown in grid)."""
        old_p = self._assets.get(old_primary_id)
        new_p = self._assets.get(new_primary_id)
        if not old_p or not new_p:
            return

        # Transfer all linked_ids to new primary
        all_versions = list(old_p.linked_ids)
        if new_primary_id in all_versions:
            all_versions.remove(new_primary_id)
        all_versions.append(old_primary_id)

        new_p.linked_ids = all_versions
        new_p.version_of = None

        old_p.linked_ids = []
        old_p.version_of = new_primary_id

        # Update all children to point to new primary
        for vid in all_versions:
            v = self._assets.get(vid)
            if v and v.id != new_primary_id:
                v.version_of = new_primary_id
        self.save()

    # Legacy compat
    def link_assets(self, id_a: str, id_b: str):
        self.link_as_version(id_a, id_b)

    def unlink_assets(self, id_a: str, id_b: str):
        self.unlink_version(id_a, id_b)

    def get_linked(self, asset_id: str) -> list:
        versions = self.get_versions(asset_id)
        return [v for v in versions if v.id != asset_id]

    # ── Persistence ───────────────────────────────────────────────────────────

    def verify(self) -> Tuple[bool, str]:
        """Verify the current library is valid."""
        count = len(self._assets)
        return True, f"OK — {count} assets (JSON)"

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
