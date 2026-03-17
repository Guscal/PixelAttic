"""
widgets.py — Reusable UI widgets for Pixel Attic.
"""
import hashlib
from pathlib import Path
from typing import Optional

from PySide2.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QWidget, QScrollArea
)
from PySide2.QtGui  import QPixmap, QCursor, QPainter, QPen, QColor
from PySide2.QtCore import Qt, Signal, QRect

from config   import TAG_COLORS
from database import Asset

# ── Global pill-click callback (set by app at startup) ────────────────────────
_pill_search_requested = None

# ── Tag Pill ──────────────────────────────────────────────────────────────────

class TagPill(QPushButton):
    """Colored pill button for tags.

    search_enabled=True  (default) — clicking also adds tag to the search bar.
    search_enabled=False            — only emits pressed_tag; no search-bar side-effect.
                                      Use for edit/toggle contexts (detail panel,
                                      right-click menu, list-view pills).
    """
    pressed_tag = Signal(str)

    def __init__(self, tag_name: str, active: bool = False, parent=None,
                 search_enabled: bool = True):
        from config import normalize_tag
        display = normalize_tag(tag_name).upper() if tag_name else tag_name
        super().__init__(f" {display} ", parent)
        self.tag_name        = normalize_tag(tag_name) if tag_name else tag_name
        self._search_enabled = search_enabled
        self.setFlat(True)
        self.setFixedHeight(20)
        self.setActive(active)
        self.clicked.connect(self._on_click)

    def _on_click(self, checked=False):
        self.pressed_tag.emit(self.tag_name)
        if self._search_enabled:
            global _pill_search_requested
            if _pill_search_requested is not None:
                _pill_search_requested(self.tag_name)

    @staticmethod
    def _color_for_tag(tag_name: str) -> tuple:
        if tag_name in TAG_COLORS:
            return TAG_COLORS[tag_name]
        h = int(hashlib.md5(tag_name.encode()).hexdigest(), 16)
        PALETTE = [
            (248,113,113),(251,146, 60),(251,191, 36),(163,230, 53),
            ( 52,211,153),( 45,212,191),( 34,211,238),( 96,165,250),
            (129,140,248),(167,139,250),(192,132,252),(244,114,182),
            (110,231,183),(125,211,252),(253,186, 86),
        ]
        return PALETTE[h % len(PALETTE)]

    def setActive(self, active: bool):
        self._active = active
        r, g, b = self._color_for_tag(self.tag_name)
        if active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({r},{g},{b},55);
                    color: rgb({r},{g},{b});
                    border: 1px solid rgba({r},{g},{b},120);
                    border-radius: 3px; padding: 1px 5px; font-size: 11px;
                }}
                QPushButton:hover {{
                    background: rgba({r},{g},{b},90);
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba({r},{g},{b},18);
                    color: rgba({r},{g},{b},160);
                    border: 1px solid rgba({r},{g},{b},35);
                    border-radius: 3px; padding: 1px 5px; font-size: 11px;
                }}
                QPushButton:hover {{
                    background: rgba({r},{g},{b},40);
                    color: rgb({r},{g},{b});
                    border: 1px solid rgba({r},{g},{b},80);
                }}
            """)

# ── Flow Tag Layout ───────────────────────────────────────────────────────────

class FlowTagLayout(QVBoxLayout):
    """Pills in horizontal rows, wrapping every 4 items."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = []
        self.setSpacing(4)
        self.setContentsMargins(0, 0, 0, 0)
        self._row = None
        self._row_layout = None
        self._new_row()

    def _new_row(self):
        self._row = QWidget()
        self._row_layout = QHBoxLayout(self._row)
        self._row_layout.setContentsMargins(0, 0, 0, 0)
        self._row_layout.setSpacing(4)
        self._row_layout.addStretch()
        super().addWidget(self._row)

    def addWidget(self, widget):
        self._widgets.append(widget)
        self._row_layout.insertWidget(self._row_layout.count() - 1, widget)
        if len(self._widgets) % 4 == 0:
            self._new_row()

    def count(self):
        return len(self._widgets)

    def takeAt(self, i):
        if i < len(self._widgets):
            w = self._widgets.pop(i)
            class _Item:
                def widget(self_): return w
            return _Item()
        return None

