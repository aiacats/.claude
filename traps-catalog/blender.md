# blender の罠（カタログ）

Blender（bpy・アドオン・モディファイア・シェイプキー・リグ・UV・書き出し）と BMCP で踏んだ罠の全件。ステージ・小物制作の罠は skill blender-stage が正。

### op の途中で redraw_timer を呼ぶと Blender が落ちる／SWAP 付きの直後の screenshot は 1×1
- 症状: 演算子の実行中に `wm.redraw_timer` を呼ぶとアクセス違反（`UI_panel_category_draw_all`）でクラッシュ。`DRAW_WIN_SWAP` / `DRAW_SWAP` の直後に `screenshot_area` で撮った画像が 1×1。
- 原因: 演算子実行中の UI 再描画は Blender 側で安全でない。スワップ後のバッファは空。
- 対策: 進捗は `window_manager.progress_begin/update/end` で出す。再描画させるなら `DRAW_WIN` を使う。
- 実例: 2026-09-16 BMCP
- 自動検出: 候補 `blender-redraw-swap`（patterns-dcc.md。SWAP 側のみ。op 中かどうかは判定できない）
- 出典: BMCP\CLAUDE.md:56-72 / BMCP\log\claudeLog.txt:24 / Notion 3dde4d4b-751b-81d8-a78b-e1b32d93919b

### op の実行中は Blender の UI ボタン（キャンセル等）が押せない
- 症状: 長い op の間、パネルのキャンセルボタンが反応しない。
- 原因: メインスレッドが op に占有される。
- 対策: Esc を OS のキー状態（GetAsyncKeyState）で見張る別スレッドで取り消しを受ける。長いループには progress / check_cancel を挟む。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:73-75

### 作成直後のオブジェクトが view_layer.objects に無い／削除直後の列挙に None が混ざる
- 症状: 作ってリンクした直後のオブジェクトが `view_layer.objects` に出ない。削除直後の列挙に `None` が残る。
- 原因: view layer の同期が遅延する。
- 対策: `bpy.context.view_layer.update()` を挟んでから引く。列挙は None を除外する補助関数を通す。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:76-78 / Notion 3dde4d4b-751b-81fd-b139-da6daae2c505

### Python から ID プロパティを変えてもドライバーが再評価されない
- 症状: カスタムプロパティを書き換えても、それを参照するドライバーの結果が変わらない。
- 原因: Python からの ID プロパティ変更は depsgraph にタグ付けされない。
- 対策: `update_tag()`（`refresh={'OBJECT','DATA'}`）+ `view_layer.update()` を呼ぶ。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:79-80 / Notion 3dde4d4b-751b-81fd-b139-da6daae2c505

### インポーター（FBX/glTF/VRM）に active_object=None の temp_override を渡すと落ちる
- 症状: `temp_override(active_object=None)` で取り込みを呼ぶと失敗する。
- 原因: インポーターは内部でコンテキストの `active_object` を参照する。
- 対策: active を上書きせず、選択解除だけにする。
- 実例: 2026-09-16 BMCP
- 自動検出: 候補 `blender-importer-active-none`（patterns-dcc.md）
- 出典: BMCP\CLAUDE.md:95-96 / BMCP\log\claudeLog.txt:27 / Notion 3dde4d4b-751b-8195-841d-f6f8cacc9f4a

### parent_set(type=BONE) が失敗する／長さ 0 のボーンが黙って消える
- 症状: コントロールリグ生成後（Deform コレクション非表示）に BONE 親子付けが失敗する。つま先の無い足などでコントロール作成が失敗し、ボーンが無くなっている。
- 原因: 演算子は表示中のボーンしか対象にしない。head==tail のボーンは編集モードを抜けると削除される。
- 対策: 演算子を使わず `parent` / `parent_type='BONE'` / `parent_bone` をデータで直接設定する。ボーンを作る前に長さを検査する。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可（`parent_set(type='BONE')` 自体は表示中なら正しいので、正規表現では誤検知になる）
- 出典: BMCP\CLAUDE.md:111-114 / Notion 3dde4d4b-751b-815b-bb66-d78398e62624

### ボーン親のオブジェクトの親を外して戻すと OBJECT 親になる
- 症状: 一時的に親を外して戻したら、骨に付いていた root がオブジェクト親に変わる。
- 原因: 親を外すと `parent_type` / `parent_bone` が消える。
- 対策: `parent_type` と `parent_bone` も控えて復元する。
- 実例: 2026-09-26 BMCP
- 自動検出: 不可
- 出典: BMCP\log\claudeLog.txt:406

