---
name: MultiPassRenderer パッケージの技術背景
description: com.aiacats.multipass-renderer の設計判断と技術的注意点
type: project
---

MultiPassRenderer（com.aiacats.multipass-renderer）はURP向けマルチパスEXRオフラインレンダラー。最大13パスに分解してEXR出力する。

**Why:** Nuke/AE/DaVinci Resolveでのコンポジット用。VFX業界標準のCryptomatte・ACES対応。

**How to apply:**
- Cryptomatte/CryptomatteMaterialPass は DrawMesh 方式（SRP Batcher が PropertyBlock を無視するため）
- SkinnedMeshRenderer の BakeMesh は rootBone のローカル空間で出力 → rootBone.localToWorldMatrix を使用（2026-04-08修正済み）
- RimLight は差分キャプチャ方式（NiloToon Cinematic Rim Light OFF で再レンダリングし差分取得）
- 離散値パス（ObjectId, Cryptomatte）はMSAA非対応のDiscreteDepthRTを使用
- パス追加は PassTypeInfo.Registry に1行追加 + シェーダー + パスクラスで完結
- 解説記事: Documentation~/MultiPassRenderer-Architecture.md
