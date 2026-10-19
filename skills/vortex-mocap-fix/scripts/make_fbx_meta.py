# 取り込む前の FBX に、キーフレーム削減 Off・Humanoid（このモデルから作る）だけを書いた .meta を作る。残りの項目は Unity が既定で埋める。
# FBX を Assets に置く前（Unity が .meta を作る前）に、置き先で FBX と同じ名前 + .meta を作る。
# 長い収録 FBX を既定（削減あり）で取り込むと、削減の処理で Unity が落ち、起動し直しても同じ取り込みで落ちる（2026-10-12 エルセ）。
# 削減ありで取り込んだクリップはキーがまばらで、後で間引いた .anim を作ると足がガタつく（2026-10-15 AZKi）。
# 使い方: python make_fbx_meta.py <fbx のパス>
import os
import sys
import uuid

fbx = sys.argv[1]
meta = fbx + ".meta"
if os.path.exists(meta):
    sys.exit("meta already exists: " + meta)
text = (
    "fileFormatVersion: 2\n"
    f"guid: {uuid.uuid4().hex}\n"
    "ModelImporter:\n"
    "  serializedVersion: 22200\n"
    "  animations:\n"
    "    animationCompression: 0\n"
    "  animationType: 3\n"
    "  avatarSetup: 1\n"
)
open(meta, "w", encoding="utf-8", newline="\n").write(text)
print(text)
