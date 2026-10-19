"""Timeline（.playable）のトラックとクリップを一覧にする（Unity 不要）。

トラックごとに、グループ・種類（スクリプト名）・ミュート、クリップごとに 開始・長さ・終わり・ClipIn・速度・名前・参照しているアセットのパス、
アニメーションなら Foot IK / Remove Start Offset を出す。時刻合わせで「今の置き方」を読むのに使う。

使い方: python tl_dump.py <playable>... [--root <Unity プロジェクト>] [--extra <GUID を引く追加のフォルダ>...]
  --root を省くと、playable の上の Assets の親をプロジェクトとみなす。GUID → パスは Assets・Packages・Library/PackageCache と --extra を探す
"""
import argparse
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
HDR = re.compile(r"(?m)^--- !u!(\d+) &(-?\d+).*$")


def guid_map(dirs, guids):
    """guids（GUID の集合）だけを .meta から引く。.meta を 1 本ずつ開くと数万本で数分かかる（Windows）ので、git grep に探させる
    （--no-index なら git の管理外のフォルダ = Library/PackageCache も探せる）。"""
    import subprocess
    out, todo = {}, set(guids)
    for root in dirs:
        if not todo or not os.path.isdir(root):
            continue
        args = ["git", "-C", root, "grep", "--no-index", "-I", "-F", "--no-color"]
        for g in todo:
            args += ["-e", "guid: " + g]
        r = subprocess.run(args + ["--", "*.meta"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        for line in r.stdout.splitlines():
            path, _, rest = line.partition(":guid: ")
            g = rest.strip()[:32]
            if g in todo and path.endswith(".meta"):
                out[g] = os.path.join(root, path[:-5])
                todo.discard(g)
    return out


def field(body, name):
    m = re.search(rf"(?m)^\s*{name}: (.*?)\r?$", body)
    return m.group(1) if m else None


def dump(path, g2p, project):
    text = open(path, encoding="utf-8").read()
    ms = list(HDR.finditer(text))
    objs = {}
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        objs[m.group(2)] = text[m.end():end]

    def rel(guid):
        p = g2p.get(guid)
        if p is None:
            return guid
        p = os.path.relpath(p, project)
        return p.replace("\\", "/")

    def script(body):
        g = re.search(r"m_Script: \{fileID: -?\d+, guid: ([0-9a-f]{32})", body)
        return os.path.basename(g2p[g.group(1)])[:-3] if g and g.group(1) in g2p else "?"

    def group_path(body):
        names, cur = [], field(body, "m_Parent")
        for _ in range(8):
            fid = re.search(r"fileID: (-?\d+)", cur or "")
            if not fid or fid.group(1) not in objs:
                break
            b = objs[fid.group(1)]
            if field(b, "m_Parent") is None and "m_Tracks" in b and "m_Clips" not in b and script(b) == "TimelineAsset":
                break
            # グループごとミュートされていると、中のトラックは自分の m_Muted が 0 でも鳴らない（春猿火の DMX・Facial など）
            names.append((field(b, "m_Name") or "?") + (" MUTED" if field(b, "m_Muted") == "1" else ""))
            cur = field(b, "m_Parent")
        return "/".join(reversed(names))

    def children(body, key):
        m = re.search(rf"(?m)^  {key}:\r?\n((?:  - \{{fileID: -?\d+\}}\r?\n)*)", body)
        return re.findall(r"fileID: (-?\d+)", m.group(1)) if m else []

    # Timeline の表示順: TimelineAsset の m_Tracks を上から、グループは m_Children を入れ子でたどる
    root = next((b for b in objs.values() if "  m_Tracks:" in b), "")
    ordered = []

    def walk(ids):
        for i in ids:
            if i in objs and i not in ordered:
                ordered.append(i)
                walk(children(objs[i], "m_Children"))
    walk(children(root, "m_Tracks"))
    ordered += [k for k, b in objs.items() if "  m_Clips:" in b and k not in ordered]

    print("=" * 100)
    print(os.path.basename(path))
    for fid in ordered:
        body = objs[fid]
        if "  m_Clips:" not in body or script(body) == "GroupTrack":
            continue
        muted = field(body, "m_Muted")
        grp = group_path(body)
        print(f"-- [{grp}] {field(body, 'm_Name')}  ({script(body)}){'  MUTED' if muted == '1' else ''}")
        clips = body.split("  m_Clips:", 1)[1]
        end = re.search(r"\n  m_(?!Version)\w+:", clips)
        clips = clips[:end.start()] if end else clips
        for c in re.split(r"\n  - m_Version", clips):
            st = re.search(r"m_Start: ([\d.eE+-]+)", c)
            if not st:
                continue
            num = lambda k: float((re.search(k + r": ([\d.eE+-]+)", c) or [None, "nan"])[1])
            start, dur = float(st.group(1)), num("m_Duration")
            name = field(c, "m_DisplayName") or ""
            asset = re.search(r"m_Asset: \{fileID: (-?\d+)", c)
            src = ""
            if asset and asset.group(1) in objs:
                ab = objs[asset.group(1)]
                refs = [rel(g) for g in re.findall(r"guid: ([0-9a-f]{32})", ab)
                        if not g.startswith("0000") and g != re.search(r"m_Script: \{fileID: -?\d+, guid: ([0-9a-f]{32})", ab).group(1)]
                src = ", ".join(dict.fromkeys(refs))
                flags = []
                for k in ("m_ApplyFootIK", "m_RemoveStartOffset", "m_Loop"):
                    v = field(ab, k)
                    if v is not None:
                        flags.append(f"{k[2:]}={v}")
                extra = re.findall(r"(?m)^  (_?\w*(?:[Oo]ffset|[Ii]ndex|[Ll]evel|[Ss]peed|[Ee]lement)\w*): ([^\n{]+?)\r?$", ab)
                flags += [f"{k}={v.strip()}" for k, v in extra[:6] if k not in ("m_ApplyFootIK", "m_RemoveStartOffset")]
                if flags:
                    src += "  [" + " ".join(flags) + "]"
            print(f"   {start:10.4f} → {start + dur:10.4f} (dur {dur:9.4f}) clipIn {num('m_ClipIn'):8.4f} ts {num('m_TimeScale'):.7g}"
                  f"  {name} | {src}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("playables", nargs="+")
    p.add_argument("--root")
    p.add_argument("--extra", nargs="*", default=[])
    a = p.parse_args()
    root = a.root
    if root is None:
        d = os.path.abspath(a.playables[0])
        while os.path.basename(d) != "Assets" and os.path.dirname(d) != d:
            d = os.path.dirname(d)
        root = os.path.dirname(d)
    guids = set()
    for pl in a.playables:
        guids |= set(re.findall(r"guid: ([0-9a-f]{32})", open(pl, encoding="utf-8").read()))
    g2p = guid_map([os.path.join(root, "Assets"), os.path.join(root, "Packages"),
                    os.path.join(root, "Library", "PackageCache")] + a.extra, guids)
    for pl in a.playables:
        dump(pl, g2p, root)


if __name__ == "__main__":
    main()
