import os
import sys
import re
import time
import json
import threading
import requests
from requests.adapters import HTTPAdapter
import tkinter as tk
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ─── Fix for PyInstaller Config Saving & Resources ───────────────────────────

if getattr(sys, 'frozen', False):
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APPLICATION_PATH, "ragalahari_gui_config.json")

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = APPLICATION_PATH
    return os.path.join(base_path, relative_path)

# ─── Configuration & Network Setup ───────────────────────────────────────────

BASE_URL = "https://www.ragalahari.com"
IMAGE_CDN_HOSTS = [
    "imgcdn.ragalahari.com",
    "starzone.ragalahari.com",
    "img.ragalahari.com",
    "szcdn1.ragalahari.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": BASE_URL,
}

session = requests.Session()
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=2)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.headers.update(HEADERS)

# ─── Core Scraper Logic ──────────────────────────────────────────────────────

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt < retries - 1: time.sleep(2)
            else: return None

def get_soup(url):
    resp = fetch(url)
    if resp: return BeautifulSoup(resp.text, 'html.parser')
    return None

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def extract_gallery_id(url):
    match = re.search(r'/(?:actress|actor|gallery|photos|starzone)/(\d+)/', url)
    return match.group(1) if match else ''

def get_galleries(actor_url):
    galleries = []
    soup = get_soup(actor_url)
    if not soup: return galleries
    gallery_patterns = ['/actress/', '/actor/', '/gallery/', '/photos/']
    
    galleries_panel = soup.find('div', id='galleries_panel')
    search_area = galleries_panel if galleries_panel else soup

    for link in search_area.find_all('a', href=True):
        href = link.get('href', '')
        if any(p in href for p in gallery_patterns) and href.endswith('.aspx'):
            name = link.get_text(strip=True)
            if not name:
                img = link.find('img')
                if img: name = img.get('alt', '') or img.get('title', '')
            if not name:
                name = href.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
            full_url = urljoin(BASE_URL, href)
            gal_id = extract_gallery_id(full_url)
            if full_url != actor_url and name:
                galleries.append({'name': name, 'url': full_url, 'id': gal_id})
    
    seen, unique = set(), []
    for g in galleries:
        if g['url'] not in seen:
            seen.add(g['url'])
            unique.append(g)
    return unique

def thumbnail_to_fullsize(thumb_url):
    return re.sub(r't(\.(jpg|jpeg|png|webp|gif))$', r'\1', thumb_url, flags=re.I)

def get_gallery_pages(gallery_url):
    soup = get_soup(gallery_url)
    if not soup: return [(gallery_url, None)]
    pages = [(gallery_url, soup)]
    page_links = set()
    paging_cell = soup.find('td', id='pagingCell')
    if paging_cell:
        for link in paging_cell.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True)
            full_url = urljoin(BASE_URL, href)
            if full_url != gallery_url and (text.isdigit() or 'next' in text.lower() or link.get('id') == 'linkNext'):
                page_links.add(full_url)
    else:
        for link in soup.find_all('a', class_='otherPage'):
            full_url = urljoin(BASE_URL, link['href'])
            if full_url != gallery_url: page_links.add(full_url)
        next_link = soup.find('a', id='linkNext')
        if next_link and next_link.get('href'):
            full_url = urljoin(BASE_URL, next_link['href'])
            if full_url != gallery_url: page_links.add(full_url)
    if not page_links:
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            if text.isdigit() and int(text) > 1:
                full_url = urljoin(BASE_URL, link['href'])
                if full_url != gallery_url: page_links.add(full_url)
    for url in sorted(page_links): pages.append((url, None))
    return pages

def get_images_from_page(soup):
    images = []
    if not soup: return images
    
    galdiv = soup.find('div', id='galdiv')
    if galdiv:
        thumb_imgs = galdiv.find_all('img', class_=re.compile(r'thumbnail|lazyload', re.I))
        if not thumb_imgs: thumb_imgs = galdiv.find_all('img', src=True)
    else:
        main_content = soup.find('div', class_='raga-movie') or soup
        thumb_imgs = main_content.find_all('img', class_=re.compile(r'thumbnail|lazyload', re.I))

    seen = set()
    for img in thumb_imgs:
        thumb_url = img.get('data-srcset', '') or img.get('srcset', '') or img.get('src', '')
        if not thumb_url or 'galpreload' in thumb_url or 'preload' in thumb_url:
            thumb_url = img.get('data-srcset', '')
            if not thumb_url: continue
        if 'ragalahari.com' not in thumb_url: continue
        fullsize_url = thumbnail_to_fullsize(thumb_url)
        if fullsize_url not in seen:
            seen.add(fullsize_url)
            images.append(fullsize_url)
    
    if not images:
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if not re.search(r'/image\d+\.aspx', href): continue
            img_tag = link.find('img')
            if img_tag:
                thumb_url = img_tag.get('data-srcset', '') or img_tag.get('src', '')
                if thumb_url and 'ragalahari.com' in thumb_url and 'galpreload' not in thumb_url:
                    fullsize_url = thumbnail_to_fullsize(thumb_url)
                    if fullsize_url not in seen:
                        seen.add(fullsize_url)
                        images.append(fullsize_url)
    return images

def generate_fallback_urls(url):
    parsed = urlparse(url)
    path = parsed.path
    query = "?" + parsed.query if parsed.query else ""
    urls = []
    if parsed.netloc: urls.append(f"https://{parsed.netloc}{path}{query}")
    for host in IMAGE_CDN_HOSTS:
        if host != parsed.netloc: urls.append(f"https://{host}{path}{query}")
    return urls

# ─── GUI Application (v2.0 — redesigned interface) ───────────────────────────

import subprocess
import platform
from datetime import datetime

APP_NAME = "Ragalahari Gallery Downloader"
APP_VERSION = "2.2.0"
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    try:  # Proper taskbar icon + sharp text on high-DPI screens
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("hansonds.RagalahariDownloader")
    except Exception:
        pass

try:  # System-tray support
    import pystray
    from PIL import Image as PILImage
    HAS_TRAY = True
except Exception:
    HAS_TRAY = False

FONT = "Segoe UI" if IS_WINDOWS else "Helvetica"
MONO = "Consolas" if IS_WINDOWS else "Courier"

# Two dark base themes — picked in Settings. Accent colour is switchable on top of either.
THEMES = {
    # Soft, low-glare slate with pastel accents (default — easy on the eyes)
    "Aurora": {
        "bg": "#1B1E27", "sidebar": "#20232E", "card": "#252935", "card_hi": "#2D3240",
        "border": "#363B4A", "input": "#1E212B", "text": "#D3D6E0", "muted": "#949AAE",
        "faint": "#646A7E", "ok": "#84C9A8", "warn": "#E3C07D", "err": "#E3929F",
        "info": "#8DB4DE", "dark_text": "#1B1E27", "on_accent": "#1B1E27",
        "log_text": "#BFC4D3", "err_hover": "#EBA6B1", "warn_hover": "#EBCB91", "exit_hover": "#3A2E35",
    },
    # Deep navy with vivid accents (the original v2 look)
    "Midnight": {
        "bg": "#0B0D17", "sidebar": "#10131F", "card": "#161A2B", "card_hi": "#1D2237",
        "border": "#262C45", "input": "#0E1120", "text": "#E7E9F5", "muted": "#8A90AD",
        "faint": "#4E5576", "ok": "#3DDC97", "warn": "#FFB547", "err": "#FF5C7A",
        "info": "#5AB8FF", "dark_text": "#0B0D17", "on_accent": "#FFFFFF",
        "log_text": "#C9CEE8", "err_hover": "#FF7A92", "warn_hover": "#FFC56E", "exit_hover": "#3A1A26",
    },
}
THEME_INFO = {
    "Aurora": "Soft & calm — lower contrast, pastel colours",
    "Midnight": "Bold & vivid — high contrast, bright colours",
}

ACCENT_SETS = {
    "Aurora": {
        "Violet":  ("#A496E8", "#B7ACF0"),
        "Ocean":   ("#7EA6E3", "#97B8EA"),
        "Emerald": ("#74C4A4", "#8FD1B6"),
        "Sunset":  ("#E8A27C", "#EEB596"),
        "Rose":    ("#E095B7", "#E8ABC7"),
        "Gold":    ("#D9BC6E", "#E2CA88"),
    },
    "Midnight": {
        "Violet":  ("#8B5CF6", "#A78BFA"),
        "Ocean":   ("#3B82F6", "#60A5FA"),
        "Emerald": ("#10B981", "#34D399"),
        "Sunset":  ("#F97316", "#FB923C"),
        "Rose":    ("#EC4899", "#F472B6"),
        "Gold":    ("#EAB308", "#FACC15"),
    },
}

