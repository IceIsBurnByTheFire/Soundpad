"""
Soundboard v2  (Qt UI, Windows + macOS)
  Real mic + sound clips  ->  virtual cable   (Windows: VB-Audio "CABLE Input", Mac: BlackHole 2ch)
                              games/Discord use the other end (CABLE Output / BlackHole 2ch) as mic
  Sound clips             ->  your headphones (monitor, so you hear them too)
Global hotkeys work while in-game (CS2 etc).
The old Tk version is kept in legacy/soundboard_tk.py.
"""
import ctypes
import json
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

IS_MAC = sys.platform == "darwin"
if IS_MAC:
    from pynput import keyboard as pkb
else:
    import keyboard
from PySide6.QtCore import (Qt, QObject, Signal, QTimer, QRect, QRectF, QSize, QPoint, QPointF,
                            QMimeData, QEvent)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QDrag, QFont, QFontDatabase, QFontMetrics,
                           QIcon, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget, QGridLayout)

APP_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = APP_DIR / "sounds"
CONFIG_PATH = APP_DIR / "config.json"
SR = 48000          # internal sample rate
BLOCK = 256         # ~5 ms per audio callback
AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".aiff", ".aif"}

# The virtual cable: the app writes to SEND_DEVICE, games use GAME_MIC as their microphone.
if IS_MAC:
    CABLE_NAME, SEND_DEVICE, GAME_MIC = "BlackHole", "BlackHole 2ch", "BlackHole 2ch"
else:
    CABLE_NAME, SEND_DEVICE, GAME_MIC = "VB-Cable", "CABLE Input", "CABLE Output"

DEFAULT_CONFIG = {
    "mic": "Headset Microphone",
    "cable": SEND_DEVICE,
    "monitor": "Headset Earphone",
    "mic_gain": 1.0,
    "sound_gain": 0.8,
    "monitor_gain": 0.6,
    "mic_buffer_ms": 40,            # raise to 60-80 if your voice crackles
    "stop_hotkey": "ctrl+alt+0",
    "mic_toggle_hotkey": "ctrl+alt+m",
    "ptt_enabled": False,           # hold the game's push-to-talk key while a sound plays
    "ptt_key": "",
    "voice_effect": "none",         # see VOICE_EFFECTS
    "effect_enabled": True,
    "effect_hotkey": "",            # toggles the voice effect on/off
    "hear_self": False,             # play your own mic in your headphones
    "hear_self_hotkey": "",
    "sounds": [],                   # {"name", "file", "hotkey", "volume", "color", "mode"}
}

MODES = [("overlap", "Overlap", "Each press plays another copy"),
         ("restart", "Restart", "Each press starts it from the top"),
         ("toggle", "Play / stop", "Press again to stop"),
         ("loop", "Loop", "Loops until you press again")]

# ---------------------------------------------------------------- theme
BG, SIDE, SURFACE, SURFACE2, HOVER = "#0a0d13", "#0e1219", "#141924", "#1a2030", "#212839"
BORDER, BORDER_HI, TRACK, CHIP = "#232a3a", "#343d52", "#252c3d", "#1f2638"
TEXT, MUTED, DIM = "#e9edf5", "#8b94a8", "#5c6578"
ACCENT, ACCENT2 = "#7c5cff", "#22d3ee"
OK, WARN, DANGER = "#2ee6a6", "#fbbf24", "#ff4d6d"
PAD_COLORS = ["#8b5cf6", "#22d3ee", "#f472b6", "#fbbf24", "#34d399", "#fb7185", "#60a5fa", "#fb923c"]
COLOR_NAMES = ["Violet", "Cyan", "Pink", "Amber", "Mint", "Rose", "Blue", "Orange"]

# Segoe Fluent Icons (Win 11) / Segoe MDL2 Assets (Win 10) glyphs
G_ADD, G_SETTINGS, G_MIC, G_SEARCH = "", "", "", ""
G_PLAY, G_STOP, G_VOLUME, G_MUSIC = "", "", "", ""
G_HEADPHONE, G_LOOP, G_KEYBOARD, G_DELETE = "", "", "", ""
G_EDIT, G_FOLDER, G_GAME, G_GRID = "", "", "", ""
G_FULL, G_EXITFULL = "", ""
ICON_FONT = None                  # set in main(): a Segoe icon font, or None to draw icons
MONO_FONT = "Menlo" if IS_MAC else "Consolas"

QSS = """
* { font-family: @UIFONT; font-size: 13px; color: @TEXT; }
QMainWindow, QWidget#root, QWidget#page { background: @BG; }
QWidget#sidebar { background: @SIDE; border-right: 1px solid @BORDER; }
QLabel { background: transparent; }
QLabel#brand { font-size: 16px; font-weight: 700; }
QLabel#muted { color: @MUTED; }
QLabel#dim { color: @DIM; font-size: 11px; font-weight: 600; letter-spacing: 1px; }
QLabel#h1 { font-family: @DISPLAYFONT; font-size: 26px; font-weight: 700; }
QLabel#h2 { font-size: 15px; font-weight: 600; }
QLabel#value { color: @MUTED; font-family: @MONO; font-size: 12px; }
QLabel#chip { background: @CHIP; border: 1px solid @BORDER; border-radius: 6px; padding: 4px 9px;
              font-family: @MONO; font-size: 12px; }
QPushButton { background: @SURFACE2; border: 1px solid @BORDER; border-radius: 10px;
              padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: @HOVER; border-color: @BORDER_HI; }
QPushButton:pressed { background: @SURFACE; }
QPushButton#primary { border: none; color: white;
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @ACCENT, stop:1 #4f8dff); }
QPushButton#primary:hover {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8f73ff, stop:1 #64a0ff); }
QPushButton#danger { background: rgba(255,77,109,0.10); border: 1px solid rgba(255,77,109,0.35);
                     color: #ff8fa3; }
QPushButton#danger:hover { background: rgba(255,77,109,0.20); }
QPushButton#nav { background: transparent; border: none; text-align: left; padding: 10px 12px;
                  color: @MUTED; border-radius: 10px; }
QPushButton#nav:hover { background: @SURFACE; color: @TEXT; }
QPushButton#nav:checked { background: rgba(124,92,255,0.16); color: @TEXT; }
QPushButton#micBtn { min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px;
                     border-radius: 26px; padding: 0; background: rgba(46,230,166,0.12);
                     border: 1px solid rgba(46,230,166,0.45); }
QPushButton#micBtn:hover { background: rgba(46,230,166,0.20); }
QPushButton#micBtn:checked { background: rgba(255,77,109,0.14); border: 1px solid rgba(255,77,109,0.55); }
QPushButton#earBtn { min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px;
                     border-radius: 26px; padding: 0; background: @SURFACE; border: 1px solid @BORDER; }
QPushButton#earBtn:hover { background: @SURFACE2; border-color: @BORDER_HI; }
QPushButton#earBtn:checked { background: rgba(34,211,238,0.14); border: 1px solid rgba(34,211,238,0.55); }
QLineEdit, QSpinBox { background: @SURFACE; border: 1px solid @BORDER; border-radius: 10px;
                      padding: 8px 10px; selection-background-color: @ACCENT; }
QLineEdit:focus, QSpinBox:focus { border-color: @ACCENT; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }
QFrame#card { background: @SURFACE; border: 1px solid @BORDER; border-radius: 16px; }
QFrame#strip { background: @SURFACE; border: 1px solid @BORDER; border-radius: 14px; }
QFrame#mixer { background: @SIDE; border-top: 1px solid @BORDER; }
QFrame#statusCard { background: @SURFACE; border: 1px solid @BORDER; border-radius: 12px; }
QFrame#sep { background: @BORDER; max-height: 1px; min-height: 1px; border: none; }
QSlider { min-height: 18px; }
QSlider::groove:horizontal { height: 6px; background: @TRACK; border-radius: 3px; }
QSlider::sub-page:horizontal { border-radius: 3px;
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 @ACCENT, stop:1 @ACCENT2); }
QSlider::handle:horizontal { background: white; width: 14px; height: 14px; margin: -4px 0;
                             border-radius: 7px; }
QComboBox { background: @SURFACE2; border: 1px solid @BORDER; border-radius: 10px; padding: 7px 10px; }
QComboBox:hover { border-color: @BORDER_HI; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url("@ARROW"); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: @SURFACE2; border: 1px solid @BORDER_HI; outline: 0;
                              padding: 4px; selection-background-color: rgba(124,92,255,0.35); }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid @BORDER_HI;
                       background: @SURFACE2; }
QCheckBox::indicator:checked { background: @ACCENT; border-color: @ACCENT; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @BORDER_HI; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QMenu { background: @SURFACE2; border: 1px solid @BORDER_HI; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 28px 7px 12px; border-radius: 6px; }
QMenu::item:selected { background: rgba(124,92,255,0.28); }
QMenu::separator { height: 1px; background: @BORDER; margin: 5px 8px; }
QMenu::indicator { width: 14px; height: 14px; left: 6px; }
QPushButton#fxTile { background: @SURFACE; border: 1px solid @BORDER; border-radius: 16px; padding: 0; }
QPushButton#fxTile:hover { background: @SURFACE2; border-color: @BORDER_HI; }
QPushButton#fxTile:checked { background: rgba(124,92,255,0.16); border: 1px solid @ACCENT; }
QComboBox#fxBox { padding: 3px 10px; border-radius: 8px; }
QDialog, QMessageBox, QInputDialog { background: @SURFACE; }
QToolTip { background: @SURFACE2; color: @TEXT; border: 1px solid @BORDER_HI; padding: 6px; }
"""


def arrow_png():
    """Combo-box arrow; Qt stylesheets can only take an image file for it."""
    path = Path(tempfile.gettempdir()) / "soundboard_arrow.png"
    pm = QPixmap(36, 36)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(MUTED), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(8, 13), QPointF(18, 23), QPointF(28, 13)])
    p.end()
    pm.save(str(path))
    return path.as_posix()


def font_tokens():
    if IS_MAC:     # the macOS system font (San Francisco)
        ui = f'"{QApplication.font().family()}"'
        return dict(DISPLAYFONT=ui, UIFONT=ui, MONO=MONO_FONT)
    return dict(DISPLAYFONT='"Segoe UI Variable Display", "Segoe UI"',
                UIFONT='"Segoe UI Variable Text", "Segoe UI"', MONO=MONO_FONT)


def build_qss():
    tokens = dict(BG=BG, SIDE=SIDE, SURFACE2=SURFACE2, SURFACE=SURFACE, HOVER=HOVER,
                  BORDER_HI=BORDER_HI, BORDER=BORDER, TRACK=TRACK, CHIP=CHIP, TEXT=TEXT,
                  MUTED=MUTED, DIM=DIM, ACCENT2=ACCENT2, ACCENT=ACCENT, ARROW=arrow_png(), **font_tokens())
    s = QSS
    for k, v in tokens.items():          # longest names first so @SURFACE2 isn't eaten by @SURFACE
        s = s.replace("@" + k, v)
    return s