### Undo で読み直すと Python の参照が切れる
- 症状: Undo 後に保持していたオブジェクト参照へアクセスすると無効。
- 原因: Undo は main database を再読み込みする。
- 対策: モードや対象の復元は名前で行う。書き込み op の Undo はオブジェクトモードで「前」を積んでからモードを戻す（編集モードで積むと編集メッシュの Undo になり op の変更が入らない）。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:102-106

### show_only_shape_key のまま評価するとミュート中・頂点グループ付きのキーが壊れる
- 症状: モディファイア適用で、ミュート中のキーが Basis に、頂点グループ付きキーがマスク済みの形で焼かれる。
- 原因: 単独表示中の評価結果はミュート・マスク状態を反映した形になる。
- 対策: 評価の間だけ `show_only_shape_key` / mute / vertex_group を外し、finally で戻す。
- 実例: 2026-09-16 BMCP（回帰テスト ModifierTests.test_apply_keeps_muted_and_masked_keys）
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:107-110 / Notion 3dde4d4b-751b-81dc-aff7-de6bff45cbd3

### ポーズや変換を行列で退避・復元すると値が化ける（370°→10°）
- 症状: 丸め誤差が出る。オイラー角が同じ向きの別表記（370°→10°）に変わる。X 反転が全軸反転になる。
- 原因: 行列経由で分解し直すため。
- 対策: 各チャンネル（location / rotation_* / scale）を値のまま保存する。フレームを戻すのはポーズ復元より前（`frame_set` がアニメ値で上書きするため）。
- 実例: 2026-09-17 BMCP / 2026-09-26 BMCP（アセット書き出しで変換を行列で戻した）
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:123-126 / BMCP\log\claudeLog.txt:407

### Blender 5.0 で shape_key_add の追加時の値が 1.0 になった
- 症状: 5.x で `shape_key_add` した途端に形が変わる。transfer 等で 2 つ目以降の差分が狂う（服が 10cm ずれた）。
- 原因: 追加時の value が 5.0 は 1.0、4.2 は 0.0。
- 対策: 生成箇所を 1 関数に集約し `value = 0.0` を明示する。テスト・フィクスチャでも値を明示する。
- 実例: 2026-09-23 BMCP
- 自動検出: 候補 `blender-shape-key-add-no-value`（patterns-dcc.md）
- 出典: BMCP\CLAUDE.md:140-142 / BMCP\log\claudeLog.txt:153-166 / Notion 3e4e4d4b-751b-81b3-baaa-c04311deede4

### Blender 5.0 で Geometry Nodes の入力 API が変わった（mod["Socket_2"] が効かない）
- 症状: 5.x で `mod["Socket_2"] = ...` が効かない（4.2 の書き方）。
- 原因: 5.0 で `mod.properties.inputs.<識別子>.value / .type / .attribute_name` へ移行。ポインタ型ソケットは attribute_name を持たない。
- 対策: `bpy.app.version >= (5, 0)` で分岐し、見つからなければ黙って旧経路へ落とさずエラーにする。
- 実例: 2026-09-23 BMCP
- 自動検出: 候補 `blender-gn-socket-index`（patterns-dcc.md）
- 出典: BMCP\CLAUDE.md:135-139 / BMCP\log\claudeLog.txt:141-143 / Notion 3e4e4d4b-751b-81b3-baaa-c04311deede4

### Blender 5.2 で link/append の取り込み方に APPEND_REUSE を代入すると弾かれる
- 症状: RNA 定義には APPEND_REUSE があるのに代入するとエラー。
- 原因: 5.2 で有効値は LINK / APPEND / PACK。
- 対策: 版で選ぶ。
- 実例: 2026-09-26 BMCP
- 自動検出: 候補 `blender-append-reuse`（patterns-dcc.md）
- 出典: BMCP\log\claudeLog.txt:388

### 画像を unpack(USE_ORIGINAL) するとパス文字列が正規化される
- 症状: パック→アンパックで相対パス `//textures/..` が別の表記に書き換わる。
- 原因: unpack がパス文字列を正規化する。
- 対策: 元の filepath 文字列を控えて戻す。
- 実例: 2026-09-26 BMCP
- 自動検出: 不可
- 出典: BMCP\log\claudeLog.txt:389

### Blender 4.2 のバックグラウンド（-b）では gpu 描画も blf.bind_imbuf も無い
- 症状: `-b` 実行で画像へのラベル描画ができない。
- 原因: バックグラウンドには GPU コンテキストが無く、4.2 には `blf.bind_imbuf` も無い。
- 対策: Pillow で描く（Extension の wheels に同梱）。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: MEM(BMCP)\project-decisions.md:23

