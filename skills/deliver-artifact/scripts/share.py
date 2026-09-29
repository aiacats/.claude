"""成果物を共有用 Google Drive へ置いて、リンクを出す。

    python share.py put <ファイル> [名前] [--public]
                                            … 上げてリンクを返す（名前を省くと日付を付ける。
                                              名前に拡張子が無ければ、元の拡張子と日付を補う）
                                              既定は「所有者 + komao9160 + mao.komatsu」だけが見られる。
                                              --public でリンクを知っている全員へ広げる。
    python share.py public <名前>            … 既に上げたものをリンク共有（全員が閲覧）に広げる
    python share.py private <名前>           … リンク共有をやめて、既定の共有先だけに戻す
    python share.py list                    … 今置いてあるものを見る
    python share.py clean [日数]            … 指定日数より古いものを消す（既定 7 日）

rclone の `gdrive:` リモート（SessionControl のビルド配布で使っているもの）を、
共有フォルダの ID を差し替えて使う。ビルド成果物の置き場とは別。
"""

import datetime
import json
import os
import re
import subprocess
import sys

FOLDER_ID = "1CFs1lfQmZAyQL_txLZ8u7r-FAkF2hyY9"
REMOTE = f"gdrive,root_folder_id={FOLDER_ID}:"
# 既定の共有先。上げた本人（gdrive リモートの所有者）に加えて、このアカウントだけが見られる状態にする。
# リンクを知っている全員へ広げるのは put --public を明示したときだけ（ユーザー指示 2026-09-23）。
SHARE_WITH = ["komao9160@gmail.com", "mao.komatsu@pjblue.com"]


def run(args: list[str]) -> str:
    done = subprocess.run(["rclone", *args], capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        raise SystemExit(f"rclone {' '.join(args)} が失敗しました:\n{done.stderr.strip()}")
    return done.stdout.strip()


def _token() -> str:
    """rclone が保持している gdrive の access_token を借りる。"""
    cfg = json.loads(run(["config", "dump"]))
    return json.loads(cfg["gdrive"]["token"])["access_token"]


def _api(method: str, path: str, payload: dict | None = None) -> tuple[int, str]:
    import urllib.error
    import urllib.request

    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"https://www.googleapis.com/drive/v3{path}", data=data, method=method)
    req.add_header("Authorization", "Bearer " + _token())
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()[:300]


def file_id(name: str) -> str:
    items = json.loads(run(["lsjson", REMOTE]))
    for it in items:
        if it["Name"] == name and it.get("ID"):
            return it["ID"]
    raise SystemExit(f"ファイル ID を取れませんでした: {name}")


def grant(fid: str, public: bool) -> None:
    """既定は SHARE_WITH だけに閲覧を許す。public のときだけリンク共有にする。"""
    if public:
        status, body = _api("POST", f"/files/{fid}/permissions", {"type": "anyone", "role": "reader"})
        if status not in (200, 204):
            raise SystemExit(f"権限の付与に失敗しました（HTTP {status}）: {body}")
        print("[share] 共有先: 所有者 + リンクを知っている全員")
        return
    for mail in SHARE_WITH:
        status, body = _api(
            "POST",
            f"/files/{fid}/permissions?sendNotificationEmail=false",
            {"type": "user", "role": "reader", "emailAddress": mail},
        )
        if status not in (200, 204):
            raise SystemExit(f"{mail} への権限付与に失敗しました（HTTP {status}）: {body}")
    print("[share] 共有先: 所有者 + " + " / ".join(SHARE_WITH))


def dated_name(path: str) -> str:
    """日付を入れた名前にする。あとで古いものを機械的に選べるようにするため。"""
    base = os.path.basename(path)
    stem, ext = os.path.splitext(base)
    stamp = datetime.date.today().strftime("%y%m%d")
    if re.search(r"\d{6}", stem):
        return base
    return f"{stem}-{stamp}{ext}"


def target_name(path: str, name: str | None) -> str:
    """置くときの名前。名前を省けば日付を付ける。

    名前に拡張子が無ければ、元のファイルの拡張子と日付を補う。
    拡張子の無い名前で置くと、Drive からダウンロードしたときに種類が分からず、
    Unity などに読み込めないため（2026-09-24 に実際にやった）。
    """
    if not name:
        return dated_name(path)
    stem, ext = os.path.splitext(name)
    if ext:
        return name
    return dated_name(os.path.join(os.path.dirname(path), stem + os.path.splitext(path)[1]))


