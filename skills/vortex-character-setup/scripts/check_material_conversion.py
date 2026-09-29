# NiloToon 変換の抜け漏れチェック。
# 元の MToon マテリアル(<名前>.Materials/*.asset) と 変換後(<名前>(NiloToon)(Materials)/*.mat) を
# テクスチャ GUID で突き合わせ、MatCap / Emission / その他テクスチャの取りこぼしを出す。
#
#   python check_material_conversion.py <キャラフォルダの親>   例: Assets/02_vortex_character
#
# Unity を起動していなくても実行できる（ファイルを読むだけ）。

import glob
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# NiloToon 側で MatCap を実際に描くのに使うスロット。_SphereAdd は NiloToon シェーダに存在しないため受け皿にならない
NILO_MATCAP_SLOTS = ["_MatCapAdditiveMap", "_MatCapAlphaBlendMap", "_MatCapOcclusionMap"]
PASSTHROUGH_SLOTS = ["_MainTex", "_ShadeTexture", "_BumpMap", "_RimTexture",
                     "_UvAnimMaskTexture", "_OutlineWidthTexture"]


def parse_material(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    textures = {m.group(1): m.group(3) for m in
                re.finditer(r"- (_\w+):\s*\n\s*m_Texture: \{fileID: (\d+)(?:, guid: (\w+))?", text)}
    floats = dict(re.findall(r"- (_\w+): (-?[\d.]+)\s*\n", text))
    colors = {m[0]: tuple(float(x) for x in m[1:]) for m in
              re.findall(r"- (_\w+): \{r: ([-\d.]+), g: ([-\d.]+), b: ([-\d.]+), a: ([-\d.]+)\}", text)}
    keywords = re.findall(r"m_ValidKeywords:\s*\n((?:\s+- \w+\n)*)", text)
    keywords = re.findall(r"- (\w+)", keywords[0]) if keywords else []
    return textures, floats, colors, keywords


def check(root):
    issues = []
    checked = 0
    for conv_dir in sorted(glob.glob(os.path.join(root, "*", "*(NiloToon)(Materials)"))):
        orig_dir = conv_dir.split("(NiloToon)")[0] + ".Materials"
        label = os.path.basename(os.path.dirname(conv_dir)) + "/" + os.path.basename(conv_dir)
        if not os.path.isdir(orig_dir):
            issues.append(f"{label}: 元マテリアルのフォルダが無い（{orig_dir}）")
            continue

        for conv_path in sorted(glob.glob(os.path.join(conv_dir, "*.mat"))):
            name = os.path.splitext(os.path.basename(conv_path))[0]
            orig_path = os.path.join(orig_dir, name + ".asset")
            if not os.path.exists(orig_path):
                issues.append(f"{label}/{name}: 対応する元マテリアルが無い")
                continue

            checked += 1
            otex, _, ocol, _ = parse_material(orig_path)
            ctex, cfl, ccol, ckw = parse_material(conv_path)
            conv_guids = {g for g in ctex.values() if g}

            sphere = otex.get("_SphereAdd")
            if sphere and not any(ctex.get(s) == sphere for s in NILO_MATCAP_SLOTS):
                issues.append(f"{label}/{name}: MatCap 未反映 "
                              f"(_SphereAdd={sphere[:8]} / _UseMatCapAdditive={cfl.get('_UseMatCapAdditive')} "
                              f"/ keyword={[k for k in ckw if 'MATCAP' in k]})")

            emission_map = otex.get("_EmissionMap")
            if emission_map and ctex.get("_EmissionMap") != emission_map:
                issues.append(f"{label}/{name}: Emission テクスチャ未反映 (_EmissionMap={emission_map[:8]})")

            emission_color = ocol.get("_EmissionColor")
            if emission_color and max(emission_color[:3]) > 0.001:
                use = cfl.get("_UseEmission") or cfl.get("_UseEmissionMap")
                if use in (None, "0"):
                    issues.append(f"{label}/{name}: 元は発光色 {emission_color} だが変換後の発光が無効 (_UseEmission={use})")

            for slot in PASSTHROUGH_SLOTS:
                guid = otex.get(slot)
                if guid and guid not in conv_guids:
                    issues.append(f"{label}/{name}: {slot} のテクスチャ {guid[:8]} が変換後に見当たらない")

    print(f"検査したマテリアル: {checked} 件")
    print("=== 検出された問題 ===")
    print("\n".join(issues) if issues else "なし")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(check(sys.argv[1] if len(sys.argv) > 1 else "."))
