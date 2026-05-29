# Terminal Traffic Light - Shell 钩子
# 将此文件 source 到你的 .zshrc 中：
#   source /path/to/terminal-traffic-light/shell_hook.zsh
#
# 原理：
#   preexec: 命令开始执行前 → 写 "yellow:命令名" 到状态文件
#   precmd:  命令执行完毕后 → 写 "green" 到状态文件
#   这样无论在 Terminal.app、Qoder 还是 VS Code 终端都能检测

_TTL_STATE_DIR="$HOME/.terminal_traffic_light"

# 生成唯一会话 ID（兼容无 TTY 的环境如 Qoder）
if [[ -n "$TTY" ]]; then
    _TTL_SESSION_ID="${TTY:t}"  # 取 ttys001 而非 /dev/ttys001
else
    _TTL_SESSION_ID="session_$$"
fi

function _ttl_preexec() {
    local cmd="$1"
    local cmd_name="${cmd%% *}"
    cmd_name="${cmd_name##*/}"

    # 确定是红灯（需要回复）还是黄灯（运行中）
    local state="yellow"

    case "$cmd_name" in
        # 永远是红灯：这些命令只有交互模式，不执行文件
        vim|vi|nvim|nano|emacs|ed|micro|\
        less|more|most|\
        ssh|mosh|telnet|ftp|sftp|\
        gdb|lldb|\
        htop|btop|top|atop|\
        screen|tmux|lazygit|tig|\
        man|info|\
        mysql|psql|sqlite3|redis-cli|mongosh|\
        crontab|visudo|\
        mail|mutt|neomutt|\
        claude|chatgpt|aider|codex)
            state="red"
            ;;
        # 可能是 REPL 也可能执行脚本：无参数 = 红灯，有参数 = 黄灯
        python|python3|python2|ipython|ipython3|\
        node|ruby|irb|pry|lua|bc|julia|\
        rails|jupyter)
            # 去掉命令名后看剩余参数
            # -c（执行代码串）、-m（执行模块）等视为执行模式 → 黄灯
            # 脚本文件名（不以-开头）也是执行模式 → 黄灯
            # 完全没有参数，或只有 --version/--help 等纯信息 flag → 红灯（REPL）
            local rest="${cmd#$cmd_name}"
            local has_exec_arg=0
            for arg in ${=rest}; do
                if [[ "$arg" != -* ]]; then
                    # 非 flag 参数（脚本文件名等）
                    has_exec_arg=1
                    break
                elif [[ "$arg" == -c || "$arg" == -m || "$arg" == -e ]]; then
                    # 执行代码/模块的 flag
                    has_exec_arg=1
                    break
                fi
            done
            if (( has_exec_arg == 0 )); then
                state="red"
            fi
            ;;
    esac

    echo "${state}:$cmd" > "$_TTL_STATE_DIR/$_TTL_SESSION_ID"
}

function _ttl_precmd() {
    echo "green" > "$_TTL_STATE_DIR/$_TTL_SESSION_ID"
}

function _ttl_exit() {
    # shell 退出时立即标记为 gray，让指示灯不再计入此 tab
    rm -f "$_TTL_STATE_DIR/$_TTL_SESSION_ID"
}

# 创建状态目录
mkdir -p "$_TTL_STATE_DIR"

# 注册钩子（兼容用户已有的钩子）
autoload -Uz add-zsh-hook
add-zsh-hook preexec _ttl_preexec
add-zsh-hook precmd _ttl_precmd
zshexit() { _ttl_exit; }
