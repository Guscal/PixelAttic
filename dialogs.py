"""
dialogs.py — Settings, Import, and Tag Editor dialogs for Pixel Attic.
"""
import subprocess
from pathlib import Path

from PySide2.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QPushButton, QLineEdit, QTextEdit, QCheckBox,
    QComboBox, QSlider, QFileDialog, QFrame, QMessageBox,
    QScrollArea
)
from PySide2.QtCore import Qt

from config   import APP_NAME, VERSION, LIBRARY_FILE, THUMBS_DIR
from database import Library, Asset
from settings import Settings, THEMES, ACCENT_COLORS, CARD_SIZES
from widgets  import TagPill

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("section_label")
    return lbl

# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, lib: Library, parent=None):
        super().__init__(parent)
        self.settings = Settings(**settings.__dict__)   # working copy
        self.setWindowTitle("Settings")
        self.setMinimumSize(640, 580)
        self.setModal(True)

        # ── Global checkbox style: accent fill + checkmark icon ─────────────
        from icons import icon_path, icon_exists
        from settings import ACCENT_COLORS
        _ar, _ag, _ab = ACCENT_COLORS.get(
            self.settings.accent_color, (249, 115, 22))
        _acc_rgb = f"rgb({_ar},{_ag},{_ab})"
        _chk_url = icon_path("check.png").replace("\\", "/")
        _has_icon = icon_exists("check.png")
        if _has_icon:
            self.setStyleSheet(self.styleSheet() +
                "QCheckBox::indicator {"
                "  width:16px; height:16px;"
                "  border:1.5px solid rgb(55,60,90);"
                "  border-radius:3px;"
                "  background:rgb(14,16,28);}"
                "QCheckBox::indicator:hover {"
                "  border-color:rgb(100,110,150);}"
                "QCheckBox::indicator:checked {"
                f"  background:{_acc_rgb};"
                f"  border-color:{_acc_rgb};"
                f'  image:url("{_chk_url}");'
                "}"
                "QCheckBox {"
                "  spacing:6px;"
                "  color:rgb(200,210,230);}")
        else:
            self.setStyleSheet(self.styleSheet() +
                "QCheckBox::indicator {"
                "  width:16px; height:16px;"
                "  border:1.5px solid rgb(55,60,90);"
                "  border-radius:3px;"
                "  background:rgb(14,16,28);}"
                "QCheckBox::indicator:hover {"
                "  border-color:rgb(100,110,150);}"
                "QCheckBox::indicator:checked {"
                f"  background:{_acc_rgb};"
                f"  border-color:{_acc_rgb};"
                "}"
                "QCheckBox {"
                "  spacing:6px;"
                "  color:rgb(200,210,230);}")

        layout = QVBoxLayout(self)
        tabs   = QTabWidget()
        layout.addWidget(tabs)

        tabs.addTab(self._build_appearance_tab(self.settings), "Appearance")
        tabs.addTab(self._build_viewers_tab(self.settings),    "Viewers")
        tabs.addTab(self._build_general_tab(self.settings),    "General")
        tabs.addTab(self._build_database_tab(lib),             "Database")
        tabs.addTab(self._build_about_tab(),                   "About")

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Reset Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        save_btn  = QPushButton("  Save Settings  ")
        save_btn.setObjectName("btn_accent")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    # ── Appearance tab ────────────────────────────────────────────────────────

    def _build_appearance_tab(self, s: Settings) -> QWidget:
        tab = QWidget()
        al  = QVBoxLayout(tab)

        # Theme
        al.addWidget(_section_label("THEME"))
        self._theme_btns: dict[str, QPushButton] = {}
        th_scroll = QScrollArea(); th_scroll.setFixedHeight(80)
        th_scroll.setWidgetResizable(True)
        th_scroll.setFrameShape(QFrame.NoFrame)
        th_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        th_w = QWidget(); th_l = QVBoxLayout(th_w)
        th_l.setSpacing(4); th_l.setContentsMargins(0,0,0,0)
        for name in THEMES:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(name == s.theme)
            btn.clicked.connect(
                lambda checked=False, n=name: self._preview_theme(n))
            th_l.addWidget(btn)
            self._theme_btns[name] = btn
        th_scroll.setWidget(th_w)
        al.addWidget(th_scroll)

        # Accent color
        al.addWidget(_section_label("ACCENT COLOR"))
        self._accent_btns: dict[str, QPushButton] = {}
        acc_w = QWidget(); acc_grid = QHBoxLayout(acc_w)
        acc_grid.setSpacing(4); acc_grid.setContentsMargins(0,0,0,0)
        # 2 rows of accent buttons
        col1 = QVBoxLayout(); col2 = QVBoxLayout()
        names = list(ACCENT_COLORS.keys())
        half  = (len(names) + 1) // 2
        for i, name in enumerate(names):
            r, g, b = ACCENT_COLORS[name]
            btn = QPushButton(f"  ● {name}")
            btn.setCheckable(True)
            btn.setChecked(name == s.accent_color)
            btn.setStyleSheet(
                f"QPushButton::indicator {{}} "
                f"QPushButton {{ color: rgb({r},{g},{b}); text-align:left; }}")
            btn.clicked.connect(
                lambda checked=False, n=name: self._preview_accent(n))
            self._accent_btns[name] = btn
            (col1 if i < half else col2).addWidget(btn)
        acc_grid.addLayout(col1); acc_grid.addLayout(col2)
        al.addWidget(acc_w)

        # Card size
        al.addWidget(_section_label("CARD SIZE"))
        size_row = QHBoxLayout()
        self._size_btns: dict[str, QPushButton] = {}
        for sz in CARD_SIZES:
            b = QPushButton(sz)
            b.setCheckable(True)
            b.setChecked(sz == s.card_size)
            b.clicked.connect(lambda checked=False, n=sz: self._set_card_size(n))
            self._size_btns[sz] = b
            size_row.addWidget(b)
        size_row.addStretch()
        al.addLayout(size_row)

        al.addWidget(_section_label("DEFAULT VIEW ON STARTUP"))
        view_row = QHBoxLayout()
        self._view_grid_btn = QPushButton("Grid")
        self._view_list_btn = QPushButton("List")
        self._view_grid_btn.setCheckable(True)
        self._view_list_btn.setCheckable(True)
        _dv = getattr(s, "view_mode_default", "grid")
        self._view_grid_btn.setChecked(_dv == "grid")
        self._view_list_btn.setChecked(_dv == "list")
        self._view_grid_btn.clicked.connect(lambda: (self._view_grid_btn.setChecked(True), self._view_list_btn.setChecked(False)))
        self._view_list_btn.clicked.connect(lambda: (self._view_list_btn.setChecked(True), self._view_grid_btn.setChecked(False)))
        view_row.addWidget(self._view_grid_btn)
        view_row.addWidget(self._view_list_btn)
        view_row.addStretch()
        al.addLayout(view_row)

        # Grid display options
        al.addWidget(_section_label("GRID OPTIONS"))
        opts_row = QHBoxLayout()
        self._show_filename = QCheckBox("Filename")
        self._show_filename.setChecked(s.grid_show_filename)
        self._show_res      = QCheckBox("Resolution")
        self._show_res.setChecked(s.grid_show_resolution)
        self._show_tags     = QCheckBox("Tags")
        self._show_tags.setChecked(s.grid_show_tags)
        for cb in (self._show_filename, self._show_res, self._show_tags):
            opts_row.addWidget(cb)
        opts_row.addStretch()
        al.addLayout(opts_row)

        # Font
        al.addWidget(_section_label("FONT"))
        font_row = QHBoxLayout()
        self._font_combo = QComboBox()
        self._font_combo.addItem("Default")
        from PySide2.QtGui import QFontDatabase
        # All fonts installed in the OS — reliable on Windows/Mac/Linux
        for fam in sorted(QFontDatabase().families()):
            if not fam.startswith("@"):  # skip vertical/CJK aliases
                self._font_combo.addItem(fam)
        idx = self._font_combo.findText(s.font_name)
        self._font_combo.setCurrentIndex(max(0, idx))
        self._font_size = QSlider(Qt.Horizontal)
        self._font_size.setRange(10, 22)
        self._font_size.setValue(s.font_size)
        self._font_size.setFixedWidth(100)
        self._font_size_lbl = QLabel(f"{s.font_size}pt")
        self._font_size.valueChanged.connect(
            lambda v: self._font_size_lbl.setText(f"{v}pt"))
        font_row.addWidget(QLabel("Font:"))
        font_row.addWidget(self._font_combo)
        font_row.addSpacing(8)
        font_row.addWidget(QLabel("Size:"))
        font_row.addWidget(self._font_size)
        font_row.addWidget(self._font_size_lbl)
        font_row.addStretch()
        al.addLayout(font_row)
        al.addStretch()
        return tab

    def _refresh_custom_cats_ui(self):
        # Remove all widgets except the trailing stretch
        while self._cats_vl.count() > 1:
            item = self._cats_vl.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        from config import get_categories, BASE_CATEGORIES
        PROTECTED = {"All", "Misc"}  # never deletable
        hidden = set(getattr(self, "_hidden_base_cats", []))
        all_cats = get_categories(self._custom_cats_list, list(hidden))
        for cat in all_cats:
            if cat in PROTECTED:
                continue
            is_custom = cat not in BASE_CATEGORIES
            row = QWidget()
            rl  = QHBoxLayout(row)
            rl.setContentsMargins(2, 0, 2, 0)
            rl.setSpacing(4)
            icon = "·" if is_custom else "·"
            lbl = QLabel(f"{icon}  {cat}")
            lbl.setStyleSheet(
                f"color: {'rgb(180,190,210)' if is_custom else 'rgb(140,155,180)'};"
                " font-size: 12px; background: transparent;")
            rl.addWidget(lbl)
            rl.addStretch()
            rm = QPushButton("×")
            rm.setFixedSize(20, 20)
            rm.setStyleSheet(
                "QPushButton{background:transparent;border:none;"
                "color:rgb(80,90,110);font-size:14px;font-weight:bold;"
                "padding:0;margin:0;}"
                "QPushButton:hover{color:rgb(248,113,113);}")
            rm.setToolTip(f"Remove '{cat}'")
            rm.clicked.connect(
                lambda checked=False, c=cat, custom=is_custom:
                    self._remove_cat_any(c, custom))
            rl.addWidget(rm)
            self._cats_vl.insertWidget(self._cats_vl.count() - 1, row)

    def _add_custom_cat(self):
        name = self._new_cat_input.text().strip()
        from config import BASE_CATEGORIES
        if name and name not in BASE_CATEGORIES and name not in self._custom_cats_list:
            self._custom_cats_list.append(name)
            self._new_cat_input.clear()
            self._refresh_custom_cats_ui()
    def _remove_cat_any(self, cat: str, is_custom: bool):
        from config import BASE_CATEGORIES
        if is_custom:
            if cat in self._custom_cats_list:
                self._custom_cats_list.remove(cat)
        else:
            # Hide a base category
            if not hasattr(self, "_hidden_base_cats"):
                self._hidden_base_cats = []
            if cat not in self._hidden_base_cats:
                self._hidden_base_cats.append(cat)
        self._refresh_custom_cats_ui()

    def _run_find_duplicates(self):
        """Delegate to main window's _find_duplicates method."""
        parent = self.parent()
        if parent and hasattr(parent, "_find_duplicates"):
            self.accept()  # close settings first
            parent._find_duplicates()

    # ── Viewers tab ───────────────────────────────────────────────────────────

    def _build_viewers_tab(self, s: Settings) -> QWidget:
        tab = QWidget()
        vl  = QVBoxLayout(tab)
        vl.setSpacing(2)

        _INP = (
            "QLineEdit{background:rgb(14,14,24);color:rgb(148,163,184);"
            "border:1px solid rgb(30,32,50);border-radius:4px;"
            "padding:0 8px;font-size:11px;}"
            "QLineEdit:focus{border:1px solid rgba(249,115,22,140);}"
            "QLineEdit::placeholder{color:rgb(45,55,72);}"
        )
        _BTN = (
            "QPushButton{background:rgb(14,14,24);color:rgb(71,85,105);"
            "border:1px solid rgb(30,32,50);border-radius:4px;font-size:11px;padding:0 8px;}"
            "QPushButton:hover{background:rgb(20,20,35);color:rgb(148,163,184);"
            "border-color:rgb(50,55,75);}"
        )
        _BTN_TEST = (
            "QPushButton{background:rgba(249,115,22,15);color:rgb(249,115,22);"
            "border:1px solid rgba(249,115,22,50);border-radius:4px;font-size:11px;padding:0 10px;}"
            "QPushButton:hover{background:rgba(249,115,22,180);color:rgb(15,15,25);}"
        )
        _BTN_CLR = (
            "QPushButton{background:transparent;color:rgb(55,65,85);"
            "border:1px solid rgb(28,30,45);border-radius:4px;font-size:13px;}"
            "QPushButton:hover{color:rgb(248,113,113);border-color:rgba(248,113,113,80);}"
        )
        _NOTE = "color:rgb(55,68,90);font-size:10px;"

        def _exe_row(inp_attr, cur_val, placeholder, is_dir=False):
            row = QHBoxLayout(); row.setSpacing(4)
            inp = QLineEdit(cur_val or "")
            inp.setFixedHeight(28); inp.setStyleSheet(_INP)
            inp.setPlaceholderText(placeholder)
            setattr(self, inp_attr, inp)
            br = QPushButton("Browse…"); br.setFixedHeight(28); br.setStyleSheet(_BTN)
            if is_dir:
                br.clicked.connect(lambda checked=False, w=inp: self._browse_dir(w))
            else:
                br.clicked.connect(lambda checked=False, w=inp: self._browse_exe(w))
            cl = QPushButton("✕"); cl.setFixedSize(28,28); cl.setStyleSheet(_BTN_CLR)
            cl.clicked.connect(lambda checked=False, w=inp: w.clear())
            row.addWidget(inp,1); row.addWidget(br); row.addWidget(cl)
            return row

        # ── FFMPEG ────────────────────────────────────────────────────────
        vl.addWidget(_section_label("FFMPEG"))
        note = QLabel("Used for scrub strips and proxy generation.  Leave blank to auto-detect.")
        note.setStyleSheet(_NOTE); note.setWordWrap(True); vl.addWidget(note)

        ff_row = _exe_row("_ffmpeg_inp", getattr(s,"ffmpeg_path",""),
                          r"e.g. C:fmpeginfmpeg.exe")
        test_ff = QPushButton("Test"); test_ff.setFixedHeight(28)
        test_ff.setStyleSheet(_BTN_TEST)
        test_ff.clicked.connect(lambda: self._test_exe(
            self._ffmpeg_inp, "ffmpeg", ["-version"]))
        ff_row.addWidget(test_ff)
        vl.addLayout(ff_row)

        from preview import ffmpeg_path as _det_ff
        _ff = _det_ff()
        _ff_lbl = QLabel(f"  ✓  Auto-detected: {_ff}" if _ff
                         else "  ⚠  Not found in PATH — set path above")
        _ff_lbl.setStyleSheet(
            f"color:{'rgb(52,211,153)' if _ff else 'rgb(248,113,113)'};font-size:10px;")
        vl.addWidget(_ff_lbl)
        vl.addSpacing(10)

        # ── VLC ───────────────────────────────────────────────────────────
        vl.addWidget(_section_label("VLC LIBRARY"))
        note2 = QLabel("Folder containing libvlc.dll.  Leave blank to auto-detect.")
        note2.setStyleSheet(_NOTE); note2.setWordWrap(True); vl.addWidget(note2)

        vlc_row = _exe_row("_vlc_inp", getattr(s,"vlc_path",""),
                           r"e.g. C:\Program Files\VideoLAN\VLC", is_dir=True)
        test_vlc = QPushButton("Test"); test_vlc.setFixedHeight(28)
        test_vlc.setStyleSheet(_BTN_TEST)
        test_vlc.clicked.connect(lambda: self._test_vlc_dir(self._vlc_inp))
        vlc_row.addWidget(test_vlc)
        vl.addLayout(vlc_row)

        import shutil as _sh
        from pathlib import Path as _P
        _vlc_auto = None
        for _d in [r"C:\Program Files\VideoLAN\VLC",
                   r"C:\Program Files (x86)\VideoLAN\VLC"]:
            if (_P(_d) / "libvlc.dll").exists():
                _vlc_auto = _d; break
        if not _vlc_auto:
            _vlc_auto = _sh.which("vlc")
        _vlc_lbl = QLabel(f"  ✓  Auto-detected: {_vlc_auto}" if _vlc_auto
                          else "  ⚠  Not found — set path above")
        _vlc_lbl.setStyleSheet(
            f"color:{'rgb(52,211,153)' if _vlc_auto else 'rgb(248,113,113)'};font-size:10px;")
        vl.addWidget(_vlc_lbl)
        vl.addSpacing(10)

        # ── External viewers ──────────────────────────────────────────────
        vl.addWidget(_section_label("EXTERNAL VIEWER APPS"))
        note3 = QLabel("Leave blank to use system default for each type.")
        note3.setStyleSheet(_NOTE); vl.addWidget(note3)
        self._viewer_inputs: dict = {}
        for key, label, ph in [
            ("viewer_video",    "Videos  (MOV, MP4…)",
             r"e.g. C:\Program Files\djvin\djv.exe"),
            ("viewer_image",    "Images  (PNG, EXR, TGA…)", ""),
            ("viewer_sequence", "Sequences  (EXR seq, DPX…)",
             r"e.g. C:\Program Files\djvin\djv.exe"),
        ]:
            vl.addWidget(_section_label(label))
            row = QHBoxLayout(); row.setSpacing(4)
            inp = QLineEdit(getattr(s, key, ""))
            inp.setFixedHeight(28); inp.setStyleSheet(_INP)
            inp.setPlaceholderText(ph or "Path to viewer (blank = system default)")
            br = QPushButton("Browse…"); br.setFixedHeight(28); br.setStyleSheet(_BTN)
            br.clicked.connect(lambda checked=False, w=inp: self._browse_exe(w))
            cl = QPushButton("✕"); cl.setFixedSize(28,28); cl.setStyleSheet(_BTN_CLR)
            cl.clicked.connect(lambda checked=False, w=inp: w.clear())
            row.addWidget(inp,1); row.addWidget(br); row.addWidget(cl)
            vl.addLayout(row)
            self._viewer_inputs[key] = inp

        vl.addSpacing(8)
        djv = QLabel(
            "Tip: DJV is a free VFX viewer with EXR/DPX/sequence support.\n"
            "https://darbyjohnston.github.io/DJV/")
        djv.setStyleSheet("color:rgb(45,55,72);font-size:10px;")
        djv.setWordWrap(True); vl.addWidget(djv)
        vl.addStretch()
        return tab

    def _test_exe(self, inp_widget, name: str, args: list):
        """Test exe: first checks file exists, then runs it."""
        import subprocess
        from pathlib import Path
        p = inp_widget.text().strip()
        if not p:
            QMessageBox.information(self, f"{name} Test",
                "No path entered.\nLeave blank to use auto-detection from PATH.")
            return
        p = str(Path(p))
        if not Path(p).exists():
            QMessageBox.critical(self, f"{name} — Not Found",
                f"File not found:\n{p}\n\n"
                "Check the path is correct and uses the full path to the .exe")
            return
        # File exists — try running it for version info
        try:
            r = subprocess.run([p] + args, capture_output=True,
                               text=True, timeout=6)
            first_line = (r.stdout or r.stderr or "OK").splitlines()[0]
            QMessageBox.information(self, f"{name} — ✓ Found",
                f"✓  {name} found and working.\n\n{first_line}")
        except Exception:
            # File exists but couldn't run — still valid, just report exists
            QMessageBox.information(self, f"{name} — ✓ Found",
                f"✓  {name} found at:\n{p}")

    def _test_vlc_dir(self, inp_widget):
        """Test VLC directory by checking for libvlc.dll."""
        from pathlib import Path
        p = inp_widget.text().strip()
        if not p:
            QMessageBox.information(self, "VLC Test",
                "No path entered.\nLeave blank to use auto-detection.")
            return
        d = Path(p)
        if not d.exists():
            QMessageBox.critical(self, "VLC — Not Found",
                f"Directory not found:\n{p}")
            return
        dll = d / "libvlc.dll"
        if dll.exists():
            QMessageBox.information(self, "VLC — ✓ Found",
                f"✓  libvlc.dll found in:\n{p}")
        else:
            QMessageBox.warning(self, "VLC — libvlc.dll Missing",
                f"Directory exists but libvlc.dll was not found in:\n{p}\n\n"
                "Make sure this is the VLC installation folder.")

    def _browse_exe(self, inp: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Viewer Application", "",
            "Executable (*.exe);;All Files (*)")
        if path:
            inp.setText(path)

    def _browse_dir(self, inp: QLineEdit):
        path = QFileDialog.getExistingDirectory(self, "Select Directory")
        if path:
            inp.setText(path)

    # ── General tab ───────────────────────────────────────────────────────────

    def _build_general_tab(self, s: Settings) -> QWidget:
        outer = QWidget()
        outer_l = QVBoxLayout(outer)
        outer_l.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tab = QWidget()
        gl  = QVBoxLayout(tab)
        gl.addWidget(_section_label("BEHAVIOR"))
        self._confirm_delete = QCheckBox(
            "Confirm before removing assets from library")
        self._confirm_delete.setChecked(s.confirm_before_delete)
        gl.addWidget(self._confirm_delete)

        # ── Video player time display ─────────────────────────────────────
        gl.addWidget(_section_label("VIDEO PLAYER"))
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Time display:"))
        from PySide2.QtWidgets import QComboBox as _QCB
        self._time_display = _QCB()
        self._time_display.addItems(["Frames  (f 288)", "Timecode  (0:12)"])
        _td = getattr(s, 'time_display_mode', 'frames')
        self._time_display.setCurrentIndex(0 if _td == 'frames' else 1)
        time_row.addWidget(self._time_display)
        time_row.addStretch()
        gl.addLayout(time_row)
        gl.addSpacing(8)

        # ── Performance ───────────────────────────────────────────────────
        gl.addWidget(_section_label("PERFORMANCE"))
        self._gpu_accel = QCheckBox(
            "Enable GPU acceleration (OpenGL rendering)")
        self._gpu_accel.setChecked(getattr(s, 'gpu_acceleration', False))
        self._gpu_accel.setToolTip(
            "Uses OpenGL for widget rendering. Faster on modern GPUs.\n"
            "Disable if you see visual glitches. Requires restart.")
        gl.addWidget(self._gpu_accel)

        self._lazy_thumbs = QCheckBox(
            "Load thumbnails in background (non-blocking)")
        self._lazy_thumbs.setChecked(getattr(s, 'lazy_thumbnails', True))
        self._lazy_thumbs.setToolTip(
            "Cards appear instantly with placeholders, thumbnails load after.\n"
            "Disable for immediate thumbnails (slower on large libraries).")
        gl.addWidget(self._lazy_thumbs)

        self._auto_proxies = QCheckBox(
            "Auto-generate proxy videos on import")
        self._auto_proxies.setChecked(getattr(s, 'auto_generate_proxies', True))
        self._auto_proxies.setToolTip(
            "Generates lightweight H.264 proxies for faster playback.\n"
            "Disable to save disk space (playback will use original files).")
        gl.addWidget(self._auto_proxies)

        # Proxy resolution
        pr_row = QHBoxLayout()
        pr_row.addWidget(QLabel("Proxy resolution:"))
        self._proxy_res = _QCB()
        self._proxy_res.addItems(["480p (lightweight)", "720p HD (default)", "1080p Full HD"])
        _pr = getattr(s, 'proxy_resolution', '720p')
        self._proxy_res.setCurrentIndex({"480p": 0, "720p": 1, "1080p": 2}.get(_pr, 1))
        pr_row.addWidget(self._proxy_res)
        pr_row.addStretch()
        gl.addLayout(pr_row)

        # Thumbnail quality
        tq_row = QHBoxLayout()
        tq_row.addWidget(QLabel("Thumbnail scaling:"))
        self._thumb_quality = _QCB()
        self._thumb_quality.addItems(["Fast (better performance)", "Smooth (better quality)"])
        _tq = getattr(s, 'thumbnail_quality', 'fast')
        self._thumb_quality.setCurrentIndex(0 if _tq == 'fast' else 1)
        tq_row.addWidget(self._thumb_quality)
        tq_row.addStretch()
        gl.addLayout(tq_row)

        # Scrub frames
        sf_row = QHBoxLayout()
        sf_row.addWidget(QLabel("Scrub strip frames:"))
        self._scrub_frames = _QCB()
        self._scrub_frames.addItems(["4 (lighter)", "8 (default)", "12 (smoother)"])
        _sf = getattr(s, 'scrub_frames', 8)
        self._scrub_frames.setCurrentIndex({4: 0, 8: 1, 12: 2}.get(_sf, 1))
        sf_row.addWidget(self._scrub_frames)
        sf_row.addStretch()
        gl.addLayout(sf_row)

        # Memory cache size
        mc_row = QHBoxLayout()
        mc_row.addWidget(QLabel("Thumbnail cache:"))
        self._max_thumbs = _QCB()
        self._max_thumbs.addItems([
            "200 items (~80 MB)",
            "500 items (~200 MB)",
            "1000 items (~400 MB)"])
        _mt = getattr(s, 'max_memory_thumbs', 500)
        self._max_thumbs.setCurrentIndex(
            {200: 0, 500: 1, 1000: 2}.get(_mt, 1))
        mc_row.addWidget(self._max_thumbs)
        mc_row.addStretch()
        gl.addLayout(mc_row)

        # Thumbnail resolution
        tr_row = QHBoxLayout()
        tr_row.addWidget(QLabel("Thumbnail quality:"))
        self._thumb_res = _QCB()
        self._thumb_res.addItems([
            "Low (160x120, fast)",
            "Medium (200x150, default)",
            "High (320x240, sharp)"])
        _tr = getattr(s, 'thumbnail_resolution', 'medium')
        self._thumb_res.setCurrentIndex(
            {"low": 0, "medium": 1, "high": 2}.get(_tr, 1))
        tr_row.addWidget(self._thumb_res)
        tr_row.addStretch()
        gl.addLayout(tr_row)
        gl.addSpacing(8)

        # ── Behavior ──────────────────────────────────────────────────────
        gl.addWidget(_section_label("BEHAVIOR"))
        self._restore_cat = QCheckBox(
            "Restore last active category on startup")
        self._restore_cat.setChecked(getattr(s, 'restore_last_category', True))
        gl.addWidget(self._restore_cat)

        self._import_summary = QCheckBox(
            "Show error summary after import")
        self._import_summary.setChecked(getattr(s, 'show_import_summary', True))
        gl.addWidget(self._import_summary)

        # Double-click action
        dc_row = QHBoxLayout()
        dc_row.addWidget(QLabel("Double-click card:"))
        self._dbl_click = _QCB()
        self._dbl_click.addItems([
            "Open in system viewer",
            "Show in file explorer",
            "Copy file path",
            "Do nothing"])
        _dc = getattr(s, 'double_click_action', 'open')
        self._dbl_click.setCurrentIndex(
            {"open": 0, "explorer": 1, "copy_path": 2, "nothing": 3}.get(_dc, 0))
        dc_row.addWidget(self._dbl_click)
        dc_row.addStretch()
        gl.addLayout(dc_row)
        gl.addSpacing(8)

        # ── Storage backend ───────────────────────────────────────────────
        gl.addWidget(_section_label("STORAGE BACKEND"))
        storage_row = QHBoxLayout()
        storage_row.addWidget(QLabel("Library format:"))
        self._storage_combo = _QCB()
        self._storage_combo.addItems(["JSON (default)", "SQLite (faster, crash-safe)"])
        _sb = getattr(s, 'storage_backend', 'json')
        self._storage_combo.setCurrentIndex(1 if _sb == 'sqlite' else 0)
        storage_row.addWidget(self._storage_combo)
        storage_row.addStretch()
        gl.addLayout(storage_row)

        _migrate_btn = QPushButton("  Migrate JSON → SQLite  ")
        _migrate_btn.setObjectName("btn_accent_outline")
        _migrate_btn.setFixedHeight(28)
        _migrate_btn.setToolTip(
            "One-time import of your existing JSON library into SQLite.\n"
            "The JSON file is kept as backup.")
        _migrate_btn.clicked.connect(self._run_sqlite_migration)

        _migrate_back_btn = QPushButton("  Migrate SQLite → JSON  ")
        _migrate_back_btn.setObjectName("btn_accent_outline")
        _migrate_back_btn.setFixedHeight(28)
        _migrate_back_btn.setToolTip(
            "Export the SQLite database back to JSON format.\n"
            "Useful for sharing or as manual backup.")
        _migrate_back_btn.clicked.connect(self._run_json_migration)

        _mig_row = QHBoxLayout()
        _mig_row.addWidget(_migrate_btn)
        _mig_row.addWidget(_migrate_back_btn)
        _mig_row.addStretch()
        gl.addLayout(_mig_row)
        gl.addSpacing(8)

        gl.addWidget(_section_label("CATEGORIES"))
        gl.addWidget(QLabel("Add or delete categories:"))
        self._custom_cats_list  = list(s.custom_categories or [])
        self._hidden_base_cats  = list(getattr(s, "hidden_base_categories", []) or [])
        cats_scroll = QScrollArea()
        cats_scroll.setWidgetResizable(True)
        cats_scroll.setFixedHeight(180)
        cats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        cats_scroll.setStyleSheet("QScrollArea{border:1px solid rgb(30,30,50);border-radius:4px;}")
        self._cats_container = QWidget()
        self._cats_vl = QVBoxLayout(self._cats_container)
        self._cats_vl.setContentsMargins(4, 4, 4, 4)
        self._cats_vl.setSpacing(2)
        self._cats_vl.addStretch()
        cats_scroll.setWidget(self._cats_container)
        self._refresh_custom_cats_ui()
        gl.addWidget(cats_scroll)

        add_cat_row = QHBoxLayout()
        self._new_cat_input = QLineEdit()
        self._new_cat_input.setPlaceholderText("New category name…")
        self._new_cat_input.setFixedHeight(28)
        add_cat_btn = QPushButton("+  Add")
        add_cat_btn.setObjectName("btn_accent_outline")
        add_cat_btn.setFixedHeight(28)
        add_cat_btn.clicked.connect(self._add_custom_cat)
        self._new_cat_input.returnPressed.connect(self._add_custom_cat)
        add_cat_row.addWidget(self._new_cat_input)
        add_cat_row.addWidget(add_cat_btn)
        gl.addLayout(add_cat_row)
        gl.addSpacing(8)

        gl.addWidget(_section_label("TOOLS"))
        find_dup_btn = QPushButton("  Find Duplicate Assets…")
        find_dup_btn.setObjectName("btn_accent_outline")
        find_dup_btn.setFixedHeight(28)
        find_dup_btn.clicked.connect(self._run_find_duplicates)
        gl.addWidget(find_dup_btn)
        gl.addSpacing(8)

        gl.addWidget(_section_label("ABOUT"))
        gl.addWidget(QLabel(f"{APP_NAME}  v{VERSION}"))
        app_dir_btn = QPushButton("  Open App Data Folder  ")
        app_dir_btn.clicked.connect(
            lambda checked=False: subprocess.Popen(
                f'explorer "{Path.home() / ".pixelattic"}"'))
        gl.addWidget(app_dir_btn)
        gl.addStretch()
        scroll.setWidget(tab)
        outer_l.addWidget(scroll)
        return outer

    def _build_about_tab(self) -> QWidget:
        from PySide2.QtWidgets import QTextBrowser
        tab = QWidget()
        al  = QVBoxLayout(tab)
        al.setSpacing(10)

        # App name + version header
        name_lbl = QLabel(f"{APP_NAME}")
        name_lbl.setStyleSheet("font-size:20px;font-weight:bold;color:rgb(226,232,240);")
        ver_lbl  = QLabel(f"Version {VERSION}")
        ver_lbl.setStyleSheet("font-size:12px;color:rgb(100,116,139);")
        al.addWidget(name_lbl)
        al.addWidget(ver_lbl)

        al.addWidget(_section_label("COPYRIGHT"))
        copy_lbl = QLabel("© 2026 GHST Software. All rights reserved.")
        copy_lbl.setStyleSheet("color:rgb(148,163,184);font-size:12px;")
        al.addWidget(copy_lbl)

        al.addWidget(_section_label("LICENSE — MIT"))
        lic_text = QTextBrowser()
        lic_text.setFixedHeight(140)
        lic_text.setStyleSheet(
            "QTextBrowser{background:rgba(255,255,255,4);border:1px solid rgb(30,30,50);"
            "border-radius:4px;color:rgb(100,116,139);font-size:10px;padding:6px;}"
            "QTextBrowser:focus{border-color:rgb(40,40,65);}"
        )
        lic_text.setPlainText(
            "MIT License\n\n"
            f"Copyright (c) 2026 GHST Software\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included\n"
            "in all copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL\n"
            "THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING\n"
            "FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER\n"
            "DEALINGS IN THE SOFTWARE.")
        al.addWidget(lic_text)

        al.addWidget(_section_label("SUPPORT"))
        support_lbl = QLabel(
            "If you find Pixel Attic useful, consider supporting development:")
        support_lbl.setStyleSheet("color:rgb(100,116,139);font-size:11px;")
        support_lbl.setWordWrap(True)
        al.addWidget(support_lbl)
        link_row = QHBoxLayout()
        for label, url in [
            ("GitHub",  "https://github.com/Guscal/PixelAttic"),
            ("Gumroad", "https://4471282674150.gumroad.com/coffee"),
            ("Ko-fi",   "https://ko-fi.com/guscal"),
        ]:
            lnk = QPushButton(label)
            lnk.setObjectName("btn_edit")
            lnk.setFixedHeight(26)
            lnk.clicked.connect(
                lambda checked=False, u=url: __import__("webbrowser").open(u))
            link_row.addWidget(lnk)
        link_row.addStretch()
        al.addLayout(link_row)

        al.addSpacing(8)
        app_dir_btn = QPushButton("  Open App Data Folder  ")
        app_dir_btn.setFixedHeight(26)
        app_dir_btn.clicked.connect(
            lambda checked=False: subprocess.Popen(
                f'explorer "{Path.home() / ".pixelattic"}"')
            )
        al.addWidget(app_dir_btn)
        al.addStretch()
        return tab

    # ── Database tab ──────────────────────────────────────────────────────────

    def _build_database_tab(self, lib: Library) -> QWidget:
        tab = QWidget()
        dl  = QVBoxLayout(tab)
        import settings as _sm
        from database import BACKUP_FILE
        from preview  import _DEFAULT_PROXY_DIR

        dl.addWidget(_section_label("FILE LOCATIONS"))
        note = QLabel("Changes take effect after restarting the app.")
        note.setStyleSheet("color:rgb(55,68,90);font-size:10px;")
        dl.addWidget(note)
        dl.addSpacing(6)

        # ── Shared styles ────────────────────────────────────────────────────
        _INP = (
            "QLineEdit{background:rgb(14,14,24);color:rgb(148,163,184);"
            "border:1px solid rgb(30,32,50);border-radius:4px;"
            "padding:0 8px;font-size:11px;}"
            "QLineEdit:focus{border:1px solid rgba(249,115,22,140);}"
            "QLineEdit:read-only{color:rgb(55,68,90);"
            "background:rgb(11,11,20);border:1px solid rgb(22,24,38);}"
        )
        _BTN_BROWSE = (
            "QPushButton{background:rgba(249,115,22,18);color:rgb(249,115,22);"
            "border:1px solid rgba(249,115,22,60);border-radius:4px;"
            "font-size:13px;font-weight:bold;padding:0;}"
            "QPushButton:hover{background:rgba(249,115,22,200);color:rgb(15,15,25);}"
        )
        _BTN_RESET = (
            "QPushButton{background:rgb(14,14,24);color:rgb(71,85,105);"
            "border:1px solid rgb(30,32,50);border-radius:4px;"
            "font-size:12px;padding:0;}"
            "QPushButton:hover{background:rgb(20,20,35);color:rgb(148,163,184);"
            "border-color:rgb(50,55,75);}"
        )

        def _row(label, default_path, inp_attr, cur_val, readonly=False):
            row = QHBoxLayout(); row.setSpacing(4)
            lbl = QLabel(label); lbl.setFixedWidth(68)
            lbl.setStyleSheet(
                f"color:rgb({'71,85,105' if readonly else '148,163,184'});"
                "font-size:11px;")
            inp = QLineEdit(cur_val or str(default_path))
            inp.setFixedHeight(28)
            inp.setStyleSheet(_INP)
            if readonly:
                inp.setReadOnly(True)
            else:
                inp.setPlaceholderText(str(default_path))
                inp.setToolTip(f"Leave empty to use default:\n{default_path}")
                setattr(self, inp_attr, inp)
                br = QPushButton("…"); br.setFixedSize(28, 28)
                br.setStyleSheet(_BTN_BROWSE)
                br.setToolTip("Browse folder")
                br.clicked.connect(
                    lambda checked=False, w=inp, d=default_path:
                        self._browse_path(w, d))
                rs = QPushButton("↺"); rs.setFixedSize(28, 28)
                rs.setStyleSheet(_BTN_RESET)
                rs.setToolTip("Reset to default")
                rs.clicked.connect(lambda checked=False, w=inp: w.clear())
                row.addWidget(lbl); row.addWidget(inp, 1)
                row.addWidget(br); row.addWidget(rs)
                dl.addLayout(row)
                return
            row.addWidget(lbl); row.addWidget(inp)
            dl.addLayout(row)

        # Read bootstrap for custom paths
        bp = _sm._read_bootstrap()

        _row("Settings:", _sm.SETTINGS_FILE,
             "_st_path_inp", bp.get("settings",""), readonly=False)
        _row("Database:", LIBRARY_FILE,
             "_db_path_inp", bp.get("library",""), readonly=False)
        _row("Backup:",   BACKUP_FILE,
             "_bk_path_inp", bp.get("backup",""),  readonly=False)
        _row("Thumbs:",   THUMBS_DIR,
             "_th_path_inp", bp.get("thumbs",""),  readonly=False)
        _row("Proxies:",  _DEFAULT_PROXY_DIR,
             "_pr_path_inp", bp.get("proxies",""), readonly=False)
        # Keep proxy_dir_inp alias for backwards compat
        self._proxy_dir_inp = self._pr_path_inp

        dl.addSpacing(10)
        dl.addWidget(_section_label("BACKUP & INTEGRITY"))
        self._db_status = QLabel("")
        self._db_status.setStyleSheet("color: rgb(52,211,153);")
        dl.addWidget(self._db_status)
        btn_row = QHBoxLayout(); btn_row.setSpacing(6)
        verify_btn  = QPushButton("  \u2713  Verify  ")
        backup_btn  = QPushButton("  \u2b73  Backup  ")
        restore_btn = QPushButton("  \u21ba  Restore  ")
        backup_btn.setObjectName("btn_accent")
        verify_btn.clicked.connect(self._verify_db)
        backup_btn.clicked.connect(self._backup_db)
        restore_btn.clicked.connect(self._restore_db)
        btn_row.addWidget(verify_btn)
        btn_row.addWidget(backup_btn)
        btn_row.addWidget(restore_btn)
        btn_row.addStretch()
        dl.addLayout(btn_row)
        dl.addStretch()
        self._lib = lib
        return tab

    def _main_window(self):
        w = self.parent()
        while w is not None:
            if hasattr(w, 'apply_theme'): return w
            p = getattr(w, 'parent', None)
            w = p() if callable(p) else None
        return None

    def _preview_theme(self, name: str):
        self.settings.theme = name
        for n, b in self._theme_btns.items():
            b.blockSignals(True); b.setChecked(n == name); b.blockSignals(False)
        mw = self._main_window()
        if mw: mw.apply_theme(name, self.settings.accent_color)

    def _preview_accent(self, name: str):
        self.settings.accent_color = name
        for n, b in self._accent_btns.items():
            b.blockSignals(True); b.setChecked(n == name); b.blockSignals(False)
        mw = self._main_window()
        if mw: mw.apply_theme(self.settings.theme, name)

    def _set_card_size(self, name: str):
        self.settings.card_size = name
        for n, b in self._size_btns.items():
            b.blockSignals(True); b.setChecked(n == name); b.blockSignals(False)

    def _browse_path(self, inp_widget, default_path):
        """Generic folder browser that writes into inp_widget."""
        current = inp_widget.text() or str(default_path)
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", current)
        if folder:
            inp_widget.setText(folder)
    def _verify_db(self):
        ok, msg = Library.verify_file(LIBRARY_FILE)
        self._db_status.setStyleSheet(
            f"color: {'rgb(52,211,153)' if ok else 'rgb(248,113,113)'};")
        self._db_status.setText(f"Database: {msg}")

    def _backup_db(self):
        ok, msg = self._lib.backup()
        self._db_status.setStyleSheet(
            f"color: {'rgb(52,211,153)' if ok else 'rgb(248,113,113)'};")
        self._db_status.setText(msg)

    def _restore_db(self):
        if QMessageBox.question(self, "Restore",
                "Overwrite current database with backup?",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            ok, msg = self._lib.restore_from_backup()
            self._db_status.setStyleSheet(
                f"color: {'rgb(52,211,153)' if ok else 'rgb(248,113,113)'};")
            self._db_status.setText(msg)
            if ok and self.parent(): self.parent()._reload_library()

    def _reset_defaults(self):
        from PySide2.QtWidgets import QMessageBox
        r = QMessageBox.question(
            self, "Reset",
            "Reset all settings to defaults?\n\n"
            "This will not delete your library or assets.",
            QMessageBox.Yes | QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        self.settings = Settings()
        self.reject()
        if self.parent():
            self.parent().apply_theme(
                self.settings.theme, self.settings.accent_color)

    def _run_sqlite_migration(self):
        from PySide2.QtWidgets import QMessageBox
        try:
            from sqlite_db import SQLiteLibrary
            slib = SQLiteLibrary()
            count = slib.migrate_from_json()
            slib.close()
            QMessageBox.information(
                self, "Migration Complete",
                f"Migrated {count} assets to SQLite.\n\n"
                f"Set storage backend to 'SQLite' and restart\n"
                f"to use the new database.")
        except Exception as e:
            QMessageBox.warning(
                self, "Migration Error", f"Migration failed:\n{e}")

    def _run_json_migration(self):
        from PySide2.QtWidgets import QMessageBox
        try:
            from sqlite_db import SQLiteLibrary
            slib = SQLiteLibrary()
            slib.export_to_json()
            count = len(slib.all_assets())
            slib.close()
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {count} assets to JSON.\n\n"
                f"Set storage backend to 'JSON' and restart\n"
                f"to use the JSON library.")
        except Exception as e:
            QMessageBox.warning(
                self, "Export Error", f"Export failed:\n{e}")

    def get_settings(self) -> Settings:
        s = self.settings
        s.grid_show_filename     = self._show_filename.isChecked()
        s.grid_show_resolution   = self._show_res.isChecked()
        s.grid_show_tags         = self._show_tags.isChecked()
        s.font_name              = self._font_combo.currentText()
        s.font_size              = self._font_size.value()
        s.confirm_before_delete  = self._confirm_delete.isChecked()
        s.custom_categories      = list(self._custom_cats_list)
        # Viewers
        for key, inp in self._viewer_inputs.items():
            setattr(s, key, inp.text().strip())
        # Card size — read from button state, not from mutable settings ref
        s.card_size = next(
            (n for n, b in self._size_btns.items() if b.isChecked()),
            s.card_size)
        s.view_mode_default = "list" if getattr(self, "_view_list_btn", None) and self._view_list_btn.isChecked() else "grid"
        s.hidden_base_categories = list(getattr(self, "_hidden_base_cats", []) or [])
        s.ffmpeg_path        = self._ffmpeg_inp.text().strip()
        s.vlc_path           = self._vlc_inp.text().strip()
        s.proxy_dir          = getattr(self, "_proxy_dir_inp", None) and self._proxy_dir_inp.text().strip() or ""
        s.custom_library_path = getattr(self, "_db_path_inp",  None) and self._db_path_inp.text().strip()  or ""
        s.custom_backup_path  = getattr(self, "_bk_path_inp",  None) and self._bk_path_inp.text().strip()  or ""
        s.custom_thumbs_path  = getattr(self, "_th_path_inp",  None) and self._th_path_inp.text().strip()  or ""
        # Write all custom paths to bootstrap file
        import settings as _sm
        _sm._write_bootstrap({
            "settings": getattr(self, "_st_path_inp", None) and self._st_path_inp.text().strip() or "",
            "library":  s.custom_library_path,
            "backup":   s.custom_backup_path,
            "thumbs":   s.custom_thumbs_path,
            "proxies":  s.proxy_dir,
        })
        # Guard: _time_display lives in General tab which may not be visited
        _td = getattr(self, '_time_display', None)
        if _td is not None:
            s.time_display_mode = 'frames' if _td.currentIndex() == 0 else 'timecode'
        # Performance
        _gpu = getattr(self, '_gpu_accel', None)
        if _gpu is not None:
            s.gpu_acceleration = _gpu.isChecked()
        _lt = getattr(self, '_lazy_thumbs', None)
        if _lt is not None:
            s.lazy_thumbnails = _lt.isChecked()
        _ap = getattr(self, '_auto_proxies', None)
        if _ap is not None:
            s.auto_generate_proxies = _ap.isChecked()
        _tq = getattr(self, '_thumb_quality', None)
        if _tq is not None:
            s.thumbnail_quality = 'fast' if _tq.currentIndex() == 0 else 'smooth'
        _sf = getattr(self, '_scrub_frames', None)
        if _sf is not None:
            s.scrub_frames = [4, 8, 12][_sf.currentIndex()]
        _pr = getattr(self, '_proxy_res', None)
        if _pr is not None:
            s.proxy_resolution = ["480p", "720p", "1080p"][_pr.currentIndex()]
        _mt = getattr(self, '_max_thumbs', None)
        if _mt is not None:
            s.max_memory_thumbs = [200, 500, 1000][_mt.currentIndex()]
        _tr = getattr(self, '_thumb_res', None)
        if _tr is not None:
            s.thumbnail_resolution = ["low", "medium", "high"][_tr.currentIndex()]
        # Behavior
        _rc = getattr(self, '_restore_cat', None)
        if _rc is not None:
            s.restore_last_category = _rc.isChecked()
        _is = getattr(self, '_import_summary', None)
        if _is is not None:
            s.show_import_summary = _is.isChecked()
        _dc = getattr(self, '_dbl_click', None)
        if _dc is not None:
            s.double_click_action = ["open", "explorer", "copy_path", "nothing"][_dc.currentIndex()]
        # Storage backend
        _sc = getattr(self, '_storage_combo', None)
        if _sc is not None:
            s.storage_backend = 'sqlite' if _sc.currentIndex() == 1 else 'json'
        return s

# ── Import Dialog — per-asset table ───────────────────────────────────────────

# Auto-category keywords: maps filename substrings to categories
_AUTO_CAT_KEYWORDS = {
    "fire": "Fire", "flame": "Fire", "burn": "Fire",
    "smoke": "Smoke", "fog": "Smoke", "haze": "Smoke",
    "explo": "Explosions", "blast": "Explosions", "boom": "Explosions",
    "debris": "Explosions",
    "particle": "Particles", "spark": "Particles", "dust": "Particles",
    "ember": "Particles",
    "matte": "Mattes", "alpha": "Mattes", "mask": "Mattes",
    "transition": "Transitions", "wipe": "Transitions",
    "atmos": "Atmospherics", "cloud": "Atmospherics", "sky": "Atmospherics",
    "rain": "Liquids", "water": "Liquids", "liquid": "Liquids",
    "splash": "Liquids", "drip": "Liquids",
    "distort": "Distortion", "warp": "Distortion", "heat": "Distortion",
    "lens": "Lens FX", "flare": "Lens FX", "bokeh": "Lens FX",
    "light_leak": "Lens FX",
    "grunge": "Grunge", "scratch": "Grunge", "dirt": "Grunge",
    "blood": "Blood & Gore", "gore": "Blood & Gore",
    "magic": "Magic & Energy", "energy": "Magic & Energy",
    "electric": "Magic & Energy", "lightning": "Magic & Energy",
}

def _guess_category(name: str) -> str:
    """Guess a category from a filename using keyword matching."""
    low = name.lower().replace("-", "_").replace(" ", "_")
    for kw, cat in _AUTO_CAT_KEYWORDS.items():
        if kw in low:
            return cat
    return "Misc"


class ImportDialog(QDialog):
    def __init__(self, paths: list, default_cat: str, parent=None,
                 custom_categories: list = None, hidden_categories: list = None):
        super().__init__(parent)
        self.paths = paths
        self._custom_categories = custom_categories or []
        self._hidden_categories = hidden_categories or []
        self.setWindowTitle(f"Import — {len(paths)} item(s)")
        self.setMinimumSize(820, 560)
        self.setModal(True)

        from config import get_categories, SequenceGroup, EXT_TO_TYPE
        self._categories = get_categories(
            self._custom_categories, self._hidden_categories)[1:]

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Summary ──────────────────────────────────────────────────────
        type_counts: dict = {}
        for p in paths:
            if isinstance(p, SequenceGroup):
                t = "sequence"
            else:
                t = EXT_TO_TYPE.get(p.suffix.lower(), "image")
            type_counts[t] = type_counts.get(t, 0) + 1
        summary = QLabel("  " + " · ".join(
            f"{t}: {n}" for t, n in type_counts.items()))
        summary.setObjectName("app_name")
        layout.addWidget(summary)

        # ── Batch apply bar ──────────────────────────────────────────────
        batch_bar = QFrame()
        batch_bar.setStyleSheet(
            "QFrame{background:rgba(249,115,22,8);"
            "border:1px solid rgba(249,115,22,30);border-radius:4px;}")
        bb = QHBoxLayout(batch_bar)
        bb.setContentsMargins(8, 4, 8, 4)
        bb.setSpacing(6)
        bb.addWidget(QLabel("Apply to all:"))

        self._batch_cat = QComboBox()
        self._batch_cat.addItem("—")
        for c in self._categories:
            self._batch_cat.addItem(c)
        self._batch_cat.setFixedWidth(120)
        bb.addWidget(self._batch_cat)

        self._batch_tags = QLineEdit()
        self._batch_tags.setPlaceholderText("Tags (comma-separated)")
        self._batch_tags.setFixedWidth(200)
        bb.addWidget(self._batch_tags)

        self._batch_notes = QLineEdit()
        self._batch_notes.setPlaceholderText("Notes")
        self._batch_notes.setFixedWidth(160)
        bb.addWidget(self._batch_notes)

        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("btn_accent")
        apply_btn.setFixedSize(60, 26)
        apply_btn.clicked.connect(self._apply_batch)
        bb.addWidget(apply_btn)
        bb.addStretch()
        layout.addWidget(batch_bar)

        # ── Per-asset table ──────────────────────────────────────────────
        from PySide2.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
        COLS = ["Name", "Type", "Category", "Tags", "Notes"]
        self._table = QTableWidget(len(paths), len(COLS))
        self._table.setHorizontalHeaderLabels(COLS)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(32)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.Interactive)
        hdr.setStretchLastSection(True)
        self._table.setColumnWidth(0, 200)  # Name
        self._table.setColumnWidth(1, 60)   # Type
        self._table.setColumnWidth(2, 120)  # Category
        self._table.setColumnWidth(3, 200)  # Tags

        for row, item in enumerate(paths):
            is_seq = isinstance(item, SequenceGroup)
            name   = item.name if is_seq else item.stem
            ftype  = "sequence" if is_seq else EXT_TO_TYPE.get(
                item.suffix.lower() if hasattr(item, 'suffix') else '', 'image')

            # Name (read-only)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 0, name_item)

            # Type (read-only)
            type_item = QTableWidgetItem(ftype.upper())
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 1, type_item)

            # Category (combo)
            cat_combo = QComboBox()
            for c in self._categories:
                cat_combo.addItem(c)
            guessed = _guess_category(name)
            if guessed in self._categories:
                cat_combo.setCurrentText(guessed)
            else:
                cat_combo.setCurrentText(default_cat)
            self._table.setCellWidget(row, 2, cat_combo)

            # Tags (editable text)
            self._table.setItem(row, 3, QTableWidgetItem(""))

            # Notes (editable text)
            self._table.setItem(row, 4, QTableWidgetItem(""))

        layout.addWidget(self._table, 1)

        # ── Options ──────────────────────────────────────────────────────
        opts = QHBoxLayout()
        self._auto_res = QCheckBox("Auto-detect resolution tags")
        self._auto_res.setChecked(True)
        opts.addWidget(self._auto_res)
        opts.addStretch()
        layout.addLayout(opts)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        ok_btn = QPushButton(f"  Import {len(paths)} Item(s)  ")
        ok_btn.setObjectName("btn_accent")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

    def _apply_batch(self):
        """Apply batch bar values to all rows."""
        cat = self._batch_cat.currentText()
        tags = self._batch_tags.text().strip()
        notes = self._batch_notes.text().strip()
        for row in range(self._table.rowCount()):
            if cat and cat != "—":
                combo = self._table.cellWidget(row, 2)
                if combo:
                    combo.setCurrentText(cat)
            if tags:
                item = self._table.item(row, 3)
                if item:
                    existing = item.text().strip()
                    merged = f"{existing}, {tags}" if existing else tags
                    item.setText(merged)
            if notes:
                item = self._table.item(row, 4)
                if item:
                    existing = item.text().strip()
                    merged = f"{existing} {notes}" if existing else notes
                    item.setText(merged)

    def get_result(self) -> list:
        """Return per-asset metadata list.

        Each element: {"category": str, "tags": list, "notes": str}
        Indexed same as self.paths.
        """
        from config import normalize_tag
        results = []
        for row in range(self._table.rowCount()):
            combo = self._table.cellWidget(row, 2)
            cat   = combo.currentText() if combo else "Misc"
            raw_tags = (self._table.item(row, 3).text()
                        if self._table.item(row, 3) else "")
            tags = [normalize_tag(t) for t in raw_tags.split(",") if t.strip()]
            notes = (self._table.item(row, 4).text()
                     if self._table.item(row, 4) else "")
            results.append({
                "category": cat,
                "tags": tags,
                "notes": notes.strip(),
            })
        return results

    def get_auto_res(self) -> bool:
        return self._auto_res.isChecked()

