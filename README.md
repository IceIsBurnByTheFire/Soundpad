# 🎛️ Soundboard

Play sounds through your microphone in games and on Discord, **while you keep talking normally**.
Like Voicemod, but free and simple.

- 🔊 Play your own audio clips (mp3, wav, ogg, flac) so everyone in the call hears them
- 🎙️ Your real voice still goes through at the same time, no switching mics
- ⌨️ Hotkeys that work while you're in a game
- 🖥️ Full-screen **Soundboard mode** with big pads you can drag into any order
- 🤖 Voice effects: Chipmunk, Deep, Robot, Radio, Echo
- 🎧 You hear the sounds too, and you can turn on "Hear myself" to check how you sound

Works on **Windows 10 / 11** and **macOS** (MacBook, iMac, Mac mini).

👉 Jump to: [Windows setup](#-windows-setup) · [Mac setup](#-mac-setup) · [Using it](#using-it) · [Problems?](#problems)

---

## How it works (30-second version)

Your computer doesn't let two programs share a microphone like this, so we use a free
**virtual cable**: a fake audio device. The Soundboard mixes your voice and your sounds and sends
them into the cable. Discord or your game uses the cable as its microphone.

```
 Your real mic  ─┐
                 ├─►  Soundboard  ─►  virtual cable  ─►  Discord / your game
 Your sounds    ─┘                                       (pick the cable as your mic)
```

| | Virtual cable | The app sends to | Your game's mic |
|---|---|---|---|
| Windows | VB-Cable | **CABLE Input** | **CABLE Output** |
| Mac | BlackHole | **BlackHole 2ch** | **BlackHole 2ch** |

---

## 🪟 Windows setup
About 10 minutes, only once.

### Step 1 — Install Python
1. Go to **https://www.python.org/downloads/** and click the big yellow **Download Python** button.
2. Open the file you downloaded.
3. ⚠️ **Important:** on the first screen, tick **"Add python.exe to PATH"** at the bottom.
4. Click **Install Now** and wait until it says *Setup was successful*.

> Already have Python 3.10 or newer? Skip this step.

### Step 2 — Install the virtual cable (VB-Cable)
1. Go to **https://vb-audio.com/Cable/** and click **Download** (the Windows version).
2. You get a `.zip` file. Right-click it → **Extract All…** → **Extract**.
3. In the extracted folder, right-click **`VBCABLE_Setup_x64.exe`** → **Run as administrator**.
   *(On an older 32-bit PC use `VBCABLE_Setup.exe`.)*
4. Click **Install Driver**, then **OK**.
5. **Restart your PC.** The cable doesn't show up until you do.

> VB-Cable is free (donationware) and made by VB-Audio, not by this project.

### Step 3 — Start the Soundboard
1. Download this project and unzip it somewhere you'll keep it, e.g. `Documents\Soundboard`.
2. Double-click **`start.bat`**.
   - If Windows shows a blue *"Windows protected your PC"* box, click **More info** → **Run anyway**.
3. The **first time**, a black window downloads what the app needs (about 150 MB). This takes a few minutes.
   After that it starts in seconds.

### Step 4 — Check the devices in the app
Open **Settings** (left side) → **Audio devices**:

| Setting | Pick this |
|---|---|
| **Real mic** | Your actual microphone (headset, USB mic…) |
| **Send to (virtual cable)** | **CABLE Input (VB-Audio Virtual Cable)** — *not* "CABLE In 16ch" |
| **Monitor (your ears)** | Your headphones or speakers |

Click **Apply and restart audio**. The box at the bottom left should turn green and say **Live**.
Talk into your mic: the **Mic** meter at the bottom should move.

### Step 5 — Use the cable as the mic in Discord / your game
- **Discord:** User Settings → **Voice & Video** → **Input Device** → **CABLE Output (VB-Audio Virtual Cable)**.
- **Most games:** in the game's voice settings, set the microphone to **CABLE Output**.
- **Games without a mic setting (e.g. CS2)** use the Windows default mic:
  1. Right-click the speaker icon on the taskbar → **Sound settings**.
  2. Under **Input**, choose **CABLE Output**.
  3. Back in the Soundboard, make sure **Real mic** is still your real mic (not CABLE Output).

✅ Done! Ask a friend if they can hear you, then play a sound.

---

## 🍎 Mac setup
About 10 minutes, only once. Works on Apple Silicon (M1/M2/M3/M4) and Intel Macs.

### Step 1 — Install Python
1. Go to **https://www.python.org/downloads/macos/** and download the latest **macOS 64-bit universal2 installer**.
2. Open the `.pkg` file and click **Continue** → **Agree** → **Install** (enter your Mac password when asked).

> The `python3` that comes with macOS is often too old, so install this one even if you think you have Python.

### Step 2 — Install the virtual cable (BlackHole)
1. Go to **https://existential.audio/blackhole/** and choose **BlackHole 2ch**.
   It's free; the site asks for your email and sends you the download link.
2. Open the downloaded `.pkg` file and click through the installer.
3. **Restart your Mac.**

> BlackHole is free and open source, made by Existential Audio, not by this project.
> If you use Homebrew, `brew install blackhole-2ch` does the same thing.

### Step 3 — Start the Soundboard
1. Download this project and unzip it (double-click the `.zip`). Move the folder somewhere you'll keep it, e.g. **Documents**.
2. **Right-click** (or Control-click) **`start.command`** → **Open** → **Open**.
   - You only need the right-click the first time. After that, a normal double-click works.
   - If it says it *"can't be opened because Apple cannot check it"*: open **System Settings → Privacy & Security**,
     scroll down and click **Open Anyway** next to `start.command`.
   - If it says *"you do not have appropriate access privileges"* (common when downloaded from GitHub):
     open **Terminal** (press `⌘ Space`, type *Terminal*, Enter), type `bash ` (with a space after it),
     **drag `start.command` into the Terminal window**, and press **Enter**.
3. The **first time**, Terminal downloads what the app needs (about 150 MB). This takes a few minutes.

### Step 4 — Allow microphone and hotkeys
- When macOS asks **"Terminal would like to access the microphone"**, click **Allow**.
- For **hotkeys** (they're optional; clicking pads always works):
  1. Open **System Settings → Privacy & Security → Accessibility** and turn on **Terminal**.
  2. Do the same under **Privacy & Security → Input Monitoring**.
  3. Quit Terminal completely (`⌘ Q`) and start the Soundboard again.

  The app shows a reminder if this permission is missing.

### Step 5 — Check the devices in the app
Open **Settings** (left side) → **Audio devices**:

| Setting | Pick this |
|---|---|
| **Real mic** | *MacBook Pro Microphone*, or your headset / USB mic |
| **Send to (virtual cable)** | **BlackHole 2ch** |
| **Monitor (your ears)** | Your headphones, or *MacBook Pro Speakers* |

Click **Apply and restart audio**. The box at the bottom left should turn green and say **Live**.

### Step 6 — Use BlackHole as the mic in Discord / your game
- **Discord:** User Settings → **Voice & Video** → **Input Device** → **BlackHole 2ch**.
- **Games, Zoom, etc.:** set the microphone to **BlackHole 2ch**.
- ⚠️ Leave your Mac's **sound output** (System Settings → Sound → Output) on your speakers or headphones,
  **not** BlackHole, or you won't hear anything.

✅ Done!

> **Mac keys in hotkeys:** Option shows as **Alt**, Command as **Cmd**, Control as **Ctrl**.

---

## Using it

### Add sounds
Click **Add sounds**, or just **drag audio files onto the window**.
Supported: mp3, wav, ogg, flac, aiff. The files get copied into the `sounds` folder.

### Play sounds
- **Click a pad** to play it.
- **Right-click a pad** for: hotkey, volume, color, play mode, rename, remove.
- **Stop all** (top right) stops everything.
- **Drag a pad** to move it. The other pads shift out of the way, and the new order is saved.

### Soundboard mode (full screen)
Click **Soundboard mode** at the top (or press **F11**) to show only your pads, full screen.
The pads grow to fill the screen: a few sounds get huge pads, lots of sounds get smaller ones, and if there
are too many to fit, you scroll. Great on a second monitor or a touchscreen.
Press **Esc** (or **Exit** at the top right) to go back.

### Hotkeys
Right-click a pad → **Set hotkey…**, then press the keys you want (e.g. `Ctrl + Alt + 1`).
Hotkeys work everywhere, even inside a game.
💡 Pick combos your game doesn't use. Number-pad keys are a good choice.

### Play modes (right-click a pad → Play mode)
| Mode | What a press does |
|---|---|
| **Overlap** | Plays another copy on top |
| **Restart** | Starts the sound again from the beginning |
| **Play / stop** | First press plays, second press stops |
| **Loop** | Repeats until you press again |

### The bottom bar
| Control | What it does |
|---|---|
| 🎙️ round **mic** button | Mute / unmute your voice (sounds still play) |
| 🎧 round **headphones** button | **Hear myself**: hear your own mic in your headphones |
| **Mic** slider | How loud your voice is to others |
| **Sounds** slider | How loud the clips are to others |
| **Monitor** slider | How loud things are in *your* ears |
| **Sent to game** meter | What your friends actually hear |
| **Voice FX** | Pick a voice effect |

### Voice effects
Open **Voice effects** on the left (or use the **Voice FX** box at the bottom) and pick one:
None, Chipmunk, Deep, Robot, Radio, Echo. Only your voice changes; your sound clips don't.
Turn on 🎧 **Hear myself** to listen to how you sound.

### Push-to-talk games (CS2, Valorant…)
Some games only send your voice while you hold the push-to-talk key, so your friends won't hear sounds
unless you're holding it. Fix: **Settings → Game push-to-talk** → tick the box and set your game's PTT key.
The app then holds that key for you while a sound plays.

---

## Problems?

**"Python is not installed" when I start the app**
- Windows: install Python (Step 1) and make sure **"Add python.exe to PATH"** was ticked. If you forgot,
  run the Python installer again → **Modify** → tick *Add Python to environment variables*.
- Mac: install Python from python.org (Mac Step 1), then open `start.command` again.

**The box at the bottom left says "VB-Cable not found" / "BlackHole not found"**
Install the virtual cable (Step 2) and **restart your computer**.

**Nobody hears my sounds**
- In Discord/the game, the mic must be **CABLE Output** (Windows) or **BlackHole 2ch** (Mac).
- In the Soundboard, **Send to** must be **CABLE Input** (Windows) or **BlackHole 2ch** (Mac).
- Push-to-talk game? See *Push-to-talk games* above.
- Watch the **Sent to game** meter while a sound plays. If it moves, the app is working and the problem is the game's mic setting.

**Nobody hears my voice**
- In Settings, **Real mic** must be your real microphone, *not* the cable.
- Is the round mic button red? Click it to unmute.
- Talk and watch the **Mic** meter. If it doesn't move, pick a different Real mic.
- Mac: System Settings → Privacy & Security → **Microphone** → make sure **Terminal** is on.

**My voice sounds crackly or robotic (with no effect on)**
Settings → raise **Mic buffer** to 60–80 ms → **Apply and restart audio**.

**Hotkeys don't work**
- Windows, inside a game: some games run as administrator and block other apps' hotkeys.
  Close the Soundboard, then right-click `start.bat` → **Run as administrator**.
- Mac: turn on **Terminal** under both **Accessibility** and **Input Monitoring** (Mac Step 4), then quit and restart Terminal.

**Mac: I can't hear anything at all**
System Settings → **Sound** → **Output**: pick your speakers or headphones, not BlackHole.

**I hear a loud squeal when "Hear myself" is on**
Your mic is picking up your speakers. Use headphones, or turn Hear myself off.

**My antivirus complains (Windows)**
The app listens for your hotkeys system-wide, which some antivirus tools flag. It only reacts to the
hotkeys you set, and the full source code is in `soundboard.py` if you want to check.

**Something else broke**
The black window (Windows) or Terminal (Mac) shows the error. It's also saved in `error.log` in the app's folder.

---

## Uninstall
- Delete the Soundboard folder.
- Optional, Windows: remove VB-Cable by running its setup again as administrator → **Remove Driver**, then restart.
- Optional, Mac: remove BlackHole with the uninstaller from **https://existential.audio/blackhole/support/**.
- Set your Discord / game / system mic back to your real microphone.

## Files
| File | What it is |
|---|---|
| `start.bat` | Windows: double-click to run |
| `start.command` | Mac: double-click to run (right-click → Open the first time) |
| `soundboard.py` | The app |
| `requirements.txt` | What the launcher downloads the first time |
| `sounds/` | Your sound files (created on first run) |
| `config.json` | Your settings (created on first run) |
| `.venv/` | Mac only: the app's own Python packages (created on first run) |
