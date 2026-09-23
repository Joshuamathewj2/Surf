# Surf – Local AI Desktop Automation Agent

A lightweight, modular desktop automation agent powered by a **local LLM** (Ollama + Mistral). Speak in natural language — Surf converts your commands into keyboard and mouse actions automatically.

---

## Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.10+** | Runtime |
| **Ollama** | Local LLM server ([install](https://ollama.com)) |
| **FFmpeg** | Required for faster-whisper voice recognition ([install](https://ffmpeg.org), add to PATH) |
| **Tesseract OCR** | For screen understanding and click-by-voice ([install](https://github.com/UB-Mannheim/tesseract/wiki), add to PATH) |
| **phi3:mini model** | Pulled into Ollama |

## Quick Start

```bash
# 1. Pull the model (one-time)
ollama run phi3:mini

# 2. Install FFmpeg (Windows)
# Download from https://ffmpeg.org and add to your system PATH

# 3. Start Ollama (if not already running)
ollama serve

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run Surf
python main.py
```

At the `>>> ` prompt, try:

```
open notepad
open chrome
open Microsoft Whiteboard
```

Type `exit` to quit.

---

## Architecture

```
Surf/
├── main.py              # Entry point
├── config.py            # Settings (Ollama URL, model, delays)
├── requirements.txt
│
├── llm/
│   └── planner.py       # NL command → JSON action list via Mistral
│
├── executor/
│   └── actions.py       # pyautogui action execution
│
├── agent/
│   └── loop.py          # Input → Plan → Execute loop
│
├── voice/
│   └── recognizer.py    # Voice input and transcription
│
└── vision/
    └── screen_reader.py # Screenshot OCR and text locating
```

**Data flow:**

```
Voice/Text  ──►  Autocorrect  ──►  Safety  ──►  Router  ──►  Direct Action / LLM  ──►  Executor
```

### Supported Actions

| Command | Action |
|---|---|
| `open notepad` | Launches Notepad |
| `open vscode` | Launches VS Code |
| `open whiteboard` | Launches Microsoft Whiteboard |
| `google machine learning` | Opens Google search |
| `search youtube for lofi music` | Opens YouTube search |
| `take screenshot` | Saves timestamped PNG |
| `volume up` / `volume down` | Adjusts system volume |
| `mute` | Toggles mute |
| `click Save` | Finds and clicks "Save" on screen |

---

## Future Roadmap (design only)

- **OCR-based clicking** — locate UI text on screen and click it
- **Vision model integration** — understand screenshots for smarter planning
- **Voice input** — trigger commands by speaking

---

## Safety

`pyautogui.FAILSAFE` is enabled: move the mouse to any screen corner to abort execution instantly.