# ---------------------------------------------------------------- config
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as e:
            print("config.json unreadable, using defaults:", e)
    for i, s in enumerate(cfg["sounds"]):
        s.setdefault("hotkey", "")
        s.setdefault("volume", 1.0)
        s.setdefault("color", PAD_COLORS[i % len(PAD_COLORS)])
        s.setdefault("mode", "overlap")
    return cfg


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- devices
def wasapi_api():
    for i, h in enumerate(sd.query_hostapis()):
        if "WASAPI" in h["name"]:
            return i
    return None


def devices(kind):
    """List (index, name) for 'input' or 'output' devices (WASAPI only = low latency, full names)."""
    api = wasapi_api()
    res = []
    for i, d in enumerate(sd.query_devices()):
        if api is not None and d["hostapi"] != api:
            continue
        if d[f"max_{kind}_channels"] > 0:
            res.append((i, d["name"]))
    return res


def guess_device(kind):
    """The user's real default mic / speakers, skipping the virtual cable."""
    def real(i):
        if i is None or i < 0:
            return False
        name = sd.query_devices(i)["name"].lower()
        return "cable" not in name and "blackhole" not in name
    api = wasapi_api()
    try:
        i = (sd.query_hostapis(api)[f"default_{kind}_device"] if api is not None
             else sd.default.device[0 if kind == "input" else 1])
        if real(i):
            return i
    except Exception:
        pass
    return next((i for i, _ in devices(kind) if real(i)), None)


def reveal_file(path):
    if IS_MAC:
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["explorer", "/select,", str(path)])


def find_device(kind, name):
    if not name or name == "(none)":
        return None
    lst = devices(kind)
    for i, n in lst:
        if n == name:
            return i
    for i, n in lst:
        if name.lower() in n.lower():
            return i
    return None


# ---------------------------------------------------------------- audio
def resample(data, src, dst):
    n = int(round(len(data) * dst / src))
    x_old = np.linspace(0.0, 1.0, len(data), endpoint=False)
    x_new = np.linspace(0.0, 1.0, n, endpoint=False)
    return np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])],
                    axis=1).astype(np.float32)


def load_sound(path):
    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    if sr != SR:
        data = resample(data, sr, SR)
    return np.ascontiguousarray(data)


class Ring:
    """Small jitter buffer between the mic stream and the cable stream."""

    def __init__(self, cap, ch):
        self.buf = np.zeros((cap, ch), np.float32)
        self.cap, self.r, self.n = cap, 0, 0
        self.starving = True
        self.lock = threading.Lock()

    def write(self, x):
        with self.lock:
            k = len(x)
            if k >= self.cap:
                x, k = x[-self.cap:], self.cap
            over = self.n + k - self.cap
            if over > 0:
                self.r = (self.r + over) % self.cap
                self.n -= over
            w = (self.r + self.n) % self.cap
            first = min(k, self.cap - w)
            self.buf[w:w + first] = x[:first]
            self.buf[:k - first] = x[first:]
            self.n += k

    def read(self, k, target):
        out = np.zeros((k, self.buf.shape[1]), np.float32)
        with self.lock:
            if self.n > target * 2:                 # clock drift: drop to keep latency low
                drop = self.n - target
                self.r = (self.r + drop) % self.cap
                self.n -= drop
            if self.starving:
                if self.n < target:
                    return out
                self.starving = False
            m = min(k, self.n)
            if m < k:
                self.starving = True
            first = min(m, self.cap - self.r)
            out[:first] = self.buf[self.r:self.r + first]
            out[first:m] = self.buf[:m - first]
            self.r = (self.r + m) % self.cap
            self.n -= m
        return out


# ---------------------------------------------------------------- voice effects
# All effects run on the mic path, block by block, with numpy only (no extra deps).
class Feedback:
    """Feedback delay y[n] = x[n] + fb * y[n-D]. Returns y[n-D] (the echo) for each input sample."""

    def __init__(self, delay, fb):
        self.buf = np.zeros(delay, np.float32)
        self.d, self.fb, self.pos = delay, fb, 0

    def process(self, x):
        out = np.empty_like(x)
        for s in range(0, len(x), self.d):          # chunks <= D, so no sample needs its own output
            c = x[s:s + self.d]
            idx = (self.pos + np.arange(len(c))) % self.d
            old = self.buf[idx]
            self.buf[idx] = c + self.fb * old
            out[s:s + len(c)] = old
            self.pos = (self.pos + len(c)) % self.d
        return out


class FIR:
    """Streaming FIR filter (keeps the tail between blocks)."""

    def __init__(self, taps):
        self.h = taps.astype(np.float32)
        self.tail = np.zeros(len(taps) - 1, np.float32)

    def process(self, x):
        xx = np.concatenate([self.tail, x])
        self.tail = xx[len(xx) - len(self.tail):]
        return np.convolve(xx, self.h, mode="valid").astype(np.float32)


def bandpass_taps(lo, hi, n=511):
    t = np.arange(n) - (n - 1) / 2
    ideal = (2 * hi / SR) * np.sinc(2 * hi / SR * t) - (2 * lo / SR) * np.sinc(2 * lo / SR * t)
    return ideal * np.hamming(n)


class PitchShift:
    """Low-latency delay-line pitch shifter: two taps sweep through a ~40 ms window
    and crossfade, so the voice is re-read faster (higher) or slower (lower)."""
    SIZE = 8192

    def __init__(self, ratio, window_ms=40):
        self.buf = np.zeros(self.SIZE, np.float32)
        self.w = SR * window_ms / 1000
        self.step = (1.0 - ratio) / self.w        # phase change per sample
        self.phase, self.pos = 0.0, 0

    def process(self, x):
        k = len(x)
        widx = (self.pos + np.arange(k)) % self.SIZE
        self.buf[widx] = x
        n = self.pos + np.arange(k)
        ph = (self.phase + self.step * np.arange(1, k + 1)) % 1.0
        out = np.zeros(k, np.float32)
        for p in (ph, (ph + 0.5) % 1.0):
            r = n - 2.0 - p * self.w              # 2 samples of headroom for interpolation
            i0 = np.floor(r)
            f = (r - i0).astype(np.float32)
            i0 = i0.astype(np.int64) % self.SIZE
            s = self.buf[i0] * (1 - f) + self.buf[(i0 + 1) % self.SIZE] * f
            out += s * np.sin(np.pi * p).astype(np.float32) ** 2
        self.phase = float(ph[-1])
        self.pos = (self.pos + k) % self.SIZE
        return out


class Effect:
    """One voice preset. process() takes and returns a mono float32 block."""

    def __init__(self, kind):
        self.kind = kind
        self.t = 0                                 # sample clock for oscillators
        if kind == "chipmunk":
            self.ps = PitchShift(1.6)
        elif kind == "deep":
            self.ps = PitchShift(0.72)
        elif kind == "robot":
            self.comb = Feedback(int(SR * 0.006), 0.55)
        elif kind == "radio":
            self.bp = FIR(bandpass_taps(350, 3200))
        elif kind == "echo":
            self.fb = Feedback(int(SR * 0.28), 0.42)

    def process(self, x):
        k = self.kind
        if k in ("chipmunk", "deep"):
            return self.ps.process(x)
        if k == "robot":
            n = self.t + np.arange(len(x))
            self.t = (self.t + len(x)) % SR
            y = x * np.sin(2 * np.pi * 70 * n / SR).astype(np.float32) * 1.6
            return (y + 0.6 * self.comb.process(y)) * 0.8
        if k == "radio":
            y = self.bp.process(x) * 2.2
            return np.tanh(y * 2.5).astype(np.float32) * 0.5
        if k == "echo":
            return x + 0.55 * self.fb.process(x)
        return x


VOICE_EFFECTS = [("none", "None", "Your normal voice"),
                 ("chipmunk", "Chipmunk", "Pitch up"),
                 ("deep", "Deep", "Pitch down"),
                 ("robot", "Robot", "Metallic ring-mod voice"),
                 ("radio", "Radio", "Tinny walkie-talkie"),
                 ("echo", "Echo", "Big room delay")]


