"""
styles.py — Stylesheet builder for Pixel Attic.
"""
from settings import THEMES, ACCENT_COLORS


def rgb(r, g, b) -> str:
    return f"rgb({r},{g},{b})"

def rgba(r, g, b, a=255) -> str:
    return f"rgba({r},{g},{b},{a})"


def build_stylesheet(theme_name: str, accent_name: str) -> str:
    t = THEMES.get(theme_name, THEMES["Dark Industrial"])
    a = ACCENT_COLORS.get(accent_name, ACCENT_COLORS["Orange"])

    bg        = rgb(*t["bg"])
    bg2       = rgb(*t["bg2"])
    panel     = rgb(*t["panel"])
    panel2    = rgb(*t["panel2"])
    border    = rgb(*t["border"])
    border_lt = rgb(*t["border_lt"])
    text      = rgb(*t["text"])
    text_med  = rgb(*t["text_med"])
    text_dim  = rgb(*t["text_dim"])
    hover     = rgb(*t["hover"])
    selected  = rgb(*t["selected"])
    acc       = rgb(*a)
    acc_dim   = rgba(*a, 25)
    acc_med   = rgba(*a, 90)
    acc_hi    = rgba(*a, 140)

    return f"""
    /* ── Base ── */
    QMainWindow, QWidget {{
        background: {bg};
        color: {text};
        font-family: "Segoe UI", Arial, sans-serif;
        font-size: 13px;
    }}
    QFrame {{ background: {bg}; border: none; }}

    /* ── Toolbar ── */
    QToolBar {{
        background: {bg2};
        border-bottom: 1px solid {border};
        spacing: 4px;
        padding: 2px 6px;
    }}
    QToolBar::separator {{
        background: {border};
        width: 1px;
        margin: 4px 3px;
    }}
    QToolBar QLineEdit {{
        background: {panel2};
        color: {text};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QToolBar QLineEdit:focus {{ border: 1px solid {acc}; }}

    /* ── Buttons ── */
    QPushButton {{
        background: {panel2};
        color: {text};
        border: 1px solid {border_lt};
        border-radius: 4px;
        padding: 4px 10px;
        font-size: 12px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        background: {hover};
        border: 1px solid {rgba(*a, 100)};
        color: {text};
    }}
    QPushButton:pressed {{ background: {selected}; }}
    QPushButton:checked {{
        background: {selected};
        color: {acc};
        border: 1px solid {rgba(*a, 100)};
    }}
    QPushButton:disabled {{
        color: {text_dim};
        border-color: {border};
        background: {panel};
    }}
    /* Player control buttons */
    QPushButton#player_ctrl {{
        background: {panel2};
        color: {text};
        border: 1px solid {border_lt};
        border-radius: 4px;
        padding: 3px 8px;
        font-size: 13px;
        min-height: 26px;
        min-width: 30px;
    }}
    QPushButton#player_ctrl:hover {{
        background: {hover};
        color: {acc};
        border-color: {rgba(*a, 80)};
    }}
    QPushButton#player_ctrl:checked {{
        background: {acc_dim};
        color: {acc};
        border: 1px solid {rgba(*a, 80)};
    }}

    /* ── Accent buttons ── */
    QPushButton#btn_accent {{
        background: {acc};
        color: {bg};
        border: none;
        border-radius: 4px;
        padding: 5px 14px;
        font-weight: bold;
    }}
    QPushButton#btn_accent:hover {{ background: {rgba(*a, 210)}; }}
    QPushButton#btn_accent_outline {{
        background: {acc_dim};
        color: {acc};
        border: 1px solid {rgba(*a, 80)};
        border-radius: 4px;
        padding: 5px 14px;
    }}
    QPushButton#btn_accent_outline:hover {{ background: {acc_med}; }}
    QPushButton#btn_done {{
        background: {acc};
        color: {bg};
        border: none;
        border-radius: 4px;
        padding: 6px 20px;
        font-weight: bold;
    }}
    QPushButton#btn_done:hover {{ background: {rgba(*a, 210)}; }}
    QPushButton#btn_flash_ok {{
        background: rgba(52,211,153,25);
        color: rgb(52,211,153);
        border: 1px solid rgba(52,211,153,80);
        border-radius: 4px;
        font-weight: bold;
    }}
    QPushButton#btn_active {{
        background: {selected};
        color: {acc};
        border: 1px solid {rgba(*a, 60)};
        border-radius: 4px;
        padding: 5px 12px;
    }}
    QPushButton#btn_edit {{
        background: {panel2};
        color: {text_med};
        border: 1px solid {border_lt};
        border-radius: 3px;
        padding: 2px 8px;
        font-size: 12px;
        min-height: 24px;
    }}
    QPushButton#btn_edit:hover {{
        background: {hover};
        color: {text};
        border-color: {rgba(*a, 80)};
    }}
    QPushButton#btn_edit:checked {{
        color: {acc};
        border-color: {acc};
        background: {acc_dim};
    }}

    /* ── Sidebar ── */
    #sidebar {{
        background: {panel};
        border-right: 1px solid {border};
        min-width: 200px;
        max-width: 245px;
    }}
    /* Category / tag / collection list buttons inside sidebar */
    #sidebar QPushButton {{
        background: transparent;
        border: none;
        border-left: 2px solid transparent;
        text-align: left;
        padding: 5px 10px;
        color: {text_med};
        font-size: 12px;
        border-radius: 0px;
        min-height: 24px;
    }}
    #sidebar QPushButton:hover {{
        background: {hover};
        color: {text};
        border-left: 2px solid {rgba(*a, 50)};
    }}
    #sidebar QPushButton:checked {{
        background: {acc_dim};
        color: {acc};
        font-weight: bold;
        border-left: 2px solid {acc};
    }}
    /* Import/New buttons in sidebar headers — must override the generic rule above */
    #sidebar QPushButton#btn_accent {{
        background: {acc};
        color: {bg};
        border: none;
        border-radius: 4px;
        padding: 2px 8px;
        font-weight: bold;
        text-align: center;
    }}
    #sidebar QPushButton#btn_accent:hover {{ background: {rgba(*a, 210)}; }}
    #sidebar QPushButton#btn_edit {{
        background: {panel2};
        color: {text_med};
        border: 1px solid {border_lt};
        border-radius: 3px;
        padding: 2px 6px;
        text-align: center;
        font-size: 11px;
        min-height: 20px;
    }}
    #sidebar QPushButton#btn_edit:hover {{
        background: {hover};
        color: {text};
        border-color: {rgba(*a, 80)};
    }}

    /* ── Detail panel ── */
    #detail_panel {{
        background: {panel};
        border-left: 1px solid {border};
        min-width: 300px;
    }}

    /* ── Status bar ── */
    QStatusBar {{
        background: {bg2};
        border-top: 1px solid {border_lt};
        color: {text_med};
        font-size: 11px;
        padding: 2px 4px;
        min-height: 22px;
    }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{
        color: {text_med};
        font-size: 11px;
        background: transparent;
        padding: 0 4px;
    }}

    /* ── Scrollbars ── */
    QScrollArea {{ background: {bg}; border: none; }}
    QScrollBar:vertical {{
        background: {bg}; width: 8px; border: none;
    }}
    QScrollBar::handle:vertical {{
        background: {border_lt}; border-radius: 4px; min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {acc_hi}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar:horizontal {{
        background: {bg}; height: 8px; border: none;
    }}
    QScrollBar::handle:horizontal {{
        background: {border_lt}; border-radius: 4px; min-width: 24px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {acc_hi}; }}

    /* ── Inputs ── */
    QLineEdit, QTextEdit, QComboBox {{
        background: {panel2};
        color: {text};
        border: 1px solid {border};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    QLineEdit:focus, QTextEdit:focus {{ border: 1px solid {acc}; }}
    QComboBox:focus {{ border: 1px solid {acc}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {panel2};
        color: {text};
        border: 1px solid {border};
        selection-background-color: {selected};
        selection-color: {acc};
        outline: none;
    }}

    /* ── Checkbox ── */
    QCheckBox {{ color: {text_med}; spacing: 6px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {border_lt};
        border-radius: 3px;
        background: {panel2};
    }}
    QCheckBox::indicator:checked {{
        background: {acc};
        border: 1px solid {acc};
        image: none;
    }}

    /* ── Tabs ── */
    QTabWidget::pane {{ border: 1px solid {border}; background: {bg}; }}
    QTabBar::tab {{
        background: {panel};
        color: {text_dim};
        padding: 6px 16px;
        border: 1px solid {border};
        border-bottom: none;
        border-radius: 3px 3px 0 0;
    }}
    QTabBar::tab:selected {{
        background: {bg};
        color: {text};
        border-bottom: 2px solid {acc};
    }}
    QTabBar::tab:hover {{ color: {text_med}; background: {hover}; }}

    /* ── Splitter ── */
    QSplitter::handle {{ background: {border}; width: 2px; }}
    QSplitter::handle:hover {{ background: {acc_hi}; }}

    /* ── Menu ── */
    QMenu {{
        background: {panel2};
        color: {text};
        border: 1px solid {border};
        padding: 4px;
        border-radius: 4px;
    }}
    QMenu::item {{ padding: 5px 20px 5px 10px; border-radius: 3px; }}
    QMenu::item:selected {{ background: {acc_dim}; color: {acc}; }}
    QMenu::separator {{ height: 1px; background: {border}; margin: 3px 0px; }}

    /* ── Table (list view) ── */
    QTableWidget {{
        background: {bg};
        color: {text};
        border: none;
        gridline-color: transparent;
        alternate-background-color: {panel};
        selection-background-color: {selected};
        selection-color: {text};
    }}
    QTableWidget::item {{
        background: transparent;
        color: {text};
        border: none;
        padding: 2px 6px;
    }}
    QTableWidget::item:selected {{
        background: {acc_dim};
        color: {text};
        border-left: 2px solid {acc};
    }}
    QHeaderView::section {{
        background: {panel2};
        color: {text_dim};
        border: none;
        border-bottom: 1px solid {border};
        padding: 5px 8px;
        font-size: 11px;
        letter-spacing: 1px;
    }}
    QHeaderView::section:hover {{ color: {acc}; }}

    /* ── Dialog ── */
    QDialog {{ background: {bg}; }}
    QGroupBox {{
        color: {text_dim};
        border: 1px solid {border};
        border-radius: 4px;
        margin-top: 8px;
        padding-top: 6px;
        font-size: 11px;
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}

    /* ── Slider ── */
    QSlider::groove:horizontal {{
        background: {panel2}; height: 4px; border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{ background: {acc_hi}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {acc};
        width: 14px; height: 14px;
        border-radius: 7px;
        margin: -5px 0;
    }}

    /* ── Progress dialog ── */
    QProgressBar {{
        background: {panel2};
        border: 1px solid {border};
        border-radius: 4px;
        text-align: center;
        color: {text};
        height: 8px;
    }}
    QProgressBar::chunk {{
        background: {acc};
        border-radius: 3px;
    }}

    /* ── Named labels ── */
    QLabel#app_name {{
        color: {acc};
        font-weight: bold;
        font-size: 14px;
        letter-spacing: 2px;
    }}
    QLabel#type_badge {{
        color: {acc};
        background: {acc_dim};
        border-radius: 3px;
        padding: 1px 5px;
        font-size: 11px;
        font-weight: bold;
    }}
    QLabel#section_label {{
        color: {text_med};
        font-size: 10px;
        font-weight: bold;
        letter-spacing: 1.5px;
        text-transform: uppercase;
        padding: 4px 2px 2px 2px;
        border-bottom: 1px solid {border_lt};
        margin-bottom: 2px;
    }}

    /* ── Search frame focus ring ── */
    QFrame#search_frame {{ border: 1px solid {border}; border-radius: 6px; background: {panel2}; }}
    QFrame#search_frame:focus-within {{ border: 1px solid {acc}; }}

    /* ── Card ── */
    QFrame[class="AssetCard"] {{
        background: {panel};
        border: 1px solid {border};
        border-radius: 4px;
    }}
    QFrame[class="AssetCard"]:hover {{ background: {hover}; border: 1px solid {border_lt}; }}

    /* ── Video player area ── */
    #video_container {{
        background: {t["panel"]};
        border: 1px solid {border};
        border-radius: 4px;
    }}

    /* Pagination buttons */
    QPushButton#page_btn {{
        background: transparent;
        color: {text_med};
        border: 1px solid {border};
        border-radius: 3px;
        padding: 0;
        font-size: 12px;
    }}
    QPushButton#page_btn:hover {{
        background: {hover};
        color: {text};
        border-color: {border_lt};
    }}
    QPushButton#page_btn_active {{
        background: {acc_dim};
        color: {acc};
        border: 1px solid {rgba(*a, 80)};
        border-radius: 3px;
        font-size: 12px;
        font-weight: bold;
    }}

    /* ── Custom title bar ── */
    #title_bar {{
        background: {bg2};
        border-bottom: 1px solid {border};
    }}
    #title_bar_label {{
        color: {text_dim};
        font-size: 11px;
        letter-spacing: 1px;
        background: transparent;
    }}
    /* Window control buttons */
    QPushButton#wm_min, QPushButton#wm_max, QPushButton#wm_close {{
        background: transparent;
        color: {text_dim};
        border: none;
        border-radius: 0;
        font-size: 13px;
        padding: 0;
    }}
    QPushButton#wm_min:hover {{
        background: {hover};
        color: {text};
    }}
    QPushButton#wm_max:hover {{
        background: {hover};
        color: {text};
    }}
    QPushButton#wm_close:hover {{
        background: rgb(196, 43, 28);
        color: rgb(255,255,255);
    }}
    QPushButton#wm_min:pressed, QPushButton#wm_max:pressed {{
        background: {selected};
    }}
    QPushButton#wm_close:pressed {{
        background: rgb(180, 30, 20);
    }}
    
    /* ── Custom title bar ── */
    #title_bar {{
        background: {bg2};
        border-bottom: 1px solid {border};
    }}
    #title_bar_label {{
        color: {text_dim};
        font-size: 11px;
        letter-spacing: 1px;
        background: transparent;
    }}
    /* Window control buttons */
    QPushButton#wm_min, QPushButton#wm_max, QPushButton#wm_close {{
        background: transparent;
        color: {text_dim};
        border: none;
        border-radius: 0;
        font-size: 13px;
        padding: 0;
    }}
    QPushButton#wm_min:hover {{
        background: {hover};
        color: {text};
    }}
    QPushButton#wm_max:hover {{
        background: {hover};
        color: {text};
    }}
    QPushButton#wm_close:hover {{
        background: rgb(196, 43, 28);
        color: rgb(255,255,255);
    }}
    QPushButton#wm_min:pressed, QPushButton#wm_max:pressed {{
        background: {selected};
    }}
    QPushButton#wm_close:pressed {{
        background: rgb(180, 30, 20);
    }}
        """
