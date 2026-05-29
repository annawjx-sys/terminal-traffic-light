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

State is detected differently depending on the tool:

### Claude Code

Configure hooks in `~/.claude/settings.json`:

```json
"hooks": {
  "Stop": [
    {
      "matcher": "",
      "hooks": [{ "type": "command", "command": "TTY=$(tty 2>/dev/null); TTY=${TTY#/dev/}; [[ \"$TTY\" == tty* ]] && echo \"red:claude\" > \"$HOME/.terminal_traffic_light/$TTY\"" }]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "",
      "hooks": [{ "type": "command", "command": "TTY=$(tty 2>/dev/null); TTY=${TTY#/dev/}; [[ \"$TTY\" == tty* ]] && echo \"yellow:claude\" > \"$HOME/.terminal_traffic_light/$TTY\"" }]
    }
  ]
}
```

| Event | Light |
|-------|-------|
| `Stop` — Claude finished responding, waiting for your input | 🔴 Red |
| `PreToolUse` — Claude is executing a tool (read/write/run) | 🟡 Yellow |

This is the most accurate method — Claude reports its own state directly.

---

### Codex

Create `~/.codex/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "command": "TTY=$(tty 2>/dev/null); TTY=${TTY#/dev/}; [[ \"$TTY\" == tty* ]] && echo \"yellow:codex\" > \"$HOME/.terminal_traffic_light/$TTY\"" }
    ],
    "PostToolUse": [
      { "command": "TTY=$(tty 2>/dev/null); TTY=${TTY#/dev/}; [[ \"$TTY\" == tty* ]] && echo \"red:codex\" > \"$HOME/.terminal_traffic_light/$TTY\"" }
    ]
  }
}
```

| Event | Light |
|-------|-------|
| `PreToolUse` — Codex is executing a tool | 🟡 Yellow |
| `PostToolUse` — Tool finished, Codex waiting for your input | 🔴 Red |

---

### Everything else (zsh shell hooks)

For all other commands, `shell_hook.zsh` uses zsh's `preexec` / `precmd` hooks:

| Situation | Light |
|-----------|-------|
| Command starts running (`preexec`) | 🟡 Yellow |
| Command finishes, shell prompt returns (`precmd`) | 🟢 Green |
| Interactive tools: `vim`, `ssh`, `mysql`, `python` (no args), etc. | 🔴 Red |
| No Terminal.app windows open | ⚪ Gray |

For long-running commands that pause mid-way to ask for confirmation (outside of Claude Code / Codex), the red state is held for 5 seconds after the last `preexec`, then degrades to yellow if the process is still alive.

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

**5. Keep the menu bar always visible**

By default, macOS hides the menu bar in full-screen or when using certain display settings. To keep it always visible:

- **macOS Ventura / Sonoma / Sequoia**: System Settings → Control Center → Menu Bar → set "Automatically hide and show the menu bar" to **Never**
- Or run this command once in Terminal:

```bash
defaults write -g _HIHideMenuBar -bool false && killall SystemUIServer
```

## Files

| File | Description |
|------|-------------|
| `terminal_traffic_light.py` | Main menu bar app |
| `shell_hook.zsh` | Zsh hooks that write state files |
| `build_app.py` | Builds the `.app` bundle with pixel cat icon |
| `requirements.txt` | Python dependencies |

## License

MIT
