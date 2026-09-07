#!/usr/bin/env python3
"""packages-lock.json から自作 Unity MCP パッケージの痕跡を取り除く git clean フィルタ。

Packages/com.aiacats.unity-mcp は各自のローカル環境にだけ置く embedded パッケージで
.gitignore 済み。しかし Unity は packages-lock.json には必ず書き込むため、
そのままだとロックファイル経由でリポジトリへ漏れる。

git の clean フィルタとして働き、作業ツリーはそのまま・インデックスに入る内容だけを掃除する。
設定は各自のクローンローカル（.git/info/attributes + git config --local）で行うため、
他のメンバーには一切影響しない。

失敗時は入力をそのまま返す。フィルタが落ちると add した内容が壊れるため。
"""
import json
import sys

PACKAGE = "com.aiacats.unity-mcp"


def strip(text):
    lock = json.loads(text)
    deps = lock.get("dependencies")
    if not isinstance(deps, dict) or PACKAGE not in deps:
        return text

    del deps[PACKAGE]

    # MCP だけが要求していた間接依存（newtonsoft-json 等）も道連れに消す。
    # depth 0 は manifest.json に載っている本物の依存なので触らない。
    changed = True
    while changed:
        changed = False
        required = set()
        for entry in deps.values():
            required.update((entry.get("dependencies") or {}).keys())

        for name in list(deps.keys()):
            if deps[name].get("depth", 0) > 0 and name not in required:
                del deps[name]
                changed = True

    # Unity が書く体裁（2 スペース + 末尾改行）に合わせる
    return json.dumps(lock, indent=2, ensure_ascii=False) + "\n"


def main():
    # Windows の Python は text mode の stdout で改行を CRLF に変換してしまい、
    # ファイル全体が差分になる。入出力ともバイトで扱う。
    raw = sys.stdin.buffer.read()
    try:
        out = strip(raw.decode("utf-8")).encode("utf-8")
    except Exception:
        out = raw
    sys.stdout.buffer.write(out)


if __name__ == "__main__":
    main()
