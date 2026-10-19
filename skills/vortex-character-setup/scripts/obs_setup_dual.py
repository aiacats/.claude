"""OBS を「FHD 2 画面（左半分を録る）」の構成にする。vortex-timeline-export の obs_rec.py setup-dual の包み。

    python obs_setup_dual.py [--top 147]

- モニタ ID は主モニタ（Windows の \\\\.\\DISPLAY1 など Primary）から EnumDisplayDevices(EDD_GET_DEVICE_INTERFACE_NAME) で取る。
  obs_rec.py restore はキャプチャ入力を消すので、setup のたびに ID が要る。
- Git Bash から --monitor-id '\\\\?\\DISPLAY#...' を渡すと先頭の \\\\ が 1 つに畳まれて画が真っ黒になるため、
  ここでは subprocess へ引数リストで直接渡す。
- 最後に obs_rec.py shot で 1 枚撮り、真っ黒（輝度が全部 0）なら失敗として終了コード 1 を返す。
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
OBS_REC = os.path.expanduser(r"~/.claude/skills/vortex-timeline-export/scripts/obs_rec.py")


class DISPLAY_DEVICEW(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("DeviceName", wt.WCHAR * 32), ("DeviceString", wt.WCHAR * 128),
                ("StateFlags", wt.DWORD), ("DeviceID", wt.WCHAR * 128), ("DeviceKey", wt.WCHAR * 128)]


DISPLAY_DEVICE_PRIMARY_DEVICE = 0x4
EDD_GET_DEVICE_INTERFACE_NAME = 0x1


def primary_monitor_id():
    user32 = ctypes.windll.user32
    i = 0
    while True:
        adapter = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(adapter), 0):
            break
        i += 1
        if not adapter.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE:
            continue
        mon = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
        if user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(mon), EDD_GET_DEVICE_INTERFACE_NAME):
            return adapter.DeviceName, mon.DeviceID
    raise SystemExit("primary monitor (not found)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=147, help="Game View の描画の上端（PlaceDisplay(n, 0, 100, 1920, 1101) なら 147）")
    a = ap.parse_args()

    name, mid = primary_monitor_id()
    print(f"primary monitor: {name} {mid}")
    r = subprocess.run([sys.executable, OBS_REC, "setup-dual", "--top", str(a.top), "--monitor-id", mid],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout.strip() or r.stderr.strip())
    if r.returncode != 0:
        sys.exit(r.returncode)

    shot = os.path.join(tempfile.gettempdir(), "obs_setup_dual_check.png")
    subprocess.run([sys.executable, OBS_REC, "shot", shot], capture_output=True)
    from PIL import Image
    lo, hi = Image.open(shot).convert("L").getextrema()
    print(f"check shot: {shot} luma={lo}-{hi}")
    if hi == 0:
        print("NG: 画が真っ黒。モニタ ID か、キャプチャ対象のデスクトップを確かめる")
        sys.exit(1)


if __name__ == "__main__":
    main()
