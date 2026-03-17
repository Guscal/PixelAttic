"""
app.py — PixelAtticApp main window. Production build.
"""
import sys, os, shutil, subprocess
from pathlib import Path
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import importlib.util as _ilu
def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_HERE, name + ".py"))
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

for _m in ["config","database","settings","thumbnails","styles",
           "widgets","panels","dialogs","search_bar","preview"]:
    _load(_m)

from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QToolBar,
    QStatusBar, QLabel, QPushButton, QFileDialog, QSizePolicy,
    QInputDialog, QMessageBox, QMenu, QDialog, QHBoxLayout,
    QVBoxLayout, QFrame, QTableWidget, QTableWidgetItem,
    QHeaderView, QAction, QProgressDialog
)
from PySide2.QtCore import Qt, QTimer, QPoint
from PySide2.QtGui  import QFont, QCursor, QKeySequence, QPixmap

from config     import APP_NAME, VERSION, get_categories
from database   import Library, Asset
from settings   import Settings, CARD_SIZES, ACCENT_COLORS
from thumbnails import load_or_generate
from styles     import build_stylesheet
from widgets    import AssetCard, ContentArea, PaginationBar
from panels     import Sidebar, DetailPanel
from dialogs    import SettingsDialog, ImportDialog, TagEditorDialog
from search_bar import PillSearchBar, SearchToken
from preview    import generate_strip, generate_proxy, get_proxy_path, invalidate_strip, set_ffmpeg_path, set_proxy_dir, get_strip_path
from logger     import log_info, log_error, log_debug

class PixelAtticApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.settings = Settings.load()

        # Initialize library based on storage backend setting
        backend = getattr(self.settings, 'storage_backend', 'json')
        if backend == 'sqlite':
            try:
                from sqlite_db import SQLiteLibrary
                self.lib = SQLiteLibrary()
                log_info("[App] Using SQLite backend")
            except Exception as e:
                log_error(f"[App] SQLite init failed, falling back to JSON: {e}")
                self.lib = Library()
        else:
            self.lib = Library()

        # Filter state
        self.search_tokens: list  = []
        if getattr(self.settings, 'restore_last_category', True):
            self.category = getattr(self.settings, 'last_category', 'All')
        else:
            self.category = "All"
        self.active_tags: list    = []
        self.filter_starred: bool = False
        self.sort_by              = getattr(self.settings, 'sort_by',      'name')
        self.sort_reverse         = getattr(self.settings, 'sort_reverse', False)
        # Session state: starts from the persistent defaults in Settings
        self._session_card_size   = getattr(self.settings, 'card_size', 'Medium')
        self.view_mode            = getattr(self.settings, 'view_mode_default', 'grid')
        self.active_collection: Optional[str] = None
        self._current_page:     int           = 0
        self.selected_id:       Optional[str] = None
        self._selected_ids: set               = set()

        self._thumb_cache: dict = {}
        self._filtered_cache: Optional[list] = None   # perf: avoid re-filtering

        self.setWindowTitle(f"{APP_NAME}  v{VERSION}")
        self.resize(1440, 900)
        # Frameless custom chrome
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAcceptDrops(True)   # drag-and-drop import
        self._is_maximized = False
        self._drag_pos = QPoint()

        self._build_ui()
        self._setup_shortcuts()
        self.apply_theme(self.settings.theme, self.settings.accent_color)
        # Restore window geometry
        if getattr(self.settings, 'window_maximized', False):
            self.showMaximized()
            self._is_maximized = True
        elif getattr(self.settings, 'window_w', 0) > 400:
            self.setGeometry(
                self.settings.window_x, self.settings.window_y,
                self.settings.window_w, self.settings.window_h)
        self.apply_font()
        self._register_pill_callback()
        # Apply configured ffmpeg path
        self._apply_ffmpeg()
        # Purge stale text-placeholder thumbnails so real frames regenerate
        try:
            from thumbnails import purge_placeholder_thumbnails
            _n = purge_placeholder_thumbnails(self.lib)
            if _n: log_info(f"Purged {_n} placeholder thumbnail(s)")
        except Exception: pass
        log_info("App initialized")
        self._full_refresh()

        # ── Startup: regenerate thumbnails for assets that are missing them ──
        # This catches: purged placeholders, assets imported when ffmpeg was
        # absent, and thumbnails deleted outside the app.
        try:
            from thumbnails import thumb_cache_path
            _needs = [
                a for a in self.lib.all_assets()
                if a.file_type in ("video", "sequence")
                and not thumb_cache_path(a.id).exists()
            ]
            if _needs:
                log_info(f"Startup: regenerating {len(_needs)} missing thumbnail(s)")
                self._start_strip_thread(_needs)
        except Exception as _e:
            log_error(f"Startup thumb regen: {_e}")

        # ── Periodic save: flush dirty library to disk every 2s ──────────
        self._save_timer = QTimer(self)
        self._save_timer.setInterval(2000)
        self._save_timer.timeout.connect(self.lib.flush_if_dirty)
        self._save_timer.start()

    # ═══════════════════════════════════════════════════════
    # UI BUILD
    # ═══════════════════════════════════════════════════════

    def _build_ui(self):
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(3)
        self.setCentralWidget(self._splitter)

        self._sidebar = Sidebar(self.lib)
        self._sidebar.categorySelected.connect(self._on_category)
        self._sidebar.tagToggled.connect(self._on_tag_toggle)
        self._sidebar.collectionSelected.connect(self._on_collection_select)
        self._sidebar.newCollectionReq.connect(self._new_collection)
        self._sidebar.importCollectionReq.connect(self._import_collection)
        self._sidebar.exportCollectionReq.connect(self._export_collection)
        self._sidebar.deleteCollectionReq.connect(self._delete_collection)
        self._sidebar.renameCollectionReq.connect(self._rename_collection)
        self._sidebar.clearTagsReq.connect(self._clear_tags)
        self._sidebar.addCategoryReq.connect(self._add_category)
        self._sidebar.deleteCategoryReq.connect(self._delete_category)
        self._sidebar.saveSearchReq.connect(self._save_search)
        self._sidebar.loadSearchReq.connect(self._load_search)
        self._sidebar.deleteSearchReq.connect(self._delete_search)
        self._sidebar.renameSearchReq.connect(self._rename_search)
        self._splitter.addWidget(self._sidebar)

        self._content_splitter = QSplitter(Qt.Horizontal)
        self._content_splitter.setHandleWidth(3)
        self._splitter.addWidget(self._content_splitter)

        # Content area = content toolbar + scroll area + pagination bar
        self._content_wrapper = QWidget()
        self._content_wrapper.setObjectName("content_wrapper")
        _cw_layout = QVBoxLayout(self._content_wrapper)
        _cw_layout.setContentsMargins(0, 0, 0, 0)
        _cw_layout.setSpacing(0)

        # ── Content toolbar (sort · view · size · page) ──────────────────
        self._build_content_toolbar(_cw_layout)

        self._content_area = ContentArea()
        _cw_layout.addWidget(self._content_area, 1)

        self._pagination_bar = PaginationBar()
        self._pagination_bar.page_changed.connect(self._on_page_changed)
        self._pagination_bar.hide()  # hidden until needed
        _cw_layout.addWidget(self._pagination_bar, 0)

        self._content_splitter.addWidget(self._content_wrapper)

        self._detail_panel = DetailPanel(self.lib)
        self._detail_panel.tagAdded.connect(self._on_tag_added)
        self._detail_panel.tagRemoved.connect(self._on_tag_removed)
        self._detail_panel.nameChanged.connect(self._on_name_changed)
        self._detail_panel.catChanged.connect(self._on_cat_changed)
        self._detail_panel.notesChanged.connect(self._on_notes_changed)
        self._detail_panel.ratingChanged.connect(self._on_rating_changed)
        self._detail_panel.starChanged.connect(self._on_detail_star_changed)
        self._detail_panel.openFileReq.connect(self._open_file)
        self._detail_panel.showExplorerReq.connect(self._show_in_explorer_id)
        self._detail_panel.searchTagReq.connect(self._add_tag_token)
        self._detail_panel.searchCatReq.connect(self._add_cat_token)
        self._detail_panel.prevAssetReq.connect(self._nav_prev_asset)
        self._detail_panel.nextAssetReq.connect(self._nav_next_asset)
        self._detail_panel.navigateToReq.connect(self._navigate_to_asset)
        self._detail_panel.unlinkReq.connect(self._unlink_assets)
        self._sync_detail_categories()
        self._content_splitter.addWidget(self._detail_panel)

        # Restore splitter positions from settings
        _sw = getattr(self.settings, 'sidebar_width', 215)
        _dw = getattr(self.settings, 'detail_width', 320)
        # Clamp old oversized defaults (pre-update settings may have 460)
        if _dw > 380:
            _dw = 320
        self._splitter.setSizes([_sw, self.width() - _sw])
        self._content_splitter.setSizes([max(400, self.width() - _sw - _dw), _dw])
        self._detail_panel.setMinimumWidth(260)

        # ── Re-render grid when splitters are dragged ─────────────────────
        self._splitter.splitterMoved.connect(self._on_splitter_moved)
        self._content_splitter.splitterMoved.connect(self._on_splitter_moved)

        self._build_title_bar()
        self._build_toolbar()

        self._status_bar   = QStatusBar()
        self._status_label = QLabel("")
        self._status_bar.addWidget(self._status_label, 1)
        # Right side: individual labeled segments with tooltips
        self._stat_vid   = QLabel("")
        self._stat_seq   = QLabel("")
        self._stat_img   = QLabel("")
        self._stat_size  = QLabel("")
        self._stat_ffmpeg = QLabel("")
        _stat_style = "color:rgb(80,95,115);font-size:11px;padding:0 6px;"
        for lbl, tip in [
            (self._stat_vid,  "Videos in library"),
            (self._stat_seq,  "Image sequences in library"),
            (self._stat_img,  "Still images in library"),
            (self._stat_size,   "Total library size on disk"),
            (self._stat_ffmpeg, "ffmpeg status"),
        ]:
            lbl.setStyleSheet(_stat_style)
            lbl.setToolTip(tip)
            self._status_bar.addPermanentWidget(lbl)
        import preview as _pv
        if _pv.FFMPEG is None:
            self._stat_ffmpeg.setText("⚠ ffmpeg not found — scrub previews disabled")
        self.setStatusBar(self._status_bar)

    def _build_toolbar(self):
        """
        CANONICAL Qt toolbar pattern — each item added directly to QToolBar.
        Spacers with QSizePolicy.Expanding push groups apart reliably.
        No wrapper widget needed. Tested pattern from Qt Creator / KDE apps.

        Groups:  [Name] | [⊕Files ⊕Folder] || [Search] || [Sort] | [View] [Size] [Pg] | [⚙]
                  left fixed               spacer  spacer  right fixed
        """
        BH = 26   # button height  — every button uses this
        IW = 38   # icon button width (⊞ ≡ M ⚙)

        # ── helpers ──────────────────────────────────────────────────────────
        def _spacer(max_w=80):
            """Expanding spacer capped at max_w px — centers search without wasting space."""
            sp = QWidget()
            sp.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            sp.setMaximumWidth(max_w)
            sp.setAttribute(Qt.WA_TransparentForMouseEvents)
            sp.setStyleSheet("background:transparent;")
            return sp

        def _sep():
            """Thin vertical divider between groups."""
            s = QFrame()
            s.setFrameShape(QFrame.VLine)
            s.setFixedSize(1, 18)
            s.setStyleSheet("background:rgb(35,35,55);border:none;margin:0 3px;")
            return s

        def _flash_inline(btn, accent_rgb="52,211,153", ms=900):
            """
            Feedback flash using setStyleSheet inline — no CSS class needed.
            Saves/restores style sheet so objectName styles are unaffected.
            """
            saved = btn.styleSheet()
            saved_text = btn.text()
            r, g, b = accent_rgb.split(",")
            btn.setStyleSheet(
                f"QPushButton{{background:rgba({r},{g},{b},30);"
                f"color:rgb({r},{g},{b});"
                f"border:1px solid rgba({r},{g},{b},80);"
                f"border-radius:4px;font-size:12px;"
                f"min-height:{BH}px;font-weight:bold;}}"
            )
            btn.setText("  ✓  ")
            def _restore():
                btn.setText(saved_text)
                btn.setStyleSheet(saved)
            QTimer.singleShot(ms, _restore)

        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setFloatable(False)

        # ── App name (click to toggle sidebar) ────────────────────────────────
        from settings import ACCENT_COLORS
        _ar, _ag, _ab = ACCENT_COLORS.get(self.settings.accent_color, (249, 115, 22))
        name_lbl = QLabel(f"  {APP_NAME}  ")
        name_lbl.setObjectName("app_name")
        name_lbl.setStyleSheet(
            f"#app_name{{font-size:14px;font-weight:bold;letter-spacing:2px;"
            f"color:rgb({_ar},{_ag},{_ab});padding:0 8px;}}")
        name_lbl.setFixedHeight(BH + 8)
        name_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        name_lbl.setToolTip("Toggle sidebar")
        name_lbl.mousePressEvent = lambda e: self._toggle_sidebar()
        self._logo_lbl = name_lbl
        tb.addWidget(name_lbl)
        tb.addWidget(_sep())

        # ── LEFT spacer — pushes import buttons toward center ─────────────
        tb.addWidget(_spacer())

        # ── Import buttons ────────────────────────────────────────────────────
        from icons import icon_path, icon_exists
        from PySide2.QtGui import QIcon as _TBIcon
        from PySide2.QtCore import QSize as _TBSize

        imp_btn = QPushButton(" Import Files ")
        if icon_exists("add.png"):
            imp_btn.setIcon(_TBIcon(icon_path("add.png")))
            imp_btn.setIconSize(_TBSize(14, 14))
        imp_btn.setObjectName("btn_accent")
        imp_btn.setFixedHeight(BH)
        imp_btn.setToolTip("Import files  (Ctrl+I)")
        imp_btn.clicked.connect(lambda: (
            self._import_files(),
            _flash_inline(imp_btn, "249,115,22")
        ))
        tb.addWidget(imp_btn)

        _imp_gap = QWidget()
        _imp_gap.setFixedWidth(4)
        tb.addWidget(_imp_gap)

        imp_folder = QPushButton(" Import Folder ")
        if icon_exists("folder.png"):
            imp_folder.setIcon(_TBIcon(icon_path("folder.png")))
            imp_folder.setIconSize(_TBSize(14, 14))
        imp_folder.setObjectName("btn_accent_outline")
        imp_folder.setFixedHeight(BH)
        imp_folder.setToolTip("Import folder  (Ctrl+Shift+I)")
        imp_folder.clicked.connect(lambda: (
            self._import_folder(),
            _flash_inline(imp_folder, "249,115,22")
        ))
        tb.addWidget(imp_folder)

        # ── RIGHT spacer — mirrors left so buttons stay centered ──────────
        tb.addWidget(_spacer())
        tb.addWidget(_sep())

        # ── Search bar ────────────────────────────────────────────────────────
        self._search_bar = PillSearchBar(self)
        self._search_bar.setFixedHeight(BH + 6)
        self._search_bar.setMinimumWidth(380)
        self._search_bar.setMaximumWidth(9999)
        self._search_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._search_bar.filter_changed.connect(self._on_filter_changed)
        tb.addWidget(self._search_bar)

        # ── RIGHT spacer — mirrors left so search stays centered ───────────────
        tb.addWidget(_sep())
        tb.addWidget(_spacer())
        tb.addWidget(_sep())

        # ── Settings ──────────────────────────────────────────────────────
        settings_btn = QPushButton("Settings")
        if icon_exists("settings.png"):
            settings_btn.setIcon(_TBIcon(icon_path("settings.png")))
            settings_btn.setIconSize(_TBSize(16, 16))
        settings_btn.setFixedSize(80, BH)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self._open_settings)
        tb.addWidget(settings_btn)

    # ═══════════════════════════════════════════════════════
    # CONTENT TOOLBAR (sort · view mode · card size · page)
    # ═══════════════════════════════════════════════════════

    def _build_content_toolbar(self, parent_layout):
        """Build a slim toolbar above the grid with sort, view, size, page controls."""
        BH = 22

        bar = QWidget()
        bar.setObjectName("content_toolbar")
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            "QWidget#content_toolbar {"
            "  background: rgb(9,9,16);"
            "  border-bottom: 1px solid rgb(22,22,38);"
            "}")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(8, 3, 8, 3)
        hl.setSpacing(3)

        _BTN = (
            "QPushButton{background:transparent;color:rgb(100,116,139);"
            "border:1px solid transparent;border-radius:3px;"
            f"font-size:11px;min-height:{BH}px;padding:0 6px;}}"
            "QPushButton:hover{color:rgb(200,210,230);background:rgb(20,20,34);"
            "border-color:rgb(35,35,55);}"
        )
        _BTN_ACTIVE = (
            "QPushButton{background:rgba(249,115,22,15);color:rgb(249,115,22);"
            "border:1px solid rgba(249,115,22,40);border-radius:3px;"
            f"font-size:11px;min-height:{BH}px;padding:0 6px;font-weight:bold;}}"
        )

        # ── Sort ─────────────────────────────────────────────────────────
        sort_lbl = QLabel("Sort:")
        sort_lbl.setStyleSheet("color:rgb(55,65,85);font-size:10px;background:transparent;")
        hl.addWidget(sort_lbl)

        self._sort_btns: dict = {}
        for key, label in [("name", "Name"), ("date", "Date"), ("size", "Size"), ("type", "Type"), ("rating", "Rating")]:
            btn = QPushButton(label)
            btn.setFixedHeight(BH)
            btn.setStyleSheet(_BTN)
            btn.clicked.connect(lambda checked=False, k=key: self._on_sort(k))
            hl.addWidget(btn)
            self._sort_btns[key] = btn

        # ── Separator ────────────────────────────────────────────────────
        def _sep():
            s = QFrame(); s.setFrameShape(QFrame.VLine)
            s.setFixedSize(1, 16)
            s.setStyleSheet("background:rgb(28,28,44);border:none;")
            return s
        hl.addWidget(_sep())

        # ── View mode ────────────────────────────────────────────────────
        self._grid_btn = QPushButton("Grid")
        self._grid_btn.setFixedHeight(BH)
        self._grid_btn.setStyleSheet(_BTN)
        self._grid_btn.setToolTip("Grid view  (G)")
        self._grid_btn.clicked.connect(lambda checked=False: self._set_view("grid"))
        hl.addWidget(self._grid_btn)

        self._list_btn = QPushButton("List")
        self._list_btn.setFixedHeight(BH)
        self._list_btn.setStyleSheet(_BTN)
        self._list_btn.setToolTip("List view  (L)")
        self._list_btn.clicked.connect(lambda checked=False: self._set_view("list"))
        hl.addWidget(self._list_btn)

        hl.addWidget(_sep())

        # ── Card size ────────────────────────────────────────────────────
        size_lbl = QLabel("Size:")
        size_lbl.setStyleSheet("color:rgb(55,65,85);font-size:10px;background:transparent;")
        hl.addWidget(size_lbl)

        _SIZE_CYCLE = ["Small", "Medium", "Large", "X-Large"]
        self._size_btn = QPushButton("M")
        self._size_btn.setFixedHeight(BH)
        self._size_btn.setStyleSheet(_BTN)
        self._size_btn.setToolTip("Card size — click to cycle  S / M / L / XL")
        def _cycle_size(checked=False):
            cur = self._current_card_size()
            idx = (_SIZE_CYCLE.index(cur) + 1) % len(_SIZE_CYCLE) if cur in _SIZE_CYCLE else 1
            self._set_card_size(_SIZE_CYCLE[idx])
        self._size_btn.clicked.connect(_cycle_size)
        hl.addWidget(self._size_btn)

        hl.addWidget(_sep())

        # ── Page size ────────────────────────────────────────────────────
        self._page_size_btn = QPushButton(f"{self.settings.page_size}/page")
        self._page_size_btn.setFixedHeight(BH)
        self._page_size_btn.setStyleSheet(_BTN)
        self._page_size_btn.setToolTip("Assets per page — click to cycle  25 / 50 / 100")
        def _cycle_page_size(checked=False):
            cycle = [25, 50, 100]
            cur   = self.settings.page_size
            nxt   = cycle[(cycle.index(cur) + 1) % len(cycle)] if cur in cycle else 50
            self.settings.page_size = nxt
            self._page_size_btn.setText(f"{nxt}/page")
            self._current_page = 0
            self._render_content()
        self._page_size_btn.clicked.connect(_cycle_page_size)
        hl.addWidget(self._page_size_btn)

        hl.addWidget(_sep())

        # ── Starred filter (independent toggle) ──────────────────────────
        self._starred_btn = QPushButton("  ★ Starred Only  ")
        self._starred_btn.setCheckable(True)
        self._starred_btn.setChecked(False)
        self._starred_btn.setFixedHeight(BH)
        self._starred_btn.setToolTip("Show only starred assets")
        self._starred_btn.setStyleSheet(
            f"QPushButton{{background:transparent;color:rgb(80,95,120);"
            f"border:1px solid transparent;border-radius:3px;"
            f"font-size:11px;min-height:{BH}px;padding:0 6px;}}"
            f"QPushButton:hover{{color:rgb(251,191,36);background:rgb(20,20,34);"
            f"border-color:rgba(251,191,36,30);}}"
            f"QPushButton:checked{{color:rgb(251,191,36);"
            f"background:rgba(251,191,36,12);border:1px solid rgba(251,191,36,40);"
            f"font-weight:bold;}}")
        self._starred_btn.toggled.connect(self._on_starred_toggle)
        hl.addWidget(self._starred_btn)

        hl.addStretch()
        parent_layout.addWidget(bar)

        # Store styles for update methods
        self._ct_btn_style = _BTN
        self._ct_btn_active = _BTN_ACTIVE

    # ═══════════════════════════════════════════════════════
    # CUSTOM TITLE BAR
    # ═══════════════════════════════════════════════════════

    def _build_title_bar(self):
        """
        Frameless window custom title bar.
        Sits as a menu-widget above the toolbar (QMainWindow.setMenuWidget).
        Provides: drag to move, double-click to maximize, min/max/close.
        """
        bar = QWidget()
        bar.setObjectName("title_bar")
        bar.setFixedHeight(30)
        bar.setCursor(Qt.ArrowCursor)

        hl = QHBoxLayout(bar)
        hl.setContentsMargins(10, 0, 4, 0)
        hl.setSpacing(0)

        # App icon placeholder + name
        icon_lbl = QLabel("●")
        icon_lbl.setStyleSheet(
            "color: rgb(249,115,22); font-size: 13px; "
            "background: transparent; padding-right: 6px;")
        hl.addWidget(icon_lbl)

        title_lbl = QLabel(f"{APP_NAME}  ·  v{VERSION}")
        title_lbl.setObjectName("title_bar_label")
        hl.addWidget(title_lbl)

        hl.addStretch()

        # Window control buttons
        BTN_W, BTN_H = 38, 30

        def _wbtn(symbol, tip, obj_name):
            b = QPushButton(symbol)
            b.setObjectName(obj_name)
            b.setFixedSize(BTN_W, BTN_H)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            return b

        min_btn = _wbtn("—", "Minimize", "wm_min")
        max_btn = _wbtn("□", "Maximize / Restore", "wm_max")
        cls_btn = _wbtn("✕", "Close", "wm_close")

        min_btn.clicked.connect(self.showMinimized)
        cls_btn.clicked.connect(self.close)

        def _toggle_max():
            if self._is_maximized:
                self.showNormal()
                self._is_maximized = False
                max_btn.setText("□")
            else:
                self.showMaximized()
                self._is_maximized = True
                max_btn.setText("❐")
        max_btn.clicked.connect(_toggle_max)

        hl.addWidget(min_btn)
        hl.addWidget(max_btn)
        hl.addWidget(cls_btn)

        # Drag behaviour — entire bar minus buttons
        bar._drag_active = False
        bar._drag_start  = QPoint()

        def _tb_press(e):
            if e.button() == Qt.LeftButton:
                bar._drag_active = True
                bar._drag_start  = e.globalPos() - self.frameGeometry().topLeft()
                e.accept()
        def _tb_move(e):
            if bar._drag_active and e.buttons() & Qt.LeftButton:
                if self._is_maximized:
                    self.showNormal()
                    self._is_maximized = False
                    max_btn.setText("□")
                self.move(e.globalPos() - bar._drag_start)
                e.accept()
        def _tb_release(e):
            bar._drag_active = False
        def _tb_dblclick(e):
            if e.button() == Qt.LeftButton:
                _toggle_max()

        bar.mousePressEvent   = _tb_press
        bar.mouseMoveEvent    = _tb_move
        bar.mouseReleaseEvent = _tb_release
        bar.mouseDoubleClickEvent = _tb_dblclick

        self.setMenuWidget(bar)
        self._title_bar = bar
        self._max_btn   = max_btn

    def changeEvent(self, event):
        super().changeEvent(event)
        # Sync max button icon if window state changes externally
        if hasattr(self, "_max_btn"):
            from PySide2.QtCore import QEvent
            if event.type() == QEvent.WindowStateChange:
                is_max = bool(self.windowState() & Qt.WindowMaximized)
                self._is_maximized = is_max
                self._max_btn.setText("❐" if is_max else "□")

    def _setup_shortcuts(self):
        def _act(name, seq, fn):
            a = QAction(name, self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(fn)
            self.addAction(a)

        _act("Focus Search", "Ctrl+F",
             lambda: self._search_bar.focus_input())
        _act("Import Files",  "Ctrl+I", self._import_files)
        _act("Import Folder", "Ctrl+Shift+I", self._import_folder)
        _act("Grid View",       "G",     lambda: self._set_view("grid"))
        _act("List View",       "L",     lambda: self._set_view("list"))
        _act("Prev Asset",      "Left",  self._nav_prev_asset)
        _act("Next Asset",      "Right", self._nav_next_asset)
        _act("Open File",   "Ctrl+Return", self._open_selected_file)
        _act("Show Explorer","Ctrl+E",  self._show_selected_in_explorer)
        _act("Copy Path",   "Ctrl+Shift+C", self._copy_selected_path)
        _act("Edit Tags",   "T",   self._edit_selected_tags)
        _act("Delete",      "Delete", self._delete_selected)
        _act("Escape",      "Escape", self._clear_detail)
        _act("Select All",  "Ctrl+A", self._select_all)

    # ═══════════════════════════════════════════════════════
    # RENDER
    # ═══════════════════════════════════════════════════════

    def _sync_detail_categories(self):
        """Push current custom/hidden categories to the detail panel."""
        custom = self.settings.custom_categories or []
        hidden = getattr(self.settings, "hidden_base_categories", []) or []
        self._detail_panel.set_categories(custom, hidden)

    def _full_refresh(self):
        custom = self.settings.custom_categories or []
        hidden = getattr(self.settings, "hidden_base_categories", []) or []
        self._sidebar.rebuild_categories(self.lib, self.category, custom, hidden)
        self._sidebar.rebuild_tags(self.lib, self.category, self.active_tags)
        self._sidebar.rebuild_collections(self.lib, self.active_collection)
        self._sidebar.rebuild_saved_searches(
            getattr(self.settings, 'saved_searches', []))
        self._sync_detail_categories()
        self._update_search_completions()
        self._update_sort_buttons()
        self._render_content()

    def _render_content(self):
        self._invalidate_filter_cache()
        assets = self._filtered_assets()

        # Status bar
        parts = []
        if self.active_collection:
            parts.append(f"● {self.active_collection}")
        else:
            if self.category != "All": parts.append(f"[{self.category}]")
            for t in self.active_tags: parts.append(f"#{t}")
        for tok in self.search_tokens:
            parts.append(tok.label)
        f_str = "  ·  ".join(parts) if parts else "All assets"
        sel   = f"   ·   ✓ {self.lib.get(self.selected_id).name}" \
                if self.selected_id and self.lib.get(self.selected_id) else ""
        multi = f"   ·   {len(self._selected_ids)} selected" \
                if len(self._selected_ids) > 1 else ""
        self._status_label.setText(
            f"  {f_str}  —  {len(assets)} / {len(self.lib.all_assets())} assets{sel}{multi}")

        # Rich right-side stats: type breakdown + total size
        all_a    = self.lib.all_assets()
        n_vid    = sum(1 for a in all_a if a.file_type == "video")
        n_seq    = sum(1 for a in all_a if a.file_type == "sequence")
        n_img    = sum(1 for a in all_a if a.file_type == "image")
        total_mb = sum(a.file_size_mb or 0 for a in all_a)
        size_str = f"{total_mb/1024:.1f} GB" if total_mb >= 1024 else f"{total_mb:.0f} MB"
        self._stat_vid.setText(f"Vid {n_vid}" if n_vid else "")
        self._stat_seq.setText(f"Seq {n_seq}" if n_seq else "")
        self._stat_img.setText(f"Img {n_img}" if n_img else "")
        self._stat_size.setText(f"  {size_str}  ")

        if not assets:
            self._pagination_bar.hide()
            empty = QWidget()
            vl = QVBoxLayout(empty)
            vl.addStretch()
            lbl = QLabel("No assets match the current filters.\nTry adjusting search, category or tags.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: rgb(50,60,80); font-size: 13px; background: transparent;")
            vl.addWidget(lbl)
            vl.addStretch()
            self._content_area.set_content(empty)
            return

        # Pagination — clamp current page
        page_sz    = max(1, self.settings.page_size)
        total_pages = max(1, (len(assets) + page_sz - 1) // page_sz)
        self._current_page = max(0, min(self._current_page, total_pages - 1))

        page_assets = assets[self._current_page * page_sz : (self._current_page + 1) * page_sz]

        # Update pagination bar
        if total_pages > 1:
            self._pagination_bar.set_state(
                self._current_page, total_pages, len(assets), page_sz)
            self._pagination_bar.show()
        else:
            self._pagination_bar.hide()

        if self.view_mode == "grid":
            self._render_grid(page_assets)
        else:
            self._render_list(page_assets)

    def _invalidate_filter_cache(self):
        """Mark the filtered assets cache as stale."""
        self._filtered_cache = None

    def _filtered_assets(self) -> list:
        if self._filtered_cache is not None:
            return self._filtered_cache

        tag_f  = [t.value.lower() for t in self.search_tokens if t.kind == "tag"]
        cat_f  = next((t.value for t in self.search_tokens if t.kind == "cat"), None)
        fmt_f  = next((t.value.lower() for t in self.search_tokens if t.kind == "fmt"), None)
        gt     = next((float(t.value) for t in self.search_tokens if t.kind == "size_gt"), None)
        lt     = next((float(t.value) for t in self.search_tokens if t.kind == "size_lt"), None)
        texts  = [t.value for t in self.search_tokens if t.kind == "text"]
        # Exclude operators
        excl_tags = [t.value.lower() for t in self.search_tokens if t.kind == "exclude_tag"]
        excl_fmts = [t.value.lower() for t in self.search_tokens if t.kind == "exclude_fmt"]
        # Starred token
        has_star_token = any(t.kind == "starred" for t in self.search_tokens)
        # Advanced operators
        dur_gt = next((float(t.value) for t in self.search_tokens if t.kind == "dur_gt"), None)
        dur_lt = next((float(t.value) for t in self.search_tokens if t.kind == "dur_lt"), None)
        res_f  = next((t.value.upper() for t in self.search_tokens if t.kind == "res"), None)
        codec_f = next((t.value.lower() for t in self.search_tokens if t.kind == "codec"), None)
        depth_f = next((int(t.value) for t in self.search_tokens if t.kind == "depth"), None)
        date_f  = next((t.value for t in self.search_tokens if t.kind == "date"), None)
        query  = " ".join(texts)
        cat    = cat_f or self.category

        # ── Starred mode: bypass category filter, search ALL assets ───────
        if self.filter_starred or has_star_token:
            all_a = self.lib.all_assets()
            pool = [a for a in all_a if bool(getattr(a, 'starred', False))]
            if query:
                q = query.lower()
                pool = [a for a in pool
                        if q in a.name.lower() or q in (a.notes or "").lower()]
            # Apply sort
            key_fn = {
                "name": lambda a: a.name.lower(),
                "date": lambda a: a.date_added or "",
                "size": lambda a: a.file_size_mb or 0,
                "type": lambda a: (a.file_type or "", a.format or "", a.name.lower()),
                "rating": lambda a: (a.rating or 0, a.name.lower()),
            }.get(self.sort_by, lambda a: a.name.lower())
            pool = sorted(pool, key=key_fn, reverse=self.sort_reverse)
        elif self.active_collection is not None:
            pool = self.lib.collection_assets(self.active_collection)
            if query:
                q = query.lower()
                pool = [a for a in pool
                        if q in a.name.lower() or q in (a.notes or "").lower()]
        else:
            pool = self.lib.filtered(
                search=query, category=cat,
                active_tags=self.active_tags,
                sort_by=self.sort_by, sort_reverse=self.sort_reverse)

        for tf in tag_f:
            pool = [a for a in pool if any(tf in t.lower() for t in a.tags)]
        if fmt_f:
            pool = [a for a in pool if a.format and fmt_f in a.format.lower()]
        if gt is not None:
            pool = [a for a in pool if a.file_size_mb and a.file_size_mb > gt]
        if lt is not None:
            pool = [a for a in pool if a.file_size_mb and a.file_size_mb < lt]
        # ── Exclude operators ─────────────────────────────────────────────
        for et in excl_tags:
            pool = [a for a in pool if not any(et in t.lower() for t in a.tags)]
        for ef in excl_fmts:
            pool = [a for a in pool if not (a.format and ef in a.format.lower())]
        # ── Advanced filters (C3) ─────────────────────────────────────────
        if dur_gt is not None:
            pool = [a for a in pool if a.duration_s and a.duration_s > dur_gt]
        if dur_lt is not None:
            pool = [a for a in pool if a.duration_s and a.duration_s < dur_lt]
        if res_f:
            pool = [a for a in pool if a.display_res and res_f in a.display_res.upper()]
        if codec_f:
            pool = [a for a in pool
                    if getattr(a, 'codec', None) and codec_f in a.codec.lower()]
        if depth_f:
            pool = [a for a in pool if getattr(a, 'bit_depth', None) == depth_f]
        if date_f:
            pool = [a for a in pool if a.date_added and a.date_added.startswith(date_f)]
        self._filtered_cache = pool
        return pool

    def _render_grid(self, assets: list):
        cw, ch = CARD_SIZES.get(self._current_card_size(), CARD_SIZES["Medium"])
        avail  = max(self._content_area.width() - 24, cw + 8)
        cols   = max(1, avail // (cw + 8))

        from widgets import VirtualGrid

        # Card factory — creates one card on demand
        def _make_card(asset):
            from preview import get_strip_path
            thumb = self._thumb_cache.get(asset.id)
            if not thumb:
                from thumbnails import thumb_cache_path
                cf = thumb_cache_path(asset.id)
                if cf.exists():
                    thumb = cf
                    self._thumb_cache[asset.id] = cf

            sp = get_strip_path(asset.id)
            strip = sp if sp.exists() else None
            card = AssetCard(
                asset, thumb, cw, ch,
                self.settings.grid_show_filename,
                self.settings.grid_show_resolution,
                self.settings.grid_show_tags,
                accent=self.settings.accent_color,
                strip_path=strip,
            )
            card.setSelected(asset.id in self._selected_ids)
            card.clicked.connect(self._on_card_click)
            card.rightClicked.connect(self._on_card_right_click)
            card.doubleClicked.connect(self._open_file)
            card.starToggled.connect(self._on_star_toggle)

            # Queue background thumb if missing
            if thumb is None and asset.file_type not in ("video", "sequence"):
                if getattr(self.settings, 'lazy_thumbnails', True):
                    self._bg_load_thumbs([(card, asset)])
            return card

        # Create or reuse VirtualGrid
        vgrid = VirtualGrid(self._content_area)
        vgrid.configure(assets, cols, cw, ch, _make_card)
        self._content_area.set_content(vgrid, preserve_scroll=True)

        # Trim thumb cache
        _max = getattr(self.settings, 'max_memory_thumbs', 500)
        if len(self._thumb_cache) > _max:
            excess = len(self._thumb_cache) - _max
            for k in list(self._thumb_cache.keys())[:excess]:
                del self._thumb_cache[k]

    def _bg_load_thumbs(self, items: list):
        """Load thumbnails in background thread and update cards. items=[(card, asset)]"""
        from PySide2.QtCore import QThread, QObject, Signal as _Sig

        class _Loader(QObject):
            thumb_ready = _Sig(str, str)  # (asset_id, thumb_path)
            finished    = _Sig()

            def __init__(self, work_items, parent=None):
                super().__init__(parent)
                self._items = work_items

            def run(self):
                for asset in self._items:
                    try:
                        result = load_or_generate(asset)
                        if result:
                            self.thumb_ready.emit(asset.id, str(result))
                    except Exception:
                        pass
                self.finished.emit()

        assets_list = [a for _, a in items]
        card_map = {a.id: c for c, a in items}

        thread = QThread(self)
        loader = _Loader(assets_list)
        loader.moveToThread(thread)

        def _on_ready(aid, tpath):
            self._thumb_cache[aid] = Path(tpath)
            card = card_map.get(aid)
            if card:
                try:
                    card.update_thumbnail(tpath)
                except RuntimeError:
                    pass

        loader.thumb_ready.connect(_on_ready)
        loader.finished.connect(thread.quit)
        loader.finished.connect(loader.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(loader.run)
        thread.start()

    def _render_list(self, assets: list):
        from widgets import TagPill
        from PySide2.QtWidgets import QWidget, QHBoxLayout

        COLS = ["", "Name", "Category", "Format", "Res", "Dur", "Size", "Tags"]
        # Default column widths (px); thumb=80, tags flexible
        COL_WIDTHS = [80, None, 110, 70, 70, 65, 75, None]

        table = QTableWidget(len(assets), len(COLS))
        table.setHorizontalHeaderLabels(COLS)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(58)

        # ── Column sizing: all manually resizable (like Excel) ────────────────
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)          # Tags column fills remaining space
        hdr.setMinimumSectionSize(40)
        for col, w in enumerate(COL_WIDTHS):
            if w is not None:
                table.setColumnWidth(col, w)
        # Name column gets a generous default
        table.setColumnWidth(1, 200)

        # ── Center alignment for all text columns ─────────────────────────────
        def _item(text, align=Qt.AlignVCenter | Qt.AlignLeft):
            it = QTableWidgetItem(str(text))
            it.setTextAlignment(align)
            return it
        _center = Qt.AlignVCenter | Qt.AlignHCenter

        for row, asset in enumerate(assets):
            # Thumbnail
            thumb = self._get_thumb(asset)
            if thumb and Path(str(thumb)).exists():
                lbl = QLabel()
                pix = QPixmap(str(thumb)).scaled(
                    76, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                lbl.setPixmap(pix)
                lbl.setAlignment(Qt.AlignCenter)
                table.setCellWidget(row, 0, lbl)

            table.setItem(row, 1, _item(asset.name))
            table.setItem(row, 2, _item(asset.category,  _center))
            table.setItem(row, 3, _item(asset.format or "", _center))
            table.setItem(row, 4, _item(asset.display_res, _center))
            table.setItem(row, 5, _item(asset.duration_str or "", _center))
            table.setItem(row, 6, _item(
                f"{asset.file_size_mb:.1f} MB" if asset.file_size_mb else "", _center))

            # Tags as pills — click adds tag to search bar (same behaviour as grid)
            tags_w = QWidget()
            tags_w.setStyleSheet("background: transparent;")
            tags_l = QHBoxLayout(tags_w)
            tags_l.setContentsMargins(4, 4, 4, 4)
            tags_l.setSpacing(3)
            for tag in asset.tags[:7]:
                pill = TagPill(tag, active=False, search_enabled=True)
                tags_l.addWidget(pill)
            tags_l.addStretch()
            table.setCellWidget(row, 7, tags_w)

        table.cellClicked.connect(
            lambda r, c, a=assets: self._on_card_click(a[r].id) if r < len(a) else None)
        table.cellDoubleClicked.connect(
            lambda r, c, a=assets: self._open_file(a[r].id) if r < len(a) else None)
        self._content_area.set_content(table)

    # ═══════════════════════════════════════════════════════
    # THUMBS
    # ═══════════════════════════════════════════════════════

    def _get_thumb(self, asset: Asset) -> Optional[Path]:
        from thumbnails import thumb_cache_path
        cached_file = thumb_cache_path(asset.id)
        # If we have a real path cached and it still exists, use it
        cached = self._thumb_cache.get(asset.id)
        if cached is not None and cached.exists():
            return cached
        # File on disk? Always prefer that (worker may have finished)
        if cached_file.exists():
            self._thumb_cache[asset.id] = cached_file
            return cached_file
        # For video/sequence: never block — return None, let bg thread handle it
        if asset.file_type in ("video", "sequence"):
            self._thumb_cache.pop(asset.id, None)  # don't cache None
            return None
        # For images: generate synchronously (PIL, fast, no ffmpeg)
        result = load_or_generate(asset)
        self._thumb_cache[asset.id] = result
        return result

    # ═══════════════════════════════════════════════════════
    # DETAIL
    # ═══════════════════════════════════════════════════════

    def _show_detail(self, asset: Asset):
        # Update nav position label
        assets = self._filtered_assets()
        try:
            idx = next(i for i, a in enumerate(assets) if a.id == asset.id)
            self._detail_panel.set_nav_index(idx, len(assets))
        except StopIteration:
            pass
        strip = None
        import preview as _prev
        if _prev.FFMPEG and asset.file_type in ("video", "sequence"):
            strip = generate_strip(asset)
        self._detail_panel.show_asset(
            asset, self._get_thumb(asset), strip_path=strip)

    def _clear_detail(self):
        self.selected_id = None
        self._selected_ids.clear()
        self._detail_panel.show_placeholder()
        self._render_content()

    # ═══════════════════════════════════════════════════════
    # CLICK
    # ═══════════════════════════════════════════════════════

    def _on_card_click(self, asset_id: str):
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ControlModifier:
            if asset_id in self._selected_ids:
                self._selected_ids.discard(asset_id)
                self.selected_id = next(iter(self._selected_ids), None)
            else:
                self._selected_ids.add(asset_id)
                self.selected_id = asset_id
        elif mods & Qt.ShiftModifier:
            # Range select in current visible order
            assets = self._filtered_assets()
            ids    = [a.id for a in assets]
            if self.selected_id and self.selected_id in ids and asset_id in ids:
                i0 = ids.index(self.selected_id)
                i1 = ids.index(asset_id)
                lo, hi = sorted([i0, i1])
                self._selected_ids = set(ids[lo:hi+1])
            self.selected_id = asset_id
        else:
            if self.selected_id == asset_id and len(self._selected_ids) == 1:
                self._clear_detail()
                return
            self._selected_ids = {asset_id}
            self.selected_id   = asset_id

        asset = self.lib.get(self.selected_id) if self.selected_id else None
        if asset:
            self._show_detail(asset)
        else:
            self._detail_panel.show_placeholder()
        self._update_card_selection()

    def _update_card_selection(self):
        """Update selection borders on existing cards without rebuilding the grid."""
        try:
            content = self._content_area.widget()
            if content is None:
                return
            for card in content.findChildren(AssetCard):
                card.setSelected(card.asset_id in self._selected_ids)
        except RuntimeError:
            pass  # grid was rebuilt

    def _on_card_right_click(self, asset_id: str):
        if asset_id not in self._selected_ids:
            self._selected_ids = {asset_id}
            self.selected_id   = asset_id

        asset = self.lib.get(asset_id)
        if not asset:
            return

        menu = QMenu(self)
        hdr  = menu.addAction(f"  {asset.name[:36]}")
        hdr.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Open File",            lambda: self._open_file(asset_id))
        menu.addAction("Show in Explorer",     lambda: self._show_in_explorer_id(asset_id))
        menu.addAction("Copy Path",            lambda: self._copy_path(asset))
        menu.addAction("Edit Tags…",           lambda: self._open_tag_editor(asset))
        import preview as _pv_cm
        if _pv_cm.FFMPEG:
            lbl = "Regenerate Preview" if asset.file_type in ("video","sequence") else "Regenerate Thumbnail"
            menu.addAction(lbl, lambda: self._regen_preview(asset_id))
            if asset.file_type in ("video", "sequence") and asset.duration_s:
                menu.addAction("Set Poster Frame…",
                    lambda: self._set_poster_frame(asset_id))
        menu.addSeparator()

        if len(self._selected_ids) > 1:
            bm = menu.addMenu(f"Batch ({len(self._selected_ids)} selected)")
            bm.addAction("Move to Category…",       self._batch_category)
            bm.addAction("Add Tag…",               self._batch_add_tag)
            bm.addAction("Remove Tag…",            self._batch_remove_tag)
            bm.addSeparator()
            bm.addAction("Add to Collection…",     self._batch_add_to_collection)
            bm.addAction("New Collection from Selection…", self._batch_new_collection)
            bm.addSeparator()
            if len(self._selected_ids) >= 2:
                bm.addAction("Link as Versions",       self._batch_link_versions)
            bm.addAction("Remove All from Library",self._batch_remove)
            menu.addSeparator()

        colls     = self.lib.get_collections()
        member_of = self.lib.collections_for_asset(asset_id)
        if colls:
            cm = menu.addMenu("Collections")
            for cname in sorted(colls.keys()):
                if cname in member_of:
                    cm.addAction(f"  ✓  {cname}",
                        lambda checked=False, n=cname: self._remove_from_collection(asset_id, n))
                else:
                    cm.addAction(f"      {cname}",
                        lambda checked=False, n=cname: self._add_to_collection(asset_id, n))

        _custom = self.settings.custom_categories or []
        _hidden = getattr(self.settings, "hidden_base_categories", []) or []
        catm = menu.addMenu("Move to Category")
        for cat in get_categories(_custom, _hidden)[1:]:
            if cat != asset.category:
                catm.addAction(cat,
                    lambda checked=False, c=cat: self._change_category(asset_id, c))

        menu.addSeparator()
        menu.addAction("Remove from Library", lambda: self._remove_asset(asset_id))
        menu.exec_(QCursor.pos())

    # ═══════════════════════════════════════════════════════
    # FILTERS
    # ═══════════════════════════════════════════════════════

    def _on_filter_changed(self, tokens: list):
        self._current_page = 0
        self.search_tokens = tokens
        self._render_content()

    def _update_search_completions(self):
        if not hasattr(self, '_search_bar'):
            return
        sug = set()
        for a in self.lib.all_assets():
            sug.add(a.name)
            sug.add(f"cat:{a.category}")
            if a.format:
                sug.add(f"fmt:{a.format}")
            for t in a.tags:
                sug.add(f"#{t}")
        cats = get_categories(self.settings.custom_categories,
                              getattr(self.settings, "hidden_base_categories", []))
        for c in cats[1:]:
            sug.add(f"cat:{c}")
        self._search_bar.set_completions(sorted(sug))

    def _register_pill_callback(self):
        """Wire global pill-click to add a tag token to the search bar."""
        import widgets as _w
        def _on_pill_click(tag: str):
            from search_bar import SearchToken
            self._search_bar.add_token(SearchToken("tag", tag))
        _w._pill_search_requested = _on_pill_click

    def _add_tag_token(self, tag: str):
        from search_bar import SearchToken
        self._search_bar.add_token(SearchToken("tag", tag))

    def _add_cat_token(self, cat: str):
        from search_bar import SearchToken
        self._search_bar.replace_token_kind("cat", SearchToken("cat", cat))

    def _on_page_changed(self, page: int):
        self._current_page = page
        self._render_content()
        # Scroll content area back to top
        self._content_area.verticalScrollBar().setValue(0)

    def _nav_prev_asset(self):
        """Select the previous asset in the current filtered+sorted list."""
        if not self.selected_id:
            return
        assets = self._filtered_assets()
        ids = [a.id for a in assets]
        if self.selected_id not in ids:
            return
        idx = ids.index(self.selected_id)
        if idx > 0:
            self._on_card_click(ids[idx - 1])

    def _nav_next_asset(self):
        """Select the next asset in the current filtered+sorted list."""
        if not self.selected_id:
            return
        assets = self._filtered_assets()
        ids = [a.id for a in assets]
        if self.selected_id not in ids:
            return
        idx = ids.index(self.selected_id)
        if idx < len(ids) - 1:
            self._on_card_click(ids[idx + 1])

    def _navigate_to_asset(self, asset_id: str):
        """Navigate directly to a specific asset by ID."""
        asset = self.lib.get(asset_id)
        if asset:
            self._selected_ids = {asset_id}
            self.selected_id = asset_id
            self._show_detail(asset)
            self._update_card_selection()

    def _unlink_assets(self, id_a: str, id_b: str):
        """Remove version link between two assets and refresh detail."""
        self.lib.unlink_assets(id_a, id_b)
        asset = self.lib.get(id_a)
        if asset:
            self._show_detail(asset)

    def _on_sort(self, key: str):
        if self.sort_by == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_by, self.sort_reverse = key, False
        self.settings.sort_by      = self.sort_by
        self.settings.sort_reverse = self.sort_reverse
        self.settings.save()
        self._update_sort_buttons()
        self._render_content()

    def _update_sort_buttons(self):
        labels = {"name":"Name","date":"Date","size":"Size","type":"Type","rating":"Rating"}
        _normal = getattr(self, '_ct_btn_style', '')
        # Build active style from current accent
        ar, ag, ab = self.settings.effective_accent()
        BH = 22
        _active = (
            f"QPushButton{{background:rgba({ar},{ag},{ab},15);color:rgb({ar},{ag},{ab});"
            f"border:1px solid rgba({ar},{ag},{ab},40);border-radius:3px;"
            f"font-size:11px;min-height:{BH}px;padding:0 6px;font-weight:bold;}}")
        for key, btn in self._sort_btns.items():
            is_a  = (self.sort_by == key)
            arrow = (" ↑" if self.sort_reverse else " ↓") if is_a else ""
            btn.setText(labels[key] + arrow)
            btn.setStyleSheet(_active if is_a else _normal)
        # Also update view mode + size buttons
        self._ct_btn_active = _active

    def _set_view(self, mode: str):
        self.view_mode = mode
        self.settings.view_mode = mode
        self.settings.save()
        self._update_view_buttons()
        self._render_content()

    def _update_view_buttons(self):
        _normal = getattr(self, '_ct_btn_style', '')
        _active = getattr(self, '_ct_btn_active', '')
        for btn, mode in [(self._grid_btn,"grid"),(self._list_btn,"list")]:
            btn.setStyleSheet(_active if self.view_mode == mode else _normal)

    def _current_card_size(self) -> str:
        return getattr(self, "_session_card_size", self.settings.card_size)

    def _set_card_size(self, size: str):
        """Session-only card size change — does NOT persist to disk.
        To change the persistent default, use Settings dialog."""
        self._session_card_size = size
        self._update_size_button()
        self._render_content()

    def _update_size_button(self):
        """Update the single cycling size button label."""
        if not hasattr(self, '_size_btn'):
            return
        abbr = {"Small": "S", "Medium": "M", "Large": "L", "X-Large": "XL"}
        self._size_btn.setText(abbr.get(self._current_card_size(), "M"))

    def _on_category(self, cat: str):
        self.category    = cat
        self.active_tags = []
        self._sidebar.set_active_category(cat)
        self._sidebar.rebuild_tags(self.lib, cat, [])
        self._render_content()

    def _on_tag_toggle(self, tag: str, active: bool):
        if active:
            # Add to active_tags AND to search bar token
            if tag not in self.active_tags:
                self.active_tags.append(tag)
            self._add_tag_token(tag)
        else:
            if tag in self.active_tags:
                self.active_tags.remove(tag)
            # Remove token from search bar via public API
            self._search_bar.remove_token("tag", tag)
        self._render_content()

    def _clear_tags(self):
        self.active_tags = []
        self._sidebar.rebuild_tags(self.lib, self.category, [])
        self._render_content()

    def _on_starred_toggle(self, on: bool):
        self.filter_starred = on
        self._current_page = 0
        if on:
            self.category = "All"
            self.active_collection = None
            self._sidebar.set_active_category("All")
        self._render_content()

    def _on_collection_select(self, coll: Optional[str]):
        self.active_collection = coll
        self._sidebar.rebuild_collections(self.lib, coll)
        self._render_content()

    def _select_all(self):
        assets = self._filtered_assets()
        self._selected_ids = {a.id for a in assets}
        self._render_content()

    # ═══════════════════════════════════════════════════════
    # ASSET EDITS
    # ═══════════════════════════════════════════════════════

    def _on_tag_added(self, asset_id: str, tag: str):
        from config import normalize_tag
        tag = normalize_tag(tag)
        asset = self.lib.get(asset_id)
        if asset and tag not in asset.tags:
            asset.tags.append(tag)
            self.lib.update(asset)
            # Refresh pills in-place — preserves edit mode
            self._detail_panel.refresh_tags(asset)
            self._sidebar.rebuild_tags(self.lib, self.category, self.active_tags)
            # New tag may need to appear in autocomplete suggestions
            self._update_search_completions()

    def _on_tag_removed(self, asset_id: str, tag: str):
        asset = self.lib.get(asset_id)
        if asset and tag in asset.tags:
            asset.tags.remove(tag)
            self.lib.update(asset)
            # Refresh pills in-place — preserves edit mode
            self._detail_panel.refresh_tags(asset)
            self._sidebar.rebuild_tags(self.lib, self.category, self.active_tags)
            self._update_search_completions()

    def _on_name_changed(self, asset_id: str, new_name: str):
        if not new_name: return
        asset = self.lib.get(asset_id)
        if asset and asset.name != new_name:
            asset.name = new_name
            self.lib.update(asset)
            self._render_content()

    def _on_cat_changed(self, asset_id: str, new_cat: str):
        asset = self.lib.get(asset_id)
        if asset:
            asset.category = new_cat
            self.lib.update(asset)
            self._full_refresh()

    def _on_notes_changed(self, asset_id: str, notes: str):
        asset = self.lib.get(asset_id)
        if asset:
            asset.notes = notes
            self.lib.update(asset)

    def _on_star_toggle(self, asset_id: str, starred: bool):
        """Card star toggled — persist and update detail panel if showing same asset."""
        asset = self.lib.get(asset_id)
        if asset:
            asset.starred = bool(starred)
            self.lib.update(asset)
            try: self.lib.save_now()
            except Exception: pass
        # Refresh detail panel if it's showing this asset
        if self.selected_id == asset_id:
            fresh = self.lib.get(asset_id)
            if fresh:
                self._show_detail(fresh)

    def _on_detail_star_changed(self, asset_id: str, starred: bool):
        """Detail panel star toggled — find and update the matching card visually."""
        from widgets import AssetCard
        content = self._content_area.widget()
        if content:
            for card in content.findChildren(AssetCard):
                if card.asset_id == asset_id:
                    card.set_starred(starred)
                    break

    def _on_rating_changed(self, asset_id: str, rating: int):
        asset = self.lib.get(asset_id)
        if asset:
            asset.rating = max(0, min(5, rating))
            self.lib.update(asset)

    # ═══════════════════════════════════════════════════════
    # ASSET ACTIONS
    # ═══════════════════════════════════════════════════════

    def _cleanup_asset_cache(self, asset_id: str):
        """Delete thumbnail, strip, and proxy files for an asset."""
        from preview    import get_strip_path, get_proxy_path, invalidate_strip, invalidate_proxy
        from thumbnails import thumb_cache_path
        invalidate_strip(asset_id)
        invalidate_proxy(asset_id)
        tp = thumb_cache_path(asset_id)
        if tp.exists():
            tp.unlink()
        self._thumb_cache.pop(asset_id, None)
        log_debug(f"[Cache] cleaned up {asset_id}")

    def _remove_asset(self, asset_id: str):
        if self.settings.confirm_before_delete:
            asset = self.lib.get(asset_id)
            name  = asset.name if asset else asset_id
            if QMessageBox.question(self, "Remove Asset",
                    f"Remove '{name}' from library?\n(File stays on disk.)",
                    QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        self._cleanup_asset_cache(asset_id)
        self.lib.remove(asset_id)
        self._selected_ids.discard(asset_id)
        if self.selected_id == asset_id:
            self.selected_id = None
            self._detail_panel.show_placeholder()
        self._full_refresh()

    def _delete_selected(self):
        if self._selected_ids:
            if len(self._selected_ids) > 1:
                self._batch_remove()
            elif self.selected_id:
                self._remove_asset(self.selected_id)

    def _open_file(self, asset_id: str):
        dbl_action = getattr(self.settings, 'double_click_action', 'open')
        if dbl_action == 'nothing':
            return
        if dbl_action == 'explorer':
            self._show_in_explorer_id(asset_id)
            return
        if dbl_action == 'copy_path':
            asset = self.lib.get(asset_id)
            if asset:
                QApplication.clipboard().setText(str(asset.path))
                self._status_label.setText(f"  Copied: {asset.path}")
            return
        asset = self.lib.get(asset_id)
        if not asset: return
        p = Path(asset.path)
        if not p.exists():
            QMessageBox.warning(self, "File Not Found", f"Cannot find:\n{asset.path}")
            return
        # Determine configured viewer for this file type
        viewer = ""
        if asset.file_type == "video":
            viewer = getattr(self.settings, 'viewer_video', '').strip()
        elif asset.file_type == "sequence":
            viewer = getattr(self.settings, 'viewer_sequence', '').strip()
        elif asset.file_type == "image":
            viewer = getattr(self.settings, 'viewer_image', '').strip()

        # Try configured viewer first
        if viewer:
            viewer_path = Path(viewer)
            if viewer_path.exists():
                try:
                    subprocess.Popen([str(viewer_path), str(p)])
                    self._status_label.setText(f"  Opening with {viewer_path.stem}…")
                    return
                except Exception as e:
                    print(f"[Viewer] Launch failed: {e}")
                    # Fall through to system default
            else:
                # Viewer configured but not found — warn and offer settings
                reply = QMessageBox.warning(self, "Viewer Not Found",
                    f"Configured viewer not found:\n{viewer}\n\n"
                    f"Open with system default instead?",
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Open)
                if reply == QMessageBox.No:
                    return
                if reply == QMessageBox.Open:
                    self._open_settings()
                    return
                # Yes → fall through to system default

        # System default fallback
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            QMessageBox.critical(self, "Open Error", f"Could not open file:\n{e}")

    def _open_selected_file(self):
        if self.selected_id: self._open_file(self.selected_id)

    def _show_in_explorer_id(self, asset_id: str):
        asset = self.lib.get(asset_id)
        if asset: self._show_in_explorer(asset)

    def _show_in_explorer(self, asset: Asset):
        p = Path(asset.path)
        if not p.exists():
            QMessageBox.warning(self, "File Not Found",
                f"Cannot locate file:\n{asset.path}")
            return
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", f"/select,{p}"])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p.parent)])
        except Exception as e:
            QMessageBox.warning(self, "Explorer Error", f"Could not open:\n{e}")

    def _show_selected_in_explorer(self):
        if self.selected_id:
            asset = self.lib.get(self.selected_id)
            if asset: self._show_in_explorer(asset)

    def _copy_path(self, asset: Asset):
        QApplication.clipboard().setText(str(asset.path))
        self._status_label.setText(f"  ✓  Copied: {asset.path}")

    def _copy_selected_path(self):
        if self.selected_id:
            asset = self.lib.get(self.selected_id)
            if asset: self._copy_path(asset)

    def _change_category(self, asset_id: str, new_cat: str):
        asset = self.lib.get(asset_id)
        if asset:
            asset.category = new_cat
            self.lib.update(asset)
            self._full_refresh()

    def _add_to_collection(self, asset_id: str, coll_name: str):
        self.lib.add_to_collection(coll_name, asset_id)
        self._sidebar.rebuild_collections(self.lib, self.active_collection)
        if self.selected_id == asset_id:
            a = self.lib.get(asset_id)
            if a: self._show_detail(a)

    def _remove_from_collection(self, asset_id: str, coll_name: str):
        self.lib.remove_from_collection(coll_name, asset_id)
        self._sidebar.rebuild_collections(self.lib, self.active_collection)
        if self.selected_id == asset_id:
            a = self.lib.get(asset_id)
            if a: self._show_detail(a)

    def _open_tag_editor(self, asset: Asset):
        dlg = TagEditorDialog(asset, self.lib, self)
        dlg.exec_()
        if self.selected_id == asset.id:
            fresh = self.lib.get(asset.id)
            if fresh: self._show_detail(fresh)
        self._full_refresh()

    def _edit_selected_tags(self):
        if self.selected_id:
            asset = self.lib.get(self.selected_id)
            if asset: self._open_tag_editor(asset)

    def _regen_preview(self, asset_id: str):
        """Invalidate caches then re-queue generation.
        For images: regenerate thumbnail only.
        For video/sequence: regenerate strip + proxy."""
        from preview import invalidate_proxy
        invalidate_strip(asset_id)
        invalidate_proxy(asset_id)
        # Also clear thumbnail cache so it regenerates
        from thumbnails import thumb_cache_path
        try: thumb_cache_path(asset_id).unlink(missing_ok=True)
        except Exception: pass
        if asset_id in self._thumb_cache:
            del self._thumb_cache[asset_id]
        asset = self.lib.get(asset_id)
        if asset:
            self._start_strip_thread([asset])
            self._show_detail(asset)

    def _set_poster_frame(self, asset_id: str):
        """Extract a specific frame from a video and save as thumbnail."""
        asset = self.lib.get(asset_id)
        if not asset:
            return
        fps = asset.fps or 24.0
        total_frames = asset.frame_count or int((asset.duration_s or 10.0) * fps)
        from PySide2.QtWidgets import QInputDialog
        frame_num, ok = QInputDialog.getInt(
            self, "Set Poster Frame",
            f"Frame number (0 – {total_frames}):",
            value=total_frames // 2, min=0, max=total_frames)
        if not ok:
            return
        import preview as _pv
        if not _pv.FFMPEG:
            return
        from thumbnails import thumb_cache_path
        from config import THUMB_W, THUMB_H
        import subprocess
        out = thumb_cache_path(asset_id)
        secs = frame_num / fps
        seek = f"{int(secs//3600):02d}:{int((secs%3600)//60):02d}:{secs%60:06.3f}"
        cmd = [_pv.FFMPEG, "-y", "-ss", seek, "-i", str(asset.path),
               "-vframes", "1",
               "-vf", f"scale={THUMB_W}:{THUMB_H}:force_original_aspect_ratio=decrease,"
                      f"pad={THUMB_W}:{THUMB_H}:(ow-iw)/2:(oh-ih)/2:color=0a0a12",
               str(out)]
        try:
            r = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15)
            if r.returncode == 0 and out.exists():
                self._thumb_cache.pop(asset_id, None)
                self._status_label.setText(
                    f"  Poster frame set at {secs:.1f}s for {asset.name}")
                self._render_content()
                self._show_detail(asset)
        except Exception as e:
            log_error(f"[Poster] {e}")

    # ═══════════════════════════════════════════════════════
    # BATCH
    # ═══════════════════════════════════════════════════════

    def _batch_category(self):
        from config import get_categories as _gc
        _custom = self.settings.custom_categories or []
        _hidden = getattr(self.settings, "hidden_base_categories", []) or []
        _cats = _gc(_custom, _hidden)[1:]  # skip "All"
        cat, ok = QInputDialog.getItem(self, "Batch: Move to Category",
            "Select category:", _cats, 0, False)
        if not ok: return
        self.lib.begin_batch()
        for aid in self._selected_ids:
            a = self.lib.get(aid)
            if a:
                a.category = cat
                self.lib.update(a)
        self.lib.end_batch()
        self._full_refresh()

    def _batch_add_tag(self):
        from config import normalize_tag
        tag, ok = QInputDialog.getText(self, "Batch: Add Tag", "Tag to add:")
        if not ok or not tag.strip(): return
        tag = normalize_tag(tag)
        self.lib.begin_batch()
        for aid in self._selected_ids:
            a = self.lib.get(aid)
            if a and tag not in a.tags:
                a.tags.append(tag)
                self.lib.update(a)
        self.lib.end_batch()
        self._full_refresh()

    def _batch_remove_tag(self):
        tag, ok = QInputDialog.getText(self, "Batch: Remove Tag", "Tag to remove:")
        if not ok or not tag.strip(): return
        tag = tag.strip()
        self.lib.begin_batch()
        for aid in self._selected_ids:
            a = self.lib.get(aid)
            if a and tag in a.tags:
                a.tags.remove(tag)
                self.lib.update(a)
        self.lib.end_batch()
        self._full_refresh()

    def _batch_add_to_collection(self):
        colls = list(self.lib.get_collections().keys())
        if not colls:
            # No collections yet — offer to create one
            reply = QMessageBox.question(self, "Collections",
                "No collections yet. Create one now?",
                QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._batch_new_collection()
            return
        coll, ok = QInputDialog.getItem(self, "Batch: Add to Collection",
            "Select collection:", sorted(colls), 0, False)
        if ok:
            self.lib.begin_batch()
            for aid in self._selected_ids:
                self.lib.add_to_collection(coll, aid)
            self.lib.end_batch()
            self._full_refresh()

    def _batch_new_collection(self):
        """Create a new collection and add all selected assets to it."""
        name, ok = QInputDialog.getText(self, "New Collection from Selection",
            "Collection name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not self.lib.create_collection(name):
            QMessageBox.warning(self, "Error", f'Collection "{name}" already exists.')
            return
        self.lib.begin_batch()
        for aid in self._selected_ids:
            self.lib.add_to_collection(name, aid)
        self.lib.end_batch()
        self.active_collection = name
        self._full_refresh()
        self._status_label.setText(
            f"  ✓  Collection '{name}' created with {len(self._selected_ids)} asset(s)")

    def _batch_link_versions(self):
        """Link all selected assets as versions of each other."""
        ids = list(self._selected_ids)
        if len(ids) < 2:
            return
        self.lib.begin_batch()
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                self.lib.link_assets(ids[i], ids[j])
        self.lib.end_batch()
        names = [self.lib.get(i).name for i in ids[:3] if self.lib.get(i)]
        self._status_label.setText(
            f"  Linked {len(ids)} assets as versions: {', '.join(names)}…")
        if self.selected_id:
            asset = self.lib.get(self.selected_id)
            if asset:
                self._show_detail(asset)

    def _batch_remove(self):
        n = len(self._selected_ids)
        if QMessageBox.question(self, "Batch Remove",
                f"Remove {n} assets? (Files stay on disk.)",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        for aid in list(self._selected_ids):
            self._cleanup_asset_cache(aid)
            self.lib.remove(aid)
        self._selected_ids.clear()
        self.selected_id = None
        self._detail_panel.show_placeholder()
        self._full_refresh()

    # ═══════════════════════════════════════════════════════
    # SAVED SEARCHES
    # ═══════════════════════════════════════════════════════

    def _save_search(self):
        """Save the current search bar tokens as a named preset."""
        tokens = self._search_bar.get_tokens()
        if not tokens:
            QMessageBox.information(self, "Save Search",
                "Nothing to save — add some filters first.")
            return
        # Build a readable default name from tokens
        default_name = " + ".join(t.label for t in tokens[:4])
        name, ok = QInputDialog.getText(
            self, "Save Search Preset", "Preset name:", text=default_name)
        if not ok or not name.strip():
            return
        entry = {
            "name": name.strip(),
            "tokens": [{"kind": t.kind, "value": t.value} for t in tokens],
        }
        if self.settings.saved_searches is None:
            self.settings.saved_searches = []
        self.settings.saved_searches.append(entry)
        self.settings.save()
        self._full_refresh()
        self._status_label.setText(f"  Search preset '{name.strip()}' saved")

    def _load_search(self, index: int):
        """Restore a saved search preset by index."""
        searches = getattr(self.settings, 'saved_searches', []) or []
        if index < 0 or index >= len(searches):
            return
        entry = searches[index]
        from search_bar import SearchToken
        self._search_bar.clear_all()
        for td in entry.get("tokens", []):
            token = SearchToken(td["kind"], td["value"])
            self._search_bar.add_token(token)

    def _delete_search(self, index: int):
        """Delete a saved search preset by index."""
        searches = getattr(self.settings, 'saved_searches', []) or []
        if index < 0 or index >= len(searches):
            return
        name = searches[index].get("name", "")
        searches.pop(index)
        self.settings.saved_searches = searches
        self.settings.save()
        self._full_refresh()
        self._status_label.setText(f"  Search preset '{name}' deleted")

    def _rename_search(self, index: int):
        """Rename a saved search preset."""
        searches = getattr(self.settings, 'saved_searches', []) or []
        if index < 0 or index >= len(searches):
            return
        old_name = searches[index].get("name", "")
        new_name, ok = QInputDialog.getText(
            self, "Rename Search Preset", f"New name:", text=old_name)
        if not ok or not new_name.strip():
            return
        searches[index]["name"] = new_name.strip()
        self.settings.saved_searches = searches
        self.settings.save()
        self._full_refresh()

    # ═══════════════════════════════════════════════════════
    # COLLECTIONS
    # ═══════════════════════════════════════════════════════

    def _add_category(self):
        name, ok = QInputDialog.getText(self, "Add Category", "Category name:")
        if ok and name.strip():
            name = name.strip()
            from config import BASE_CATEGORIES
            if name in BASE_CATEGORIES:
                QMessageBox.warning(self, "Category", f"'{name}' already exists.")
                return
            if self.settings.custom_categories is None:
                self.settings.custom_categories = []
            if name not in self.settings.custom_categories:
                self.settings.custom_categories.append(name)
                self.settings.save()
                self._full_refresh()

    def _delete_category(self, name: str):
        from config import BASE_CATEGORIES
        if name in BASE_CATEGORIES:
            QMessageBox.warning(self, "Category",
                "Cannot delete built-in categories.")
            return
        # Block deletion if any assets still use this category
        assets_in_cat = [a for a in self.lib.all_assets() if a.category == name]
        if assets_in_cat:
            QMessageBox.warning(self, "Category Not Empty",
                f"\"{name}\" still has {len(assets_in_cat)} asset(s).\n\n"
                "Move or delete all assets in this category first,\n"
                "then you can remove it.")
            return
        if QMessageBox.question(self, "Delete Category",
                f"Delete empty category '{name}'?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            if self.settings.custom_categories and name in self.settings.custom_categories:
                self.settings.custom_categories.remove(name)
                self.settings.save()
            if self.category == name:
                self.category = "All"
            self._full_refresh()

    def _new_collection(self):
        name, ok = QInputDialog.getText(self, "New Collection", "Collection name:")
        if ok and name.strip():
            if not self.lib.create_collection(name.strip()):
                QMessageBox.warning(self, "Error", f'Collection "{name}" already exists.')
            else:
                self.active_collection = name.strip()
                self._full_refresh()

    def _import_collection(self):
        """Import a .pixcol collection file shared from another studio."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Collection", "",
            "Pixel Attic Collections (*.pixcol);;JSON Files (*.json);;All Files (*.*)")
        if not path: return
        imported, skipped, coll_name, err = self.lib.import_collection(Path(path))
        if err:
            QMessageBox.critical(self, "Import Failed", f"Could not import:\n{err}")
            return
        self.active_collection = coll_name
        self._full_refresh()
        QMessageBox.information(
            self, "Collection Imported",
            f"✓  Collection '{coll_name}' imported\n\n"
            f"  {imported} new assets added\n"
            f"  {skipped} already existed (skipped)")

    def _export_collection(self, name: str):
        """Export a collection as a .pixcol file for sharing."""
        safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export Collection '{name}'",
            f"{safe}.pixcol",
            "Pixel Attic Collections (*.pixcol);;JSON Files (*.json)")
        if not path: return
        try:
            self.lib.export_collection(name, Path(path))
            count = self.lib.collection_count(name)
            self._status_label.setText(
                f"  Exported '{name}' ({count} assets) → {Path(path).name}")
            QMessageBox.information(
                self, "Collection Exported",
                f"✓  '{name}' exported successfully\n\n"
                f"  {count} assets\n"
                f"  File: {path}\n\n"
                f"Share the .pixcol file — teammates can import it\n"
                f"via the Import button in the Collections panel.")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Could not export:\n{e}")

    def _delete_collection(self, name: str):
        if QMessageBox.question(self, "Delete Collection",
                f"Delete '{name}'? Assets stay in library.",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.lib.delete_collection(name)
            if self.active_collection == name:
                self.active_collection = None
            self._full_refresh()

    def _rename_collection(self, old_name: str):
        new_name, ok = QInputDialog.getText(
            self, "Rename Collection", f"New name for '{old_name}':")
        if ok and new_name.strip():
            if not self.lib.rename_collection(old_name, new_name.strip()):
                QMessageBox.warning(self, "Error", "Could not rename.")
            else:
                if self.active_collection == old_name:
                    self.active_collection = new_name.strip()
                self._full_refresh()

    # ═══════════════════════════════════════════════════════
    # IMPORT
    # ═══════════════════════════════════════════════════════

    def _find_duplicates(self):
        """Scan library for content-identical assets (by hash) and show a dialog."""
        prog = QProgressDialog("Scanning library for duplicates…", "Cancel", 0, 0, self)
        prog.setWindowTitle("Duplicate Scan")
        prog.setMinimumDuration(0)
        prog.setValue(0)
        prog.setRange(0, 0)  # indeterminate
        QApplication.processEvents()

        def _progress(i, total):
            prog.setRange(0, total)
            prog.setValue(i)
            prog.setLabelText(f"Hashing file {i+1} of {total}…")
            QApplication.processEvents()

        newly_hashed = self.lib.compute_missing_hashes(progress_cb=_progress)
        prog.close()

        dups = self.lib.find_duplicates()
        if not dups:
            msg = "No duplicate assets found."
            if newly_hashed:
                msg += f"\n\nScanned {newly_hashed} new file(s)."
            QMessageBox.information(self, "No Duplicates", msg)
            return

        # Build summary dialog
        from PySide2.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Duplicates Found — {len(dups)} group(s)")
        dlg.setMinimumSize(560, 420)
        ll = QVBoxLayout(dlg)
        ll.addWidget(QLabel(f"Found {len(dups)} group(s) of identical files. Select assets to remove:"))
        lst = QListWidget()
        lst.setSelectionMode(QListWidget.MultiSelection)
        asset_map = {}
        for group in dups:
            # Sort: keep the one with the shortest path (likely the original)
            group_sorted = sorted(group, key=lambda a: len(a.path))
            for j, a in enumerate(group_sorted):
                label = f"[Group] {a.name}  —  {a.path}"
                if j == 0:
                    label = f"  KEEP   {a.name}  —  {a.path}"
                else:
                    label = f"  DUP    {a.name}  —  {a.path}"
                item = QListWidgetItem(label)
                item.setForeground(QColor(100,116,139) if j == 0 else QColor(248,113,113))
                lst.addItem(item)
                asset_map[lst.count()-1] = (a.id, j > 0)  # (id, is_dup)
        ll.addWidget(lst)
        ll.addWidget(QLabel("Red items are duplicates. Select items and click Remove to delete from library."))
        btn_row = QHBoxLayout()
        select_dups = QPushButton("Select All Duplicates")
        select_dups.clicked.connect(lambda: [
            lst.item(i).setSelected(asset_map[i][1])
            for i in range(lst.count()) if i in asset_map])
        remove_btn = QPushButton("Remove Selected")
        remove_btn.setObjectName("btn_accent")
        close_btn  = QPushButton("Close")
        btn_row.addWidget(select_dups)
        btn_row.addStretch()
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(close_btn)
        ll.addLayout(btn_row)
        close_btn.clicked.connect(dlg.accept)
        def _remove_selected():
            to_remove = [asset_map[i][0] for i in range(lst.count())
                         if i in asset_map and lst.item(i).isSelected()]
            if not to_remove: return
            for aid in to_remove:
                self._cleanup_asset_cache(aid)
                self.lib.remove(aid)
            dlg.accept()
            self._full_refresh()
            self._status_label.setText(f"  ✓  Removed {len(to_remove)} duplicate(s)")
        remove_btn.clicked.connect(_remove_selected)
        dlg.exec_()

    def _import_files(self):
        from config import ALL_EXT, detect_sequences
        ext_filter = "VFX Assets (" + " ".join(f"*{e}" for e in ALL_EXT) + ")"
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import VFX Assets", "",
            ext_filter + ";;All Files (*.*)")
        if paths:
            items = detect_sequences([Path(p) for p in paths])
            self._show_import_dialog(items)

    def _import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Import Folder")
        if not folder: return
        from config import ALL_EXT, detect_sequences
        found = [p for p in Path(folder).rglob("*")
                 if p.is_file() and p.suffix.lower() in ALL_EXT]
        if not found:
            QMessageBox.information(self, "Import",
                f"No VFX files found in:\n{folder}")
            return
        # Group image sequences → fewer cards
        items = detect_sequences(found)
        n_seq  = sum(1 for x in items if not isinstance(x, Path))
        n_lone = sum(1 for x in items if isinstance(x, Path))
        if n_seq:
            msg = (f"Found {n_seq} sequence(s) and {n_lone} individual file(s) "
                   f"(from {len(found)} total files).\n\n"
                   f"Each sequence will be imported as one card.")
            QMessageBox.information(self, "Sequences Detected", msg)
        self._show_import_dialog(items)

    def _show_import_dialog(self, paths: list):
        _custom = self.settings.custom_categories or []
        _hidden = getattr(self.settings, "hidden_base_categories", []) or []
        dlg = ImportDialog(paths, "Misc", self,
                           custom_categories=_custom, hidden_categories=_hidden)
        if dlg.exec_() == QDialog.Accepted:
            per_asset = dlg.get_result()   # list of per-asset dicts
            auto_res  = dlg.get_auto_res()
            self._run_import(paths, per_asset, auto_res)

    def _run_import(self, paths: list, per_asset: list, auto_res: bool):
        from config import SequenceGroup, normalize_tag
        total = len(paths)
        prog = QProgressDialog(
            f"Importing {total} item(s)…", "Cancel",
            0, total, self)
        prog.setWindowTitle("Import")
        prog.setMinimumDuration(0)
        prog.setValue(0)

        imported = errors = skipped = 0
        _strip_queue = []
        _error_details = []
        existing     = {a.path: a for a in self.lib.all_assets()}
        _apply_all   = None
        _last_cat    = "Misc"

        self.lib.begin_batch()

        for i, item in enumerate(paths):
            is_seq = isinstance(item, SequenceGroup)
            p      = item.base_path if is_seq else item
            label  = item.name if is_seq else item.name

            # Per-asset metadata from dialog
            meta = per_asset[i] if i < len(per_asset) else {}
            cat        = meta.get("category", "Misc")
            extra_tags = meta.get("tags", [])
            meta_note  = meta.get("notes", "")
            _last_cat  = cat

            # ── Progress update with phase indicator ──────────────────────
            prog.setValue(i)
            phase = "Validating" if i < total * 0.1 else "Importing"
            prog.setLabelText(
                f"{phase}: {label}\n"
                f"({i + 1} of {total}  ·  {imported} ok  ·  {skipped} skipped  ·  {errors} errors)")
            QApplication.processEvents()
            if prog.wasCanceled():
                log_info(f"[Import] cancelled by user at item {i + 1}/{total}")
                break

            if str(p) in existing:
                if _apply_all is False:
                    skipped += 1
                    log_debug(f"[Import] skipped (skip-all): {label}")
                    continue
                elif _apply_all is True:
                    pass  # overwrite — fall through
                else:
                    prog.hide()
                    from PySide2.QtWidgets import QDialog
                    dlg = QMessageBox(self)
                    dlg.setWindowTitle("Duplicate Asset")
                    dlg.setIcon(QMessageBox.Warning)
                    dlg.setText(
                        f"<b>{label}</b> is already in your library.<br><br>"
                        "What would you like to do?")
                    ow_btn  = dlg.addButton("Overwrite",     QMessageBox.AcceptRole)
                    sk_btn  = dlg.addButton("Skip",          QMessageBox.RejectRole)
                    owa_btn = dlg.addButton("Overwrite All", QMessageBox.YesRole)
                    ska_btn = dlg.addButton("Skip All",      QMessageBox.NoRole)
                    can_btn = dlg.addButton("Cancel Import", QMessageBox.DestructiveRole)
                    dlg.exec_()
                    prog.show()
                    clicked = dlg.clickedButton()
                    if clicked == can_btn:
                        log_info(f"[Import] cancelled by user at {label}")
                        break
                    elif clicked == sk_btn:
                        skipped += 1
                        continue
                    elif clicked == ska_btn:
                        _apply_all = False
                        skipped += 1
                        continue
                    elif clicked == owa_btn:
                        _apply_all = True
                        # fall through to overwrite
                    # else ow_btn — overwrite once, fall through

                # Overwrite: clean up old caches then remove
                old_asset = existing[str(p)]
                self._cleanup_asset_cache(old_asset.id)
                self.lib.remove(old_asset.id)
                log_info(f"[Import] overwriting {label}")

            try:
                if is_seq:
                    asset = Asset.from_sequence(item, category=cat)
                else:
                    asset = Asset.from_path(p, category=cat)
                # Content hash for duplicate detection
                try:
                    if Path(asset.path).exists():
                        asset.content_hash = self.lib.hash_file(asset.path)
                except Exception: pass

                for t in extra_tags:
                    nt = normalize_tag(t) if t else t
                    if nt and nt not in asset.tags:
                        asset.tags.append(nt)
                if not auto_res:
                    asset.tags = [t for t in asset.tags
                                  if t not in ("8K","4K","2K","HD")]
                if meta_note:
                    asset.notes = meta_note
                # Only pre-generate thumb for images (fast, no ffmpeg)
                # Video/sequence thumbs are generated in background thread
                if asset.file_type not in ("video", "sequence"):
                    self._get_thumb(asset)
                self.lib.add(asset)
                # Queue video/sequence for background strip+thumb+proxy
                if asset.file_type in ("video", "sequence") and Path(asset.path).exists():
                    _strip_queue.append(asset)
                imported += 1
                log_info(f"[Import] imported: {label}")

            except FileNotFoundError as e:
                _error_details.append((label, f"File not found: {e}"))
                log_error(f"[Import] {label}: {e}")
                errors += 1
            except PermissionError as e:
                _error_details.append((label, f"Permission denied: {e}"))
                log_error(f"[Import] {label}: {e}")
                errors += 1
            except ValueError as e:
                _error_details.append((label, f"Invalid file: {e}"))
                log_error(f"[Import] {label}: {e}")
                errors += 1
            except Exception as e:
                _error_details.append((label, str(e)))
                log_error(f"[Import] {label}: {e}")
                errors += 1

        prog.setValue(total)
        self.lib.end_batch()
        self.category = _last_cat
        parts = [f"✓ {imported} imported"]
        if skipped: parts.append(f"{skipped} skipped")
        if errors:  parts.append(f"{errors} errors")
        if _strip_queue:
            parts.append(f"generating {len(_strip_queue)} previews…")
        self._status_label.setText("  " + "  ·  ".join(parts))

        # ── Show error summary dialog if there were any failures ──────────
        if _error_details and getattr(self.settings, 'show_import_summary', True):
            err_dlg = QMessageBox(self)
            err_dlg.setWindowTitle(f"Import — {errors} Error(s)")
            err_dlg.setIcon(QMessageBox.Warning)
            err_dlg.setText(
                f"<b>{imported} asset(s) imported successfully.</b><br>"
                f"{errors} file(s) could not be imported:<br>")
            # Build detailed text list
            detail_lines = []
            for name, err in _error_details[:50]:  # cap at 50 to avoid huge dialog
                detail_lines.append(f"• {name}\n  {err}")
            if len(_error_details) > 50:
                detail_lines.append(f"\n… and {len(_error_details) - 50} more")
            err_dlg.setDetailedText("\n\n".join(detail_lines))
            err_dlg.exec_()

        # Generate strips in background thread (if auto-proxy enabled)
        if _strip_queue and getattr(self.settings, 'auto_generate_proxies', True):
            self._start_strip_thread(_strip_queue)
        self._full_refresh()

    def _start_strip_thread(self, assets: list):
        """Generate scrub strips for a list of assets in a background QThread."""
        # ── Guard: stop any existing thread before starting a new one ────
        if hasattr(self, "_strip_thread") and self._strip_thread is not None:
            try:
                self._strip_thread.quit()
                self._strip_thread.wait(2000)
            except Exception:
                pass
            self._strip_thread = None
            self._strip_worker = None

        from PySide2.QtCore import QThread, QObject, Signal as _Signal

        class StripWorker(QObject):
            done     = _Signal(str)   # asset_id when one strip finishes
            finished = _Signal(int)   # total count when all done

            def __init__(self, assets):
                super().__init__()
                self._assets = assets

            def run(self):
                count = 0
                for a in self._assets:
                    try:
                        from preview import generate_strip, generate_proxy
                        from logger  import log_info, log_error
                        if a.file_type == "image":
                            # Single image: just regenerate thumbnail, no strip/proxy
                            from thumbnails import thumb_cache_path
                            tc = thumb_cache_path(a.id)
                            try: tc.unlink(missing_ok=True)
                            except Exception: pass
                            from thumbnails import load_or_generate
                            load_or_generate(a)
                            count += 1
                            self.done.emit(a.id)
                            log_info(f"[Preview] thumb regen: {a.name}")
                            continue
                        # Generate thumbnail first (same ffmpeg, fast)
                        from thumbnails import load_or_generate, thumb_cache_path
                        _tc = thumb_cache_path(a.id)
                        if not _tc.exists():
                            load_or_generate(a)
                        # Generate scrub strip
                        strip = generate_strip(a)
                        # Generate proxy MP4
                        proxy = generate_proxy(a)
                        if strip or proxy or _tc.exists():
                            count += 1
                            self.done.emit(a.id)
                        if strip:
                            log_info(f"[Preview] strip ok: {a.name}")
                        if proxy:
                            log_info(f"[Preview] proxy ok: {a.name}")
                    except Exception as e:
                        log_error(f"[PreviewThread] {a.name}: {e}")
                self.finished.emit(count)

        thread  = QThread(self)
        worker  = StripWorker(assets)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        _done_count = [0]
        _total      = len(assets)

        def _on_done(asset_id: str):
            _done_count[0] += 1
            # Live progress in status bar
            self._status_label.setText(
                f"  Generating previews: {_done_count[0]} / {_total}…")
            # Bust thumb cache so card picks up the newly generated thumbnail
            self._thumb_cache.pop(asset_id, None)
            # Refresh the card in the grid (handles deleted cards gracefully)
            self._update_card_strip(asset_id)
            # Refresh detail panel if this asset is currently selected
            try:
                if self.selected_id == asset_id:
                    a = self.lib.get(asset_id)
                    if a: self._show_detail(a)
            except RuntimeError:
                pass  # widget deleted mid-update

        def _on_finished(count: int):
            self._status_label.setText(f"  ✓  {count} / {_total} preview(s) ready")
            # Full refresh guarantees every card shows its new thumbnail,
            # even if individual _on_done updates were missed (grid rebuild)
            self._full_refresh()
            try:
                thread.quit()
                thread.wait(2000)
            except Exception:
                pass
            self._strip_thread = None
            self._strip_worker = None

        worker.done.connect(_on_done)
        worker.finished.connect(_on_finished)
        thread.finished.connect(thread.deleteLater)
        # Keep references so GC doesn't kill them
        self._strip_thread = thread
        self._strip_worker = worker
        thread.start()

    def _update_card_strip(self, asset_id: str):
        """Find the card for asset_id, update its thumbnail and strip from disk.

        Uses AssetCard.update_thumbnail / update_strip which handle
        pixmap scaling, style reset, and strip frame parsing internally.
        Wrapped in try/except because the card may have been deleted
        if the grid was rebuilt while the background thread was running.
        """
        try:
            content = self._content_area.widget()
            if content is None:
                return
            for card in content.findChildren(AssetCard):
                if card.asset_id != asset_id:
                    continue
                # ── Update thumbnail if it now exists on disk ────────────
                from thumbnails import thumb_cache_path
                tc = thumb_cache_path(asset_id)
                if tc.exists() and card._thumb_pix is None:
                    card.update_thumbnail(tc)
                # ── Update strip if it exists ────────────────────────────
                sp = get_strip_path(asset_id)
                if sp.exists():
                    card.update_strip(sp)
                break
        except RuntimeError:
            # C++ object deleted — grid was rebuilt, card is gone.
            # _on_finished will do a full refresh anyway.
            pass

    # ═══════════════════════════════════════════════════════
    # SETTINGS
    # ═══════════════════════════════════════════════════════

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self.lib, self)
        if dlg.exec_() == QDialog.Accepted:
            self.settings = dlg.get_settings()
            self.settings.save()
            self.apply_theme(self.settings.theme, self.settings.accent_color)
            self.apply_font()
            self._apply_ffmpeg()
            self._apply_proxy_dir()
            # Apply new defaults — update session state
            self._session_card_size = self.settings.card_size
            self.view_mode = getattr(self.settings, "view_mode_default", "grid")
            self._update_size_button()
            self._update_view_buttons()
            self._update_sort_buttons()
            self._page_size_btn.setText(f"{self.settings.page_size}/page")
            log_info("[Settings] saved")
            self._full_refresh()

    def _apply_proxy_dir(self):
        """Apply custom proxy directory from settings."""
        set_proxy_dir(getattr(self.settings, "proxy_dir", "") or "")

    def _apply_ffmpeg(self):
        """Apply ffmpeg path from settings and update status bar."""
        import preview as _preview
        configured = getattr(self.settings, 'ffmpeg_path', '').strip()
        set_ffmpeg_path(configured)
        # Re-read the module-level FFMPEG after update
        ff = _preview.FFMPEG
        if ff:
            self._stat_ffmpeg.setText(f"  ffmpeg: {ff}" if configured else "")
            self._stat_ffmpeg.setStyleSheet(
                "color: rgb(52,211,153); font-size: 11px; padding-right: 8px;")
        else:
            self._stat_ffmpeg.setText("⚠ ffmpeg not found — scrub previews disabled")
            self._stat_ffmpeg.setStyleSheet(
                "color: rgb(248,113,113); font-size: 11px; padding-right: 8px;")

    def apply_theme(self, theme_name: str, accent_name: str):
        self.setStyleSheet(build_stylesheet(theme_name, accent_name))
        # Sync accent colour into detail panel buttons
        from settings import ACCENT_COLORS
        a = ACCENT_COLORS.get(accent_name, ACCENT_COLORS["Orange"])
        accent_rgb = f"{a[0]},{a[1]},{a[2]}"
        if hasattr(self, '_detail_panel'):
            self._detail_panel.apply_accent(accent_rgb)
        # Update logo color
        if hasattr(self, '_logo_lbl'):
            self._logo_lbl.setStyleSheet(
                f"#app_name{{font-size:14px;font-weight:bold;letter-spacing:2px;"
                f"color:rgb({a[0]},{a[1]},{a[2]});padding:0 8px;}}")

    def apply_font(self):
        if self.settings.font_name == "Default":
            return
        try:
            fam = self.settings.font_name
            sz  = getattr(self.settings, 'font_size', 13)
            QApplication.setFont(QFont(fam, sz))
        except Exception as e:
            log_error(f"[Font] {e}")

    def _reload_library(self):
        self.lib._assets.clear()
        self.lib._collections.clear()
        self.lib._load()
        self._full_refresh()

    # ═══════════════════════════════════════════════════════
    # RESIZE
    # ═══════════════════════════════════════════════════════

    def closeEvent(self, event):
        """Clean shutdown: stop background threads, kill VLC, save state."""
        # Stop strip generation thread
        if hasattr(self, "_strip_thread") and self._strip_thread is not None:
            try:
                self._strip_thread.quit()
                self._strip_thread.wait(1500)
            except Exception:
                pass

        # Stop any active VLC player in the detail panel
        try:
            scroll = self._detail_panel._scroll.widget()
            if scroll:
                for child in scroll.findChildren(QWidget):
                    player = getattr(child, "_vlc_player", None)
                    timer  = getattr(child, "_vlc_timer",  None)
                    if timer:
                        try: timer.stop()
                        except Exception: pass
                    if player:
                        try:
                            player.stop()
                            player.release()
                        except Exception: pass
                    inst = getattr(child, "_vlc_inst", None)
                    if inst:
                        try: inst.release()
                        except Exception: pass
        except Exception:
            pass

        # Save window geometry and maximized state
        self.settings.window_maximized = self._is_maximized
        if not self._is_maximized:
            geo = self.geometry()
            self.settings.window_x = geo.x()
            self.settings.window_y = geo.y()
            self.settings.window_w = geo.width()
            self.settings.window_h = geo.height()
        # Save splitter positions
        try:
            ss = self._splitter.sizes()
            if len(ss) >= 2:
                self.settings.sidebar_width = ss[0]
            cs = self._content_splitter.sizes()
            if len(cs) >= 2:
                self.settings.detail_width = cs[1]
        except Exception:
            pass
        self.settings.last_category = self.category
        self.settings.save()
        # Flush any pending library changes immediately
        self.lib.save_now()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Freeze grid during resize
        content = self._content_area.widget()
        from widgets import VirtualGrid
        if isinstance(content, VirtualGrid):
            content.freeze()
        if not hasattr(self, "_resize_timer"):
            self._resize_timer = QTimer(self)
            self._resize_timer.setSingleShot(True)
            def _on_resize_end():
                c = self._content_area.widget()
                if isinstance(c, VirtualGrid):
                    c.unfreeze()
                self._render_content()
            self._resize_timer.timeout.connect(_on_resize_end)
        self._resize_timer.start(300)

    def _on_splitter_moved(self, pos=0, index=0):
        """Freeze grid + video during drag, re-render only after user stops."""
        # Freeze VirtualGrid
        content = self._content_area.widget()
        from widgets import VirtualGrid
        if isinstance(content, VirtualGrid):
            content.freeze()

        # Freeze video container — lock its size so VLC doesn't re-render
        if not getattr(self, '_video_frozen', False):
            self._video_frozen = True
            try:
                scroll = self._detail_panel._scroll.widget()
                if scroll:
                    for child in scroll.findChildren(QWidget):
                        if child.objectName() == "video_container":
                            sz = child.size()
                            child.setFixedSize(sz)
                            self._frozen_video_container = child
                            break
            except Exception:
                pass

        if not hasattr(self, "_splitter_timer"):
            self._splitter_timer = QTimer(self)
            self._splitter_timer.setSingleShot(True)
            self._splitter_timer.timeout.connect(self._on_drag_end)
            self._last_grid_cols = 0
        self._splitter_timer.start(300)

    def _on_drag_end(self):
        """Splitter drag ended — unfreeze grid + video."""
        # Unfreeze VirtualGrid
        content = self._content_area.widget()
        from widgets import VirtualGrid
        if isinstance(content, VirtualGrid):
            content.unfreeze()

        # Unfreeze video container — release fixed size
        if getattr(self, '_video_frozen', False):
            self._video_frozen = False
            c = getattr(self, '_frozen_video_container', None)
            if c:
                c.setMinimumSize(0, 0)
                c.setMaximumSize(16777215, 16777215)  # QWIDGETSIZE_MAX
                self._frozen_video_container = None

        self._check_rerender_needed()

    def _toggle_sidebar(self):
        """Toggle sidebar visibility — instant, no re-render."""
        self._splitter.blockSignals(True)
        sizes = self._splitter.sizes()
        if sizes[0] > 0:
            self._sidebar_saved_width = sizes[0]
            self._splitter.setSizes([0, sizes[0] + sizes[1]])
        else:
            w = getattr(self, '_sidebar_saved_width', 215)
            self._splitter.setSizes([w, max(400, sizes[1] - w)])
        self._splitter.blockSignals(False)

    def _check_rerender_needed(self):
        """Only re-render if the number of grid columns changed."""
        cw, ch = CARD_SIZES.get(self._current_card_size(), CARD_SIZES["Medium"])
        avail = max(self._content_area.width() - 24, cw + 8)
        new_cols = max(1, avail // (cw + 8))
        if new_cols != getattr(self, '_last_grid_cols', 0):
            self._last_grid_cols = new_cols
            self._render_content()

    # ═══════════════════════════════════════════════════════
    # DRAG & DROP IMPORT
    # ═══════════════════════════════════════════════════════

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        from config import ALL_EXT, detect_sequences
        urls = event.mimeData().urls()
        if not urls:
            return
        paths = []
        for url in urls:
            p = Path(url.toLocalFile())
            if p.is_file() and p.suffix.lower() in ALL_EXT:
                paths.append(p)
            elif p.is_dir():
                paths.extend(
                    f for f in p.rglob("*")
                    if f.is_file() and f.suffix.lower() in ALL_EXT)
        if not paths:
            QMessageBox.information(self, "Drop Import",
                "No supported VFX files found in the dropped items.")
            return
        items = detect_sequences(paths)
        self._status_label.setText(
            f"  Dropped {len(paths)} file(s) — opening import…")
        self._show_import_dialog(items)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    # ── Windows: set AppUserModelID so taskbar shows OUR icon ─────────────
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ghstsoftware.pixelattic.app.1")
    except Exception:
        pass

    # ── GPU acceleration (must be set BEFORE QApplication) ────────────────
    try:
        _s = Settings.load()
        if getattr(_s, 'gpu_acceleration', False):
            from PySide2.QtCore import Qt as _QtC
            QApplication.setAttribute(_QtC.AA_UseOpenGLES, True)
            # Also enable high-DPI scaling
            QApplication.setAttribute(_QtC.AA_EnableHighDpiScaling, True)
            print("[App] GPU acceleration enabled (OpenGL)")
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    # ── App icon (taskbar + title bar + Alt-Tab) ──────────────────────────
    from PySide2.QtGui import QIcon
    from icons import icon_dir
    _ico = Path(icon_dir()).parent / "pixelattic.ico"
    if not _ico.exists():
        # Fallback: check next to main script
        _ico = Path(__file__).resolve().parent / "pixelattic.ico"
    if _ico.exists():
        app.setWindowIcon(QIcon(str(_ico)))

    window = PixelAtticApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
