"""Dropbox の共有フォルダのリンク（scl/fo/...）の中身を一覧する・1 ファイルを落とす・1 ファイルの URL を得る。

収録データ（OBS プレビュー・2Mix・HyperDeck の番組映像）は共有フォルダで渡されることが多い。全体（数百 GB）は落とさず、要る物だけを取る。
トークンは rclone の dropbox リモートのものを使い、画面には出さない（期限切れなら rclone が更新する）。

使い方:
  python dbx_shared.py list <共有リンク> [サブパス]          サブパスは "OBS" や "OBS/t003_OK.mp4"（先頭の / はこちらで補う。
                                                            Git Bash で "/OBS" と書くと C:/Program Files/Git/OBS に書き換えられて 400 になる）
  python dbx_shared.py get  <共有リンク> <サブパス> <保存先>   ファイル全体を落とす
  python dbx_shared.py url  <共有リンク> <サブパス>            そのファイル単体の共有 URL（dl=1。ffmpeg の -ss で区間だけ読める）

共有フォルダのファイルを get_shared_link_file に Range を付けて読むと、本体が返らず止まる（大きな mov。traps-catalog/cloud-sync.md）。
区間だけ読むなら url で単体の URL を得て、ffmpeg に渡す（奥の位置も数秒で読めた。2026-10-14 HyperDeck_SWMain）。
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


def token():
    subprocess.run(["rclone", "about", "dropbox:"], capture_output=True)  # 期限切れのトークンを更新させる
    cfg = json.loads(subprocess.run(["rclone", "config", "dump"], capture_output=True, text=True, check=True).stdout)
    return json.loads(cfg["dropbox"]["token"])["access_token"]


def api(url, body, tok, content=False):
    if content:
        req = urllib.request.Request(url, method="POST", headers={
            "Authorization": "Bearer " + tok, "Dropbox-API-Arg": json.dumps(body, ensure_ascii=True)})
    else:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")[:400]
        hint = "  (pass the subpath without the leading '/': Git Bash rewrites '/xxx' to C:/Program Files/Git/xxx)" if "bad path" in msg else ""
        sys.exit(f"HTTP {e.code}: {msg}{hint}")


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, link = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 3 and sys.argv[3] and not sys.argv[3].startswith("/"):
        sys.argv[3] = "/" + sys.argv[3]  # サブパス（3 番目の引数）だけ
    tok = token()
    if cmd == "list":
        path = sys.argv[3] if len(sys.argv) > 3 else ""
        r = json.load(api("https://api.dropboxapi.com/2/files/list_folder", {"path": path, "shared_link": {"url": link}}, tok))
        while True:
            for e in r["entries"]:
                print(f"{e['.tag']:7s} {e.get('size', 0) / 1e6:12.1f} MB  {e.get('client_modified', ''):20s}  {e['name']}")
            if not r.get("has_more"):
                break
            r = json.load(api("https://api.dropboxapi.com/2/files/list_folder/continue", {"cursor": r["cursor"]}, tok))
    elif cmd == "get":
        sub, out = sys.argv[3], sys.argv[4]
        with api("https://content.dropboxapi.com/2/sharing/get_shared_link_file", {"url": link, "path": sub}, tok, True) as resp, \
                open(out, "wb") as f:
            while True:
                b = resp.read(1 << 22)
                if not b:
                    break
                f.write(b)
        print("saved", out)
    elif cmd == "url":
        r = json.load(api("https://api.dropboxapi.com/2/sharing/get_shared_link_metadata", {"url": link, "path": sys.argv[3]}, tok))
        u = r.get("url", "")
        print(u.replace("dl=0", "dl=1") if "dl=0" in u else u)
        print(r.get("name"), r.get("size"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
