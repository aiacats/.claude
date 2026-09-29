---
name: vortex-character-setup
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、キャラクターモデルをシーンへ仕込む。NiloToon 変換 → マテリアル変換の抜け漏れチェック（MatCap/Emission）→ CharacterSetup 実行 → 旧方式(uLipSync/FacialManager)から新方式(OscRx_LipSync/vortex_FacialController)への付け替え → CharacterActivator と LookatManager への登録 → 既存キャラとの突き合わせ、までを行う。「キャラを仕込む」「モデルをセットアップ」「NiloToon 変換」「マテリアルの抜け漏れ確認」と言われたら使う。
---

# vortex キャラクターセットアップ

Submod_RealtimeLiveUtility（`jp.pjblue.realtime-live-utility`）を使う案件で、キャラ 1 体を既存キャラと同じ形に仕込む手順。

## 毎回ユーザーに聞くこと / 聞かないこと

**聞くのはこの 2 つだけ**（無ければ作業に入れないため）。
1. モデルのファイル（VRM / プレハブ）のパス
2. 仕込み先のシーン（指定されたシーンだけに入れる。他のシーンへ勝手に広げない）

**決定済みの既定値（2026-09-16 ユーザー決定。聞き直さない）**

| 項目 | 既定 |
|---|---|
| `OscRx_LipSync.characterID` | 0 |
| `OptitrackSkeletonAnimator.SkeletonAssetName` | `Skeleton1`（既定のまま） |
| `vortex_FacialController._expressions`（表情プリセット） | 空のまま。必要と言われたら既存キャラから複製 |
| `_controllerLabel` | 空 |
| 瞬き間隔 | 2500〜3000ms（既存キャラに合わせる） |
| マテリアル変換の取りこぼし | **勝手に直さない**。検査結果を報告し、直すかは判断を仰ぐ（見た目が変わるため） |

**判断を仰ぐのはここだけ**: マテリアルの修正可否、既存キャラの設定を書き換えるとき、
他シーンへの横展開、コミットの可否。作業そのもの（保存・起動・設定投入）はユーザーにやらせない。

## 0. 前提を確認する

- 仕込み先シーンは**ユーザーが指定したものだけ**。勝手に他のシーンへ入れない。
- Unity MCP が応答するか（`get_play_state`）。Unity が落ちていたら
  `Unity.exe -projectPath <プロジェクト>` で起動する（**管理者シェルからは起動しない**）。
- シーンに未保存の変更があるか確認する。この手順は最後に「保存せず開き直して破棄」で後片付けするため、
  **始める前に `save_scene` で保存しておく**（保存されていない他人の作業が消えるため）。
- 既存キャラの実例を 1 体決めておく（比較対象）。`Character/` 直下の `*(NiloToon)_setupped`。

## 1. NiloToon プレハブへの変換

`Window/vortex/NiloToon 複数プレハブ変換` で、Project ビューの VRM プレハブを選択して変換する。
`<名前>(NiloToon).prefab` と `<名前>(NiloToon)(Materials)/` ができる。

## 2. マテリアル変換の抜け漏れチェック（必須）

NiloToon の自動変換は **MatCap を取りこぼすことがある**（実測: 5 キャラ 24 マテリアル）。
`scripts/check_material_conversion.py` を `Assets/02_vortex_character`（キャラ置き場）で実行する。

```bash
python <スキルのパス>/scripts/check_material_conversion.py <キャラフォルダの親>
```

チェック内容:

| 元(MToon) | NiloToon 側の受け皿 | 落ちていたときの症状 |
|---|---|---|
| `_SphereAdd` | `_MatCapAdditiveMap` ほか MatCap 系 + `_UseMatCapAdditive`=1 + キーワード `_MATCAP_ADD` | MatCap が一切出ない |
| `_EmissionMap` / `_EmissionColor` | `_EmissionMap` / `_UseEmission` | 発光しない |
| `_MainTex` `_ShadeTexture` `_BumpMap` `_RimTexture` `_UvAnimMaskTexture` `_OutlineWidthTexture` | いずれかのスロット | テクスチャが反映されない |

**注意**: 変換後マテリアルに `_SphereAdd` の値が残っていても、NiloToon シェーダにそのプロパティは無いので**使われない**。
「値がある = 反映されている」ではない。受け皿側のスロットとスイッチで判定すること。

直す場合は `_MatCapAdditiveMap` にテクスチャを入れ、`_UseMatCapAdditive`=1、キーワード `_MATCAP_ADD` を有効にする。
**見た目が変わるので、直す前にユーザーへ確認する**。

## 3. シーンへ仕込む

