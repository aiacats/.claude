# OBS を「Unity の Game View を画面録画する」ための構成にし、終わったら元に戻す。
#
#   python obs_rec.py setup-4k   [--monitor-id ID]            … 4K 1 画面（キャンバス 3840x2160、モニタ全体を等倍）
#   python obs_rec.py setup-dual --top 147 [--monitor-id ID]  … FHD 2 画面を左右に（キャンバス 3840x1080）
#   python obs_rec.py shot <out.png> [--scene NAME]           … 今の出力を PNG に保存
#   python obs_rec.py edges <png>                             … 上端・下端の行に Game View のツールバーやタスクバーが残っていないか
#   python obs_rec.py restore                                 … setup 前の状態へ戻す（シーン・キャンバス・作った入力を消す）
#
# setup は最初の 1 回だけ「元の状態」を %TEMP%\obs_rec_state.json に保存し、restore がそれを読む。
# 録画の開始・停止は screen-recording スキルの obs.py start / stop を使う。
import argparse
import asyncio
import importlib.util
import json
import os
import sys

OBS_PY = os.path.expanduser(r"~/.claude/skills/screen-recording/scripts/obs.py")
STATE = os.path.join(os.environ.get("TEMP", "."), "obs_rec_state.json")
SRC = "ClaudeRec_Monitor"
SCENE_4K = "ClaudeRec_4K"
SCENE_DUAL = "ClaudeRec_Dual"

# Unity の窓の枠は R=G=B の灰色で、値は次のどれか（2026-09-27 に 4K で実測）:
#   タイトルバー 193 / タブ 40・41 / 区切り 16・17・28 / Game View のツールバー 48・49
# タスクバー（Windows 11 ダーク）はほぼ灰色の 30〜40（例 35,34,33）。
# 場面の白い板は (230,230,229)、黒い床は (4,10,15) のように値か色味で区別できる。
UNITY_CHROME = {193, 40, 41, 16, 17, 28, 48, 49}


def is_chrome(p):
    r, g, b = p
    if r == g == b and r in UNITY_CHROME:
        return "Unity の枠"
    if 30 <= r <= 40 and max(p) - min(p) <= 3:
        return "タスクバー"
    return None

spec = importlib.util.spec_from_file_location("obs", OBS_PY)
obs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(obs)


def call(req, data=None):
    res = asyncio.run(obs.call(req, data))
    status = res.get("requestStatus", res.get("status", {}))
    if not status.get("result", False):
        raise SystemExit(f"{req} 失敗: {status}")
    return res.get("responseData", res.get("data")) or {}


def save_state_once():
    if os.path.exists(STATE):
        return
    video = call("GetVideoSettings")
    scene = call("GetCurrentProgramScene")
    state = {"video": video, "sceneUuid": scene.get("currentProgramSceneUuid") or scene.get("sceneUuid"),
             "sceneName": scene.get("currentProgramSceneName") or scene.get("sceneName")}
    json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("元の状態を保存:", STATE, state["sceneName"], f'{video["baseWidth"]}x{video["baseHeight"]}')


def ensure_monitor(monitor_id):
    inputs = [i["inputName"] for i in call("GetInputList")["inputs"]]
    if SRC not in inputs and not monitor_id:
        raise SystemExit(f"{SRC} がまだ無い。初回は --monitor-id を渡す"
                         "（OBS の画面キャプチャのプロパティ、または既存の monitor_capture 入力の設定から取る）")
    return inputs


def ensure_scene(scene, monitor_id):
    inputs = ensure_monitor(monitor_id)
    names = [s["sceneName"] for s in call("GetSceneList")["scenes"]]
    if scene not in names:
        call("CreateScene", {"sceneName": scene})
    if SRC not in inputs:
        call("CreateInput", {"sceneName": scene, "inputName": SRC, "inputKind": "monitor_capture",
                             "inputSettings": {"monitor_id": monitor_id, "capture_cursor": False}})
    elif monitor_id:
        call("SetInputSettings", {"inputName": SRC, "inputSettings": {"monitor_id": monitor_id, "capture_cursor": False}})
    else:
        call("SetInputSettings", {"inputName": SRC, "inputSettings": {"capture_cursor": False}})
    items = call("GetSceneItemList", {"sceneName": scene})["sceneItems"]
    return items


def set_transform(scene, item_id, crop, pos, bounds):
    l, t, r, b = crop
    call("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item_id, "sceneItemTransform": {
        "cropLeft": l, "cropTop": t, "cropRight": r, "cropBottom": b,
        "positionX": pos[0], "positionY": pos[1],
        "boundsType": "OBS_BOUNDS_STRETCH", "boundsWidth": bounds[0], "boundsHeight": bounds[1]}})


