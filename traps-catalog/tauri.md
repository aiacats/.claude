# tauri の罠（カタログ）

Tauri 2 / WebView2 デスクトップアプリ（参考として Wails も）で踏んだ罠の全件。トラブル時に grep で引く。厳選版は `~/.claude/rules/traps/tauri.md`。

## スレッドと IPC

### 同期コマンドは UI スレッドで走る（画面ごと固まる・進捗が描かれない・窓が真っ白）
- 症状: 書き出し中にアプリ全体が停止し、進捗の仕組みはあるのにバーが出ない。収録を始めると画面全体がカクつく（実測 17ms → 32ms と収録に比例して伸びる）。キュー数千件で画面がもたつく。ConPTY の resize で「応答なし」（CPU 低）。映像用サブウィンドウが白いまま。
- 原因: `#[tauri::command] fn`（同期）はウェブビューの IPC ハンドラ = UI スレッドで走る。待つ間は `get_status` のような状態取得ごと止まる（進捗が出ないのではなく描く暇が無い）。同期コマンドの中でウィンドウを作ると WebView2 の初期化と待ち合う。Sequence ではさらに毎回ログ全体を走査していた。
- 対策: 時間のかかりうるコマンドは `async fn` + `tauri::async_runtime::spawn_blocking`。入力量に比例して伸びるもの（書き出し・取り込み・ログ走査・要約・応答待ち）は 1 回が短くても分ける。ウィンドウを作るコマンドは `async fn`。各コマンドの所要をログに出し、入力を増やして伸びるかを見る。Sequence は別スレッド化 + 差分読みで 7ms 横ばい。
- 実例: 2026-06-11 Claudes（ConPTY resize）/ 2026-09 Sequence（映像ウィンドウが白い）/ 2026-09-17 Sequence（書き出し・タイムライン要約）/ 2026-09-23 ftpDeck（一覧作成）
- 自動検出: hook `tauri-sync-command`
- 出典: rules/app.md:59-67, CLAUDE.md:26-37, Notion 3dee4d4b-751b-81ad-8c9c-d00a683e9d05, Seq/log/claudeLog.txt:2708-2716, 2779-2786, Seq/CLAUDE.md（映像ウィンドウは async）, ftpDeck/log/claudeLog.txt:897, Claudes:139-141

### async コマンドの中でブロッキング I/O を叩くと取り消しが返らない
- 症状: 取り消しコマンドが返らない。
- 原因: `#[tauri::command] async fn` の中で直接ブロッキング I/O（同期 FTP 等）を呼ぶと非同期ランタイムのワーカーを占有する。
- 対策: `spawn_blocking` 越しに呼ぶ。非同期版 suppaftp へ乗り換えない（`DataConnectionAlreadyOpen` を踏む）。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 不可
- 出典: rules/app.md:57-58, ftpDeck/CLAUDE.md:57

### 高頻度のイベント / ポーリングを UI へ生で流すと描画が詰まる
- 症状: タブ切替が重い（LTC 波形を 30fps × 1024 サンプルで IPC ポーリング）。音声メーターが「数秒おき」にしか動かない（ffmpeg 側は 47Hz）。
- 原因: 毎フレーム・毎行で重い state を emit / invoke し、WebView の再描画が引きずられる。
- 対策: 受信スレッドと配信スレッドを分け、溜まった分をまとめて 1 回で渡す。軽量な専用イベントに分けてスロットル。表示中のタブ・動作中だけに限定。レートは用途ごとに測って決め、根拠をコメントに残す（DMX 値・転送の進捗は実測 10Hz で足りた。メーター類は ~20-30Hz + rAF + ピークホールド）。
- 実例: 2026-04 SignalHub / 2026-07-19, 2026-07-20 SRT-Blue（Wails）
- 自動検出: 不可
- 出典: rules/app.md:68-72, SH/log/claudeLog.txt:179-182, SRT-Blue/log/claudeLog.txt:741, 758, 809-812

### React StrictMode で Tauri の listen の解除 Promise を取りこぼしリスナが多重登録される
- 症状: リスナが多重登録され、表示順などが一貫せず壊れる。進捗イベントが重複表示。純粋関数のテストは通る。
- 原因: 開発時の StrictMode は effect を mount → unmount → mount する。cleanup 時点で `listen()` の unlisten Promise が未解決で、解除できない。
- 対策: `disposed`（cancelled）フラグを持ち、遅れて届いた解除関数をその場で呼ぶ。
- 実例: 2026-06-05 AvolitesRemote / 2026-09-06 OSC2MIDI
- 自動検出: 候補 `listen\([^)]*\)\.then\(\s*\w+\s*=>\s*\w+\.push`（warn）
- 出典: Notion 3d3e4d4b-751b-8150-83ab-c94e5ed2447d, AvolitesRemote:45-46

