"""Unity のシーン（.unity / .prefab）を塊（--- !u!）単位で比べ、要る塊だけを元の版に足した版を作る。

Unity で保存すると、触っていない塊（実行時に作られたマテリアル・RenderTexture・ライトの値など）まで数千行書き換わる。
変えたかった塊だけを元の版（HEAD）へ写すと、差分が意図したものだけになる。

使い方:
  python scene_diff.py fromgit <rev> <repo 内のパス> <出力>          git の版を取り出す（LFS なら実体へ戻す）。cwd はリポジトリの中
  python scene_diff.py list <元> <保存後> [--assets <dir>...] [--class 114,1] [--grep 文字]
                                                                     増えた（NEW）・変わった（MOD）・消えた（GONE）塊の一覧
  python scene_diff.py show <シーン> <fileID か検索文字列>... [--lines 80]   塊の中身（fileID に名前を添える）
  python scene_diff.py take <元> <保存後> <出力> <fileID,fileID,...> [--drop fileID,...] [--no-closure]
                                                                     指定した塊だけ保存後の版から採る
  python scene_diff.py refcheck <シーン>...                           同じファイル内の参照が切れていないか・fileID の重複

take の振る舞い:
  - 指定した塊は、元にあれば置き換え、無ければ新しく足す（SceneRoots の手前）。
  - 足した・置き換えた塊が指す fileID が元に無く保存後にあれば、それも足す（参照の連鎖。--no-closure で止める）。
    保存後にも無ければ止める（壊れた版を書かない）。
  - 新しい Transform の親（m_Father）の m_Children に自分が無ければ、元の親の塊へ 1 行足す（親の他の変更は採らない）。
    親が 0（ルート）なら SceneRoots の m_Roots に足す。
  - --drop の塊は元から消し、親の m_Children・SceneRoots からも外す。他から参照が残れば refcheck で分かる。
"""
import argparse
import re
import sys

from unity_yaml import CLASS_NAMES, FATHER, TRANSFORM_CLASSES, Index, from_git, load, local_refs, parse, script_names, write

sys.stdout.reconfigure(encoding="utf-8")


def cmd_fromgit(a):
    text = from_git(a.rev, a.path)
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"written {a.out} ({len(text)} chars)")


def tail(s, n):
    """長いヒエラルキーパスは末尾（自分の名前の側）を残す。"""
    return s if len(s) <= n else "…" + s[-(n - 1):]


def changed_lines(old, new, n=3):
    o = set(old.splitlines())
    return [l.strip()[:60] for l in new.splitlines() if l not in o][:n]


def cmd_list(a):
    _, hd = load(a.head)
    _, nd = load(a.saved)
    names = script_names(a.assets) if a.assets else {}
    H, N = Index(hd, names), Index(nd, names)
    classes = set(a.cls.split(",")) if a.cls else None
    rows, summary = [], {}
    for d in nd:
        kind = "NEW" if d.fid not in H.by else ("MOD" if H.by[d.fid].text != d.text else None)
        if kind is None:
            continue
        summary[(kind, d.class_name)] = summary.get((kind, d.class_name), 0) + 1
        if classes and d.cls not in classes:
            continue
        if a.grep and a.grep not in d.text:
            continue
        label, where = N.describe(d)
        extra = "" if kind == "NEW" else " | ".join(changed_lines(H.by[d.fid].text, d.text))
        rows.append(f"{kind:4s} {d.fid:>22} {label[:28]:28s} {tail(where, 70):70s} {extra}")
    for d in hd:
        if d.fid not in N.by:
            summary[("GONE", d.class_name)] = summary.get(("GONE", d.class_name), 0) + 1
            if (not classes or d.cls in classes) and (not a.grep or a.grep in d.text):
                label, where = H.describe(d)
                rows.append(f"GONE {d.fid:>22} {label[:28]:28s} {tail(where, 70)}")
    print("summary:", ", ".join(f"{k[0]} {k[1]} {v}" for k, v in sorted(summary.items(), key=lambda x: (x[0][0], -x[1]))))
    print("\n".join(rows))


def cmd_show(a):
    _, docs = load(a.scene)
    ix = Index(docs)
    for key in a.keys:
        hits = [ix.by[key]] if re.fullmatch(r"-?\d+", key) and key in ix.by else [d for d in docs if key in d.text]
        if not hits:
            print(f"== {key}: not found")
        for d in hits[:20]:
            label, where = ix.describe(d)
            print(f"== {d.fid} {label} {where}")
            for line in d.text.splitlines()[:a.lines]:
                ids = [i for i in re.findall(r"\{fileID: (-?\d+)\}", line) if i != "0" and i in ix.by]
                note = "  # " + ", ".join(" ".join(ix.describe(ix.by[i], False)) for i in ids) if ids else ""
                print(line + note)


def add_child(doc_text, key, child):
    """「  m_Children:」/「  m_Roots:」のリストに child を足す（無ければ text をそのまま返す）。"""
    nl = "\r\n" if "\r\n" in doc_text else "\n"
    item = f"  - {{fileID: {child}}}{nl}"
    if item in doc_text:
        return doc_text
    m = re.search(rf"(?m)^  {key}:[ \t]*\[\][ \t]*\r?\n", doc_text)
    if m:
        return doc_text[:m.start()] + f"  {key}:{nl}{item}" + doc_text[m.end():]
    m = re.search(rf"(?m)^  {key}:[ \t]*\r?\n((?:  - \{{fileID: -?\d+\}}\r?\n)*)", doc_text)
    if not m:
        return None
    return doc_text[:m.end()] + item + doc_text[m.end():]


