# Terminal Traffic Light

A macOS menu bar app that monitors your Terminal.app tabs and shows a colored indicator light.

![Preview](cat_preview.png)

## States

| Light | Meaning |
|-------|---------|
| 🔴 Red (blinking) | Terminal is waiting for your input |
| 🟡 Yellow | A command is running |
| 🟢 Green | All terminals are idle |
| ⚪ Gray | No Terminal.app windows open |

## How It Works

- Uses **zsh shell hooks** (`preexec` / `precmd`) to write state files to `~/.terminal_traffic_light/`
- The menu bar app polls these files every second
- Only monitors **Terminal.app** tabs (not other terminal emulators)
- For interactive tools like `claude`, distinguishes between "waiting for input" (red) and "processing" (yellow) via CPU usage

## Requirements

- macOS
- Python 3
- [rumps](https://github.com/jaredks/rumps)

```bash
pip3 install rumps
```

## Installation

**1. Clone the repo**

```bash
git clone https://github.com/YOUR_USERNAME/terminal-traffic-light.git
cd terminal-traffic-light
```

**2. Install dependency**

```bash
pip3 install -r requirements.txt
```

**3. Add shell hook to your `.zshrc`**

```bash
echo "source $(pwd)/shell_hook.zsh" >> ~/.zshrc
source ~/.zshrc
```

**4. Build and launch the app**

```bash
python3 build_app.py
open TerminalTrafficLight.app
```

To auto-start on login, add `TerminalTrafficLight.app` to **System Settings → General → Login Items**.

## Files

| File | Description |
|------|-------------|
| `terminal_traffic_light.py` | Main menu bar app |
| `shell_hook.zsh` | Zsh hooks that write state files |
| `build_app.py` | Builds the `.app` bundle with pixel cat icon |
| `requirements.txt` | Python dependencies |

## License

MIT
