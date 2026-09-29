"""タイリングするテクスチャを作って、画像ファイルとして書き出す。

前提: UV は「1m = 1UV」なので、1 枚の画像が実寸 1m 角に対応する。
端で繋がるように、全てのノイズは折り返し（wrap）ありで作る。

素材は carpet / fabric / plaster / wood を用意してある。どれも (明暗, 高さ) を返すので、
tint() で色を掛けてカラーマップに、height_to_normal() でノーマルマップにする。
新しい素材を足すときも同じ形（0〜1 の 2 枚を返す）に揃える。

    import importlib, sys
    sys.path.insert(0, os.path.expanduser("~/.claude/skills/blender-stage/scripts"))
    import texlib as T
    importlib.reload(T)
    shade, height = T.carpet(1024)
    T.save_image("T_Carpet_Color", T.tint(shade, (0.135, 0.145, 0.165)), tex_dir)
    T.save_image("T_Carpet_Normal", T.height_to_normal(height, 2.5), tex_dir, non_color=True)
"""
from __future__ import annotations

import os

import bpy
import numpy as np


def _smooth(a: np.ndarray, passes: int = 1) -> np.ndarray:
    """端が繋がるぼかし（np.roll なので折り返しが保たれる）。"""
    out = a
    for _ in range(passes):
        out = (out
               + np.roll(out, 1, 0) + np.roll(out, -1, 0)
               + np.roll(out, 1, 1) + np.roll(out, -1, 1)) / 5.0
    return out


