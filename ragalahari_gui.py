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
        base_path = os.path.abspath(".")
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

# FIX 1: Massively increase the connection pool so IDM-style chunks don't block each other
session = requests.Session()
adapter = HTTPAdapter(pool_connections=100, pool_maxsize=100, max_retries=2)
session.mount('http://', adapter)
session.mount('https://', adapter)
session.headers.update(HEADERS)

# ─── Colorful & Eye-Friendly UI Palette (Catppuccin Mocha Inspired) ──────────

UI = {
    "bg": "#1E1E2E", "frame": "#313244", "accent": "#CBA6F7", 
    "accent_hover": "#F5C2E7", "text": "#CDD6F4", "text_dim": "#89B4FA", 
    "btn_start": "#A6E3A1", "btn_start_hover": "#94E2D5", "btn_stop": "#F38BA8", 
    "btn_stop_hover": "#EBA0AC", "btn_browse": "#89DCEB", "btn_browse_hover": "#74C7D6",
    "input_bg": "#11111B", "input_border": "#585B70", "log_bg": "#181825", 
    "log_text": "#F9E2AF", "button_text": "#11111B"
}

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

# ─── GUI Application ─────────────────────────────────────────────────────────

ctk.set_appearance_mode("Dark")

class DownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ragalahari Gallery Downloader")
        self.geometry("780x720")
        self.minsize(750, 680)
        self.configure(fg_color=UI["bg"]) 
        
        try:
            ico_path = resource_path("logo.ico")
            self.iconbitmap(ico_path)
        except Exception:
            try:
                png_path = resource_path("logo.png")
                self.app_icon = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self.app_icon)
            except Exception: pass
            
        self.is_downloading = False
        self.stop_event = threading.Event()
        
        self.load_config()
        self._build_ui()

    def load_config(self):
        self.config = {
            "download_dir": os.path.join(os.path.expanduser("~"), "Downloads", "Ragalahari"),
            "threads": 3,
            "direct_dl": False
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    self.config.update(json.load(f))
            except Exception: pass

    def save_config(self):
        try:
            self.config["download_dir"] = self.path_entry.get().strip()
            self.config["threads"] = int(self.threads_slider.get())
            self.config["direct_dl"] = self.direct_dl_var.get()
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log(f"[ERROR] Could not save config: {e}")

    def _build_ui(self):
        self.header_label = ctk.CTkLabel(
            self, text="RAGALAHARI GALLERY DOWNLOADER", 
            font=ctk.CTkFont(size=24, weight="bold", family="Segoe UI Black"), text_color=UI["accent"]
        )
        self.header_label.pack(pady=(25, 15))

        self.url_frame = ctk.CTkFrame(self, fg_color=UI["frame"], corner_radius=12)
        self.url_frame.pack(fill="x", padx=35, pady=10)
        
        ctk.CTkLabel(self.url_frame, text="Actor/Actress gallery or Profile URL:", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 0))
        
        self.url_input_container = ctk.CTkFrame(self.url_frame, fg_color="transparent")
        self.url_input_container.pack(fill="x", padx=15, pady=(5, 15))
        
        self.url_entry = ctk.CTkEntry(
            self.url_input_container, placeholder_text="https://www.ragalahari.com/... .aspx", 
            height=42, fg_color=UI["input_bg"], border_color=UI["input_border"], text_color=UI["text"]
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.paste_btn = ctk.CTkButton(
            self.url_input_container, text="Paste", font=ctk.CTkFont(weight="bold"),
            width=65, height=42, fg_color=UI["btn_browse"], hover_color=UI["btn_browse_hover"],
            text_color=UI["button_text"], command=self.paste_url
        )
        self.paste_btn.pack(side="left", padx=(0, 5))
        
        self.clear_btn = ctk.CTkButton(
            self.url_input_container, text="Clear", font=ctk.CTkFont(weight="bold"),
            width=65, height=42, fg_color=UI["btn_stop"], hover_color=UI["btn_stop_hover"],
            text_color=UI["button_text"], command=self.clear_url
        )
        self.clear_btn.pack(side="left")

        self.settings_frame = ctk.CTkFrame(self, fg_color=UI["frame"], corner_radius=12)
        self.settings_frame.pack(fill="x", padx=35, pady=10)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.settings_frame, text="Save Location:", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.path_entry = ctk.CTkEntry(self.settings_frame, height=38, fg_color=UI["input_bg"], border_color=UI["input_border"], text_color=UI["text"])
        self.path_entry.insert(0, self.config["download_dir"])
        self.path_entry.grid(row=0, column=1, padx=(0, 10), pady=(15, 5), sticky="ew")
        
        self.browse_btn = ctk.CTkButton(
            self.settings_frame, text="Browse", font=ctk.CTkFont(weight="bold"),
            width=80, height=38, fg_color=UI["btn_browse"], hover_color=UI["btn_browse_hover"],
            text_color=UI["button_text"], command=self.browse_folder
        )
        self.browse_btn.grid(row=0, column=2, padx=(0, 15), pady=(15, 5))

        ctk.CTkLabel(self.settings_frame, text="Threads (Speed):", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=15, pady=(10, 5), sticky="w")
        
        self.slider_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.slider_frame.grid(row=1, column=1, columnspan=2, padx=(0, 15), pady=(10, 5), sticky="ew")
        
        self.threads_slider = ctk.CTkSlider(
            self.slider_frame, from_=1, to=15, number_of_steps=14, 
            button_color=UI["accent"], button_hover_color=UI["accent_hover"],
            progress_color=UI["accent"], command=self.on_thread_change
        )
        self.threads_slider.set(self.config["threads"])
        self.threads_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.threads_label = ctk.CTkLabel(self.slider_frame, text=str(self.config["threads"]), font=ctk.CTkFont(weight="bold", size=15), text_color=UI["accent"])
        self.threads_label.pack(side="right", padx=(5, 0))

        self.direct_dl_var = ctk.BooleanVar(value=self.config["direct_dl"])
        self.direct_dl_cb = ctk.CTkCheckBox(
            self.settings_frame, text="Download directly to folder (Skip subfolders)", 
            variable=self.direct_dl_var, text_color=UI["text"], fg_color=UI["accent"],
            hover_color=UI["accent_hover"], border_color=UI["input_border"], command=self.save_config
        )
        self.direct_dl_cb.grid(row=2, column=0, columnspan=3, padx=15, pady=(10, 15), sticky="w")

        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        self.start_btn = ctk.CTkButton(
            self.btn_frame, text="▶ START DOWNLOAD", font=ctk.CTkFont(weight="bold", size=14), 
            height=45, width=200, corner_radius=8, fg_color=UI["btn_start"],
            hover_color=UI["btn_start_hover"], text_color=UI["button_text"], command=self.start_download_thread
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ctk.CTkButton(
            self.btn_frame, text="■ STOP / CANCEL", font=ctk.CTkFont(weight="bold", size=14), 
            height=45, width=200, corner_radius=8, fg_color=UI["frame"], hover_color=UI["btn_stop_hover"], 
            text_color=UI["text_dim"], state="disabled", command=self.stop_download
        )
        self.stop_btn.pack(side="left", padx=10)

        self.progress_bar = ctk.CTkProgressBar(self, height=12, corner_radius=6, progress_color=UI["accent"], fg_color=UI["frame"])
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=35, pady=(5, 5))
        
        self.status_label = ctk.CTkLabel(self, text="Ready.", text_color=UI["text_dim"], font=ctk.CTkFont(size=13))
        self.status_label.pack(pady=(0, 10))

        self.log_box = ctk.CTkTextbox(
            self, state="disabled", font=ctk.CTkFont(family="Consolas", size=13),
            fg_color=UI["log_bg"], text_color=UI["log_text"], border_color=UI["frame"],
            border_width=2, corner_radius=10
        )
        self.log_box.pack(fill="both", expand=True, padx=35, pady=(0, 25))

    def paste_url(self):
        try:
            cb_data = self.clipboard_get()
            if cb_data:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, cb_data.strip())
        except tk.TclError: pass

    def clear_url(self): self.url_entry.delete(0, "end")

    def on_thread_change(self, value):
        self.threads_label.configure(text=str(int(value)))
        self.save_config()

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_entry.get())
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.save_config()

    def log(self, message): self.after(0, self._log_ui, message)
    def _log_ui(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", "> " + message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def update_status(self, msg, progress=None):
        self.after(0, self._update_status_ui, msg, progress)
    def _update_status_ui(self, msg, progress):
        self.status_label.configure(text=msg)
        if progress is not None: self.progress_bar.set(progress)

    def stop_download(self):
        if self.is_downloading:
            self.stop_event.set()
            self.log("[!] Stopping requested... Waiting for threads.")
            self.stop_btn.configure(state="disabled")

    def start_download_thread(self):
        self.save_config()
        url = self.url_entry.get().strip()
        save_dir = self.path_entry.get().strip()
        
        if not url: return messagebox.showerror("Error", "Please enter a valid URL.")
        if not save_dir: return messagebox.showerror("Error", "Please enter a save location.")

        self.is_downloading = True
        self.stop_event.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.log("System Initialized. Starting robust chunked process...")
        
        self.start_btn.configure(state="disabled", fg_color=UI["frame"], text_color=UI["text_dim"])
        self.stop_btn.configure(state="normal", fg_color=UI["btn_stop"], text_color=UI["button_text"])
        self.progress_bar.set(0)
        
        threading.Thread(target=self.process_url, args=(url, save_dir), daemon=True).start()

    def process_url(self, url, base_save_dir):
        try:
            self.log(f"[*] Analyzing: {url}")
            if '/stars/profile/' in url or '/star/' in url or re.search(r'/stars?/\d+/', url):
                actor_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                galleries = get_galleries(url)
                if not galleries: self.log("[-] No galleries found.")
                else:
                    self.log(f"[+] Found {len(galleries)} galleries.")
                    for i, gal in enumerate(galleries, 1):
                        if self.stop_event.is_set(): break
                        self.log(f"\n[*] Processing Gallery {i}/{len(galleries)}: {gal['name']}")
                        self.process_gallery(gal['url'], gal['name'], actor_name, base_save_dir)
            else:
                gallery_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                self.process_gallery(url, gallery_name, "Direct", base_save_dir)
        except Exception as e:
            self.log(f"[ERROR] Critical failure: {str(e)}")
        finally:
            self.is_downloading = False
            self.after(0, lambda: self.start_btn.configure(state="normal", fg_color=UI["btn_start"], text_color=UI["button_text"]))
            self.after(0, lambda: self.stop_btn.configure(state="disabled", fg_color=UI["frame"], text_color=UI["text_dim"]))
            if self.stop_event.is_set(): self.log("[!] Operation Cancelled.")
            else: self.log("\n[✓] Completed.")

    def process_gallery(self, url, gallery_name, actor_name, base_save_dir):
        self.log(f"[*] Scanning pages...")
        pages = get_gallery_pages(url)
        all_images, seen = [], set()
        
        for i, (page_url, page_soup) in enumerate(pages, 1):
            if self.stop_event.is_set(): return
            if page_soup is None: page_soup = get_soup(page_url)
            if not page_soup: continue
            imgs = get_images_from_page(page_soup)
            new_imgs = [img for img in imgs if img not in seen]
            seen.update(new_imgs)
            all_images.extend(new_imgs)
            self.update_status(f"Scanning page {i}/{len(pages)}...")

        if not all_images: return self.log("[-] No images found.")
        self.execute_download(all_images, gallery_name, actor_name, base_save_dir)

    def execute_download(self, images, gallery_name, actor_name, base_dir):
        if self.direct_dl_var.get(): save_dir = base_dir
        else:
            actor_dir = sanitize_filename(actor_name)
            gallery_dir = sanitize_filename(gallery_name)
            save_dir = os.path.join(base_dir, actor_dir, gallery_dir)
            
        os.makedirs(save_dir, exist_ok=True)
        total, completed, skipped, failed = len(images), 0, 0, 0
        failed_urls = []
        self.log(f"[+] Starting robust download of {total} images...")
        threads = int(self.threads_slider.get())
        
        def worker(idx, url):
            if self.stop_event.is_set(): return ('cancelled', url)
            parsed = urlparse(url)
            raw_filename = unquote(os.path.basename(parsed.path))
            if not raw_filename or '.' not in raw_filename:
                raw_filename = f"image_{idx:04d}.jpg"
            filename = sanitize_filename(raw_filename)
            save_path = os.path.join(save_dir, filename)
            if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
                return ('skipped', url)
            ok = self.download_single_image(url, save_path)
            return ('ok', url) if ok else ('failed', url)

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(worker, i, url): url for i, url in enumerate(images, 1)}
            for future in as_completed(futures):
                if self.stop_event.is_set(): break
                status, url = future.result()
                completed += 1
                if status == 'skipped': skipped += 1
                elif status == 'failed': 
                    failed += 1
                    failed_urls.append(url)
                self.update_status(f"Downloading... {completed}/{total} (Skipped: {skipped}, Failed: {failed})", completed/total)

        if failed_urls and not self.stop_event.is_set():
            self.log(f"\n[!] Failed to download {len(failed_urls)} images:")
            for furl in failed_urls: self.log(f"  - {furl}")

    def download_single_image(self, url, save_path):
        urls_to_try = generate_fallback_urls(url)
        for img_url in urls_to_try:
            if self.stop_event.is_set(): return False
            try:
                headers = {"Referer": "https://www.ragalahari.com/"}
                
                # Step 1: Probe server
                head_resp = session.head(img_url, headers=headers, timeout=10, allow_redirects=True)
                if head_resp.status_code not in (200, 206):
                    head_resp = session.get(img_url, headers=headers, stream=True, timeout=10)
                    if head_resp.status_code != 200: continue

                file_size = int(head_resp.headers.get('Content-Length', 0))
                supports_ranges = head_resp.headers.get('Accept-Ranges') == 'bytes'
                
                # Step 2: IDM Chunking (With Retries)
                if supports_ranges and file_size > 50000:
                    num_parts = 4
                    chunk_size = file_size // num_parts
                    with open(save_path, "wb") as f: f.truncate(file_size)
                        
                    def download_chunk(part_num, start_byte, end_byte):
                        chunk_headers = headers.copy()
                        chunk_headers['Range'] = f'bytes={start_byte}-{end_byte}'
                        
                        # FIX 2: Retry loop just for this chunk (IDM style)
                        for attempt in range(3):
                            if self.stop_event.is_set(): return False
                            try:
                                r = session.get(img_url, headers=chunk_headers, stream=True, timeout=(10, 45))
                                if r.status_code in (200, 206):
                                    with open(save_path, "r+b") as f:
                                        f.seek(start_byte)
                                        for data in r.iter_content(32768): # 32KB buffer
                                            if self.stop_event.is_set(): return False
                                            if data: f.write(data)
                                    return True
                            except Exception:
                                time.sleep(1) # wait 1s and try chunk again
                                continue
                        return False

                    ranges = [(i, i * chunk_size, file_size - 1 if i == num_parts - 1 else (i * chunk_size) + chunk_size - 1) for i in range(num_parts)]
                    
                    success = True
                    with ThreadPoolExecutor(max_workers=num_parts) as chunk_executor:
                        futures = [chunk_executor.submit(download_chunk, i, s, e) for i, s, e in ranges]
                        for future in as_completed(futures):
                            if not future.result(): success = False
                                
                    if success and not self.stop_event.is_set(): return True
                    # If chunking failed entirely, DO NOT CONTINUE to next URL immediately.
                    # We will drop down to Step 3 below and try a standard download first!
                
                # Step 3: Failsafe Standard Download
                # Runs if chunking is not supported, OR if chunking failed above
                resp = session.get(img_url, timeout=(15, 60), stream=True, headers=headers)
                if resp.status_code == 200 and "image" in resp.headers.get("Content-Type", "").lower():
                    size = 0
                    with open(save_path, "wb") as f:
                        for chunk in resp.iter_content(32768):
                            if self.stop_event.is_set(): break
                            if chunk:
                                f.write(chunk)
                                size += len(chunk)
                    if self.stop_event.is_set():
                        os.remove(save_path)
                        return False
                    if size >= 5000: return True
                
                # Clean up bad files before trying next fallback URL
                if os.path.exists(save_path): os.remove(save_path)

            except Exception:
                if os.path.exists(save_path): os.remove(save_path)
                continue
                
        return False

if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()
