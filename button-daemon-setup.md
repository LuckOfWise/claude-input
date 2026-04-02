# Claude Code 物理ボタン入力デバイス セットアップ記録

## 概要

Claude Codeの選択肢（1/2/3）をフォーカスに関係なく物理ボタンで入力できるシステムを構築する。

## 最終構成

```
PCsensor MK321（物理ボタン3個）
F13/F14/F15として送信（Bluetooth）
    ↓
Mac側 button_daemon.py（常駐）
F13/F14/F15をフックして 1/2/3 に変換
    ↓
Claude CodeのPTYに直接書き込み
```

## ハードウェア

- **PCsensor MK321**（3キーワイヤレスマクロパッド）
  - Bluetooth接続
  - 充電式（USB-C）
  - Amazonで約3,000〜4,000円

## ソフトウェアセットアップ

### 1. ElfKeyでボタンをF13/F14/F15に設定

1. [software.pcsensor.com](http://software.pcsensor.com) からElfKey（Mac版）をダウンロード
2. MK321をUSB-Cケーブル（データ通信対応）で接続
3. 本体のコネクトボタンを押してライトを青（USBモード）に切り替え
4. ElfKeyでデバイスが認識されたら各ボタンを設定：
   - ボタン1 → `F13`
   - ボタン2 → `F14`
   - ボタン3 → `F15`
5. 保存後、Bluetoothモードに切り替えてMacとペアリング

> **注意**: USBケーブルはデータ通信対応のものを使うこと。充電専用ケーブルではデバイスが認識されない。

### 2. Mac側デーモンのセットアップ

```bash
pip3 install pynput
```

### 3. button_daemon.py

```python
#!/usr/bin/env python3
from pynput import keyboard
import subprocess, os

KEY_MAP = {
    keyboard.Key.f13: '1',
    keyboard.Key.f14: '2',
    keyboard.Key.f15: '3',
}

def find_claude_processes():
    """nodeプロセスでclaudeを実行しているものを検索。自分自身のPTYは除外。"""
    try:
        my_pty = os.ttyname(0)
    except Exception:
        my_pty = None

    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    processes = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        cmd = parts[10]
        # nodeプロセスでclaudeが含まれるものだけ対象
        if 'node' not in parts[10].split()[0]:
            continue
        if 'claude' not in cmd:
            continue
        if 'grep' in cmd:
            continue

        pid = parts[1]
        cwd_out = subprocess.run(
            ['lsof', '-p', pid, '-d', 'cwd', '-Fn'],
            capture_output=True, text=True
        ).stdout
        cwd = next((l[1:] for l in cwd_out.splitlines() if l.startswith('n')), '')
        tty = subprocess.run(
            ['ps', '-p', pid, '-o', 'tty='],
            capture_output=True, text=True
        ).stdout.strip()
        if not tty or tty == '??':
            continue

        pty = f'/dev/{tty}'
        if pty == my_pty:
            continue  # 自分自身のPTYは除外

        processes.append({
            'pty': pty,
            'project': os.path.basename(cwd) or f'PID:{pid}'
        })
    return processes

def send_key(key_char):
    processes = find_claude_processes()
    if not processes:
        print("Claude Codeが見つかりません")
        return
    target = processes[0]
    try:
        fd = os.open(target['pty'], os.O_WRONLY | os.O_NOCTTY)
        os.write(fd, (key_char + '\n').encode())
        os.close(fd)
        print(f"送信: {key_char} → {target['project']}")
    except Exception as e:
        print(f"エラー: {e}")

def on_press(key):
    if key in KEY_MAP:
        send_key(KEY_MAP[key])
        # return Falseしない（イベントを消費しない）

with keyboard.Listener(on_press=on_press, suppress=False) as listener:
    print("デーモン起動中... F13/F14/F15を監視")
    listener.join()
```

### 4. アクセシビリティ権限の付与

システム設定 → プライバシーとセキュリティ → アクセシビリティ → Terminal.app を許可

### 5. 起動

デーモンはClaude Codeとは**別のターミナルウィンドウ**で起動すること。

```bash
python3 button_daemon.py
```

### 6. 自動起動（任意）

```bash
cat > ~/Library/LaunchAgents/com.local.buttondaemon.plist << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.local.buttondaemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/button_daemon.py</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.local.buttondaemon.plist
```

## トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| ElfKeyがデバイスを認識しない | 充電専用ケーブルを使っている / USBモードになっていない | データ通信対応ケーブルに変更 / コネクトボタンでライトを青に切り替え |
| デーモンがすぐ終了する | アクセシビリティ権限がない | システム設定で権限を付与して再起動 |
| Macキーボードが効かなくなる | `suppress=True`またはon_pressで`return False`している | `suppress=False`に変更、`return False`を削除 |
| 誤ったターミナルに送信される | デーモン自身のPTYや別プロセスを誤検知 | `os.ttyname(0)`で自PTYを除外、nodeプロセスに絞り込む |
| `^[[25~`などが送信される | F13のエスケープシーケンスがそのまま届いている | pynputで受け取った後に`1`/`2`/`3`の文字列を送信する |

## 未解決・今後の課題

- Claude Codeを複数同時起動している場合の送信先選択（プロジェクト名で選べるUIの追加）
