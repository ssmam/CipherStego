
#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import struct
import socket
import base64
import re

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import secrets

try:
    import cv2
    CV2_AVAILABLE = True
except:
    CV2_AVAILABLE = False

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except:
    PIL_AVAILABLE = False

try:
    import pygame
    pygame.mixer.pre_init(frequency=22050, size=-16, channels=2, buffer=512)
    pygame.mixer.init()
    Pygame_AVAILABLE = True
except:
    Pygame_AVAILABLE = False

# ===================== CRYPTO & STEG FUNCTIONS =====================
def check_password_strength(pwd):
    if len(pwd) < 12: return False, "Too short (min 12 chars)"
    if not re.search(r'[A-Z]', pwd): return False, "Needs uppercase"
    if not re.search(r'[a-z]', pwd): return False, "Needs lowercase"
    if not re.search(r'\d', pwd): return False, "Needs number"
    if not re.search(r'[!@#$%^&*]', pwd): return False, "Needs symbol"
    return True, "Strong password"

SALT_SIZE = 16
TERMINATOR = b"::END::END::"

def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt,
                     iterations=200000, backend=default_backend())
    return kdf.derive(password.encode('utf-8'))

def encrypt_bytes(password: str, plaintext: bytes) -> bytes:
    salt = secrets.token_bytes(SALT_SIZE)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return salt + nonce + ct

def decrypt_bytes(password: str, data: bytes) -> bytes:
    if len(data) < SALT_SIZE + 12:
        raise ValueError("Too short")
    salt = data[:SALT_SIZE]
    nonce = data[SALT_SIZE:SALT_SIZE+12]
    ct = data[SALT_SIZE+12:]
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)

