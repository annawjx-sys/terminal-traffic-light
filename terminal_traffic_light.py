#!/usr/bin/env python3
"""
Terminal Traffic Light - macOS 菜单栏应用
监控 Terminal.app 的状态并在菜单栏显示指示灯：
  红灯 🔴: 终端需要你回复（等待输入）
  黄灯 🟡: 命令正在运行
  绿灯 🟢: 命令已完成（回到 shell 提示符）
"""

import os
import struct
import subprocess
import sys
import time
import zlib

import rumps

# Shell 钩子状态文件目录
SHELL_HOOK_DIR = os.path.expanduser("~/.terminal_traffic_light")


# ─── 图标生成 ───────────────────────────────────────────────

ICON_COLORS = {
    "red": (255, 59, 48),
    "yellow": (255, 204, 0),
    "green": (52, 199, 89),
    "gray": (180, 180, 180),
}

# 需要用户回复的交互式命令 → 红灯
INTERACTIVE_COMMANDS = frozenset({
    # 编辑器
    "vim", "vi", "nvim", "nano", "emacs", "ed", "micro",
    # 分页器
    "less", "more", "most",
    # 远程连接（需要持续交互的终端）
    "ssh", "slogin", "telnet", "rlogin", "mosh",
    # 调试器
    "gdb", "lldb",
    # 全屏交互工具
    "htop", "btop", "bashtop", "atop",
    "screen", "tmux", "lazygit", "tig",
    "man", "info",
    "pass", "gpg", "pinentry",
    "crontab", "visudo", "vigr",
    # 邮件
    "mail", "mutt", "neomutt",
    # 网络交互
    "ftp", "sftp", "nc", "ncat", "socat",
    # 其他
    "gnuplot", "julia", "mongo", "python2",
})

# 既是 REPL 也可能执行脚本的命令
# 无参数 = REPL 等待输入 → 红灯；有脚本参数 = 运行中 → 黄灯
REPL_OR_SCRIPT = frozenset({
    "python", "python3", "ipython", "ipython3",
    "node", "irb", "pry", "lua", "bc",
    "ruby", "perl",
})

# 始终等待用户输入的 REPL / AI 助手 → 红灯
ALWAYS_REPL = frozenset({
    "claude", "chatgpt", "aider", "cursor",
    "jupyter", "jupyter-console",
    "rails",
    "mysql", "psql", "sqlite3", "redis-cli", "mongosh",
})

# 常见后台/守护进程类命令，即使在前台 sleep 也不代表等用户输入
BACKGROUND_COMMANDS = frozenset({
    "caffeinate", "sleep", "watch", "tail", "stdbuf",
    "nohup", "daemon", "launchctl",
    "ping", "traceroute", "mtr",
    "top",  # top 虽然交互但不需要用户回复
})

SHELL_NAMES = frozenset({
    "bash", "zsh", "sh", "dash", "fish", "ksh", "csh", "tcsh",
})


def create_dot_png(filepath, r, g, b, size=22):
    """创建带透明度的圆形 PNG 图标（纯 Python，无外部依赖）。"""
    rows = []
    center = size / 2
    radius = size / 2 - 1.5
    for y in range(size):
        row = b"\x00"  # PNG filter: None
        for x in range(size):
            dx = x - center + 0.5
            dy = y - center + 0.5
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius:
                alpha = min(1.0, max(0.0, radius - dist + 0.5))
                row += bytes([
                    int(r * alpha),
                    int(g * alpha),
                    int(b * alpha),
                    int(255 * alpha),
                ])
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(row)

    raw_data = b"".join(rows)

    def _chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    with open(filepath, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)))
        f.write(_chunk(b"IDAT", zlib.compress(raw_data, 9)))
        f.write(_chunk(b"IEND", b""))


def ensure_icons(icon_dir):
    """确保所有颜色图标文件存在。"""
    os.makedirs(icon_dir, exist_ok=True)
    paths = {}
    for name, color in ICON_COLORS.items():
        path = os.path.join(icon_dir, f"{name}.png")
        if not os.path.exists(path):
            create_dot_png(path, *color)
        paths[name] = path
    return paths


