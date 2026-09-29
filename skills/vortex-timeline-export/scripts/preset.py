# TimelineExporter の書き出しプリセット（ExportPreset .asset）の録画元と範囲を書き換える。
#
#   python preset.py <preset.asset> --rt <RenderTexture の guid> --test [開始秒]
#   python preset.py <preset.asset> --rt <guid> --whole
#
# --test は開始秒から 5 秒だけ書き出す設定にする（中身の確認用。既定 300 秒）。
# --whole は全尺に戻す。
# Unity が開いている間に書き換えたら、MCP で AssetDatabase.ImportAsset(<preset>) を呼ぶこと
# （Auto Refresh が無効な案件では、呼ばないと古い設定のまま書き出される）。
import argparse
import re

# ExportRange.Mode の並び（ExportRange.cs）: 0=Whole, 1=Seconds, 2=Frames
MODE_WHOLE, MODE_SECONDS = 0, 1
# 確認用の尺。フレームを 1 枚抜いて中身を見るのに足りる長さで、4K でも 10 秒前後で書き終わる
TEST_LENGTH = 5.0

ap = argparse.ArgumentParser()
ap.add_argument("preset")
ap.add_argument("--rt", help="録画元 RenderTexture の guid")
g = ap.add_mutually_exclusive_group(required=True)
g.add_argument("--test", nargs="?", const=300.0, type=float, metavar="START")
g.add_argument("--whole", action="store_true")
a = ap.parse_args()

text = open(a.preset, encoding="utf-8").read()

if a.rt:
    text, n = re.subn(r"^(  _renderTexture: \{fileID: 8400000, guid: )\w+(, type: 2\})$",
                      r"\g<1>" + a.rt + r"\2", text, flags=re.M)
    if n == 0:
        # 未設定（fileID: 0）の場合は行ごと置き換える
        text = re.sub(r"^  _renderTexture: \{fileID: 0\}$",
                      "  _renderTexture: {fileID: 8400000, guid: " + a.rt + ", type: 2}", text, flags=re.M)

if a.test is not None:
    start, end, mode = a.test, a.test + TEST_LENGTH, MODE_SECONDS
else:
    start, end, mode = 0, -1, MODE_WHOLE

# _defaultRange ブロックの中だけを書き換える
m = re.search(r"^  _defaultRange:\n((?:    .*\n)+)", text, re.M)
if m is None:
    raise SystemExit("_defaultRange が見つかりません")
block = m.group(1)
block = re.sub(r"^(    _mode: )\d+$", r"\g<1>%d" % mode, block, flags=re.M)
block = re.sub(r"^(    _startSeconds: ).*$", r"\g<1>%s" % start, block, flags=re.M)
block = re.sub(r"^(    _endSeconds: ).*$", r"\g<1>%s" % end, block, flags=re.M)
text = text[:m.start(1)] + block + text[m.end(1):]

open(a.preset, "w", encoding="utf-8", newline="\n").write(text)
for line in text.splitlines():
    if re.match(r"^\s+_(sourceKind|renderTexture|coreQuality|mode|startSeconds|endSeconds):", line):
        print(line)