## serde の境界

### serde の境界はハンドラより手前で落ち、ログに何も残らない（rename_all と頭字語）
- 症状: HyperDeck を含む cue だけ fire されない。`[CMD] cue_fire` のログすら出ない。
- 原因: `#[serde(rename_all = "snake_case")]` が `HyperDeckRecord` を `hyper_deck_record` にし、JS の `hyperdeck_record` と不一致。IPC の手前で deserialize に失敗するのでコマンドが呼ばれない（「Tauri command が呼ばれていない」≠「JS の invoke が呼ばれていない」）。
- 対策: 頭字語・略号を含む variant は `#[serde(rename = "...")]` を明示。JS が実際に送る JSON を Rust で `from_str` する対称テストを置く。
- 実例: 2026-04-26 SignalHub
- 自動検出: 候補 `rename_all\s*=\s*"snake_case"`（warn。正しい用途も多く誤検知する）
- 出典: rules/app.md:93-98, SH/log/claudeLog.txt:781-840

### enum の rename_all = "camelCase" は variant 名にしか効かない
- 症状: JS で `ev.firstIp` / `rttMs` が undefined。alive ハンドラが黙って例外を吐き IP 一覧が出ない。
- 原因: enum に付けた `rename_all` は variant 名だけを変換し、struct variant のフィールドは snake_case のまま。
- 対策: enum には `rename_all_fields = "camelCase"` も付ける。対称テストで確認。
- 実例: 2026-04 SignalHub
- 自動検出: 候補 `#\[serde\([^)]*rename_all\s*=\s*"camelCase"[^)]*\)\]\s*(pub\s+)?enum`（`rename_all_fields` が無いとき。unit variant だけの enum で誤検知）
- 出典: SH/log/claudeLog.txt:146-149, 290-291

### container に付けた #[serde(default)] が欠損フィールドを Default の非空値で埋め、移行が効かない
- 症状: 旧 settings.json（host/port）から新形式（destinations）へ移行されない。
- 原因: `Settings::default()` の destinations が localhost 1 件の非空 Vec なので、欠損時にそれで埋まり「空でない」と判定される。
- 対策: field-level の `#[serde(default)]` にして欠損は空 Vec にする。旧形式を書いて起動するテストを置く。
- 実例: 2026-07 ExtOsc
- 自動検出: 候補 `#\[serde\(default\)\]\s*\r?\n\s*(pub\s+)?struct`（warn）
- 出典: EXTOSC-LOG:86-91

### 入力途中の値を invoke すると serde の境界で落ちる
- 症状: IP 欄に `192.168.1.10` と打つと途中の `1` `19` … がエラー。数値欄も打ち途中の `5` で確定。別フィールドを変えた拍子に保存が失敗する（OscArg Int/Float）。enum を Rust に無いタグ `"enum"` で送って deserialize エラー。
- 原因: onChange ごとに `Ipv4Addr` 等の型で invoke。編集中の文字列を commit 前に数値化していない。フロントの型名と Rust の enum 表現の不一致。
- 対策: Enter / blur で確定する欄にし、確定前に Rust と同じ判定で検証する。すべての commit を sanitize 経由にして kind に合わせて数値化する。
- 実例: 2026-07 ExtOsc / 2026-09-03 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2023-2035, EXTOSC-LOG:26-27, 162-166

## 起動・ウィンドウ・dev

