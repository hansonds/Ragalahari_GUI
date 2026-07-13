import os
import sys
import re
import time
import json
import threading
import requests
import tkinter as tk
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import customtkinter as ctk
from tkinter import filedialog, messagebox

# ─── Fix for PyInstaller Config Saving & Resources ───────────────────────────

if getattr(sys, 'frozen', False):
    # If running as a PyInstaller .exe, save next to the .exe
    APPLICATION_PATH = os.path.dirname(sys.executable)
else:
    # If running as a Python script, save next to the script
    APPLICATION_PATH = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(APPLICATION_PATH, "ragalahari_gui_config.json")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
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

session = requests.Session()
session.headers.update(HEADERS)

# ─── Professional UI Color Palette ───────────────────────────────────────────

UI = {
    "bg": "#202124",             
    "frame": "#292A2D",          
    "accent": "#8AB4F8",         
    "accent_hover": "#AECBFA",   
    "text": "#E8EAED",           
    "text_dim": "#9AA0A6",       
    "btn_start": "#1E8E3E",      
    "btn_start_hover": "#1A7332",
    "btn_stop": "#D93025",       
    "btn_stop_hover": "#B3261E",
    "btn_browse": "#3C4043",     
    "btn_browse_hover": "#5F6368",
    "input_bg": "#171717",       
    "input_border": "#5F6368",   
    "log_bg": "#171717",         
    "log_text": "#E8EAED"        
}

# ─── Core Scraper Logic (Untouched features) ─────────────────────────────────

def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            return resp
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2)
            else:
                return None

def get_soup(url):
    resp = fetch(url)
    if resp:
        return BeautifulSoup(resp.text, 'html.parser')
    return None

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

def extract_gallery_id(url):
    match = re.search(r'/(?:actress|actor|gallery|photos|starzone)/(\d+)/', url)
    return match.group(1) if match else ''

def get_galleries(actor_url):
    galleries = []
    soup = get_soup(actor_url)
    if not soup:
        return galleries
    gallery_patterns = ['/actress/', '/actor/', '/gallery/', '/photos/']
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if any(p in href for p in gallery_patterns) and href.endswith('.aspx'):
            name = link.get_text(strip=True)
            if not name:
                img = link.find('img')
                if img:
                    name = img.get('alt', '') or img.get('title', '')
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
    if not soup:
        return [(gallery_url, None)]
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
            if full_url != gallery_url:
                page_links.add(full_url)
        next_link = soup.find('a', id='linkNext')
        if next_link and next_link.get('href'):
            full_url = urljoin(BASE_URL, next_link['href'])
            if full_url != gallery_url:
                page_links.add(full_url)
    if not page_links:
        for link in soup.find_all('a', href=True):
            text = link.get_text(strip=True)
            if text.isdigit() and int(text) > 1:
                full_url = urljoin(BASE_URL, link['href'])
                if full_url != gallery_url:
                    page_links.add(full_url)
    for url in sorted(page_links):
        pages.append((url, None))
    return pages

