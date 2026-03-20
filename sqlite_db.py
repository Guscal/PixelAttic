"""
sqlite_db.py — SQLite-backed asset library for Pixel Attic.

Drop-in replacement for the JSON Library in database.py.
Provides crash-safe writes, faster queries, and full-text search.

Usage:
    from sqlite_db import SQLiteLibrary
    lib = SQLiteLibrary()   # uses ~/.pixelattic/library.db
    lib.migrate_from_json() # one-time import from JSON library

The interface mirrors database.Library exactly so app.py can swap
with a single import change.
"""
import json
import sqlite3
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from database import Asset, LIBRARY_FILE, BACKUP_FILE

DB_DIR  = Path.home() / ".pixelattic"

def _get_db_path() -> Path:
    """Get SQLite DB path: custom directory from bootstrap/settings + library.db."""
    # 1. Check bootstrap paths.json
    try:
        _bp = Path.home() / ".pixelattic" / "paths.json"
        if _bp.exists():
            import json as _j
            bp = _j.loads(_bp.read_text(encoding="utf-8"))
            _lib = (bp.get("library") or "").strip()
            if _lib:
                p = Path(_lib)
                if p.suffix == ".db":
                    return p
                elif p.suffix == ".json":
                    return p.with_suffix(".db")
                else:
                    # It's a directory — append filename
                    return p / "library.db"
    except Exception:
        pass
    # 2. Check settings custom_library_path
    try:
        _sf = Path.home() / ".pixelattic" / "settings.json"
        if _sf.exists():
            import json as _j
            data = _j.loads(_sf.read_text(encoding="utf-8"))
            _clp = (data.get("custom_library_path") or "").strip()
            if _clp:
                p = Path(_clp)
                if p.suffix == ".db":
                    return p
                elif p.suffix == ".json":
                    return p.with_suffix(".db")
                else:
                    return p / "library.db"
    except Exception:
        pass
    return DB_DIR / "library.db"