# ── Tag Editor Dialog ─────────────────────────────────────────────────────────

class TagEditorDialog(QDialog):
    def __init__(self, asset: Asset, lib: Library, parent=None):
        super().__init__(parent)
        self.asset = asset
        self.lib   = lib
        self.setWindowTitle(f"Edit Tags — {asset.name}")
        self.setMinimumSize(480, 420)
        ll = QVBoxLayout(self)
        ll.addWidget(QLabel(f"<b>{asset.name}</b>"))
        ll.addWidget(QLabel(
            f"{asset.category}  ·  {asset.format}  ·  {asset.display_res}"))
        ll.addWidget(_section_label("CURRENT TAGS"))
        self._tag_list = QLabel()
        self._refresh_tag_list()
        ll.addWidget(self._tag_list)
        ll.addWidget(_section_label("ADD TAGS (comma-separated)"))
        self._add_input = QLineEdit()
        self._add_input.setPlaceholderText("Alpha, Loop, 4K…")
        self._add_input.returnPressed.connect(self._do_add)
        ll.addWidget(self._add_input)
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(lambda checked=False: self._do_add())
        ll.addWidget(add_btn)
        ll.addWidget(_section_label("PRESET TAGS"))
        for grp_name, grp_tags in [
            ("Resolution", ["8K","4K","2K","HD"]),
            ("Alpha",      ["Alpha","Pre-Mult","No Alpha"]),
            ("Loop",       ["Loop","Seamless","One-Shot"]),
            ("Blend",      ["Overlay","Screen","Add","Multiply"]),
            ("Motion",     ["Slow","Fast","Still"]),
        ]:
            row_w = QWidget(); row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0,0,0,0)
            lbl = QLabel(f"{grp_name:<12}")
            lbl.setStyleSheet(
                "color:rgb(71,85,105);font-size:10px;min-width:80px;")
            row_l.addWidget(lbl)
            for tname in grp_tags:
                pill = TagPill(tname, active=(tname in asset.tags), search_enabled=False)
                pill.pressed_tag.connect(
                    lambda t, p=pill: self._toggle_preset(t, p))
                row_l.addWidget(pill)
            row_l.addStretch()
            ll.addWidget(row_w)
        done_btn = QPushButton("Done")
        done_btn.setObjectName("btn_accent")
        done_btn.clicked.connect(self.accept)
        ll.addWidget(done_btn)

    def _refresh_tag_list(self):
        text = "  " + "  ".join(self.asset.tags) if self.asset.tags else "  (no tags)"
        self._tag_list.setText(text)
        self._tag_list.setStyleSheet("color:rgb(148,163,184);font-size:11px;")

    def _do_add(self):
        for t in [x.strip() for x in self._add_input.text().split(",") if x.strip()]:
            if t not in self.asset.tags:
                self.asset.tags.append(t)
        self.lib.update(self.asset)
        self._add_input.clear()
        self._refresh_tag_list()

    def _toggle_preset(self, tag: str, pill):
        if tag in self.asset.tags:
            self.asset.tags.remove(tag); pill.setActive(False)
        else:
            self.asset.tags.append(tag); pill.setActive(True)
        self.lib.update(self.asset)
        self._refresh_tag_list()
