---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
  - "**/*.{fbx,vrm,glb,gltf}"
---
# unity-import の罠
全件は ~/.claude/traps-catalog/unity-import.md。ここは再発しやすいものだけ。

### Blender 由来の FBX はルートの回転を上書きしない
モデルが縦に倒れる（部屋の奥行きが高さになる）。原因は `bakeAxisConversion: 0` のままだとルートに -90° の軸変換（X=270）が入っていて、`SetPositionAndRotation(..., Quaternion.identity)` で消えること。→ 位置だけ設定する。上書きしたら `PrefabUtility.RevertPropertyOverride`（m_LocalRotation / m_LocalEulerAnglesHint）で戻す。（実例: 2026-09-24 Ext_TokinoSora_2026-pia / 2026-09-24 BMCP）

### Blender の FBX の金属度は URP で 0 になる
クロームが白い樹脂に見える（`_Metallic=0`）。原因は Blender が Metallic を `ReflectionFactor` に書き、URP の `FBXMaterialDescriptionPreprocessor` がそれを読まないこと。→ Ext_TokinoSora_2026-pia の `vortex.EditorTools.BlenderFbxMetallic` を移植。対象の印は ModelImporter.userData（`vortex:BlenderMetallic`）で持つ。ラベルは変えても再インポートされないので使わない。全 FBX には効かせない。（実例: 2026-09-26/27 Ext_TokinoSora_2026-pia）

### FBX の埋め込みテクスチャは自動で展開されない
取り込んだだけではマテリアルが真っ白。→ `ModelImporter.ExtractTextures(<フォルダ>)` → `*_Normal` を `TextureImporterType.NormalMap` に → FBX を ForceUpdate で再インポートし、`_BaseMap` / `_BumpMap` が埋まったか確かめる。（実例: 2026-09-24 Ext_TokinoSora_2026-pia）

### VRM は Unity を前面にしてから取り込む・読む
背面の Unity では .vrm からテクスチャだけ展開され Prefab ができない。ランタイムの `Vrm10.LoadPathAsync` も非フォーカスだと SkinningBake で例外もログも無く止まる。原因はどちらもフレーム進行（delayCall / await）頼みなこと。→ focus_window してから ImportAsset / ロードする。（実例: 2026-09-24 ModelChecker / 2026-06-01 LiveMultiRecorder）

### VRM のランタイムロードが URP でマゼンタ
ロードは成功するのにマゼンタ。原因は `materialGenerator` が null で Built-in 用が選ばれること。→ `LoadPathAsync` の `materialGenerator` に URP 用を明示。（実例: 2026-06-01 LiveMultiRecorder）

### 収録モーションで首がずっと上を向く・内股になる・親指が開く
カーブは「データの通り」でも、キャラが全編で顎を上げる・頭を傾ける・膝が内へ入る・拳から親指が突き出す。原因は収録 FBX の Avatar の基準の姿勢がキャラとずれていること（首が前へ倒れる、脚が外へ開く。マッスルは基準からの差）。→ 基準の姿勢の胴・首・頭・脚をキャラに合わせて取り込み直し、演者との平均の差を補正して詰める。胸を回したら肩の向きを戻す（指のカーブが変わる）。親指は 3 節それぞれの向きを合わせる（付け根だけだと中の節の曲がりが残る）。道具と手順は skill vortex-mocap-fix（BodyRestFix）。（実例: 2026-10-15 SinkaiFes2026 MZM・エルセ・AZKi）

### 間引いて作った .anim で足の接地がガタつく
元の FBX では起きないのに、作り直した .anim だと着いている足が 1 コマで数 mm 跳ねる。原因は Root と足の IK の目標（RootT/Q・*FootT/Q）をマッスルと同じ許容（0.002）で間引いたこと（RootQ 0.2° が足元で 4 mm）と、毎フレーム前提の直線の間引きを圧縮して取り込んだ（キーがまばらな）FBX に掛けたこと。→ FBX を圧縮 Off で取り込み、Root・足の目標は 1e-4（RootQ 5e-5）で間引く。Foot IK Off のキャラは脚のマッスルも 1e-4（足が股関節からの積み重ねで決まる）。道具は skill vortex-mocap-fix（BodyRestFix.ExtractClip / RebuildCurves）。（実例: 2026-10-15 SinkaiFes2026 AZKi・エルセ・きまゆ）