`Window/vortex/CharacterSetup` が正規の導線。自動でやりたい場合は
`scripts/CharSetupTest.cs` を `Assets/_TempVerify/Editor/` に置き、`invoke_method` で
`CharSetupTest.SetupFull("<プレハブのパス>")` を呼ぶ（ウィンドウのボタンと同じ処理を反射で実行する）。

ツールがやってくれること:
- プレハブを配置し `_setupped` と命名、`Character/` 直下へ
- `OptitrackSkeletonAnimator`（Streaming Client / Destination Avatar を結線、Skeleton Asset Name は既定 `Skeleton1`）
- SkinnedMeshRenderer の rendering layer と Update When Offscreen
- `CharacterActivator` への登録（対象・Hips・secondary・入退場エフェクト 1.6 秒）

**ツールだけでは足りないところ**（毎回手当てが要る）:

1. **LookatManager に登録されない**。`LookatController` の GameObject が非アクティブだと
   `FindObjectOfType` が拾えず、**警告も出ずにスキップ**される。
   非アクティブも含めて探して手動で代入してから登録処理を呼ぶ（`CharSetupTest.cs` 参照）。
2. **口パク・表情が旧方式**。ツールは `uLipSync` 3 種 + `AudioSource` + `FacialManager` を付ける。
   既存キャラは `OscRx_LipSync` + `vortex_FacialController`（OSC 受信）なので付け替える。
   - `OscRx_LipSync`: `characterID`（既定 0）、`blendShapeProxy` にそのキャラの `VRMBlendShapeProxy`
   - `vortex_FacialController`: `_proxy` を同上、瞬き間隔は既存に合わせる（実測 2500〜3000ms。追加直後の既定は 500〜2500ms）
   - `_expressions`（ゲームパッド割当）は既存キャラが 14 件持っている。必要なら複製する
3. **位置・スケール**。ツールは原点・スケール 1 で置く。既存キャラは個別調整済み（例: x=0.5 / scale 1.2、scale 1.015）。

## 4. 既存キャラと突き合わせる

`CharSetupTest.Compare("<既存の名前>", "<今回の名前>", "<出力先>")` で、
コンポーネントの種類・順序・シリアライズ値・SkinnedMeshRenderer の設定を比較する。

**既存キャラは非アクティブなことが多い**ので、`GameObject.Find` ではなく
`Resources.FindObjectsOfTypeAll` で探すこと（アクティブしか見つからず「無い」と誤判定する）。

期待する結果: コンポーネント 12 件が一致。差分として出てよいのは
Transform（個別調整）・proxy 参照（自分自身を指す）・`_expressions`（方針次第）だけ。

## 5. 後片付けと報告

- テストだけなら、`EditorSceneManager.OpenScene` で**保存せず開き直して破棄**する
  （`CharacterActivator` / `LookatManager` への登録も一緒に消える）。
- 一時スクリプト（`Assets/_TempVerify/`）は必ず削除し、削除後にコンパイルが通ることを確認する。
- 本番で仕込んだ場合は `save_scene`。
- **仕込んだファイルを git にステージングする。コミットはしない（恒久・ユーザー指示 2026-09-16）**。
    - 対象は今回の作業で触れたものだけ（`git add <パス>` で明示する。`git add -A` や `.` は使わない）。
      典型的には 仕込み先シーン / `Assets/02_vortex_character/<キャラ>/` 配下（`(NiloToon).prefab`、
      `(NiloToon)(Materials)/`、VRM から生成されたフォルダ、`.meta`）。
    - **リポジトリには元から無関係な変更が溜まっていることがある**。`git status --short` で
      作業前後を見比べ、自分が触っていないものを巻き込まない。
    - サブモジュール側は触らない（`Submod_*` にコミットもステージングもしない）。
    - ステージング後に `git status --short` の結果（ステージ済み / 未ステージ）を報告に載せる。
- `log/claudeLog.txt` に、仕込んだキャラ・手当てした項目・マテリアルチェックの結果を追記する。

## 詰まりやすい点

- キャラを増やしたときの登録先は `System_PrimeStage/Controller/` に集約されている
  （`CharacterActivator._characters` / `LookatManager._lookatTargets` / `ExternalControlManager` /
  `MicController._targets` / `MeshActivator._controlMeshes`）。後ろ 3 つは空運用のこともある。
- `LookatManager._lookatTargets` の `_index` は既存が全部 0 で重複している。揃えるなら既存に合わせる。
- VRM 関連の DLL を Editor 限定にしないと Player ビルドがリンカで失敗した事例がある。
- 仕込み後は Play せずに済ませない。見た目はキャプチャで確認する。