def safe_base64_decode(b64_string: str) -> bytes:
    if not b64_string or len(b64_string) < 10:
        return b""
    clean_b64 = ''.join(c for c in b64_string
                        if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    missing_padding = len(clean_b64) % 4
    if missing_padding:
        clean_b64 += '=' * (4 - missing_padding)
    try:
        return base64.b64decode(clean_b64)
    except:
        return b""

# ===================== FIXED AUDIO STEG =====================
def embed_payload_in_audio_wav(cover_audio: str, out_audio: str, payload_text: str):
    import wave
    
    with wave.open(cover_audio, 'rb') as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        sampwidth = wav_file.getsampwidth()
        channels = wav_file.getnchannels()
        audio_data = wav_file.readframes(frames)
    
    # FIXED: Byte-level processing (no numpy)
    audio_bytes = bytearray(audio_data)
    data_bits = ''.join(format(byte, '08b') for byte in payload_text.encode('ascii', errors='ignore'))
    bit_idx = 0
    
    # Embed 1 bit per sample (LSB of each byte)
    for i in range(len(audio_bytes)):
        if bit_idx < len(data_bits):
            audio_bytes[i] = (audio_bytes[i] & 0xFE) | int(data_bits[bit_idx])
            bit_idx += 1
        if bit_idx >= len(data_bits):
            break
    
    with wave.open(out_audio, 'wb') as out_wav:
        out_wav.setnchannels(channels)
        out_wav.setsampwidth(sampwidth)
        out_wav.setframerate(rate)
        out_wav.writeframes(bytes(audio_bytes))

def extract_payload_from_audio_wav(audio_path: str) -> bytes:
    import wave
    
    with wave.open(audio_path, 'rb') as wav_file:
        audio_data = wav_file.readframes(wav_file.getnframes())
    
    audio_bytes = bytearray(audio_data)
    bits = ''
    
    for byte_val in audio_bytes:
        bits += str(byte_val & 1)
        if len(bits) > 100000:
            break
    
    bytes_data = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        bytes_data.append(int(bits[i:i+8], 2))
    return bytes(bytes_data)

# ===================== IMAGE STEG =====================
def embed_payload_in_image(cover_img: str, out_img: str, payload_text: str):
    if not CV2_AVAILABLE:
        raise RuntimeError("pip install opencv-python")
    img = cv2.imread(cover_img)
    if img is None:
        raise FileNotFoundError(f"Cannot read {cover_img}")

    data_bytes = payload_text.encode('ascii', errors='ignore')
    binary_data = ''.join(format(byte, '08b') for byte in data_bytes)

    h, w, _ = img.shape
    bit_idx = 0

    for i in range(h):
        for j in range(w):
            for c in range(3):
                if bit_idx < len(binary_data):
                    img[i, j, c] = (img[i, j, c] & 0xFE) | int(binary_data[bit_idx])
                    bit_idx += 1
                if bit_idx >= len(binary_data):
                    break
            if bit_idx >= len(binary_data):
                break
        if bit_idx >= len(binary_data):
            break

    cv2.imwrite(out_img, img, [cv2.IMWRITE_PNG_COMPRESSION, 0])

def extract_payload_from_image(image_path: str) -> bytes:
    if not CV2_AVAILABLE:
        raise RuntimeError("pip install opencv-python")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read {image_path}")

    h, w, _ = img.shape
    bits = ''
    for i in range(h):
        for j in range(w):
            for c in range(3):
                bits += str(img[i, j, c] & 1)
                if len(bits) > 100000:
                    break
            if len(bits) > 100000:
                break
        if len(bits) > 100000:
            break

    bytes_data = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        bytes_data.append(int(bits[i:i+8], 2))
    return bytes(bytes_data)

# ===================== TEXT STEG =====================
ZWC = {"00": '\u200C', "01": '\u202C', "10": '\u200E', "11": '\u202D'}
ZWC_REV = {v: k for k, v in ZWC.items()}

def bytes_to_zwc(b: bytes) -> str:
    bits = ''.join(format(byte, '08b') for byte in b)
    if len(bits) % 2 != 0:
        bits += '0'
    return ''.join(ZWC[bits[i:i+2]] for i in range(0, len(bits), 2))

def zwc_to_bytes(zwc: str) -> bytes:
    bits = ''.join(ZWC_REV.get(ch, '00') for ch in zwc)
    bits = bits[:len(bits) - (len(bits) % 8)]
    out = bytearray()
    for i in range(0, len(bits), 8):
        out.append(int(bits[i:i+8], 2))
    return bytes(out)

def embed_zwc_in_text(cover_path: str, out_path: str, zwc: str):
    with open(cover_path, 'r', encoding='utf-8') as f:
        content = f.read()
    parts = content.split('\n\n', 1)
    new_content = parts[0] + zwc + ('' if len(parts) == 1 else '\n\n' + parts[1])
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

def extract_zwc_from_text(path: str) -> bytes:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        zwc_only = ''.join(ch for ch in content if ch in ZWC_REV)
        return zwc_to_bytes(zwc_only)
    except:
        return b''

# ===================== VIDEO STEG =====================
def embed_payload_in_video_mp4(cover_video: str, out_video: str, payload_text: str):
    if not CV2_AVAILABLE:
        raise RuntimeError("pip install opencv-python")
    
    cap = cv2.VideoCapture(cover_video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(out_video, fourcc, fps, (width, height))
    
    data_bits = ''.join(format(byte, '08b') for byte in payload_text.encode('ascii', errors='ignore'))
    bit_idx = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        h, w = frame.shape[:2]
        for i in range(min(h, 50)):  # First 50 rows
            for j in range(w):
                for c in range(3):
                    if bit_idx < len(data_bits):
                        frame[i, j, c] = (frame[i, j, c] & 0xFE) | int(data_bits[bit_idx])
                        bit_idx += 1
                    if bit_idx >= len(data_bits):
                        break
                if bit_idx >= len(data_bits):
                    break
            if bit_idx >= len(data_bits):
                break
        
        out.write(frame)
        if bit_idx >= len(data_bits):
            break
    
    cap.release()
    out.release()
    cv2.destroyAllWindows()

def extract_payload_from_video_mp4(video_path: str) -> bytes:
    if not CV2_AVAILABLE:
        raise RuntimeError("pip install opencv-python")
    
    cap = cv2.VideoCapture(video_path)
    bits = ''
    
    frame_count = 0
    while cap.isOpened() and len(bits) < 100000 and frame_count < 100:
        ret, frame = cap.read()
        if not ret:
            break
        
        h, w = frame.shape[:2]
        for i in range(min(h, 50)):
            for j in range(w):
                for c in range(3):
                    bits += str(frame[i, j, c] & 1)
                    if len(bits) > 100000:
                        break
                if len(bits) > 100000:
                    break
            if len(bits) > 100000:
                break
        frame_count += 1
    
    cap.release()
    cv2.destroyAllWindows()
    
    bytes_data = bytearray()
    for i in range(0, len(bits) - len(bits) % 8, 8):
        bytes_data.append(int(bits[i:i+8], 2))
    return bytes(bytes_data)

# ===================== NETWORK =====================
def send_file_over_tcp(host: str, port: int, path: str, status_callback=None):
    filename = os.path.basename(path).encode('utf-8')
    payload = open(path, 'rb').read()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    s.sendall(struct.pack('!I', len(filename)) + filename)
    s.sendall(struct.pack('!Q', len(payload)))
    s.sendall(payload)
    s.close()
    if status_callback:
        status_callback(f"Sent {os.path.basename(path)} ({len(payload)} bytes)")

def listen_once_and_save(bind_port: int, save_dir: str, status_callback=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', bind_port))
    s.listen(1)
    if status_callback:
        status_callback(f"Listening on port {bind_port}...")
    conn, addr = s.accept()
    if status_callback:
        status_callback(f"Connection from {addr}")

    fname_len = struct.unpack('!I', conn.recv(4))[0]
    filename = conn.recv(fname_len).decode('utf-8')
    payload_len = struct.unpack('!Q', conn.recv(8))[0]

    if status_callback:
        status_callback(f"Receiving {filename} ({payload_len} bytes)...")
    data = b''
    while len(data) < payload_len:
        part = conn.recv(4096)
        if not part:
            break
        data += part

    conn.close()
    s.close()
    os.makedirs(save_dir, exist_ok=True)
    out_path = os.path.join(save_dir, filename)
    with open(out_path, 'wb') as f:
        f.write(data)
    if status_callback:
        status_callback(f"Saved: {out_path}")
    return out_path

# ===================== YOUR ORIGINAL THEME =====================
THEME = {
    "bg_window": "#f8fafc",
    "fg_main": "#1e293b",
    "fg_sub": "#475569",
    "accent": "#3b82f6",
    "accent_dark": "#1d4ed8",
    "danger": "#dc2626",
    "success": "#16a34a",
    "decoded_fg": "#d97706",
    "sender_bg": "#eff6ff",
    "sender_panel": "#dbeafe",
    "sender_text": "#1e40af",
    "receiver_bg": "#f0fdf4",
    "receiver_panel": "#dcfce7",
    "receiver_text": "#166534",
    "terminal_bg": "#fdf4ff",
    "terminal_text": "#581c87",
    "button_primary": "#3b82f6",
    "button_secondary": "#10b981",
    "entry_bg": "#ffffff",
    "preview_bg": "#fefce8"
}

FONTS = {
    "title": ("Segoe UI", 20, "bold"),
    "subtitle": ("Segoe UI", 11),
    "heading": ("Segoe UI", 13, "bold"),
    "body": ("Segoe UI", 9),
    "button": ("Segoe UI", 9, "bold")
}

class ThemedButton(tk.Button):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.configure(
            bg=THEME["button_primary"],
            fg="white",
            activebackground=THEME["accent_dark"],
            activeforeground="white",
            relief="flat",
            bd=0,
            font=FONTS["button"],
            cursor="hand2",
            padx=20,
            pady=8
        )
        self.bind("<Enter>", lambda e: self.config(bg=THEME["accent_dark"]))
        self.bind("<Leave>", lambda e: self.config(bg=THEME["button_primary"]))

class ThemedSecondaryButton(tk.Button):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.configure(
            bg=THEME["button_secondary"],
            fg="white",
            activebackground="#059669",
            activeforeground="white",
            relief="flat",
            bd=0,
            font=FONTS["button"],
            cursor="hand2",
            padx=20,
            pady=8
        )
        self.bind("<Enter>", lambda e: self.config(bg="#059669"))
        self.bind("<Leave>", lambda e: self.config(bg=THEME["button_secondary"]))

class ThemedEntry(tk.Entry):
    def __init__(self, master, width=20, **kw):
        super().__init__(master, width=width, **kw)
        self.configure(
            bg=THEME["entry_bg"],
            fg=THEME["fg_main"],
            insertbackground=THEME["fg_main"],
            relief="flat",
            highlightthickness=2,
            highlightbackground=THEME["accent"],
            highlightcolor=THEME["accent"],
            font=FONTS["body"]
        )

# ===================== FIXED PREVIEW WINDOW (YOUR ORIGINAL STYLE) =====================
class PreviewWindow:
    def __init__(self, parent, stego_path, callback):
        self.parent = parent
        self.stego_path = stego_path
        self.callback = callback
        self.window = tk.Toplevel(parent)
        self.window.title("📁 Received Stego File Preview")
        self.window.geometry("850x650")
        self.window.configure(bg=THEME["preview_bg"])
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(True, True)
        
        self._build_preview()
    
    def _build_preview(self):
        title_frame = tk.Frame(self.window, bg=THEME["preview_bg"])
        title_frame.pack(fill="x", pady=(10, 5))
        
        tk.Label(
            title_frame,
            text="🎨 STEG FILE PREVIEW",
            font=FONTS["title"],
            fg=THEME["accent"],
            bg=THEME["preview_bg"]
        ).pack(pady=(0, 5))
        
        tk.Label(
            title_frame,
            text=f"File: {os.path.basename(self.stego_path)}",
            font=FONTS["subtitle"],
            fg=THEME["fg_main"],
            bg=THEME["preview_bg"]
        ).pack(pady=(0, 15))
        
        content_frame = tk.Frame(self.window, bg=THEME["preview_bg"])
        content_frame.pack(fill="both", expand=True, padx=20, pady=10)
        content_frame.pack_propagate(False)
        
        self.content_subframe = tk.Frame(content_frame, bg=THEME["preview_bg"])
        self.content_subframe.pack(fill="both", expand=True)
        
        file_ext = os.path.splitext(self.stego_path)[1].lower()
        
        if file_ext in ['.png', '.jpg', '.jpeg', '.bmp'] and CV2_AVAILABLE and PIL_AVAILABLE:
            self._show_image_preview(self.content_subframe)
        elif file_ext in ['.txt', '.md']:
            self._show_text_preview(self.content_subframe)
        elif file_ext == '.wav' and Pygame_AVAILABLE:
            self._show_audio_preview(self.content_subframe)
        elif file_ext == '.mp4' and CV2_AVAILABLE:
            self._show_video_preview(self.content_subframe)
        else:
            tk.Label(self.content_subframe, text="✅ STEGO FILE READY\n🔓 Click DECRYPT to extract secret", 
                    font=FONTS["heading"], fg=THEME["success"],
                    bg=THEME["preview_bg"]).pack(expand=True)
        
        # ALWAYS SHOW DECRYPT BUTTON (AS REQUESTED)
        btn_frame = tk.Frame(self.window, bg=THEME["preview_bg"])
        btn_frame.pack(fill="x", pady=(10, 20))
        
        ThemedSecondaryButton(btn_frame, text="🔓 DECRYPT NOW", 
                            command=self._decrypt).pack(side="left", padx=(20, 10))
        ThemedSecondaryButton(btn_frame, text="❌ Close", 
                            command=self.window.destroy).pack(side="left", padx=10)
    
    def _show_image_preview(self, parent):
        try:
            img = cv2.imread(self.stego_path)
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            h, w = img_rgb.shape[:2]
            
            max_size = 550
            scale = min(max_size/w, max_size/h, 1.0)
            new_w, new_h = int(w*scale), int(h*scale)
            
            img_resized = cv2.resize(img_rgb, (new_w, new_h))
            pil_img = Image.fromarray(img_resized)
            photo = ImageTk.PhotoImage(pil_img)
            
            label = tk.Label(parent, image=photo, bg=THEME["preview_bg"], 
                           relief="solid", bd=1)
            label.image = photo
            label.pack(pady=10)
            
            tk.Label(parent, text="🖼️ Steganography Image (LSB embedded)",
                    font=FONTS["body"], fg=THEME["fg_sub"],
                    bg=THEME["preview_bg"]).pack()
        except Exception as e:
            tk.Label(parent, text="✅ Image stego file ready for extraction", 
                    font=FONTS["body"], fg=THEME["success"],
                    bg=THEME["preview_bg"]).pack(expand=True)
    
    def _show_text_preview(self, parent):
        try:
            with open(self.stego_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            text_frame = tk.Frame(parent, bg=THEME["preview_bg"])
            text_frame.pack(fill="both", expand=True, pady=5)
            
            text_widget = tk.Text(text_frame, wrap="word", height=20, width=70,
                                bg="white", fg="#1e293b", font=("Consolas", 10),
                                relief="flat", bd=2, state="normal")
            text_widget.insert("1.0", content[:5000])
            text_widget.config(state="disabled")
            
            v_scrollbar = tk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
            text_widget.configure(yscrollcommand=v_scrollbar.set)
            
            text_widget.pack(side="left", fill="both", expand=True, padx=(5,0))
            v_scrollbar.pack(side="right", fill="y")
            
            tk.Label(parent, text="📝 Steganography Text (ZWC embedded)",
                    font=FONTS["body"], fg=THEME["fg_sub"],
                    bg=THEME["preview_bg"]).pack(pady=(5,0))
        except:
            tk.Label(parent, text="✅ Text stego file ready for extraction", 
                    font=FONTS["body"], fg=THEME["success"],
                    bg=THEME["preview_bg"]).pack(expand=True)
    
    def _show_audio_preview(self, parent):
        tk.Label(parent, text="🎵 AUDIO STEG FILE (WAV)", 
                font=FONTS["heading"], fg=THEME["success"],
                bg=THEME["preview_bg"]).pack(pady=20)
        
        play_btn = ThemedSecondaryButton(parent, text="▶️ PLAY AUDIO", 
                                       command=self._play_audio)
        play_btn.pack(pady=10)
        
        tk.Label(parent, text="✅ Audio stego ready - Click PLAY to test\n🔓 DECRYPT button always available",
                font=FONTS["body"], fg=THEME["fg_sub"],
                bg=THEME["preview_bg"]).pack(pady=10)
    
    def _play_audio(self):
        try:
            pygame.mixer.music.load(self.stego_path)
            pygame.mixer.music.play()
        except:
            pass
    
    def _show_video_preview(self, parent):
        tk.Label(parent, text="🎥 VIDEO STEG FILE (MP4)", 
                font=FONTS["heading"], fg=THEME["success"],
                bg=THEME["preview_bg"]).pack(pady=20)
        
        tk.Label(parent, text="✅ Video stego ready for extraction\n📹 Hidden data embedded in frames",
                font=FONTS["body"], fg=THEME["fg_sub"],
                bg=THEME["preview_bg"]).pack(expand=True, pady=20)
    
    def _decrypt(self):
        self.window.destroy()
        self.callback(self.stego_path)

# ===================== YOUR ORIGINAL UI (UNCHANGED) =====================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cyber project proposal - 0xCipherLink v8.2")
        self.geometry("1000x700")
        self.configure(bg=THEME["bg_window"])
        self.minsize(950, 650)
        self.received_stego_path = None
        self._build_ui()

    def _build_ui(self):
        title_frame = tk.Frame(self, bg=THEME["bg_window"])
        title_frame.pack(fill="x", pady=(15, 8))

        tk.Label(
            title_frame,
            text="🔒 CipherStego Transit",
            font=FONTS["title"],
            fg=THEME["accent"],
            bg=THEME["bg_window"]
        ).pack(pady=2)

        tk.Label(
            title_frame,
            text="Secure File Transfer using Image/Text/Audio Steganography",
            font=FONTS["subtitle"],
            fg=THEME["fg_sub"],
            bg=THEME["bg_window"]
        ).pack(pady=(0, 10))

        main_panel = tk.Frame(self, bg=THEME["bg_window"])
        main_panel.pack(fill="both", expand=True, padx=25, pady=10)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=THEME["bg_window"])
        style.configure("TNotebook.Tab", 
                       background="#e2e8f0", 
                       foreground=THEME["fg_main"],
                       font=FONTS["heading"],
                       padding=[15, 10])
        style.map("TNotebook.Tab",
                 background=[("selected", "#ffffff"), ("active", "#f1f5f9")],
                 foreground=[("selected", THEME["fg_main"]), ("active", THEME["fg_main"])])

        notebook = ttk.Notebook(main_panel)
        notebook.pack(fill="both", expand=True)

        sender_page = tk.Frame(notebook, bg=THEME["sender_bg"])
        receiver_page = tk.Frame(notebook, bg=THEME["receiver_bg"])
        logs_page = tk.Frame(notebook, bg=THEME["terminal_bg"])

        notebook.add(sender_page, text=" 👤 SENDER ")
        notebook.add(receiver_page, text=" 📥 RECEIVER ")
        notebook.add(logs_page, text=" 💻 TERMINAL ")

        self._build_sender(sender_page)
        self._build_receiver(receiver_page)
        self._build_logs(logs_page)

    def _build_sender(self, parent):
        tk.Label(
            parent,
            text="🚀 SENDER CONSOLE",
            font=("Segoe UI", 16, "bold"),
            fg=THEME["sender_text"],
            bg=THEME["sender_bg"]
        ).pack(anchor="w", padx=20, pady=(15, 10))

        conn_frame = tk.LabelFrame(parent, text="Connection Settings", 
                                   font=FONTS["heading"], fg=THEME["sender_text"],
                                   bg=THEME["sender_panel"])
        conn_frame.pack(fill="x", padx=20, pady=5)
        conn_frame.configure(padx=12, pady=10)

        row1 = tk.Frame(conn_frame, bg=THEME["sender_panel"])
        row1.pack(fill="x", pady=5)
        tk.Label(row1, text="🌐 Host / IP:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["sender_panel"]).pack(side="left")
        self.sender_host = ThemedEntry(row1, width=20)
        self.sender_host.pack(side="left", padx=(10, 15))

        tk.Label(row1, text="🔌 Port:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["sender_panel"]).pack(side="left")
        self.sender_port = ThemedEntry(row1, width=8)
        self.sender_port.pack(side="left", padx=(5, 0))

        row2 = tk.Frame(conn_frame, bg=THEME["sender_panel"])
        row2.pack(fill="x", pady=5)
        tk.Label(row2, text="🔐 Passphrase:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["sender_panel"]).pack(side="left")
        self.sender_pwd = ThemedEntry(row2, width=22)
        self.sender_pwd.pack(side="left", padx=(10, 10))
        self.sender_pwd.config(show="*")
        self.sender_pwd_status = tk.Label(row2, text="Enter strong password", 
                                        font=FONTS["body"], fg=THEME["fg_sub"],
                                        bg=THEME["sender_panel"])
        self.sender_pwd_status.pack(side="left")
        self.sender_pwd.bind("<KeyRelease>", self._check_sender_pwd)

        files_frame = tk.LabelFrame(parent, text="📁 File Selection", 
                                    font=FONTS["heading"], fg=THEME["sender_text"],
                                    bg=THEME["sender_panel"])
        files_frame.pack(fill="x", padx=20, pady=10)
        files_frame.configure(padx=12, pady=10)
        files_frame.columnconfigure(1, weight=1)

        tk.Label(files_frame, text="📄 Secret file:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["sender_panel"]
                ).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=8)
        self.secret_file = ThemedEntry(files_frame, width=40)
        self.secret_file.grid(row=0, column=1, padx=8, pady=8, sticky="we")
        ThemedSecondaryButton(files_frame, text="📂 Browse", 
                            command=self._browse_secret).grid(row=0, column=2, padx=(8, 12), pady=8)

        tk.Label(files_frame, text="🖼️ Cover file:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["sender_panel"]
                ).grid(row=1, column=0, sticky="w", padx=(12, 8), pady=8)
        self.cover_file = ThemedEntry(files_frame, width=40)
        self.cover_file.grid(row=1, column=1, padx=8, pady=8, sticky="we")
        ThemedSecondaryButton(files_frame, text="📂 Browse", 
                            command=self._browse_cover).grid(row=1, column=2, padx=(8, 12), pady=8)

        method_frame = tk.Frame(parent, bg=THEME["sender_bg"])
        method_frame.pack(fill="x", padx=20, pady=5)
        tk.Label(method_frame, text="🎯 Steganography Method:", 
                font=FONTS["heading"], fg=THEME["sender_text"],
                bg=THEME["sender_bg"]).pack(anchor="w", pady=(8, 3))
        
        self.transport_var = tk.StringVar(value="stego_image")
        tk.Radiobutton(method_frame, text="🖼️ Image LSB (PNG/JPG)", 
                      variable=self.transport_var, value="stego_image",
                      bg=THEME["sender_bg"], fg=THEME["fg_main"],
                      selectcolor="#bfdbfe", font=FONTS["body"]
                      ).pack(anchor="w", padx=12, pady=3)
        tk.Radiobutton(method_frame, text="📝 Text ZWC (TXT)", 
                      variable=self.transport_var, value="stego_text",
                      bg=THEME["sender_bg"], fg=THEME["fg_main"],
                      selectcolor="#bfdbfe", font=FONTS["body"]
                      ).pack(anchor="w", padx=12, pady=3)
        tk.Radiobutton(method_frame, text="🎵 Audio LSB (WAV)", 
                      variable=self.transport_var, value="stego_audio",
                      bg=THEME["sender_bg"], fg=THEME["fg_main"],
                      selectcolor="#bfdbfe", font=FONTS["body"]
                      ).pack(anchor="w", padx=12, pady=3)
        tk.Radiobutton(method_frame, text="🎥 Video LSB (MP4)", 
                      variable=self.transport_var, value="stego_video",
                      bg=THEME["sender_bg"], fg=THEME["fg_main"],
                      selectcolor="#bfdbfe", font=FONTS["body"]
                      ).pack(anchor="w", padx=12, pady=3)

        btn_frame = tk.Frame(parent, bg=THEME["sender_bg"])
        btn_frame.pack(fill="x", pady=20)
        ThemedButton(btn_frame, text="🚀 SEND STEGO PAYLOAD",
                     command=self._sender_send).pack(pady=10)

    def _build_receiver(self, parent):
        tk.Label(parent, text="📥 RECEIVER CONSOLE", 
                font=("Segoe UI", 16, "bold"), fg=THEME["receiver_text"],
                bg=THEME["receiver_bg"]).pack(anchor="w", padx=20, pady=(15, 10))

        settings_frame = tk.LabelFrame(parent, text="⚙️ Receiver Settings", 
                                       font=FONTS["heading"], fg=THEME["receiver_text"],
                                       bg=THEME["receiver_panel"])
        settings_frame.pack(fill="x", padx=20, pady=5)
        settings_frame.configure(padx=12, pady=10)

        row1 = tk.Frame(settings_frame, bg=THEME["receiver_panel"])
        row1.pack(fill="x", pady=5)
        tk.Label(row1, text="🔌 Port:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["receiver_panel"]).pack(side="left")
        self.recv_port = ThemedEntry(row1, width=8)
        self.recv_port.pack(side="left", padx=(10, 0))

        row2 = tk.Frame(settings_frame, bg=THEME["receiver_panel"])
        row2.pack(fill="x", pady=5)
        tk.Label(row2, text="🔐 Passphrase:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["receiver_panel"]).pack(side="left")
        self.recv_pwd = ThemedEntry(row2, width=22)
        self.recv_pwd.pack(side="left", padx=(10, 10))
        self.recv_pwd.config(show="*")
        self.recv_pwd_status = tk.Label(row2, text="Enter strong password", 
                                       font=FONTS["body"], fg=THEME["fg_sub"],
                                       bg=THEME["receiver_panel"])
        self.recv_pwd_status.pack(side="left")
        self.recv_pwd.bind("<KeyRelease>", self._check_recv_pwd)

        row3 = tk.Frame(settings_frame, bg=THEME["receiver_panel"])
        row3.pack(fill="x", pady=5)
        tk.Label(row3, text="📁 Output folder:", font=FONTS["body"],
                fg=THEME["fg_main"], bg=THEME["receiver_panel"]).pack(side="left")
        self.recv_folder = ThemedEntry(row3, width=35)
        self.recv_folder.insert(0, "./received")
        self.recv_folder.pack(side="left", padx=(10, 0))

        btn_frame = tk.Frame(parent, bg=THEME["receiver_bg"])
        btn_frame.pack(fill="x", pady=20)
        ThemedButton(btn_frame, text="👂 LISTEN FOR STEGO FILE",
                     command=self._receiver_listen).pack(pady=10)

    def _build_logs(self, parent):
        tk.Label(parent, text="💻 COMMAND TERMINAL", 
                font=("Segoe UI", 16, "bold"), fg=THEME["terminal_text"],
                bg=THEME["terminal_bg"]).pack(anchor="w", padx=20, pady=(15, 10))

        log_container = tk.Frame(parent, bg=THEME["terminal_bg"])
        log_container.pack(fill="both", expand=True, padx=20, pady=5)

        self.log_text = tk.Text(log_container, bg="#ffffff", fg="#1e293b",
                               font=("Consolas", 10), relief="flat",
                               insertbackground=THEME["terminal_text"], wrap="word")
        self.log_text.tag_configure("log", foreground="#1e293b")
        self.log_text.tag_configure("decoded_header", foreground=THEME["terminal_text"], 
                                   font=("Consolas", 10, "bold"))
        self.log_text.tag_configure("decoded_msg", foreground=THEME["decoded_fg"], 
                                   font=("Consolas", 10, "bold"), background="#fef3c7")

        scrollbar = tk.Scrollbar(log_container, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _check_sender_pwd(self, event=None):
        pwd = self.sender_pwd.get()
        ok, msg = check_password_strength(pwd)
        self.sender_pwd_status.config(text=msg, fg=THEME["success"] if ok else THEME["danger"])

    def _check_recv_pwd(self, event=None):
        pwd = self.recv_pwd.get()
        ok, msg = check_password_strength(pwd)
        self.recv_pwd_status.config(text=msg, fg=THEME["success"] if ok else THEME["danger"])

    def _browse_secret(self):
        path = filedialog.askopenfilename()
        if path:
            self.secret_file.delete(0, "end")
            self.secret_file.insert(0, path)

    def _browse_cover(self):
        mode = self.transport_var.get()
        if mode == "stego_image":
            ftypes = [("Images", "*.png *.jpg *.jpeg *.bmp")]
        elif mode == "stego_text":
            ftypes = [("Text files", "*.txt *.md")]
        elif mode == "stego_audio":
            ftypes = [("WAV Audio", "*.wav")]
        elif mode == "stego_video":
            ftypes = [("MP4 Video", "*.mp4")]
        path = filedialog.askopenfilename(filetypes=ftypes)
        if path:
            self.cover_file.delete(0, "end")
            self.cover_file.insert(0, path)

    def log(self, msg):
        self.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg):
        self.log_text.insert("end", msg + "\n", ("log",))
        self.log_text.see("end")

    def _append_decoded(self, header, message_text):
        self.log_text.insert("end", "\n", ("log",))
        self.log_text.insert("end", header + "\n", ("decoded_header",))
        self.log_text.insert("end", message_text + "\n", ("decoded_msg",))
        self.log_text.see("end")

    def _sender_send(self):
        pwd = self.sender_pwd.get()
        ok, msg = check_password_strength(pwd)
        if not ok:
            messagebox.showerror("Weak password", msg)
            return
        threading.Thread(target=self._sender_worker, daemon=True).start()

    def _sender_worker(self):
        try:
            secret_path = self.secret_file.get()
            cover_path = self.cover_file.get()
            host = self.sender_host.get()
            port = int(self.sender_port.get())
            pwd = self.sender_pwd.get()
            transport = self.transport_var.get()

            if not all([secret_path, cover_path, pwd, host]):
                self.log("❌ Missing files / password / host")
                return

            self.log(f"🔒 Encrypting {os.path.basename(secret_path)}...")
            secret_data = open(secret_path, "rb").read()
            encrypted = encrypt_bytes(pwd, secret_data + TERMINATOR)
            b64_data = base64.b64encode(encrypted).decode("ascii")
            self.log(f"✅ Encrypted size: {len(encrypted)} bytes")

            stego_path = "stego_file"
            if transport == "stego_image":
                if not CV2_AVAILABLE:
                    self.log("❌ Install: pip install opencv-python")
                    return
                stego_path += ".png"
                embed_payload_in_image(cover_path, stego_path, b64_data)
                self.log("✅ Image LSB embedding done")
            elif transport == "stego_text":
                stego_path += ".txt"
                zwc = bytes_to_zwc(b64_data.encode("ascii"))
                embed_zwc_in_text(cover_path, stego_path, zwc)
                self.log("✅ Text ZWC embedding done")
            elif transport == "stego_audio":
                stego_path += ".wav"
                embed_payload_in_audio_wav(cover_path, stego_path, b64_data)
                self.log("✅ Audio WAV LSB embedding done")
            elif transport == "stego_video":
                if not CV2_AVAILABLE:
                    self.log("❌ Install: pip install opencv-python")
                    return
                stego_path += ".mp4"
                embed_payload_in_video_mp4(cover_path, stego_path, b64_data)
                self.log("✅ Video MP4 LSB embedding done")

            self.log(f"📤 Sending to {host}:{port}...")
            send_file_over_tcp(host, port, stego_path, self.log)
            self.log("🎉 Send complete!")
            if os.path.exists(stego_path):
                os.remove(stego_path)
        except Exception as e:
            self.log(f"❌ Sender error: {e}")

    def _receiver_listen(self):
        threading.Thread(target=self._receiver_listen_worker, daemon=True).start()

    def _receiver_listen_worker(self):
        try:
            port = int(self.recv_port.get())
            save_dir = self.recv_folder.get()
            
            self.log("👂 Listening for stego file...")
            self.received_stego_path = listen_once_and_save(port, save_dir, self.log)
            
            if self.received_stego_path:
                self.after(0, lambda: self._show_stego_preview(self.received_stego_path))
        except Exception as e:
            self.log(f"❌ Listen error: {e}")

    def _show_stego_preview(self, stego_path):
        PreviewWindow(self, stego_path, self._manual_decrypt)

    def _manual_decrypt(self, stego_path):
        pwd = self.recv_pwd.get()
        ok, msg = check_password_strength(pwd)
        if not ok:
            messagebox.showerror("Weak password", msg)
            return
        
        threading.Thread(target=lambda: self._decrypt_worker(stego_path, pwd), daemon=True).start()

    def _decrypt_worker(self, stego_path, pwd):
        try:
            self.log(f"🔍 Processing {os.path.basename(stego_path)}...")
            file_ext = os.path.splitext(stego_path)[1].lower()
            
            if file_ext in ['.png', '.jpg', '.jpeg', '.bmp'] and CV2_AVAILABLE:
                self.log("🖼️ Extracting from image LSB...")
                raw_bytes = extract_payload_from_image(stego_path)
            elif file_ext in ['.txt', '.md']:
                self.log("📝 Extracting from text ZWC...")
                raw_bytes = extract_zwc_from_text(stego_path)
            elif file_ext == '.wav':
                self.log("🎵 Extracting from audio WAV...")
                raw_bytes = extract_payload_from_audio_wav(stego_path)
            elif file_ext == '.mp4' and CV2_AVAILABLE:
                self.log("🎥 Extracting from video MP4...")
                raw_bytes = extract_payload_from_video_mp4(stego_path)
            else:
                self.log("❌ Unsupported file type")
                return

            self.log(f"📦 Extracted {len(raw_bytes)} raw bytes")
            b64_str = raw_bytes.decode("ascii", errors="ignore").strip()
            enc_data = safe_base64_decode(b64_str)

            if enc_data:
                self.log("🔓 Decrypting...")
                decrypted = decrypt_bytes(pwd, enc_data)
                if decrypted.endswith(TERMINATOR):
                    original = decrypted[:-len(TERMINATOR)]
                    save_dir = self.recv_folder.get()
                    out_path = os.path.join(save_dir, "DECRYPTED_SECRET.bin")
                    with open(out_path, "wb") as f:
                        f.write(original)
                    self.log(f"✅ Decryption success: {out_path}")

                    try:
                        preview = original.decode("utf-8")
                        self._append_decoded("🎉 DECRYPTED MESSAGE:", preview[:500])
                    except:
                        preview = f"<binary data> ({len(original)} bytes)"
                        self._append_decoded("🎉 DECRYPTED FILE:", preview)
                    return
            self.log("❌ Wrong password or corrupted data")
        except Exception as e:
            self.log(f"❌ Decryption error: {e}")

if __name__ == "__main__":
    app = App()
    app.mainloop()