def value_noise(res: int, freq: int, seed: int) -> np.ndarray:
    """周期 freq の値ノイズ（0〜1、タイリングする）。"""
    rng = np.random.default_rng(seed)
    grid = rng.random((freq, freq))
    # 最近傍で拡大してから何度もぼかす（端は roll で繋がる）
    rep = res // freq + 1
    big = np.kron(grid, np.ones((rep, rep)))[:res, :res]
    return _smooth(big, passes=max(2, rep // 2))


def fbm(res: int, freq: int, octaves: int, seed: int, gain: float = 0.5) -> np.ndarray:
    total = np.zeros((res, res))
    amp, f, norm = 1.0, freq, 0.0
    for i in range(octaves):
        if res % f:
            f = max(1, res // (res // f))
        total += value_noise(res, f, seed + i * 17) * amp
        norm += amp
        amp *= gain
        f *= 2
        if f > res:
            break
    return total / norm


def normalize(a: np.ndarray) -> np.ndarray:
    lo, hi = a.min(), a.max()
    return (a - lo) / (hi - lo) if hi > lo else np.zeros_like(a)


def height_to_normal(height: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """高さ（0〜1）から接空間のノーマルマップ（RGB 0〜1）を作る。"""
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength
    nz = np.ones_like(height)
    length = np.sqrt(dx * dx + dy * dy + nz * nz)
    return np.stack([(-dx / length) * 0.5 + 0.5, (-dy / length) * 0.5 + 0.5, (nz / length) * 0.5 + 0.5], axis=-1)


def save_image(name: str, rgb: np.ndarray, directory: str, non_color: bool = False) -> str:
    """RGB 配列（0〜1）を PNG に保存して、Blender の画像として返す。"""
    res = rgb.shape[0]
    # 既にある画像は作り直す。Image.scale() を挟むと、その後に書いた画素が保存に反映されず
    # 真っ黒の PNG になる（Blender 5.2 で実測）
    old = bpy.data.images.get(name)
    if old is not None:
        bpy.data.images.remove(old)
    img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=False)
    rgba = np.concatenate([rgb, np.ones((res, res, 1))], axis=-1).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    img.update()
    # 色空間は「保存してから」設定する。保存前に触ると画素バッファが作り直され、
    # 書いた内容が捨てられて真っ黒の PNG になる（Blender 5.2 で実測）
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{name}.png")
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.filepath = path
    img.source = "FILE"
    img.reload()
    img.colorspace_settings.name = "Non-Color" if non_color else "sRGB"
    return path


# --- 素材ごとの模様（1m 角。タイリングする） ---

def carpet(res: int = 1024, seed: int = 1):
    """タイルカーペット: 50cm 角が 2×2。目地の溝と、貼る向きで変わる毛並み。"""
    y, x = np.mgrid[0:res, 0:res] / res
    tile = ((x * 2).astype(int) + (y * 2).astype(int)) % 2   # 50cm の市松（貼る向きの差）
    # 毛足: 向きで異方性を変える（縦向きのタイルと横向きのタイル）
    fine_v = fbm(res, 64, 3, seed) * 0.6 + value_noise(res, 256, seed + 3) * 0.4
    fine_h = fine_v.T
    fiber = np.where(tile == 0, fine_v, fine_h)
    fiber = normalize(fiber)
    # 目地（タイルの境目）は少し沈む
    gx = np.minimum((x * 2) % 1.0, 1.0 - (x * 2) % 1.0)
    gy = np.minimum((y * 2) % 1.0, 1.0 - (y * 2) % 1.0)
    groove = np.clip(np.minimum(gx, gy) / 0.012, 0.0, 1.0)
    height = fiber * 0.55 + groove * 0.45
    shade = 0.82 + fiber * 0.30 + (tile * 0.05)     # 貼る向きで濃淡が出る
    shade *= 0.82 + 0.18 * groove
    return shade, height


def fabric(res: int = 1024, seed: int = 11, threads_per_m: int = 160):
    """吸音パネルの布: 平織りの目と、糸のむら。"""
    y, x = np.mgrid[0:res, 0:res] / res
    u = (x * threads_per_m) % 1.0
    v = (y * threads_per_m) % 1.0
    warp = np.sin(u * np.pi) ** 2
    weft = np.sin(v * np.pi) ** 2
    over = (((x * threads_per_m).astype(int) + (y * threads_per_m).astype(int)) % 2) == 0
    weave = np.where(over, warp, weft)
    slub = fbm(res, 32, 3, seed) * 0.25 + fbm(res, 128, 2, seed + 5) * 0.15
    height = normalize(weave * 0.7 + slub * 0.3)
    shade = 0.86 + weave * 0.14 + (slub - 0.2) * 0.25
    return shade, height


def plaster(res: int = 1024, seed: int = 21):
    """塗り壁: 大きなむらと細かい砂目。"""
    big = fbm(res, 8, 4, seed)
    grain = value_noise(res, 256, seed + 7)
    height = normalize(big * 0.35 + grain * 0.65)
    shade = 0.94 + (big - 0.5) * 0.06 + (grain - 0.5) * 0.05
    return shade, height


def wood(res: int = 1024, seed: int = 31, boards: int = 3, rings: float = 22.0):
    """縦張りの板（腰壁向け）。1m あたり boards 枚、板ごとに色と木目の位相を変える。

    1 枚の板の中では木目が縦（V 方向）に流れ、板の境目に細い目地が入る。
    板の幅が 1/boards m なので、1m 角のまま継ぎ目なく並ぶ。
    """
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:res, 0:res] / res
    idx = np.clip((x * boards).astype(int), 0, boards - 1)
    phase = rng.random(boards)[idx]          # 板ごとの木目のずれ
    tone = (rng.random(boards)[idx] - 0.5)   # 板ごとの色の濃淡

    warp = (fbm(res, 4, 3, seed) - 0.5) * 0.05 + (fbm(res, 16, 2, seed + 4) - 0.5) * 0.015
    band = np.sin(((y + phase) * rings + warp * rings) * 2 * np.pi)
    grain = normalize(np.sign(band) * np.abs(band) ** 0.55 * 0.5 + 0.5)
    pores = value_noise(res, 512, seed + 9)

    # 板の継ぎ目（目地）
    edge = np.minimum((x * boards) % 1.0, 1.0 - (x * boards) % 1.0)
    seam = np.clip(edge / 0.02, 0.0, 1.0)

    height = normalize(grain * 0.35 + pores * 0.15 + seam * 0.5)
    shade = (0.90 + (grain - 0.5) * 0.14 + (pores - 0.5) * 0.04 + tone * 0.10) * (0.45 + 0.55 * seam)
    return shade, height


def tint(shade: np.ndarray, color) -> np.ndarray:
    """明暗（0〜1 前後）に色を掛けて RGB にする。"""
    s = np.clip(shade, 0.0, 2.0)[..., None]
    return np.clip(s * np.array(color, dtype=float)[None, None, :], 0.0, 1.0)

def foam(res: int = 1024, seed: int = 41, cells: int = 8):
    """吸音スポンジ（ウェッジ型）。1m 角に cells × cells 個の山。

    山の稜線が交互に直交する、よくある形。高さは山（0〜1）、明暗は面の向きに近い陰影を混ぜる。
    """
    y, x = np.mgrid[0:res, 0:res] / res
    u = (x * cells) % 1.0
    v = (y * cells) % 1.0
    # 市松で稜線の向きを 90 度変える
    flip = (((x * cells).astype(int) + (y * cells).astype(int)) % 2) == 0
    wedge = np.where(flip, 1.0 - np.abs(u * 2 - 1), 1.0 - np.abs(v * 2 - 1))
    grain = value_noise(res, 256, seed) * 0.15
    height = normalize(wedge * 0.85 + grain)
    shade = 0.62 + wedge * 0.30 + (grain - 0.075) * 0.4
    return shade, height