def remove_child(doc_text, child):
    out = re.sub(rf"(?m)^  - \{{fileID: {child}\}}\r?\n", "", doc_text)
    return re.sub(r"(?m)^(  m_(?:Children|Roots):)[ \t]*\r?\n(?=  [a-zA-Z_])", r"\1 []\n", out)


def cmd_take(a):
    pre, hd = load(a.head)
    _, nd = load(a.saved)
    H, N = {d.fid: d for d in hd}, {d.fid: d for d in nd}
    want = [x for x in a.ids.split(",") if x]
    drop = [x for x in (a.drop or "").split(",") if x]
    missing = [x for x in want if x not in N]
    if missing:
        sys.exit(f"not in saved: {missing}")
    text = {d.fid: d.text for d in hd}
    taken, added, pulled, patched = [], [], [], []

    def take(fid, why):
        if fid in H:
            text[fid] = N[fid].text
            taken.append(fid)
        else:
            text[fid] = N[fid].text
            added.append(fid)
            if why != "asked":
                pulled.append((fid, why))

    for fid in want:
        take(fid, "asked")
    if not a.no_closure:
        queue = list(want)
        while queue:
            fid = queue.pop()
            for r in sorted(local_refs(text[fid])):
                if r in text:
                    continue
                if r in N:
                    take(r, f"referenced by {fid}")
                    queue.append(r)
                else:
                    sys.exit(f"{fid} refers to {r}, which is in neither version")

    roots = next((d.fid for d in hd if d.cls == "1660057539"), None)
    for fid in added:
        d = N[fid]
        if d.cls not in TRANSFORM_CLASSES or d.stripped:
            continue
        father = FATHER.search(d.text)
        parent = father.group(1) if father else "0"
        target, key = (parent, "m_Children") if parent != "0" else (roots, "m_Roots")
        if target is None:
            continue  # SceneRoots の無い古い形式・プレハブ
        if target not in text:
            sys.exit(f"new transform {fid}: parent {target} is in neither version")
        new = add_child(text[target], key, fid)
        if new is None:
            sys.exit(f"new transform {fid}: no {key} list in {target}")
        if new != text[target]:
            text[target] = new
            patched.append((target, fid))

    for fid in drop:
        if fid not in text:
            sys.exit(f"drop: {fid} not in head")
        del text[fid]
        for k in list(text):
            if f"{{fileID: {fid}}}" in text[k] and re.search(r"(?m)^  m_(?:Children|Roots):", text[k]):
                text[k] = remove_child(text[k], fid)

    order = [d.fid for d in hd if d.fid in text]
    new_docs = [fid for fid in (d.fid for d in nd) if fid in added]
    if roots and roots in order:
        i = order.index(roots)
        order[i:i] = new_docs
    else:
        order += new_docs
    _, docs = parse(pre + "".join(text[f] for f in order))
    write(a.out, pre, docs)
    print(f"replaced {len(taken)}: {taken}")
    print(f"added {len(added)}: {added}")
    for fid, why in pulled:
        print(f"  pulled in {fid} ({CLASS_NAMES.get(N[fid].cls, N[fid].cls)}) {why}")
    for parent, child in patched:
        print(f"  listed {child} under {parent}")
    if drop:
        print(f"dropped {len(drop)}: {drop}")
    print(f"written {a.out}")


def cmd_refcheck(a):
    bad = False
    for path in a.scenes:
        _, docs = load(path)
        ids = [d.fid for d in docs]
        dup = len(ids) - len(set(ids))
        have = set(ids)
        missing = {}
        for d in docs:
            for r in local_refs(d.text):
                if r not in have:
                    missing.setdefault(r, d.fid)
        print(f"{path}: docs {len(docs)} duplicated ids {dup} unresolved local refs {len(missing)}"
              + (" " + ", ".join(f"{r} (from {f})" for r, f in list(missing.items())[:10]) if missing else ""))
        bad |= bool(dup or missing)
    sys.exit(1 if bad else 0)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("fromgit"); s.add_argument("rev"); s.add_argument("path"); s.add_argument("out")
    s = sub.add_parser("list"); s.add_argument("head"); s.add_argument("saved")
    s.add_argument("--assets", nargs="*"); s.add_argument("--class", dest="cls"); s.add_argument("--grep")
    s = sub.add_parser("show"); s.add_argument("scene"); s.add_argument("keys", nargs="+"); s.add_argument("--lines", type=int, default=80)
    s = sub.add_parser("take"); s.add_argument("head"); s.add_argument("saved"); s.add_argument("out"); s.add_argument("ids")
    s.add_argument("--drop"); s.add_argument("--no-closure", action="store_true")
    s = sub.add_parser("refcheck"); s.add_argument("scenes", nargs="+")
    a = p.parse_args()
    {"fromgit": cmd_fromgit, "list": cmd_list, "show": cmd_show, "take": cmd_take, "refcheck": cmd_refcheck}[a.cmd](a)


if __name__ == "__main__":
    main()
