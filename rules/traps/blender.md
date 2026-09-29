---
paths:
  - "**/*.{blend,blend1}"
  - "**/bmcp/**"
  - "**/BMCP/**"
  - "**/*_addon/**"
---

# blender の罠

全件は ~/.claude/traps-catalog/blender.md。ここは再発しやすいものだけ。ステージ・小物制作の罠は skill blender-stage にある。

### ポーズや変換を行列で退避・復元しない
丸め誤差が出て、オイラー角が 370°→10° に、X 反転が全軸反転に化ける。原因は行列から分解し直すこと。→ location / rotation_* / scale を値のまま保存し、`frame_set` はポーズ復元より前に呼ぶ。（実例: 2026-09-17 / 09-26 BMCP）

### Blender 5.x で黙って変わった API
5.0 は `shape_key_add` の値が 1.0（4.2 は 0）で、足した途端に形が変わる。GN の入力は `mod["Socket_2"]` から `mod.properties.inputs.<id>` へ移り、旧経路は効かない。5.2 は `APPEND_REUSE` の代入が弾かれる。→ 値を明示し、`bpy.app.version` で分岐して見つからなければエラーにする。（実例: 2026-09-23 BMCP）

### 作った直後のオブジェクトは view_layer に見えない
作ってリンクした直後は `view_layer.objects` に無く、削除直後の列挙には None が混ざる。ID プロパティを変えてもドライバーは再評価されない。原因は depsgraph の同期の遅れ。→ `update_tag()` と `view_layer.update()` を挟み、None を除外して回す。（実例: 2026-09-16 BMCP）

### op の途中で redraw_timer を呼ぶと落ちる
演算子の実行中に `wm.redraw_timer` を呼ぶとアクセス違反で落ちる。SWAP 付きの直後の `screenshot_area` は 1×1。→ 進捗は `window_manager.progress_*`、再描画は `DRAW_WIN`。（実例: 2026-09-16 BMCP）

### インポーターに active_object=None を渡さない
`temp_override(active_object=None)` で FBX / glTF / VRM の取り込みを呼ぶと落ちる。インポーターが内部で active を参照するため。→ active は上書きせず、選択解除だけにする。（実例: 2026-09-16 BMCP）

### ボーンの親子付けは演算子でなくデータで
`parent_set(type='BONE')` はアクティブボーンが非表示コレクションにあると失敗する。長さ 0 のボーンは編集モードを抜けると黙って消える。親を外すと `parent_type` / `parent_bone` も消える。→ `parent` / `parent_type` / `parent_bone` を直接設定し、長さを先に検査し、外すときは控えて戻す。（実例: 2026-09-16 / 09-26 BMCP）

### show_only_shape_key のまま評価して焼かない
モディファイア適用で、ミュート中のキーが Basis に、頂点グループ付きのキーがマスク済みの形で焼かれる。Undo の後は Python の参照が切れる点も同じ作業で踏む。→ 評価の間だけ show_only / mute / vertex_group を外して finally で戻す。対象は名前で引き直す。（実例: 2026-09-16 BMCP）
