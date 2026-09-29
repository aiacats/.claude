"""OBS を obs-websocket 越しに操作する。

使い方:
    python obs.py status          … つながるか・録画中かを見る
    python obs.py start           … 録画開始
    python obs.py stop            … 録画停止（保存されたファイルのパスを出す）

認証は OBS の設定ファイルにあるパスワードを読む（引数で渡さない）。
"""

import asyncio
import base64
import hashlib
import io
import json
import os
import sys

import websockets

# 応答にウィンドウ名などの非 ASCII（✳ など）が入ると、cp932 の標準出力では print が落ちる
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CONFIG = os.path.expandvars(
    r"%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json"
)


def settings() -> dict:
    return json.load(io.open(CONFIG, encoding="utf-8"))


def auth_string(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


async def call(request_type: str, data: dict | None = None) -> dict:
    cfg = settings()
    url = f"ws://127.0.0.1:{cfg.get('server_port', 4455)}"
    async with websockets.connect(url, open_timeout=10) as ws:
        hello = json.loads(await ws.recv())
        identify = {"op": 1, "d": {"rpcVersion": 1}}
        auth = hello["d"].get("authentication")
        if auth:
            identify["d"]["authentication"] = auth_string(
                cfg.get("server_password", ""), auth["salt"], auth["challenge"]
            )
        await ws.send(json.dumps(identify))
        await ws.recv()  # Identified
        await ws.send(
            json.dumps(
                {
                    "op": 6,
                    "d": {
                        "requestType": request_type,
                        "requestId": "ftpdeck",
                        "requestData": data or {},
                    },
                }
            )
        )
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("op") == 7:
                return msg["d"]


async def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "status"
    if what == "status":
        version = await call("GetVersion")
        rec = await call("GetRecordStatus")
        print("OBS", version["responseData"]["obsVersion"], "/ websocket", version["responseData"]["obsWebSocketVersion"])
        print("録画中:", rec["responseData"]["outputActive"])
        return 0
    if what == "start":
        res = await call("StartRecord")
        print("開始:", res["requestStatus"])
        return 0 if res["requestStatus"]["result"] else 1
    if what == "stop":
        res = await call("StopRecord")
        path = res.get("responseData", {}).get("outputPath")
        print("停止:", res["requestStatus"], "→", path)
        return 0 if res["requestStatus"]["result"] else 1
    if what == "call":
        # 任意の obs-websocket リクエスト。シーンやソースの用意に使う（例は SKILL.md）
        if len(sys.argv) < 3:
            print("使い方: obs.py call <RequestType> [JSON]")
            return 1
        data = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
        res = await call(sys.argv[2], data)
        print(json.dumps({"status": res["requestStatus"], "data": res.get("responseData")}, ensure_ascii=False))
        return 0 if res["requestStatus"]["result"] else 1
    print("使い方: obs.py [status|start|stop|call <RequestType> [JSON]]")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
