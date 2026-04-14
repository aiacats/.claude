---
name: lilToon Unity 6.3 修正作業状態
description: lilToon Unity 6.3 シャドウ修正の進行状況とアウトライン問題の調査状態
type: project
---

## 完了済み: 影の問題修正

**根本原因**: URP 17 で `_FORWARD_PLUS` が `_CLUSTER_LIGHT_LOOP` にリネームされ、lilToon が Forward+ を検出できなかった。追加ライトが頂点シェーダーの mode 4 で処理され、カメラ移動でクラスタ境界のライト寄与が不連続に変化。

**修正**: `lil_common_macro.hlsl` の Forward+ 検出条件 2箇所に `USE_CLUSTER_LIGHT_LOOP` / `_CLUSTER_LIGHT_LOOP` を追加。

**How to apply:** lilToon を `Packages/jp.lilxyzw.liltoon/` にローカルパッケージ化済み。manifest.json は `"file:jp.lilxyzw.liltoon"` を参照。

## 未解決: アウトラインが表示されない問題

lilToonMultiOutline でアウトラインが描画されない。Forward+ 修正とは無関係（修正を戻しても復活しない）。

**調査済み:**
- ltsmulti_o.shader の FORWARD_OUTLINE パスは正常（LightMode = SRPDefaultUnlit、Name = FORWARD_OUTLINE）
- Fallback Off の変更は復元済み（元の "Universal Render Pipeline/Unlit" に戻した）
- ShaderCache 削除済み
- GetShadowCoord 重複エラーは lilGetShadowCoord にリネームして解消
- Editor.log の最新部分にはコンパイルエラーなし

**次のステップ:** Unity MCP をセットアップ中。`.mcp.json` 作成済み、npm install 済み。Claude Code の再起動が必要。再起動後に `get_console_logs` / `check_compilation_status` で現在のエラーを確認し、アウトラインの問題を調査する。

**追加変更（デバッグ中のクリーンアップ必要）:**
- `lil_common_macro.hlsl`: GetShadowCoord を lilGetShadowCoord にリネーム、Fog 計算を元に戻した（Fallback Off も戻した）
- `ltspass_*.shader`: Fallback を元の "Universal Render Pipeline/Unlit" に戻した
