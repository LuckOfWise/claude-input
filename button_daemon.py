#!/usr/bin/env python3
import subprocess, os, sys, threading, fcntl
import Quartz
from CoreFoundation import CFRunLoopRun

# macOSキーコード: F13=105, F14=107, F15=113
KEY_MAP = {
    105: '1',  # F13
    107: '2',  # F14
}
FOCUS_KEY = 113  # F15: Claude Codeターミナルをフォーカス

def get_own_pty():
    try:
        return os.ttyname(0)
    except OSError:
        return None

def find_claude_processes():
    own_pty = get_own_pty()
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    processes = []
    for line in result.stdout.splitlines()[1:]:
        fields = line.split(None, 10)
        if len(fields) < 11:
            continue
        cmd_full = fields[10]
        cmd_parts = cmd_full.split()
        cmd_name = os.path.basename(cmd_parts[0])
        is_claude_binary = cmd_name == 'claude'
        is_claude_node = cmd_name == 'node' and any('/claude' in p or p == 'claude' for p in cmd_parts[1:])
        if not (is_claude_binary or is_claude_node):
            continue
        pid = fields[1]
        tty = subprocess.run(
            ['ps', '-p', pid, '-o', 'tty='],
            capture_output=True, text=True
        ).stdout.strip()
        if not tty or tty == '??':
            continue
        pty_path = f'/dev/{tty}'
        if own_pty and pty_path == own_pty:
            continue
        processes.append({'pty': pty_path})
    return processes

TIOCSTI = 0x80017472  # macOS: ioctl で入力バッファに文字を挿入

def send_key(key_char):
    processes = find_claude_processes()
    if not processes:
        print("Claude Codeが見つかりません")
        return
    pty_path = processes[0]['pty']
    try:
        fd = os.open(pty_path, os.O_RDWR | os.O_NOCTTY)
        for c in key_char.encode():
            fcntl.ioctl(fd, TIOCSTI, bytes([c]))
        os.close(fd)
        print(f"送信: {key_char} → {pty_path}")
    except Exception as e:
        print(f"エラー: {e}")

def focus_claude_terminal():
    processes = find_claude_processes()
    if not processes:
        print("Claude Codeが見つかりません")
        return
    pty_path = processes[0]['pty']
    script = f'''
tell application "Terminal"
    repeat with w in windows
        repeat with t in tabs of w
            if tty of t is "{pty_path}" then
                activate
                set frontmost of w to true
                set selected tab of w to t
                exit repeat
            end if
        end repeat
    end repeat
end tell
'''
    r = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"フォーカスエラー: {r.stderr.strip()}")
    else:
        print(f"フォーカス: {pty_path}")

def event_callback(proxy, event_type, event, refcon):
    if event_type == Quartz.kCGEventKeyDown:
        keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        if keycode in KEY_MAP:
            key_char = KEY_MAP[keycode]
            threading.Thread(target=send_key, args=(key_char,), daemon=True).start()
            return None  # このキーイベントだけ抑制
        elif keycode == FOCUS_KEY:
            threading.Thread(target=focus_claude_terminal, daemon=True).start()
            return None  # F15イベントを抑制
    return event  # 他のキーはそのまま通す

tap = Quartz.CGEventTapCreate(
    Quartz.kCGSessionEventTap,
    Quartz.kCGHeadInsertEventTap,
    Quartz.kCGEventTapOptionDefault,
    Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
    event_callback,
    None
)

if tap is None:
    print("アクセシビリティ権限が必要です: システム環境設定 → プライバシーとセキュリティ → アクセシビリティ")
    exit(1)

run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), run_loop_source, Quartz.kCFRunLoopDefaultMode)
Quartz.CGEventTapEnable(tap, True)

print("デーモン起動中... F13/F14/F15を監視")
CFRunLoopRun()