BASE = dict(THEMES["Aurora"])
ACCENTS = dict(ACCENT_SETS["Aurora"])


def mix(c1, c2, t):
    """Blend colour c1 into c2 by t (0..1)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02X%02X%02X" % tuple(round(x * t + y * (1 - t)) for x, y in zip(a, b))


def detect_link_type(url):
    """Mirrors the routing used by process_url, for the live badge only."""
    if not url:
        return None
    if "ragalahari.com" not in url.lower():
        return "invalid"
    if '/stars/profile/' in url or '/star/' in url or re.search(r'/stars?/\d+/', url):
        return "profile"
    return "gallery"


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_time(sec):
    if sec is None or sec < 0 or sec > 360000:
        return "--:--"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def open_path(path):
    try:
        if IS_WINDOWS:
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


ctk.set_appearance_mode("Dark")


class StatCard(ctk.CTkFrame):
    def __init__(self, master, title, color, icon):
        super().__init__(master, fg_color=BASE["card"], corner_radius=14,
                         border_width=1, border_color=BASE["border"])
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(FONT, 14), text_color=color).pack(side="left")
        ctk.CTkLabel(top, text=title.upper(), font=ctk.CTkFont(FONT, 10, "bold"),
                     text_color=BASE["muted"]).pack(side="left", padx=(6, 0))
        self.value = ctk.CTkLabel(self, text="0", font=ctk.CTkFont(FONT, 24, "bold"),
                                  text_color=BASE["text"], anchor="w")
        self.value.pack(fill="x", padx=14, pady=(0, 10))

    def set(self, v):
        self.value.configure(text=str(v))


class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.load_config()
        self.theme = self.config.get("base_theme") if self.config.get("base_theme") in THEMES else "Aurora"
        BASE.clear()
        BASE.update(THEMES[self.theme])
        ACCENTS.clear()
        ACCENTS.update(ACCENT_SETS[self.theme])
        self.accent, self.accent_hi = ACCENTS.get(self.config["accent"], ACCENTS["Violet"])
        self.tint = mix(self.accent, BASE["card"], 0.16)  # soft accent glow for active items

        self.title(f"{APP_NAME}  ·  v{APP_VERSION}")
        self.geometry(self.config.get("geometry") or "1200x840")
        self.minsize(1040, 740)
        self.configure(fg_color=BASE["bg"])
        self.attributes("-topmost", bool(self.config.get("always_on_top")))

        try:
            self.iconbitmap(resource_path("logo.ico"))
        except Exception:
            try:
                self.app_icon = tk.PhotoImage(file=resource_path("logo.png"))
                self.iconphoto(True, self.app_icon)
            except Exception:
                pass

        self.is_downloading = False
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # set = running
        self.queue = []
        self.last_failed = []   # [(url, save_path)]
        self.last_save_dir = None
        self._bytes_lock = threading.Lock()
        self._bytes = 0
        self._job = {}
        self._toast = None

        self._build_ui()
        self.show_page("download")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.url_entry.bind("<Return>", lambda e: self.start_download_thread() if not self.is_downloading else None)
        self._restart = False
        self._quitting = False
        self._tray_hint_shown = False
        self.tray = None
        self.bind_all("<Control-q>", lambda e: self.request_exit())
        self._start_tray()
        self.after(10, self._theme_title_bar)
        self.after(500, self._tick_stats)
        if self.config.get("auto_paste"):
            self.after(400, self._auto_paste)

    # ── Config ───────────────────────────────────────────────────────────────
    def load_config(self):
        self.config = {
            "download_dir": os.path.join(os.path.expanduser("~"), "Downloads", "Ragalahari"),
            "threads": 3,
            "direct_dl": False,
            "accent": "Violet",
            "base_theme": "Aurora",
            "open_when_done": False,
            "sound_when_done": True,
            "auto_paste": True,
            "always_on_top": False,
            "close_to_tray": True,
            "history": [],
            "geometry": "",
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config.update(json.load(f))
            except Exception:
                pass

    def save_config(self, *_):
        try:
            self.config["download_dir"] = self.path_entry.get().strip()
            self.config["threads"] = int(self.threads_slider.get())
            self.config["direct_dl"] = self.direct_dl_var.get()
            self.config["open_when_done"] = self.open_done_var.get()
            self.config["sound_when_done"] = self.sound_var.get()
            self.config["auto_paste"] = self.auto_paste_var.get()
            self.config["always_on_top"] = self.top_var.get()
            self.config["close_to_tray"] = self.tray_var.get()
            self.config["history"] = self.config.get("history", [])[-200:]
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log(f"[ERROR] Could not save config: {e}")

    # ── Window close / tray / exit ───────────────────────────────────────────
    def on_close(self):
        """The window's X button: hide to tray (if enabled), otherwise ask to exit."""
        if self.tray is not None and self.tray_var.get():
            self.hide_to_tray()
        else:
            self.request_exit()

    def hide_to_tray(self):
        try:
            self.config["geometry"] = self.geometry()
        except Exception:
            pass
        self.save_config()
        self.withdraw()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            try:
                self.tray.notify("Still running in the system tray. Right-click the icon and choose Exit to quit.",
                                 APP_NAME)
            except Exception:
                pass

    # ── Themed Windows title bar ─────────────────────────────────────────────
    def _theme_title_bar(self):
        """Colours the Windows title bar (minimise / maximise / close) to match the app.
        Windows 11: custom caption, text and border colours. Windows 10: dark title bar."""
        if not IS_WINDOWS:
            return
        try:
            import ctypes
            from ctypes import wintypes
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute

            def colorref(hex_color):
                h = hex_color.lstrip("#")
                r_, g_, b_ = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                return wintypes.DWORD(r_ | (g_ << 8) | (b_ << 16))

            def setattr_(attr, value):
                return dwm(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value))

            # Dark mode title bar (20 on newer builds, 19 on early Windows 10)
            on = ctypes.c_int(1)
            if setattr_(20, on) != 0:
                setattr_(19, on)
            # Windows 11 colours: 34 = border, 35 = caption background, 36 = caption text
            setattr_(35, colorref(BASE["sidebar"]))
            setattr_(36, colorref(BASE["text"]))
            setattr_(34, colorref(self.accent))
            # Nudge Windows to repaint the frame straight away
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
        except Exception:
            pass

    def show_window(self):
        self.deiconify()
        self.after(10, self._theme_title_bar)
        self.state("normal")
        self.lift()
        self.attributes("-topmost", True)
        self.after(150, lambda: self.attributes("-topmost", bool(self.top_var.get())))
        self.focus_force()

    def request_exit(self):
        """Exit with confirmation (sidebar Exit button, tray menu, Ctrl+Q)."""
        if self._quitting:
            return
        if not self.winfo_viewable():
            self.show_window()
        msg = "Are you sure you want to exit Ragalahari Downloader?"
        if self.is_downloading:
            msg = "A download is still running and will be stopped.\n\n" + msg
        if not messagebox.askyesno("Exit", msg, icon="warning" if self.is_downloading else "question", parent=self):
            return
        self.quit_app()

    def quit_app(self):
        self._quitting = True
        self.stop_event.set()
        self.pause_event.set()
        try:
            if self.winfo_viewable():
                self.config["geometry"] = self.geometry()
        except Exception:
            pass
        self.save_config()
        self._stop_tray()
        self.destroy()

    def _tray_image(self):
        try:
            return PILImage.open(resource_path("logo.png")).convert("RGBA")
        except Exception:
            img = PILImage.new("RGBA", (64, 64), (0, 0, 0, 0))
            from PIL import ImageDraw
            ImageDraw.Draw(img).rounded_rectangle((4, 4, 60, 60), 14, fill=self.accent)
            return img

    def _start_tray(self):
        if not HAS_TRAY:
            return
        ui = lambda fn: (lambda icon=None, item=None: self.after(0, fn))
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show window", ui(self.show_window), default=True),
                pystray.MenuItem(lambda item: "Resume download" if not self.pause_event.is_set() else "Pause download",
                                 ui(self.toggle_pause), enabled=lambda item: self.is_downloading),
                pystray.MenuItem("Stop download", ui(self.stop_download), enabled=lambda item: self.is_downloading),
                pystray.MenuItem("Open download folder", ui(self.open_save_folder)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", ui(self.request_exit)),
            )
            image = self._tray_image()
        except Exception:
            return

        def run_tray():
            # Built and run off the UI thread so the window can never hang on the tray.
            try:
                icon = pystray.Icon("RagalahariDownloader", image, APP_NAME, menu)

                def ready(ic):
                    ic.visible = True
                    self.tray = ic
                icon.run(setup=ready)
            except Exception:
                self.tray = None

        threading.Thread(target=run_tray, daemon=True).start()

    def _stop_tray(self):
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None

    def _refresh_tray(self, title=None):
        if self.tray is None:
            return
        try:
            self.tray.title = (title or APP_NAME)[:120]
            self.tray.update_menu()
        except Exception:
            pass

    # ── Layout ───────────────────────────────────────────────────────────────
    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()

        self.pages_host = ctk.CTkFrame(self, fg_color="transparent")
        self.pages_host.grid(row=0, column=1, sticky="nsew", padx=(0, 0))
        self.pages_host.grid_columnconfigure(0, weight=1)
        self.pages_host.grid_rowconfigure(0, weight=1)

        self.pages = {
            "download": self._build_download_page(),
            "history": self._build_history_page(),
            "settings": self._build_settings_page(),
            "about": self._build_about_page(),
        }

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=BASE["sidebar"], corner_radius=0, width=230)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)
        self.sidebar = sb

        brand = ctk.CTkFrame(sb, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(26, 30))
        try:
            from PIL import Image
            img = Image.open(resource_path("logo.png"))
            self._logo = ctk.CTkImage(light_image=img, dark_image=img, size=(38, 38))
            ctk.CTkLabel(brand, image=self._logo, text="").pack(side="left")
        except Exception:
            ctk.CTkLabel(brand, text="◆", font=ctk.CTkFont(FONT, 30, "bold"),
                         text_color=self.accent).pack(side="left")
        tbox = ctk.CTkFrame(brand, fg_color="transparent")
        tbox.pack(side="left", padx=(10, 0))
        self.brand_title = ctk.CTkLabel(tbox, text="RAGALAHARI", font=ctk.CTkFont(FONT, 16, "bold"),
                                        text_color=BASE["text"], anchor="w")
        self.brand_title.pack(anchor="w")
        self.brand_sub = ctk.CTkLabel(tbox, text="Gallery Downloader", font=ctk.CTkFont(FONT, 11),
                                      text_color=self.accent, anchor="w")
        self.brand_sub.pack(anchor="w")

        ctk.CTkLabel(sb, text="MENU", font=ctk.CTkFont(FONT, 10, "bold"),
                     text_color=BASE["faint"]).pack(anchor="w", padx=24, pady=(0, 6))
        self.nav_buttons = {}
        for key, icon, label in (("download", "⬇", "Downloader"), ("history", "🕘", "History"),
                                 ("settings", "⚙", "Settings"), ("about", "ℹ", "About")):
            b = ctk.CTkButton(sb, text=f"  {icon}   {label}", anchor="w", height=42, corner_radius=10,
                              font=ctk.CTkFont(FONT, 13, "bold"), fg_color="transparent",
                              hover_color=BASE["card"], text_color=BASE["muted"],
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=14, pady=3)
            self.nav_buttons[key] = b

        spacer = ctk.CTkFrame(sb, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        ctk.CTkButton(sb, text="  ⏻   Exit", anchor="w", height=40, corner_radius=10,
                      font=ctk.CTkFont(FONT, 13, "bold"), fg_color="transparent",
                      hover_color=BASE["exit_hover"], text_color=BASE["err"],
                      command=self.request_exit).pack(fill="x", padx=14, pady=(0, 10))

        status = ctk.CTkFrame(sb, fg_color=BASE["card"], corner_radius=12)
        status.pack(fill="x", padx=14, pady=(0, 18))
        row = ctk.CTkFrame(status, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(10, 2))
        self.sb_dot = ctk.CTkLabel(row, text="●", text_color=BASE["ok"], font=ctk.CTkFont(FONT, 12))
        self.sb_dot.pack(side="left")
        self.sb_state = ctk.CTkLabel(row, text="Idle", font=ctk.CTkFont(FONT, 12, "bold"),
                                     text_color=BASE["text"])
        self.sb_state.pack(side="left", padx=6)
        self.sb_speed = ctk.CTkLabel(status, text="0.0 KB/s", font=ctk.CTkFont(FONT, 11),
                                     text_color=BASE["muted"], anchor="w")
        self.sb_speed.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkLabel(sb, text=f"v{APP_VERSION}", font=ctk.CTkFont(FONT, 10),
                     text_color=BASE["faint"]).pack(pady=(0, 12))

    def show_page(self, key):
        for k, p in self.pages.items():
            p.grid_forget()
        self.pages[key].grid(row=0, column=0, sticky="nsew", padx=26, pady=22)
        for k, b in self.nav_buttons.items():
            if k == key:
                b.configure(fg_color=self.tint, text_color=self.accent_hi)
            else:
                b.configure(fg_color="transparent", text_color=BASE["muted"])
        if key == "history":
            self._render_history()

    def _card(self, master, **kw):
        return ctk.CTkFrame(master, fg_color=BASE["card"], corner_radius=16,
                            border_width=1, border_color=BASE["border"], **kw)

    def _section_label(self, master, text):
        return ctk.CTkLabel(master, text=text, font=ctk.CTkFont(FONT, 11, "bold"),
                            text_color=BASE["muted"], anchor="w")

    def _btn(self, master, text, cmd, kind="ghost", width=90, height=40):
        styles = {
            "accent": (self.accent, self.accent_hi, BASE["on_accent"]),
            "ghost": (BASE["card_hi"], BASE["border"], BASE["text"]),
            "danger": (BASE["err"], BASE["err_hover"], BASE["on_accent"]),
            "warn": (BASE["warn"], BASE["warn_hover"], BASE["dark_text"]),
        }
        fg, hv, tc = styles[kind]
        return ctk.CTkButton(master, text=text, command=cmd, width=width, height=height,
                             corner_radius=10, fg_color=fg, hover_color=hv, text_color=tc,
                             font=ctk.CTkFont(FONT, 12, "bold"))

    # ── Download page ────────────────────────────────────────────────────────
    def _build_download_page(self):
        page = ctk.CTkFrame(self.pages_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=3, uniform="cols")
        page.grid_columnconfigure(1, weight=2, uniform="cols")
        page.grid_rowconfigure(3, weight=1)

        # Header
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(hdr, text="Downloader", font=ctk.CTkFont(FONT, 26, "bold"),
                     text_color=BASE["text"]).pack(side="left")
        self.header_status = ctk.CTkLabel(hdr, text="Paste a gallery or profile link to begin",
                                          font=ctk.CTkFont(FONT, 12), text_color=BASE["muted"])
        self.header_status.pack(side="left", padx=16, pady=(8, 0))

        # URL card
        url_card = self._card(page)
        url_card.grid(row=1, column=0, columnspan=2, sticky="ew")
        url_card.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(url_card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))
        self._section_label(top, "GALLERY OR ACTOR / ACTRESS PROFILE URL").pack(side="left")
        self.type_badge = ctk.CTkLabel(top, text="", font=ctk.CTkFont(FONT, 10, "bold"),
                                       corner_radius=8, height=22, padx=10)
        self.type_badge.pack(side="right")

        row = ctk.CTkFrame(url_card, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 16))
        self.url_entry = ctk.CTkEntry(row, placeholder_text="https://www.ragalahari.com/actress/...aspx",
                                      height=46, corner_radius=12, fg_color=BASE["input"],
                                      border_color=BASE["border"], text_color=BASE["text"],
                                      font=ctk.CTkFont(FONT, 13))
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.url_entry.bind("<KeyRelease>", lambda e: self._update_badge())
        self.paste_btn = self._btn(row, "📋 Paste", self.paste_url, "ghost", 92, 46)
        self.paste_btn.pack(side="left", padx=(0, 6))
        self.clear_btn = self._btn(row, "✕", self.clear_url, "ghost", 46, 46)
        self.clear_btn.pack(side="left", padx=(0, 6))
        self.queue_btn = self._btn(row, "＋ Queue", self.add_to_queue, "ghost", 96, 46)
        self.queue_btn.pack(side="left")

        # Options row
        opts = ctk.CTkFrame(url_card, fg_color=BASE["input"], corner_radius=12)
        opts.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        opts.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(opts, text="📁  Save to", font=ctk.CTkFont(FONT, 12, "bold"),
                     text_color=BASE["muted"]).grid(row=0, column=0, padx=(14, 10), pady=(12, 6), sticky="w")
        self.path_entry = ctk.CTkEntry(opts, height=36, corner_radius=10, fg_color=BASE["card"],
                                       border_color=BASE["border"], text_color=BASE["text"],
                                       font=ctk.CTkFont(FONT, 12))
        self.path_entry.insert(0, self.config["download_dir"])
        self.path_entry.grid(row=0, column=1, sticky="ew", pady=(12, 6))
        self.path_entry.bind("<FocusOut>", self.save_config)
        self.browse_btn = self._btn(opts, "Browse", self.browse_folder, "ghost", 80, 36)
        self.browse_btn.grid(row=0, column=2, padx=(8, 4), pady=(12, 6))
        self._btn(opts, "Open", self.open_save_folder, "ghost", 64, 36).grid(
            row=0, column=3, padx=(0, 14), pady=(12, 6))

        ctk.CTkLabel(opts, text="⚡  Threads", font=ctk.CTkFont(FONT, 12, "bold"),
                     text_color=BASE["muted"]).grid(row=1, column=0, padx=(14, 10), pady=(6, 12), sticky="w")
        sl = ctk.CTkFrame(opts, fg_color="transparent")
        sl.grid(row=1, column=1, sticky="ew", pady=(6, 12))
        self.threads_slider = ctk.CTkSlider(sl, from_=1, to=15, number_of_steps=14,
                                            button_color=self.accent, button_hover_color=self.accent_hi,
                                            progress_color=self.accent, fg_color=BASE["border"],
                                            command=self.on_thread_change)
        self.threads_slider.set(self.config["threads"])
        self.threads_slider.pack(side="left", fill="x", expand=True)
        self.threads_label = ctk.CTkLabel(sl, text=str(self.config["threads"]), width=36,
                                          font=ctk.CTkFont(FONT, 15, "bold"), text_color=self.accent_hi)
        self.threads_label.pack(side="left", padx=(10, 0))

        self.direct_dl_var = ctk.BooleanVar(value=self.config["direct_dl"])
        self.direct_dl_cb = ctk.CTkSwitch(opts, text="Direct to folder (skip subfolders)",
                                          variable=self.direct_dl_var, command=self.save_config,
                                          progress_color=self.accent, button_color=BASE["text"],
                                          text_color=BASE["text"], font=ctk.CTkFont(FONT, 12))
        self.direct_dl_cb.grid(row=1, column=2, columnspan=2, padx=(8, 14), pady=(6, 12), sticky="e")

        # Stats row
        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.grid(row=2, column=0, columnspan=2, sticky="ew", pady=14)
        for i in range(5):
            stats.grid_columnconfigure(i, weight=1, uniform="s")
        self.stat_gal = StatCard(stats, "Galleries", self.accent_hi, "▦")
        self.stat_total = StatCard(stats, "Images", BASE["info"], "🖼")
        self.stat_done = StatCard(stats, "Saved", BASE["ok"], "✔")
        self.stat_skip = StatCard(stats, "Skipped", BASE["warn"], "↷")
        self.stat_fail = StatCard(stats, "Failed", BASE["err"], "✖")
        for i, c in enumerate((self.stat_gal, self.stat_total, self.stat_done, self.stat_skip, self.stat_fail)):
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0 if i == 4 else 6))

        # Left: progress + log
        left = self._card(page)
        left.grid(row=3, column=0, sticky="nsew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(3, weight=1)

        ctrl = ctk.CTkFrame(left, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        self.start_btn = ctk.CTkButton(ctrl, text="▶  START DOWNLOAD", height=48, width=200,
                                       corner_radius=12, fg_color=self.accent, hover_color=self.accent_hi,
                                       text_color=BASE["on_accent"], font=ctk.CTkFont(FONT, 14, "bold"),
                                       command=self.start_download_thread)
        self.start_btn.pack(side="left")
        self.pause_btn = self._btn(ctrl, "❚❚  Pause", self.toggle_pause, "ghost", 100, 48)
        self.pause_btn.configure(state="disabled")
        self.pause_btn.pack(side="left", padx=8)
        self.stop_btn = self._btn(ctrl, "■  Stop", self.stop_download, "ghost", 90, 48)
        self.stop_btn.configure(state="disabled")
        self.stop_btn.pack(side="left")
        self.retry_btn = self._btn(ctrl, "↻  Retry", self.retry_failed, "warn", 104, 48)

        prog = ctk.CTkFrame(left, fg_color="transparent")
        prog.grid(row=1, column=0, sticky="ew", padx=18)
        info = ctk.CTkFrame(prog, fg_color="transparent")
        info.pack(fill="x")
        self.status_label = ctk.CTkLabel(info, text="Ready.", font=ctk.CTkFont(FONT, 12, "bold"),
                                         text_color=BASE["text"], anchor="w")
        self.status_label.pack(side="left")
        self.pct_label = ctk.CTkLabel(info, text="0%", font=ctk.CTkFont(FONT, 12, "bold"),
                                      text_color=self.accent_hi)
        self.pct_label.pack(side="right")
        self.overall_label = ctk.CTkLabel(info, text="", font=ctk.CTkFont(FONT, 11),
                                          text_color=BASE["muted"])
        self.overall_label.pack(side="right", padx=14)
        self.progress_bar = ctk.CTkProgressBar(prog, height=10, corner_radius=5,
                                               progress_color=self.accent, fg_color=BASE["input"])
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", pady=(6, 4))
        meta = ctk.CTkFrame(prog, fg_color="transparent")
        meta.pack(fill="x")
        self.speed_label = ctk.CTkLabel(meta, text="Speed  —", font=ctk.CTkFont(FONT, 11),
                                        text_color=BASE["muted"])
        self.speed_label.pack(side="left")
        self.eta_label = ctk.CTkLabel(meta, text="ETA  --:--", font=ctk.CTkFont(FONT, 11),
                                      text_color=BASE["muted"])
        self.eta_label.pack(side="right")
        self.elapsed_label = ctk.CTkLabel(meta, text="Elapsed  00:00", font=ctk.CTkFont(FONT, 11),
                                          text_color=BASE["muted"])
        self.elapsed_label.pack(side="right", padx=16)

        lhdr = ctk.CTkFrame(left, fg_color="transparent")
        lhdr.grid(row=2, column=0, sticky="ew", padx=18, pady=(8, 6))
        self._section_label(lhdr, "ACTIVITY LOG").pack(side="left")
        self._btn(lhdr, "Save", self.save_log, "ghost", 54, 26).pack(side="right")
        self._btn(lhdr, "Copy", self.copy_log, "ghost", 54, 26).pack(side="right", padx=6)
        self._btn(lhdr, "Clear", self.clear_log, "ghost", 54, 26).pack(side="right")

        self.log_box = ctk.CTkTextbox(left, state="disabled", font=ctk.CTkFont(MONO, 12),
                                      fg_color=BASE["input"], text_color=BASE["log_text"],
                                      corner_radius=12, border_width=0, wrap="word")
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))
        for tag, col in (("ok", BASE["ok"]), ("err", BASE["err"]), ("warn", BASE["warn"]),
                         ("info", BASE["info"]), ("time", BASE["faint"]), ("head", self.accent_hi)):
            self.log_box.tag_config(tag, foreground=col)

        # Right: queue
        right = self._card(page)
        right.grid(row=3, column=1, sticky="nsew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        qh = ctk.CTkFrame(right, fg_color="transparent")
        qh.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 8))
        self._section_label(qh, "DOWNLOAD QUEUE").pack(side="left")
        self.queue_count = ctk.CTkLabel(qh, text="0", font=ctk.CTkFont(FONT, 10, "bold"),
                                        fg_color=BASE["card_hi"], corner_radius=8, width=26, height=20,
                                        text_color=self.accent_hi)
        self.queue_count.pack(side="left", padx=8)
        self._btn(qh, "Clear", self.clear_queue, "ghost", 54, 26).pack(side="right")
        self.queue_frame = ctk.CTkScrollableFrame(right, fg_color=BASE["input"], corner_radius=12,
                                                  scrollbar_button_color=BASE["border"])
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 10))
        self.queue_hint = ctk.CTkLabel(right, text="Tip: add several links with ＋ Queue,\nthen press Start to run them one by one.",
                                       font=ctk.CTkFont(FONT, 11), text_color=BASE["faint"], justify="left")
        self.queue_hint.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 16))
        self._render_queue()

        self._update_badge()
        return page

    # ── History page ─────────────────────────────────────────────────────────
    def _build_history_page(self):
        page = ctk.CTkFrame(self.pages_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        hdr = ctk.CTkFrame(page, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        ctk.CTkLabel(hdr, text="History", font=ctk.CTkFont(FONT, 26, "bold"),
                     text_color=BASE["text"]).pack(side="left")
        self._btn(hdr, "Clear history", self.clear_history, "ghost", 120, 36).pack(side="right")
        self.history_frame = ctk.CTkScrollableFrame(page, fg_color=BASE["card"], corner_radius=16,
                                                    border_width=1, border_color=BASE["border"],
                                                    scrollbar_button_color=BASE["border"])
        self.history_frame.grid(row=1, column=0, sticky="nsew")
        self.history_frame.grid_columnconfigure(0, weight=1)
        return page

    def _render_history(self):
        for w in self.history_frame.winfo_children():
            w.destroy()
        hist = list(reversed(self.config.get("history", [])))
        if not hist:
            ctk.CTkLabel(self.history_frame, text="No downloads yet. Finished jobs will appear here.",
                         font=ctk.CTkFont(FONT, 13), text_color=BASE["muted"]).grid(pady=40)
            return
        for i, h in enumerate(hist):
            row = ctk.CTkFrame(self.history_frame, fg_color=BASE["card_hi"], corner_radius=12)
            row.grid(row=i, column=0, sticky="ew", padx=10, pady=5)
            row.grid_columnconfigure(0, weight=1)
            ok = h.get("status") == "Completed"
            ctk.CTkLabel(row, text=h.get("title", "Download"), font=ctk.CTkFont(FONT, 13, "bold"),
                         text_color=BASE["text"], anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            ctk.CTkLabel(row, text=h.get("url", ""), font=ctk.CTkFont(FONT, 11),
                         text_color=BASE["faint"], anchor="w").grid(row=1, column=0, sticky="w", padx=14)
            ctk.CTkLabel(row, text=f"{h.get('date', '')}   ·   {h.get('saved', 0)} saved   ·   "
                                   f"{h.get('skipped', 0)} skipped   ·   {h.get('failed', 0)} failed   ·   "
                                   f"{h.get('size', '')}",
                         font=ctk.CTkFont(FONT, 11), text_color=BASE["muted"], anchor="w").grid(
                row=2, column=0, sticky="w", padx=14, pady=(2, 10))
            ctk.CTkLabel(row, text=h.get("status", ""), font=ctk.CTkFont(FONT, 10, "bold"),
                         text_color=BASE["dark_text"], fg_color=BASE["ok"] if ok else BASE["warn"],
                         corner_radius=8, height=20, padx=8).grid(row=0, column=1, padx=6, pady=(10, 0))
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.grid(row=1, column=1, rowspan=2, padx=10)
            self._btn(btns, "Open", lambda p=h.get("folder"): p and open_path(p), "ghost", 60, 30).pack(side="left", padx=3)
            self._btn(btns, "Reuse", lambda u=h.get("url"): self._reuse(u), "ghost", 64, 30).pack(side="left", padx=3)

    def _reuse(self, url):
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url or "")
        self._update_badge()
        self.show_page("download")

    def clear_history(self):
        if messagebox.askyesno("Clear history", "Remove all history entries?"):
            self.config["history"] = []
            self.save_config()
            self._render_history()

    # ── Settings page ────────────────────────────────────────────────────────
    def _build_settings_page(self):
        page = ctk.CTkScrollableFrame(self.pages_host, fg_color="transparent",
                                      scrollbar_button_color=BASE["border"])
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text="Settings", font=ctk.CTkFont(FONT, 26, "bold"),
                     text_color=BASE["text"]).grid(row=0, column=0, sticky="w", pady=(0, 16))

        c1 = self._card(page)
        c1.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        self._section_label(c1, "APPEARANCE").pack(anchor="w", padx=20, pady=(16, 8))
        ctk.CTkLabel(c1, text="Theme", font=ctk.CTkFont(FONT, 13), text_color=BASE["text"]).pack(anchor="w", padx=20)
        tr = ctk.CTkFrame(c1, fg_color="transparent")
        tr.pack(fill="x", padx=20, pady=(8, 14))
        for name in THEMES:
            t = THEMES[name]
            sel = name == self.theme
            box = ctk.CTkFrame(tr, fg_color=t["bg"], corner_radius=14, border_width=2,
                               border_color=self.accent if sel else BASE["border"])
            box.pack(side="left", padx=(0, 12))
            sw_row = ctk.CTkFrame(box, fg_color="transparent")
            sw_row.pack(anchor="w", padx=14, pady=(12, 6))
            for col in (t["sidebar"], t["card_hi"], ACCENT_SETS[name][self.config["accent"]][0], t["ok"], t["text"]):
                ctk.CTkFrame(sw_row, fg_color=col, width=22, height=22, corner_radius=11).pack(side="left", padx=(0, 5))
            ctk.CTkLabel(box, text=("✓  " if sel else "") + name, font=ctk.CTkFont(FONT, 13, "bold"),
                         text_color=t["text"], anchor="w").pack(anchor="w", padx=14)
            ctk.CTkLabel(box, text=THEME_INFO[name], font=ctk.CTkFont(FONT, 11),
                         text_color=t["muted"], anchor="w").pack(anchor="w", padx=14, pady=(0, 10))
            ctk.CTkButton(box, text="In use" if sel else "Use this theme", height=30, corner_radius=8,
                          state="disabled" if sel else "normal",
                          fg_color=t["card_hi"], hover_color=t["border"], text_color=t["text"],
                          text_color_disabled=t["muted"], font=ctk.CTkFont(FONT, 12, "bold"),
                          command=lambda n=name: self.set_theme(n)).pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(c1, text="Accent colour", font=ctk.CTkFont(FONT, 13), text_color=BASE["text"]).pack(anchor="w", padx=20)
        sw = ctk.CTkFrame(c1, fg_color="transparent")
        sw.pack(anchor="w", padx=20, pady=(8, 6))
        for name, (col, hi) in ACCENTS.items():
            sel = name == self.config["accent"]
            ctk.CTkButton(sw, text="✓" if sel else "", width=40, height=40, corner_radius=20,
                          fg_color=col, hover_color=hi, text_color=BASE["on_accent"],
                          border_width=3 if sel else 0, border_color=BASE["text"],
                          font=ctk.CTkFont(FONT, 14, "bold"),
                          command=lambda n=name: self.set_accent(n)).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(c1, text="Changing the theme or accent refreshes the window (settings are kept).",
                     font=ctk.CTkFont(FONT, 11), text_color=BASE["faint"]).pack(anchor="w", padx=20, pady=(0, 16))

        c2 = self._card(page)
        c2.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        self._section_label(c2, "BEHAVIOUR").pack(anchor="w", padx=20, pady=(16, 6))
        self.open_done_var = ctk.BooleanVar(value=self.config["open_when_done"])
        self.sound_var = ctk.BooleanVar(value=self.config["sound_when_done"])
        self.auto_paste_var = ctk.BooleanVar(value=self.config["auto_paste"])
        self.top_var = ctk.BooleanVar(value=self.config["always_on_top"])
        self.tray_var = ctk.BooleanVar(value=self.config["close_to_tray"])
        for var, title, desc, cmd in (
            (self.open_done_var, "Open folder when finished", "Opens the save folder automatically after a job.", self.save_config),
            (self.sound_var, "Play sound when finished", "A short chime when downloads complete.", self.save_config),
            (self.auto_paste_var, "Auto-paste Ragalahari links", "Fills the URL box from your clipboard on start-up.", self.save_config),
            (self.tray_var, "Close to system tray", "The X button hides the app to the tray. Use Exit (sidebar or tray menu) to quit.", self.save_config),
            (self.top_var, "Keep window on top", "Stays above other windows.", self._apply_topmost),
        ):
            r = ctk.CTkFrame(c2, fg_color="transparent")
            r.pack(fill="x", padx=20, pady=6)
            tb = ctk.CTkFrame(r, fg_color="transparent")
            tb.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(tb, text=title, font=ctk.CTkFont(FONT, 13), text_color=BASE["text"], anchor="w").pack(anchor="w")
            ctk.CTkLabel(tb, text=desc, font=ctk.CTkFont(FONT, 11), text_color=BASE["muted"], anchor="w").pack(anchor="w")
            ctk.CTkSwitch(r, text="", variable=var, command=cmd, progress_color=self.accent,
                          button_color=BASE["text"], width=46).pack(side="right")
        ctk.CTkFrame(c2, fg_color="transparent", height=10).pack()

        c3 = self._card(page)
        c3.grid(row=3, column=0, sticky="ew", pady=(0, 14))
        self._section_label(c3, "STORAGE").pack(anchor="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(c3, text=f"Settings file:  {CONFIG_FILE}", font=ctk.CTkFont(FONT, 11),
                     text_color=BASE["muted"], anchor="w", wraplength=700, justify="left").pack(anchor="w", padx=20)
        ctk.CTkLabel(c3, text="Folder layout:  <Save to> / <Actor name> / <gallery number> /   "
                              "(or straight into <Save to> with Direct mode)",
                     font=ctk.CTkFont(FONT, 11), text_color=BASE["muted"], anchor="w").pack(anchor="w", padx=20, pady=(4, 16))
        return page

    def _apply_topmost(self):
        self.attributes("-topmost", self.top_var.get())
        self.save_config()

    def set_theme(self, name):
        self.set_accent(self.config["accent"], theme=name)

    def set_accent(self, name, theme=None):
        if self.is_downloading:
            return self.toast("Can't change theme while downloading", "warn")
        self.config["accent"] = name
        if theme:
            self.config["base_theme"] = theme
        self.save_config()
        try:
            self.config["geometry"] = self.geometry()
        except Exception:
            pass
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)
        self._restart = True
        self._stop_tray()
        self.destroy()

    # ── About page ───────────────────────────────────────────────────────────
    def _build_about_page(self):
        page = ctk.CTkFrame(self.pages_host, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(page, text="About", font=ctk.CTkFont(FONT, 26, "bold"),
                     text_color=BASE["text"]).grid(row=0, column=0, sticky="w", pady=(0, 16))
        c = self._card(page)
        c.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(c, text=APP_NAME, font=ctk.CTkFont(FONT, 20, "bold"),
                     text_color=self.accent_hi).pack(anchor="w", padx=22, pady=(20, 0))
        ctk.CTkLabel(c, text=f"Version {APP_VERSION}  ·  by hansonds", font=ctk.CTkFont(FONT, 12),
                     text_color=BASE["muted"]).pack(anchor="w", padx=22)
        feats = ("Broken-image recovery across multiple CDN hosts",
                 "Auto-detects gallery links and full actor/actress profiles",
                 "Multi-threaded downloads (up to 15 at once) with 4-part chunking",
                 "Skips files you already have, retries failed ones",
                 "Download queue, pause / resume, live speed and ETA",
                 "History of every job with one-click folder access")
        for f in feats:
            ctk.CTkLabel(c, text=f"✦  {f}", font=ctk.CTkFont(FONT, 13), text_color=BASE["text"],
                         anchor="w").pack(anchor="w", padx=22, pady=3)
        ctk.CTkLabel(c, text="For personal archiving only. Please respect Ragalahari.com's terms of service.",
                     font=ctk.CTkFont(FONT, 11), text_color=BASE["faint"]).pack(anchor="w", padx=22, pady=(14, 6))
        self._btn(c, "GitHub page", lambda: open_path("https://github.com/hansonds/Ragalahari_GUI"),
                  "accent", 130, 38).pack(anchor="w", padx=22, pady=(4, 22))
        return page

    # ── Small UI helpers ─────────────────────────────────────────────────────
    def _update_badge(self):
        t = detect_link_type(self.url_entry.get().strip())
        if t is None:
            self.type_badge.configure(text="", fg_color="transparent")
        elif t == "profile":
            self.type_badge.configure(text="👤  PROFILE · ALL GALLERIES", fg_color=self.accent, text_color=BASE["on_accent"])
        elif t == "gallery":
            self.type_badge.configure(text="🖼  SINGLE GALLERY", fg_color=BASE["info"], text_color=BASE["dark_text"])
        else:
            self.type_badge.configure(text="⚠  NOT A RAGALAHARI LINK", fg_color=BASE["err"], text_color=BASE["on_accent"])

    def toast(self, msg, kind="ok"):
        col = {"ok": BASE["ok"], "warn": BASE["warn"], "err": BASE["err"], "info": BASE["info"]}[kind]
        if self._toast is not None:
            try:
                self._toast.destroy()
            except Exception:
                pass
        t = ctk.CTkFrame(self, fg_color=BASE["card_hi"], corner_radius=12, border_width=1, border_color=col)
        ctk.CTkLabel(t, text="●", text_color=col, font=ctk.CTkFont(FONT, 12)).pack(side="left", padx=(14, 6), pady=12)
        ctk.CTkLabel(t, text=msg, text_color=BASE["text"], font=ctk.CTkFont(FONT, 12, "bold")).pack(side="left", padx=(0, 16))
        t.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        self._toast = t
        self.after(3200, lambda: t.destroy() if t.winfo_exists() else None)

    def paste_url(self):
        try:
            cb_data = self.clipboard_get()
            if cb_data:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, cb_data.strip())
        except tk.TclError:
            pass
        self._update_badge()

    def _auto_paste(self):
        try:
            cb = self.clipboard_get().strip()
            if "ragalahari.com" in cb and not self.url_entry.get().strip():
                self.url_entry.insert(0, cb)
                self._update_badge()
                self.toast("Link pasted from clipboard", "info")
        except Exception:
            pass

    def clear_url(self):
        self.url_entry.delete(0, "end")
        self._update_badge()

    def on_thread_change(self, value):
        self.threads_label.configure(text=str(int(value)))
        self.save_config()

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_entry.get())
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.save_config()

    def open_save_folder(self):
        p = self.last_save_dir if (self.last_save_dir and os.path.isdir(self.last_save_dir)) else self.path_entry.get().strip()
        if p:
            os.makedirs(p, exist_ok=True)
            open_path(p)

    # Queue
    def add_to_queue(self):
        url = self.url_entry.get().strip()
        if detect_link_type(url) not in ("profile", "gallery"):
            return self.toast("Enter a valid Ragalahari link first", "err")
        if url in self.queue:
            return self.toast("Already in the queue", "warn")
        self.queue.append(url)
        self.url_entry.delete(0, "end")
        self._update_badge()
        self._render_queue()
        self.toast("Added to queue", "ok")

    def clear_queue(self):
        if self.is_downloading:
            return self.toast("Queue is locked while downloading", "warn")
        self.queue.clear()
        self._render_queue()

    def _remove_from_queue(self, url):
        if self.is_downloading:
            return
        if url in self.queue:
            self.queue.remove(url)
        self._render_queue()

    def _render_queue(self, active=None):
        for w in self.queue_frame.winfo_children():
            w.destroy()
        self.queue_count.configure(text=str(len(self.queue)))
        if not self.queue:
            ctk.CTkLabel(self.queue_frame, text="Queue is empty", font=ctk.CTkFont(FONT, 12),
                         text_color=BASE["faint"]).pack(pady=30)
            return
        for i, u in enumerate(self.queue, 1):
            is_active = u == active
            r = ctk.CTkFrame(self.queue_frame, corner_radius=10,
                             fg_color=self.tint if is_active else BASE["card"],
                             border_width=1 if is_active else 0, border_color=self.accent)
            r.pack(fill="x", pady=3, padx=2)
            t = detect_link_type(u)
            ctk.CTkLabel(r, text="👤" if t == "profile" else "🖼", width=24).pack(side="left", padx=(8, 2), pady=8)
            name = u.rstrip('/').split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
            ctk.CTkLabel(r, text=f"{i}. {name[:34]}", font=ctk.CTkFont(FONT, 12, "bold" if is_active else "normal"),
                         text_color=self.accent_hi if is_active else BASE["text"], anchor="w").pack(
                side="left", fill="x", expand=True)
            ctk.CTkButton(r, text="✕", width=26, height=26, corner_radius=8, fg_color="transparent",
                          hover_color=BASE["border"], text_color=BASE["muted"],
                          command=lambda x=u: self._remove_from_queue(x)).pack(side="right", padx=6)

    # Log
    def log(self, message):
        self.after(0, self._log_ui, message)

    def _log_ui(self, message):
        m = message.strip("\n")
        tag = None
        if m.startswith("[ERROR]") or m.startswith("[-]"):
            tag = "err"
        elif m.startswith("[!]"):
            tag = "warn"
        elif m.startswith("[+]") or m.startswith("[✓]"):
            tag = "ok"
        elif m.startswith("[*] Processing") or m.startswith("[*] Analyzing"):
            tag = "head"
        elif m.startswith("[*]") or m.startswith("[↻]"):
            tag = "info"
        self.log_box.configure(state="normal")
        if message.startswith("\n"):
            self.log_box.insert("end", "\n")
        self.log_box.insert("end", datetime.now().strftime("%H:%M:%S  "), "time")
        self.log_box.insert("end", m + "\n", tag) if tag else self.log_box.insert("end", m + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_box.get("1.0", "end"))
        self.toast("Log copied", "info")

    def save_log(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", initialfile="ragalahari_log.txt",
                                         filetypes=[("Text", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_box.get("1.0", "end"))
            self.toast("Log saved", "ok")

    # Status & live stats
    def update_status(self, msg, progress=None):
        self.after(0, self._update_status_ui, msg, progress)

    def _update_status_ui(self, msg, progress):
        self.status_label.configure(text=msg)
        if progress is not None:
            self.progress_bar.set(progress)
            self.pct_label.configure(text=f"{int(progress * 100)}%")

    def _add_bytes(self, n):
        with self._bytes_lock:
            self._bytes += n

    def _tick_stats(self):
        j = self._job
        if self.is_downloading and j:
            now = time.time()
            with self._bytes_lock:
                b = self._bytes
            dt = max(now - j["last_t"], 1e-6)
            inst = (b - j["last_b"]) / dt
            j["speed"] = inst if j["speed"] == 0 else j["speed"] * 0.7 + inst * 0.3
            j["last_t"], j["last_b"] = now, b
            sp = fmt_bytes(j["speed"]) + "/s"
            self.speed_label.configure(text=f"Speed  {sp}   ·   {fmt_bytes(b)} total")
            self.sb_speed.configure(text=sp)
            elapsed = now - j["start"] - j["paused_total"] - ((now - j["paused_at"]) if j["paused_at"] else 0)
            self.elapsed_label.configure(text=f"Elapsed  {fmt_time(elapsed)}")
            done = j["done_in_gal"]
            tot = j["total_in_gal"]
            if done and tot and elapsed > 0 and j["gal_start"]:
                gel = now - j["gal_start"]
                rate = done / max(gel, 1e-6)
                self.eta_label.configure(text=f"ETA  {fmt_time((tot - done) / rate if rate else None)}")
            self.stat_gal.set(f"{j['gal_i']}/{j['gal_n']}" if j["gal_n"] else "0")
            self.stat_total.set(j["images"])
            self.stat_done.set(j["saved"])
            self.stat_skip.set(j["skipped"])
            self.stat_fail.set(j["failed"])
            qn = j.get("q_n", 1)
            self.overall_label.configure(
                text=f"Link {j.get('q_i', 1)} of {qn}   ·   gallery {j['gal_i']} of {j['gal_n'] or '?'}" if qn > 1
                else (f"Gallery {j['gal_i']} of {j['gal_n']}" if j["gal_n"] > 1 else ""))
        if self.tray is not None:
            if self.is_downloading:
                pct = self.pct_label.cget("text")
                state = "Paused" if not self.pause_event.is_set() else "Downloading"
                self._refresh_tray(f"Ragalahari — {state} {pct}")
            elif self.tray.title != APP_NAME:
                self._refresh_tray(APP_NAME)
        self.after(500, self._tick_stats)

    def _set_running_ui(self, running):
        if running:
            self.start_btn.configure(state="disabled", fg_color=BASE["card_hi"], text_color=BASE["muted"],
                                     text="⏳  DOWNLOADING…")
            self.stop_btn.configure(state="normal", fg_color=BASE["err"], hover_color=BASE["err_hover"], text_color=BASE["on_accent"])
            self.pause_btn.configure(state="normal", text="❚❚  Pause")
            self.retry_btn.pack_forget()
            self.sb_dot.configure(text_color=self.accent_hi)
            self.sb_state.configure(text="Downloading")
            self.header_status.configure(text="Working…")
        else:
            self.start_btn.configure(state="normal", fg_color=self.accent, text_color=BASE["on_accent"],
                                     text="▶  START DOWNLOAD")
            self.stop_btn.configure(state="disabled", fg_color=BASE["card_hi"], text_color=BASE["muted"])
            self.pause_btn.configure(state="disabled", text="❚❚  Pause")
            self.sb_dot.configure(text_color=BASE["ok"])
            self.sb_state.configure(text="Idle")
            self.sb_speed.configure(text="0.0 KB/s")
            if self.last_failed:
                self.retry_btn.configure(text=f"↻  Retry ({len(self.last_failed)})")
                self.retry_btn.pack(side="left", padx=8)

    # ── Controls ─────────────────────────────────────────────────────────────
    def toggle_pause(self):
        if not self.is_downloading:
            return
        j = self._job
        if self.pause_event.is_set():
            self.pause_event.clear()
            j["paused_at"] = time.time()
            self.pause_btn.configure(text="▶  Resume")
            self.sb_dot.configure(text_color=BASE["warn"])
            self.sb_state.configure(text="Paused")
            self.log("[!] Paused. Active transfers will finish their current file.")
        else:
            if j.get("paused_at"):
                j["paused_total"] += time.time() - j["paused_at"]
                j["paused_at"] = None
            self.pause_event.set()
            self.pause_btn.configure(text="❚❚  Pause")
            self.sb_dot.configure(text_color=self.accent_hi)
            self.sb_state.configure(text="Downloading")
            self.log("[*] Resumed.")

    def stop_download(self):
        if self.is_downloading:
            self.stop_event.set()
            self.pause_event.set()
            self.log("[!] Stopping requested... Waiting for threads.")
            self.stop_btn.configure(state="disabled")

    def _new_job(self):
        now = time.time()
        with self._bytes_lock:
            self._bytes = 0
        self._job = {"start": now, "last_t": now, "last_b": 0, "speed": 0, "paused_total": 0,
                     "paused_at": None, "gal_i": 0, "gal_n": 0, "images": 0, "saved": 0,
                     "skipped": 0, "failed": 0, "done_in_gal": 0, "total_in_gal": 0, "gal_start": None}
        for c in (self.stat_gal, self.stat_total, self.stat_done, self.stat_skip, self.stat_fail):
            c.set(0)

    def start_download_thread(self):
        self.save_config()
        url = self.url_entry.get().strip()
        save_dir = self.path_entry.get().strip()

        urls = list(self.queue)
        if url and url not in urls:
            urls.append(url)
        if not urls:
            return messagebox.showerror("Error", "Please enter a valid URL.")
        if not save_dir:
            return messagebox.showerror("Error", "Please enter a save location.")

        # Snapshot settings so worker threads never touch Tk widgets
        self.run_threads = int(self.threads_slider.get())
        self.run_direct = self.direct_dl_var.get()

        self.is_downloading = True
        self.stop_event.clear()
        self.pause_event.set()
        self.last_failed = []
        self.clear_log()
        self._new_job()
        self.log("System Initialized. Starting robust chunked process...")
        self._set_running_ui(True)
        self.progress_bar.set(0)
        self.pct_label.configure(text="0%")
        self.eta_label.configure(text="ETA  --:--")
        threading.Thread(target=self._run_all, args=(urls, save_dir), daemon=True).start()

    def _run_all(self, urls, save_dir):
        self._job["q_n"] = len(urls)
        for qi, u in enumerate(urls, 1):
            if self.stop_event.is_set():
                break
            self._job["q_i"] = qi
            self.after(0, self._render_queue, u)
            self._job.update({"gal_i": 0, "gal_n": 0})
            before = dict(saved=self._job["saved"], skipped=self._job["skipped"], failed=self._job["failed"])
            self.process_url(u, save_dir)
            self._record_history(u, save_dir, before)
            if u in self.queue and not self.stop_event.is_set():
                self.queue.remove(u)
        self.after(0, self._finish_all)

    def _record_history(self, url, save_dir, before):
        j = self._job
        title = url.rstrip('/').split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
        with self._bytes_lock:
            size = fmt_bytes(self._bytes)
        self.config.setdefault("history", []).append({
            "title": title, "url": url, "date": datetime.now().strftime("%d %b %Y, %I:%M %p"),
            "saved": j["saved"] - before["saved"], "skipped": j["skipped"] - before["skipped"],
            "failed": j["failed"] - before["failed"], "size": size,
            "folder": self.last_save_dir or save_dir,
            "status": "Cancelled" if self.stop_event.is_set() else "Completed",
        })

    def _finish_all(self):
        self.is_downloading = False
        self._render_queue()
        self._set_running_ui(False)
        self.save_config()
        j = self._job
        if j.get("gal_n"):
            self.stat_gal.set(f"{j['gal_i']}/{j['gal_n']}")
        self.stat_total.set(j.get("images", 0))
        self.stat_done.set(j.get("saved", 0))
        self.stat_skip.set(j.get("skipped", 0))
        self.stat_fail.set(j.get("failed", 0))
        if self.stop_event.is_set():
            self.header_status.configure(text="Cancelled")
            self.toast("Download cancelled", "warn")
        else:
            self.header_status.configure(text=f"Done · {j.get('saved', 0)} images saved")
            self.toast(f"Finished — {j.get('saved', 0)} saved, {j.get('failed', 0)} failed",
                       "ok" if not j.get("failed") else "warn")
            self.eta_label.configure(text="ETA  00:00")
            if self.tray is not None and not self.winfo_viewable():
                try:
                    self.tray.notify(f"Finished — {j.get('saved', 0)} saved, {j.get('failed', 0)} failed", APP_NAME)
                except Exception:
                    pass
            if self.sound_var.get():
                try:
                    if IS_WINDOWS:
                        import winsound
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    else:
                        self.bell()
                except Exception:
                    pass
            if self.open_done_var.get() and self.last_save_dir:
                open_path(self.last_save_dir)

    def retry_failed(self):
        if self.is_downloading or not self.last_failed:
            return
        items = list(self.last_failed)
        self.last_failed = []
        self.is_downloading = True
        self.stop_event.clear()
        self.pause_event.set()
        self._new_job()
        self._job.update({"images": len(items), "total_in_gal": len(items), "gal_start": time.time(),
                          "gal_n": 1, "gal_i": 1, "q_n": 1})
        self._set_running_ui(True)
        self.log(f"\n[↻] Retrying {len(items)} failed images...")
        threads = int(self.threads_slider.get())

        def run():
            done = 0
            with ThreadPoolExecutor(max_workers=threads) as ex:
                futs = {ex.submit(self.download_single_image, u, p): (u, p) for u, p in items}
                for f in as_completed(futs):
                    done += 1
                    u, p = futs[f]
                    if f.result():
                        self._job["saved"] += 1
                    else:
                        self._job["failed"] += 1
                        self.last_failed.append((u, p))
                    self._job["done_in_gal"] = done
                    self.update_status(f"Retrying... {done}/{len(items)}", done / len(items))
            if self.last_failed:
                self.log(f"[!] {len(self.last_failed)} images still failed.")
            else:
                self.log("[✓] All retried images downloaded.")
            self.after(0, self._finish_all)

        threading.Thread(target=run, daemon=True).start()

    # ── Core workflow (original behaviour preserved) ────────────────────────
    def process_url(self, url, base_save_dir):
        try:
            self.log(f"[*] Analyzing: {url}")
            if '/stars/profile/' in url or '/star/' in url or re.search(r'/stars?/\d+/', url):
                actor_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                galleries = get_galleries(url)
                if not galleries:
                    self.log("[-] No galleries found.")
                else:
                    self.log(f"[+] Found {len(galleries)} galleries. Reversing order...")
                    galleries.reverse()  # Start processing from the last gallery first
                    self._job["gal_n"] = len(galleries)
                    for i, gal in enumerate(galleries, 1):
                        if self.stop_event.is_set():
                            break
                        self._job["gal_i"] = i
                        self.log(f"\n[*] Processing Gallery {i}/{len(galleries)}: {gal['name']}")
                        self.process_gallery(gal['url'], gal['name'], actor_name, base_save_dir, gallery_index=i)
            else:
                gallery_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                self._job.update({"gal_n": 1, "gal_i": 1})
                self.process_gallery(url, gallery_name, "Direct", base_save_dir, gallery_index=1)
        except Exception as e:
            self.log(f"[ERROR] Critical failure: {str(e)}")
        finally:
            if self.stop_event.is_set():
                self.log("[!] Operation Cancelled.")
            else:
                self.log("\n[✓] Completed.")

    def process_gallery(self, url, gallery_name, actor_name, base_save_dir, gallery_index):
        self.log(f"[*] Scanning pages...")
        pages = get_gallery_pages(url)
        all_images, seen = [], set()

        for i, (page_url, page_soup) in enumerate(pages, 1):
            if self.stop_event.is_set():
                return
            if page_soup is None:
                page_soup = get_soup(page_url)
            if not page_soup:
                continue
            imgs = get_images_from_page(page_soup)
            new_imgs = [img for img in imgs if img not in seen]
            seen.update(new_imgs)
            all_images.extend(new_imgs)
            self.update_status(f"Scanning page {i}/{len(pages)}...")

        if not all_images:
            return self.log("[-] No images found.")
        self.execute_download(all_images, gallery_name, actor_name, base_save_dir, gallery_index)

    def execute_download(self, images, gallery_name, actor_name, base_dir, gallery_index):
        if self.run_direct:
            save_dir = base_dir
        else:
            actor_dir = sanitize_filename(actor_name)
            # Use the index as the folder name instead of the gallery title
            gallery_dir = str(gallery_index)
            save_dir = os.path.join(base_dir, actor_dir, gallery_dir)

        os.makedirs(save_dir, exist_ok=True)
        self.last_save_dir = save_dir if self.run_direct else os.path.dirname(save_dir)
        total, completed, skipped, failed = len(images), 0, 0, 0
        failed_urls = []
        self.log(f"[+] Starting robust download of {total} images into folder '{gallery_index}'...")
        threads = self.run_threads
        self._job["images"] += total
        self._job.update({"total_in_gal": total, "done_in_gal": 0, "gal_start": time.time()})

        def worker(idx, url):
            self.pause_event.wait()
            if self.stop_event.is_set():
                return ('cancelled', url, None)
            parsed = urlparse(url)
            raw_filename = unquote(os.path.basename(parsed.path))
            if not raw_filename or '.' not in raw_filename:
                raw_filename = f"image_{idx:04d}.jpg"
            filename = sanitize_filename(raw_filename)
            save_path = os.path.join(save_dir, filename)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
                return ('skipped', url, save_path)
            ok = self.download_single_image(url, save_path)
            return ('ok', url, save_path) if ok else ('failed', url, save_path)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(worker, i, url): url for i, url in enumerate(images, 1)}
            for future in as_completed(futures):
                if self.stop_event.is_set():
                    break
                status, url, path = future.result()
                completed += 1
                if status == 'skipped':
                    skipped += 1
                    self._job["skipped"] += 1
                elif status == 'failed':
                    failed += 1
                    failed_urls.append(url)
                    self.last_failed.append((url, path))
                    self._job["failed"] += 1
                elif status == 'ok':
                    self._job["saved"] += 1
                self._job["done_in_gal"] = completed
                self.update_status(f"Downloading... {completed}/{total} (Skipped: {skipped}, Failed: {failed})", completed / total)

        if failed_urls and not self.stop_event.is_set():
            self.log(f"\n[!] Failed to download {len(failed_urls)} images:")
            for furl in failed_urls:
                self.log(f"  - {furl}")

    def download_single_image(self, url, save_path):
        urls_to_try = generate_fallback_urls(url)
        for img_url in urls_to_try:
            if self.stop_event.is_set():
                return False
            try:
                headers = {"Referer": "https://www.ragalahari.com/"}

                # Step 1: Probe server
                head_resp = session.head(img_url, headers=headers, timeout=10, allow_redirects=True)
                if head_resp.status_code not in (200, 206):
                    head_resp = session.get(img_url, headers=headers, stream=True, timeout=10)
                    if head_resp.status_code != 200:
                        continue

                file_size = int(head_resp.headers.get('Content-Length', 0))
                supports_ranges = head_resp.headers.get('Accept-Ranges') == 'bytes'

                # Step 2: IDM Chunking (With Retries)
                if supports_ranges and file_size > 50000:
                    num_parts = 4
                    chunk_size = file_size // num_parts
                    with open(save_path, "wb") as f:
                        f.truncate(file_size)

                    def download_chunk(part_num, start_byte, end_byte):
                        chunk_headers = headers.copy()
                        chunk_headers['Range'] = f'bytes={start_byte}-{end_byte}'
                        for attempt in range(3):
                            if self.stop_event.is_set():
                                return False
                            try:
                                r = session.get(img_url, headers=chunk_headers, stream=True, timeout=(10, 45))
                                if r.status_code in (200, 206):
                                    with open(save_path, "r+b") as f:
                                        f.seek(start_byte)
                                        for data in r.iter_content(32768):  # 32KB buffer
                                            if self.stop_event.is_set():
                                                return False
                                            if data:
                                                f.write(data)
                                                self._add_bytes(len(data))
                                    return True
                            except Exception:
                                time.sleep(1)  # wait 1s and try chunk again
                                continue
                        return False

                    ranges = [(i, i * chunk_size, file_size - 1 if i == num_parts - 1 else (i * chunk_size) + chunk_size - 1) for i in range(num_parts)]

                    success = True
                    with ThreadPoolExecutor(max_workers=num_parts) as chunk_executor:
                        futures = [chunk_executor.submit(download_chunk, i, s, e) for i, s, e in ranges]
                        for future in as_completed(futures):
                            if not future.result():
                                success = False

                    if success and not self.stop_event.is_set():
                        return True
                    # If chunking failed, fall through to the standard download below

                # Step 3: Failsafe Standard Download
                resp = session.get(img_url, timeout=(15, 60), stream=True, headers=headers)
                if resp.status_code == 200 and "image" in resp.headers.get("Content-Type", "").lower():
                    size = 0
                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(32768):
                            if self.stop_event.is_set():
                                break
                            if chunk:
                                f.write(chunk)
                                size += len(chunk)
                                self._add_bytes(len(chunk))
                    if self.stop_event.is_set():
                        os.remove(save_path)
                        return False
                    if size >= 5000:
                        return True

                # Clean up bad files before trying next fallback URL
                if os.path.exists(save_path):
                    os.remove(save_path)

            except Exception:
                if os.path.exists(save_path):
                    os.remove(save_path)
                continue

        return False


if __name__ == "__main__":
    first = True
    while True:
        app = DownloaderApp()
        if not first:
            app.show_page("settings")
        app.mainloop()
        if not getattr(app, "_restart", False):
            break
        first = False
