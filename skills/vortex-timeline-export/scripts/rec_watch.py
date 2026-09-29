# OBS 録画中の見張り。30 秒ごとに Unity のタイトル・録画の伸び・OBS の落ちフレーム・GPU を記録し、
# 異常（Unity Error / 録画が伸びない / Unity が消えた）を見つけたら理由を出して終わる。
# 期限（秒）に達したら正常終了する。
#
#   python rec_watch.py <Unity の PID> <期限の秒数（Timeline の尺）>
#
# run_in_background で投げ、Monitor で出力の末尾を 1 分おきに読む。
# 終了コード: 0=期限まで異常なし / 2=Unity が消えた / 3=Unity Error / 4=録画が止まった / 5=ファイルが伸びない
import json
import os
import subprocess
import sys
import time

OBS = os.path.expanduser(r"~/.claude/skills/screen-recording/scripts/obs.py")
UNITY_PID = int(sys.argv[1])
DEADLINE = time.time() + float(sys.argv[2])
INTERVAL = 30  # 録画が 5 分続くか見る粒度。フリーズは 1 回の間隔で検知できれば足りる


def obs(req):
    out = subprocess.run([sys.executable, OBS, "call", req, "{}"], capture_output=True, text=True).stdout.strip().splitlines()
    try:
        return json.loads(out[-1]).get("data") or {}
    except Exception:
        return {}


def ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True).stdout.strip()


last_bytes = -1
while time.time() < DEADLINE:
    title = ps(f"(Get-Process -Id {UNITY_PID} -ErrorAction SilentlyContinue).MainWindowTitle")
    rec = obs("GetRecordStatus")
    stats = obs("GetStats")
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    b = rec.get("outputBytes", -1)
    print(f"{time.strftime('%H:%M:%S')} rec={rec.get('outputActive')} {rec.get('outputTimecode')} "
          f"MB={b / 1e6:.0f} renderSkip={stats.get('renderSkippedFrames')} outSkip={stats.get('outputSkippedFrames')} "
          f"fps={stats.get('activeFps', 0):.1f} gpu=[{gpu}] unity='{title[:40]}'", flush=True)
    if not title:
        print("ABORT: Unity プロセスが無い", flush=True); sys.exit(2)
    if "Error" in title:
        print("ABORT: Unity Error", flush=True); sys.exit(3)
    if not rec.get("outputActive"):
        print("ABORT: 録画が止まっている", flush=True); sys.exit(4)
    if b == last_bytes:
        print("ABORT: 録画ファイルが伸びていない", flush=True); sys.exit(5)
    last_bytes = b
    time.sleep(INTERVAL)
print("DONE: 期限まで異常なし", flush=True)
