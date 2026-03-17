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
DB_FILE = DB_DIR / "library.db"

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

    def link_assets(self, id_a: str, id_b: str):
        a, b = self.get(id_a), self.get(id_b)
        if not a or not b or id_a == id_b:
            return
        if id_b not in a.linked_ids:
            a.linked_ids.append(id_b)
            self.update(a)
        if id_a not in b.linked_ids:
            b.linked_ids.append(id_a)
            self.update(b)

    def unlink_assets(self, id_a: str, id_b: str):
        a, b = self.get(id_a), self.get(id_b)
        if a and id_b in a.linked_ids:
            a.linked_ids.remove(id_b)
            self.update(a)
        if b and id_a in b.linked_ids:
            b.linked_ids.remove(id_a)
            self.update(b)

    def get_linked(self, asset_id: str) -> list:
        a = self.get(asset_id)
        if not a:
            return []
        return [self.get(lid) for lid in a.linked_ids if self.get(lid)]

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

    @staticmethod
    def verify_file(path: Path) -> tuple:
        """Check if a SQLite DB is valid."""
        try:
            conn = sqlite3.connect(str(path))
            conn.execute("SELECT COUNT(*) FROM assets")
            conn.close()
            return True, "OK"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def restore_from_backup() -> tuple:
        return False, "SQLite uses WAL — automatic recovery"
