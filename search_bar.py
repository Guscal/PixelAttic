"""
search_bar.py — Multi-token pill search bar for Pixel Attic.

Tokens:
  plain text     → busca en nombre / notas
  #tag           → filtra por tag exacto
  cat:Category   → filtra por categoría
  >50mb  <50mb   → filtra por tamaño
  fmt:MP4        → filtra por formato

Múltiples tokens se combinan con AND.
Enter / Tab / Space después de un # confirma el token como pill.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from PySide2.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QLabel, QScrollArea, QCompleter, QSizePolicy,
    QFrame, QApplication
)
from PySide2.QtGui  import QColor, QKeyEvent, QFontMetrics
from PySide2.QtCore import Qt, Signal, QStringListModel, QTimer, QSize


# ── Token dataclass ───────────────────────────────────────────────────────────

@dataclass
class SearchToken:
    kind:  str   # "text"|"tag"|"cat"|"fmt"|"size_gt"|"size_lt"|"exclude_tag"|"exclude_fmt"|"starred"
    value: str

    @property
    def label(self) -> str:
        v = self.value.upper()
        if self.kind == "tag":         return f"#{v}"
        if self.kind == "exclude_tag": return f"!#{v}"
        if self.kind == "cat":         return f"CAT:{v}"
        if self.kind == "fmt":         return f"FMT:{v}"
        if self.kind == "exclude_fmt": return f"!FMT:{v}"
        if self.kind == "size_gt":     return f">{self.value}MB"
        if self.kind == "size_lt":     return f"<{self.value}MB"
        if self.kind == "starred":     return "STARRED"
        if self.kind == "dur_gt":      return f"DUR>{self.value}S"
        if self.kind == "dur_lt":      return f"DUR<{self.value}S"
        if self.kind == "res":         return f"RES:{v}"
        if self.kind == "codec":       return f"CODEC:{v}"
        if self.kind == "depth":       return f"DEPTH:{v}"
        if self.kind == "date":        return f"DATE:{v}"
        return v

    @property
    def color(self) -> tuple:
        """RGB for pill background tint."""
        if self.kind == "tag":         return (96, 165, 250)   # blue
        if self.kind == "exclude_tag": return (248, 113, 113)  # red
        if self.kind == "cat":         return (52, 211, 153)   # green
        if self.kind == "fmt":         return (167, 139, 250)  # purple
        if self.kind == "exclude_fmt": return (248, 113, 113)  # red
        if self.kind in ("size_gt", "size_lt"): return (245, 158, 11) # amber
        if self.kind == "starred":     return (251, 191, 36)   # gold
        if self.kind in ("dur_gt", "dur_lt"): return (45, 212, 191)  # teal
        if self.kind == "res":         return (249, 115, 22)   # orange
        if self.kind == "codec":       return (129, 140, 248)  # indigo
        if self.kind == "depth":       return (192, 132, 252)  # violet
        if self.kind == "date":        return (163, 230, 53)   # lime
        return (100, 116, 139)   # grey for text

    @classmethod
    def parse(cls, raw: str) -> Optional["SearchToken"]:
        from config import normalize_tag
        s = raw.strip()
        if not s:
            return None
        # Starred shortcut
        if s.lower() in ("starred", "star", "fav"):
            return cls("starred", "yes")
        # Exclude: !#tag  !fmt:X
        if s.startswith("!#"):
            v = s[2:].strip()
            return cls("exclude_tag", normalize_tag(v)) if v else None
        if s.lower().startswith("!fmt:"):
            v = s[5:].strip()
            return cls("exclude_fmt", v.upper()) if v else None
        # Normal tokens
        if s.startswith("#"):
            v = s[1:].strip()
            return cls("tag", normalize_tag(v)) if v else None
        low = s.lower()
        if low.startswith("cat:"):
            v = s[4:].strip()
            return cls("cat", v.title()) if v else None
        if low.startswith("fmt:"):
            v = s[4:].strip()
            return cls("fmt", v.upper()) if v else None
        # Advanced: dur:>5s  dur:<2s
        if low.startswith("dur:>"):
            v = s[5:].rstrip("s").strip()
            if v.replace(".", "").isdigit():
                return cls("dur_gt", v)
        if low.startswith("dur:<"):
            v = s[5:].rstrip("s").strip()
            if v.replace(".", "").isdigit():
                return cls("dur_lt", v)
        # Advanced: res:4K  res:HD  res:2K
        if low.startswith("res:"):
            v = s[4:].strip().upper()
            if v: return cls("res", v)
        # Advanced: codec:prores  codec:h264
        if low.startswith("codec:"):
            v = s[6:].strip().lower()
            if v: return cls("codec", v)
        # Advanced: depth:16  depth:32
        if low.startswith("depth:"):
            v = s[6:].strip()
            if v.isdigit(): return cls("depth", v)
        # Advanced: date:2024  date:2024-03
        if low.startswith("date:"):
            v = s[5:].strip()
            if v: return cls("date", v)
        # Size filters
        if s.startswith(">") and s[1:].replace(".", "").isdigit():
            return cls("size_gt", s[1:])
        if s.startswith("<") and s[1:].replace(".", "").isdigit():
            return cls("size_lt", s[1:])
        return cls("text", s)


# ── Token Pill widget ─────────────────────────────────────────────────────────

class TokenPill(QFrame):
    remove_requested = Signal(object)   # emits the SearchToken

    def __init__(self, token: SearchToken, parent=None):
        super().__init__(parent)
        self.token = token
        self._highlighted = False
        r, g, b = token.color
        self._r, self._g, self._b = r, g, b
        self._apply_style(highlighted=False)
        self.setFixedHeight(22)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(7, 0, 4, 0)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignVCenter)

        lbl = QLabel(token.label)
        lbl.setStyleSheet(
            f"color: rgb({r},{g},{b}); font-size: 11px;"
            f" border: none; background: transparent; padding: 0; margin: 0;")
        lbl.setAlignment(Qt.AlignVCenter)
        lay.addWidget(lbl)

        # Close label — QLabel gives pixel-perfect centering unlike QPushButton
        rm = QLabel("✕")
        rm.setFixedSize(14, 14)
        rm.setAlignment(Qt.AlignCenter)
        rm.setCursor(Qt.PointingHandCursor)
        rm.setStyleSheet(
            f"color: rgba({r},{g},{b},120); font-size: 10px;"
            f" border: none; background: transparent; padding: 0; margin: 0;")
        rm.mousePressEvent = lambda e, t=token: self.remove_requested.emit(t)
        # Hover effect via enter/leave
        rm.enterEvent = lambda e: rm.setStyleSheet(
            f"color: rgb(248,113,113); font-size: 10px;"
            f" border: none; background: transparent; padding: 0; margin: 0;")
        rm.leaveEvent = lambda e: rm.setStyleSheet(
            f"color: rgba({r},{g},{b},120); font-size: 10px;"
            f" border: none; background: transparent; padding: 0; margin: 0;")
        lay.addWidget(rm)

    def _apply_style(self, highlighted: bool):
        r, g, b = self._r, self._g, self._b
        if highlighted:
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba({r},{g},{b},70);
                    border: 1px solid rgba({r},{g},{b},180);
                    border-radius: 10px; padding: 0px 2px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba({r},{g},{b},30);
                    border: 1px solid rgba({r},{g},{b},90);
                    border-radius: 10px; padding: 0px 2px;
                }}
            """)

    def set_highlighted(self, on: bool):
        self._highlighted = on
        self._apply_style(on)