def setup_4k(a):
    save_state_once()
    call("SetVideoSettings", {"baseWidth": 3840, "baseHeight": 2160, "outputWidth": 3840, "outputHeight": 2160})
    items = ensure_scene(SCENE_4K, a.monitor_id)
    item = items[0]["sceneItemId"] if items else call("CreateSceneItem", {"sceneName": SCENE_4K, "sourceName": SRC})["sceneItemId"]
    set_transform(SCENE_4K, item, (0, 0, 0, 0), (0, 0), (3840, 2160))
    call("SetCurrentProgramScene", {"sceneName": SCENE_4K})
    print("4K 1 画面にした:", SCENE_4K)


def setup_dual(a):
    # 左右に 1920x1080 の Game View を並べた 4K モニタから、それぞれの描画領域を切り出す。
    # --top は描画の上端の行（Game View を y=100 に置いたときの実測 147）。
    save_state_once()
    call("SetVideoSettings", {"baseWidth": 3840, "baseHeight": 1080, "outputWidth": 3840, "outputHeight": 1080})
    items = ensure_scene(SCENE_DUAL, a.monitor_id)
    ids = [i["sceneItemId"] for i in items]
    while len(ids) < 2:
        ids.append(call("CreateSceneItem", {"sceneName": SCENE_DUAL, "sourceName": SRC})["sceneItemId"])
    mon_w, mon_h = 3840, 2160
    top, bottom = a.top, a.top + 1080 - 1
    for item_id, x0, x1, pos_x in ((ids[0], 0, 1919, 0), (ids[1], 1920, 3839, 1920)):
        set_transform(SCENE_DUAL, item_id, (x0, top, mon_w - 1 - x1, mon_h - 1 - bottom), (pos_x, 0), (1920, 1080))
    call("SetCurrentProgramScene", {"sceneName": SCENE_DUAL})
    print("FHD 2 画面にした:", SCENE_DUAL, "top =", top)


def shot(a):
    scene = a.scene or call("GetCurrentProgramScene").get("currentProgramSceneName")
    call("SaveSourceScreenshot", {"sourceName": scene, "imageFormat": "png",
                                  "imageFilePath": os.path.abspath(a.out)})
    print("保存:", os.path.abspath(a.out))


def edges(a):
    from PIL import Image
    img = Image.open(a.png).convert("RGB")
    w, h = img.size
    bad = 0
    # 上端・下端から 2 行ずつ、横 480 点を見る。半分以上が枠の色なら、その行は Game View の外
    for y in (0, 1, h - 2, h - 1):
        row = [img.getpixel((x, y)) for x in range(0, w, max(1, w // 480))]
        kinds = [k for k in (is_chrome(p) for p in row) if k]
        flag = "OK"
        if len(kinds) > len(row) // 2:
            flag = max(set(kinds), key=kinds.count) + " が残っている"
            bad += 1
        print(f"y={y}: {flag}  ({len(kinds)}/{len(row)})")
    print("NG" if bad else "OK")
    return 1 if bad else 0


def restore(a):
    if not os.path.exists(STATE):
        raise SystemExit("保存された元の状態が無い（setup していない）")
    state = json.load(open(STATE, encoding="utf-8"))
    v = state["video"]
    call("SetVideoSettings", {k: v[k] for k in ("baseWidth", "baseHeight", "outputWidth", "outputHeight")})
    if state.get("sceneUuid"):
        call("SetCurrentProgramScene", {"sceneUuid": state["sceneUuid"]})
    else:
        call("SetCurrentProgramScene", {"sceneName": state["sceneName"]})
    names = [s["sceneName"] for s in call("GetSceneList")["scenes"]]
    for scene in (SCENE_4K, SCENE_DUAL):
        if scene in names:
            call("RemoveScene", {"sceneName": scene})
    if SRC in [i["inputName"] for i in call("GetInputList")["inputs"]]:
        call("RemoveInput", {"inputName": SRC})
    os.remove(STATE)
    print("元に戻した:", state["sceneName"], f'{v["baseWidth"]}x{v["baseHeight"]}')


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("setup-4k"); p.add_argument("--monitor-id"); p.set_defaults(fn=setup_4k)
p = sub.add_parser("setup-dual"); p.add_argument("--monitor-id"); p.add_argument("--top", type=int, default=147); p.set_defaults(fn=setup_dual)
p = sub.add_parser("shot"); p.add_argument("out"); p.add_argument("--scene"); p.set_defaults(fn=shot)
p = sub.add_parser("edges"); p.add_argument("png"); p.set_defaults(fn=edges)
p = sub.add_parser("restore"); p.set_defaults(fn=restore)
args = ap.parse_args()
sys.exit(args.fn(args) or 0)