### 別プロジェクトの画面が出る（devUrl 1420 の衝突 / custom-protocol フィーチャ無し）
- 症状: 自分のウィンドウ（dev でも release でも）に別プロジェクト（FixtureTuner）の画面が出る。窓の題もプロセスも自分なのに中身が違う。
- 原因: (1) 全 Tauri プロジェクトが既定の localhost:1420 を使い、先に動いていた別プロジェクトの Vite が掴んでいた。(2) Cargo.toml に `custom-protocol` フィーチャが無いと `is_dev()` が真になり、素の `cargo build --release` でも devUrl を読む。開発サーバーが無いときは埋め込みに落ちるので気づけない。
- 対策: プロジェクトごとに固有ポートを割り当て、vite.config.ts（`strictPort: true`）と tauri.conf.json の devUrl を揃える。`[features] default = ["custom-protocol"]` と `custom-protocol = ["tauri/custom-protocol"]` を入れ、無い状態で作った exe は作り直す。確認は `netstat -ano | findstr :1420`。
- 実例: 2026-09-02 Sequence / 2026-09-02 ftpDeck
- 自動検出: 候補（patterns-app.md の `tauri-devurl-1420` / `tauri-custom-protocol-missing`）
- 出典: Notion 3cfe4d4b-751b-81f1-abc6-d737034b7af5, 3cfe4d4b-751b-81fd-bb1a-c9a4f7b2c958, Seq/log/claudeLog.txt:1650-1667, 1719-1720, ftpDeck/log/claudeLog.txt:62

### 同じ identifier の Tauri アプリを 2 つ起動すると 2 つ目のウィンドウが出ない
- 症状: `npm run tauri dev` で窓が出ない。ログにエラー無し、16x16 のダミー窓だけ。
- 原因: WebView2 のユーザーデータフォルダを共有しており、先行インスタンスがロックしている。
- 対策: 先に release 版を終了する。併存させたいなら dev 側の `WEBVIEW2_USER_DATA_FOLDER` を分けるか、dev 用に identifier を変える。
- 実例: 2026-09-02 FixtureTuner（2609SuiseiTour26）
- 自動検出: 不可
- 出典: rules/app.md:73-77, Notion 3cfe4d4b-751b-813a-bf74-dc779a01e1e1, 2609SuiseiTour26/log/claudeLog.txt:3570-3572

### single-instance プラグインがあると稼働中の exe が dev 起動を奪う
- 症状: `npm run tauri dev` を起動しても既存ウィンドウが前面に出るだけ。
- 原因: tauri-plugin-single-instance が既存プロセスへ引き渡す。
- 対策: 稼働中の release / インストール版を終了してから dev を起動する。
- 実例: 2026-06-12 Claudes
- 自動検出: 不可
- 出典: Claudes:185, 317-318

### 複数ウィンドウの additionalBrowserArgs が違うと 2 枚目を作れない
- 症状: 2 枚目のウィンドウが作れない。
- 原因: ユーザーデータフォルダを共有する WebView2 は、起動引数が違う環境を同時に持てない。
- 対策: 全ウィンドウで同じ文字列にし、一致をテストで固定する（Sequence: `browser_args_match_the_main_window`）。隠れた窓の間引きを切る引数もここへ入れる。
- 実例: 2026-09 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（映像: additionalBrowserArgs）

### src-tauri/ 配下へログを書くと tauri dev が開いては閉じるを繰り返す
- 症状: `npm run tauri dev` でウィンドウが開閉を高速反復し、src-tauri/log に .log が量産される。
- 原因: current_dir（= src-tauri）の log/ へ書く → tauri dev の監視が検知して再起動 → 新しいログを生成。
- 対策: dev は current_dir から上方向へ `package.json` を探してプロジェクトルート/log へ。配布 exe は exe の隣の log へ。
- 実例: 2026-06-11 Claudes
- 自動検出: 候補（patterns-app.md の `tauri-log-under-src-tauri`）
- 出典: rules/app.md:84-87, Claudes:94-106

### requireAdministrator のアプリは非管理者ターミナルからの dev 起動で失敗する
- 症状: `npm run tauri dev` が昇格要求で失敗する。
- 原因: マニフェストで管理者権限を要求している。
- 対策: dev は管理者ターミナルから起動する。配布 exe は UAC が出るだけ。
- 実例: （rules/app.md。日付不明）
- 自動検出: 不可
- 出典: rules/app.md:99-100

### identifier を変えると利用者の設定とウィンドウ位置が消える / .app で終わると警告
- 症状: identifier 変更後に設定とウィンドウ位置が初期化される。`com.signalhub.app` で非推奨警告。
- 原因: WebView2 のユーザーデータと設定の保存先が identifier で決まる。`.app` 終わりは macOS のバンドル拡張子と衝突。
- 対策: 既存の identifier は据え置く（`jp.<組織>.<アプリ名>` に揃えるのは新規のみ）。新規は `.app` で終わらせない。
- 実例: 2026-07-29 SignalHub
- 自動検出: 候補（patterns-app.md の `tauri-identifier-dot-app`）
- 出典: rules/app.md:101-103, SH/log/claudeLog.txt:884-888

