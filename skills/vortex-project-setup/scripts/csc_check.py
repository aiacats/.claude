"""Unity が作った .rsp（参照・define）を借りて、Editor 用の雛形の .cs だけを Roslyn でコンパイルする（Unity を開かずに型を確かめる）。
使い方: python csc_check.py <Unity プロジェクト> <rsp の名前（Assembly-CSharp-Editor など）> <.cs> [...]
- 終了コード 0 = 通った / 1 = エラー（error と、渡した .cs の warning を出す）/ 2 = 準備ができない（rsp や Unity が無い）
- 一度 Unity でそのプロジェクトを開いてコンパイルしたことがある（Library/Bee/artifacts/*.dag/<名前>.rsp がある）こと
- 同梱 Roslyn の単体コンパイルは asmdef の参照条件を再現しないので偽陰性がある（traps unity-build「同梱 Roslyn の単体コンパイルは…」）。
  通っても、Unity を開いたら force_compilation で確かめ直す"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8")


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    proj, name, files = Path(sys.argv[1]).resolve(), sys.argv[2], [Path(p).resolve() for p in sys.argv[3:]]
    rsps = sorted(proj.glob(f"Library/Bee/artifacts/*.dag/{name}.rsp"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not rsps:
        print(f"rsp が無い: {proj}/Library/Bee/artifacts/*.dag/{name}.rsp（Unity で一度開いてコンパイルする）")
        sys.exit(2)
    m = re.search(r"m_EditorVersion: (\S+)", (proj / "ProjectSettings/ProjectVersion.txt").read_text(encoding="utf-8"))
    unity = Path(r"C:/Program Files/Unity/Hub/Editor") / (m.group(1) if m else "?") / "Editor/Data"
    dotnet, csc = unity / "NetCoreRuntime/dotnet.exe", unity / "DotNetSdkRoslyn/csc.dll"
    if not dotnet.exists() or not csc.exists():
        print(f"Unity の Roslyn が無い: {csc}")
        sys.exit(2)
    out = Path(tempfile.mkdtemp(prefix="csc_check_"))
    keep = []
    for line in rsps[0].read_text(encoding="utf-8").splitlines():
        s = line.strip().strip('"')
        if s.endswith(".cs") or line.startswith(("-out:", "-refout:", "-generatedfilesout")):
            continue  # 元のアセンブリのソースと出力先は使わない
        if line.startswith(("-analyzer:", "-additionalfile:", "-ruleset:")):
            continue  # 解析器は相対パスがずれる。型の確かめには要らない
        keep.append(line)
    keep.append(f'-out:"{out / "check.dll"}"')
    keep += [f'"{p}"' for p in files]
    rsp = out / "check.rsp"
    rsp.write_text("\n".join(keep), encoding="utf-8")
    r = subprocess.run([str(dotnet), str(csc), "/noconfig", "@" + str(rsp)], cwd=str(proj), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    names = [p.name for p in files]
    lines = [l for l in (r.stdout + r.stderr).splitlines()
             if " error " in l or (" warning " in l and any(n in l for n in names))]
    print("\n".join(lines[:60]))
    print(f"rsp: {rsps[0]}")
    print("exit", r.returncode)
    sys.exit(0 if r.returncode == 0 else 1)


if __name__ == "__main__":
    main()
