<div align="center">
  <h1>📸 Ragalahari Gallery Downloader</h1>
  <p>
    <img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/UI-CustomTkinter-emerald.svg" alt="CustomTkinter">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
    <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Platform">
    <img src="https://github.com/hansonds/Ragalahari_GUI/actions/workflows/build-release.yml/badge.svg" alt="Build">
    <img src="https://img.shields.io/github/v/release/hansonds/Ragalahari_GUI" alt="Release">
  </p>
  <p><i>A professional, multi-threaded Windows GUI application designed to batch-download high-resolution image galleries from Ragalahari.com effortlessly.</i></p>

**[⬇️ Download Portable EXE](https://github.com/hansonds/Ragalahari_GUI/releases/latest/download/Ragalahari_Downloader.exe)**

  <img src="Screenshot 2026-07-14 102524.png" alt="Ragalahari Downloader Main UI" width="700">
</div>

---

**[⬇️ Download Portable EXE](https://github.com/hansonds/Ragalahari_GUI/releases/latest/download/Ragalahari_Downloader.exe)**

## 📑 Table of Contents
- [🚀 Features](#-features)
- [🦸‍♂️ Feature Spotlight: Broken Image Recovery](#️-feature-spotlight-broken-image-recovery)
- [💻 Prerequisites](#-prerequisites)
- [🛠️ Installation](#️-installation)
- [📖 Usage Guide](#-usage-guide)
- [📦 Building the Executable (.exe)](#-building-the-executable-exe)
- [⚙️ Configuration](#️-configuration)
- [🤝 Contributing](#-contributing)
- [⚠️ Disclaimer](#️-disclaimer)

---

**[⬇️ Download Portable EXE](https://github.com/hansonds/Ragalahari_GUI/releases/latest/download/Ragalahari_Downloader.exe)**

## ✨ What's new in v2.0

* **Brand-new dashboard UI** — sidebar navigation (Downloader · History · Settings · About), card layout, live stat tiles for galleries, images, saved, skipped and failed.
* **Live speed, ETA and elapsed time** while downloading.
* **Pause / Resume** a running job, plus Stop.
* **Download queue** — add several gallery or profile links and run them back-to-back.
* **One-click Retry** for any images that failed.
* **Smart link badge** — instantly tells you if a link is a single gallery, a full profile, or not a Ragalahari link.
* **Colour-coded, timestamped activity log** with Copy / Save / Clear.
* **History page** — every finished job with counts, size, *Open folder* and *Reuse link*.
* **Settings** — 6 accent themes, open folder when done, finish sound, auto-paste links from clipboard, always-on-top.
* **Automatic builds** — every update is built into a portable `.exe` by GitHub Actions and published in [Releases](https://github.com/hansonds/Ragalahari_GUI/releases).

> The scraping, CDN recovery, chunked downloading, skip-existing logic and folder layout (`Actor/1, 2, 3…`) are unchanged from v1.

---

## 🚀 Features

* **Broken Image Recovery & CDN Resilience**: Even if the images are completely missing or display as broken icons on the website itself, the app's intelligent failover logic pings multiple backend CDN servers to find, recover, and download the original HD images.
* **Intelligent Scraping**: Paste a specific gallery URL or an entire Actor/Actress profile URL. The app automatically detects the link type and fetches all associated HD images.
* **Blazing Fast**: Multi-threaded architecture allows downloading up to 15 images simultaneously.
* **Custom Routing**: Choose between organized subfolders (`Actor Name/Gallery Name/`) or a direct "dump" of images straight into a specific folder.
* **Persistent Settings**: Automatically remembers your exact download path, thread count, and folder preferences across sessions via a local JSON config.
* **Enterprise-Grade UI**: A clean, professional dark-mode interface built with `CustomTkinter`, designed to reduce eye strain.
* **Live Terminal Log**: Real-time integrated console to monitor download progress, server handshakes, and system status without a messy command prompt window.

---

## 🦸‍♂️ Feature Spotlight: Broken Image Recovery

Older galleries on the website often suffer from dead links or geo-blocking, resulting in a page full of broken image icons. Our tool bypasses the frontend entirely to retrieve the missing files.

**The Problem: Broken Website View**  
*The website fails to load the images.*
<br>
<img src="Screenshot 2026-07-14 102815.png" alt="Broken Website Images" width="700">

**The Solution: App Recovery**  
*The app successfully locates the active backend hosts and downloads the full gallery anyway.*
<br>
<img src="Screenshot 2026-07-14 102910.png" alt="Successful App Download" width="700">

---

**[⬇️ Download Portable EXE](https://github.com/hansonds/Ragalahari_GUI/releases/latest/download/Ragalahari_Downloader.exe)**



## 📦 Building the Executable (.exe)

You don't need to build it yourself — GitHub does it automatically. Every time `ragalahari_gui.py` changes on `main`, the **Build portable EXE & publish release** workflow runs and uploads `Ragalahari_Downloader.exe` to a release named after `APP_VERSION` in the script. Bump `APP_VERSION` to publish a new version; you can also start a build manually from the **Actions** tab → *Run workflow*.

To build locally on Windows:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller ragalahari_gui.py --name Ragalahari_Downloader --onefile --windowed --icon logo.ico --add-data "logo.ico;." --add-data "logo.png;." --collect-data customtkinter
```

---

## 🤝 Contributing

Contributions, issues, and feature requests are welcome!

1. Fork the Project
2. Create your Feature Branch
3. Commit your Changes
4. Push to the Branch
5. Open a Pull Request

---

## ⚠️ Disclaimer

> This tool is created for educational and personal archiving purposes only. Please respect the Terms of Service of [Ragalahari.com](https://www.ragalahari.com) and do not use this script to overload their servers. The developer assumes no liability for the misuse of this software or copyright infringement.

---
### ⚖️ License

Distributed under the MIT License. See `LICENSE` for more information.
