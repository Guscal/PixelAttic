"""
panels.py — Sidebar and DetailPanel for Pixel Attic.
"""
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import (
    QWidget, QFrame, QScrollArea, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QSizePolicy, QSlider
)
from PySide2.QtGui  import QPixmap, QCursor
from PySide2.QtCore import Qt, Signal, QTimer

from config   import CATEGORY_ICONS
from database import Library, Asset
from widgets  import TagPill, FlowTagLayout

def _dim_lbl(text: str, size: int = 11) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: rgb(71,85,105); font-size: {size}px; background: transparent;")
    return lbl

def _section_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section_label")
    return lbl

# ── Sidebar ───────────────────────────────────────────────────────────────────

class Sidebar(QWidget):
    categorySelected    = Signal(str)
    tagToggled          = Signal(str, bool)
    collectionSelected  = Signal(object)
    newCollectionReq      = Signal()
    importCollectionReq   = Signal()
    exportCollectionReq   = Signal(str)
    deleteCollectionReq   = Signal(str)
    renameCollectionReq   = Signal(str)
    clearTagsReq        = Signal()
    addCategoryReq      = Signal()
    deleteCategoryReq   = Signal(str)
    saveSearchReq       = Signal()
    loadSearchReq       = Signal(int)
    deleteSearchReq     = Signal(int)
    renameSearchReq     = Signal(int)

    def __init__(self, lib: Library, parent=None):
        super().__init__(parent)
        self.lib = lib
        self.setObjectName("sidebar")
        self._active_cat  = "All"
        self._active_tags: list = []
        self._active_coll: Optional[str] = None
        self._cat_btns:  dict = {}
        self._tag_btns:  dict = {}
        self._coll_btns: dict = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(0)

        def _sidebar_sep():
            """Thin horizontal separator line between sidebar sections."""
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFixedHeight(1)
            sep.setStyleSheet("background: rgb(30, 33, 52); border: none;")
            layout.addWidget(sep)
            layout.addSpacing(3)

        # ── Categories ──────────────────────────────────────────────────────
        cat_hdr = QHBoxLayout()
        cat_hdr.addWidget(_dim_lbl("  CATEGORIES", 10))
        cat_hdr.addStretch()
        add_cat_btn = QPushButton("+")
        add_cat_btn.setFixedHeight(20)
        add_cat_btn.setFixedWidth(28)
        add_cat_btn.setObjectName("btn_accent")
        add_cat_btn.setToolTip("Add custom category")
        add_cat_btn.clicked.connect(lambda checked=False: self.addCategoryReq.emit())
        cat_hdr.addWidget(add_cat_btn)
        cat_hdr.addSpacing(4)
        layout.addLayout(cat_hdr)

        self._cat_container = QWidget()
        self._cat_layout = QVBoxLayout(self._cat_container)
        self._cat_layout.setContentsMargins(4, 0, 4, 0)
        self._cat_layout.setSpacing(1)
        cat_scroll = QScrollArea()
        cat_scroll.setWidgetResizable(True)
        cat_scroll.setMinimumHeight(80)
        cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cat_scroll.setFrameShape(QFrame.NoFrame)
        cat_scroll.setWidget(self._cat_container)
        layout.addWidget(cat_scroll, 3)  # stretch factor 3

        _sidebar_sep()

        # ── Tags ────────────────────────────────────────────────────────────
        tags_hdr = QHBoxLayout()
        tags_hdr.addWidget(_dim_lbl("  TAGS", 10))
        tags_hdr.addStretch()
        layout.addLayout(tags_hdr)

        tags_scroll = QScrollArea()
        tags_scroll.setMinimumHeight(60)
        tags_scroll.setWidgetResizable(True)
        tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tags_scroll.setFrameShape(QFrame.NoFrame)
        self._tag_container = QWidget()
        self._tag_layout = QVBoxLayout(self._tag_container)
        self._tag_layout.setContentsMargins(4, 0, 4, 0)
        self._tag_layout.setSpacing(1)
        tags_scroll.setWidget(self._tag_container)
        layout.addWidget(tags_scroll, 2)  # stretch factor 2

        _sidebar_sep()

        # ── Saved Searches ──────────────────────────────────────────────
        ss_hdr = QHBoxLayout()
        ss_hdr.addWidget(_dim_lbl("  SAVED SEARCHES", 10))
        ss_hdr.addStretch()
        save_search_btn = QPushButton("+")
        save_search_btn.setFixedHeight(20)
        save_search_btn.setFixedWidth(28)
        save_search_btn.setObjectName("btn_accent")
        save_search_btn.setToolTip("Save current search as preset")
        save_search_btn.clicked.connect(lambda checked=False: self.saveSearchReq.emit())
        ss_hdr.addWidget(save_search_btn)
        ss_hdr.addSpacing(4)
        layout.addLayout(ss_hdr)

        self._search_container = QWidget()
        self._search_layout = QVBoxLayout(self._search_container)
        self._search_layout.setContentsMargins(4, 0, 4, 0)
        self._search_layout.setSpacing(1)
        ss_scroll = QScrollArea()
        ss_scroll.setWidgetResizable(True)
        ss_scroll.setMinimumHeight(30)
        ss_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ss_scroll.setFrameShape(QFrame.NoFrame)
        ss_scroll.setWidget(self._search_container)
        layout.addWidget(ss_scroll, 1)

        _sidebar_sep()

        # ── Collections ─────────────────────────────────────────────────────
        coll_hdr = QHBoxLayout()
        coll_hdr.addWidget(_dim_lbl("  COLLECTIONS", 10))
        coll_hdr.addStretch()

        imp_btn = QPushButton("Import")
        imp_btn.setFixedHeight(20)
        imp_btn.setFixedWidth(72)
        imp_btn.setObjectName("btn_edit")
        imp_btn.setToolTip("Import a shared collection (.pixcol file)")
        imp_btn.clicked.connect(lambda checked=False: self.importCollectionReq.emit())
        coll_hdr.addWidget(imp_btn)

        new_coll_btn = QPushButton("+")
        new_coll_btn.setFixedHeight(20)
        new_coll_btn.setFixedWidth(28)
        new_coll_btn.setObjectName("btn_accent")
        new_coll_btn.setToolTip("New collection")
        new_coll_btn.clicked.connect(lambda checked=False: self.newCollectionReq.emit())
        coll_hdr.addWidget(new_coll_btn)
        coll_hdr.addSpacing(4)
        layout.addLayout(coll_hdr)

        self._all_coll_btn = QPushButton("  ●  All Assets")
        self._all_coll_btn.setCheckable(True)
        self._all_coll_btn.setChecked(True)
        self._all_coll_btn.clicked.connect(
            lambda checked=False: self.collectionSelected.emit(None))

        self._coll_container = QWidget()
        self._coll_layout = QVBoxLayout(self._coll_container)
        self._coll_layout.setContentsMargins(4, 0, 4, 0)
        self._coll_layout.setSpacing(1)

        # Wrap "All Assets" + collection items in scroll
        _coll_inner = QWidget()
        _coll_inner_l = QVBoxLayout(_coll_inner)
        _coll_inner_l.setContentsMargins(0, 0, 0, 0)
        _coll_inner_l.setSpacing(1)
        _coll_inner_l.addWidget(self._all_coll_btn)
        _coll_inner_l.addWidget(self._coll_container)
        _coll_inner_l.addStretch()

        coll_scroll = QScrollArea()
        coll_scroll.setWidgetResizable(True)
        coll_scroll.setMinimumHeight(30)
        coll_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        coll_scroll.setFrameShape(QFrame.NoFrame)
        coll_scroll.setWidget(_coll_inner)
        layout.addWidget(coll_scroll, 2)

    # ── Rebuild ───────────────────────────────────────────────────────────────

    def rebuild_categories(self, lib: Library, active_cat: str,
                           custom_cats: list = None, hidden_cats: list = None):
        self._active_cat = active_cat
        while self._cat_layout.count():
            item = self._cat_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._cat_btns.clear()
        from config import get_categories
        for cat in get_categories(custom_cats, hidden_cats):
            icon  = CATEGORY_ICONS.get(cat, "·")
            count = lib.category_counts().get(cat, 0)
            row   = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(0)
            btn = QPushButton(f"  {icon}  {cat}  ({count})")
            btn.setCheckable(True)
            btn.setChecked(cat == active_cat)
            btn.clicked.connect(
                lambda checked=False, c=cat: self.categorySelected.emit(c))
            row_l.addWidget(btn, 1)
            self._cat_layout.addWidget(row)
            self._cat_btns[cat] = btn

    def rebuild_tags(self, lib: Library, active_cat: str, active_tags: list):
        self._active_tags = active_tags
        while self._tag_layout.count():
            item = self._tag_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._tag_btns.clear()
        for tag_name, count in sorted(lib.tag_counts(active_cat).items()):
            btn = QPushButton(f"  {tag_name.upper()}  ({count})")
            btn.setCheckable(True)
            btn.setChecked(tag_name in active_tags)
            btn.clicked.connect(
                lambda checked=False, t=tag_name, b=btn:
                    self.tagToggled.emit(t, b.isChecked()))
            self._tag_layout.addWidget(btn)
            self._tag_btns[tag_name] = btn

    def rebuild_saved_searches(self, searches: list):
        """Rebuild saved search preset buttons — matches collection row style."""
        while self._search_layout.count():
            item = self._search_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for idx, ss in enumerate(searches or []):
            name = ss.get("name", f"Search {idx + 1}")
            row   = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(2)

            btn = QPushButton(f"  {name[:20]}{'…' if len(name)>20 else ''}")
            btn.setToolTip(f"Click to apply: {name}")
            btn.clicked.connect(
                lambda checked=False, i=idx: self.loadSearchReq.emit(i))
            row_l.addWidget(btn, 1)

            # Rename button (same style as collection rename)
            def _sb(icon_text, tip, bg_col, hover_col, border_col):
                from PySide2.QtWidgets import QToolButton
                tb2 = QToolButton()
                tb2.setText(icon_text)
                tb2.setFixedSize(22, 22)
                tb2.setToolTip(tip)
                tb2.setStyleSheet(
                    f"QToolButton{{background:{bg_col};border:1px solid {border_col};"
                    f"border-radius:3px;font-size:12px;color:rgb(80,95,120);"
                    f"padding:0;margin:0;}}"
                    f"QToolButton:hover{{background:{hover_col};"
                    f"color:white;border-color:{hover_col};}}")
                return tb2

            ren_b = _sb("~", "Rename preset",
                "rgba(96,165,250,15)", "rgba(96,165,250,200)", "rgba(96,165,250,40)")
            ren_b.clicked.connect(
                lambda checked=False, i=idx: self.renameSearchReq.emit(i))
            row_l.addWidget(ren_b)

            del_b = _sb("✕", "Delete preset",
                "rgba(248,113,113,10)", "rgba(220,80,80,200)", "rgba(248,113,113,35)")
            del_b.clicked.connect(
                lambda checked=False, i=idx: self.deleteSearchReq.emit(i))
            row_l.addWidget(del_b)

            self._search_layout.addWidget(row)

    def rebuild_collections(self, lib: Library, active_coll: Optional[str]):
        self._active_coll = active_coll
        while self._coll_layout.count():
            item = self._coll_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._coll_btns.clear()
        self._all_coll_btn.setChecked(active_coll is None)
        for name in sorted(lib.get_collections().keys()):
            count = lib.collection_count(name)
            row   = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(2)
            btn = QPushButton(
                f" ● {name[:16]}{'…' if len(name)>16 else ''} ({count})")
            btn.setCheckable(True)
            btn.setChecked(name == active_coll)
            btn.clicked.connect(
                lambda checked=False, n=name: self.collectionSelected.emit(n))
            # Right-click → context menu
            btn.setContextMenuPolicy(Qt.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, n=name, b=btn: self._coll_context_menu(n, b))
            row_l.addWidget(btn)
            def _coll_btn(icon_text, tip, bg_col, hover_col, border_col, sig_name=name):
                from PySide2.QtWidgets import QToolButton
                tb2 = QToolButton()
                tb2.setText(icon_text)
                tb2.setFixedSize(22, 22)
                tb2.setToolTip(tip)
                tb2.setStyleSheet(
                    f"QToolButton{{background:{bg_col};border:1px solid {border_col};"
                    f"border-radius:3px;font-size:12px;color:rgb(80,95,120);"
                    f"padding:0;margin:0;qproperty-toolButtonStyle:0;}}"
                    f"QToolButton:hover{{background:{hover_col};color:white;border-color:{hover_col};}}")
                return tb2
            ren_b = _coll_btn("~", "Rename collection",
                "rgba(96,165,250,15)", "rgba(96,165,250,200)", "rgba(96,165,250,40)")
            ren_b.clicked.connect(
                lambda checked=False, n=name: self.renameCollectionReq.emit(n))
            row_l.addWidget(ren_b)
            del_b = _coll_btn("✕", "Delete collection",
                "rgba(248,113,113,10)", "rgba(220,80,80,200)", "rgba(248,113,113,35)")
            del_b.clicked.connect(
                lambda checked=False, n=name: self.deleteCollectionReq.emit(n))
            row_l.addWidget(del_b)
            self._coll_layout.addWidget(row)
            self._coll_btns[name] = btn

    def _coll_context_menu(self, name: str, btn):
        """Right-click context menu on a collection button."""
        from PySide2.QtWidgets import QMenu
        from PySide2.QtGui     import QCursor
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:rgb(12,12,22);border:1px solid rgb(30,30,50);"
            "color:rgb(200,210,230);font-size:12px;padding:4px;}"
            "QMenu::item{padding:6px 18px;border-radius:3px;}"
            "QMenu::item:selected{background:rgb(249,115,22);color:black;}")
        menu.addAction(f"Export  '{name}'",
                       lambda n=name: self.exportCollectionReq.emit(n))
        menu.addSeparator()
        menu.addAction(f"Rename  '{name}'",
                       lambda n=name: self.renameCollectionReq.emit(n))
        menu.addAction(f"Delete  '{name}'",
                       lambda n=name: self.deleteCollectionReq.emit(n))
        menu.exec_(QCursor.pos())

    def set_active_category(self, cat: str):
        self._active_cat = cat
        for c, btn in self._cat_btns.items():
            btn.setChecked(c == cat)