### ウィンドウ位置の保存で最小化中の値や画面外の座標を復元する
- 症状: 次回起動で窓が見えない / サイズ 0。
- 原因: 最小化中（サイズ 0）の値を保存した。モニタ構成が変わり保存座標が画面外を指す。
- 対策: 最小化中は保存しない。画面外を指す場合は復元しない。
- 実例: （rules/app.md。日付不明）
- 自動検出: 不可
- 出典: rules/app.md:78-79

### Rust / Tauri プロジェクトを移動したら target を捨てる
- 症状: cargo check が `failed to read plugin permissions ... <旧パス>`。
- 原因: target に絶対パスが焼き込まれている。
- 対策: 移動後は src-tauri/target を削除して再ビルド。
- 実例: 2026-08-06 FixtureTuner（2609SuiseiTour26）
- 自動検出: 候補 `\b(mv|Move-Item)\b.*src-tauri`（warn）
- 出典: 2609SuiseiTour26/log/claudeLog.txt:1182-1185

### tauri.conf.json の version が package.json / Cargo.toml とずれる
- 症状: インストーラ名が古いバージョン（0.1.0）になる。
- 原因: バンドル名は tauri.conf.json の version を使う。
- 対策: 3 ファイルの version を揃える（または tauri.conf.json で package.json を参照）。
- 実例: 2026-04-15 IPing
- 自動検出: 不可（3 ファイル比較が要る）
- 出典: IPing:9

### tauri_build が rerun-if-changed を出すので build.rs の埋め込み時刻が更新されない
- 症状: フッタのビルド時刻・コミットが古いまま。
- 原因: `tauri_build::build()` が独自に rerun-if-changed を出し、build.rs が再実行されない。
- 対策: `.git/logs/HEAD` 等を rerun-if-changed に明示する。無いパスを宣言すると毎回再ビルドになるので存在するときだけ。
- 実例: 2026-09-02 ftpDeck / 2026-09-23 ftpDeck（2 回）
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:66, 950

## WebView の挙動・プラグイン

### Tauri v2 の WebView では window.prompt / confirm が無視される
- 症状: リスト追加・改名・削除確認が機能しない（ダイアログが出ずに素通り）。
- 原因: Tauri v2 の WebView で `window.prompt` / `window.confirm` が無効。
- 対策: 自前のモーダルか `@tauri-apps/plugin-dialog`。
- 実例: 2026-04 SignalHub
- 自動検出: 候補 `\bwindow\.(prompt|confirm|alert)\s*\(`（Tauri プロジェクトの .ts/.tsx に限れば warn）
- 出典: SH/log/claudeLog.txt:159-161, 294-295

### dragDropEnabled（既定 true）が HTML5 のドラッグ＆ドロップを横取りする
- 症状: dockview のタブドラッグ・分割ドラッグが効かない。
- 原因: WebView2 がネイティブのドラッグを横取りする。`dragDropEnabled: false` にすると HTML5 DnD は効くが Tauri のファイルドロップ（onDragDropEvent）が使えなくなる（排他）。
- 対策: どちらを取るか決め、`app.windows[].dragDropEnabled` を明示する。コンパイル時設定なので exe の再ビルドが要る。
- 実例: 2026-06-12, 2026-06-13 Claudes
- 自動検出: 不可
- 出典: Claudes:256-263, 357-368

### opener の allow-open-path は文字列だけだとパスのスコープが空で全拒否
- 症状: ダブルクリックでファイルを開けない。握り潰すと無反応、表示すると "Not allowed to open path ..."。
- 原因: capability の `"opener:allow-open-path"` はコマンド許可だけで path スコープが空。
- 対策: `{ "identifier": "opener:allow-open-path", "allow": [{ "path": "**" }] }` とスコープ付きで書く。capability はビルド時に組み込まれるので再ビルドが要る。
- 実例: 2026-06-12 Claudes
- 自動検出: 候補（patterns-app.md の `tauri-opener-scope-empty`）
- 出典: Claudes:217-233

### mpv の --wid 子ウィンドウが WebView の上に重なり DOM イベントを奪う
- 症状: タイルの右クリックメニューが開かない・ラベルが見えない・浮動メニューが映像の裏に隠れる。
- 原因: mpv がネイティブ子ウィンドウとして WebView の上に描画する。
- 対策: 操作 UI は映像領域の外（サイドレール等）に置き、インライン展開にする。
- 実例: 2026-08 SRT-Blue（Wails）
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:899-901

