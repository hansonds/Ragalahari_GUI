<div align="center">
  <h1>📸 Ragalahari Gallery Downloader</h1>
  <p>
    <img src="https://img.shields.io/badge/python-3.8%2B-blue.svg" alt="Python Version">
    <img src="https://img.shields.io/badge/UI-CustomTkinter-emerald.svg" alt="CustomTkinter">
    <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
    <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Platform">
  </p>
  <p><i>A professional, multi-threaded Windows GUI application designed to batch-download high-resolution image galleries from Ragalahari.com effortlessly.</i></p>
</div>

---

## 📑 Table of Contents
- [🚀 Features](#-features)
- [💻 Prerequisites](#-prerequisites)
- [🛠️ Installation](#️-installation)
- [📖 Usage Guide](#-usage-guide)
- [📦 Building the Executable (.exe)](#-building-the-executable-exe)
- [⚙️ Configuration](#️-configuration)
- [🤝 Contributing](#-contributing)
- [⚠️ Disclaimer](#️-disclaimer)

---

## 🚀 Features

* **Intelligent Scraping**: Paste a specific gallery URL or an entire Actor/Actress profile URL. The app automatically detects the link type and fetches all associated HD images.
* **Smart CDN Resilience**: Built-in failover logic. It pings multiple image CDN servers to find the active host, ensuring downloads succeed even if standard links are geo-blocked or dead.
* **Blazing Fast**: Multi-threaded architecture allows downloading up to 15 images simultaneously.
* **Custom Routing**: Choose between organized subfolders (`Actor Name/Gallery Name/`) or a direct "dump" of images straight into a specific folder.
* **Persistent Settings**: Automatically remembers your exact download path, thread count, and folder preferences across sessions via a local JSON config.
* **Enterprise-Grade UI**: A clean, professional dark-mode interface built with `CustomTkinter`, designed to reduce eye strain.
* **Live Terminal Log**: Real-time integrated console to monitor download progress, server handshakes, and system status without a messy command prompt window.

---

## 💻 Prerequisites

To run the Python script from source, you will need:
* **Python 3.8** or higher installed on your system.
* **pip** (Python package installer).

---

## 🛠️ Installation

**1. Clone the repository:**
git clone https://github.com/yourusername/ragalahari-downloader.git
cd ragalahari-downloader

**2. Install required dependencies:**
pip install requests beautifulsoup4 customtkinter

**3. Run the application:**
python ragalahari_gui.py

---

## 📖 Usage Guide

1. **Launch the App**: Open the compiled `.exe` or run the `.py` script.
2. **Paste URL**: Insert a Ragalahari gallery URL (e.g., a specific photoshoot) or a star profile URL into the top text box.
3. **Select Location**: Click **Browse** to choose the destination folder where images will be saved.
4. **Adjust Speed**: Use the **Threads** slider (1-15) depending on your internet connection speed (5 is recommended for a balance of speed and stability).
5. **Set Folder Rules**: Check the **Download directly to folder** box if you want images placed exactly in the chosen folder without the app creating `Actor Name/Gallery Name/` subdirectories.
6. **Start**: Click **Start Download**. You can monitor the live progress bar and the terminal log at the bottom of the window.

---

## 📦 Building the Executable (.exe)

Want to share this tool with someone who doesn't have Python installed, or just want a portable app? You can compile it into a single, standalone Windows `.exe`.

**1. Install PyInstaller:**
pip install pyinstaller

**2. Compile the App:**
Run the exact command below in your project folder. The `--collect-all` flag is critical to ensure the `CustomTkinter` UI themes load properly.

pyinstaller --noconsole --onefile --collect-all customtkinter --add-data "logo.png;." --add-data "logo.ico;." --icon=logo.ico ragalahari_gui.py

**3. Locate your Exe:**
Once finished, your standalone program will be located in the newly created `dist/` folder. You can safely delete the `build/` folder and `.spec` file that are generated during the process.

---

## ⚙️ Configuration

The application operates dynamically by updating a `ragalahari_gui_config.json` file to remember your settings between sessions.

* **When running as a Python script (`.py`)**: The config file saves in the project root folder.
* **When running as a compiled executable (`.exe`)**: The config file safely saves in the exact same directory where the `.exe` file is placed.

It stores the following state seamlessly:

{
    "download_dir": "C:\\Users\\YourName\\Downloads\\Ragalahari",
    "threads": 5,
    "direct_dl": false
}

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