# ── Detail Panel ──────────────────────────────────────────────────────────────

class DetailPanel(QWidget):
    tagAdded         = Signal(str, str)
    tagRemoved       = Signal(str, str)
    nameChanged      = Signal(str, str)
    catChanged       = Signal(str, str)
    notesChanged     = Signal(str, str)
    openFileReq      = Signal(str)
    showExplorerReq  = Signal(str)
    ratingChanged    = Signal(str, int)   # (asset_id, rating 0-5)
    searchTagReq     = Signal(str)
    searchCatReq     = Signal(str)
    editModeExited   = Signal()           # emitted when user clicks "Done"
    switchVersionReq = Signal(str, str)   # (new_primary_id, old_primary_id)
    linkVersionFromLib = Signal(str)      # (primary_id) — open link-from-library dialog
    linkVersionFromFile = Signal(str)     # (primary_id) — open link-from-file dialog
    unlinkVersionReq = Signal(str, str)   # (primary_id, child_id)
    deleteVersionReq = Signal(str, str)   # (primary_id, child_id) — unlink + remove from lib
    prevAssetReq     = Signal()   # navigate to previous asset in list
    nextAssetReq     = Signal()   # navigate to next asset in list
    navigateToReq    = Signal(str)  # navigate to specific asset by ID
    unlinkReq        = Signal(str, str)  # (asset_id_a, asset_id_b)
    starChanged      = Signal(str, bool)  # (asset_id, starred)

    def __init__(self, lib: Library, parent=None):
        super().__init__(parent)
        self.lib = lib
        self._edit_mode      = False
        self._current_asset  = None
        self._accent_rgb     = "249,115,22"  # default orange; updated by apply_accent()
        self._custom_cats    = []    # custom categories from Settings
        self._hidden_cats    = []    # hidden base categories from Settings
        self.setObjectName("detail_panel")
        self.setMinimumWidth(460)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self._scroll)

        # Notes debounce timer — saves 800ms after last keystroke
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(800)
        self._notes_timer.timeout.connect(self._flush_notes)
        self._pending_notes = ("", "")  # (asset_id, text)

        self._content = None
        self._cl = None
        self._rebuild_content_widget()
        self.show_placeholder()

    # ── Public ────────────────────────────────────────────────────────────────

    def set_nav_index(self, current: int, total: int):
        """Update the nav position label. Call after show_asset()."""
        self._nav_current = current
        self._nav_total   = total
        if hasattr(self, '_nav_idx_lbl'):
            try:
                self._nav_idx_lbl.setText(f"{current + 1} / {total}")
            except RuntimeError:
                pass  # C++ widget already deleted — label will be rebuilt on next show_asset

    def apply_accent(self, accent_rgb: str):
        """Update stored accent colour (r,g,b string) used by action buttons."""
        self._accent_rgb = accent_rgb

    def set_categories(self, custom: list, hidden: list):
        """Update the custom/hidden category lists (call after Settings change)."""
        self._custom_cats = custom or []
        self._hidden_cats = hidden or []

    def show_placeholder(self):
        self._clear()
        self._edit_mode = False
        self._current_asset = None
        self._cl.addStretch()
        title = QLabel("SELECT AN ASSET")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: rgb(71,85,105); font-size: 12px; letter-spacing: 1px;")
        sub = QLabel(
            "Click a card to view details\n\n"
            "Ctrl+click  —  multi-select\n"
            "Double-click  —  open file")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet(
            "color: rgb(36,42,58); font-size: 11px; background: transparent;")
        self._cl.addWidget(title)
        self._cl.addSpacing(8)
        self._cl.addWidget(sub)
        self._cl.addStretch()

    def show_asset(self, asset: Asset, thumb_path: Optional[Path],
                   strip_path: Optional[Path] = None,
                   skip_player: bool = False):
        self._notes_timer.stop()
        self._clear()
        self._current_asset = asset
        self._edit_mode = False

        # ── Minimal mode during import — just name + thumb + hint ─────────
        if skip_player:
            # Name
            name_lbl = QLabel(asset.name)
            name_lbl.setStyleSheet(
                "color:rgb(226,232,240);font-size:13px;font-weight:bold;")
            name_lbl.setWordWrap(True)
            self._cl.addWidget(name_lbl)

            # Format + res
            info = f"{asset.format or ''} · {asset.display_res}"
            info_lbl = QLabel(info)
            info_lbl.setStyleSheet("color:rgb(100,116,139);font-size:11px;")
            self._cl.addWidget(info_lbl)
            self._cl.addSpacing(6)

            # Thumbnail if cached
            if thumb_path and Path(str(thumb_path)).exists():
                pix = QPixmap(str(thumb_path))
                if not pix.isNull():
                    panel_w = max(self.width() - 16, 200)
                    scaled = pix.scaledToWidth(panel_w, Qt.FastTransformation)
                    lbl = QLabel()
                    lbl.setAlignment(Qt.AlignCenter)
                    lbl.setPixmap(scaled)
                    self._cl.addWidget(lbl)

            # Hint
            self._cl.addSpacing(8)
            hint = QLabel("⟳  Import in progress\nFull details load when done")
            hint.setAlignment(Qt.AlignCenter)
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "color:rgba(96,165,250,180);font-size:11px;"
                "background:rgba(96,165,250,6);border-radius:4px;"
                "padding:12px;")
            self._cl.addWidget(hint)
            self._cl.addStretch()
            return

        # ── Full detail mode ──────────────────────────────────────────────

        # ── Asset navigation ── prev / next in filtered list ───────────────
        nav = QHBoxLayout()
        nav.setContentsMargins(8, 0, 8, 0)
        nav.setSpacing(4)
        _NAV_S = (
            "QPushButton{background:rgb(14,16,26);color:rgb(120,135,165);"
            "border:1px solid rgb(30,33,52);border-radius:4px;"
            "font-size:12px;min-height:24px;padding:0 10px;}"
            "QPushButton:hover{color:rgb(220,228,245);"
            "border-color:rgb(55,60,90);background:rgb(18,22,36);}"
        )
        prev_btn = QPushButton("Prev")
        prev_btn.setFixedHeight(24)
        prev_btn.setStyleSheet(_NAV_S)
        prev_btn.setToolTip("Previous asset  (Left arrow)")
        prev_btn.clicked.connect(lambda checked=False: self.prevAssetReq.emit())

        next_btn = QPushButton("Next")
        next_btn.setFixedHeight(24)
        next_btn.setStyleSheet(_NAV_S)
        next_btn.setToolTip("Next asset  (Right arrow)")
        next_btn.clicked.connect(lambda checked=False: self.nextAssetReq.emit())
        asset_idx_lbl = QLabel()
        asset_idx_lbl.setStyleSheet(
            "color:rgb(60,70,100);font-size:10px;background:transparent;")
        asset_idx_lbl.setAlignment(Qt.AlignCenter)
        _cur = getattr(self, '_nav_current', 0)
        _tot = getattr(self, '_nav_total',   0)
        if _tot:
            asset_idx_lbl.setText(f"{_cur + 1} / {_tot}")
        nav.addWidget(prev_btn, 1)
        nav.addWidget(asset_idx_lbl, 0)
        nav.addWidget(next_btn, 1)
        self._nav_idx_lbl = asset_idx_lbl
        self._cl.addLayout(nav)
        self._cl.addSpacing(2)

        # ── Favorite toggle row ───────────────────────────────────────────
        _is_starred = getattr(asset, 'starred', False)
        fav_row = QHBoxLayout()
        fav_row.setContentsMargins(8, 0, 8, 0)
        fav_row.setSpacing(6)

        _STAR_ON  = ("QPushButton{background:rgba(251,191,36,15);"
                     "color:rgb(251,191,36);border:1px solid rgba(251,191,36,50);"
                     "border-radius:4px;font-size:13px;padding:2px 10px;}"
                     "QPushButton:hover{background:rgba(251,191,36,30);}")
        _STAR_OFF = ("QPushButton{background:rgb(14,16,26);"
                     "color:rgb(55,65,90);border:1px solid rgb(30,33,52);"
                     "border-radius:4px;font-size:13px;padding:2px 10px;}"
                     "QPushButton:hover{color:rgba(251,191,36,160);}")

        fav_btn = QPushButton("★  Favorite" if _is_starred else "☆  Favorite")
        fav_btn.setFixedHeight(26)
        fav_btn.setCursor(QCursor(Qt.PointingHandCursor))
        fav_btn.setStyleSheet(_STAR_ON if _is_starred else _STAR_OFF)
        self._detail_star_state = [_is_starred]

        _asset_id = asset.id  # capture for closure
        def _toggle_detail_star(checked=False):
            self._detail_star_state[0] = not self._detail_star_state[0]
            s = self._detail_star_state[0]
            fav_btn.setText("★  Favorite" if s else "☆  Favorite")
            fav_btn.setStyleSheet(_STAR_ON if s else _STAR_OFF)
            a = self.lib.get(_asset_id)
            if a:
                a.starred = bool(s)
                self.lib.update(a)
                try: self.lib.save_now()
                except Exception: pass
            self.starChanged.emit(_asset_id, s)
        fav_btn.clicked.connect(_toggle_detail_star)

        fav_row.addWidget(fav_btn)
        fav_row.addStretch()
        self._cl.addLayout(fav_row)
        self._cl.addSpacing(2)

        # ── Rating row (clickable 1–5 stars) ──────────────────────────────
        rating_row = QHBoxLayout()
        rating_row.setContentsMargins(8, 0, 8, 0)
        rating_row.setSpacing(1)
        _cur_rating = getattr(asset, 'rating', 0) or 0
        self._rating_btns = []
        _STAR_DIM = ("QPushButton{background:transparent;color:rgb(50,55,75);"
                     "border:none;font-size:16px;padding:0;min-width:20px;}"
                     "QPushButton:hover{color:rgba(251,191,36,180);}")
        _STAR_LIT = ("QPushButton{background:transparent;color:rgb(251,191,36);"
                     "border:none;font-size:16px;padding:0;min-width:20px;}"
                     "QPushButton:hover{color:rgb(253,224,71);}")
        for i in range(1, 6):
            sb = QPushButton("★")
            sb.setFixedSize(22, 20)
            sb.setStyleSheet(_STAR_LIT if i <= _cur_rating else _STAR_DIM)
            sb.setCursor(Qt.PointingHandCursor)
            sb.setToolTip(f"Rate {i} star{'s' if i > 1 else ''}")
            sb.clicked.connect(
                lambda checked=False, n=i, aid=asset.id: self._set_rating(aid, n))
            rating_row.addWidget(sb)
            self._rating_btns.append(sb)
        # Clear rating button
        clr = QLabel("clear")
        clr.setStyleSheet("color:rgb(50,55,75);font-size:9px;background:transparent;"
                          "padding:0 4px;")
        clr.setCursor(Qt.PointingHandCursor)
        clr.mousePressEvent = lambda e, aid=asset.id: self._set_rating(aid, 0)
        rating_row.addWidget(clr)
        rating_row.addStretch()
        self._cl.addLayout(rating_row)
        self._cl.addSpacing(4)

        # ── Preview (video scrub / image thumb / player) ───────────────────
        self._add_preview(asset, thumb_path, strip_path, skip_player)

        self._cl.addSpacing(4)

        # ── Action buttons — 3 equal-width, theme-aware accent ─────────────
        act = QHBoxLayout()
        act.setSpacing(6)
        act.setContentsMargins(8, 4, 8, 4)

        _ACC = self._accent_rgb            # e.g. "249,115,22" from current theme
        _OK  = "52,211,153"               # green confirmation flash

        # Compute contrasting text color for accent background
        try:
            _ar, _ag, _ab = [int(x) for x in _ACC.split(",")]
            from settings import text_color_for_bg
            _ACC_TEXT = text_color_for_bg(_ar, _ag, _ab)
        except Exception:
            _ACC_TEXT = "rgb(8,8,16)"

        # Base style for secondary buttons (Explorer, Copy)
        _S_SEC = (
            "QPushButton{background:rgb(18,22,36);color:rgb(148,163,184);"
            "border:1px solid rgb(40,42,68);border-radius:4px;"
            "font-size:12px;min-height:28px;padding:0;}"
            "QPushButton:hover{background:rgb(24,28,48);"
            "color:rgb(220,228,245);border-color:rgb(70,75,110);}"
        )
        # Accent style for Open button — uses live accent colour + contrast text
        _S_ACC = (
            f"QPushButton{{background:rgb({_ACC});color:{_ACC_TEXT};"
            f"border:none;border-radius:4px;font-size:12px;"
            f"font-weight:bold;min-height:28px;padding:0;}}"
            f"QPushButton:hover{{background:rgba({_ACC},210);}}"
        )
        # Flash styles
        _S_ACC_FL = (
            f"QPushButton{{background:rgba({_ACC},30);color:rgb({_ACC});"
            f"border:1px solid rgba({_ACC},80);border-radius:4px;"
            f"font-size:12px;min-height:28px;padding:0;}}"
        )
        _S_OK_FL = (
            f"QPushButton{{background:rgba({_OK},20);color:rgb({_OK});"
            f"border:1px solid rgba({_OK},60);border-radius:4px;"
            f"font-size:12px;min-height:28px;padding:0;font-weight:bold;}}"
        )

        def _flash(btn, fl_st, fl_txt, base_st, base_txt, ms=1000):
            btn.setStyleSheet(fl_st); btn.setText(fl_txt)
            QTimer.singleShot(ms, lambda: (
                btn.setStyleSheet(base_st), btn.setText(base_txt)))

        BW, BH = 0, 28   # BW=0 means addWidget with stretch=1 each

        open_btn = QPushButton("Open")
        open_btn.setFixedHeight(BH)
        open_btn.setStyleSheet(_S_ACC)
        open_btn.setToolTip("Open in configured viewer  (double-click / Ctrl+Enter)")
        open_btn.clicked.connect(lambda checked=False: (
            self.openFileReq.emit(asset.id),
            _flash(open_btn, _S_ACC_FL, "Opening…", _S_ACC, "Open")))
        act.addWidget(open_btn, 1)

        exp_btn = QPushButton("Explorer")
        exp_btn.setFixedHeight(BH)
        exp_btn.setStyleSheet(_S_SEC)
        exp_btn.setToolTip("Show in Explorer  (Ctrl+E)")
        exp_btn.clicked.connect(lambda checked=False: (
            self.showExplorerReq.emit(asset.id),
            _flash(exp_btn, _S_OK_FL, "Opened", _S_SEC, "Explorer")))
        act.addWidget(exp_btn, 1)

        cp_btn = QPushButton("Copy Path")
        cp_btn.setFixedHeight(BH)
        cp_btn.setStyleSheet(_S_SEC)
        cp_btn.setToolTip("Copy full file path to clipboard")
        cp_btn.clicked.connect(lambda checked=False: (
            self._copy_path(asset),
            _flash(cp_btn, _S_OK_FL, "Copied!", _S_SEC, "Copy Path")))
        act.addWidget(cp_btn, 1)

        self._cl.addLayout(act)

        # ── Meta row ───────────────────────────────────────────────────────
        self._sep()
        meta = QHBoxLayout()
        meta.setContentsMargins(8, 0, 8, 0)
        type_lbl = QLabel(f" {asset.file_type.upper()} ")
        type_lbl.setObjectName("type_badge")
        type_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        type_lbl.mousePressEvent = lambda e: self.searchTagReq.emit(
            f"fmt:{asset.format}" if asset.format else asset.file_type)
        meta.addWidget(type_lbl)
        if asset.format:
            meta.addWidget(_dim_lbl(f"· {asset.format}"))
        if asset.detail_res and asset.detail_res != "—":
            meta.addWidget(_dim_lbl(f"· {asset.detail_res}"))
        if asset.duration_str and asset.duration_str != "—":
            meta.addWidget(_dim_lbl(f"· {asset.duration_str}"))
        meta.addStretch()
        self._cl.addLayout(meta)

        # ── Name ──────────────────────────────────────────────────────────
        self._section("NAME")
        name_edit = QLineEdit(asset.name)
        name_edit.setPlaceholderText("Display name…")
        name_edit.returnPressed.connect(
            lambda: self.nameChanged.emit(asset.id, name_edit.text().strip()))
        self._cl.addWidget(name_edit)

        # ── Category ──────────────────────────────────────────────────────
        self._section("CATEGORY")
        from config import get_categories
        cat_combo = QComboBox()
        for c in get_categories(self._custom_cats, self._hidden_cats)[1:]:
            cat_combo.addItem(c)
        cat_combo.setCurrentText(asset.category)
        cat_combo.currentTextChanged.connect(
            lambda v: self.catChanged.emit(asset.id, v))
        self._cl.addWidget(cat_combo)

        # ── Tags ──────────────────────────────────────────────────────────
        tag_hdr = QHBoxLayout()
        tag_hdr.setContentsMargins(0, 4, 0, 0)
        tag_hdr.addWidget(_section_lbl("TAGS"))
        tag_hdr.addStretch()
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setObjectName("btn_edit")
        self._edit_btn.setCheckable(True)
        self._edit_btn.setFixedHeight(20)
        self._edit_btn.setFixedWidth(46)
        self._edit_btn.toggled.connect(
            lambda on, a=asset: self._toggle_edit_mode(on, a))
        tag_hdr.addWidget(self._edit_btn)
        self._cl.addLayout(tag_hdr)
        self._sep()

        self._tag_widget = QWidget()
        self._tag_widget.setStyleSheet("background: transparent;")
        self._tag_flow = FlowTagLayout(self._tag_widget)
        self._rebuild_tag_pills(asset, edit=False)
        self._cl.addWidget(self._tag_widget)

        # Add-tag row (hidden until edit mode)
        self._add_tag_row = QWidget()
        add_row_l = QHBoxLayout(self._add_tag_row)
        add_row_l.setContentsMargins(0, 0, 0, 0)
        add_row_l.setSpacing(4)
        self._tag_input = QLineEdit()
        self._tag_input.setPlaceholderText("Add tags (comma-separated) ↵")
        self._tag_input.returnPressed.connect(
            lambda: self._do_add_tags(asset.id, self._tag_input.text()))
        add_btn = QPushButton("+")
        add_btn.setFixedSize(28, 28)
        add_btn.setObjectName("btn_accent")
        add_btn.clicked.connect(
            lambda checked=False: self._do_add_tags(asset.id, self._tag_input.text()))
        add_row_l.addWidget(self._tag_input)
        add_row_l.addWidget(add_btn)
        self._add_tag_row.setVisible(False)
        self._cl.addWidget(self._add_tag_row)

        # Quick-add presets (hidden until edit mode)
        self._quick_widget = QWidget()
        self._quick_widget.setStyleSheet("background: transparent;")
        q_layout = QVBoxLayout(self._quick_widget)
        q_layout.setContentsMargins(0, 2, 0, 0)
        q_layout.setSpacing(3)
        q_layout.addWidget(_section_lbl("QUICK ADD"))
        from config import PRESET_TAGS
        presets_w = QWidget(); presets_w.setStyleSheet("background: transparent;")
        presets_flow = FlowTagLayout(presets_w)
        for tag in PRESET_TAGS[:24]:
            pill = TagPill(tag, active=(tag in asset.tags), search_enabled=False)
            pill.pressed_tag.connect(
                lambda t, aid=asset.id: self._toggle_tag(aid, t))
            presets_flow.addWidget(pill)
        q_layout.addWidget(presets_w)
        self._quick_widget.setVisible(False)
        self._cl.addWidget(self._quick_widget)

        # ── File info (collapsed) ──────────────────────────────────────────
        self._section("FILE INFO")

        # ── Path row ──────────────────────────────────────────
        path_str = str(asset.path)
        path_container = QWidget()
        path_container.setStyleSheet(
            "background:rgba(255,255,255,4); border:1px solid rgb(30,30,50);"
            " border-radius:4px;")
        path_vl = QVBoxLayout(path_container)
        path_vl.setContentsMargins(8, 5, 8, 5)
        path_lbl = QLabel(("…" + path_str[-38:]) if len(path_str) > 40 else path_str)
        path_lbl.setStyleSheet("color:rgb(100,116,139);font-size:10px;background:transparent;")
        path_lbl.setToolTip(path_str)
        path_vl.addWidget(path_lbl)
        self._cl.addWidget(path_container)
        self._cl.addSpacing(6)

        # ── Info helpers ─────────────────────────────────────────
        _KST = ("color:rgb(71,85,105);font-size:10px;font-weight:bold;"
                "background:transparent;letter-spacing:0.5px;")
        _VST = "color:rgb(200,212,230);font-size:11px;background:transparent;"

        def _info_row(key, val, key_w=52):
            r = QHBoxLayout()
            r.setSpacing(6)
            kl = QLabel(key.upper()); kl.setFixedWidth(key_w)
            kl.setStyleSheet(_KST)
            vl = QLabel(str(val))
            vl.setStyleSheet(_VST)
            r.addWidget(kl); r.addWidget(vl); r.addStretch()
            return r

        # ── Basic info card ───────────────────────────────────────
        card = QWidget()
        card.setStyleSheet(
            "background:rgba(255,255,255,4); border:1px solid rgb(30,30,50);"
            " border-radius:4px;")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(8, 6, 8, 6)
        card_l.setSpacing(5)

        basic_items = [
            ("Res",    asset.detail_res or "—"),
            ("FPS",    f"{asset.fps:.3f}".rstrip('0').rstrip('.') if asset.fps else "—"),
            ("Frames", str(asset.frame_count) if asset.frame_count else "—"),
            ("Dur",    f"{asset.duration_s:.2f}s" if asset.duration_s else "—"),
            ("Size",   f"{asset.file_size_mb:.1f} MB" if asset.file_size_mb else "—"),
            ("Added",  asset.date_added or "—"),
        ]
        for j in range(0, len(basic_items), 2):
            pair = QHBoxLayout()
            pair.setSpacing(4)
            pair.addLayout(_info_row(basic_items[j][0], basic_items[j][1]))
            if j + 1 < len(basic_items):
                pair.addLayout(_info_row(basic_items[j+1][0], basic_items[j+1][1]))
            card_l.addLayout(pair)
        self._cl.addWidget(card)

        # ── Technical metadata card (codec / depth / color / audio) ───
        _has_tech = any([
            getattr(asset, 'codec', None),
            getattr(asset, 'bit_depth', None),
            getattr(asset, 'color_space', None),
            getattr(asset, 'audio_codec', None),
        ])
        if _has_tech:
            self._cl.addSpacing(4)
            tech_card = QWidget()
            tech_card.setStyleSheet(
                "background:rgba(96,165,250,6); border:1px solid rgba(96,165,250,30);"
                " border-radius:4px;")
            tech_vl = QVBoxLayout(tech_card)
            tech_vl.setContentsMargins(8, 6, 8, 6)
            tech_vl.setSpacing(5)

            _codec = getattr(asset, 'codec', None)
            _bd    = getattr(asset, 'bit_depth', None)
            _cs    = getattr(asset, 'color_space', None)
            _ac    = getattr(asset, 'audio_codec', None)
            _ach   = getattr(asset, 'audio_channels', None)
            _rend  = getattr(asset, 'renderer', None)
            _comp  = getattr(asset, 'compression', None)

            tech_items = []
            if _codec: tech_items.append(("Codec", _codec.upper()))
            if _bd:    tech_items.append(("Depth", f"{_bd}-bit"))
            if _cs:    tech_items.append(("Color", _cs))
            if _comp:  tech_items.append(("Comp", _comp.upper()))
            if _rend:  tech_items.append(("Engine", _rend))
            if _ac:
                _ch_str = {1:"Mono",2:"Stereo",6:"5.1",8:"7.1"}.get(
                    _ach, f"{_ach}ch" if _ach else "")
                tech_items.append(("Audio", f"{_ac.upper()} {_ch_str}".strip()))

            for j in range(0, len(tech_items), 2):
                pair = QHBoxLayout()
                pair.setSpacing(4)
                pair.addLayout(_info_row(tech_items[j][0], tech_items[j][1]))
                if j + 1 < len(tech_items):
                    pair.addLayout(_info_row(tech_items[j+1][0], tech_items[j+1][1]))
                tech_vl.addLayout(pair)
            self._cl.addWidget(tech_card)

        # ── Notes (debounced) ─────────────────────────────────────────────
        self._section("NOTES")
        notes_edit = QTextEdit()
        notes_edit.setPlainText(asset.notes or "")
        notes_edit.setFixedHeight(64)
        notes_edit.setPlaceholderText("Notes, source, license…")
        def _on_notes_changed():
            self._pending_notes = (asset.id, notes_edit.toPlainText())
            self._notes_timer.start()  # restart debounce
        notes_edit.textChanged.connect(_on_notes_changed)
        self._cl.addWidget(notes_edit)

        # ── Collections ───────────────────────────────────────────────────
        colls = self.lib.collections_for_asset(asset.id)
        if colls:
            self._section("IN COLLECTIONS")
            for cname in colls:
                cw = QWidget(); cw.setStyleSheet("background: transparent;")
                cl = QHBoxLayout(cw); cl.setContentsMargins(0, 0, 0, 0)
                lbl = _dim_lbl(f"● {cname}")
                search_b = QPushButton("›")
                search_b.setFixedSize(20, 20)
                search_b.setStyleSheet(
                    "QPushButton{background:transparent;border:none;font-size:11px;}"
                    f"QPushButton:hover{{color:rgb({self._accent_rgb});}}")
                search_b.clicked.connect(
                    lambda checked=False, n=cname: self.searchCatReq.emit(f"coll:{n}"))
                cl.addWidget(lbl); cl.addStretch(); cl.addWidget(search_b)
                self._cl.addWidget(cw)

        # ── Versions ──────────────────────────────────────────────────────
        versions = self.lib.get_versions(asset.id)
        if len(versions) > 1:
            self._section("VERSIONS")
            _pid = asset.id if not asset.version_of else asset.version_of

            # Dropdown selector
            ver_row = QWidget()
            ver_row.setStyleSheet("background:transparent;")
            vrl = QHBoxLayout(ver_row)
            vrl.setContentsMargins(0, 0, 0, 0)
            vrl.setSpacing(4)

            ver_combo = QComboBox()
            ver_combo.setFixedHeight(24)
            ver_combo.setStyleSheet(
                f"QComboBox{{background:rgb(14,16,26);color:rgb(200,210,230);"
                f"border:1px solid rgb(35,38,60);border-radius:3px;"
                f"padding:2px 8px;font-size:11px;}}"
                f"QComboBox:hover{{border-color:rgba({self._accent_rgb},80);}}"
                f"QComboBox::drop-down{{border:none;width:18px;}}"
                f"QComboBox QAbstractItemView{{background:rgb(12,12,22);"
                f"color:rgb(200,210,230);selection-background-color:rgba({self._accent_rgb},40);"
                f"border:1px solid rgb(35,38,60);}}")
            _current_idx = 0
            n_total = len(versions)
            for i, va in enumerate(versions):
                is_cur = (va.id == asset.id)
                marker = " ◀" if is_cur else ""
                label = f"V{i+1}  ·  {va.name[:28]}  ({va.format} {va.display_res}){marker}"
                ver_combo.addItem(label, va.id)
                if is_cur:
                    _current_idx = i
            ver_combo.setCurrentIndex(_current_idx)

            def _on_version_changed(idx):
                vid = ver_combo.itemData(idx)
                if vid and vid != asset.id:
                    self.switchVersionReq.emit(vid, _pid)
            ver_combo.currentIndexChanged.connect(_on_version_changed)
            vrl.addWidget(ver_combo, 1)

            # Edit Versions button
            edit_btn = QPushButton("Edit")
            edit_btn.setFixedSize(40, 24)
            edit_btn.setStyleSheet(
                f"QPushButton{{background:rgba({self._accent_rgb},10);"
                f"color:rgb({self._accent_rgb});border:1px solid rgba({self._accent_rgb},30);"
                "border-radius:3px;font-size:9px;padding:0 6px;}"
                f"QPushButton:hover{{background:rgba({self._accent_rgb},22);}}")
            edit_btn.clicked.connect(
                lambda checked=False, pid=_pid, vs=versions, cur=asset.id:
                    self._show_edit_versions_menu(edit_btn, pid, vs, cur))
            vrl.addWidget(edit_btn)

            self._cl.addWidget(ver_row)

        self._cl.addStretch()

    def refresh_tags(self, asset: Asset):
        """Refresh only tag pills — preserves edit mode and scroll position."""
        self._current_asset = asset
        # Save scroll position
        scroll_bar = self._scroll.verticalScrollBar()
        saved_scroll = scroll_bar.value()
        self._rebuild_tag_pills(asset, edit=self._edit_mode)
        self._refresh_quick_presets(asset)
        # Restore scroll position
        from PySide2.QtCore import QTimer
        QTimer.singleShot(0, lambda: scroll_bar.setValue(saved_scroll))

    def _refresh_quick_presets(self, asset: Asset):
        """Update quick-add preset pill active states IN-PLACE (no destroy/recreate)."""
        if not hasattr(self, '_quick_widget'):
            return
        q_layout = self._quick_widget.layout()
        if not q_layout or q_layout.count() < 2:
            return
        container = q_layout.itemAt(1).widget()
        if not container or not container.layout():
            return
        flow = container.layout()
        for i in range(flow.count()):
            item = flow.itemAt(i)
            pill = item.widget() if item else None
            if pill and hasattr(pill, 'tag_name') and hasattr(pill, 'setActive'):
                pill.setActive(pill.tag_name in asset.tags)

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_preview(self, asset: Asset, thumb_path: Optional[Path],
                     strip_path: Optional[Path],
                     skip_player: bool = False):
        """
        Detail panel preview — video gets embedded player, images get thumbnail.
        skip_player=True: show thumbnail + hint instead of VLC (during import).
        """
        is_video = asset.file_type in ("video", "sequence")

        if is_video and not skip_player:
            from preview import get_proxy_path
            proxy = get_proxy_path(asset.id)

            if proxy.exists():
                # Proxy ready — play it via VLC (lightweight mp4)
                self._try_embedded_player(str(proxy), asset)
                return
            else:
                # No proxy yet — show thumbnail + "generating" message
                # NEVER load original ProRes/EXR into VLC
                skip_player = True  # fall through to thumbnail display below

        if is_video and skip_player:
            hint = QLabel("  ⟳  Generating preview — playback available when ready")
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "color: rgba(96,165,250,180); font-size: 10px;"
                " background: rgba(96,165,250,8); border-radius: 3px;"
                " padding: 4px 8px;")
            self._cl.addWidget(hint)

        has_thumb = thumb_path and Path(str(thumb_path)).exists()
        if has_thumb:
            container = QWidget()
            container.setStyleSheet("background: rgb(9,9,16); border-radius: 4px;")
            vl = QVBoxLayout(container)
            vl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)

            # During import: only use small cached thumbnail, never load original
            pix = None
            if not skip_player:
                # Try to load the original asset file for best quality
                src_path = Path(asset.path)
                _LDR = {".png",".jpg",".jpeg",".tga",".bmp",".tiff",".tif",".webp"}
                if src_path.exists() and src_path.suffix.lower() in _LDR:
                    pix = QPixmap(str(src_path))
                    if pix.isNull():
                        pix = None
            if pix is None:
                pix = QPixmap(str(thumb_path))

            if not pix.isNull():
                panel_w = max(self.width() - 16, 280)
                _tf = Qt.FastTransformation if skip_player else Qt.SmoothTransformation
                scaled = pix.scaledToWidth(panel_w, _tf)
                if scaled.height() > 420:
                    scaled = pix.scaled(panel_w, 420,
                                        Qt.KeepAspectRatio, _tf)
                lbl.setPixmap(scaled)
                container.setFixedHeight(scaled.height())
            else:
                container.setFixedHeight(160)

            vl.addWidget(lbl)
            self._cl.addWidget(container)

    def _try_embedded_player(self, path: str, asset: 'Asset' = None):
        """
        Embedded video player using python-vlc (preferred) → Qt Multimedia.
        Plays the PROXY mp4 if available, falls back to original path.
        python-vlc: pip install python-vlc  (requires VLC installed on system)
        """
        container = QWidget()
        container.setObjectName("video_container")
        # Height = panel width * 9/16 + 36px for controls (16:9 aspect ratio)
        panel_w = max(self.width() - 16, 240)
        video_h = int(panel_w * 9 / 16)
        container.setMinimumHeight(video_h + 36)
        container.setMaximumHeight(video_h + 50)
        vl = QVBoxLayout(container)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        self._cl.addWidget(container)

        # ── python-vlc (best — works with any codec via libvlc) ────────────
        try:
            import vlc as _vlc

            frame = QWidget()
            frame.setStyleSheet("background: black;")
            frame.setMinimumHeight(video_h)
            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            vl.addWidget(frame)

            # Instant loading label so the UI doesn't look frozen
            _loading = QLabel("Loading player…", frame)
            _loading.setStyleSheet(
                "color:rgba(180,180,200,120);font-size:11px;background:transparent;")
            _loading.setAlignment(Qt.AlignCenter)
            _loading.setGeometry(0, 0, frame.width() or 240, video_h)
            _loading.show()

            # ── Frame info HUD overlay (toggle with 'I' key) ────────────
            # Parent to container (NOT frame) because VLC renders natively
            # on frame's surface and covers any Qt children.
            _hud_lines = []
            if asset:
                if asset.detail_res and asset.detail_res != "—":
                    _hud_lines.append(asset.detail_res)
                if getattr(asset, 'codec', None):
                    _hud_lines.append(asset.codec.upper())
                if asset.fps:
                    _hud_lines.append(f"{asset.fps:.2f} fps")
                if getattr(asset, 'bit_depth', None):
                    _hud_lines.append(f"{asset.bit_depth}-bit")
                if getattr(asset, 'color_space', None):
                    _hud_lines.append(asset.color_space)
                if getattr(asset, 'compression', None):
                    _hud_lines.append(asset.compression.upper())
                if getattr(asset, 'renderer', None):
                    _hud_lines.append(asset.renderer)
                if asset.duration_s:
                    _hud_lines.append(f"{asset.duration_s:.1f}s")
                if asset.file_size_mb:
                    _hud_lines.append(f"{asset.file_size_mb:.1f} MB")
            _hud_text = "   ·   ".join(_hud_lines) if _hud_lines else "No metadata"
            _hud = QLabel(_hud_text, container)
            _hud.setStyleSheet(
                "color:rgba(230,235,250,220);font-size:11px;font-weight:bold;"
                "background:rgba(0,0,0,170);border-radius:4px;padding:4px 10px;")
            _hud.adjustSize()
            _hud.move(6, 6)
            _hud.setVisible(False)
            _hud.raise_()
            container._hud = _hud  # ref for keyboard/button toggle

            ctrl, pb, pos_lbl, dur_lbl, seek, mb, pf, nf, gs, lb, vol, fs_btn, info_btn = self._ctrl_row()
            vl.addLayout(ctrl)

            def _start_vlc():
                try:
                    import sys as _sys_vlc, os as _os_vlc
                    # On Windows: python-vlc finds libvlc.dll via PATH or registry.
                    # Add the standard VLC install paths proactively so it works
                    # even when VLC is not on the system PATH.
                    if _sys_vlc.platform == "win32":
                        # Build candidate list: settings path first, then defaults
                        _vlc_candidates = []
                        try:
                            from settings import Settings as _S
                            _sp = _S.load().vlc_path.strip()
                            if _sp: _vlc_candidates.append(_sp)
                        except Exception:
                            pass
                        _vlc_candidates += [
                            r"C:\Program Files\VideoLAN\VLC",
                            r"C:\Program Files (x86)\VideoLAN\VLC",
                        ]
                        for _p in _vlc_candidates:
                            if _os_vlc.path.isdir(_p) and _p not in _os_vlc.environ.get("PATH", ""):
                                _os_vlc.environ["PATH"] = _p + ";" + _os_vlc.environ.get("PATH", "")
                                break
                        _vlc_args = [
                            "--directx-use-sysmem",
                            "--aout=directsound",
                            "--no-video-title-show",
                            "--quiet",               # suppress hw accel warnings in console
                        ]
                        # GPU accel: ON = let VLC pick best hw decoder (DXVA2/D3D11VA)
                        #            OFF = force software decoding
                        try:
                            from settings import Settings as _SVlc
                            if _SVlc.load().gpu_acceleration:
                                _vlc_args.append("--avcodec-hw=any")
                            else:
                                _vlc_args.append("--avcodec-hw=none")
                        except Exception:
                            _vlc_args.append("--avcodec-hw=none")
                        inst = _vlc.Instance(*_vlc_args)
                    else:
                        _vlc_args_linux = [
                            "--no-xlib",
                            "--no-video-title-show",
                            "--quiet",
                        ]
                        try:
                            from settings import Settings as _SVlc
                            if _SVlc.load().gpu_acceleration:
                                _vlc_args_linux.append("--avcodec-hw=any")
                            else:
                                _vlc_args_linux.append("--avcodec-hw=none")
                        except Exception:
                            _vlc_args_linux.append("--avcodec-hw=none")
                        inst = _vlc.Instance(*_vlc_args_linux)
                    if inst is None:
                        raise RuntimeError(
                            "libvlc not found — install VLC from https://videolan.org "
                            "then restart the app")
                    player = inst.media_player_new()
                    container._vlc_inst   = inst
                    container._vlc_player = player
                    # Mark content widget so cleanup knows to stop VLC
                    if self._content:
                        self._content._has_player = True

                    # Embed into Qt widget
                    import sys as _sys
                    wid = int(frame.winId())
                    if _sys.platform == "win32":
                        player.set_hwnd(wid)
                    elif _sys.platform == "darwin":
                        player.set_nsobject(wid)
                    else:
                        player.set_xwindow(wid)

                    media = inst.media_new(path)
                    player.set_media(media)
                    player.audio_set_volume(30)
                    # Load first frame then pause — no autoplay
                    # Use VLC event to pause as soon as playback starts
                    _em = player.event_manager()
                    _pause_done = [False]
                    def _on_playing(event):
                        if not _pause_done[0]:
                            _pause_done[0] = True
                            player.set_pause(1)
                    try:
                        _em.event_attach(_vlc.EventType.MediaPlayerPlaying, _on_playing)
                    except Exception:
                        pass
                    player.play()
                    pb._set_state(False)

                    # ── Time display (frames / timecode, toggleable) ───
                    try:
                        from settings import Settings as _Sv
                        _default_mode = _Sv.load().time_display_mode
                    except Exception:
                        _default_mode = "frames"
                    _mode = [_default_mode]   # mutable for closure
                    _fps  = (asset.fps if asset else None) or 24.0

                    def _fmt_pos(ms):
                        if _mode[0] == "frames":
                            return self._fmt_fr(ms, _fps)
                        return self._fmt_tc(ms)
                    def _fmt_dur(ms):
                        if _mode[0] == "frames":
                            return self._fmt_fr(ms, _fps)
                        return self._fmt_tc(ms)

                    def _toggle_mode(e=None):
                        _mode[0] = "timecode" if _mode[0] == "frames" else "frames"
                        dur = player.get_length()
                        pos = player.get_time()
                        if dur > 0:
                            dur_lbl.setText(_fmt_dur(dur))
                            pos_lbl.setText(_fmt_pos(pos))
                    pos_lbl.mousePressEvent = _toggle_mode
                    dur_lbl.mousePressEvent = _toggle_mode

                    # Position ticker
                    _t = QTimer(container)
                    _t.setInterval(150)
                    def _tick():
                        if not _alive[0]: return
                        try:
                            dur = player.get_length()  # ms
                            pos = player.get_time()    # ms
                            if dur > 0:
                                dur_lbl.setText(_fmt_dur(dur))
                                pos_lbl.setText(_fmt_pos(pos))
                        except RuntimeError:
                            _alive[0] = False; _t.stop()
                        except Exception:
                            pass
                    _t.timeout.connect(_tick)
                    _t.start()
                    container._vlc_timer = _t

                    # ── Alive guard: stops timer + player when Qt deletes container
                    _alive = [True]
                    def _on_destroyed():
                        _alive[0] = False
                        try: _t.stop()
                        except Exception: pass
                        try: player.stop()
                        except Exception: pass
                    container.destroyed.connect(_on_destroyed)

                    # Controls
                    def _toggle_play(c=False):
                        st = player.get_state()
                        if st == _vlc.State.Playing:
                            player.pause()
                            pb._set_state(False)
                        else:
                            if st in (_vlc.State.Stopped, _vlc.State.Ended):
                                player.stop()
                            player.play()
                            pb._set_state(True)
                    pb.clicked.connect(_toggle_play)

                    # ── Seek slider (VLC) ──────────────────────────────
                    _seeking = [False]
                    _orig_press   = seek.mousePressEvent
                    _orig_release = seek.mouseReleaseEvent
                    def _on_seek_press(e, _op=_orig_press):
                        _seeking[0] = True; _op(e)
                    def _on_seek_release(e, _or=_orig_release):
                        _seeking[0] = False; _or(e)
                        dur = player.get_length()
                        if dur > 0:
                            player.set_time(int(seek.value() / 1000 * dur))
                    seek.mousePressEvent   = _on_seek_press
                    seek.mouseReleaseEvent = _on_seek_release

                    def _tick_seek():
                        if not _alive[0]: return
                        if _seeking[0]: return
                        try:
                            dur = player.get_length()
                            pos = player.get_time()
                            if dur > 0:
                                seek.setValue(int(pos / dur * 1000))
                        except RuntimeError:
                            _alive[0] = False; _t.stop()
                        except Exception: pass
                    _t.timeout.connect(_tick_seek)

                    # ── Mute (VLC) ─────────────────────────────────────
                    def _toggle_mute(checked):
                        player.audio_set_mute(checked)
                        mb._set_state(checked)
                    mb.toggled.connect(_toggle_mute)

                    # Volume
                    player.audio_set_volume(vol.value())
                    vol.valueChanged.connect(lambda v: player.audio_set_volume(v))

                    # ── Frame step ─────────────────────────────────────
                    _asset_fps = (asset.fps if asset else None) or 24.0
                    _step_ms   = max(1, int(round(1000.0 / _asset_fps)))  # exact 1 frame

                    def _force_update():
                        """Force tick to update labels after frame step."""
                        if not _alive[0]: return
                        try:
                            dur = player.get_length()
                            pos = player.get_time()
                            if dur > 0:
                                seek.setValue(int(pos / dur * 1000))
                                dur_lbl.setText(_fmt_dur(dur))
                                pos_lbl.setText(_fmt_pos(pos))
                        except RuntimeError:
                            _alive[0] = False; _t.stop()
                        except Exception: pass

                    def _ensure_paused_then(fn):
                        st = player.get_state()
                        if st == _vlc.State.Playing:
                            player.pause()
                            pb._set_state(False)
                            QTimer.singleShot(60, fn)
                        else:
                            fn()

                    def _do_next():
                        dur = player.get_length()
                        t   = player.get_time() + _step_ms
                        if dur > 0:
                            player.set_time(min(t, dur - 1))
                        QTimer.singleShot(80, _force_update)

                    def _do_prev():
                        t = max(0, player.get_time() - _step_ms)
                        player.set_time(t)
                        QTimer.singleShot(80, _force_update)

                    nf.clicked.connect(lambda c=False: _ensure_paused_then(_do_next))
                    pf.clicked.connect(lambda c=False: _ensure_paused_then(_do_prev))

                    # ── Go to start ────────────────────────────────────
                    def _goto_start(c=False):
                        if not _alive[0]: return
                        was_playing = player.get_state() == _vlc.State.Playing
                        player.set_time(0)
                        seek.setValue(0)
                        if not was_playing:
                            # Stay paused — re-pause after VLC settles
                            try: player.pause()
                            except Exception: pass
                            def _ensure_paused():
                                if not _alive[0]: return
                                try:
                                    if player.get_state() == _vlc.State.Playing:
                                        player.pause()
                                except RuntimeError: pass
                                _force_update()
                            QTimer.singleShot(80, _ensure_paused)
                        QTimer.singleShot(30, _force_update)
                    gs.clicked.connect(_goto_start)

                    # ── Loop toggle ────────────────────────────────────
                    _looping = [False]
                    def _on_loop(checked):
                        _looping[0] = checked
                    lb.toggled.connect(_on_loop)

                    # ── End-of-video: pause at frame 0 (or loop) ───────
                    def _check_ended():
                        if not _alive[0]: return
                        try:
                            st = player.get_state()
                            if st in (_vlc.State.Ended, _vlc.State.Stopped):
                                if _looping[0]:
                                    player.stop()
                                    player.play()
                                    pb._set_state(True)
                                else:
                                    player.stop()
                                    player.play()
                                    pb._set_state(False)
                                    def _reset_ui():
                                        if not _alive[0]: return
                                        try:
                                            player.pause()
                                            seek.setValue(0)
                                            _force_update()
                                        except RuntimeError: pass
                                    QTimer.singleShot(120, _reset_ui)
                        except RuntimeError:
                            _alive[0] = False; _t.stop()
                        except Exception: pass
                    _t.timeout.connect(_check_ended)

                    # ── Seek click anywhere on slider ──────────────────
                    def _seek_click(e):
                        if not _alive[0]: return
                        if e.button() == Qt.LeftButton:
                            ratio = e.x() / max(seek.width(), 1)
                            dur   = player.get_length()
                            if dur > 0:
                                player.set_time(int(ratio * dur))
                                seek.setValue(int(ratio * 1000))
                                QTimer.singleShot(60, _force_update)
                    seek.mousePressEvent = _seek_click

                    # ── Fullscreen toggle ───────────────────────────────
                    _fs_state = {"win": None, "parent": None, "idx": 0}

                    def _toggle_fs(checked=False):
                        if _fs_state["win"] is not None:
                            # ── EXIT fullscreen ──────────────────────────
                            # Reparent container back to detail panel
                            fs_w = _fs_state["win"]
                            fs_w.layout().removeWidget(container)
                            parent_layout = _fs_state["parent"]
                            idx = _fs_state["idx"]
                            parent_layout.insertWidget(idx, container)
                            container.show()
                            fs_w.close()
                            fs_w.deleteLater()
                            _fs_state["win"] = None
                            fs_btn._set_state(False)
                            return

                        # ── ENTER fullscreen ─────────────────────────────
                        # Remember where the container lives
                        parent_layout = container.parentWidget().layout()
                        idx = parent_layout.indexOf(container)
                        _fs_state["parent"] = parent_layout
                        _fs_state["idx"] = idx

                        # Create fullscreen window
                        fs_w = QWidget()
                        fs_w.setWindowFlags(
                            Qt.Window | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint)
                        fs_w.setStyleSheet("background: black;")
                        fs_layout = QVBoxLayout(fs_w)
                        fs_layout.setContentsMargins(0, 0, 0, 0)
                        fs_layout.setSpacing(0)

                        # Move the EXISTING container (VLC keeps rendering)
                        parent_layout.removeWidget(container)
                        fs_layout.addWidget(container)
                        container.setMinimumHeight(0)
                        container.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
                        container.show()

                        # Escape / F / double-click exits
                        def _fs_key(e):
                            if e.key() in (Qt.Key_Escape, Qt.Key_F):
                                _toggle_fs()
                            elif e.key() == Qt.Key_Space:
                                _toggle_play()
                        fs_w.keyPressEvent = _fs_key

                        fs_w.showFullScreen()
                        _fs_state["win"] = fs_w
                        fs_btn._set_state(True)

                    fs_btn.clicked.connect(_toggle_fs)

                    # ── Info HUD toggle ─────────────────────────────────
                    def _toggle_hud(checked=False):
                        hud = getattr(container, '_hud', None)
                        if hud:
                            hud.setVisible(not hud.isVisible())
                            hud.raise_()
                    info_btn.clicked.connect(_toggle_hud)

                except Exception as e:
                    from logger import log_error
                    log_error(f"[VLC player] {e}")

            QTimer.singleShot(120, _start_vlc)
            return

        except ImportError:
            pass

        # ── Qt Multimedia fallback (MP4/H264 only) ─────────────────────────
        try:
            from PySide2.QtMultimedia        import QMediaPlayer, QMediaContent
            from PySide2.QtMultimediaWidgets import QVideoWidget
            from PySide2.QtCore              import QUrl

            vw = QVideoWidget()
            vw.setMinimumHeight(video_h)
            vw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            player = QMediaPlayer(container)
            player.setVideoOutput(vw)
            player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            container._qt_player = player
            if self._content:
                self._content._has_player = True

            ctrl, pb, pos_lbl, dur_lbl, seek, mb, pf, nf, gs, lb, vol, fs_btn, info_btn = self._ctrl_row()
            vl.addWidget(vw)
            vl.addLayout(ctrl)

            def _qt_play(c=False):
                if player.state() == QMediaPlayer.PlayingState:
                    player.pause(); pb._set_state(False)
                else:
                    player.play(); pb._set_state(True)
            pb.clicked.connect(_qt_play)
            try:
                from settings import Settings as _Sq
                _qt_mode = [_Sq.load().time_display_mode]
            except Exception:
                _qt_mode = ["frames"]
            _qt_fps = (asset.fps if asset else None) or 24.0
            _qt_dur = [0]

            def _qt_fmt_pos(ms):
                if _qt_mode[0] == "frames": return self._fmt_fr(ms, _qt_fps)
                return self._fmt_tc(ms)
            def _qt_fmt_dur(ms):
                if _qt_mode[0] == "frames": return self._fmt_fr(ms, _qt_fps)
                return self._fmt_tc(ms)

            def _qt_toggle_mode(e=None):
                _qt_mode[0] = "timecode" if _qt_mode[0] == "frames" else "frames"
                dur_lbl.setText(_qt_fmt_dur(_qt_dur[0]))
                pos_lbl.setText(_qt_fmt_pos(player.position()))
            pos_lbl.mousePressEvent = _qt_toggle_mode
            dur_lbl.mousePressEvent = _qt_toggle_mode

            def _qt_dur_changed(ms):
                _qt_dur[0] = ms
                dur_lbl.setText(_qt_fmt_dur(ms))
                seek.setRange(0, max(ms, 1))
            player.durationChanged.connect(_qt_dur_changed)
            def _qt_pos_changed(ms):
                pos_lbl.setText(_qt_fmt_pos(ms))
                if not seek.isSliderDown():
                    seek.setValue(ms)
            player.positionChanged.connect(_qt_pos_changed)
            seek.sliderMoved.connect(lambda ms: player.setPosition(ms))
            mb.toggled.connect(lambda checked: (
                player.setMuted(checked),
                mb._set_state(checked)))
            player.setVolume(vol.value())
            vol.valueChanged.connect(lambda v: player.setVolume(v))
            _qt_fps    = (asset.fps if asset else None) or 24.0
            _qt_frms   = max(1, int(round(1000.0 / _qt_fps)))
            _qt_looping = [False]

            def _qt_force_update():
                pos_lbl.setText(_qt_fmt_pos(player.position()))
                dur_lbl.setText(_qt_fmt_dur(_qt_dur[0]))
                if not seek.isSliderDown():
                    seek.setValue(player.position())

            # Frame step
            nf.clicked.connect(lambda c=False: (
                player.pause(), pb._set_state(False),
                player.setPosition(min(player.position() + _qt_frms, player.duration())),
                QTimer.singleShot(40, _qt_force_update)))
            pf.clicked.connect(lambda c=False: (
                player.pause(), pb._set_state(False),
                player.setPosition(max(0, player.position() - _qt_frms)),
                QTimer.singleShot(40, _qt_force_update)))

            # Go to start
            gs.clicked.connect(lambda c=False: (
                player.setPosition(0), seek.setValue(0),
                QTimer.singleShot(40, _qt_force_update)))

            # Loop
            lb.toggled.connect(lambda checked: _qt_looping.__setitem__(0, checked))

            # End of media — pause at 0 or loop
            from PySide2.QtMultimedia import QMediaPlayer as _QMP
            def _qt_state_changed(state):
                if state == _QMP.StoppedState and player.mediaStatus() == _QMP.EndOfMedia:
                    if _qt_looping[0]:
                        player.setPosition(0); player.play(); pb._set_state(True)
                    else:
                        player.setPosition(0); seek.setValue(0)
                        pb._set_state(False)
                        QTimer.singleShot(40, _qt_force_update)
            player.stateChanged.connect(_qt_state_changed)

            # Seek click
            def _qt_seek_click(e):
                if e.button() == Qt.LeftButton:
                    ratio = e.x() / max(seek.width(), 1)
                    dur   = player.duration()
                    if dur > 0:
                        player.setPosition(int(ratio * dur))
                        QTimer.singleShot(40, _qt_force_update)
            seek.mousePressEvent = _qt_seek_click

            # Fullscreen toggle
            _qt_fs = [False]
            def _qt_toggle_fs(checked=False):
                _qt_fs[0] = not _qt_fs[0]
                vw.setFullScreen(_qt_fs[0])
                fs_btn._set_state(_qt_fs[0])
            fs_btn.clicked.connect(_qt_toggle_fs)
            # Escape exits fullscreen for QVideoWidget
            orig_key = vw.keyPressEvent
            def _vw_key(e):
                if e.key() == Qt.Key_Escape and vw.isFullScreen():
                    _qt_toggle_fs()
                elif e.key() == Qt.Key_F:
                    _qt_toggle_fs()
                elif orig_key:
                    orig_key(e)
            vw.keyPressEvent = _vw_key

            player.setVolume(30)
            # Load then pause — no autoplay
            pb._set_state(False)
            def _qt_pause_after_load():
                player.pause()
            QTimer.singleShot(200, _qt_pause_after_load)
            player.play()

            return

        except Exception as e:
            from logger import log_error
            log_error(f"[QtPlayer] {e}")

        # ── Nothing available ──────────────────────────────────────────────
        tip = QLabel(
            "No player available\n\n"
            "Install VLC for embedded playback:\n"
            "  pip install python-vlc\n"
            "  (VLC must be installed on your system)")
        tip.setAlignment(Qt.AlignCenter)
        tip.setWordWrap(True)
        tip.setStyleSheet("color:rgb(50,60,80);font-size:11px;background:transparent;")
        vl.addWidget(tip)

    def _ctrl_row(self):
        """
        Playback control row.
        Returns: outer, pb, pos_lbl, dur_lbl, seek, mb, pf, nf, gs, lb
          gs=go-to-start  lb=loop-toggle

        Layout: [|<] [<] [>] [>]  ·  f288 / f3600  ·  [L] [M]
        """
        from PySide2.QtWidgets import QSlider
        from PySide2.QtCore    import Qt as _Qt

        outer = QVBoxLayout()
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Seek slider ───────────────────────────────────────────────────
        _A = self._accent_rgb  # e.g. "249,115,22"
        seek = QSlider(_Qt.Horizontal)
        seek.setRange(0, 1000)
        seek.setValue(0)
        seek.setFixedHeight(8)
        seek.setCursor(_Qt.PointingHandCursor)
        seek.setStyleSheet(
            "QSlider::groove:horizontal{"
            "background:rgb(24,26,42);height:4px;border-radius:2px;margin:0;}"
            "QSlider::sub-page:horizontal{"
            f"background:rgb({_A});border-radius:2px;}}"
            "QSlider::handle:horizontal{"
            f"background:rgb({_A});width:12px;height:12px;"
            "border-radius:6px;margin:-4px 0;}"
        )
        outer.addWidget(seek)

        # ── Styles ────────────────────────────────────────────────────────
        _BTN = (
            "QPushButton{background:rgb(16,18,30);color:rgb(200,210,230);"
            "border:1px solid rgb(35,38,60);border-radius:4px;"
            "font-size:12px;padding:0;}"
            "QPushButton:hover{background:rgb(22,26,42);"
            f"color:rgb({_A});border-color:rgba({_A},80);}}"
            f"QPushButton:checked{{background:rgba({_A},18);"
            f"color:rgb({_A});border-color:rgba({_A},80);}}"
        )
        _LBL = (
            "color:rgb(130,145,175);font-size:11px;"
            "background:transparent;padding:0 2px;"
        )

        ctrl = QHBoxLayout()
        ctrl.setSpacing(3)
        ctrl.setContentsMargins(4, 3, 4, 3)

        from icons import icon_path, icon_exists
        from PySide2.QtGui import QIcon as _QIcon
        from PySide2.QtCore import QSize as _QSize
        _ISZ = _QSize(16, 16)

        def _ic(name):
            if icon_exists(name):
                return _QIcon(icon_path(name))
            return None

        def _btn(text, tip, ic=None, w=26, h=26, checkable=False):
            b = QPushButton()
            if ic:
                b.setIcon(ic); b.setIconSize(_ISZ)
            else:
                b.setText(text)
            b.setFixedSize(w, h)
            b.setToolTip(tip)
            b.setStyleSheet(_BTN)
            b.setCheckable(checkable)
            return b

        # Exact filenames: skip_prev play pause prev next loop
        #   volume volume_off fullscreen info
        _IC_SKIP  = _ic("skip_prev.png")
        _IC_PREV  = _ic("prev.png")
        _IC_PLAY  = _ic("play.png")
        _IC_PAUSE = _ic("pause.png")
        _IC_NEXT  = _ic("next.png")
        _IC_LOOP  = _ic("loop.png")
        _IC_VOL   = _ic("volume.png")
        _IC_MUTE  = _ic("volume_off.png")
        _IC_FS    = _ic("fullscreen.png")
        _IC_FSX   = _ic("fullscreen_exit.png")
        _IC_INFO  = _ic("info.png")

        goto_start = _btn("|<", "Go to start",         _IC_SKIP)
        prev_fr    = _btn("<",  "Previous frame (,)",   _IC_PREV)
        play_btn   = _btn(">",  "Play / Pause (Space)", _IC_PLAY, w=30)
        next_fr    = _btn(">",  "Next frame (.)",       _IC_NEXT)
        loop_btn   = _btn("L",  "Loop playback",        _IC_LOOP, checkable=True)
        mute_btn   = _btn("M",  "Mute / Unmute",        _IC_VOL, checkable=True)
        fs_btn     = _btn("[ ]","Fullscreen (F)",        _IC_FS, w=30)
        info_btn   = _btn("i",  "Info overlay (I)",      _IC_INFO, checkable=True)

        def _swap(btn, ic, fallback):
            if ic:
                btn.setIcon(ic); btn.setIconSize(_ISZ); btn.setText("")
            else:
                btn.setIcon(_QIcon()); btn.setText(fallback)

        play_btn._set_state = lambda on: _swap(play_btn, _IC_PAUSE if on else _IC_PLAY, "||" if on else ">")
        mute_btn._set_state = lambda on: _swap(mute_btn, _IC_MUTE if on else _IC_VOL, "X" if on else "M")
        fs_btn._set_state   = lambda on: _swap(fs_btn, _IC_FSX if on else _IC_FS, "x" if on else "[ ]")

        # Center widget: pos / dur — both white, no gap, centered
        time_w = QWidget()
        time_w.setStyleSheet("background:transparent;")
        time_l = QHBoxLayout(time_w)
        time_l.setContentsMargins(0, 0, 0, 0)
        time_l.setSpacing(0)
        _LBL_W = (
            "color:rgb(220,228,240);font-size:11px;"
            "background:transparent;padding:0 1px;"
        )
        pos_lbl = QLabel("f 0")
        pos_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        pos_lbl.setStyleSheet(_LBL_W + "min-width:48px;")
        pos_lbl.setCursor(Qt.PointingHandCursor)
        pos_lbl.setToolTip("Click to toggle frames / timecode")
        sep_lbl = QLabel(" / ")
        sep_lbl.setStyleSheet("color:rgb(80,95,130);font-size:11px;"
                              "background:transparent;padding:0;")
        dur_lbl = QLabel("f 0")
        dur_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        dur_lbl.setStyleSheet(_LBL_W + "min-width:48px;")
        dur_lbl.setCursor(Qt.PointingHandCursor)
        time_l.addWidget(pos_lbl)
        time_l.addWidget(sep_lbl)
        time_l.addWidget(dur_lbl)

        # Volume slider
        vol_slider = QSlider(_Qt.Horizontal)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(40)
        vol_slider.setFixedWidth(60)
        vol_slider.setFixedHeight(8)
        vol_slider.setCursor(_Qt.PointingHandCursor)
        vol_slider.setToolTip("Volume")
        vol_slider.setStyleSheet(
            "QSlider::groove:horizontal{"
            "background:rgb(24,26,42);height:4px;border-radius:2px;margin:0;}"
            "QSlider::sub-page:horizontal{"
            "background:rgb(80,90,120);border-radius:2px;}"
            "QSlider::handle:horizontal{"
            "background:rgb(150,165,200);width:8px;height:8px;"
            "border-radius:4px;margin:-2px 0;}"
        )

        ctrl.addWidget(goto_start)
        ctrl.addWidget(prev_fr)
        ctrl.addWidget(play_btn)
        ctrl.addWidget(next_fr)
        ctrl.addStretch()
        ctrl.addWidget(time_w)
        ctrl.addStretch()
        ctrl.addWidget(loop_btn)
        ctrl.addWidget(info_btn)
        ctrl.addWidget(fs_btn)
        ctrl.addWidget(mute_btn)
        ctrl.addWidget(vol_slider)

        outer.addLayout(ctrl)
        return outer, play_btn, pos_lbl, dur_lbl, seek, mute_btn, prev_fr, next_fr, goto_start, loop_btn, vol_slider, fs_btn, info_btn

    @staticmethod
    def _fmt_tc(ms: int) -> str:
        """Format ms as M:SS timecode."""
        s = max(0, ms) // 1000
        return f"{s//60}:{s%60:02d}"

    @staticmethod
    def _fmt_fr(ms: int, fps: float) -> str:
        """Format ms as frame number (f NNN)."""
        fps = fps or 24.0
        frame = int(max(0, ms) / 1000.0 * fps)
        return f"f {frame}"

    def _copy_path(self, asset: Asset):
        from PySide2.QtWidgets import QApplication
        QApplication.clipboard().setText(str(asset.path))

    def _set_rating(self, asset_id: str, rating: int):
        """Update star rating visuals and emit signal."""
        _STAR_DIM = ("QPushButton{background:transparent;color:rgb(50,55,75);"
                     "border:none;font-size:16px;padding:0;min-width:20px;}")
        _STAR_LIT = ("QPushButton{background:transparent;color:rgb(251,191,36);"
                     "border:none;font-size:16px;padding:0;min-width:20px;}")
        for i, btn in enumerate(self._rating_btns):
            btn.setStyleSheet(_STAR_LIT if (i + 1) <= rating else _STAR_DIM)
        self.ratingChanged.emit(asset_id, rating)

    def _show_edit_versions_menu(self, btn, primary_id, versions, current_id):
        """Popup menu to unlink/delete versions + add new ones."""
        from PySide2.QtWidgets import QMenu
        menu = QMenu(self)
        for i, va in enumerate(versions):
            is_primary = (va.id == primary_id)
            label = f"V{i+1}  {va.name[:24]}"
            sub = menu.addMenu(label)
            if not is_primary:
                sub.addAction("Unlink (keep in library)",
                    lambda checked=False, pid=primary_id, cid=va.id:
                        self.unlinkVersionReq.emit(pid, cid))
                sub.addAction("Delete from library",
                    lambda checked=False, pid=primary_id, cid=va.id:
                        self.deleteVersionReq.emit(pid, cid))
            else:
                act = sub.addAction("Primary version")
                act.setEnabled(False)
        menu.addSeparator()
        menu.addAction("+ Link from Library…",
            lambda: self.linkVersionFromLib.emit(primary_id))
        menu.addAction("+ Link from File…",
            lambda: self.linkVersionFromFile.emit(primary_id))
        menu.exec_(btn.mapToGlobal(btn.rect().bottomLeft()))

    def _navigate_to_linked(self, asset_id: str):
        self.navigateToReq.emit(asset_id)

    def _unlink_version(self, aid: str, lid: str):
        self.unlinkReq.emit(aid, lid)

    def _flush_notes(self):
        """Called by debounce timer — saves notes to disk."""
        aid, text = self._pending_notes
        if aid:
            self.notesChanged.emit(aid, text)

    def _toggle_edit_mode(self, on: bool, asset: Asset):
        self._edit_mode = on
        # Always fetch fresh asset from lib (tags may have changed during edit)
        fresh = self.lib.get(asset.id) if asset else None
        if not fresh:
            fresh = asset
        if hasattr(self, '_edit_btn'):
            self._edit_btn.blockSignals(True)
            self._edit_btn.setChecked(on)
            self._edit_btn.setText("Done" if on else "Edit")
            self._edit_btn.setFixedWidth(52 if on else 46)
            self._edit_btn.blockSignals(False)
        self._rebuild_tag_pills(fresh, edit=on)
        self._add_tag_row.setVisible(on)
        self._quick_widget.setVisible(on)
        # Refresh quick-add preset active states
        self._refresh_quick_presets(fresh)
        # When exiting edit mode, signal grid to refresh
        if not on:
            self.editModeExited.emit()

    def _rebuild_tag_pills(self, asset: Asset, edit: bool = False):
        self._tag_widget.setUpdatesEnabled(False)
        while self._tag_flow.count():
            item = self._tag_flow.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for t in asset.tags:
            if edit:
                c = QWidget(); c.setStyleSheet("background: transparent;")
                cl = QHBoxLayout(c); cl.setContentsMargins(0,0,0,0); cl.setSpacing(1)
                pill = TagPill(t, active=True)
                rm = QPushButton("×")
                rm.setFixedSize(16, 20)
                rm.setStyleSheet(
                    "QPushButton{background:transparent;color:rgb(80,80,100);"
                    "border:none;font-size:12px;padding:0;}"
                    "QPushButton:hover{color:rgb(248,113,113);}")
                rm.clicked.connect(
                    lambda checked=False, tag=t, aid=asset.id:
                        self.tagRemoved.emit(aid, tag))
                cl.addWidget(pill); cl.addWidget(rm)
                self._tag_flow.addWidget(c)
            else:
                pill = TagPill(t, active=True)
                pill.pressed_tag.connect(
                    lambda tag, _=None: self.searchTagReq.emit(tag))
                self._tag_flow.addWidget(pill)
        self._tag_widget.setUpdatesEnabled(True)

    def _do_add_tags(self, asset_id: str, text: str):
        from config import normalize_tag
        for t in [x.strip() for x in text.split(",") if x.strip()]:
            self.tagAdded.emit(asset_id, normalize_tag(t))
        if hasattr(self, "_tag_input"):
            self._tag_input.clear()

    def _toggle_tag(self, asset_id: str, tag: str):
        asset = self.lib.get(asset_id)
        if not asset: return
        if tag in asset.tags:
            self.tagRemoved.emit(asset_id, tag)
        else:
            self.tagAdded.emit(asset_id, tag)

    def _stop_active_player(self):
        """Stop and release any active VLC or Qt media player — non-blocking."""
        try:
            if self._content is None:
                return
            # Collect all player refs and detach from widgets INSTANTLY
            _players = []
            _instances = []
            vlc_p = getattr(self._content, '_vlc_player', None)
            if vlc_p:
                _players.append(vlc_p)
                self._content._vlc_player = None
            qt_p = getattr(self._content, '_qt_player', None)
            if qt_p:
                try: qt_p.stop()
                except: pass
                self._content._qt_player = None
            for child in self._content.findChildren(QWidget):
                p = getattr(child, '_vlc_player', None)
                if p:
                    _players.append(p)
                    child._vlc_player = None
                inst = getattr(child, '_vlc_inst', None)
                if inst:
                    _instances.append(inst)
                    child._vlc_inst = None
                qp = getattr(child, '_qt_player', None)
                if qp:
                    try: qp.stop()
                    except: pass
                    child._qt_player = None
            # Defer stop + release to next event loop tick — never blocks UI
            if _players or _instances:
                def _deferred():
                    for p in _players:
                        try: p.stop()
                        except: pass
                    for p in _players:
                        try: p.release()
                        except: pass
                    for i in _instances:
                        try: i.release()
                        except: pass
                QTimer.singleShot(0, _deferred)
        except Exception:
            pass

    def _rebuild_content_widget(self):
        if self._content is not None:
            # Only do expensive player cleanup if we know a player was created
            if getattr(self._content, '_has_player', False):
                self._stop_active_player()
            self._scroll.takeWidget()
            self._content.deleteLater()
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._cl = QVBoxLayout(self._content)
        self._cl.setContentsMargins(8, 8, 8, 8)
        self._cl.setSpacing(4)
        self._scroll.setWidget(self._content)

    def _clear(self):
        self._rebuild_content_widget()

    def _sep(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background: rgb(22,22,38); max-height: 1px;")
        self._cl.addWidget(sep)

    def _section(self, text: str):
        self._sep()
        self._cl.addWidget(_section_lbl(text))
