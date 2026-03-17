div align="center">

# 🎬 Pixel Attic

### VFX Asset Manager

**Organize, browse, and manage your visual effects assets — fast, visual, offline.**

[![Python](https://img.shields.io/badge/Python-3.8+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![PySide2](https://img.shields.io/badge/PySide2-Qt5-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?style=flat-square)](/)
[![License](https://img.shields.io/badge/License-MIT-orange?style=flat-square)](/)

<br>

[Features](#-features) · [Install](#-install) · [Requirements](#-requirements) · [Formats](#-supported-formats)  · [Build](#-build) · [support](#-support)

<br>

</div>

---

## 🧐 What is Pixel Attic?
<img width="2559" height="1393" alt="image" src="https://github.com/user-attachments/assets/2cf35d90-2e8c-436d-9a72-13f72123531b" />


Pixel Attic is a desktop application for organizing, browsing, and managing VFX assets. Built for artists, studios, and post-production teams, it provides a fast, visual way to catalog videos, image sequences, EXR files, textures, and other media commonly used in VFX pipelines.

like dasElement but free and just starting

---

## ✨ Features

<table>
<tr><td width="50%" valign="top">

### 📁 Asset Management
- Import files & folders with auto-metadata extraction
- Categories — built-in VFX + custom user-defined
- Colored tag pills with batch tagging
- ★ Star / Favorite system with dedicated filter
- 5-star rating system with sort support
- Collections — manual grouping, import/export `.pixcol`
- Asset linking — connect related versions
- Duplicate detection via content hashing
- Per-asset text notes with auto-save

</td><td width="50%" valign="top">

### 🔍 Search & Filtering
- Pill-based search bar with colored tokens
- Advanced operators: `tag:` `fmt:` `cat:` `size:>` `dur:<` `res:` `codec:` `depth:` `date:`
- Exclude operators: `-tag:` `-fmt:`
- Saved searches — recall complex filters
- Sort by name, date, size, type, or rating

</td></tr>
<tr><td valign="top">

### 🖼️ Visual Browsing
- Grid view — cards with thumbnails & hover scrub
- List view — spreadsheet-style sortable table
- Virtual scrolling — smooth with large libraries
- Card sizes: S / M / L / XL with adaptive pills
- Auto thumbnail generation (PIL + ffmpeg)
- Custom poster frame for videos

</td><td valign="top">

### 🎬 Video Playback
- Embedded VLC player — plays any format
- Transport: play, pause, frame step, seek, loop, mute
- In-app fullscreen (reparent, no re-embed)
- Frame info HUD overlay
- Timecode / frame counter display
- Material Icons on all controls

</td></tr>
<tr><td valign="top">

### 🎨 Customization
- 8+ dark themes (Industrial, Midnight, Nordic, Monokai…)
- 16 accent colors applied across all UI elements
- Material Icons throughout
- Custom fonts and sizes
- Configurable external viewers (DJV, RV, etc.)

</td><td valign="top">


</td></tr>
</table>

### 💾 Storage

| Feature | SQLite (default) | JSON |
|---------|:---:|:---:|
| Crash-safe (WAL mode) | ✅ | — |
| Human-readable | — | ✅ |
| Indexed queries | ✅ | — |
| Auto-backup | ✅ | ✅ |
| One-click migration | ↔️ | ↔️ |

---

## 🚀 Install

```bash
# Required
pip install PySide2 Pillow python-vlc

# Run
python main.py
```

> **Note:** [VLC](https://www.videolan.org/) and [ffmpeg](https://ffmpeg.org/) must be installed on your system for video playback and proxy generation.

---

## 📋 Requirements

### Minimum

| | Requirement |
|---|---|
| **OS** | Windows 10/later |
| **Python** | 3.8+ |
| **RAM** | 4 GB |


### Dependencies

| Package | Version | Required | Purpose |
|---------|---------|:---:|---------|
| PySide2 | 5.15+ | ✅ | Qt GUI framework |
| Pillow | 8.0+ | ✅ | Image thumbnails |
| python-vlc | 3.0+ | 📌 | Video playback |
| VLC | 3.0+ | 📌 | Player backend |
| ffmpeg | 4.0+ | 📌 | Proxy / thumbnail / strip generation |
| PyInstaller | — | — | Compile to `.exe` |


---

## 🎞️ Supported Formats

<table>
<tr>
<td>

**Video**
`.mp4` `.mov` `.avi` `.mkv` `.wmv` `.flv` `.webm` `.m4v` `.mxf` `.r3d`

</td>
<td>

**Image**
`.png` `.jpg` `.jpeg` `.tga` `.bmp` `.tiff` `.tif` `.exr` `.dpx` `.hdr` `.pic` `.cin` `.sxr`

</td>
<td>

**Sequence**
Numbered frames auto-detected
`shot.0001.exr` → `shot.0240.exr`

</td>
</tr>
</table>

---


## 📦 Build

```bash
pip install pyinstaller
pyinstaller pixelattic.spec
```

Output: `dist/PixelAttic/PixelAttic.exe`

> Place `pixelattic.ico` in the project root before building.

---

## support

if you emjoy the project consider buying me a coffee :)

<div align="center">

[![GitHub]()](https://github.com/Gyscal/PixelAttic)
[![Gumroad](https://4471282674150.gumroad.com/coffee)
[![Ko-fi]()](https://ko-fi.com/guscal)

</div>

---

<div align="center">
<sub>Made with ❤️ by <strong> GHST </strong></sub>
</div>