## 状態の持ち方（画面とバックエンド）

### 設定保存で画面の控えを丸ごと書き戻し、バックエンドが更新した値を巻き戻す
- 症状: 設定の「保存」で「最後に開いた場所」が起動時の値へ戻る。サーバー側でも未知キーが消える。
- 原因: 画面は起動時に読んだ Settings を持っており、その後バックエンドが別コマンドで更新した項目を知らない。
- 対策: 画面が編集する項目だけを取り込む（take_editable）。サーバー側の保存も生の内容へマージして未知キーを消さない。書き込みはアトミックに。
- 実例: 2026-09-05 SessionControl / 2026-09-16 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:659, SessionControl/log/claudeLog.txt:192

### UI の再読み込みでバックエンドの接続状態を見失う
- 症状: バックエンドは接続中なのに画面が「未接続」。
- 原因: 画面側だけが状態を持っていた。
- 対策: 起動時に実状態を取り直すコマンド（connection_info）を用意する。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:70

## updater・署名・配布

### updater: TAURI_SIGNING_PRIVATE_KEY_PATH は読まれない
- 症状: "A public key has been found, but no private key" で署名されない。
- 原因: tauri-cli が読むのは `TAURI_SIGNING_PRIVATE_KEY`（中身でもパスでも可）。
- 対策: `TAURI_SIGNING_PRIVATE_KEY` に鍵パスを入れる。
- 実例: 2026-08-21 SignalHub
- 自動検出: 候補（patterns-app.md の `tauri-signing-key-path`）
- 出典: SH/log/claudeLog.txt:1074-1076

### updater: パスワード無しの鍵でも環境変数が無いとパスワード入力待ちで止まる
- 症状: cargo-tauri.exe だけが生存し、コンパイラもバンドラも動かず 10 分以上停止。
- 原因: tauri-cli は `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` が無いと必ず対話プロンプトを出す。
- 対策: bash は `TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""`、.bat は `CI=true`。
- 実例: 2026-08-21 SignalHub
- 自動検出: 候補 `tauri\s+build`（同じコマンドに `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` も `CI=` も無いとき。updater を使わないプロジェクトで誤検知）
- 出典: SH/log/claudeLog.txt:1078-1082

### updater: bundle/nsis に旧バージョンの成果物が残る
- 症状: latest.json 生成で 1.0.0 の setup.exe を 1.0.1 として拾いかけた。
- 原因: `target/release/bundle/nsis/` は過去の全バージョンを残す。
- 対策: ファイル名にバージョンを含むものだけ採用する。
- 実例: 2026-08-21 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1084-1087

### updater: .sig は minisign テキストをさらに base64 で包んだ形式
- 症状: .sig をテキストとして読んで鍵 ID 行を探して失敗。
- 原因: 外側が base64。latest.json の signature にもこの外側のまま入る。
- 対策: 外側を decode してから中の行を読む。
- 実例: 2026-08-23 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1200-1203

### updater の秘密鍵を失うと既存インストールへ更新を配れない
- 症状: （予防）全クライアントがこの鍵の署名しか信用しない。
- 原因: updater の公開鍵は配布済み exe に埋め込まれている。
- 対策: 鍵をリポジトリ外に置き、暗号化バックアップ + 復元検証（key id 照合）を用意する。
- 実例: 2026-08-23 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1170-1190

### NSIS バンドル後の target/release/*.exe は署名が剥がれている
- 症状: 単体 exe が NotSigned。
- 原因: NSIS 用のリパッチで最後の署名が剥がれる（インストーラ内部のものは署名済み）。
- 対策: 配布は msi / setup.exe から。単体 exe を配るなら改めて signtool する。
- 実例: 2026-04-15 IPing
- 自動検出: 不可
- 出典: IPing:30

### 署名なし・自己署名の配布では SmartScreen の警告は消えない
- 症状: 配布先で SmartScreen 警告。署名したのに出る。`Get-AuthenticodeSignature` は UnknownError。
- 原因: Authenticode 未設定、または自己署名で信頼ルートに到達しない。信頼には CA 発行の OV/EV 証明書が要る。
- 対策: 配布用は商用 CA（OV/EV）か Azure Trusted Signing。Tauri は `bundle.windows.signCommand`。自己署名はパイプライン検証用。社内テストなら LocalMachine\Root と TrustedPublisher へインポート。signtool は Windows SDK 同梱。
- 実例: 2026-04 SignalHub / 2026-04-15 IPing / 2026-05-23 KachinkoShot（Python）/ 2026-07-18 SRT-Blue（Wails）
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:572-573, IPing:22-29, KachinkoShot:109, SRT-Blue/memory/installer-and-bundled-tools.md:17

