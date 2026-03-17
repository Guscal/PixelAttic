"""
main.py — Pixel Attic entry point.
Shows a splash screen while loading, sets taskbar icon.
"""
import sys
import os
import ctypes

# ── Windows: set AppUserModelID so taskbar shows our icon ─────────────────────
if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "GHSTSoftware.PixelAttic.1.0"
        )
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import install_crash_handler, log_info
install_crash_handler()

from PySide2.QtWidgets import QApplication, QSplashScreen
from PySide2.QtGui     import QPixmap, QPainter, QColor, QFont, QIcon, \
                              QLinearGradient, QRadialGradient, QBrush, QPen
from PySide2.QtCore    import Qt, QRect

from pathlib import Path
_HERE = Path(__file__).parent


def _make_splash_pixmap(w=560, h=320):
    """Star-chart splash. Reads accent color from settings.json if available."""
    import math as _math, random as _random, json as _json
    from pathlib import Path as _Path

    # ── Read accent color from saved settings (before UI is up) ──────────
    _ACCENT_COLORS = {
        "Orange": (249,115,22), "Amber":  (245,158,11), "Gold":   (251,191,36),
        "Red":    (248,113,113),"Rose":   (251,71,120),  "Blue":   (96,165,250),
        "Indigo": (129,140,248),"Violet": (167,139,250), "Teal":   (45,212,191),
        "Green":  (74,222,128), "Lime":   (163,230,53),  "Cyan":   (34,211,238),
    }
    ar, ag, ab = 249, 115, 22   # default orange
    try:
        _sf = _Path.home() / ".pixelattic" / "settings.json"
        if _sf.exists():
            _name = _json.loads(_sf.read_text()).get("accent_color", "Orange")
            ar, ag, ab = _ACCENT_COLORS.get(_name, (249,115,22))
    except Exception:
        pass

    pix = QPixmap(w, h)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    # ── Flat dark background ──────────────────────────────────────────────
    p.setBrush(QBrush(QColor(6, 7, 16)))
    p.setPen(QPen(QColor(35, 48, 72), 2))
    p.drawRoundedRect(1, 1, w-2, h-2, 14, 14)

    # ── Dot grid ──────────────────────────────────────────────────────────
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(170, 190, 225, 16)))
    for gx in range(28, w, 28):
        for gy in range(28, h, 28):
            p.drawEllipse(gx-1, gy-1, 2, 2)

    # ── Background stars ──────────────────────────────────────────────────
    rng = _random.Random(42)
    for _ in range(55):
        sx=rng.randint(14,w-14); sy=rng.randint(14,h-14)
        p.setBrush(QBrush(QColor(205,218,242,rng.randint(30,120))))
        p.drawEllipse(sx,sy,1,1)
    for _ in range(8):
        sx=rng.randint(20,w-20); sy=rng.randint(12,h-12)
        p.setBrush(QBrush(QColor(230,238,255,rng.randint(110,190))))
        p.drawEllipse(sx-1,sy-1,2,2)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _crosshair(cx2, cy2, arm, alpha):
        col = QColor(200, 215, 245, alpha)
        p.setPen(QPen(col, 1)); p.setBrush(Qt.NoBrush)
        p.drawLine(cx2-arm, cy2, cx2+arm, cy2)
        p.drawLine(cx2, cy2-arm, cx2, cy2+arm)
        if arm >= 3:
            r2 = max(1, arm//3)
            p.drawEllipse(cx2-r2, cy2-r2, r2*2, r2*2)

    def _ring(cx2, cy2, rr, alpha):
        p.setPen(QPen(QColor(170,190,230,alpha), 1)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(cx2-rr, cy2-rr, rr*2, rr*2)
        p.setPen(QPen(QColor(170,190,230,alpha+15), 1))
        for angle in [0, 90, 180, 270]:
            rad = _math.radians(angle)
            p.drawLine(int(cx2+rr*_math.cos(rad)),     int(cy2+rr*_math.sin(rad)),
                       int(cx2+(rr+5)*_math.cos(rad)),  int(cy2+(rr+5)*_math.sin(rad)))

    LC  = QColor(140,165,215,28)
    LC2 = QColor(140,165,215,22)

    # ── Constellation 1: Big Dipper — top-left ────────────────────────────
    c1=[(62,28),(94,22),(98,46),(66,50),(110,68),(128,88),(142,112)]
    for i,j in [(0,1),(1,2),(2,3),(3,0),(2,4),(4,5),(5,6)]:
        p.setPen(QPen(LC,1)); p.drawLine(c1[i][0],c1[i][1],c1[j][0],c1[j][1])
    for i,(x,y) in enumerate(c1):
        _crosshair(x,y,[5,4,4,4,3,3,4][i],[170,150,150,150,130,120,155][i])
    _ring(c1[0][0],c1[0][1],11,35); _ring(c1[6][0],c1[6][1],9,30)

    # ── Constellation 2: Cygnus Cross — top-right ─────────────────────────
    c2=[(452,18),(436,45),(452,45),(468,45),(452,75),(442,30)]
    for i,j in [(0,2),(2,4),(1,2),(2,3),(0,5),(5,1)]:
        p.setPen(QPen(LC,1)); p.drawLine(c2[i][0],c2[i][1],c2[j][0],c2[j][1])
    for i,(x,y) in enumerate(c2):
        _crosshair(x,y,[5,3,5,3,4,3][i],[175,130,175,130,155,120][i])
    _ring(c2[0][0],c2[0][1],13,38); _ring(c2[2][0],c2[2][1],8,28)

    # ── Constellation 3: Scorpius arc — bottom ────────────────────────────
    c3=[(130,268),(172,258),(210,262),(246,272),(282,265),(316,255),(344,268),(362,288)]
    for i,j in [(0,1),(1,2),(2,3),(3,4),(4,5),(5,6),(6,7)]:
        p.setPen(QPen(LC2,1)); p.drawLine(c3[i][0],c3[i][1],c3[j][0],c3[j][1])
    for i,(x,y) in enumerate(c3):
        _crosshair(x,y,[3,3,4,5,4,3,3,4][i],[120,125,135,170,135,120,120,140][i])
    _ring(c3[3][0],c3[3][1],12,40)

    # ── Badge (uses accent color) ──────────────────────────────────────────
    bs=82; bx=w//2-bs//2; by=h//2-bs//2-20; br=int(bs*0.22)
    p.setBrush(QBrush(QColor(13,13,26))); p.setPen(QPen(QColor(45,58,82),2))
    p.drawRoundedRect(bx,by,bs,bs,br,br)
    p.setPen(Qt.NoPen); p.setBrush(QBrush(QColor(180,200,230,80)))
    gs=max(6,bs//8)
    for gx in range(bx+gs,bx+bs,gs):
        for gy in range(by+gs,by+bs,gs):
            p.drawEllipse(gx-1,gy-1,2,2)
    pad=max(3,bs//11); ca=max(3,bs//10); cr=max(1,ca//5)
    p.setBrush(QBrush(QColor(ar,ag,ab,210))); p.setPen(Qt.NoPen)
    p.drawRoundedRect(bx+pad,by+pad,ca,ca,cr,cr)
    p.drawRoundedRect(bx+bs-pad-ca,by+bs-pad-ca,ca,ca,cr,cr)
    sa2=max(2,ca//2); sr2=max(1,sa2//4)
    p.setBrush(QBrush(QColor(ar,ag,ab,100)))
    p.drawRoundedRect(bx+bs-pad-sa2,by+pad,sa2,sa2,sr2,sr2)
    p.drawRoundedRect(bx+pad,by+bs-pad-sa2,sa2,sa2,sr2,sr2)
    p.setFont(QFont("Arial",int(bs*0.40),QFont.Bold))
    p.setPen(QPen(QColor(ar,ag,ab)))
    p.drawText(QRect(bx,by,bs,bs),Qt.AlignCenter,"PA")

    # ── Title (uses accent color) ─────────────────────────────────────────
    y_name=by+bs+16
    p.setFont(QFont("Arial",20,QFont.Bold))
    p.setPen(QPen(QColor(220,228,240)))
    p.drawText(QRect(0,y_name,w//2+2,28),Qt.AlignRight,"PIXEL ")
    p.setPen(QPen(QColor(ar,ag,ab)))
    p.drawText(QRect(w//2+2,y_name,w//2,28),Qt.AlignLeft,"ATTIC")
    p.setFont(QFont("Arial",8))
    p.setPen(QPen(QColor(65,80,105)))
    p.drawText(QRect(0,y_name+34,w,16),Qt.AlignCenter,"VFX ASSET MANAGER")

    # ── Progress bar track ────────────────────────────────────────────────
    p.setBrush(QBrush(QColor(20,20,36))); p.setPen(Qt.NoPen)
    p.drawRoundedRect(40,h-28,w-80,4,2,2)
    p.end()
    return pix
def _make_app_icon():
    """
    PA icon — flat dark rounded square, orange text, no gradients.
    Renders cleanly at every size from 16×16 to 256×256.
    """
    size = 256
    pix  = QPixmap(size, size)
    pix.fill(QColor(0, 0, 0, 0))   # transparent outside the rounded rect
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    s = size
    # Corner radius — same ratio as iOS / macOS app icons (~22%)
    r = int(s * 0.22)

    # ── Background: flat dark square, thin border ────────────────────────
    p.setBrush(QBrush(QColor(13, 13, 26)))
    p.setPen(QPen(QColor(45, 58, 82), max(2, s // 64)))
    p.drawRoundedRect(1, 1, s - 2, s - 2, r, r)

    # ── Pixel grid — visible orange dots ────────────────────────────────
    step = max(8, s // 10)
    dot_r = max(1, s // 128)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(249, 115, 22, 120)))
    for x in range(step, s - step + 1, step):
        for y in range(step, s - step + 1, step):
            p.drawEllipse(x - dot_r, y - dot_r, dot_r * 2, dot_r * 2)

    # ── Corner accent squares ────────────────────────────────────────────
    pad = max(6, s // 11)
    ca  = max(5, s // 10)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor(249, 115, 22, 210)))
    cr = max(2, ca // 5)
    p.drawRoundedRect(pad, pad, ca, ca, cr, cr)
    p.drawRoundedRect(s - pad - ca, s - pad - ca, ca, ca, cr, cr)
    p.setBrush(QBrush(QColor(249, 115, 22, 100)))
    sa = max(3, ca // 2)
    sr = max(1, sa // 4)
    p.drawRoundedRect(s - pad - sa, pad, sa, sa, sr, sr)
    p.drawRoundedRect(pad, s - pad - sa, sa, sa, sr, sr)

    # ── PA text — flat orange, no gradient ──────────────────────────────
    font = QFont("Arial", int(s * 0.41), QFont.Bold)
    p.setFont(font)
    from PySide2.QtGui import QFontMetrics
    fm = QFontMetrics(font)
    tw = fm.horizontalAdvance("PA")
    th = fm.height()
    tx = (s - tw) // 2
    ty = (s - th) // 2 + fm.ascent()
    p.setPen(QPen(QColor(249, 115, 22), 1))   # flat orange — sharp at all sizes
    p.drawText(tx, ty, "PA")
    p.end()
    return QIcon(pix)


def main():
    app = QApplication(sys.argv)
    icon = _make_app_icon()
    app.setWindowIcon(icon)

    splash_pix = _make_splash_pixmap()
    splash = QSplashScreen(splash_pix, Qt.WindowStaysOnTopHint)
    splash.setWindowFlag(Qt.FramelessWindowHint, True)
    splash.show()
    app.processEvents()

    def _upd(msg, pct=0):
        pix = QPixmap(splash_pix)
        pp  = QPainter(pix)
        w, h = pix.width(), pix.height()
        bar_y = h - 28
        bar_w = w - 80
        if pct > 0:
            fill_w = int(bar_w * min(pct, 100) / 100)
            g = QLinearGradient(40, 0, 40 + bar_w, 0)
            g.setColorAt(0, QColor(249, 115, 22))
            g.setColorAt(1, QColor(251, 191, 36))
            pp.setBrush(QBrush(g))
            pp.setPen(Qt.NoPen)
            pp.drawRoundedRect(40, bar_y, fill_w, 4, 2, 2)
        pp.setFont(QFont("Arial", 8))
        pp.setPen(QPen(QColor(100, 116, 139)))
        pp.drawText(QRect(0, bar_y - 16, w, 14), Qt.AlignCenter, msg)
        pp.end()
        splash.setPixmap(pix)
        app.processEvents()

    _upd("Loading configuration…", 15)
    from config import APP_NAME, VERSION    

    _upd("Initializing database…", 35)
    from app import PixelAtticApp

    _upd("Applying settings…", 65)
    from settings import Settings
    settings = Settings.load()

    _upd("Building interface…", 85)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(VERSION)

    _upd("Ready.", 100)
    window = PixelAtticApp()
    window.setWindowIcon(icon)
    window.show()
    splash.finish(window)

    log_info("=== Pixel Attic started ===")
    sys.exit(app.exec_())


if __name__ == "__main__":
    log_info("=== Pixel Attic starting ===")
    main()
