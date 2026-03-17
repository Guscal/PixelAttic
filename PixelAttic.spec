# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Pixel Attic.
Build:  pyinstaller pixelattic.spec
"""

block_cipher = None

# Every .py source file must be included as data so runtime imports work
_py_sources = [
    ('app.py', '.'),
    ('panels.py', '.'),
    ('widgets.py', '.'),
    ('search_bar.py', '.'),
    ('database.py', '.'),
    ('config.py', '.'),
    ('settings.py', '.'),
    ('dialogs.py', '.'),
    ('thumbnails.py', '.'),
    ('preview.py', '.'),
    ('logger.py', '.'),
    ('styles.py', '.'),
    ('sqlite_db.py', '.'),
    ('icons.py', '.'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('icons', 'icons'),         # Material Icons folder
        ('pixelattic.ico', '.'),    # App icon
    ] + _py_sources,
    hiddenimports=[
        'PySide2.QtMultimedia',
        'PySide2.QtMultimediaWidgets',
        'sqlite3',
        'json',
        'hashlib',
        'shutil',
        'subprocess',
        'config',
        'settings',
        'database',
        'sqlite_db',
        'styles',
        'logger',
        'icons',
        'thumbnails',
        'preview',
        'panels',
        'widgets',
        'search_bar',
        'dialogs',
        'app',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PixelAttic',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='pixelattic.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PixelAttic',
)