# ─── 终端状态检测 ────────────────────────────────────────────


def _run(cmd, timeout=3):
    """运行命令并返回 stdout，失败返回空字符串。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def _get_all_tys():
    """获取系统所有活跃 TTY 列表（包括 Terminal、Qoder、VSCode 等的终端）。"""
    raw = _run(["ps", "-o", "tty=", "-a"])
    if not raw:
        return []
    ttys = set()
    for line in raw.splitlines():
        t = line.strip()
        if t and t.startswith("tty"):
            ttys.add(t)
    return sorted(ttys)


def _parse_ps_output(text):
    """解析 ps 输出为进程列表。"""
    procs = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 3)
        if len(parts) < 3:
            continue
        proc = {
            "pid": int(parts[0]),
            "ppid": int(parts[1]),
            "stat": parts[2],
            "command": parts[3] if len(parts) == 4 else "",
        }
        procs.append(proc)
    return procs


def _check_tty_state(tty):
    """检查指定 TTY 的状态，返回 (state, command)。"""
    raw = _run(["ps", "-o", "pid=,ppid=,stat=,command=", "-t", tty])
    if not raw:
        return "green", ""

    procs = _parse_ps_output(raw)

    # 找出非 shell 进程
    non_shell = []
    for p in procs:
        cmd = p["command"]
        tokens = cmd.split()
        base = os.path.basename(tokens[0]) if tokens else ""
        # 跳过 shell 本身和 login
        if base in SHELL_NAMES or cmd.startswith("-"):
            continue
        # 跳过 ps 自身
        if base == "ps":
            continue
        non_shell.append(p)

    if not non_shell:
        # 只有 shell → 已完成 / 空闲
        return "green", ""

    # 构建 pid → proc 的映射，用于查找父进程
    pid_map = {p["pid"]: p for p in procs}

    # 优先检查最新的（PID 最大的）非 shell 进程
    primary = max(non_shell, key=lambda p: p["pid"])
    stat = primary["stat"]
    cmd = primary["command"]
    base = os.path.basename(cmd.split()[0]) if cmd.split() else ""

    # 1) 进程被 stop（Ctrl+Z 等）→ 一定需要用户注意
    if "T" in stat:
        return "red", cmd

    # 2) ALWAYS_REPL（claude、mysql 等）→ 区分"处理中"和"空闲"
    #    有 CPU 活动 = 正在处理 → 黄灯；无 CPU = 空闲待命 → 绿灯
    #    这类工具空闲时和 shell 提示符一样，不算"需要回复"
    if base in ALWAYS_REPL:
        if _is_process_active(primary["pid"]):
            return "yellow", cmd
        return "green", cmd

    # 3) 可能是 REPL 也可能是脚本执行器（python3、node 等）
    #    有脚本参数 = 运行中 → 黄灯；无参数 + 有CPU = 运行中 → 黄灯
    #    无参数 + 无CPU = 空闲待命 → 绿灯
    if base in REPL_OR_SCRIPT:
        parts = cmd.split()
        has_script_arg = any(
            not a.startswith("-") and a != base
            for a in parts[1:]
        )
        if has_script_arg:
            return "yellow", cmd
        if _is_process_active(primary["pid"]):
            return "yellow", cmd
        return "green", cmd

    # 4) 如果父进程是 ALWAYS_REPL 或 REPL_OR_SCRIPT
    #    父进程正在运行 → 黄灯；父进程空闲 → 绿灯
    parent = pid_map.get(primary["ppid"])
    if parent:
        parent_base = os.path.basename(parent["command"].split()[0]) if parent["command"].split() else ""
        if parent_base in ALWAYS_REPL or parent_base in REPL_OR_SCRIPT:
            if _is_process_active(parent["pid"]):
                return "yellow", parent["command"]
            return "green", parent["command"]

    # 5) 已知后台/守护进程类命令 → 归为运行中
    if base in BACKGROUND_COMMANDS:
        return "yellow", cmd

    # 6) 已知交互式命令在前台 → 需要用户输入
    if base in INTERACTIVE_COMMANDS and "+" in stat:
        return "red", cmd

    # 7) 前台进程在 sleep → 可能等输入
    #    用 lsof 检查 stdin 是否为终端（而非管道/重定向）来判断
    if "S" in stat and "+" in stat:
        if _stdin_is_terminal(primary["pid"]):
            return "red", cmd
        return "yellow", cmd

    # 8) 正在运行
    return "yellow", cmd


def _is_process_active(pid):
    """检查进程是否正在使用 CPU（区分"处理中"和"等待输入"）。
    通过 ps 获取 CPU 使用率，> 5% 说明进程在活跃工作。
    空闲的事件循环通常 < 1%，处理请求时通常 > 10%。
    """
    raw = _run(["ps", "-o", "%cpu=", "-p", str(pid)], timeout=2)
    try:
        cpu = float(raw.strip())
        return cpu > 20.0
    except (ValueError, IndexError):
        return False


def _stdin_is_terminal(pid):
    """检查进程的 stdin (fd 0) 是否是终端（而非管道/文件）。"""
    raw = _run(["lsof", "-p", str(pid), "-d", "0", "-F", "t"], timeout=2)
    # lsof -F t 输出: 第一行是 "p<pid>"，后面是 "t<type>"
    # 如果 type 包含 "CHR" 或 "VCHR"，说明是字符设备（终端）
    for line in raw.splitlines():
        if line.startswith("t"):
            ftype = line[1:]
            return ftype in ("CHR", "VCHR")
    return False


def _get_tty_foreground_pid(tty):
    """获取指定 TTY 的前台进程 PID（非 shell 进程）。"""
    raw = _run(["ps", "-o", "pid=,ppid=,stat=,command=", "-t", tty])
    if not raw:
        return None, None
    for line in raw.strip().splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) < 3:
            continue
        stat = parts[2]
        cmd = parts[3] if len(parts) == 4 else ""
        base = os.path.basename(cmd.split()[0]) if cmd.split() else ""
        # 找前台非 shell 进程
        if "+" in stat and base not in SHELL_NAMES and base not in ("ps",) and not cmd.startswith("-"):
            return int(parts[0]), cmd
    return None, None


def get_terminal_state():
    """
    只监控 Terminal.app 的标签页状态。
    通过 shell 钩子状态文件读取。
    返回 (state, command, active_tty)
    """
    # 获取 Terminal.app 当前所有标签页的 TTY 列表
    raw = _run([
        "osascript", "-e",
        'tell application "Terminal" to get tty of every tab of every window',
    ])
    terminal_ttys = set()
    if raw:
        for part in raw.split(", "):
            t = part.strip().replace("/dev/", "")
            if t.startswith("tty"):
                terminal_ttys.add(t)

    # Terminal.app 没有运行或没有窗口 → 灰色
    if not terminal_ttys:
        return "gray", "", None

    worst_state = "gray"
    worst_cmd = ""
    worst_tty = None

    if os.path.isdir(SHELL_HOOK_DIR):
        now = time.time()
        for name in os.listdir(SHELL_HOOK_DIR):
            # 只处理属于 Terminal.app 标签页的文件
            if name not in terminal_ttys:
                continue
            fpath = os.path.join(SHELL_HOOK_DIR, name)
            try:
                mtime = os.path.getmtime(fpath)
                with open(fpath, "r") as f:
                    content = f.read().strip()
            except (OSError, IOError):
                continue
            if not content:
                continue
            if ":" in content:
                hook_state, hook_cmd = content.split(":", 1)
            else:
                hook_state = content
                hook_cmd = ""

            # green 状态超过 10 秒未更新视为 tab 已关闭（残留文件）
            if hook_state == "green" and now - mtime > 10:
                continue
            # red 状态超过 10 秒且进程还活着 → 降级为黄灯
            # 回复后 claude 通常 10s 内开始调工具（PreToolUse 会重新写 yellow）
            # 超过 10s 说明 claude 在纯思考/对话，不需要用户继续等待
            if hook_state == "red" and now - mtime > 10:
                pid, _ = _get_tty_foreground_pid(name)
                if pid:
                    hook_state = "yellow"
                else:
                    continue

            if hook_state in ("red", "yellow", "green"):
                if _priority(hook_state) > _priority(worst_state):
                    worst_state = hook_state
                    worst_cmd = hook_cmd
                    worst_tty = name

    # 有 Terminal.app 标签页，但没有有效的钩子文件 → 绿色（空闲）
    if worst_state == "gray" and terminal_ttys:
        return "green", "", None

    return worst_state, worst_cmd, worst_tty


def _priority(state):
    return {"red": 3, "yellow": 2, "green": 1, "gray": 0}.get(state, 0)


# ─── 菜单栏应用 ──────────────────────────────────────────────


class TerminalTrafficLight(rumps.App):
    def __init__(self, icon_paths):
        self.icon_paths = icon_paths
        super().__init__(
            name="TerminalTrafficLight",
            title="",
            icon=icon_paths["gray"],
            quit_button=None,
        )

        self.current_state = "gray"
        self.current_command = ""
        self.current_tty = None
        self._blink_on = True

        # 菜单项
        self.mi_state = rumps.MenuItem("状态: ⚪ 无活动")
        self.mi_cmd = rumps.MenuItem("命令: 无")
        self.mi_tty = rumps.MenuItem("终端: 未检测到")
        self.mi_focus = rumps.MenuItem("切换到终端", callback=self._focus_terminal)

        self.menu = [
            self.mi_state,
            self.mi_cmd,
            self.mi_tty,
            None,
            self.mi_focus,
            None,
            rumps.MenuItem("关于", callback=self._about),
            rumps.MenuItem("退出", callback=self._quit, key="q"),
        ]

        # 每 0.5 秒触发（闪烁用），状态检测每秒一次
        self.timer = rumps.Timer(self._tick, 0.5)
        self.timer.start()
        self._detect_tick = 0  # 控制状态检测频率

    # ── 定时回调 ──

    def _tick(self, _sender):
        # 状态检测每秒一次（每两个 0.5s tick 检测一次）
        self._detect_tick += 1
        if self._detect_tick >= 2:
            self._detect_tick = 0
            state, cmd, tty = get_terminal_state()
            if state != self.current_state:
                self.current_state = state
                self._blink_on = True
            self.current_command = cmd
            self.current_tty = tty
            # 更新菜单文字
            state_labels = {
                "red": "🔴 需要回复",
                "yellow": "🟡 运行中",
                "green": "🟢 已完成",
                "gray": "⚪ 无活动",
            }
            self.mi_state.title = f"状态: {state_labels.get(self.current_state, self.current_state)}"
            self.mi_cmd.title = f"命令: {cmd or '无'}"
            self.mi_tty.title = f"终端: {tty or '未检测到'}"

        # 红灯闪烁：每 0.5 秒切换一次（比原 1 秒快 50%）
        if self.current_state == "red":
            self._blink_on = not self._blink_on
            self.icon = self.icon_paths["red"] if self._blink_on else self.icon_paths["gray"]
        else:
            self.icon = self.icon_paths[self.current_state]

    # ── 菜单回调 ──

    def _focus_terminal(self, _sender):
        """将 Terminal.app 带到前台。"""
        _run([
            "osascript", "-e",
            'tell application "Terminal" to activate',
        ])

    def _about(self, _sender):
        rumps.alert(
            title="Terminal Traffic Light",
            message=(
                "监控 Terminal.app 的运行状态\n\n"
                "🔴 红灯 = 需要回复\n"
                "🟡 黄灯 = 运行中\n"
                "🟢 绿灯 = 已完成"
            ),
        )

    def _quit(self, _sender):
        rumps.quit_application()


# ─── 入口 ────────────────────────────────────────────────────


def main():
    icon_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
    icon_paths = ensure_icons(icon_dir)

    app = TerminalTrafficLight(icon_paths)
    app.run()


if __name__ == "__main__":
    main()