# ── Asset Card ────────────────────────────────────────────────────────────────

class AssetCard(QFrame):
    """Single card in the grid — supports hover scrub, star, drag."""
    clicked       = Signal(str)
    rightClicked  = Signal(str)
    doubleClicked = Signal(str)
    starToggled   = Signal(str, bool)  # (asset_id, starred)

    def __init__(self, asset: Asset, thumb_path: Optional[Path],
                 card_w: int, card_h: int,
                 show_filename: bool, show_res: bool, show_tags: bool,
                 accent: str = "Orange", strip_path: Optional[Path] = None,
                 parent=None):
        super().__init__(parent)
        self.asset_id   = asset.id
        self._asset     = asset
        self._accent    = accent
        self._selected  = False
        self._hovered   = False

        # Cache accent color once (avoid hot import in paintEvent/mouseMoveEvent)
        from settings import ACCENT_COLORS
        self._accent_rgb = ACCENT_COLORS.get(accent, (249, 115, 22))

        # Scrub state
        self._strip_pix = None
        self._n_frames  = 8
        self._scrub_idx = -1
        self._thumb_lbl = None
        self._thumb_pix = None
        self._strip_w   = 0
        self._strip_h   = 0

        if strip_path and Path(strip_path).exists():
            self._strip_pix = QPixmap(str(strip_path))
            if not self._strip_pix.isNull():
                self._strip_w = self._strip_pix.width() // self._n_frames
                self._strip_h = self._strip_pix.height()

        self.setProperty("class", "AssetCard")
        self.setFixedSize(card_w, card_h)
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMouseTracking(True)

        # ── File existence (cached on asset to avoid repeated disk I/O) ──
        if not hasattr(asset, '_exists_cached'):
            asset._exists_cached = Path(asset.path).exists()
        self._file_missing = not asset._exists_cached

        # ── Tooltip: full path (red prefix if missing) ────────────────────
        if self._file_missing:
            self.setToolTip(f"⚠ FILE MISSING\n{asset.path}")
        else:
            self.setToolTip(asset.path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # ── Thumbnail area ───────────────────────────────────────────────
        _below = 2  # scrub bar
        if show_filename: _below += 15
        if show_res:      _below += 14
        if show_tags and hasattr(asset, 'tags') and asset.tags:
            _below += 22  # TagPill native height=20 + 2px breathing
        self._thumb_h = max(40, card_h - 4 - _below)
        self._thumb_w = card_w - 4

        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(self._thumb_w, self._thumb_h)
        thumb_lbl.setAlignment(Qt.AlignCenter)
        thumb_lbl.setStyleSheet("background: rgb(9,9,16); border-radius: 2px;")

        if thumb_path and Path(thumb_path).exists():
            pix = QPixmap(str(thumb_path)).scaled(
                self._thumb_w, self._thumb_h,
                Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
            thumb_lbl.setPixmap(pix)
            self._thumb_pix = pix
            self._is_placeholder = False
        elif asset.file_type in ("video", "sequence"):
            # Video/sequence without thumb → background thread will generate it
            thumb_lbl.setText(f"⟳\n{asset.format or asset.file_type.upper()}")
            thumb_lbl.setStyleSheet(
                "color: rgba(249,115,22,90); font-size: 14px;"
                " background: rgb(9,9,16); border-radius: 2px;")
            self._is_placeholder = True
        else:
            thumb_lbl.setText(asset.format or "?")
            thumb_lbl.setStyleSheet(
                "color: rgba(100,116,139,100); font-size: 18px;"
                " background: rgb(9,9,16); border-radius: 2px;")
            self._is_placeholder = True

        self._thumb_lbl = thumb_lbl
        # Event filter: forward mouse moves from thumb to card for scrubbing
        thumb_lbl.setMouseTracking(True)
        thumb_lbl.installEventFilter(self)
        layout.addWidget(thumb_lbl)

        # ── Missing-file badge (overlays bottom-left of thumb) ────────────
        if self._file_missing:
            badge = QLabel("MISSING")
            badge.setParent(thumb_lbl)
            badge.setStyleSheet(
                "background: rgba(220,50,50,180); color: white;"
                " font-size: 9px; font-weight: bold; border-radius: 2px;"
                " padding: 1px 4px;")
            badge.setAlignment(Qt.AlignCenter)
            badge.adjustSize()
            badge.move(2, self._thumb_h - badge.height() - 2)

        # ── Star button (overlays top-right of thumb) ─────────────────────
        from icons import icon_path, icon_exists
        from PySide2.QtGui import QIcon as _QIcon
        self._starred = asset.starred if hasattr(asset, 'starred') else False
        self._star_btn = QPushButton(thumb_lbl)
        self._star_btn.setFixedSize(22, 22)
        self._star_btn.move(self._thumb_w - 24, 2)
        self._star_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._has_star_icons = icon_exists("star.png") and icon_exists("outline.png")
        if self._has_star_icons:
            self._star_icon_on  = _QIcon(icon_path("star.png"))
            self._star_icon_off = _QIcon(icon_path("outline.png"))
        self._update_star_style()
        self._star_btn.clicked.connect(self._toggle_star)
        self._star_btn.show()

        # Scrub position indicator (thin bar below thumb)
        self._scrub_bar = QFrame()
        self._scrub_bar.setFixedHeight(2)
        self._scrub_bar.setStyleSheet("background: transparent;")
        layout.addWidget(self._scrub_bar)

        # ── Filename ──────────────────────────────────────────────────────
        if show_filename:
            _max_chars = max(10, card_w // 8)
            _name = asset.name[:_max_chars] + ("…" if len(asset.name) > _max_chars else "")
            name_lbl = QLabel(_name)
            name_lbl.setFixedHeight(15)
            if self._file_missing:
                name_lbl.setStyleSheet(
                    "color: rgba(248,113,113,160); font-size: 11px;")
            else:
                name_lbl.setStyleSheet(
                    "color: rgb(226,232,240); font-size: 11px;")
            name_lbl.setToolTip(asset.name)
            layout.addWidget(name_lbl)

        # ── Format + resolution ───────────────────────────────────────────
        if show_res:
            res_w = QWidget()
            res_w.setFixedHeight(14)
            res_w.setStyleSheet("background:transparent;")
            row = QHBoxLayout(res_w)
            row.setSpacing(4)
            row.setContentsMargins(0, 0, 0, 0)
            r, g, b = TagPill._color_for_tag(asset.format or "")
            fmt_lbl = QLabel(asset.format or "")
            fmt_lbl.setStyleSheet(f"color: rgb({r},{g},{b}); font-size: 10px;")
            res_lbl = QLabel(asset.display_res)
            res_lbl.setStyleSheet("color: rgb(71,85,105); font-size: 10px;")
            row.addWidget(fmt_lbl)
            row.addWidget(res_lbl)
            row.addStretch()
            layout.addWidget(res_w)

        # ── Tags with expand/collapse ─────────────────────────────────────
        if show_tags and asset.tags:
            self._show_filename = show_filename
            self._show_res      = show_res
            self._show_tags     = show_tags
            self._tag_overlay   = None  # ref to expanded overlay

            self._tags_outer = QWidget()
            self._tags_outer.setStyleSheet("background: transparent;")
            self._tags_vl = QVBoxLayout(self._tags_outer)
            self._tags_vl.setContentsMargins(0, 0, 0, 0)
            self._tags_vl.setSpacing(0)
            self._build_tag_rows(collapsed=True)
            layout.addWidget(self._tags_outer)

    def _cleanup_popup(self):
        ov = getattr(self, '_tag_overlay', None)
        if ov:
            ov.hide()
            ov.deleteLater()
            self._tag_overlay = None

    def hideEvent(self, event):
        self._cleanup_popup()
        super().hideEvent(event)

    # Max pills that fit in one row — calculated from card width
    @property
    def _max_pills(self):
        # Average pill ~42px + 2px gap, "+N" badge ~26px
        avail = self._thumb_w - 28  # reserve space for "+N"
        per_pill = 44  # avg pill width
        return max(1, avail // per_pill)

    def _build_tag_rows(self, collapsed: bool = True):
        """Collapsed: 1 compact row + '+N'. Expanded: overlay inside card with scroll."""
        while self._tags_vl.count():
            item = self._tags_vl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cleanup_popup()

        tags = self._asset.tags
        if not tags:
            return

        MAX = self._max_pills

        if collapsed:
            row = QWidget()
            row.setFixedHeight(22)
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            for t in tags[:MAX]:
                pill = TagPill(t, active=False)
                rl.addWidget(pill)
            overflow = len(tags) - MAX
            if overflow > 0:
                more = QPushButton(f"+{overflow}")
                more.setFixedSize(24, 20)
                more.setStyleSheet(
                    "QPushButton{background:rgba(71,85,105,40);color:rgb(100,116,139);"
                    "border:1px solid rgba(71,85,105,60);border-radius:3px;"
                    "font-size:9px;padding:0;}"
                    "QPushButton:hover{background:rgba(249,115,22,30);"
                    "color:rgb(249,115,22);}")
                more.setToolTip(f"Show all {len(tags)} tags")
                more.clicked.connect(self._expand_tags)
                rl.addWidget(more)
            rl.addStretch()
            self._tags_vl.addWidget(row)
        else:
            # Show mini label in the normal row
            mini = QWidget()
            mini.setFixedHeight(16)
            mini.setStyleSheet("background:transparent;")
            ml = QHBoxLayout(mini)
            ml.setContentsMargins(0, 0, 0, 0)
            ml.setSpacing(2)
            ml.addStretch()
            self._tags_vl.addWidget(mini)

            # ── Overlay: dark bg, expands up from bottom, inside card ──
            card_w = self.width()
            card_h = self.height()

            # Build all pill rows into inner widget
            inner = QWidget()
            inner.setStyleSheet("background:transparent;")
            inner_l = QVBoxLayout(inner)
            inner_l.setContentsMargins(4, 4, 4, 2)
            inner_l.setSpacing(2)
            for chunk_start in range(0, len(tags), MAX):
                row = QWidget()
                row.setStyleSheet("background:transparent;")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(0, 0, 0, 0)
                rl.setSpacing(3)
                for t in tags[chunk_start:chunk_start + MAX]:
                    pill = TagPill(t, active=False)
                    pill.setFixedHeight(16)
                    rl.addWidget(pill)
                rl.addStretch()
                inner_l.addWidget(row)
            inner_l.addStretch()

            # Measure how tall the pills would be
            row_count = len(range(0, len(tags), MAX))
            pills_h = row_count * 20 + 8  # rows + padding
            # Max overlay height: 70% of card (leave top of thumb visible)
            max_overlay_h = int(card_h * 0.7)
            content_h = min(pills_h, max_overlay_h - 24)  # 24 for less btn

            overlay = QWidget(self)
            overlay.setStyleSheet(
                "background:rgba(6,8,16,210);border-radius:4px;")
            ol = QVBoxLayout(overlay)
            ol.setContentsMargins(0, 0, 0, 0)
            ol.setSpacing(0)

            if pills_h <= max_overlay_h - 24:
                # All pills fit — no scroll needed
                ol.addWidget(inner)
            else:
                # Needs scroll
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                scroll.setFrameShape(QFrame.NoFrame)
                scroll.setStyleSheet("background:transparent;")
                scroll.setFixedHeight(content_h)
                scroll.setWidget(inner)
                ol.addWidget(scroll)

            # Less button — always at bottom of overlay
            less = QPushButton("▴ less")
            less.setFixedHeight(20)
            less.setStyleSheet(
                "QPushButton{background:rgba(30,34,55,220);color:rgb(140,150,175);"
                "border-top:1px solid rgba(55,60,90,120);border-radius:0;"
                "font-size:9px;padding:0 8px;}"
                "QPushButton:hover{color:rgb(220,228,245);"
                "background:rgba(40,46,70,240);}")
            less.clicked.connect(self._collapse_tags)
            ol.addWidget(less)

            overlay_h = content_h + 20 + 4  # content + less btn + margin
            overlay.setGeometry(
                2, card_h - overlay_h - 2,
                card_w - 4, overlay_h)
            overlay.raise_()
            overlay.show()
            self._tag_overlay = overlay

    def _expand_tags(self, checked=False):
        self._build_tag_rows(collapsed=False)

    def _collapse_tags(self, checked=False):
        self._build_tag_rows(collapsed=True)

    # ── Live update API (called from background thread callbacks) ─────────

    def update_thumbnail(self, thumb_path):
        """Replace placeholder with a real thumbnail. Called when bg thread finishes."""
        if not thumb_path or not Path(str(thumb_path)).exists():
            return
        pix = QPixmap(str(thumb_path)).scaled(
            self._thumb_w, self._thumb_h,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        if pix.isNull():
            return
        self._thumb_pix = pix
        self._is_placeholder = False
        if self._thumb_lbl:
            self._thumb_lbl.setPixmap(pix)
            self._thumb_lbl.setStyleSheet(
                "background: rgb(9,9,16); border-radius: 2px;")

    def update_strip(self, strip_path):
        """Load a scrub strip from disk. Called when bg thread finishes."""
        if not strip_path or not Path(str(strip_path)).exists():
            return
        pix = QPixmap(str(strip_path))
        if pix.isNull():
            return
        self._strip_pix = pix
        self._n_frames  = 8
        self._strip_w   = pix.width() // self._n_frames
        self._strip_h   = pix.height()

    # ── Selection & paint ─────────────────────────────────────────────────────

    def setSelected(self, selected: bool):
        self._selected = selected
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        if self._selected:
            ar, ag, ab = self._accent_rgb
            painter.setPen(QPen(QColor(ar, ag, ab), 1.5))
        elif self._hovered:
            painter.setPen(QPen(QColor(70, 80, 105), 1))
        elif self._file_missing:
            painter.setPen(QPen(QColor(180, 60, 60, 120), 1))
        else:
            painter.setPen(QPen(QColor(30, 30, 50), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(r, 4, 4)
        painter.end()

    # ── Hover scrub ───────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self._scrub_idx = -1
        self._scrub_frac = 0.0
        if self._strip_pix:
            self._scrub_bar.setStyleSheet(
                "background: rgba(249,115,22,30); border-radius: 1px;")
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self._scrub_idx  = -1
        self._scrub_frac = 0.0
        self._scrub_bar.setStyleSheet("background: transparent;")
        if self._thumb_lbl and self._thumb_pix:
            self._thumb_lbl.setPixmap(self._thumb_pix)
        self.update()

    # (mouseMoveEvent is defined below with drag + scrub combined)

    def eventFilter(self, obj, event):
        """Forward mouse moves from thumb_lbl to card for scrubbing."""
        from PySide2.QtCore import QEvent
        if event.type() == QEvent.MouseMove and obj is self._thumb_lbl:
            # Map position to card coords and call our handler
            pos = obj.mapTo(self, event.pos())
            class _FakeEv:
                def x(_s): return pos.x()
            self.mouseMoveEvent(_FakeEv())
        return False  # don't consume — let normal handling continue

    # ── Star toggle ────────────────────────────────────────────────────────

    def _toggle_star(self, checked=False):
        self._starred = not self._starred
        self._update_star_style()
        self.starToggled.emit(self.asset_id, self._starred)

    def set_starred(self, starred: bool):
        """Set star state externally (no signal emitted)."""
        self._starred = starred
        self._update_star_style()

    def _update_star_style(self):
        if self._has_star_icons:
            self._star_btn.setIcon(
                self._star_icon_on if self._starred else self._star_icon_off)
            from PySide2.QtCore import QSize
            self._star_btn.setIconSize(QSize(14, 14))
        else:
            self._star_btn.setText("★" if self._starred else "☆")
        if self._starred:
            self._star_btn.setStyleSheet(
                "QPushButton{background:rgba(251,191,36,25);"
                "color:rgb(251,191,36);border:none;font-size:14px;padding:0;}"
                "QPushButton:hover{color:rgb(253,224,71);}")
        else:
            self._star_btn.setStyleSheet(
                "QPushButton{background:transparent;"
                "color:rgba(100,116,139,0);border:none;font-size:14px;padding:0;}"
                "QPushButton:hover{color:rgba(251,191,36,160);}")

    # ── Mouse events + drag to external apps ─────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start = event.pos()
            self.clicked.emit(self.asset_id)
        elif event.button() == Qt.RightButton:
            self.rightClicked.emit(self.asset_id)

    def mouseMoveEvent(self, event):
        # ── Drag-to-external-app: left button held + moved far enough ────
        if (event.buttons() & Qt.LeftButton
                and hasattr(self, '_drag_start')
                and (event.pos() - self._drag_start).manhattanLength() > 20):
            from PySide2.QtCore import QMimeData, QUrl
            from PySide2.QtGui  import QDrag
            drag = QDrag(self)
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(self._asset.path))])
            mime.setText(str(self._asset.path))
            drag.setMimeData(mime)
            if self._thumb_pix:
                drag.setPixmap(self._thumb_pix.scaled(
                    80, 60, Qt.KeepAspectRatio, Qt.FastTransformation))
            drag.exec_(Qt.CopyAction)
            return

        # ── Hover scrub (no button pressed) ──────────────────────────────
        if not self._strip_pix:
            return
        frac = max(0.0, min(1.0, event.x() / max(self.width(), 1)))
        idx  = min(int(frac * self._n_frames), self._n_frames - 1)
        if idx != self._scrub_idx:
            self._scrub_idx = idx
            self._scrub_frac = frac
            if self._thumb_lbl and self._strip_w > 0:
                frame = self._strip_pix.copy(
                    QRect(idx * self._strip_w, 0, self._strip_w, self._strip_h))
                # FastTransformation during live scrub — big perf win
                scaled = frame.scaled(
                    self._thumb_w, self._thumb_h,
                    Qt.KeepAspectRatioByExpanding, Qt.FastTransformation)
                self._thumb_lbl.setPixmap(scaled)
            ar, ag, ab = self._accent_rgb
            pct = max(0, min(100, int(frac * 100)))
            self._scrub_bar.setStyleSheet(
                f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:{max(pct-1,0)/100:.2f} rgba({ar},{ag},{ab},200),"
                f"stop:{min(pct+1,100)/100:.2f} rgba({ar},{ag},{ab},30));"
                "border-radius:1px;")
            self.update()

    def eventFilter(self, obj, event):
        """Forward mouse moves from thumb_lbl to card for scrubbing."""
        from PySide2.QtCore import QEvent
        if event.type() == QEvent.MouseMove and obj is self._thumb_lbl:
            pos = obj.mapTo(self, event.pos())
            class _FakeEv:
                def x(_s): return pos.x()
                def buttons(_s): return Qt.NoButton
                def pos(_s): return pos
            self.mouseMoveEvent(_FakeEv())
        return False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.doubleClicked.emit(self.asset_id)

class ContentArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("background: transparent;")

    def set_content(self, widget: QWidget, preserve_scroll: bool = False):
        _scroll_y = self.verticalScrollBar().value() if preserve_scroll else 0
        old = self.takeWidget()
        if old:
            old.deleteLater()
        self.setWidget(widget)
        if preserve_scroll and _scroll_y > 0:
            # Defer scroll restore until Qt has laid out the new widget
            from PySide2.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.verticalScrollBar().setValue(_scroll_y))

# ── Virtual Grid — only renders visible cards ────────────────────────────────

import math

class VirtualGrid(QWidget):
    """High-performance grid that only creates card widgets for visible rows.
    Cards outside the viewport are destroyed. Connects to QScrollArea."""

    def __init__(self, scroll_area: QScrollArea, parent=None):
        super().__init__(parent)
        self._scroll = scroll_area
        self._assets = []
        self._cols = 4
        self._card_w = 210
        self._card_h = 200
        self._gap = 8
        self._card_factory = None
        self._visible_cards = {}    # row_index -> [card widgets]
        self._buffer_rows = 2
        self._total_rows = 0
        self._row_h = 0
        self._connected = False

    def configure(self, assets, cols, card_w, card_h, card_factory):
        """Set data and dimensions. card_factory(asset) -> QWidget."""
        for cards in self._visible_cards.values():
            for c in cards:
                c.setParent(None); c.deleteLater()
        self._visible_cards.clear()

        self._assets = assets
        self._cols = max(1, cols)
        self._card_w = card_w
        self._card_h = card_h
        self._card_factory = card_factory
        self._gap = 8
        self._row_h = card_h + self._gap
        self._total_rows = math.ceil(len(assets) / self._cols) if assets else 0

        total_h = max(1, self._total_rows * self._row_h + self._gap)
        self.setMinimumHeight(total_h)
        self.setFixedHeight(total_h)

        if not self._connected:
            self._scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
            self._connected = True

        self._on_scroll()

    def _on_scroll(self, _value=0):
        if not self._assets or not self._card_factory:
            return
        if getattr(self, '_frozen', False):
            return
        vp_h = self._scroll.viewport().height()
        scroll_y = self._scroll.verticalScrollBar().value()
        first_row = max(0, scroll_y // self._row_h - self._buffer_rows)
        last_row = min(
            self._total_rows - 1,
            (scroll_y + vp_h) // self._row_h + self._buffer_rows)
        visible_set = set(range(first_row, last_row + 1))

        # Remove rows no longer visible
        for r in list(self._visible_cards.keys()):
            if r not in visible_set:
                for card in self._visible_cards[r]:
                    card.setParent(None); card.deleteLater()
                del self._visible_cards[r]

        # Centering offset
        total_grid_w = self._cols * self._card_w + (self._cols - 1) * self._gap
        x_offset = max(0, (self.width() - total_grid_w) // 2)

        # Add newly visible rows
        for r in range(first_row, last_row + 1):
            if r in self._visible_cards:
                continue
            start = r * self._cols
            end = min(start + self._cols, len(self._assets))
            if start >= len(self._assets):
                continue
            cards = []
            for i, asset in enumerate(self._assets[start:end]):
                card = self._card_factory(asset)
                card.setParent(self)
                x = x_offset + i * (self._card_w + self._gap)
                y = r * self._row_h + self._gap // 2
                card.move(x, y)
                card.show()
                cards.append(card)
            self._visible_cards[r] = cards

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_frozen', False):
            return
        if self._visible_cards:
            total_grid_w = self._cols * self._card_w + (self._cols - 1) * self._gap
            x_offset = max(0, (self.width() - total_grid_w) // 2)
            for r, cards in self._visible_cards.items():
                for i, card in enumerate(cards):
                    x = x_offset + i * (self._card_w + self._gap)
                    y = r * self._row_h + self._gap // 2
                    card.move(x, y)

    def get_all_visible_cards(self):
        """Return all currently rendered cards (for selection updates etc)."""
        result = []
        for cards in self._visible_cards.values():
            result.extend(cards)
        return result

    def freeze(self):
        """Pause all card creation/destruction during resize drag."""
        self._frozen = True

    def unfreeze(self):
        """Resume and refresh visible cards."""
        self._frozen = False
        self._on_scroll()

# ── Grid Widget (legacy — used for list view) ────────────────────────────────

class GridWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 0, 4, 4)
        self._layout.setSpacing(6)

    def set_cards(self, cards: list, cols: int):
        """
        Lay cards out in rows of `cols`, centered symmetrically.
        Equal stretch on both sides of every row — same gap left and right
        at any card size, even the last partial row.
        """
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

        if not cards:
            self._layout.addStretch()
            return

        GAP = 8   # fixed gap — same px between cards in all directions
        rows = [cards[i:i + cols] for i in range(0, len(cards), cols)]

        card_w = cards[0].minimumWidth()  if cards else 0
        card_h = cards[0].minimumHeight() if cards else 0

        # Outer centering wrapper
        outer_w = QWidget()
        outer_w.setStyleSheet("background: transparent;")
        outer_l = QHBoxLayout(outer_w)
        outer_l.setContentsMargins(0, 0, 0, 0)
        outer_l.setSpacing(0)

        # Inner block — left-aligned rows, fixed row heights
        block_w_widget = QWidget()
        block_w_widget.setStyleSheet("background: transparent;")
        block_l = QVBoxLayout(block_w_widget)
        block_l.setContentsMargins(0, 0, 0, 0)
        block_l.setSpacing(GAP)   # vertical gap between rows = GAP

        for row_cards in rows:
            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            if card_h > 0:
                row_w.setFixedHeight(card_h)  # pin height → no vertical stretching
            row_l = QHBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(0)
            for j, card in enumerate(row_cards):
                row_l.addWidget(card)
                if j < len(row_cards) - 1:
                    row_l.addSpacing(GAP)   # horizontal gap between cards = GAP
            row_l.addStretch(1)
            block_l.addWidget(row_w)

        block_l.addStretch(1)   # push rows to top, extra space goes here

        outer_l.addStretch(1)
        outer_l.addWidget(block_w_widget)
        outer_l.addStretch(1)
        self._layout.addWidget(outer_w)
        self._layout.addStretch()

# ── Pagination Bar ─────────────────────────────────────────────────────────────

class PaginationBar(QWidget):
    """
    Bottom pagination bar: ← [1] [2] [3] → with page size cycle button.
    Emits page_changed(int) when user navigates.
    """
    from PySide2.QtCore import Signal as _Sig
    page_changed = _Sig(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self._total   = 1
        self.setFixedHeight(38)
        self.setStyleSheet("background: rgb(9,9,16); border-top: 1px solid rgb(22,22,36);")

        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 4, 8, 4)
        hl.setSpacing(4)

        self._prev = QPushButton("‹")
        self._prev.setFixedSize(28, 26)
        self._prev.setObjectName("page_btn")
        self._prev.clicked.connect(self._go_prev)
        hl.addWidget(self._prev)

        self._page_container = QWidget()
        self._page_container.setStyleSheet("background: transparent;")
        self._page_hl = QHBoxLayout(self._page_container)
        self._page_hl.setContentsMargins(0, 0, 0, 0)
        self._page_hl.setSpacing(2)
        hl.addWidget(self._page_container)

        self._next = QPushButton("›")
        self._next.setFixedSize(28, 26)
        self._next.setObjectName("page_btn")
        self._next.clicked.connect(self._go_next)
        hl.addWidget(self._next)

        hl.addStretch()

        self._info = QLabel("")
        self._info.setStyleSheet("color:rgb(71,85,105);font-size:11px;background:transparent;")
        hl.addWidget(self._info)

    def set_state(self, current: int, total: int, total_assets: int, page_size: int):
        self._current = current
        self._total   = max(1, total)
        self._prev.setEnabled(current > 0)
        self._next.setEnabled(current < self._total - 1)

        # Rebuild page buttons — show max 7 pages with ellipsis
        while self._page_hl.count():
            item = self._page_hl.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        pages = self._visible_pages(current, self._total)
        last_shown = -1
        for p in pages:
            if p == -1:
                dot = QLabel("…")
                dot.setStyleSheet("color:rgb(71,85,105);background:transparent;padding:0 2px;")
                self._page_hl.addWidget(dot)
            else:
                btn = QPushButton(str(p + 1))
                btn.setFixedSize(28, 26)
                btn.setObjectName("page_btn_active" if p == current else "page_btn")
                btn.clicked.connect(lambda checked=False, pg=p: self.page_changed.emit(pg))
                self._page_hl.addWidget(btn)

        start = current * page_size + 1
        end   = min((current + 1) * page_size, total_assets)
        self._info.setText(f"{start}–{end} of {total_assets}")

    def _visible_pages(self, cur: int, total: int) -> list:
        if total <= 7:
            return list(range(total))
        pages = set([0, total - 1, cur])
        for d in (-2, -1, 1, 2):
            p = cur + d
            if 0 <= p < total:
                pages.add(p)
        pages = sorted(pages)
        result = []
        prev = -1
        for p in pages:
            if prev >= 0 and p - prev > 1:
                result.append(-1)  # ellipsis
            result.append(p)
            prev = p
        return result

    def _go_prev(self):
        if self._current > 0:
            self.page_changed.emit(self._current - 1)

    def _go_next(self):
        if self._current < self._total - 1:
            self.page_changed.emit(self._current + 1)

