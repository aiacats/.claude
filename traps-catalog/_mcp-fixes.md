# 自作 MCP 本体を直せば消える罠（未対応の一覧）

2026-09-29 の罠の洗い出しで、「使う側が気をつける」より「MCP 本体を直す」方が筋だと分かったもの。
CLAUDE.md「足りない機能は自分で足す」に従い、その MCP を触るときに合わせて直す。直したら行を消し、カタログ側の該当項目に「vX.Y で修正」と書く。
（各項目の根拠は同じフォルダの分野別カタログ。ここに書いたのは材料からの提案で、ソースで今も未対応かは直す前に確かめること）

## Unity MCP（D:\_Personal\Project\unity-mcp）
- `get_console_logs` がワーカースレッド発のログを拾わない（`logMessageReceived` だけを購読。`logMessageReceivedThreaded` も要る）
- `force_compilation` の既定が全アセットの再インポート（`forceUpdate` の既定が true）
- `update_component` / `update_gameobject` が未知のキーを黙って無視して success を返す。objectPath の参照が null、nested struct を渡すと全フィールドが 0 に戻る
- `invoke_method` のインスタンス target の解決に失敗する（479f918 の修正後も 3 回再発）
- `set_scenes` に `m_path` / `m_enabled` が要る
- `set_object_properties` が VolumeParameter に対応していない
- UnityEvent の永続コールを編集できない
- `set_material_property` で `disabledShaderPasses` が落ちる
- `build_player` が失敗しても errors=0 を返すことがある
- Camera を作っても `UniversalAdditionalCameraData` が付かない

## BMCP（D:\_Personal\Project\BMCP）
- 未知の引数を黙って捨てる → define.ts の input を zod `.strict()` にしてエラーにする。`blender_status` で addonVersion とサーバーの VERSION を比べ、ずれていれば warnings に出す（今は protocolVersion だけ。bridge.ts:144）
- `blender_export_fbx` が小さい FBX で上書きしても気付けない → 結果にバイト数とオブジェクト数を入れ、既存より極端に小さければ警告する
- FBX で色が落ちる（Base Color が Mix / Mapping 経由）→ preset=unity のとき、画像に直結していないマテリアルと倍率 1 でない Mapping を warnings に列挙する
- `blender_export_fbx` の hierarchy 指定が黙って捨てられる
- `run_python` で踏む罠 → source に `redraw_timer` があれば拒否する。実行後、value が 0 でない新しいシェイプキーがあれば警告する。description に view_layer.update / update_tag / active_object=None / 5.x の API 差分 / 行列で退避しない、を書く
- Blender を複数クライアントで共有している → `blender_status` に接続中のクライアント数を出す。instructions に「open_file / new_file の前に確認する。検証は `-b` の別プロセスで」
- `blender_capture` に Empty を渡すと画角が潰れる → 子メッシュの範囲で撮る

## AEMCP（D:\_Personal\Project\AEMCP）
- JSX で AE が無応答になる → `ae_run_script` が送る前に source を検査し、文字クラス内の素の `/` と `renderQueue.render()` を拒否する（後者は `ae_render` へ案内）
- ExtendScript の癖を `ae_run_script` の description に書く（undefined 引数 / `save(file)` は別名保存 / `layer.index` / allFonts の入れ子 / キー付きプロパティへの setValue / setValuesAtTimes）
- instructions に「AE を強制終了しない（CloseMainWindow）」を書く。launch-ae.ps1 で作業ディレクトリをリポジトリの外に固定する（AEMCP 直下に HAP-log.txt と `NVIDIA Corporation\` が残っている）

## DvcMCP（D:\_Personal\Project\DvcMCP）
- `run_python` の名前空間の Resolve オブジェクトを包み、書き込み系が None を返したら RESOLVE_BLOCKED で止める
- description に「区間は [start,end)、AppendToTimeline の end は含む」「SetClipsLinked より mediaType 無しの Append」「WAV は Duration」を書く
- `resolve_media_import` で同じパスがプールにあり、ファイルの方が新しければ入れ直しを促す（今見ているかは未確認）

## WinGui MCP（D:\_Personal\Project\WinGuiMcp）
- ナビゲーションキーの修正（wScan / EXTENDEDKEY）がソースにだけあり、publish が古い → publish し直す
- `key_press` で Win キーを送れない（仮想デスクトップ操作が tools/virtual-desktop.ps1 頼み）
- `capture_window` が Chrome を真っ黒に撮る
- クリック前に対象が前面か確かめない（PostMessage 送信の口が無い）
- `find_window` / `capture_window` がタイトルの部分一致でターミナルを掴む
- `type_text` が連打キーと長文を取りこぼす
- `click_text` が日本語 OCR に対応せず、本文中の同じ語を押す
- `key_press("Escape")` が mpv に届かない