DB_FILE = _get_db_path()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'Misc',
    tags          TEXT NOT NULL DEFAULT '[]',
    notes         TEXT NOT NULL DEFAULT '',
    date_added    TEXT,
    file_type     TEXT,
    format        TEXT,
    thumb_path    TEXT,
    width         INTEGER,
    height        INTEGER,
    fps           REAL,
    frame_count   INTEGER,
    duration_s    REAL,
    file_size_mb  REAL,
    collections   TEXT NOT NULL DEFAULT '[]',
    content_hash  TEXT,
    codec         TEXT,
    bit_depth     INTEGER,
    color_space   TEXT,
    audio_codec   TEXT,
    audio_channels INTEGER,
    renderer      TEXT,
    compression   TEXT,
    version_of    TEXT,
    starred       INTEGER NOT NULL DEFAULT 0,
    rating        INTEGER NOT NULL DEFAULT 0,
    linked_ids    TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS collections (
    name       TEXT PRIMARY KEY,
    asset_ids  TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_assets_file_type ON assets(file_type);
CREATE INDEX IF NOT EXISTS idx_assets_starred ON assets(starred);
CREATE INDEX IF NOT EXISTS idx_assets_rating ON assets(rating);
CREATE INDEX IF NOT EXISTS idx_assets_content_hash ON assets(content_hash);
"""


class SQLiteLibrary:
    """SQLite-backed asset library — same interface as database.Library."""

    def __init__(self, db_path: Path = DB_FILE):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.OperationalError:
            # Schema error — likely corrupted from previous version.
            # Delete and recreate.
            self._conn.close()
            db_path.unlink(missing_ok=True)
            self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
            print(f"[SQLiteLib] Recreated DB (old schema was corrupted)")
        # Migrate: add columns that may not exist in older databases
        for col, typ in [("renderer", "TEXT"), ("compression", "TEXT"), ("version_of", "TEXT")]:
            try:
                self._conn.execute(f"ALTER TABLE assets ADD COLUMN {col} {typ}")
                self._conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
        self._batch_mode = False
        print(f"[SQLiteLib] Opened {db_path}")

    # ── Asset CRUD ───────────────────────────────────────────────────────────

    def _asset_from_row(self, row) -> Asset:
        d = dict(row)
        d['tags']        = json.loads(d.get('tags', '[]'))
        d['collections'] = json.loads(d.get('collections', '[]'))
        d['linked_ids']  = json.loads(d.get('linked_ids', '[]'))
        d['starred']     = bool(d.get('starred', 0))
        return Asset(**{k: d[k] for k in Asset.__dataclass_fields__ if k in d})

    def all_assets(self) -> list:
        rows = self._conn.execute("SELECT * FROM assets").fetchall()
        return [self._asset_from_row(r) for r in rows]

    def get(self, asset_id: str) -> Optional[Asset]:
        row = self._conn.execute(
            "SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
        return self._asset_from_row(row) if row else None

    def add(self, asset: Asset):
        d = asdict(asset)
        d['tags']        = json.dumps(d['tags'])
        d['collections'] = json.dumps(d['collections'])
        d['linked_ids']  = json.dumps(d.get('linked_ids', []))
        d['starred']     = int(d.get('starred', False))
        d['rating']      = int(d.get('rating', 0))
        cols = ', '.join(d.keys())
        vals = ', '.join(['?'] * len(d))
        self._conn.execute(
            f"INSERT OR REPLACE INTO assets ({cols}) VALUES ({vals})",
            list(d.values()))
        if not self._batch_mode:
            self._conn.commit()

    def update(self, asset: Asset):
        self.add(asset)  # UPSERT

    def remove(self, asset_id: str):
        self._conn.execute("DELETE FROM assets WHERE id=?", (asset_id,))
        if not self._batch_mode:
            self._conn.commit()

    # ── Queries ──────────────────────────────────────────────────────────────

    def filtered(self, search: str = "", category: str = "All",
                 active_tags: list = None, sort_by: str = "name",
                 sort_reverse: bool = False) -> list:
        pool = self.all_assets()
        pool = [a for a in pool if a.matches(search, category, active_tags or [])]
        key_fn = {
            "name":   lambda a: a.name.lower(),
            "date":   lambda a: a.date_added or "",
            "size":   lambda a: a.file_size_mb or 0,
            "type":   lambda a: (a.file_type or "", a.format or "", a.name.lower()),
            "rating": lambda a: (a.rating or 0, a.name.lower()),
        }.get(sort_by, lambda a: a.name.lower())
        return sorted(pool, key=key_fn, reverse=sort_reverse)

    def category_counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT category, COUNT(*) as cnt FROM assets GROUP BY category"
        ).fetchall()
        counts = {"All": sum(r['cnt'] for r in rows)}
        for r in rows:
            counts[r['category']] = r['cnt']
        return counts

    def tag_counts(self, category: str = "All") -> dict:
        assets = self.all_assets() if category == "All" else [
            a for a in self.all_assets() if a.category == category]
        counts = {}
        for a in assets:
            for t in a.tags:
                counts[t] = counts.get(t, 0) + 1
        return counts

    # ── Collections ──────────────────────────────────────────────────────────

    def get_collections(self) -> dict:
        rows = self._conn.execute("SELECT * FROM collections").fetchall()
        return {r['name']: json.loads(r['asset_ids']) for r in rows}

    def collection_assets(self, name: str) -> list:
        row = self._conn.execute(
            "SELECT asset_ids FROM collections WHERE name=?", (name,)).fetchone()
        if not row:
            return []
        ids = json.loads(row['asset_ids'])
        return [a for a in (self.get(i) for i in ids) if a is not None]

    def collection_count(self, name: str) -> int:
        return len(self.collection_assets(name))

    def collections_for_asset(self, asset_id: str) -> list:
        colls = self.get_collections()
        return [n for n, ids in colls.items() if asset_id in ids]

    def create_collection(self, name: str) -> bool:
        try:
            self._conn.execute(
                "INSERT INTO collections (name, asset_ids) VALUES (?, '[]')", (name,))
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def delete_collection(self, name: str):
        self._conn.execute("DELETE FROM collections WHERE name=?", (name,))
        self._conn.commit()

    def rename_collection(self, old: str, new: str) -> bool:
        try:
            self._conn.execute(
                "UPDATE collections SET name=? WHERE name=?", (new, old))
            self._conn.commit()
            return True
        except Exception:
            return False

    def add_to_collection(self, name: str, asset_id: str):
        row = self._conn.execute(
            "SELECT asset_ids FROM collections WHERE name=?", (name,)).fetchone()
        if not row:
            self._conn.execute(
                "INSERT INTO collections (name, asset_ids) VALUES (?, ?)",
                (name, json.dumps([asset_id])))
        else:
            ids = json.loads(row['asset_ids'])
            if asset_id not in ids:
                ids.append(asset_id)
                self._conn.execute(
                    "UPDATE collections SET asset_ids=? WHERE name=?",
                    (json.dumps(ids), name))
        self._conn.commit()

    def remove_from_collection(self, name: str, asset_id: str):
        row = self._conn.execute(
            "SELECT asset_ids FROM collections WHERE name=?", (name,)).fetchone()
        if row:
            ids = json.loads(row['asset_ids'])
            if asset_id in ids:
                ids.remove(asset_id)
                self._conn.execute(
                    "UPDATE collections SET asset_ids=? WHERE name=?",
                    (json.dumps(ids), name))
                self._conn.commit()

    # ── Asset linking ────────────────────────────────────────────────────────

    def link_as_version(self, primary_id: str, child_id: str):
        primary = self.get(primary_id)
        child = self.get(child_id)
        if not primary or not child or primary_id == child_id:
            return
        for sub_id in list(child.linked_ids):
            sub = self.get(sub_id)
            if sub:
                sub.version_of = primary_id
                self.update(sub)
                if sub_id not in primary.linked_ids:
                    primary.linked_ids.append(sub_id)
        child.linked_ids = []
        child.version_of = primary_id
        if child_id not in primary.linked_ids:
            primary.linked_ids.append(child_id)
        primary.version_of = None
        self.update(primary)
        self.update(child)

    def unlink_version(self, primary_id: str, child_id: str):
        primary = self.get(primary_id)
        child = self.get(child_id)
        if primary and child_id in primary.linked_ids:
            primary.linked_ids.remove(child_id)
            self.update(primary)
        if child:
            child.version_of = None
            self.update(child)

    def get_versions(self, asset_id: str) -> list:
        a = self.get(asset_id)
        if not a:
            return []
        if a.version_of:
            a = self.get(a.version_of)
            if not a:
                return []
        versions = [a]
        for lid in a.linked_ids:
            v = self.get(lid)
            if v:
                versions.append(v)
        versions.sort(key=lambda x: x.date_added or "")
        return versions

    def get_version_primary(self, asset_id: str):
        a = self.get(asset_id)
        if not a:
            return None
        if a.version_of:
            return self.get(a.version_of)
        return a

    def promote_version(self, old_primary_id: str, new_primary_id: str):
        old_p = self.get(old_primary_id)
        new_p = self.get(new_primary_id)
        if not old_p or not new_p:
            return
        all_versions = list(old_p.linked_ids)
        if new_primary_id in all_versions:
            all_versions.remove(new_primary_id)
        all_versions.append(old_primary_id)
        new_p.linked_ids = all_versions
        new_p.version_of = None
        old_p.linked_ids = []
        old_p.version_of = new_primary_id
        self.update(new_p)
        self.update(old_p)
        for vid in all_versions:
            v = self.get(vid)
            if v and v.id != new_primary_id:
                v.version_of = new_primary_id
                self.update(v)

    # Legacy compat
    def link_assets(self, id_a: str, id_b: str):
        self.link_as_version(id_a, id_b)

    def unlink_assets(self, id_a: str, id_b: str):
        self.unlink_version(id_a, id_b)

    def get_linked(self, asset_id: str) -> list:
        versions = self.get_versions(asset_id)
        return [v for v in versions if v.id != asset_id]

    # ── Duplicate detection ──────────────────────────────────────────────────

    @staticmethod
    def hash_file(path: str, sample_bytes: int = 4 * 1024 * 1024) -> Optional[str]:
        from database import Library
        return Library.hash_file(path, sample_bytes)

    def find_duplicates(self) -> list:
        from collections import defaultdict
        buckets = defaultdict(list)
        for a in self.all_assets():
            h = getattr(a, "content_hash", None)
            if h:
                buckets[h].append(a)
        return [g for g in buckets.values() if len(g) >= 2]

    def compute_missing_hashes(self, progress_cb=None) -> int:
        """Compute and store hashes for assets that don't have one yet."""
        count = 0
        need = [a for a in self.all_assets()
                if not getattr(a, "content_hash", None) and Path(a.path).exists()]
        for i, asset in enumerate(need):
            if progress_cb:
                progress_cb(i, len(need))
            h = self.hash_file(asset.path)
            if h:
                asset.content_hash = h
                self.update(asset)
                count += 1
        return count

    def backup(self) -> tuple:
        """Create a backup copy of the database file."""
        import shutil
        bak = self._db_path.with_suffix(".db.bak")
        try:
            shutil.copy2(self._db_path, bak)
            return True, f"Backup saved: {bak.name}"
        except Exception as e:
            return False, str(e)

    # ── Batch mode ───────────────────────────────────────────────────────────

    def begin_batch(self):
        self._batch_mode = True

    def end_batch(self):
        self._batch_mode = False
        self._conn.commit()

    def save(self):
        if not self._batch_mode:
            self._conn.commit()

    def save_now(self):
        self._conn.commit()

    def flush_if_dirty(self):
        pass  # SQLite commits are immediate or batched

    # ── Export/Import with JSON ──────────────────────────────────────────────

    def export_collection(self, name: str, out_path: Path):
        """Export a collection as .pixcol JSON (compatible with JSON Library)."""
        from database import Library
        # Delegate to temp JSON library
        jlib = Library.__new__(Library)
        jlib._assets = {a.id: a for a in self.all_assets()}
        jlib._collections = self.get_collections()
        jlib._batch_mode = False
        jlib._save_dirty = False
        jlib.export_collection(name, out_path)

    def import_collection(self, file_path: Path) -> tuple:
        """Import a .pixcol JSON file."""
        from database import Library
        jlib = Library.__new__(Library)
        jlib._assets = {a.id: a for a in self.all_assets()}
        jlib._collections = self.get_collections()
        jlib._batch_mode = False
        jlib._save_dirty = False
        result = jlib.import_collection(file_path)
        # Sync imported assets back to SQLite
        self.begin_batch()
        for a in jlib._assets.values():
            if not self.get(a.id):
                self.add(a)
        for n, ids in jlib._collections.items():
            if n not in self.get_collections():
                self.create_collection(n)
                for aid in ids:
                    self.add_to_collection(n, aid)
        self.end_batch()
        return result

    # ── Migration from JSON ──────────────────────────────────────────────────

    def migrate_from_json(self, json_path: Path = LIBRARY_FILE) -> int:
        """Import all assets and collections from the JSON library.
        Returns number of assets imported."""
        if not json_path.exists():
            print("[SQLiteLib] No JSON library found to migrate")
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[SQLiteLib] JSON parse error: {e}")
            return 0

        count = 0
        self.begin_batch()
        for d in data.get("assets", []):
            try:
                a = Asset.from_dict(d)
                self.add(a)
                count += 1
            except Exception as e:
                print(f"[SQLiteLib] Skip: {e}")
        for name, ids in data.get("collections", {}).items():
            self.create_collection(name)
            for aid in ids:
                self.add_to_collection(name, aid)
        self.end_batch()
        print(f"[SQLiteLib] Migrated {count} assets from JSON")
        return count

    def export_to_json(self, out_path: Path = LIBRARY_FILE):
        """Export entire library back to JSON format."""
        data = {
            "assets":             [asdict(a) for a in self.all_assets()],
            "collections":        self.get_collections(),
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[SQLiteLib] Exported to {out_path}")

    # ── Cleanup ──────────────────────────────────────────────────────────────

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def verify(self) -> tuple:
        """Check if the SQLite DB is valid and return asset count."""
        try:
            row = self._conn.execute("SELECT COUNT(*) FROM assets").fetchone()
            count = row[0] if row else 0
            return True, f"OK — {count} assets (SQLite)"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def verify_file(path: Path) -> tuple:
        """Check if a SQLite DB file is valid."""
        try:
            conn = sqlite3.connect(str(path))
            row = conn.execute("SELECT COUNT(*) FROM assets").fetchone()
            count = row[0] if row else 0
            conn.close()
            return True, f"OK — {count} assets"
        except Exception as e:
            return False, str(e)

    def restore_from_backup(self) -> tuple:
        """Restore from .db.bak backup file."""
        import shutil
        bak = self._db_path.with_suffix(".db.bak")
        if not bak.exists():
            return False, f"No backup found at {bak.name}"
        try:
            self._conn.close()
            shutil.copy2(bak, self._db_path)
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            row = self._conn.execute("SELECT COUNT(*) FROM assets").fetchone()
            count = row[0] if row else 0
            return True, f"Restored {count} assets from {bak.name}"
        except Exception as e:
            return False, str(e)
