# Reddit Arşivleyici (yt-dlp + AI + Filtreleme + Arama)
# Özellikler: Görsel/video indirimi, AI analiz, GUI, metin arama, kelime filtresi

import os
import json
import subprocess
import requests
import datetime
import threading
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import filedialog, scrolledtext
from PIL import Image
import pytesseract
import cv2
import torch
from torchvision import transforms
from torchvision.models.detection import fasterrcnn_resnet50_fpn

CONFIG_FILE = "config.json"
FAILED_URLS_FILE = "failed_downloads.txt"
AI_LOG_FILE = "ai_analyzed.txt"

# === Yardımcı Fonksiyonlar ===
def log(msg):
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)
    if 'log_area' in globals():
        log_area.insert(tk.END, msg + "\n")
        log_area.see(tk.END)
        log_area.update_idletasks()

def download_with_ytdlp(url, dest_folder):
    try:
        subprocess.run([
            "yt-dlp", url,
            "-o", str(Path(dest_folder) / "%(title).100s.%(ext)s")
        ], check=True)
        log(f"🎥 Video indirildi: {url}")
        return True
    except Exception as e:
        log(f"⛔ yt-dlp hatası ({url}): {e}")
        with open(FAILED_URLS_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
        return False

def download_file(url, dest_path):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, stream=True, timeout=15)
        if r.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            return True
    except Exception as e:
        log(f"⚠️ Görsel indirilemedi ({url}): {e}")
        with open(FAILED_URLS_FILE, "a", encoding="utf-8") as f:
            f.write(url + "\n")
    return False

def is_supported_media(url):
    valid_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".svg", ".apng", ".mp4", ".webm", ".mov", ".mkv")
    return any(url.lower().endswith(ext) for ext in valid_exts)

def load_ai_analyzed():
    return set(Path(AI_LOG_FILE).read_text(encoding="utf-8").splitlines()) if Path(AI_LOG_FILE).exists() else set()

def save_ai_analyzed(img_path):
    with open(AI_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(img_path) + "\n")

def run_ai_analysis(base_path):
    analyzed_set = load_ai_analyzed()
    model = fasterrcnn_resnet50_fpn(pretrained=True)
    model.eval()
    transform = transforms.Compose([transforms.ToTensor()])
    for post_folder in Path(base_path).glob("*"):
        img_dir = post_folder / "images"
        if not img_dir.exists(): continue
        for img_path in img_dir.glob("*.*"):
            if str(img_path) in analyzed_set:
                continue
            try:
                img_cv = cv2.imread(str(img_path))
                if img_cv is None: continue
                gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                faces = face_cascade.detectMultiScale(gray, 1.1, 4)
                if len(faces) > 0: log(f"🧠 Yüz bulundu: {img_path.name}")
                text = pytesseract.image_to_string(Image.open(img_path))
                if text.strip(): log(f"🧠 Yazı bulundu: {img_path.name} -> {text[:60]}...")
                pil_image = Image.open(img_path).convert("RGB")
                input_tensor = transform(pil_image)
                with torch.no_grad():
                    output = model([input_tensor])[0]
                for label in output['labels']:
                    log(f"🧠 Nesne tespiti ({img_path.name}): Label={label.item()}")
                save_ai_analyzed(img_path)
            except Exception as e:
                log(f"AI analiz hatası ({img_path.name}): {e}")

def matches_filter(post, keyword):
    if not keyword: return True
    keyword = keyword.lower()
    return keyword in post.title.lower() or keyword in post.selftext.lower()

def fetch_and_save(post, save_root):
    folder = save_root / post.id
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / f"{post.id}.txt", "w", encoding="utf-8") as f:
        f.write(f"Post ID: {post.id}\nBaşlık: {post.title}\n\n{post.selftext}")
    img_folder = folder / "images"
    img_folder.mkdir(exist_ok=True)
    url = post.url
    if is_supported_media(url):
        dest = img_folder / os.path.basename(urlparse(url).path)
        if not download_file(url, dest):
            download_with_ytdlp(url, img_folder)
    else:
        download_with_ytdlp(url, img_folder)

def fetch_posts(subreddit_name, client_id, client_secret, user_agent, base_folder, keyword_filter):
    import praw
    reddit = praw.Reddit(client_id=client_id, client_secret=client_secret, user_agent=user_agent)
    subreddit = reddit.subreddit(subreddit_name)
    posts = list(subreddit.new(limit=None))
    save_root = Path(base_folder) / subreddit_name
    save_root.mkdir(exist_ok=True)
    for post in posts:
        if not matches_filter(post, keyword_filter):
            continue
        try:
            fetch_and_save(post, save_root)
            log(f"✅ Post kaydedildi: {post.id}")
        except Exception as e:
            log(f"❌ Post hatası ({post.id}): {e}")