def put(path: str, name: str | None, public: bool = False) -> int:
    if not os.path.isfile(path):
        raise SystemExit(f"ファイルがありません: {path}")
    target = target_name(path, name)
    size = os.path.getsize(path) / 1048576
    print(f"[share] 上げます: {os.path.basename(path)} ({size:.1f} MB) → {target}")
    # rclone は名前を変えて置けないので、名前を変える場合は copyto を使う。
    run(["copyto", path, REMOTE + target])
    fid = file_id(target)
    grant(fid, public)
    print(f"[share] リンク: https://drive.google.com/open?id={fid}")
    return 0


def set_public(name: str, public: bool) -> int:
    """既に上げたファイルの公開範囲だけを変える（上げ直さないのでリンクは変わらない）。"""
    fid = file_id(name)
    if public:
        grant(fid, True)
    else:
        # anyone の権限 id は固定で anyoneWithLink。無ければ 404 が返るだけなので、それは成功扱い
        status, body = _api("DELETE", f"/files/{fid}/permissions/anyoneWithLink")
        if status not in (200, 204, 404):
            raise SystemExit(f"リンク共有の解除に失敗しました（HTTP {status}）: {body}")
        grant(fid, False)
    print(f"[share] リンク: https://drive.google.com/open?id={fid}")
    return 0


def sharing(name: str) -> list[str]:
    """今の共有先を人が読める形で返す（確認用）。"""
    status, body = _api("GET", f"/files/{file_id(name)}/permissions?fields=permissions(type,role,emailAddress)")
    if status != 200:
        raise SystemExit(f"共有先を取れませんでした（HTTP {status}）: {body}")
    out = []
    for perm in json.loads(body).get("permissions", []):
        who = perm.get("emailAddress") or perm.get("type")
        out.append(f"{who}（{perm.get('role')}）")
    return out


def listing() -> int:
    out = run(["lsjson", REMOTE])
    items = json.loads(out) if out else []
    if not items:
        print("[share] 共有フォルダは空です")
        return 0
    for it in sorted(items, key=lambda x: x.get("ModTime", "")):
        size = (it.get("Size") or 0) / 1048576
        print(f"  {it.get('ModTime', '')[:19]}  {size:8.1f} MB  {it['Name']}")
    return 0


def clean(days: int) -> int:
    """古い一時ファイルを消す。**消す前に必ず一覧を見せる**。"""
    out = run(["lsjson", REMOTE])
    items = json.loads(out) if out else []
    limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    old = []
    for it in items:
        when = it.get("ModTime")
        if not when:
            continue
        stamp = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
        if stamp < limit:
            old.append(it["Name"])
    if not old:
        print(f"[share] {days} 日より古いものはありません")
        return 0
    print(f"[share] {days} 日より古いもの {len(old)} 件:")
    for n in old:
        print(f"  - {n}")
    for n in old:
        run(["deletefile", REMOTE + n])
    print(f"[share] 削除しました（{len(old)} 件）")
    return 0


def main() -> int:
    what = sys.argv[1] if len(sys.argv) > 1 else "list"
    if what == "put":
        rest = [a for a in sys.argv[2:] if a != "--public"]
        public = "--public" in sys.argv[2:]
        if not rest:
            raise SystemExit("使い方: share.py put <ファイル> [名前] [--public]")
        return put(rest[0], rest[1] if len(rest) > 1 else None, public)
    if what in ("public", "private"):
        if len(sys.argv) < 3:
            raise SystemExit(f"使い方: share.py {what} <名前>")
        return set_public(sys.argv[2], what == "public")
    if what == "sharing":
        if len(sys.argv) < 3:
            raise SystemExit("使い方: share.py sharing <名前>")
        for line in sharing(sys.argv[2]):
            print("  " + line)
        return 0
    if what == "list":
        return listing()
    if what == "clean":
        return clean(int(sys.argv[2]) if len(sys.argv) > 2 else 7)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