class Voice:
    __slots__ = ("name", "data", "gain", "loop", "pos")

    def __init__(self, name, data, gain, loop):
        self.name, self.data, self.gain, self.loop, self.pos = name, data, gain, loop, 0


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.voices = {"cable": [], "monitor": []}
        self.mic_ring = Ring(SR, 1)
        self.mic_gain = 1.0
        self.sound_gain = 0.8
        self.monitor_gain = 0.6
        self.mic_on = True
        self.target = int(SR * 0.04)
        self.streams = []
        self.peak = {"mic": 0.0, "out": 0.0}
        self.effect = None              # Effect, or None for a clean voice
        self.effect_on = True
        self.hear_self = False          # also send the (processed) mic to the monitor
        self.self_ring = Ring(SR, 1)

    def set_hear_self(self, on):
        if on and not self.hear_self:
            self.self_ring = Ring(SR, 1)    # drop stale audio from the last time
        self.hear_self = on

    def set_effect(self, kind):
        self.effect = Effect(kind) if kind and kind != "none" else None

    # called from hotkey thread / UI
    def play(self, name, data, gain, loop=False):
        if not len(data):
            return
        with self.lock:
            for key in self.voices:
                self.voices[key].append(Voice(name, data, gain, loop))

    def stop(self, name):
        with self.lock:
            for key in self.voices:
                self.voices[key] = [v for v in self.voices[key] if v.name != name]

    def stop_all(self):
        with self.lock:
            for key in self.voices:
                self.voices[key].clear()

    def playing_names(self):
        with self.lock:
            return {v.name for v in self.voices["cable"]}

    def progress(self, name):
        """(playing, fraction, seconds) of the newest copy of a sound on the cable stream."""
        with self.lock:
            for v in reversed(self.voices["cable"]):
                if v.name == name:
                    return True, v.pos / len(v.data), v.pos / SR
        return False, 0.0, 0.0

    def _mix(self, key, frames):
        out = np.zeros((frames, 2), np.float32)
        with self.lock:
            alive = []
            for v in self.voices[key]:
                n, i = len(v.data), 0
                while i < frames:
                    chunk = v.data[v.pos:v.pos + frames - i]
                    out[i:i + len(chunk)] += chunk * v.gain
                    i += len(chunk)
                    v.pos += len(chunk)
                    if v.pos >= n:
                        if not v.loop:
                            break
                        v.pos = 0
                if v.pos < n:
                    alive.append(v)
            self.voices[key] = alive
        return out

    # audio callbacks
    def _mic_cb(self, indata, frames, t, status):
        x = indata[:, :1]
        fx = self.effect
        if fx is not None and self.effect_on:
            try:
                x = fx.process(indata[:, 0].copy())[:, None]
            except Exception:
                traceback.print_exc()
                self.effect = None      # never let a broken effect kill the mic
        self.mic_ring.write(x)
        if self.hear_self:
            self.self_ring.write(x)

    def _cable_cb(self, outdata, frames, t, status):
        mix = self._mix("cable", frames) * self.sound_gain
        mic = self.mic_ring.read(frames, self.target)
        if self.mic_on:
            mic = mic * self.mic_gain
            mix += mic
            self.peak["mic"] = max(self.peak["mic"], float(np.abs(mic).max(initial=0)))
        np.clip(mix, -1.0, 1.0, out=outdata)
        self.peak["out"] = max(self.peak["out"], float(np.abs(outdata).max(initial=0)))

    def _mon_cb(self, outdata, frames, t, status):
        mix = self._mix("monitor", frames) * (self.sound_gain * self.monitor_gain)
        if self.hear_self:
            # smaller buffer than the cable path: you notice your own delay quickly
            mic = self.self_ring.read(frames, max(BLOCK * 3, self.target // 2))
            if self.mic_on:
                mix += mic * (self.mic_gain * self.monitor_gain)
        np.clip(mix, -1.0, 1.0, out=outdata)

    def take_peak(self, key):
        v, self.peak[key] = self.peak[key], 0.0
        return v

    def start(self, mic_i, cable_i, mon_i, buf_ms):
        self.close_streams()
        self.target = max(BLOCK, int(SR * buf_ms / 1000))
        self.mic_ring = Ring(SR, 1)
        self.self_ring = Ring(SR, 1)
        extra = None
        if wasapi_api() is not None:
            try:
                extra = sd.WasapiSettings(auto_convert=True)   # lets 48k work on any device rate
            except TypeError:
                extra = None
        common = dict(samplerate=SR, blocksize=BLOCK, dtype="float32",
                      latency="low", extra_settings=extra)
        try:
            if mic_i is not None:
                self.streams.append(sd.InputStream(device=mic_i, channels=1,
                                                   callback=self._mic_cb, **common))
            self.streams.append(sd.OutputStream(device=cable_i, channels=2,
                                                callback=self._cable_cb, **common))
            if mon_i is not None:
                self.streams.append(sd.OutputStream(device=mon_i, channels=2,
                                                    callback=self._mon_cb, **common))
            for s in self.streams:
                s.start()
        except Exception:
            self.close_streams()
            raise

    def close_streams(self):
        for s in self.streams:
            try:
                s.stop()
                s.close()
            except Exception:
                pass
        self.streams = []


# ---------------------------------------------------------------- global hotkeys
# Combos are stored as "ctrl+alt+1" on both systems. Callbacks run on the listener's thread.
class WinHotkeys:
    """Windows: the `keyboard` library."""
    trusted = True

    def __init__(self):
        self.handles = []

    def bind(self, pairs):
        self.clear()
        for hk, fn in pairs:
            try:
                self.handles.append(keyboard.add_hotkey(hk, fn))
            except (ValueError, KeyError) as e:
                print(f"Bad hotkey {hk!r}: {e}")

    def clear(self):
        # keyboard.unhook_all_hotkeys() crashes if no hotkey was ever added,
        # so remove only the ones we registered.
        for h in self.handles:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass
        self.handles = []

    def read_combo(self):
        return keyboard.read_hotkey(suppress=False)

    def press(self, key):
        keyboard.press(key)

    def release(self, key):
        keyboard.release(key)

    def shutdown(self):
        keyboard.unhook_all()


# macOS virtual key codes -> names (position-based, so Option+1 is still "1", not "¡")
MAC_VK = {0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g", 6: "z", 7: "x", 8: "c", 9: "v", 11: "b",
          12: "q", 13: "w", 14: "e", 15: "r", 16: "y", 17: "t", 18: "1", 19: "2", 20: "3", 21: "4",
          22: "6", 23: "5", 24: "=", 25: "9", 26: "7", 27: "-", 28: "8", 29: "0", 30: "]", 31: "o",
          32: "u", 33: "[", 34: "i", 35: "p", 37: "l", 38: "j", 39: "'", 40: "k", 41: ";", 42: "\\",
          43: ",", 44: "/", 45: "n", 46: "m", 47: ".", 50: "`", 65: "num .", 67: "num *",
          69: "num +", 75: "num /", 78: "num -", 81: "num =", 82: "num 0", 83: "num 1", 84: "num 2",
          85: "num 3", 86: "num 4", 87: "num 5", 88: "num 6", 89: "num 7", 91: "num 8", 92: "num 9"}
MODIFIERS = ["ctrl", "alt", "shift", "cmd"]
ALIASES = {"control": "ctrl", "option": "alt", "command": "cmd", "windows": "cmd",
           "left ctrl": "ctrl", "right ctrl": "ctrl", "left alt": "alt", "right alt": "alt",
           "left shift": "shift", "right shift": "shift"}


def combo_set(hk):
    return frozenset(ALIASES.get(k.strip().lower(), k.strip().lower()) for k in hk.split("+") if k.strip())


def combo_str(keys):
    mods = [m for m in MODIFIERS if m in keys]
    return "+".join(mods + sorted(k for k in keys if k not in MODIFIERS))


class MacHotkeys:
    """macOS: pynput. Needs Accessibility + Input Monitoring permission for the app running Python."""

    def __init__(self):
        self.combos = {}            # frozenset of key names -> fn
        self.down = set()
        self.fired = set()          # combos already fired during this press
        self.capturing = False
        self.cap_keys = set()
        self.cap_done = threading.Event()
        self.cap_result = ""
        self.ctl = pkb.Controller()
        self.listener = pkb.Listener(on_press=self._press, on_release=self._release)
        self.listener.daemon = True
        self.listener.start()
        self.trusted = getattr(self.listener, "IS_TRUSTED", True)

    @staticmethod
    def _name(key):
        if isinstance(key, pkb.Key):
            n = key.name
            for m in MODIFIERS:
                if n == m or n.startswith(m + "_"):
                    return m
            return {"alt_gr": "alt"}.get(n, n)
        vk = getattr(key, "vk", None)
        if vk in MAC_VK:
            return MAC_VK[vk]
        ch = getattr(key, "char", None)
        return ch.lower() if ch and ch.isprintable() else f"vk{vk}"

    def _press(self, key):
        k = self._name(key)
        self.down.add(k)
        if self.capturing:
            self.cap_keys.add(k)
            return
        cur = frozenset(self.down)
        fn = self.combos.get(cur)
        if fn and cur not in self.fired:
            self.fired.add(cur)
            try:
                fn()
            except Exception:
                traceback.print_exc()

    def _release(self, key):
        self.down.discard(self._name(key))
        self.fired = {c for c in self.fired if c <= self.down}
        if self.capturing and not self.down and self.cap_keys:
            self.capturing = False
            self.cap_result = combo_str(self.cap_keys)
            self.cap_done.set()

    def bind(self, pairs):
        self.combos = {combo_set(hk): fn for hk, fn in pairs if hk}

    def clear(self):
        self.combos = {}

    def read_combo(self):
        self.cap_keys, self.cap_done = set(), threading.Event()
        self.capturing = True
        self.cap_done.wait()
        return self.cap_result

    def _key(self, name):
        name = ALIASES.get(name, name)
        if len(name) == 1:
            return pkb.KeyCode.from_char(name)
        return getattr(pkb.Key, name, None) or pkb.KeyCode.from_char(name[-1])

    def press(self, key):
        self.ctl.press(self._key(key))

    def release(self, key):
        self.ctl.release(self._key(key))

    def shutdown(self):
        self.listener.stop()


def make_hotkeys():
    return MacHotkeys() if IS_MAC else WinHotkeys()


# ---------------------------------------------------------------- small UI helpers
def _vector_glyph(p, ch, color):
    """Line icons on a 24x24 grid, for systems without the Segoe icon fonts (macOS)."""
    P = QPointF
    pen = QPen(QColor(color), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if ch == G_ADD:
        p.drawLine(P(12, 5), P(12, 19))
        p.drawLine(P(5, 12), P(19, 12))
    elif ch == G_SETTINGS:
        p.drawEllipse(P(12, 12), 3, 3)
        p.drawEllipse(P(12, 12), 7, 7)
        for i in range(8):
            a = i * math.pi / 4
            p.drawLine(P(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                       P(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)))
    elif ch == G_MIC:
        p.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        p.drawArc(QRectF(5, 4, 14, 13), 180 * 16, 180 * 16)
        p.drawLine(P(12, 17), P(12, 21))
        p.drawLine(P(8.5, 21), P(15.5, 21))
    elif ch == G_SEARCH:
        p.drawEllipse(P(11, 11), 6, 6)
        p.drawLine(P(15.5, 15.5), P(20, 20))
    elif ch == G_PLAY:
        p.drawPolygon([P(8, 5), P(19, 12), P(8, 19)])
    elif ch == G_STOP:
        p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif ch == G_VOLUME:
        p.drawPolygon([P(4, 9.5), P(8, 9.5), P(12, 5.5), P(12, 18.5), P(8, 14.5), P(4, 14.5)])
        p.drawArc(QRectF(10, 8, 8, 8), -60 * 16, 120 * 16)
        p.drawArc(QRectF(8, 5, 14, 14), -60 * 16, 120 * 16)
    elif ch == G_MUSIC:
        p.drawEllipse(P(7, 17), 2.5, 2.5)
        p.drawEllipse(P(17, 15), 2.5, 2.5)
        p.drawPolyline([P(9.5, 17), P(9.5, 6), P(19.5, 4), P(19.5, 15)])
    elif ch == G_HEADPHONE:
        p.drawArc(QRectF(4, 4, 16, 16), 0, 180 * 16)
        p.drawRoundedRect(QRectF(3, 12, 4, 7), 1.5, 1.5)
        p.drawRoundedRect(QRectF(17, 12, 4, 7), 1.5, 1.5)
    elif ch == G_LOOP:
        p.drawArc(QRectF(5, 6, 14, 12), 50 * 16, 290 * 16)
        p.drawPolyline([P(14, 4), P(16.5, 7.4), P(13, 9)])
    elif ch == G_KEYBOARD:
        p.drawRoundedRect(QRectF(3, 6, 18, 12), 2, 2)
        for x in (7, 10, 13, 16):
            p.drawPoint(P(x, 10))
        p.drawLine(P(8, 14), P(16, 14))
    elif ch == G_DELETE:
        p.drawLine(P(4, 7), P(20, 7))
        p.drawLine(P(10, 4), P(14, 4))
        p.drawPolyline([P(6, 7), P(7, 20), P(17, 20), P(18, 7)])
    elif ch == G_EDIT:
        p.drawPolygon([P(15, 4), P(20, 9), P(9, 20), P(4, 20), P(4, 15)])
    elif ch == G_FOLDER:
        p.drawPolygon([P(3, 6), P(10, 6), P(12, 8.5), P(21, 8.5), P(21, 19), P(3, 19)])
    elif ch == G_GAME:
        p.drawRoundedRect(QRectF(2.5, 7.5, 19, 10), 5, 5)
        p.drawLine(P(6.5, 12.5), P(10.5, 12.5))
        p.drawLine(P(8.5, 10.5), P(8.5, 14.5))
        p.drawPoint(P(15, 11.5))
        p.drawPoint(P(17.5, 14))
    elif ch == G_FULL:              # corners pointing out
        for pts in (((4, 9), (4, 4), (9, 4)), ((15, 4), (20, 4), (20, 9)),
                    ((4, 15), (4, 20), (9, 20)), ((15, 20), (20, 20), (20, 15))):
            p.drawPolyline([P(*q) for q in pts])
    elif ch == G_EXITFULL:          # corners pointing in
        for pts in (((4, 9), (9, 9), (9, 4)), ((15, 4), (15, 9), (20, 9)),
                    ((4, 15), (9, 15), (9, 20)), ((15, 20), (15, 15), (20, 15))):
            p.drawPolyline([P(*q) for q in pts])
    elif ch == G_GRID:
        for x, y in ((3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)):
            p.drawRoundedRect(QRectF(x, y, 7, 7), 1.5, 1.5)


def draw_glyph(p, ch, rect, color):
    """Draws an icon into rect: Segoe icon font on Windows, drawn lines elsewhere."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    if ICON_FONT:
        f = QFont(ICON_FONT)
        f.setPixelSize(max(1, int(rect.height() * 0.85)))
        p.setFont(f)
        p.setPen(QColor(color))
        p.drawText(rect, Qt.AlignCenter, ch)
    else:
        s = min(rect.width(), rect.height()) / 24
        p.translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s)
        p.scale(s, s)
        _vector_glyph(p, ch, color)
    p.restore()


def glyph_icon(ch, color=TEXT, size=16):
    pm = QPixmap(size * 3, size * 3)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.TextAntialiasing)
    m = size * 3 * 0.06
    draw_glyph(p, ch, QRectF(pm.rect()).adjusted(m, m, -m, -m), color)
    p.end()
    pm.setDevicePixelRatio(3)
    return QIcon(pm)


def dot_icon(color, size=14):
    pm = QPixmap(size * 3, size * 3)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(3, 3, size * 3 - 6, size * 3 - 6))
    p.end()
    pm.setDevicePixelRatio(3)
    return QIcon(pm)


def app_icon():
    pm = QPixmap(256, 256)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 256, 256)
    g.setColorAt(0, QColor(ACCENT))
    g.setColorAt(1, QColor(ACCENT2))
    path = QPainterPath()
    path.addRoundedRect(QRectF(8, 8, 240, 240), 64, 64)
    p.fillPath(path, g)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("white"))
    for i, h in enumerate([70, 130, 170, 110, 60]):        # equalizer bars
        x = 52 + i * 34
        p.drawRoundedRect(QRectF(x, 128 - h / 2, 18, h), 9, 9)
    p.end()
    return QIcon(pm)


def pretty_hotkey(hk):
    if not hk:
        return ""
    return " + ".join(k.upper() if len(k) == 1 else k.title() for k in hk.split("+"))


def two_lines(text, fm, width):
    """Word-wrap into at most two lines, eliding the second."""
    if fm.horizontalAdvance(text) <= width:
        return text
    words, first = text.split(" "), ""
    while words and fm.horizontalAdvance((first + " " + words[0]).strip()) <= width:
        first = (first + " " + words.pop(0)).strip()
    if not first:                                     # one very long word
        return fm.elidedText(text, Qt.ElideRight, width)
    return first + "\n" + fm.elidedText(" ".join(words), Qt.ElideRight, width)


def fmt_time(sec):
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def label(text, obj=None):
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    return lb


def card(title=None, subtitle=None):
    fr = QFrame()
    fr.setObjectName("card")
    lay = QVBoxLayout(fr)
    lay.setContentsMargins(22, 20, 22, 22)
    lay.setSpacing(12)
    if title:
        lay.addWidget(label(title, "h2"))
    if subtitle:
        sub = label(subtitle, "muted")
        sub.setWordWrap(True)
        lay.addWidget(sub)
    return fr, lay


def set_dark_titlebar(widget):
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)    # dark mode
        c = QColor(SIDE)
        colorref = ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), 4)          # caption color (Win 11)
    except Exception:
        pass


class Bridge(QObject):
    """Runs functions on the UI thread (hotkeys fire on keyboard's own thread)."""
    call = Signal(object)


class FlowGrid(QLayout):
    """Responsive grid of equal pads.
    Normal: as many columns as fit, fixed row height.
    Fit (Soundboard mode, fit_h set): pads grow to fill the screen; too many -> big pads that scroll."""

    def __init__(self, min_w=210, row_h=150, spacing=14):
        super().__init__()
        self.items, self.min_w, self.row_h, self.sp = [], min_w, row_h, spacing
        self.fit_h = 0              # available height in fit mode, 0 = normal mode
        self.slots = []             # (items index, QRect) from the last layout, for drag & drop

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._layout(QRect(0, 0, w, 0), dry=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._layout(rect)

    def sizeHint(self):
        return QSize(self.min_w, self.row_h)

    def minimumSize(self):
        return QSize(self.min_w, self.row_h)

    def _metrics(self, w, n):
        """(columns, pad width, pad height)."""
        sp = self.sp
        if self.fit_h and n:
            best = None
            for cols in range(1, n + 1):
                rows = math.ceil(n / cols)
                cw = (w - sp * (cols - 1)) / cols
                rh = min((self.fit_h - sp * (rows - 1)) / rows, cw / 1.1, 460)
                cw = min(cw, rh * 2.4)                     # not ribbon-wide
                score = cw * rh
                if best is None or score > best[0]:
                    best = (score, cols, cw, rh)
            _, cols, cw, rh = best
            if rh >= 170 and cw >= 230:                    # everything fits on one screen
                return cols, cw, rh
            cols = max(1, int((w + sp) // (250 + sp)))       # too many: big pads + scrolling
            return cols, (w - sp * (cols - 1)) / cols, 175
        cols = max(1, int((w + sp) // (self.min_w + sp)))
        return cols, (w - sp * (cols - 1)) / cols, self.row_h

    def _layout(self, rect, dry=False):
        vis = [i for i, it in enumerate(self.items) if it.widget() and not it.widget().isHidden()]
        w = max(rect.width(), self.min_w)
        cols, cw, rh = self._metrics(w, len(vis))
        used = min(cols, len(vis)) * cw + self.sp * (min(cols, len(vis)) - 1)
        x0 = rect.x() + max(0, (w - used) / 2) if self.fit_h else rect.x()   # center in fit mode
        rows = math.ceil(len(vis) / cols) if vis else 0
        total = rows * rh + max(0, rows - 1) * self.sp
        y0 = rect.y() + max(0, (self.fit_h - total) / 2) if self.fit_h else rect.y()
        if not dry:
            self.slots = []
            for n, i in enumerate(vis):
                r, c = divmod(n, cols)
                g = QRect(int(x0 + c * (cw + self.sp)), int(y0 + r * (rh + self.sp)), int(cw), int(rh))
                self.items[i].setGeometry(g)
                self.slots.append((i, g))
        return int(total + (y0 - rect.y()))

    def index_at(self, pos):
        """Index in self.items of the slot under (or nearest to) pos."""
        if not self.slots:
            return None
        for i, g in self.slots:
            if g.contains(pos):
                return i
        return min(self.slots, key=lambda s: (QPointF(s[1].center()) - QPointF(pos)).manhattanLength())[0]

    def move(self, src, dst):
        if src != dst:
            self.items.insert(dst, self.items.pop(src))
            self.invalidate()


class DropGrid(QWidget):
    """The widget holding the pads: reorders them while one is dragged over it."""
    MIME = "application/x-soundpad-pad"

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            e.ignore()          # files: let the main window take them

    def dragMoveEvent(self, e):
        if e.mimeData().hasFormat(self.MIME):
            name = bytes(e.mimeData().data(self.MIME)).decode()
            self.win.move_pad(name, e.position().toPoint())
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        if e.mimeData().hasFormat(self.MIME):
            e.acceptProposedAction()
        else:
            e.ignore()


# ---------------------------------------------------------------- widgets
class Pad(QWidget):
    clicked = Signal(str)
    menu = Signal(str, QPoint)

    def __init__(self, win, entry):
        super().__init__()
        self.win, self.entry = win, entry
        self.hover = self.down = self.dragging = False
        self.press_pos = QPoint()
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover)
        dur = len(win.sounds[entry["name"]]) / SR if entry["name"] in win.sounds else 0
        self.duration = dur
        mode = dict((m, t) for m, t, _ in MODES)[entry.get("mode", "overlap")]
        self.setToolTip(f"{entry['name']}\nMode: {mode}   Volume: {int(entry['volume'] * 100)}%\n"
                        "Click to play  ·  Right-click to edit  ·  Drag to move")

    @property
    def name(self):
        return self.entry["name"]

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = self.down = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.down = True
            self.press_pos = e.position().toPoint()
            self.update()

    def mouseMoveEvent(self, e):
        if self.down and (e.position().toPoint() - self.press_pos).manhattanLength()                 >= QApplication.startDragDistance():
            self.down = False               # it's a drag, not a click
            self.win.drag_pad(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.down:
            self.down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self.clicked.emit(self.name)

    def contextMenuEvent(self, e):
        self.menu.emit(self.name, e.globalPos())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # Drawn at the normal pad size (about 260x150), then scaled up for big pads,
        # so text, icon and chip all grow together.
        k = max(1.0, min(self.height() / 150, self.width() / 260))
        p.scale(k, k)
        r = QRectF(0, 0, self.width() / k, self.height() / k).adjusted(1, 1, -1, -1)
        if self.dragging:                   # the empty slot it will drop into
            path = QPainterPath()
            path.addRoundedRect(r, 16, 16)
            p.setPen(QPen(QColor(ACCENT), 1.5, Qt.DashLine))
            p.fillPath(path, QColor(124, 92, 255, 20))
            p.drawPath(path)
            p.end()
            return
        if self.down:
            r = r.adjusted(2, 2, -2, -2)
        col = QColor(self.entry.get("color", ACCENT))
        playing, frac, secs = self.win.engine.progress(self.name)
        missing = self.name not in self.win.sounds

        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.fillPath(path, QColor(SURFACE2 if self.hover else SURFACE))
        # soft color wash: always a hint, strong while playing
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        c1, c2 = QColor(col), QColor(col)
        c1.setAlpha(70 if playing else 22)
        c2.setAlpha(12 if playing else 0)
        g.setColorAt(0, c1)
        g.setColorAt(0.7, c2)
        p.fillPath(path, g)
        border = QColor(col) if playing else QColor(BORDER_HI if self.hover else BORDER)
        p.setPen(QPen(border, 1.6 if playing else 1))
        p.drawPath(path)

        # icon tile
        tile = QRectF(r.left() + 14, r.top() + 14, 38, 38)
        tc = QColor(col)
        tc.setAlpha(255 if playing else 46)
        tp = QPainterPath()
        tp.addRoundedRect(tile, 11, 11)
        p.fillPath(tp, tc)
        mode = self.entry.get("mode", "overlap")
        glyph = G_STOP if playing else (G_LOOP if mode == "loop" else G_PLAY)
        draw_glyph(p, glyph, QRectF(tile.center().x() - 9.5, tile.center().y() - 9.5, 19, 19),
                   QColor(BG) if playing else col)

        # top-right tags
        small = QFont(self.font())
        small.setPixelSize(10)
        small.setWeight(QFont.DemiBold)
        small.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        tags = []
        if mode != "overlap":
            tags.append(dict((m, t) for m, t, _ in MODES)[mode].upper())
        if abs(self.entry["volume"] - 1.0) > 0.001:
            tags.append(f"{int(self.entry['volume'] * 100)}%")
        if tags:
            p.setFont(small)
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(tile.right() + 8, r.top() + 14, r.right() - 14 - tile.right() - 8, 16),
                       Qt.AlignRight | Qt.AlignVCenter, "  ·  ".join(tags))

        # name
        nf = QFont(self.font())
        nf.setPixelSize(14)
        nf.setWeight(QFont.DemiBold)
        p.setFont(nf)
        p.setPen(QColor(MUTED if missing else TEXT))
        nr = QRectF(r.left() + 14, tile.bottom() + 8, r.width() - 28, 38)
        p.drawText(nr, Qt.AlignLeft | Qt.AlignTop, two_lines(self.name, QFontMetrics(nf), int(nr.width())))

        # bottom row: hotkey chip + time
        y = r.bottom() - 14 - 20
        cf = QFont(MONO_FONT)
        cf.setPixelSize(11)
        fm = QFontMetrics(cf)
        hk = pretty_hotkey(self.entry.get("hotkey"))
        if missing:
            p.setFont(small)
            p.setPen(QColor(DANGER))
            p.drawText(QRectF(r.left() + 14, y, 140, 20), Qt.AlignLeft | Qt.AlignVCenter, "FILE MISSING")
        elif hk:
            w = min(fm.horizontalAdvance(hk) + 16, r.width() - 90)
            chip = QRectF(r.left() + 14, y, w, 20)
            cp = QPainterPath()
            cp.addRoundedRect(chip, 6, 6)
            p.fillPath(cp, QColor(0, 0, 0, 90))
            p.setPen(QPen(QColor(BORDER_HI), 1))
            p.drawPath(cp)
            p.setFont(cf)
            p.setPen(QColor(TEXT))
            p.drawText(chip, Qt.AlignCenter, fm.elidedText(hk, Qt.ElideRight, int(w - 10)))
        else:
            p.setFont(small)
            p.setPen(QColor(DIM))
            p.drawText(QRectF(r.left() + 14, y, 140, 20), Qt.AlignLeft | Qt.AlignVCenter, "NO HOTKEY")
        p.setFont(cf)
        p.setPen(QColor(TEXT if playing else MUTED))
        t = f"{fmt_time(secs)} / {fmt_time(self.duration)}" if playing else fmt_time(self.duration)
        p.drawText(QRectF(r.right() - 110, y, 96, 20), Qt.AlignRight | Qt.AlignVCenter, t)

        # progress bar
        if playing:
            track = QRectF(r.left() + 14, r.bottom() - 8, r.width() - 28, 3)
            p.fillRect(track, QColor(255, 255, 255, 18))
            bar = QRectF(track.left(), track.top(), track.width() * frac, track.height())
            bg = QLinearGradient(bar.topLeft(), bar.topRight())
            bg.setColorAt(0, col.darker(120))
            bg.setColorAt(1, col.lighter(140))
            p.fillRect(bar, bg)
        p.end()


class Meter(QWidget):
    """Horizontal peak meter, -60..0 dB."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(6)
        self.v = 0.0

    def push(self, peak):
        db = 20 * math.log10(max(peak, 1e-6))
        target = min(1.0, max(0.0, (db + 60) / 60))
        self.v = target if target > self.v else self.v * 0.88
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TRACK))
        p.drawRoundedRect(r, 3, 3)
        if self.v > 0.005:
            g = QLinearGradient(r.topLeft(), r.topRight())
            g.setColorAt(0, QColor(OK))
            g.setColorAt(0.7, QColor(OK))
            g.setColorAt(0.85, QColor(WARN))
            g.setColorAt(1, QColor(DANGER))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(r.left(), r.top(), r.width() * self.v, r.height()), 3, 3)
        p.end()


class Strip(QFrame):
    """A mixer channel: icon, title, % value, slider and (optional) level meter."""
    changed = Signal(float)

    def __init__(self, glyph, title, value=None, meter=False):
        super().__init__()
        self.setObjectName("strip")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(7)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(glyph_icon(glyph, MUTED, 14).pixmap(14, 14))
        top.addWidget(ic)
        top.addWidget(label(title.upper(), "dim"))
        top.addStretch()
        self.val = label("", "value")
        top.addWidget(self.val)
        lay.addLayout(top)
        self.slider = None
        if value is not None:
            self.slider = QSlider(Qt.Horizontal)
            self.slider.setRange(0, 200)
            self.slider.setValue(int(value * 100))
            self.slider.valueChanged.connect(self._moved)
            lay.addWidget(self.slider)
            self._moved(self.slider.value())
        else:
            lay.addSpacing(18)              # keep every strip the same height
        self.meter = Meter() if meter else None
        if self.meter:
            lay.addWidget(self.meter)
        else:
            lay.addSpacing(6)

    def _moved(self, v):
        self.val.setText(f"{v}%")
        self.changed.emit(v / 100)


class CaptureDialog(QDialog):
    """Waits for the next key combo anywhere on the system. Esc cancels."""
    got = Signal(str)

    def __init__(self, parent, what):
        super().__init__(parent, Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.result_hk = None
        fr = QFrame(self)
        fr.setObjectName("card")
        fr.setStyleSheet(f"QFrame#card {{ border: 1px solid {ACCENT}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(fr)
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(36, 28, 36, 28)
        lay.setSpacing(8)
        ic = QLabel()
        ic.setPixmap(glyph_icon(G_KEYBOARD, ACCENT2, 34).pixmap(34, 34))
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        h = label("Press a key combo", "h2")
        h.setAlignment(Qt.AlignCenter)
        lay.addWidget(h)
        s = label(f"for {what}\nEsc to cancel", "muted")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(s)
        self.got.connect(self._done)
        threading.Thread(target=lambda: self.got.emit(parent.hk.read_combo()), daemon=True).start()

    def _done(self, hk):
        self.result_hk = None if hk == "esc" else hk
        self.accept()

    def keyPressEvent(self, e):      # the global listener handles keys, incl. Esc
        e.accept()

    def reject(self):
        pass


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Soundboard")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(1000, 620)
        self.setAcceptDrops(True)
        self.cfg = load_config()
        self.engine = Engine()
        self.engine.mic_gain = self.cfg["mic_gain"]
        self.engine.sound_gain = self.cfg["sound_gain"]
        self.engine.monitor_gain = self.cfg["monitor_gain"]
        self.engine.set_hear_self(bool(self.cfg["hear_self"]))
        if self.cfg["voice_effect"] not in [k for k, _, _ in VOICE_EFFECTS]:
            self.cfg["voice_effect"] = "none"
        self.engine.set_effect(self.cfg["voice_effect"])
        self.engine.effect_on = bool(self.cfg["effect_enabled"])
        self.glob_chips = {}
        self.fx_tiles = {}
        self.sounds = {}
        self.pads = {}
        self.hk = make_hotkeys()
        self._was_playing = set()
        self.ptt_down = False
        self.ptt_last = 0.0
        self.bridge = Bridge()
        self.bridge.call.connect(lambda fn: fn())
        SOUNDS_DIR.mkdir(exist_ok=True)

        self.board_mode = False
        self._build()
        QShortcut(QKeySequence(Qt.Key_F11), self, self.toggle_board_mode)
        QShortcut(QKeySequence(Qt.Key_Escape), self,
                  lambda: self.board_mode and self.toggle_board_mode())
        self._load_sounds()
        self._rebuild_pads()
        self._bind_hotkeys()
        self.start_audio()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    # ---------- layout
    def _build(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.sidebar = self._build_sidebar()
        h.addWidget(self.sidebar)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_board())
        self.stack.addWidget(self._build_effects())
        self.stack.addWidget(self._build_settings())
        rv.addWidget(self.stack, 1)
        self.mixer = self._build_mixer()
        rv.addWidget(self.mixer)
        h.addWidget(right, 1)

    def _build_sidebar(self):
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(232)
        v = QVBoxLayout(sb)
        v.setContentsMargins(16, 22, 16, 18)
        v.setSpacing(4)

        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(38, 38))
        brand.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bt.addWidget(label("Soundboard", "brand"))
        sub = label("Virtual mic mixer", "muted")
        sub.setStyleSheet("font-size: 11px;")
        bt.addWidget(sub)
        brand.addLayout(bt)
        brand.addStretch()
        v.addLayout(brand)
        v.addSpacing(26)
        v.addWidget(label("  MENU", "dim"))
        v.addSpacing(4)

        self.nav = []
        for i, (glyph, text) in enumerate([(G_GRID, "Sound board"), (G_MIC, "Voice effects"),
                                              (G_SETTINGS, "Settings")]):
            b = QPushButton("   " + text)
            b.setObjectName("nav")
            b.setIcon(glyph_icon(glyph, TEXT, 16))
            b.setIconSize(QSize(16, 16))
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, i=i: self._go(i))
            v.addWidget(b)
            self.nav.append(b)
        self.nav[0].setChecked(True)

        v.addStretch()
        v.addWidget(label("  GLOBAL KEYS", "dim"))
        v.addSpacing(4)
        self.side_keys = QLabel()
        self.side_keys.setObjectName("muted")
        self.side_keys.setStyleSheet("padding-left: 6px; font-size: 12px;")
        v.addWidget(self.side_keys)
        v.addSpacing(14)

        st = QFrame()
        st.setObjectName("statusCard")
        sl = QVBoxLayout(st)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(4)
        row = QHBoxLayout()
        self.status_dot = QLabel("●")
        row.addWidget(self.status_dot)
        self.status_title = label("Starting…")
        self.status_title.setStyleSheet("font-weight: 600;")
        row.addWidget(self.status_title)
        row.addStretch()
        sl.addLayout(row)
        self.status_text = label("", "muted")
        self.status_text.setWordWrap(True)
        self.status_text.setStyleSheet("font-size: 11px;")
        sl.addWidget(self.status_text)
        v.addWidget(st)
        self._update_side_keys()
        return sb

    def _build_board(self):
        page = QWidget()
        page.setObjectName("page")
        v = QVBoxLayout(page)
        v.setContentsMargins(32, 28, 32, 16)
        v.setSpacing(18)
        self.board_layout = v

        self.board_head = QWidget()
        head = QHBoxLayout(self.board_head)
        head.setContentsMargins(0, 0, 0, 0)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(label("Sound board", "h1"))
        self.subtitle = label("", "muted")
        tv.addWidget(self.subtitle)
        head.addLayout(tv)
        head.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sounds…")
        self.search.addAction(glyph_icon(G_SEARCH, MUTED, 14), QLineEdit.LeadingPosition)
        self.search.setMinimumWidth(150)
        self.search.setMaximumWidth(250)
        self.search.textChanged.connect(self._filter)
        head.addWidget(self.search)
        full = self.full_btn = QPushButton("  Soundboard mode")
        full.setIcon(glyph_icon(G_FULL, TEXT, 14))
        full.setCursor(Qt.PointingHandCursor)
        full.setToolTip("Full-screen pads only (F11)")
        full.clicked.connect(self.toggle_board_mode)
        head.addWidget(full)
        add = QPushButton("  Add sounds")
        add.setObjectName("primary")
        add.setIcon(glyph_icon(G_ADD, "white", 14))
        add.setCursor(Qt.PointingHandCursor)
        add.clicked.connect(self.add_sounds)
        head.addWidget(add)
        stop = QPushButton("  Stop all")
        stop.setObjectName("danger")
        stop.setIcon(glyph_icon(G_STOP, "#ff8fa3", 14))
        stop.setCursor(Qt.PointingHandCursor)
        stop.clicked.connect(self.engine.stop_all)
        head.addWidget(stop)
        v.addWidget(self.board_head)
        v.addWidget(self._build_mode_bar())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 4, 6, 4)
        self.grid_host = DropGrid(self)
        self.grid = FlowGrid()
        self.grid_host.setLayout(self.grid)
        hv.addWidget(self.grid_host)
        self.empty = self._build_empty()
        hv.addWidget(self.empty)
        hv.addStretch()
        self.scroll.setWidget(holder)
        self.scroll.viewport().installEventFilter(self)     # refit pads when the window resizes
        v.addWidget(self.scroll, 1)
        return page

    def _build_mode_bar(self):
        """Slim bar shown only in Soundboard mode."""
        self.mode_bar = QWidget()
        h = QHBoxLayout(self.mode_bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(26, 26))
        h.addWidget(logo)
        h.addWidget(label("SOUNDBOARD MODE", "dim"))
        h.addStretch()
        h.addWidget(label("Drag pads to rearrange  ·  Esc to exit", "muted"))
        h.addSpacing(8)
        stop = QPushButton("  Stop all")
        stop.setObjectName("danger")
        stop.setIcon(glyph_icon(G_STOP, "#ff8fa3", 14))
        stop.setCursor(Qt.PointingHandCursor)
        stop.clicked.connect(self.engine.stop_all)
        h.addWidget(stop)
        ex = QPushButton("  Exit")
        ex.setIcon(glyph_icon(G_EXITFULL, TEXT, 14))
        ex.setCursor(Qt.PointingHandCursor)
        ex.clicked.connect(self.toggle_board_mode)
        h.addWidget(ex)
        self.mode_bar.hide()
        return self.mode_bar

    def _build_empty(self):
        fr = QFrame()
        fr.setStyleSheet(f"QFrame {{ border: 2px dashed {BORDER_HI}; border-radius: 18px; }}"
                         "QLabel { border: none; }")
        fr.setMinimumHeight(260)
        v = QVBoxLayout(fr)
        v.setAlignment(Qt.AlignCenter)
        ic = QLabel()
        ic.setPixmap(glyph_icon(G_MUSIC, ACCENT, 40).pixmap(40, 40))
        ic.setAlignment(Qt.AlignCenter)
        v.addWidget(ic)
        t = label("Drop audio files here", "h2")
        t.setAlignment(Qt.AlignCenter)
        v.addWidget(t)
        s = label("or click Add sounds  ·  wav, mp3, ogg, flac", "muted")
        s.setAlignment(Qt.AlignCenter)
        v.addWidget(s)
        return fr

    def _build_settings(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        outer.addWidget(sc)
        body = QWidget()
        sc.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(18)
        v.addWidget(label("Settings", "h1"))

        # devices
        fr, lay = card("Audio devices", "Your clips and your real mic are mixed into the virtual "
                                        f"cable. In the game, the mic is {GAME_MIC}.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.dev_boxes = {}
        rows = [("mic", G_MIC, "Real mic", "input"),
                ("cable", G_GAME, "Send to (virtual cable)", "output"),
                ("monitor", G_HEADPHONE, "Monitor (your ears)", "output")]
        for r, (key, glyph, text, kind) in enumerate(rows):
            ic = QLabel()
            ic.setPixmap(glyph_icon(glyph, MUTED, 16).pixmap(16, 16))
            grid.addWidget(ic, r, 0)
            grid.addWidget(label(text), r, 1)
            box = QComboBox()
            names = [n for _, n in devices(kind)]
            if key != "cable":
                names = ["(none)"] + names
            box.addItems(names)
            idx = find_device(kind, self.cfg[key])
            if idx is None and key != "cable" and self.cfg[key] != "(none)":
                idx = guess_device(kind)        # first run, or the saved device is gone
            box.setCurrentText(sd.query_devices(idx)["name"] if idx is not None else "(none)")
            box.setMinimumWidth(380)
            grid.addWidget(box, r, 2)
            self.dev_boxes[key] = box
        grid.setColumnStretch(2, 1)
        ic = QLabel()
        ic.setPixmap(glyph_icon(G_SETTINGS, MUTED, 16).pixmap(16, 16))
        grid.addWidget(ic, 3, 0)
        grid.addWidget(label("Mic buffer"), 3, 1)
        brow = QHBoxLayout()
        brow.setSpacing(12)
        self.buf_spin = QSpinBox()
        self.buf_spin.setRange(10, 200)
        self.buf_spin.setSuffix(" ms")
        self.buf_spin.setValue(int(self.cfg["mic_buffer_ms"]))
        self.buf_spin.setFixedWidth(100)
        brow.addWidget(self.buf_spin)
        brow.addWidget(label("Raise to 60–80 if your voice crackles.", "muted"))
        brow.addStretch()
        grid.addLayout(brow, 3, 2)
        lay.addLayout(grid)
        apply = QPushButton("  Apply and restart audio")
        apply.setObjectName("primary")
        apply.setIcon(glyph_icon(G_PLAY, "white", 13))
        apply.setCursor(Qt.PointingHandCursor)
        apply.clicked.connect(self.start_audio)
        ar = QHBoxLayout()
        ar.addWidget(apply)
        ar.addStretch()
        lay.addLayout(ar)
        v.addWidget(fr)

        # global hotkeys
        fr, lay = card("Global hotkeys", "These work everywhere, even while you're in a game.")
        for key, text in [("stop_hotkey", "Stop all sounds"), ("mic_toggle_hotkey", "Mute / unmute mic"),
                          ("hear_self_hotkey", "Hear myself on / off")]:
            lay.addLayout(self._hotkey_row(text, key))
        v.addWidget(fr)

        # push to talk
        fr, lay = card("Game push-to-talk",
                       "Games like CS2 only send your voice while push-to-talk is held. Turn this on "
                       "and the app holds your PTT key for you while a sound is playing.")
        self.ptt_check = QCheckBox("Hold push-to-talk while a sound plays")
        self.ptt_check.setChecked(bool(self.cfg["ptt_enabled"]))
        self.ptt_check.toggled.connect(self._set_ptt_enabled)
        lay.addWidget(self.ptt_check)
        lay.addLayout(self._hotkey_row("Game's push-to-talk key", "ptt_key"))
        v.addWidget(fr)

        # setup guide
        fr, lay = card("Setup guide")
        steps = [
            "Install BlackHole 2ch (free, existential.audio/blackhole), then restart your Mac.",
            "Here, set Real mic to your Mac's mic or headset, and Send to BlackHole 2ch.",
            "In Discord or your game, pick BlackHole 2ch as the microphone.",
            "Leave your Mac's sound output on your speakers or headphones, not BlackHole.",
        ] if IS_MAC else [
            "Install VB-Audio Virtual Cable (free, vb-audio.com/Cable).",
            "Windows Sound settings → Input → set the default device to CABLE Output.",
            "Here, set Real mic to your headset mic, so it still works after step 2.",
            "In your game or Discord, pick CABLE Output (or Default) as the microphone.",
            "Use CABLE Input as the send device, not “CABLE In 16ch”.",
        ]
        for i, s in enumerate(steps, 1):
            row = QHBoxLayout()
            n = QLabel(str(i))
            n.setFixedSize(24, 24)
            n.setAlignment(Qt.AlignCenter)
            n.setStyleSheet(f"background: rgba(124,92,255,0.18); color: {TEXT}; border-radius: 12px;"
                            "font-weight: 700; font-size: 12px;")
            row.addWidget(n)
            t = label(s, "muted")
            t.setWordWrap(True)
            row.addWidget(t, 1)
            lay.addLayout(row)
        v.addWidget(fr)
        v.addStretch()
        return page

    def _build_effects(self):
        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        outer.addWidget(sc)
        body = QWidget()
        sc.setWidget(body)
        v = QVBoxLayout(body)
        v.setContentsMargins(32, 28, 32, 28)
        v.setSpacing(18)
        tv = QVBoxLayout()
        tv.setSpacing(2)
        tv.addWidget(label("Voice effects", "h1"))
        self.fx_subtitle = label("", "muted")
        tv.addWidget(self.fx_subtitle)
        v.addLayout(tv)

        fr, lay = card("Preset", "Changes your real mic before it's mixed into the virtual cable. "
                                 "Sound clips aren't affected.")
        host = QWidget()
        grid = FlowGrid(min_w=190, row_h=78, spacing=12)
        host.setLayout(grid)
        for i, (key, title, desc) in enumerate(VOICE_EFFECTS):
            b = QPushButton()
            b.setObjectName("fxTile")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)   # fill the grid cell
            tl = QHBoxLayout(b)
            tl.setContentsMargins(16, 12, 16, 12)
            tl.setSpacing(12)
            dot = QLabel()
            dot.setPixmap(dot_icon(MUTED if key == "none" else PAD_COLORS[(i - 1) % len(PAD_COLORS)],
                                   12).pixmap(12, 12))
            tl.addWidget(dot)
            texts = QVBoxLayout()
            texts.setSpacing(1)
            name, sub = label(title, "h2"), label(desc, "muted")
            texts.addWidget(name)
            texts.addWidget(sub)
            tl.addLayout(texts, 1)
            for w in (dot, name, sub):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
            b.clicked.connect(lambda _=False, k=key: self.set_voice_effect(k))
            grid.addWidget(b)
            self.fx_tiles[key] = b
        lay.addWidget(host)
        v.addWidget(fr)

        fr, lay = card("On / off", "Bypass the effect without losing your pick, e.g. for a quick "
                                   "normal-voice callout.")
        self.fx_check = QCheckBox("Voice effect enabled")
        self.fx_check.setChecked(self.engine.effect_on)
        self.fx_check.toggled.connect(lambda on: on != self.engine.effect_on and self.toggle_effect())
        lay.addWidget(self.fx_check)
        lay.addLayout(self._hotkey_row("Toggle voice effect", "effect_hotkey"))
        v.addWidget(fr)
        v.addStretch()
        return page

    def _hotkey_row(self, text, key):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(label(text))
        row.addStretch()
        chip = label("", "chip")
        self.glob_chips[key] = chip
        row.addWidget(chip)
        ch = QPushButton("Change")
        ch.setCursor(Qt.PointingHandCursor)
        ch.clicked.connect(lambda: self._set_global(key, text))
        row.addWidget(ch)
        cl = QPushButton("Clear")
        cl.setCursor(Qt.PointingHandCursor)
        cl.clicked.connect(lambda: self._clear_global(key))
        row.addWidget(cl)
        self._update_chip(key)
        return row

    def _build_mixer(self):
        bar = QFrame()
        bar.setObjectName("mixer")
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 14, 24, 14)
        h.setSpacing(12)
        self.mic_btn = QPushButton()
        self.mic_btn.setObjectName("micBtn")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setIconSize(QSize(20, 20))
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.clicked.connect(self.toggle_mic)
        h.addWidget(self.mic_btn)
        self.ear_btn = QPushButton()
        self.ear_btn.setObjectName("earBtn")
        self.ear_btn.setCheckable(True)
        self.ear_btn.setIconSize(QSize(20, 20))
        self.ear_btn.setCursor(Qt.PointingHandCursor)
        self.ear_btn.clicked.connect(self.toggle_hear_self)
        h.addWidget(self.ear_btn)
        self.s_mic = Strip(G_MIC, "Mic", self.cfg["mic_gain"], meter=True)
        self.s_sounds = Strip(G_MUSIC, "Sounds", self.cfg["sound_gain"])
        self.s_mon = Strip(G_HEADPHONE, "Monitor", self.cfg["monitor_gain"])
        self.s_out = Strip(G_GAME, "Sent to game", meter=True)
        self.s_out.val.setText("")
        for s, key in [(self.s_mic, "mic_gain"), (self.s_sounds, "sound_gain"),
                       (self.s_mon, "monitor_gain"), (self.s_out, None)]:
            if key:
                s.changed.connect(lambda val, k=key: self._set_gain(k, val))
                s.slider.sliderReleased.connect(lambda: save_config(self.cfg))
            h.addWidget(s, 1)
        h.addWidget(self._build_fx_strip(), 1)
        self._update_mic_btn()
        self._update_ear_btn()
        self._update_fx_ui()
        return bar

    def _build_fx_strip(self):
        fr = QFrame()
        fr.setObjectName("strip")
        lay = QVBoxLayout(fr)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(7)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(glyph_icon(G_MIC, MUTED, 14).pixmap(14, 14))
        top.addWidget(ic)
        top.addWidget(label("VOICE FX", "dim"))
        top.addStretch()
        self.fx_state = label("", "value")
        self.fx_state.setCursor(Qt.PointingHandCursor)
        self.fx_state.setToolTip("Click to turn the effect on / off")
        self.fx_state.mousePressEvent = lambda e: self.toggle_effect()
        top.addWidget(self.fx_state)
        lay.addLayout(top)
        self.fx_box = QComboBox()
        self.fx_box.setObjectName("fxBox")
        for key, title, _ in VOICE_EFFECTS:
            self.fx_box.addItem(title, key)
        self.fx_box.currentIndexChanged.connect(
            lambda i: self.set_voice_effect(self.fx_box.itemData(i)))
        lay.addWidget(self.fx_box)
        return fr

    # ---------- helpers
    def _entry(self, name):
        return next((s for s in self.cfg["sounds"] if s["name"] == name), None)

    def _go(self, i):
        self.stack.setCurrentIndex(i)
        for j, b in enumerate(self.nav):
            b.setChecked(i == j)

    def _set_gain(self, key, val):
        self.cfg[key] = val
        setattr(self.engine, key, val)

    def _update_mic_btn(self):
        muted = not self.engine.mic_on
        self.mic_btn.setChecked(muted)
        self.mic_btn.setIcon(glyph_icon(G_MIC, DANGER if muted else OK, 20))
        self.mic_btn.setToolTip("Mic muted, click to unmute" if muted else "Mic live, click to mute")

    def _update_ear_btn(self):
        on = self.engine.hear_self
        self.ear_btn.setChecked(on)
        self.ear_btn.setIcon(glyph_icon(G_HEADPHONE, ACCENT2 if on else MUTED, 20))
        hk = pretty_hotkey(self.cfg.get("hear_self_hotkey"))
        tip = ("Hearing yourself, click to stop" if on else "Hear myself: play your mic in your headphones")
        if not self.cfg.get("monitor") or self.cfg["monitor"] == "(none)":
            tip += "\n(Pick a Monitor device in Settings first)"
        self.ear_btn.setToolTip(tip + (f"\nHotkey: {hk}" if hk else ""))

    def _update_chip(self, key):
        if key in getattr(self, "glob_chips", {}):
            self.glob_chips[key].setText(pretty_hotkey(self.cfg.get(key)) or "Not set")

    def _update_side_keys(self):
        self.side_keys.setText(
            f"Stop all   <b style='color:{TEXT}'>{pretty_hotkey(self.cfg['stop_hotkey']) or '—'}</b><br>"
            f"Mute mic  <b style='color:{TEXT}'>{pretty_hotkey(self.cfg['mic_toggle_hotkey']) or '—'}</b><br>"
            f"Voice FX   <b style='color:{TEXT}'>{pretty_hotkey(self.cfg['effect_hotkey']) or '—'}</b>")

    def _set_status(self, ok, title, text):
        self.status_dot.setStyleSheet(f"color: {OK if ok else DANGER}; font-size: 14px;")
        self.status_title.setText(title)
        self.status_text.setText(text)

    def _load_sounds(self):
        for s in self.cfg["sounds"]:
            try:
                self.sounds[s["name"]] = load_sound(SOUNDS_DIR / s["file"])
            except Exception as e:
                print(f"Could not load {s['file']}: {e}")

    def _rebuild_pads(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.pads = {}
        for e in self.cfg["sounds"]:
            pad = Pad(self, e)
            pad.clicked.connect(self.trigger)
            pad.menu.connect(self._pad_menu)
            self.grid.addWidget(pad)
            self.pads[e["name"]] = pad
        n = len(self.cfg["sounds"])
        self.subtitle.setText(f"{n} sound{'s' if n != 1 else ''}  ·  right-click a pad to edit, drag to move")
        self._filter(self.search.text())

    def _filter(self, text):
        t = text.strip().lower()
        for name, pad in self.pads.items():
            pad.setVisible(t in name.lower())
        self.empty.setVisible(not self.pads)
        self.grid.invalidate()

    # ---------- soundboard mode (full screen, pads only)
    def toggle_board_mode(self):
        self.board_mode = on = not self.board_mode
        if on:
            self._go(0)
            self.search.clear()
            self._was_maximized = self.isMaximized()
        for w in (self.sidebar, self.mixer, self.board_head):
            w.setVisible(not on)
        self.mode_bar.setVisible(on)
        self.board_layout.setContentsMargins(*((28, 18, 28, 22) if on else (32, 28, 32, 16)))
        if on:
            self.showFullScreen()
        elif self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self._update_fit()

    def _update_fit(self):
        """In Soundboard mode the pads fill the visible area (minus the holder's margins)."""
        self.grid.fit_h = self.scroll.viewport().height() - 8 if self.board_mode else 0
        self.grid.invalidate()
        self.grid_host.updateGeometry()

    def eventFilter(self, obj, e):
        if obj is self.scroll.viewport() and e.type() == QEvent.Resize and self.board_mode:
            QTimer.singleShot(0, self._update_fit)
        return super().eventFilter(obj, e)

    # ---------- rearranging pads
    def drag_pad(self, pad):
        if self.search.text().strip():          # order is ambiguous while filtered
            return
        mime = QMimeData()
        mime.setData(DropGrid.MIME, pad.name.encode())
        snap = pad.grab()
        ghost = QPixmap(snap.size())
        ghost.setDevicePixelRatio(snap.devicePixelRatio())
        ghost.fill(Qt.transparent)
        gp = QPainter(ghost)
        gp.setOpacity(0.85)
        gp.drawPixmap(0, 0, snap)
        gp.end()
        drag = QDrag(pad)
        drag.setMimeData(mime)
        drag.setPixmap(ghost)
        drag.setHotSpot(pad.press_pos)
        pad.dragging = True
        pad.update()
        drag.exec(Qt.MoveAction)
        pad.dragging = False
        pad.update()
        save_config(self.cfg)

    def move_pad(self, name, pos):
        """Called while dragging over the grid: shift the dragged pad into the slot under pos."""
        dst = self.grid.index_at(pos)
        src = next((i for i, it in enumerate(self.grid.items)
                    if getattr(it.widget(), "name", None) == name), None)
        if dst is None or src is None or src == dst:
            return
        self.grid.move(src, dst)
        snd = self.cfg["sounds"]
        e = self._entry(name)
        snd.remove(e)
        snd.insert(dst, e)

    def _tick(self):
        self.s_mic.meter.push(self.engine.take_peak("mic"))
        self.s_out.meter.push(self.engine.take_peak("out"))
        playing = self.engine.playing_names()
        for name in playing | self._was_playing:
            if name in self.pads:
                self.pads[name].update()
        self._was_playing = playing
        self._ptt(bool(playing))

    def _ptt(self, active):
        key = self.cfg.get("ptt_key")
        if not (self.cfg.get("ptt_enabled") and key):
            active = False
        now = time.monotonic()
        if active:
            self.ptt_last = now
            if not self.ptt_down:
                try:
                    self.hk.press(key)
                    self.ptt_down = True
                except Exception as e:
                    print("PTT press failed:", e)
        elif self.ptt_down and now - self.ptt_last > 0.25:   # short tail so the end isn't cut
            self._ptt_release()

    def _ptt_release(self):
        if self.ptt_down:
            try:
                self.hk.release(self.cfg.get("ptt_key"))
            except Exception:
                pass
            self.ptt_down = False

    # ---------- hotkeys
    def _unbind_hotkeys(self):
        self.hk.clear()

    def _bind_hotkeys(self):
        pairs = []

        def add(hk, fn):
            if hk:
                pairs.append((hk, lambda: self.bridge.call.emit(fn)))

        for s in self.cfg["sounds"]:
            add(s.get("hotkey"), lambda n=s["name"]: self.trigger(n))
        add(self.cfg["stop_hotkey"], self.engine.stop_all)
        add(self.cfg["mic_toggle_hotkey"], self.toggle_mic)
        add(self.cfg["effect_hotkey"], self.toggle_effect)
        add(self.cfg["hear_self_hotkey"], self.toggle_hear_self)
        self.hk.bind(pairs)

    def _capture(self, what):
        """Returns the next key combo pressed, or None if cancelled."""
        self._unbind_hotkeys()
        self._ptt_release()
        dlg = CaptureDialog(self, what)
        dlg.exec()
        hk = dlg.result_hk
        if hk:
            self._release_hotkey(hk)
        return hk

    def _after_hotkey_change(self):
        save_config(self.cfg)
        self._bind_hotkeys()
        for k in ("stop_hotkey", "mic_toggle_hotkey", "effect_hotkey", "hear_self_hotkey", "ptt_key"):
            self._update_chip(k)
        self._update_ear_btn()
        self._update_fx_ui()
        self._update_side_keys()
        self._rebuild_pads()

    def _release_hotkey(self, hk):
        """A combo can only belong to one thing."""
        for s in self.cfg["sounds"]:
            if s.get("hotkey") == hk:
                s["hotkey"] = ""
        for k in ("stop_hotkey", "mic_toggle_hotkey", "effect_hotkey", "hear_self_hotkey"):
            if self.cfg[k] == hk:
                self.cfg[k] = ""

    def _set_global(self, key, text):
        hk = self._capture(text.lower())
        if hk:
            self.cfg[key] = hk
        self._after_hotkey_change()

    def _clear_global(self, key):
        self.cfg[key] = ""
        if key == "ptt_key":
            self._ptt_release()
        self._after_hotkey_change()

    def _set_ptt_enabled(self, on):
        self.cfg["ptt_enabled"] = on
        if not on:
            self._ptt_release()
        save_config(self.cfg)

    # ---------- pad menu
    def _pad_menu(self, name, pos):
        e = self._entry(name)
        if not e:
            return
        m = QMenu(self)
        playing = name in self.engine.playing_names()
        m.addAction(glyph_icon(G_STOP if playing else G_PLAY, TEXT, 14),
                    "Stop" if playing else "Play",
                    (lambda: self.engine.stop(name)) if playing else (lambda: self.trigger(name)))
        m.addSeparator()
        m.addAction(glyph_icon(G_KEYBOARD, TEXT, 14), "Set hotkey…", lambda: self.set_hotkey(name))
        if e.get("hotkey"):
            m.addAction("Clear hotkey", lambda: self.clear_hotkey(name))
        m.addAction(glyph_icon(G_VOLUME, TEXT, 14), f"Volume ({int(e['volume'] * 100)}%)…",
                    lambda: self.set_volume(name))

        mm = m.addMenu(glyph_icon(G_LOOP, TEXT, 14), "Play mode")
        grp = QActionGroup(mm)
        for key, title, desc in MODES:
            a = QAction(f"{title}  —  {desc}", mm)
            a.setCheckable(True)
            a.setChecked(e.get("mode", "overlap") == key)
            a.triggered.connect(lambda _=False, k=key: self._set_field(name, "mode", k))
            grp.addAction(a)
            mm.addAction(a)

        cm = m.addMenu(dot_icon(e.get("color", ACCENT)), "Color")
        for c, cname in zip(PAD_COLORS, COLOR_NAMES):
            cm.addAction(dot_icon(c), cname, lambda c=c: self._set_field(name, "color", c))

        m.addAction(glyph_icon(G_EDIT, TEXT, 14), "Rename…", lambda: self.rename_sound(name))
        m.addAction(glyph_icon(G_FOLDER, TEXT, 14), "Show file in folder",
                    lambda: reveal_file(SOUNDS_DIR / e["file"]))
        m.addSeparator()
        m.addAction(glyph_icon(G_DELETE, DANGER, 14), "Remove", lambda: self.remove_sound(name))
        m.exec(pos)

    def _set_field(self, name, field, value):
        e = self._entry(name)
        if e:
            e[field] = value
            if field == "mode":
                self.engine.stop(name)
            save_config(self.cfg)
            self._rebuild_pads()

    # ---------- actions
    def trigger(self, name):
        e, data = self._entry(name), self.sounds.get(name)
        if not e or data is None:
            return
        mode = e.get("mode", "overlap")
        if mode in ("toggle", "loop") and name in self.engine.playing_names():
            self.engine.stop(name)
            return
        if mode == "restart":
            self.engine.stop(name)
        self.engine.play(name, data, e.get("volume", 1.0), loop=(mode == "loop"))

    def toggle_mic(self):
        self.engine.mic_on = not self.engine.mic_on
        self._update_mic_btn()

    def toggle_hear_self(self):
        self.engine.set_hear_self(not self.engine.hear_self)
        self.cfg["hear_self"] = self.engine.hear_self
        self._update_ear_btn()
        save_config(self.cfg)

    def set_voice_effect(self, kind):
        if kind == self.cfg["voice_effect"]:
            self._update_fx_ui()                # re-check the tile Qt just unchecked
            return
        self.cfg["voice_effect"] = kind
        self.engine.set_effect(kind)
        self._update_fx_ui()
        save_config(self.cfg)

    def toggle_effect(self):
        if not self.engine.effect_on:
            self.engine.set_effect(self.cfg["voice_effect"])     # fresh state, no stale echo tail
        self.engine.effect_on = not self.engine.effect_on
        self.cfg["effect_enabled"] = self.engine.effect_on
        self._update_fx_ui()
        save_config(self.cfg)

    def _update_fx_ui(self):
        kind, on = self.cfg["voice_effect"], self.engine.effect_on
        title = dict((k, t) for k, t, _ in VOICE_EFFECTS)[kind]
        for k, b in self.fx_tiles.items():
            b.setChecked(k == kind)
        if hasattr(self, "fx_box"):
            self.fx_box.blockSignals(True)
            self.fx_box.setCurrentIndex([k for k, _, _ in VOICE_EFFECTS].index(kind))
            self.fx_box.blockSignals(False)
            live = on and kind != "none"
            self.fx_state.setText("ON" if live else ("OFF" if kind != "none" else ""))
            self.fx_state.setStyleSheet(f"color: {OK if live else MUTED};")
        if hasattr(self, "fx_check"):
            self.fx_check.blockSignals(True)
            self.fx_check.setChecked(on)
            self.fx_check.blockSignals(False)
            hk = pretty_hotkey(self.cfg["effect_hotkey"])
            if kind == "none":
                state = "No effect, your normal voice"
            else:
                state = f"Active: {title}" if on else f"Bypassed ({title} selected)"
            self.fx_subtitle.setText(state + (f"  ·  {hk} toggles it" if hk else ""))

    def add_sounds(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add sounds", "", "Audio (*.wav *.mp3 *.ogg *.flac *.aiff *.aif);;All files (*.*)")
        self.import_files([Path(p) for p in paths])

    def import_files(self, paths):
        failed = []
        for p in paths:
            base, name, i = p.stem, p.stem, 2
            while self._entry(name):
                name, i = f"{base}_{i}", i + 1
            dest = SOUNDS_DIR / (name + p.suffix.lower())
            try:
                if p.resolve() != dest.resolve():
                    shutil.copy2(p, dest)
                self.sounds[name] = load_sound(dest)
            except Exception as e:
                failed.append(f"{p.name}: {e}")
                continue
            self.cfg["sounds"].append({"name": name, "file": dest.name, "hotkey": "", "volume": 1.0,
                                       "color": PAD_COLORS[len(self.cfg["sounds"]) % len(PAD_COLORS)],
                                       "mode": "overlap"})
        save_config(self.cfg)
        self._rebuild_pads()
        if failed:
            QMessageBox.warning(self, "Some files couldn't be loaded", "\n".join(failed))

    def set_hotkey(self, name):
        hk = self._capture(f"“{name}”")
        if hk and self._entry(name):
            self._entry(name)["hotkey"] = hk
        self._after_hotkey_change()

    def clear_hotkey(self, name):
        self._entry(name)["hotkey"] = ""
        self._after_hotkey_change()

    def set_volume(self, name):
        e = self._entry(name)
        v, ok = QInputDialog.getInt(self, "Volume", f"Volume for {name} (0–200%)",
                                    int(e.get("volume", 1) * 100), 0, 200, 5)
        if ok:
            e["volume"] = v / 100
            save_config(self.cfg)
            self._rebuild_pads()

    def rename_sound(self, name):
        new, ok = QInputDialog.getText(self, "Rename", "New name:", text=name)
        new = new.strip()
        if not ok or not new or new == name:
            return
        if self._entry(new):
            QMessageBox.warning(self, "Rename", f"There's already a sound called “{new}”.")
            return
        self.engine.stop(name)
        self._entry(name)["name"] = new
        if name in self.sounds:
            self.sounds[new] = self.sounds.pop(name)
        save_config(self.cfg)
        self._bind_hotkeys()
        self._rebuild_pads()

    def remove_sound(self, name):
        if QMessageBox.question(self, "Remove", f"Remove “{name}” from the board?") \
                != QMessageBox.Yes:
            return
        e = self._entry(name)
        self.engine.stop(name)
        self.cfg["sounds"].remove(e)
        self.sounds.pop(name, None)
        try:
            (SOUNDS_DIR / e["file"]).unlink()
        except OSError:
            pass
        save_config(self.cfg)
        self._bind_hotkeys()
        self._rebuild_pads()

    def start_audio(self):
        for key, box in self.dev_boxes.items():
            self.cfg[key] = box.currentText()
        self.cfg["mic_buffer_ms"] = self.buf_spin.value()
        mic = find_device("input", self.cfg["mic"])
        cable = find_device("output", self.cfg["cable"])
        mon = find_device("output", self.cfg["monitor"])
        save_config(self.cfg)
        if cable is None:
            if any(SEND_DEVICE.lower() in n.lower() for _, n in devices("output")):
                self._set_status(False, "Not running", f"Pick {SEND_DEVICE} as the send device in Settings.")
            else:
                self._set_status(False, f"{CABLE_NAME} not found",
                                 f"Install {CABLE_NAME}, restart your {'Mac' if IS_MAC else 'PC'}, "
                                 "then open the app again. See the README.")
            return
        try:
            self.engine.start(mic, cable, mon, self.cfg["mic_buffer_ms"])
            self._set_status(True, "Live", f"In-game mic: {GAME_MIC}")
        except Exception as e:
            self._set_status(False, "Audio error", str(e))
            (APP_DIR / "error.log").write_text(f"Audio error: {e!r}", encoding="utf-8")

    # ---------- drag and drop
    def _dropped_paths(self, e):
        if not e.mimeData().hasUrls():
            return []
        return [Path(u.toLocalFile()) for u in e.mimeData().urls()
                if Path(u.toLocalFile()).suffix.lower() in AUDIO_EXT]

    def dragEnterEvent(self, e):
        if self._dropped_paths(e):
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = self._dropped_paths(e)
        if paths:
            self._go(0)
            self.import_files(paths)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, "full_btn"):     # icon only when the header gets tight
            self.full_btn.setText("" if self.width() < 1150 else "  Soundboard mode")

    def showEvent(self, e):
        super().showEvent(e)
        set_dark_titlebar(self)

    def closeEvent(self, e):
        save_config(self.cfg)
        self._ptt_release()
        self.hk.shutdown()
        self.engine.close_streams()
        super().closeEvent(e)


def main():
    global ICON_FONT
    try:   # own taskbar icon instead of python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("soundboard.v2")
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName("Soundboard")
    families = QFontDatabase.families()
    ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in families), None)
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss())
    app.setWindowIcon(app_icon())
    win = MainWindow()
    win.show()
    if not win.hk.trusted:
        QTimer.singleShot(400, lambda: QMessageBox.information(
            win, "Allow hotkeys",
            "To use hotkeys, macOS needs your permission.\n\n"
            "Open System Settings → Privacy & Security, then turn on Terminal under both "
            "Accessibility and Input Monitoring. Then quit Terminal and start the Soundboard again.\n\n"
            "Clicking the pads works without this."))
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        (APP_DIR / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
