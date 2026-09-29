"""アセットライブラリのプレビューを並べた一覧画像を作る（登録したものを目で確かめる用）。

    "<blender.exe>" -b --factory-startup -P asset_sheet.py -- <ライブラリのフォルダ> <出力.png> [カタログの前方一致]

各 .blend のアセットを読み込み、preview の画素を 256px のマスに並べる。
プレビューが空（全透明）のものは赤いマスにして目立たせる。標準出力に `RESULT {...}`。
"""
import glob
import json
import os
import sys

import bpy
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(args) < 2:
    raise SystemExit("使い方: -- <ライブラリ> <出力.png> [カタログの前方一致]")
lib_dir, out_path = args[0], args[1]
prefix = args[2] if len(args) > 2 else ""
CELL = 256
BG = np.array([0.18, 0.18, 0.18], dtype=np.float32)

tiles, labels, empty = [], [], []
for path in sorted(glob.glob(os.path.join(lib_dir, "**", "*.blend"), recursive=True)):
    rel = os.path.relpath(path, lib_dir).replace("\\", "/")
    if prefix and not rel.startswith(prefix):
        continue
    with bpy.data.libraries.load(path, assets_only=True) as (src, dst):
        kinds = [k for k in ("collections", "materials", "objects") if list(getattr(src, k))]
        for k in kinds:
            setattr(dst, k, list(getattr(src, k)))
    for k in kinds:
        for idb in getattr(dst, k):
            prev = idb.preview
            w, h = prev.image_size if prev else (0, 0)
            tile = np.tile(BG, (CELL, CELL, 1))
            if w and h:
                px = np.array(prev.image_pixels_float[:], dtype=np.float32).reshape(h, w, 4)
                a = px[..., 3:4]
                img = px[..., :3] * a + BG * (1 - a)
                tile[:min(h, CELL), :min(w, CELL)] = img[:CELL, :CELL]
                if float(a.max()) < 0.01:
                    empty.append(rel)
                    tile[:] = (0.6, 0.1, 0.1)
            else:
                empty.append(rel)
                tile[:] = (0.6, 0.1, 0.1)
            tiles.append(tile)
            labels.append(rel)

cols = max(1, min(6, len(tiles)))
rows = (len(tiles) + cols - 1) // cols
sheet = np.tile(BG, (rows * CELL, cols * CELL, 1))
for i, t in enumerate(tiles):
    r, c = divmod(i, cols)
    # プレビューは下から上の並びなので、上下を合わせるため行を下から積む
    y0 = (rows - 1 - r) * CELL
    sheet[y0:y0 + CELL, c * CELL:(c + 1) * CELL] = t

img = bpy.data.images.new("asset_sheet", cols * CELL, rows * CELL, alpha=True)
rgba = np.concatenate([sheet, np.ones((*sheet.shape[:2], 1), dtype=np.float32)], axis=-1)
img.pixels.foreach_set(rgba.ravel())
img.filepath_raw = out_path
img.file_format = "PNG"
img.save()
print("RESULT " + json.dumps({"count": len(tiles), "columns": cols, "order": labels, "empty": empty,
                              "out": out_path}, ensure_ascii=False))