def get_images_from_page(soup):
    images = []
    if not soup: return images
    galdiv = soup.find('div', id='galdiv')
    thumb_imgs = galdiv.find_all('img', class_=re.compile(r'thumbnail|lazyload', re.I)) if galdiv else soup.find_all('img', class_=re.compile(r'thumbnail|lazyload', re.I))
    if galdiv and not thumb_imgs:
        thumb_imgs = galdiv.find_all('img', src=True)

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
    if parsed.netloc:
        urls.append(f"https://{parsed.netloc}{path}{query}")
    for host in IMAGE_CDN_HOSTS:
        if host != parsed.netloc:
            urls.append(f"https://{host}{path}{query}")
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
        
        # --- FIX: Set Application Icon using .ico for Windows ---
        try:
            ico_path = resource_path("logo.ico")
            self.iconbitmap(ico_path)
        except Exception:
            try:
                # Fallback for systems that don't support .ico natively
                png_path = resource_path("logo.png")
                self.app_icon = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self.app_icon)
            except Exception:
                pass # Silently continue if neither format is found
            
        # State variables
        self.is_downloading = False
        self.stop_event = threading.Event()
        
        self.load_config()
        self._build_ui()

    def load_config(self):
        # Default settings
        self.config = {
            "download_dir": os.path.join(os.path.expanduser("~"), "Downloads", "Ragalahari"),
            "threads": 5,
            "direct_dl": False
        }
        
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved_config = json.load(f)
                    self.config.update(saved_config)
            except Exception:
                pass

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
        # Header
        self.header_label = ctk.CTkLabel(
            self, 
            text="RAGALAHARI GALLERY DOWNLOADER", 
            font=ctk.CTkFont(size=22, weight="bold", family="Segoe UI"),
            text_color=UI["text"]
        )
        self.header_label.pack(pady=(25, 15))

        # URL Frame
        self.url_frame = ctk.CTkFrame(self, fg_color=UI["frame"], corner_radius=10)
        self.url_frame.pack(fill="x", padx=35, pady=10)
        
        ctk.CTkLabel(self.url_frame, text="Actor gallery profile URL:", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=15, pady=(15, 0))
        self.url_entry = ctk.CTkEntry(
            self.url_frame, 
            placeholder_text="https://www.ragalahari.com/... .aspx", 
            height=40,
            fg_color=UI["input_bg"],
            border_color=UI["input_border"],
            text_color=UI["text"]
        )
        self.url_entry.pack(fill="x", padx=15, pady=(5, 15))

        # Settings Frame
        self.settings_frame = ctk.CTkFrame(self, fg_color=UI["frame"], corner_radius=10)
        self.settings_frame.pack(fill="x", padx=35, pady=10)
        self.settings_frame.grid_columnconfigure(1, weight=1)

        # Download Path
        ctk.CTkLabel(self.settings_frame, text="Save Location:", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        self.path_entry = ctk.CTkEntry(
            self.settings_frame, 
            height=35,
            fg_color=UI["input_bg"],
            border_color=UI["input_border"],
            text_color=UI["text"]
        )
        self.path_entry.insert(0, self.config["download_dir"])
        self.path_entry.grid(row=0, column=1, padx=(0, 10), pady=(15, 5), sticky="ew")
        
        self.browse_btn = ctk.CTkButton(
            self.settings_frame, 
            text="Browse", 
            width=80, 
            fg_color=UI["btn_browse"], 
            hover_color=UI["btn_browse_hover"],
            text_color=UI["text"],
            command=self.browse_folder
        )
        self.browse_btn.grid(row=0, column=2, padx=(0, 15), pady=(15, 5))

        # Threads Settings
        ctk.CTkLabel(self.settings_frame, text="Threads (Speed):", text_color=UI["text_dim"], font=ctk.CTkFont(weight="bold")).grid(row=1, column=0, padx=15, pady=(10, 5), sticky="w")
        
        self.slider_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.slider_frame.grid(row=1, column=1, columnspan=2, padx=(0, 15), pady=(10, 5), sticky="ew")
        
        self.threads_slider = ctk.CTkSlider(
            self.slider_frame, 
            from_=1, to=15, 
            number_of_steps=14, 
            button_color=UI["accent"],
            button_hover_color=UI["accent_hover"],
            progress_color=UI["accent"],
            command=self.on_thread_change
        )
        self.threads_slider.set(self.config["threads"])
        self.threads_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.threads_label = ctk.CTkLabel(self.slider_frame, text=str(self.config["threads"]), font=ctk.CTkFont(weight="bold", size=14), text_color=UI["text"])
        self.threads_label.pack(side="right", padx=(5, 0))

        # Direct Download Checkbox
        self.direct_dl_var = ctk.BooleanVar(value=self.config["direct_dl"])
        self.direct_dl_cb = ctk.CTkCheckBox(
            self.settings_frame, 
            text="Download directly to folder (Skip Actor/Gallery subfolders)", 
            variable=self.direct_dl_var,
            text_color=UI["text"],
            fg_color=UI["accent"],
            hover_color=UI["accent_hover"],
            border_color=UI["input_border"],
            command=self.save_config
        )
        self.direct_dl_cb.grid(row=2, column=0, columnspan=3, padx=15, pady=(10, 15), sticky="w")

        # Action Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(pady=15)
        
        self.start_btn = ctk.CTkButton(
            self.btn_frame, 
            text="Start Download", 
            font=ctk.CTkFont(weight="bold", size=14), 
            height=40, 
            width=180,
            corner_radius=6,
            fg_color=UI["btn_start"],
            hover_color=UI["btn_start_hover"],
            text_color="white",
            command=self.start_download_thread
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ctk.CTkButton(
            self.btn_frame, 
            text="Stop / Cancel", 
            font=ctk.CTkFont(weight="bold", size=14), 
            height=40, 
            width=180,
            corner_radius=6,
            fg_color=UI["btn_stop"], 
            hover_color=UI["btn_stop_hover"], 
            text_color="white",
            state="disabled", 
            command=self.stop_download
        )
        self.stop_btn.pack(side="left", padx=10)

        # Progress Area
        self.progress_bar = ctk.CTkProgressBar(
            self, 
            height=10, 
            corner_radius=5,
            progress_color=UI["accent"],
            fg_color=UI["frame"]
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=35, pady=(5, 5))
        
        self.status_label = ctk.CTkLabel(self, text="Ready.", text_color=UI["text_dim"], font=ctk.CTkFont(size=12))
        self.status_label.pack(pady=(0, 10))

        # Log Console
        self.log_box = ctk.CTkTextbox(
            self, 
            state="disabled", 
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=UI["log_bg"],
            text_color=UI["log_text"],
            border_color=UI["frame"],
            border_width=1,
            corner_radius=8
        )
        self.log_box.pack(fill="both", expand=True, padx=35, pady=(0, 25))

    def on_thread_change(self, value):
        self.threads_label.configure(text=str(int(value)))
        self.save_config()

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_entry.get())
        if folder:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.save_config()

    def log(self, message):
        self.after(0, self._log_ui, message)
        
    def _log_ui(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def update_status(self, msg, progress=None):
        self.after(0, self._update_status_ui, msg, progress)
        
    def _update_status_ui(self, msg, progress):
        self.status_label.configure(text=msg)
        if progress is not None:
            self.progress_bar.set(progress)

    def stop_download(self):
        if self.is_downloading:
            self.stop_event.set()
            self.log("[!] Stopping requested... Waiting for active threads to finish.")
            self.stop_btn.configure(state="disabled")

    def start_download_thread(self):
        # Save config right when a download is started
        self.save_config()
        
        url = self.url_entry.get().strip()
        save_dir = self.path_entry.get().strip()
        
        if not url:
            messagebox.showerror("Error", "Please enter a valid URL.")
            return
        if not save_dir:
            messagebox.showerror("Error", "Please enter a valid save location.")
            return

        self.is_downloading = True
        self.stop_event.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.log("System Initialized. Starting process...")
        
        self.start_btn.configure(state="disabled", fg_color=UI["frame"])
        self.stop_btn.configure(state="normal", fg_color=UI["btn_stop"])
        self.progress_bar.set(0)
        
        # Start background thread
        threading.Thread(target=self.process_url, args=(url, save_dir), daemon=True).start()

    def process_url(self, url, base_save_dir):
        try:
            self.log(f"[*] Analyzing Target URL: {url}")
            
            # Check if it's an actor profile or a direct gallery
            if '/stars/profile/' in url or '/star/' in url or re.search(r'/stars?/\d+/', url):
                self.log("[*] Detected Actor Profile. Fetching all galleries...")
                actor_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                galleries = get_galleries(url)
                
                if not galleries:
                    self.log("[-] No galleries found for this profile.")
                else:
                    self.log(f"[+] Found {len(galleries)} galleries. Starting batch download.")
                    for i, gal in enumerate(galleries, 1):
                        if self.stop_event.is_set(): break
                        self.log(f"\n[*] Processing Gallery {i}/{len(galleries)}: {gal['name']}")
                        self.process_gallery(gal['url'], gal['name'], actor_name, base_save_dir)
            else:
                self.log("[*] Detected Direct Gallery URL.")
                gallery_name = url.split('/')[-1].replace('.aspx', '').replace('-', ' ').title()
                self.process_gallery(url, gallery_name, "Direct", base_save_dir)
                
        except Exception as e:
            self.log(f"[ERROR] Critical failure: {str(e)}")
            
        finally:
            self.is_downloading = False
            self.after(0, lambda: self.start_btn.configure(state="normal", fg_color=UI["btn_start"]))
            self.after(0, lambda: self.stop_btn.configure(state="disabled", fg_color=UI["frame"]))
            if self.stop_event.is_set():
                self.update_status("Download cancelled.")
                self.log("[!] Operation Cancelled by User.")
            else:
                self.update_status("Task completed.", 1.0)
                self.log("\n[✓] All Tasks Completed Successfully.")

    def process_gallery(self, url, gallery_name, actor_name, base_save_dir):
        self.log(f"[*] Scanning pages for images in '{gallery_name}'...")
        pages = get_gallery_pages(url)
        all_images = []
        seen = set()
        
        for i, (page_url, page_soup) in enumerate(pages, 1):
            if self.stop_event.is_set(): return
            if page_soup is None:
                page_soup = get_soup(page_url)
            if not page_soup: continue
            
            imgs = get_images_from_page(page_soup)
            new_imgs = [img for img in imgs if img not in seen]
            seen.update(new_imgs)
            all_images.extend(new_imgs)
            self.update_status(f"Scanning page {i}/{len(pages)}...")

        if not all_images:
            self.log("[-] No images found in this gallery.")
            return

        self.log(f"[*] Verifying image servers for {len(all_images)} images...")
        fixed_images = self.verify_and_fix_images(all_images)
        if not fixed_images:
            self.log("[ERROR] Could not resolve image servers.")
            return
            
        self.execute_download(fixed_images, gallery_name, actor_name, base_save_dir)

    def verify_and_fix_images(self, images):
        if not images: return []
        working_host = None
        urls_to_try = generate_fallback_urls(images[0])
        
        for test_url in urls_to_try:
            if self.stop_event.is_set(): return []
            try:
                headers = {"Referer": "https://www.ragalahari.com/"}
                resp = session.get(test_url, timeout=10, stream=True, headers=headers)
                if resp.status_code == 200:
                    content_length = resp.headers.get("content-length")
                    if not content_length or int(content_length) >= 5000:
                        working_host = urlparse(test_url).netloc
                        break
            except Exception:
                continue
                
        if not working_host: return []
        
        fixed_images = []
        for url in images:
            parsed = urlparse(url)
            fixed_images.append(f"https://{working_host}{parsed.path}?{parsed.query}")
        return fixed_images

    def execute_download(self, images, gallery_name, actor_name, base_dir):
        # ─── Direct Download Logic ───
        if self.direct_dl_var.get():
            save_dir = base_dir
        else:
            actor_dir = sanitize_filename(actor_name)
            gallery_dir = sanitize_filename(gallery_name)
            save_dir = os.path.join(base_dir, actor_dir, gallery_dir)
            
        os.makedirs(save_dir, exist_ok=True)
        
        total = len(images)
        completed = 0
        skipped = 0
        failed = 0
        
        self.log(f"[+] Starting download of {total} images...")
        self.log(f"[+] Saving to: {save_dir}")
        
        threads = int(self.threads_slider.get())
        
        def worker(idx, url):
            if self.stop_event.is_set(): return 'cancelled'
            
            parsed = urlparse(url)
            raw_filename = unquote(os.path.basename(parsed.path))
            if not raw_filename or '.' not in raw_filename:
                raw_filename = f"image_{idx:04d}.jpg"
                
            filename = sanitize_filename(raw_filename)
            save_path = os.path.join(save_dir, filename)
            
            if os.path.exists(save_path) and os.path.getsize(save_path) > 5000:
                return 'skipped'

            ok = self.download_single_image(url, save_path)
            return 'ok' if ok else 'failed'

        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(worker, i, url): url for i, url in enumerate(images, 1)}
            
            for future in as_completed(futures):
                if self.stop_event.is_set(): break
                status = future.result()
                completed += 1
                
                if status == 'skipped': skipped += 1
                elif status == 'failed': failed += 1
                
                pct = completed / total
                self.update_status(f"Downloading... {completed}/{total} (Skipped: {skipped}, Failed: {failed})", pct)

    def download_single_image(self, url, save_path):
        urls_to_try = generate_fallback_urls(url)
        for img_url in urls_to_try:
            if self.stop_event.is_set(): return False
            try:
                headers = {"Referer": "https://www.ragalahari.com/"}
                resp = session.get(img_url, timeout=15, stream=True, headers=headers)
                
                if resp.status_code != 200: continue
                if "image" not in resp.headers.get("Content-Type", "").lower(): continue
                
                size = 0
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(8192):
                        if self.stop_event.is_set():
                            break
                        if chunk:
                            f.write(chunk)
                            size += len(chunk)
                            
                if self.stop_event.is_set():
                    os.remove(save_path)
                    return False
                    
                if size >= 5000:
                    return True
                else:
                    if os.path.exists(save_path): os.remove(save_path)
                    
            except Exception:
                if os.path.exists(save_path): os.remove(save_path)
                continue
        return False

if __name__ == "__main__":
    app = DownloaderApp()
    app.mainloop()