### Extension の wheel は Python の版ごと（Blender 5.2 で読めない）
- 症状: Blender 5.2 で「This Python version (3.13) isn't compatible with (3.11)」でアドオンが読めない。
- 原因: 同梱の Pillow が cp311 の wheel だけだった（Pillow は abi3 を配っていない）。
- 対策: cp311 と cp313 の両 wheel を同梱する。テスト用の展開先も版ごとに分ける。
- 実例: 2026-09-23 BMCP
- 自動検出: 不可
- 出典: BMCP\log\claudeLog.txt:132-140 / BMCP\CLAUDE.md:160-162

### シェイプキー付きメッシュに Decimate / Weld を適用するとキーが壊れる
- 症状: 適用後にシェイプキーが壊れる（頂点数は同じでもつながりが違う）。
- 原因: トポロジーが形状依存で変わるモディファイア。
- 対策: 辺の配列まで比較して一致しなければ拒否する（頂点数だけでは見逃す）。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:92-94

### BVHTree.find_nearest の法線で符号付き距離を測ると短く出る
- 症状: 押し出しが 6 割しか届かない。
- 原因: 最寄り点が辺・頂点のとき `(p-loc)·normal` は距離を短く見積もる。
- 対策: `|p-loc|` に符号を付けた真の符号付き距離で測り、届くまで測り直す。
- 実例: 2026-09-17 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:127-130 / Notion 3dde4d4b-751b-81fa-b259-f2516fd76676

### 重なった頂点を縫い目の隙間と決めつけて結合すると表情が壊れる
- 症状: 閉じた唇・まぶたを結合して口が開かなくなる。
- 原因: レストで重なっていてもシェイプキーで離れる頂点がある。
- 対策: シェイプキーの位置まで比べて除外する。
- 実例: 2026-09-17 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:131-134

### IK のポール角の符号を誤ると膝が後ろへ折れる／一直線の手足は解が定まらない
- 症状: 膝が逆に折れる。股・膝・足首が一直線だと IK が定まらない。
- 原因: よく出回る式の `signed_angle` の符号の約束。
- 対策: 符号規約を確かめて使う（BMCP は `rig/common.pole_angle`）。一直線の手足には最小の曲げを付ける。
- 実例: 2026-09-16 BMCP
- 自動検出: 不可
- 出典: BMCP\CLAUDE.md:81-87 / Notion 3dde4d4b-751b-81ff-b6fe-c7cb4d2aa749

### ステージ・小物制作の罠（skill blender-stage に記載）
- 画像保存前に colorspace を設定すると真っ黒な PNG（Notion 3e4e4d4b-751b-8169-8040-cdaaafe1005d）
- 作った直後のオブジェクトを親にすると子が二重に移動する／移動直後の matrix_world は 1 手前（Notion 3e4e4d4b-751b-8101-a34a-fba3b079ea3f）
- 編集モードの演算子（`bpy.ops.uv.*`）は run_python から poll() で落ちる → `blender_mesh_uv_project`
- Base Color の手前に Mix があると FBX で色が落ちる（Unity で白い）／Mapping の拡大率は FBX に出ない／手続き型ノードは書き出せない（実例 2026-09-25 BMCP / 2026-09-26 Ext_TokinoSora_2026-pia）
- BMCP を更新した直後は Blender と Claude Code が古い版のまま。新しい引数が黙って捨てられ、10KB の FBX で上書き（実例 2026-09-26 BMCP / Ext_TokinoSora_2026-pia）
- Base Color の数値はリニア値／8bit 画像の pixels は sRGB（Notion 3e7e4d4b-751b-812a-a0bd-e1c407a49996）
- `bmesh.ops.create_uvsphere(calc_uvs=True)` は UV レイヤーが先に無いと UV を作らない
- `node_tree.nodes` は毎回別ラッパーで `is` 比較が偽（Notion 3e7e4d4b-751b-8100-a279-dc61346f8942）
- EEVEE の Volume プローブは部屋より一回り大きく／INVOKE のベイクは run_python の中で進まない（Notion 3e7e4d4b-751b-81c6-8db3-f768db5fb479）
- Poly Haven の色テクスチャ名の揺れ／黙って単色へ落とさない
- オブジェクトを消してもメッシュデータが残り `.001` が付く
- 厚み 0 の片面ポリゴンは Unity の背面カリングで消える
- Euler の成分を足して回転を合成しない
- GLB 由来のメッシュは面ごとに頂点が分かれている
- 共有中の Blender で `read_homefile` / `open_mainfile` しない。検証・アセット登録は別プロセス（`blender -b ... -P`）で行う（実例 2026-09-26 BMCP / band_studio）
- `blender_capture` に Empty を渡すと画角が潰れる／室内は外から撮るので見えない／Workbench はノードの色を見ない
- 出典: skills\blender-stage\SKILL.md「先に読む」「Unity へ出す」
