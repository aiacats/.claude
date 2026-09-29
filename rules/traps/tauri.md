---
paths:
  - "**/src-tauri/**"
  - "**/tauri.conf.json"
---

# tauri の罠

全件は ~/.claude/traps-catalog/tauri.md。ここは再発しやすいものだけ。

### 同期コマンドは UI スレッドで走る
`#[tauri::command] fn` の処理中は画面全体が固まり、`get_status` も止まるので進捗すら描かれない。同期コマンド内で窓を作ると真っ白になる。原因は同期コマンドがウェブビューの IPC ハンドラ = UI スレッドで走ること。→ 入力量に比例して伸びうるものは **`async fn` + `tauri::async_runtime::spawn_blocking`**。窓を作るコマンドも async。（実例: 2026-06-11 Claudes / 2026-09-17 Sequence / 2026-09-23 ftpDeck）

### async コマンド内でブロッキング I/O を叩かない
取り消しコマンドが返らなくなる。原因は async fn 内の同期 I/O がランタイムのワーカーを占有すること。→ `spawn_blocking` 越しに呼ぶ。（実例: 2026-09-02 ftpDeck）

### 別プロジェクトの画面が出る
自分の窓（dev でも release でも）に別アプリの画面が出る。原因は既定ポート 1420 を先着の別プロジェクトの Vite が掴んでいること、または Cargo.toml に `custom-protocol` フィーチャが無く release でも devUrl を読むこと。→ 固有ポート + `strictPort: true`、`[features] default = ["custom-protocol"]`。（実例: 2026-09-02 Sequence / 2026-09-02 ftpDeck）

### 2 つ目のウィンドウが出ない
dev を起動しても窓が出ない（16x16 のダミーだけ、ログも無し）か、既存窓が前面に出るだけ。原因は同じ identifier の起動中インスタンスと WebView2 のユーザーデータを共有していること、または single-instance プラグインが引き渡すこと。→ release / インストール版を終了してから dev。併存させるなら `WEBVIEW2_USER_DATA_FOLDER` を分ける。（実例: 2026-06-12 Claudes / 2026-09-02 FixtureTuner）

### src-tauri 配下へ実行時生成物を書かない
`tauri dev` の窓が開いては閉じるを繰り返す。原因は src-tauri/log へのログ書き込みを dev の監視が拾って再起動すること。→ dev は上方向へ `package.json` を探してルート/log へ、配布 exe は exe の隣へ。（実例: 2026-06-11 Claudes）

### serde の境界はハンドラより手前で落ちる
コマンドが呼ばれず、ログにも何も残らない。原因は `rename_all = "snake_case"` が頭字語を割る（HyperDeck → `hyper_deck`）こと、enum の `rename_all` が struct variant のフィールドに効かないこと（`rename_all_fields` が要る）、入力途中の値を型付きで invoke すること。→ variant ごとに `rename` を明示し、JS が送る JSON を Rust で `from_str` する対称テストを置く。入力欄は Enter / blur で確定。（実例: 2026-04-26 SignalHub / 2026-07 ExtOsc / 2026-09-03 Sequence）

### container の serde(default) は旧形式の移行を潰す
旧 settings.json から新形式へ移行されない。原因は構造体に付けた `#[serde(default)]` が欠損フィールドを `Default` の非空値で埋めること。→ field 単位の `#[serde(default)]` にし、旧形式で起動するテストを置く。（実例: 2026-07 ExtOsc）

### StrictMode で listen の解除を取りこぼす
リスナが多重登録され表示が壊れる（単体テストは通る）。原因は cleanup 時点で `listen()` の unlisten Promise が未解決なこと。→ `disposed` フラグを持ち、遅れて届いた解除関数をその場で呼ぶ。（実例: 2026-06-05 AvolitesRemote / 2026-09-06 OSC2MIDI）

### 高頻度イベントを UI へ生で流さない
メーターが数秒おきにしか動かない、タブ切替が重い。原因は毎行・毎フレームの emit / IPC ポーリングで WebView の再描画が詰まること。→ 受信と配信を分けてまとめて渡し、レートは測って根拠をコメントに残す。（実例: 2026-04 SignalHub / 2026-07-19 SRT-Blue）

### WebView の既定挙動が効かない
`window.prompt` / `confirm` が素通りする。HTML5 DnD が効かない（`dragDropEnabled` 既定 true が横取り。false にするとファイルドロップと排他）。opener の `"opener:allow-open-path"` 文字列だけではスコープが空で全拒否。→ plugin-dialog か自前モーダル、`dragDropEnabled` を明示、`allow: [{ "path": "**" }]` 付きで書く（capability と dragDropEnabled は再ビルドが要る）。（実例: 2026-04 SignalHub / 2026-06-12 Claudes）

### identifier を変えると利用者の設定が消える
設定とウィンドウ位置が初期化される。原因は WebView2 のデータと設定の保存先が identifier で決まること。→ 既存は据え置き、新規は `.app` で終わらせない。（実例: 2026-07-29 SignalHub）

### updater の鍵の環境変数
署名されない、またはビルドが 10 分以上無言で止まる。原因は `TAURI_SIGNING_PRIVATE_KEY_PATH` が読まれないこと（読まれるのは `TAURI_SIGNING_PRIVATE_KEY`）と、`..._PASSWORD` が無いとパスワード無しの鍵でも対話待ちになること。→ `TAURI_SIGNING_PRIVATE_KEY=<パス>` と `TAURI_SIGNING_PRIVATE_KEY_PASSWORD=""`（.bat は `CI=true`）。（実例: 2026-08-21 SignalHub）