def perform_search():
    term = search_entry.get().strip().lower()
    result_box.delete(0, tk.END)
    if not term: return
    base_path = Path(folder_var.get()) / subreddit_entry.get()
    for post_folder in base_path.glob("*"):
        for txt_file in post_folder.glob("*.txt"):
            try:
                with open(txt_file, "r", encoding="utf-8") as f:
                    if term in f.read().lower():
                        result_box.insert(tk.END, str(post_folder))
                        break
            except: continue

def open_selected_folder():
    selected = result_box.get(tk.ACTIVE)
    if selected:
        subprocess.Popen(f'explorer "{selected}"' if os.name == "nt" else ["xdg-open", selected])

def save_config():
    data = {
        "subreddit": subreddit_entry.get(),
        "client_id": client_id_entry.get(),
        "client_secret": client_secret_entry.get(),
        "user_agent": user_agent_entry.get(),
        "folder": folder_var.get(),
        "filter": filter_entry.get()
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        subreddit_entry.insert(0, data.get("subreddit", ""))
        client_id_entry.insert(0, data.get("client_id", ""))
        client_secret_entry.insert(0, data.get("client_secret", ""))
        user_agent_entry.insert(0, data.get("user_agent", ""))
        folder_var.set(data.get("folder", ""))
        filter_entry.insert(0, data.get("filter", ""))
    except: pass

def start_scraping():
    save_config()
    log("📡 Reddit'ten veri çekiliyor...")
    log_area.update_idletasks()
    threading.Thread(target=lambda: fetch_posts(
        subreddit_entry.get(), client_id_entry.get(), client_secret_entry.get(),
        user_agent_entry.get(), folder_var.get(), filter_entry.get()
    ), daemon=True).start()

def start_analysis():
    log("🧠 AI analiz başlatılıyor...")
    threading.Thread(target=lambda: run_ai_analysis(Path(folder_var.get()) / subreddit_entry.get()), daemon=True).start()

# === GUI ===
window = tk.Tk()
window.title("Reddit Arşivleyici (yt-dlp + AI + Filtre + Arama)")
window.geometry("600x720")

subreddit_entry = tk.Entry(window, width=60)
client_id_entry = tk.Entry(window, width=60)
client_secret_entry = tk.Entry(window, width=60)
user_agent_entry = tk.Entry(window, width=60)
folder_var = tk.StringVar()
filter_entry = tk.Entry(window, width=60)

for label, entry in [
    ("Subreddit Adı:", subreddit_entry),
    ("Client ID:", client_id_entry),
    ("Client Secret:", client_secret_entry),
    ("User Agent:", user_agent_entry),
]:
    tk.Label(window, text=label).pack()
    entry.pack()

tk.Label(window, text="Kayıt Klasörü:").pack()
tk.Entry(window, textvariable=folder_var, width=60).pack()
tk.Button(window, text="Klasör Seç", command=lambda: folder_var.set(filedialog.askdirectory())).pack()

tk.Label(window, text="🔎 Sadece bu kelimeyi içeren postları indir:").pack()
filter_entry.pack()

tk.Button(window, text="📥 Postları İndir", command=start_scraping).pack(pady=5)
tk.Button(window, text="🧠 AI Analiz", command=start_analysis).pack(pady=5)

tk.Label(window, text="🗂️ Metin Dosyasında Ara:").pack()
search_entry = tk.Entry(window, width=40)
search_entry.pack()
tk.Button(window, text="Ara", command=perform_search).pack(pady=5)
result_box = tk.Listbox(window, width=70, height=8)
result_box.pack(pady=5)
tk.Button(window, text="Klasörü Aç", command=open_selected_folder).pack()

def open_search_window():
    win = tk.Toplevel(window)
    win.title("🔎 Metin Dosyasında Ara (Pencere)")
    win.geometry("520x400")
    tk.Label(win, text="Aranacak Kelime:").pack()
    entry = tk.Entry(win, width=40)
    entry.pack()
    result_box = tk.Listbox(win, width=70, height=15)
    result_box.pack(pady=10)

    def perform():
        term = entry.get().strip().lower()
        result_box.delete(0, tk.END)
        if not term:
            return
        base_path = Path(folder_var.get()) / subreddit_entry.get()
        for post_folder in base_path.glob("*"):
            for txt_file in post_folder.glob("*.txt"):
                try:
                    with open(txt_file, "r", encoding="utf-8") as f:
                        if term in f.read().lower():
                            result_box.insert(tk.END, str(post_folder))
                            break
                except:
                    continue

    def open_folder():
        selected = result_box.get(tk.ACTIVE)
        if selected:
            subprocess.Popen(
                f'explorer "{selected}"' if os.name == "nt" else ["xdg-open", selected]
            )

    tk.Button(win, text="Ara", command=perform).pack(pady=5)
    tk.Button(win, text="Klasörü Aç", command=open_folder).pack()

tk.Button(window, text="🔎 Metin Ara (Yeni Pencere)", command=open_search_window).pack(pady=5)

log_area = scrolledtext.ScrolledText(window, width=70, height=15)
log_area.pack(padx=10, pady=10)

load_config()
window.mainloop()
