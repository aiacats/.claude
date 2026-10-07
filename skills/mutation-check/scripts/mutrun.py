"""変異チェックの実行: 修正を 1 か所ずつ外し、テストがそれを検出するかを一覧にする。

使い方:
    python mutrun.py <変異の一覧.py> [--root <リポジトリのルート>] [--no-baseline] [--timeout 秒]

一覧ファイルは Python で、MUTATIONS を定義する（ROOT を書けば --root は省ける）:

    ROOT = r"D:\\path\\to\\repo"
    T = dotnet_test("tests/My.Tests", "MyTestClass")       # テストの流し方（下の補助関数）
    MUTATIONS = [
        ("何を壊したか", r"src\\File.cs", "元の文字列", "壊した文字列", T),
    ]

- 元の文字列は、そのファイルにちょうど 1 回だけ現れること（違えば NOT APPLIED）。
- テストの流し方は引数のリスト。補助関数: dotnet_test(project, filter) / npm_test(cwd, *args) /
  cargo_test(cwd, *args) / pytest(cwd, *args)。どれでもなければ ["cmd", "arg", ...] か (cwd, [...]) を直接書く。

結果:
    caught by <テスト名>   検出された
    SURVIVED               変異を入れてもテストが通った（テストが緩いか、等価な変異）
    NO TESTS RAN           絞り込みに当たるテストが 0 件（名前の間違い。SURVIVED ではない）
    BUILD ERROR            変異そのものがコンパイルできない（変異の書き直しが要る）
    NOT APPLIED            元の文字列が 0 回か 2 回以上
    TIMEOUT                時間切れ

どのファイルも、結果にかかわらず必ず元に戻す。
"""
import argparse
import importlib.util
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")


# ---- 一覧ファイルから使う補助関数 -------------------------------------------------------------

def dotnet_test(project, filter_name=None):
    """dotnet test <project> [--filter FullyQualifiedName~<filter>]。filter は "A|B" で複数。"""
    command = ["dotnet", "test", project, "--nologo"]
    if filter_name:
        parts = [part if "~" in part or "=" in part else f"FullyQualifiedName~{part}" for part in filter_name.split("|")]
        command += ["--filter", "|".join(parts)]
    return (None, command)


def npm_test(cwd, *args):
    """npm test -- <args>（vitest / jest）。cwd はルートからの相対パス。"""
    return (cwd, ["npm", "test", "--", *args] if args else ["npm", "test"])


def cargo_test(cwd, *args):
    return (cwd, ["cargo", "test", *args])


def pytest(cwd, *args):
    return (cwd, [sys.executable, "-m", "pytest", "-x", "-q", *args])


HELPERS = {"dotnet_test": dotnet_test, "npm_test": npm_test, "cargo_test": cargo_test, "pytest": pytest}

# ---- 出力の読み方 -----------------------------------------------------------------------------

# 1 件も走らなかったときの出力（dotnet の日本語・英語、vitest、jest、pytest、cargo）。
NO_TESTS = [
    r"No test matches the given testcase filter",
    r"指定されたテストケース フィルター.*に一致するテストはありません",
    r"No test files found",
    r"No tests found",
    r"no tests ran",
    r"running 0 tests",
    r"collected 0 items",
    r"^# tests 0$",  # node:test（tsx --test）
]

# コンパイルエラー（C#・TypeScript・Rust・Python の構文）。
BUILD_ERRORS = [r"\berror CS\d+", r"\berror TS\d+", r"\berror\[E\d+\]", r"SyntaxError", r"\berror MSB\d+"]

# 落ちたテストの名前を拾う（xUnit / vitest・jest / cargo / pytest）。
FAILED = [
    r"\]\s+([\w.]+)(?:\(.*?\))?\s+\[FAIL\]",
    r"^\s*(?:×|✗|FAIL)\s+(.+?)(?:\s+\d+\s*ms)?$",
    r"^test (\S+) \.\.\. FAILED",
    r"^FAILED (\S+)",
    r"^not ok \d+ - (.+)$",  # node:test（TAP 形式。tsx --test / node --test）
]


def run(root, command, timeout):
    cwd, args = command if isinstance(command, tuple) else (None, command)
    try:
        done = subprocess.run(
            args, cwd=root / cwd if cwd else root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, shell=(sys.platform == "win32" and args[0] in ("npm", "npx")))
    except subprocess.TimeoutExpired:
        return None, ""
    return done.returncode, done.stdout + done.stderr


def judge(code, out):
    if code is None:
        return "TIMEOUT"

    failed = []
    for pattern in FAILED:
        for match in re.finditer(pattern, out, re.MULTILINE):
            name = match.group(1).strip().split(".")[-1]
            if name and name not in failed:
                failed.append(name)

    if failed:
        return "caught by " + ", ".join(failed)
    if any(re.search(pattern, out, re.IGNORECASE) for pattern in NO_TESTS):
        return "NO TESTS RAN"
    if any(re.search(pattern, out) for pattern in BUILD_ERRORS):
        return "BUILD ERROR"
    if code != 0:
        return "caught (the run failed; no test name read from the output)"
    return "SURVIVED"


def main():
    parser = argparse.ArgumentParser(description="Mutation check runner")
    parser.add_argument("mutations")
    parser.add_argument("--root")
    parser.add_argument("--no-baseline", action="store_true", help="変異なしの確認を省く")
    parser.add_argument("--timeout", type=int, default=280, help="1 回のテスト実行の上限（秒）")
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("mutations", args.mutations)
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(HELPERS)
    spec.loader.exec_module(module)

    root = pathlib.Path(args.root or getattr(module, "ROOT", "."))
    mutations = module.MUTATIONS
    bad = 0

    # 変異なしで通ること・1 件以上走ることを先に確かめる。ここで落ちるなら変異チェックの結果は読めない。
    if not args.no_baseline:
        seen = []
        for mutation in mutations:
            command = mutation[4]
            if command in seen:
                continue
            seen.append(command)
            outcome = judge(*run(root, command, args.timeout))
            if outcome != "SURVIVED":
                shown = command[1] if isinstance(command, tuple) else command
                print(f"BASELINE {outcome}: {' '.join(shown)}")
                bad += 1
        if bad:
            print("\n変異なしの状態でテストが通らない（または 1 件も走らない）ので、ここで止めます。")
            return 2

    results = []
    for name, rel, old, new, command in mutations:
        path = root / rel
        original = path.read_bytes()
        text = original.decode("utf-8")
        count = text.count(old)
        # 一覧は LF で書くが、対象が CRLF のファイル（Windows の作業コピー）だと複数行の文字列が一致しない。
        # LF のままで見つからず、ファイルが CRLF なら、改行を CRLF に揃えて探し直す
        if count == 0 and "\n" in old and "\r\n" in text:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
            count = text.count(old)
        if count != 1:
            results.append((name, f"NOT APPLIED ({count} matches)"))
            continue
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        try:
            results.append((name, judge(*run(root, command, args.timeout))))
        finally:
            path.write_bytes(original)

    width = max(len(outcome) for _, outcome in results) if results else 0
    width = min(width, 80)
    for name, outcome in results:
        print(f"{outcome:{width}.{width}}  <- {name}")
        if not outcome.startswith("caught"):
            bad += 1

    caught = len(results) - bad
    print(f"\n{caught} / {len(results)} caught.")
    print("ファイルは全部元に戻しました。変異入りのビルド成果物が残っているので、GUI を見る前にビルドし直すこと。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