# ── Main search bar ───────────────────────────────────────────────────────────

class PillSearchBar(QWidget):
    """
    Multi-token pill search bar.
    Emits filter_changed(tokens) whenever the active token list changes.
    """
    filter_changed = Signal(list)   # list[SearchToken]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tokens: list[SearchToken] = []
        self._completions: list[str]   = []

        self.setObjectName("pill_search_bar")
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QWidget#pill_search_bar {
                background: transparent;
            }
        """)

        # Outer frame (looks like an input)
        frame = QFrame(self)
        frame.setObjectName("search_frame")
        frame.setStyleSheet("""
            QFrame#search_frame {
                background: rgb(14,14,24);
                border: 1px solid rgb(40,40,65);
                border-radius: 6px;
            }
            QFrame#search_frame:focus-within {
                border: 1px solid rgb(249,115,22);
            }
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

        self._inner = QHBoxLayout(frame)
        self._inner.setContentsMargins(6, 0, 4, 0)
        self._inner.setSpacing(4)
        self._inner.setAlignment(Qt.AlignVCenter)

        # Search icon
        from icons import icon_path, icon_exists
        icon = QLabel()
        if icon_exists("search.png"):
            from PySide2.QtGui import QPixmap as _SBPix
            _sp = _SBPix(icon_path("search.png")).scaled(
                14, 14, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon.setPixmap(_sp)
        else:
            icon.setText("○")
        icon.setStyleSheet("background: transparent; border: none; font-size: 12px;")
        icon.setFixedSize(18, 18)
        icon.setAlignment(Qt.AlignCenter)
        self._inner.addWidget(icon)

        # Pills + input live in a single horizontal scroll area
        # so pills and the text cursor feel like one continuous bar.
        self._flow_widget = QWidget()
        self._flow_widget.setStyleSheet("background: transparent; border: none;")
        self._flow_layout = QHBoxLayout(self._flow_widget)
        self._flow_layout.setContentsMargins(0, 0, 0, 0)
        self._flow_layout.setSpacing(4)
        self._flow_layout.setAlignment(Qt.AlignVCenter)

        # — pills get inserted here dynamically —

        # Text input (inside the same flow)
        self._input = QLineEdit()
        self._input.setPlaceholderText("Search  ·  #tag  ·  cat:Fire  ·  fmt:EXR  ·  >100mb")
        self._input.setMinimumWidth(140)
        self._input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: rgb(220,228,245);
                font-size: 13px;
                padding: 0px;
            }
        """)
        self._flow_layout.addWidget(self._input, 1)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._flow_widget)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(28)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        self._inner.addWidget(self._scroll, 1)

        # Clear all button
        self._clear_btn = QPushButton()
        self._clear_btn.setFixedSize(22, 22)
        if icon_exists("close.png"):
            from PySide2.QtGui import QIcon as _SBIcon
            from PySide2.QtCore import QSize as _SBSize
            self._clear_btn.setIcon(_SBIcon(icon_path("close.png")))
            self._clear_btn.setIconSize(_SBSize(12, 12))
        else:
            self._clear_btn.setText("✕")
        self._clear_btn.setStyleSheet(
            "QPushButton { background: rgba(248,113,113,15); color: rgb(148,163,184); "
            "border: 1px solid rgba(248,113,113,40); border-radius: 3px;"
            " font-size: 10px; padding: 0; } "
            "QPushButton:hover { background: rgba(248,113,113,30); color: rgb(248,113,113); "
            "border-color: rgba(248,113,113,100); }"
        )
        self._clear_btn.setToolTip("Clear all filters")
        self._clear_btn.hide()
        self._clear_btn.clicked.connect(self.clear_all)
        self._inner.addWidget(self._clear_btn)

        # Autocomplete
        self._model     = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setMaxVisibleItems(12)
        self._completer.popup().setStyleSheet("""
            QAbstractItemView {
                background: rgb(12,12,20);
                color: rgb(200,210,225);
                border: 1px solid rgb(40,40,65);
                border-radius: 4px;
                padding: 2px;
                selection-background-color: rgb(28,36,60);
                selection-color: rgb(249,115,22);
                font-size: 12px;
                outline: none;
            }
            QAbstractItemView::item { padding: 4px 10px; min-height: 22px; }
        """)
        self._input.setCompleter(self._completer)
        self._completer.activated.connect(self._on_completion)

        # Signals
        self._input.textChanged.connect(self._on_text_changed)
        self._input.returnPressed.connect(self._commit_input)
        self._input.installEventFilter(self)

        # Debounce timer for live text search
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._emit_changed)

        # Guard flag: prevents double-commit when completer + returnPressed both fire
        self._just_completed = False

    # ── Public API ────────────────────────────────────────────────────────────

    def set_completions(self, items: list[str]):
        """Update autocomplete suggestions from library contents."""
        self._completions = items
        self._model.setStringList(items)

    def get_tokens(self) -> list[SearchToken]:
        return list(self._tokens)

    def clear_all(self):
        self._tokens.clear()
        self._input.clear()
        self._rebuild_pills()
        self._emit_changed()

    def add_token(self, token: SearchToken):
        """Add a token pill programmatically (if not already present)."""
        if token and token not in self._tokens:
            self._tokens.append(token)
            self._rebuild_pills()
            self._emit_changed()

    def remove_token(self, kind: str, value: str):
        """Remove token(s) matching kind and value (case-insensitive value match)."""
        val_low = value.lower()
        before = len(self._tokens)
        self._tokens = [
            t for t in self._tokens
            if not (t.kind == kind and t.value.lower() == val_low)
        ]
        if len(self._tokens) != before:
            self._rebuild_pills()
            self._emit_changed()

    def replace_token_kind(self, kind: str, new_token: SearchToken):
        """Remove all tokens of `kind`, then add `new_token`.

        Useful for cat: tokens where only one should be active at a time.
        """
        self._tokens = [t for t in self._tokens if t.kind != kind]
        if new_token and new_token not in self._tokens:
            self._tokens.append(new_token)
        self._rebuild_pills()
        self._emit_changed()

    def focus_input(self):
        """Give keyboard focus to the text input field."""
        self._input.setFocus()

    # ── Input handling ────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._input and isinstance(event, QKeyEvent):
            k = event.key()
            # ── Backspace: highlight last pill → delete on second press ────
            if k == Qt.Key_Backspace and not self._input.text() and self._tokens:
                last_pill = self._get_last_pill()
                if last_pill and last_pill._highlighted:
                    # Second backspace → actually remove
                    self._remove_token(self._tokens[-1])
                else:
                    # First backspace → highlight (select) the last pill
                    self._clear_pill_highlights()
                    if last_pill:
                        last_pill.set_highlighted(True)
                return True
            # Any other key press clears pill highlights
            if k not in (Qt.Key_Backspace, Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt):
                self._clear_pill_highlights()
            # Escape clears input
            if k == Qt.Key_Escape:
                if self._input.text():
                    self._input.clear()
                else:
                    self.clear_all()
                return True
            # Tab confirms a token
            if k == Qt.Key_Tab and self._input.text().strip():
                self._commit_input()
                return True
            # Space is NOT intercepted — users can type multi-word searches
        return super().eventFilter(obj, event)

    def _get_last_pill(self):
        """Return the last TokenPill widget in the flow, or None."""
        for i in reversed(range(self._flow_layout.count())):
            item = self._flow_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TokenPill):
                return w
        return None

    def _clear_pill_highlights(self):
        """Remove highlight from all pills."""
        for i in range(self._flow_layout.count()):
            item = self._flow_layout.itemAt(i)
            w = item.widget() if item else None
            if isinstance(w, TokenPill) and w._highlighted:
                w.set_highlighted(False)

    def _on_text_changed(self, text: str):
        has_content = bool(text) or bool(self._tokens)
        self._clear_btn.setVisible(has_content)
        # Hide placeholder when pills exist — the bar already shows what's active
        self._update_placeholder()
        # Always debounce — both plain text and structured prefixes (#, cat:, etc.)
        # get live preview so the user sees results while typing.
        self._debounce.start()

    def _update_placeholder(self):
        """Show placeholder only when the bar is completely empty (no pills, no text)."""
        if self._tokens:
            self._input.setPlaceholderText("")
        else:
            self._input.setPlaceholderText(
                "Search  ·  #tag  ·  cat:Fire  ·  fmt:EXR  ·  >100mb")

    def _on_completion(self, text: str):
        """Called when user selects an item from the autocomplete popup."""
        self._just_completed = True
        self._input.setText(text)
        # Always commit the selected completion — the user explicitly chose it
        self._commit_input()
        # Reset flag after a short delay (returnPressed may fire right after)
        QTimer.singleShot(50, self._reset_completion_flag)

    def _reset_completion_flag(self):
        self._just_completed = False

    def _commit_input(self):
        # Guard: if the completer just handled this, skip the duplicate from returnPressed
        if getattr(self, '_just_completed', False) and not self._input.text().strip():
            return
        raw = self._input.text().strip()
        if not raw:
            return
        token = SearchToken.parse(raw)
        if token and token not in self._tokens:
            self._tokens.append(token)
            self._rebuild_pills()
        # Defer clear: QCompleter's internal slot writes text back AFTER activated
        # signal. Our clear must run after that, so we defer to next event loop tick.
        QTimer.singleShot(0, self._input.clear)
        self._emit_changed()

    # ── Pills ────────────────────────────────────────────────────────────────

    def _rebuild_pills(self):
        # Remove all pill widgets from the flow layout, keeping the input
        for i in reversed(range(self._flow_layout.count())):
            item = self._flow_layout.itemAt(i)
            w = item.widget() if item else None
            if w and w is not self._input:
                self._flow_layout.removeWidget(w)
                w.deleteLater()

        # Insert pills before the input (which is always last)
        input_idx = self._flow_layout.indexOf(self._input)
        for i, token in enumerate(self._tokens):
            pill = TokenPill(token)
            pill.remove_requested.connect(self._remove_token)
            self._flow_layout.insertWidget(input_idx + i, pill)

        has = bool(self._tokens) or bool(self._input.text())
        self._clear_btn.setVisible(has)
        self._update_placeholder()

        # Auto-scroll to end so newest pill + cursor are visible
        from PySide2.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: self._scroll.ensureWidgetVisible(self._input))

    def _remove_token(self, token: SearchToken):
        if token in self._tokens:
            self._tokens.remove(token)
        self._rebuild_pills()
        self._emit_changed()

    def _emit_changed(self):
        # Combine committed tokens + any live text in input
        live = self._input.text().strip()
        tokens = list(self._tokens)
        if live:
            t = SearchToken.parse(live)
            if t and t not in tokens:
                tokens.append(t)
        self.filter_changed.emit(tokens)
