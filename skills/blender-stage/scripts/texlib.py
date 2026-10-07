"""タイリングするテクスチャを作って、画像ファイルとして書き出す。

前提: UV は「1m = 1UV」なので、1 枚の画像が実寸 1m 角に対応する。
端で繋がるように、全てのノイズは折り返し（wrap）ありで作る。

素材は carpet / fabric / plaster / wood / foam、金物の brushed / powder_coat / galvanized、rubber を用意してある。
使い込んだ跡は scratches（細い引っかき傷の印）と wear（擦れ・汚れを既存の模様へ重ねる）。どれも (明暗, 高さ) を返すので、
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


def _interp_grid(grid: np.ndarray, res: int) -> np.ndarray:
    """格子（行 × 列）の値を res × res へ、なめらかな補間（smoothstep の重みの双線形）で広げる。端は折り返して繋がる。

    最近傍で拡大してからぼかすやり方は、ぼかしがマスの大きさに比べて弱いと、マスの角が模様に残る（床がマス目に見えた）。
    """
    def axis(n):
        t = np.arange(res) * n / res
        i0 = np.floor(t).astype(int) % n
        f = t - np.floor(t)
        return i0, (i0 + 1) % n, f * f * (3 - 2 * f)
    r0, r1, fr = axis(grid.shape[0])
    c0, c1, fc = axis(grid.shape[1])
    top = grid[r0][:, c0] * (1 - fc)[None, :] + grid[r0][:, c1] * fc[None, :]
    bot = grid[r1][:, c0] * (1 - fc)[None, :] + grid[r1][:, c1] * fc[None, :]
    return top * (1 - fr)[:, None] + bot * fr[:, None]


def value_noise(res: int, freq: int, seed: int) -> np.ndarray:
    """周期 freq の値ノイズ（0〜1、タイリングする）。"""
    rng = np.random.default_rng(seed)
    return _interp_grid(rng.random((freq, freq)), res)


def fbm(res: int, freq: int, octaves: int, seed: int, gain: float = 0.5) -> np.ndarray:
    total = np.zeros((res, res))
    amp, f, norm = 1.0, freq, 0.0
    for i in range(octaves):
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


def mean_one(shade: np.ndarray) -> np.ndarray:
    """明暗の平均を 1 に揃える（tint に渡した色が、そのまま面の平均の色になる）。"""
    return shade / float(shade.mean())


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


# --- 金物・樹脂と、使い込んだ跡（1m 角。タイリングする） ---

def _stretch_noise(res: int, freq_long: int, freq_short: int, seed: int) -> np.ndarray:
    """一方向（列方向）に長く伸びたノイズ（ヘアライン・すじ）。折り返しでつながる。

    行の方向は freq_long 個、列の方向は freq_short 個の格子を補間する（freq_long が小さいほど行方向に長く伸びる）。
    """
    rng = np.random.default_rng(seed)
    return _interp_grid(rng.random((freq_short, freq_long)), res)


def scratches(res: int, seed: int, count: int, length: tuple, width_px: float = 1.0) -> np.ndarray:
    """細い引っかき傷の印（0〜1）。長さは m（1m 角に対する割合）、向きはばらばら。端は折り返してつながる。"""
    rng = np.random.default_rng(seed)
    mask = np.zeros((res, res))
    for _ in range(count):
        x0, y0 = rng.random(2) * res
        ang = rng.random() * np.pi
        ln = (length[0] + (length[1] - length[0]) * rng.random()) * res
        n = max(2, int(ln))
        t = np.linspace(0.0, 1.0, n)
        bend = (rng.random() - 0.5) * 0.15                 # 少し弧を描く
        xs = x0 + np.cos(ang + bend * t) * ln * t
        ys = y0 + np.sin(ang + bend * t) * ln * t
        strength = 0.4 + 0.6 * rng.random()
        for k in range(int(np.ceil(width_px))):
            mask[(ys.astype(int) + k) % res, xs.astype(int) % res] = np.maximum(
                mask[(ys.astype(int) + k) % res, xs.astype(int) % res], strength)
    return mask


def brushed(res: int = 512, seed: int = 61):
    """ヘアライン仕上げのアルミ（トラスのパイプ）。一方向のすじと、薄い擦り傷。"""
    streak = normalize(_stretch_noise(res, 4, res // 2, seed))
    fine = value_noise(res, res // 4, seed + 3)
    scr = scratches(res, seed + 7, 60, (0.02, 0.08))
    height = normalize(streak * 0.6 + fine * 0.2 - scr * 0.4)
    shade = 0.92 + (streak - 0.5) * 0.12 + (fine - 0.5) * 0.04 + scr * 0.10
    return mean_one(shade), height


def powder_coat(res: int = 512, seed: int = 71, scratch_count: int = 40, scratch_gain: float = 1.6):
    """焼付け塗装（機材の筐体・ケース・扉）。細かい柚子肌と、地の金属が少し光る擦り傷。

    scratch_gain は傷の明るさ（色に掛ける倍率への足し分）。黒い塗装では 1.6 でうっすら見える。
    明るい色に同じ値を使うと白い線が目立つので、灰色の扉などでは 0.3 程度に下げる。
    """
    peel = fbm(res, 64, 3, seed)
    big = fbm(res, 4, 3, seed + 5)
    scr = scratches(res, seed + 9, scratch_count, (0.01, 0.06))
    height = normalize(peel * 0.7 + big * 0.1 - scr * 0.5)
    shade = 0.95 + (peel - 0.5) * 0.10 + (big - 0.5) * 0.12 + scr * scratch_gain
    return mean_one(shade), height


def galvanized(res: int = 512, seed: int = 81):
    """溶融亜鉛めっき（鉄柵・ダクト）。結晶の模様（スパングル）のまだらと、細かい凹凸。"""
    rng = np.random.default_rng(seed)
    cells = 32                                             # res（512・1024）を割り切る数（最後のマスが欠けて継ぎ目に線が出ない）
    grid = rng.random((cells, cells))
    rep = res // cells + 1
    patches = np.kron(grid, np.ones((rep, rep)))[:res, :res]   # 角ばったまだら（結晶の粒）
    patches = _smooth(patches, 1)
    fine = value_noise(res, res // 4, seed + 4)
    height = normalize(patches * 0.3 + fine * 0.7)
    shade = 0.90 + (patches - 0.5) * 0.18 + (fine - 0.5) * 0.04
    return mean_one(shade), height


def rubber(res: int = 512, seed: int = 91):
    """ゴム・樹脂（ケーブルの被覆・座席の殻・机の天板）。細かいしぼと、うっすらした汚れ。"""
    grain = value_noise(res, res // 2, seed)
    dirt = fbm(res, 8, 3, seed + 2)
    height = normalize(grain)
    shade = 0.95 + (grain - 0.5) * 0.06 + (dirt - 0.5) * 0.10
    return mean_one(shade), height


def wear(shade_height, seed: int, scuffs: float = 1.0, grime: float = 1.0, scratch_count: int = 120):
    """既存の模様（明暗, 高さ）に使い込んだ跡を重ねる: 靴の擦れ（明るい楕円の帯）、薄い汚れのむら、細い傷。

    1m 角で繰り返すので、目立つ大きな跡は入れない（並んで見えてしまう）。小さく数の多い跡だけにする。
    """
    shade, height = shade_height
    res = shade.shape[0]
    mean_before = float(shade.mean())
    grime_map = fbm(res, 4, 4, seed)
    # 擦れは、すじの模様を「まばらに出る所」だけに残す（なめらかな閾値。0/1 で切るとマス目の角が出る）
    patch = np.clip((value_noise(res, 16, seed + 5) - 0.55) / 0.15, 0.0, 1.0)
    scuff_map = normalize(_stretch_noise(res, 8, 32, seed + 3) * patch)
    scr = scratches(res, seed + 7, scratch_count, (0.02, 0.12))
    shade = shade * (1.0 - (grime_map - 0.5) * 0.25 * grime) + scuff_map * 0.10 * scuffs + scr * 0.12 * scuffs
    height = height - scr * 0.3 * scuffs                    # 正規化し直さない（元の起伏の強さを保つ）
    return shade * (mean_before / float(shade.mean())), height   # 平均の明るさは元のまま（擦れで全体を明るくしない）