### リリースビルド周り（dev が動いていると落ちる・resources の入れ忘れ・止まって見える・.bat の相対パス）
- skill tauri-release に記載（CARGO_BUILD_JOBS とコミット枠切れは rust カタログにも索引あり）。
- 実例: 2026-09-03 ftpDeck / 2026-09-13 ftpDeck（resources）/ 2026-09-23 tauri-release（2 回打ち切り）
- 出典: skills/tauri-release/SKILL.md, ftpDeck/log/claudeLog.txt:842, ftpDeck/CLAUDE.md:172

## Wails（参考。同じ WebView2 デスクトップ）

### Wails の窓が出ない = フロント初回レンダーの無限更新ループ
- 症状: プロセスは生存、`[WebView2] Environment created successfully` も出る、OnStartup も完走しているのに窓が出ない。特定画面・片方のビルドだけ再現。
- 原因: Wails はフロントの初回レンダーが idle になるまで窓を表示しない。自動スクロール（afterUpdate → scrollTop 設定 → scroll イベント → reactive 更新 → 再 afterUpdate）の無限ループ。
- 対策: 自動スクロールはデータ長の変化を購読して rAF で 1 回だけ設定し、プログラム起因のスクロールを無視する。切り分けは EnumWindows / IsWindowVisible で「無い」か「hidden」かを見て、App を trivial な div に差し替えて二分探索。production ビルドは console を stdout に流さない。
- 実例: 2026-07-18 SRT-Blue（variant / title / config / AppData を延々疑った）
- 自動検出: 候補 `afterUpdate\([\s\S]{0,200}scrollTop\s*=`（warn）
- 出典: SRT-Blue/log/claudeLog.txt:538-545, SRT-Blue/memory/wails-hidden-window-trap.md:10-19

### Wails を go build 直接で扱うときの必須フラグ
- 症状: "Wails applications will not build without the correct build tags." / Mac で `_OBJC_CLASS_$_UTType` 未定義。
- 原因: Wails CLI が付ける `desktop,production` タグが付かない。Wails v2 は macOS 11+ の UTType を使う。
- 対策: `-tags "desktop,production"`、Mac は `MACOSX_DEPLOYMENT_TARGET=11.0` と `CGO_LDFLAGS="-framework UniformTypeIdentifiers"`。
- 実例: 2026-05-10 SRT-Blue
- 自動検出: 候補 `\bgo\s+build\b(?![^\n]*-tags)`（Wails プロジェクト内のみ）
- 出典: SRT-Blue/log/claudeLog.txt:236-250

### wails build が巨大依存（tailscale.com/tsnet）でバインディング解析に失敗する
- 症状: `internal error: package "tailscale.com/tsnet" without types was imported from ...`。`-skipbindings` も効かない。
- 原因: Wails CLI の bindings parser が巨大依存ツリーを処理できない。
- 対策: `wails generate module` → `npm run build` → `go build` の手順に分ける。
- 実例: 2026-05-10 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:148-153, 211-215

### //go:embed の対象ディレクトリが新規 clone で空だと失敗する
- 症状: `pattern all:frontend/dist: no matching files found`。
- 原因: embed 先が ignore されて存在しない。
- 対策: `frontend/dist/.gitkeep` を追跡し、ignore は `frontend/dist/*` + `!frontend/dist/.gitkeep`。
- 実例: 2026-05-10 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:227-234

### EventsEmit 専用の型は Wails がモデルを生成しない
- 症状: フロントの型検査が 2 エラー。
- 原因: バインドされたメソッドの引数・戻り値に現れる型しか wailsjs に生成されない。
- 対策: イベント専用の型はフロント側で定義する。
- 実例: 2026-08-23 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:827

### 終了処理でロック解放を遅い Close の後に置くと、プロセスとロックが残る
- 症状: ウィンドウを閉じてもプロセスが残り、named mutex を掴んだまま「起動中」扱い。
- 原因: `lock.Release()` が `ts.Close()` の後で、Close が詰まると到達しない。
- 対策: ロックは最初に解放。各 Close に時間制限をかけ、最後に `time.AfterFunc(15s, os.Exit)` の強制終了網。
- 実例: 2026-07-20 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:796-801
