# rust の罠（カタログ）

Rust（tokio・並行処理・クレートの仕様・ビルド）で踏んだ罠の全件。Tauri 固有のものは tauri カタログ。末尾に Go（tsnet）を参考として置く。

## ロック・チャネル・スレッド

### Mutex を保持したままブロッキング I/O や外部プロセス起動をすると、無関係な操作まで固まる
- 症状: セッションは開けるが入力不可・新規作成も不可（デッドロック）。別の機器を触っているのに画面が固まる。rclone 起動失敗で後続が 10 秒ずつ直列に止まる。
- 原因: マップ全体の Mutex を保持したまま PTY の write / resize・taskkill を実行（Claudes）。レジストリのロックを持ったまま機器 I/O（ftpDeck）。起動待ちの間ロックを握っていた（ftpDeck）。UI からは原因が見えない。
- 対策: ロック内は共有データ構造の出し入れ（`Arc` の取り出し）だけにし、I/O はロック解放後。disconnect / keepalive は `try_lock`。起動用の錠は分け、落ちていたら起こし直す。
- 実例: 2026-06-11 Claudes / 2026-09-06 ftpDeck / 2026-09-13 ftpDeck
- 自動検出: 不可
- 出典: rules/app.md:88-90, Claudes:136-156, ftpDeck/CLAUDE.md:42, ftpDeck/log/claudeLog.txt:875

### 受け手のいない channel に送ると黙って捨てられる
- 症状: 再生してもシークバーが進まない（エラーも出ない）。収録していない間も dropped が増える。
- 原因: mpsc の受信側（`_frame_rx`）を即 drop し、`try_send` が黙って捨てられていた。「UI に何も届かない」という原因から遠い症状で出る。
- 対策: 受信タスクを必ず spawn して消費する（UI へは Tauri の Channel で流す）。
- 実例: 2026-02-20 natnet-recorder / Sequence（project-only の同型）
- 自動検出: 候補（patterns-app.md の `rust-channel-receiver-dropped`）
- 出典: rules/app.md:91-92, natnet-recorder:246-262

### チャネルを作り直すと、相手が持っている古い口へ送られて届かない
- 症状: 待ち受けの起動・停止を繰り返すと合図が届かなくなる。
- 原因: 待ち受けごとにチャネルを作り直し、相手の Sender / Receiver が古いまま。
- 対策: チャネルは所有者（AppEngine）が 1 本持ち続ける。
- 実例: 2026-08 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:1331-1332

### チャネルの一括ドレイン（while rx.try_recv().is_ok()）で直後のイベントまで捨てる
- 症状: 収録開始直後のイベントを取りこぼす。
- 原因: 「開始前の溜まり」を捨てるドレインが、開始直後に届いたものまで巻き込む（競合）。
- 対策: 到着タイムスタンプで選別する（`arrival < epoch` なら捨てる）。
- 実例: 2026-08 Sequence
- 自動検出: 候補（patterns-app.md の `rust-try-recv-drain`）
- 出典: Seq/CLAUDE.md（チャネルの一括ドレイン）

### 受信スレッドから重い処理を直接呼ぶと後続を取りこぼす
- 症状: OSC の合図で収録開始（ファイル生成）している間、続く合図を取りこぼす。開始と停止が同時に走ると順序不定。
- 原因: 受信ループ内で同期実行している。
- 対策: 受信はチャネルへ流すだけにし、実行スレッド 1 本で順に処理する。
- 実例: 2026-08 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:1326-1329

### ワーカー退避とジョブ投入の競合でキューが恒久停止する
- 症状: 転送が終わった直後に次を積むとジョブが Queued のまま。
- 原因: 「取るものが無い」判定とワーカー数の減算がロック外で分かれていた。
- 対策: 判定と減算を同じロックで行う（take_next_or_retire）。
- 実例: 2026-09-03 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:111

### 待ち行列への登録と送信が別ロックで応答を取り違える / タイムアウトで読み取りタスクが残る
- 症状: 同時コマンドで応答がずれる。read で止まったタスクが残留。
- 原因: 順序保証の欠如。
- 対策: 書き込みロックを保持したまま登録する。タイムアウト時はソケットを閉じて解放する。
- 実例: 2026-09-03 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:123-130

### spawn したタスクへ Instant を値コピーで渡すと後からのリセットが効かない
- 症状: 録画タイマーが「録画開始から」ではなく「接続時刻から」になる。
- 原因: `let start_time = self.start_time;` をタスクへ move。後の `reset_start_time()` はタスク側のコピーに届かない。
- 対策: 実行中に変わる値は `Arc<Mutex<Instant>>` / `Arc<AtomicU64>` で共有する。
- 実例: 2026-02-20 natnet-recorder
- 自動検出: 不可
- 出典: natnet-recorder:200-215

### std::sync::Mutex のガードが await をまたぐと future が !Send
- 症状: tokio::spawn / Tauri async command でコンパイルエラー。
- 原因: ガードが async fn の状態機械に残る。
- 対策: `let v = M.lock().unwrap().clone();` で即コピーしてガードを落とす（ブロックで囲む）。
- 実例: 2026-04 SignalHub
- 自動検出: 不可（コンパイラが出す）
- 出典: SH/log/claudeLog.txt:296-298

### 再帰的な async 呼び出しで Send 推論が破綻する
- 症状: fire() が別タスク経由で fire() を呼ぶ形でコンパイル不能。
- 原因: recursive async の opaque return に対して auto-trait Send 推論が破綻。
- 対策: mpsc チャネル経由にして本体を線形化する。
- 実例: 2026-04 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:286-288

### 中断が効かない（子プロセスが残る・キャンセル検知が後回し）
- 症状: スキャンを止めても止まらない。
- 原因: 子プロセス（ping）が残り、キャンセル検知が後回しになる。
- 対策: `JoinSet` + `select! { biased; ... }` で cancel 検知 / abort_all / drain を 1 ループに。`tokio::process::Command` に `kill_on_drop(true)`。
- 実例: 2026-04 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:151-153, 289-290

### hidapi の HidDevice は Send だが Sync ではない
- 症状: Stream Deck を複数スレッドから触れない。
- 原因: HidDevice / elgato-streamdeck に Sync 実装が無い。
- 対策: 単一の所有スレッドが読み取りと描画を担い、書き込みは mpsc で渡す。
- 実例: 2026-08 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:995-998

### parking_lot::Mutex::try_lock は Option を返す（std は Result）
- 症状: `if let Ok(..) = m.try_lock()` がコンパイルエラー。
- 対策: parking_lot は `if let Some(g) = m.try_lock()`。
- 実例: 2026-03-07 Aether
- 自動検出: 不可（コンパイラが出す）
- 出典: Aether:20

## 子プロセス・エラー処理・パス

### 子プロセスの stderr を読まずにパイプへ溜めるとデッドロック
- 症状: ffmpeg とアプリが互いに待って止まる。
- 原因: パイプバッファが満杯になる。
- 対策: 別スレッドで読み切る。
- 実例: 2026-09-13 ftpDeck
- 自動検出: 不可（「読むコードが無い」は正規表現で判定できない）
- 出典: ftpDeck/log/claudeLog.txt:866

### アプリ終了時に子プロセス（ffmpeg / rclone rcd）が残る
- 症状: 閉じても ffmpeg が残る。
- 対策: 走っている子を覚えて `RunEvent::Exit` で止める。
- 実例: 2026-09-13 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:864

### 失敗を let _ = / .ok() / 空配列で握り潰すと真因が隠れる
- 症状: ABOR 失敗後に同じセッションを使い回し「原因の分からない失敗」。ソケットタイムアウト設定失敗で無制限ブロック。ローカル読み取り失敗が「ファイルがありません」表示に化ける。
- 対策: 失敗を呼び出し元へ返す（Outcome で session_usable を伝える、Result を返す）。
- 実例: 2026-09-03 ftpDeck
- 自動検出: 候補 `let _ = [^;]*(abort|set_(read|write)_timeout)`（warn）
- 出典: ftpDeck/log/claudeLog.txt:131-147

### anyhow の with_context で包むと to_string() で原因が見えない
- 症状: エラー文言を検査するテストが通らない。
- 原因: context の下に原因が積まれ、`to_string()` は最上位だけ。
- 対策: `format!("{:#}", e)` で連鎖ごと見る。
- 実例: 2026-08-30 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:928-929

### PathBuf::join はリモート由来の名前で保存先を抜け出せる
- 症状: 区切り・ドライブ表記を含む名前で左側が捨てられる（パストラバーサル）。
- 原因: join は絶対パスや prefix を含むと置き換える。
- 対策: 空 / `.` / `..` / `/` `\` `:` / 制御文字を拒否する safe_component を通す。
- 実例: 2026-09-03 ftpDeck
- 自動検出: 候補 `\.join\(\s*&?(entry|name|remote)`（warn。誤検知多め）
- 出典: ftpDeck/log/claudeLog.txt:149

### cargo run の出力先が作業ディレクトリ依存になる（target/debug/log）
- 症状: プロファイラ CSV がプロジェクトルートの log/ ではなく target/debug/log/ に出る。
- 原因: 相対パスを cwd 基準で解決。
- 対策: ログの置き場はプロジェクトルート（package.json / Cargo.toml を上方向に探索）か exe 隣で明示的に解決する。
- 実例: 2026-03-08 Aether
- 自動検出: 不可
- 出典: Aether:1349-1350

### ファイル監視で .git / node_modules / target を拾って重い処理が走り続ける
- 症状: 差分監視で git がフル実行され続け負荷大。
- 原因: notify が .git / node_modules / target / dist の高頻度イベントを拾う。
- 対策: イベントのパスで除外フィルタしてから処理する。
- 実例: 2026-06 Claudes
- 自動検出: 不可
- 出典: Claudes:51-52

### バイナリヘッダ長を手書き定数にして 4 バイトずれる
- 症状: 再生で "failed to fill whole buffer"、フレームが 1 件も読めない（Writer は正常）。
- 原因: `FILE_HEADER_SIZE = 40`、実際は各フィールドの合計 36。
- 対策: ヘッダ長は各フィールドの size の和として式で書く（`4+2+2+8+8+4+4+4`）か Writer の実書き込み量から導く。Writer / Reader の round-trip テストを置く。
- 実例: 2026-02-20 natnet-recorder
- 自動検出: 不可
- 出典: natnet-recorder:277-294

### 「変更あり」の旗を操作ごとに立てると立て忘れて黙って失う
- 症状: トラックを作って閉じると保存確認が出ずに失われた。
- 原因: 未保存判定を操作ごとの旗で行うと、立て忘れた操作で漏れる。
- 対策: 最後に保存した内容を持ち `current != saved` で判定する。基準の初期値は同じ値の clone（時刻を 2 回取るとずれて変更扱い）。
- 実例: 2026-09-23 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2812-2825

## クレート・ツールチェーンの仕様

### reqwest の .query() は空白を + にする（+ を空白に戻さないサーバがある）
- 症状: ブラウザからは成功する API がツールからだけ失敗（Titan: "Sinkai+(User)" が見つからず 500）。
- 原因: `.query()` は x-www-form-urlencoded で空白を `+` にし、Titan は `+` を空白に戻さない。
- 対策: `%20` にしたい相手には `urlencoding::encode` でクエリを手組みする。サーバのログ（Titan は WebAPI/rolledexceptionlog.log）で実際に届いた値を確かめる。
- 実例: 2026-06-06 AvolitesRemote
- 自動検出: 候補 `\.query\(&`（warn。相手次第なので誤検知あり）
- 出典: AvolitesRemote:232-242, AvolitesRemote/memory/titan-api-endpoints.md:24

### suppaftp の File::from_str は LIST の見出し行を幻のファイルにする
- 症状: `total 8` や `226 Transfer complete` がサイズ 0 のファイルとして一覧に出る。
- 原因: POSIX → DOS → MLSD → MLST の順に試し、最後の MLST パーサが何でも受理する。
- 対策: FEAT で一覧形式を固定し、`ListParser::parse_posix().or_else(parse_dos)` / `parse_mlsd` を明示する。解析できない行はログへ。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 候補 `File::from_str|File::try_from`（suppaftp 使用ファイルで warn）
- 出典: Notion 3cfe4d4b-751b-813c-80bd-d957558521e7, ftpDeck/CLAUDE.md:67

### 音声 / MIDI クレートの仕様（rubato 4.0 の API 変更・midly の Result<(),&str>・FFT リサンプラの遅延）
- 症状: コンパイルが通らない / 時刻が前後にずれる。
- 対策: `rubato = "0.16"` に固定、`map_err(anyhow!)`、`output_delay()` 分を drain して理論長へ truncate。
- 実例: 2026-09-01 Sequence
- 自動検出: 候補 Cargo.toml の `rubato\s*=\s*"(\^)?[1-9]`（warn）
- 出典: Notion 3cee4d4b-751b-81b0-b6e2-feadace9a613

### 書き込み中の WAV を別スレッドから読む（hound の flush はヘッダを更新する）
- 症状: （設計上の疑問）書き込み中のファイルを追いかけて読めるか。
- 対策: hound は flush ごとに有効な WAV になる。追いかけ役は duration の差分だけ処理する。件数ヘッダ付きの自作形式は「データ追記 → ヘッダ更新」の順で書く。
- 実例: 2026-09-02 Sequence
- 自動検出: 不可
- 出典: Notion 3cfe4d4b-751b-8197-a42b-cc9f01d7d877

### tokio::process::Command の creation_flags は固有メソッド
- 症状: `use std::os::windows::process::CommandExt;` が unused 警告。
- 対策: tokio の Command なら import 不要。std へ戻すときだけ必要。
- 実例: 2026-07-29 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:859-868

### nokhwa は YUYV でしか取れず変換が重い（2 FPS）
- 症状: FaceTime HD Camera で 2 FPS。
- 対策: ffmpeg サブプロセス（AVFoundation, RGB24 直取り）でキャプチャ → 30 FPS。
- 実例: 2026-02-08 universal-sync-stream
- 自動検出: 不可
- 出典: universal-sync-stream/.claude/claudeLog.txt:135-139

### Rust 2024 edition / iced 0.13 への移行で出るエラー
- 症状: 2021 で通っていたパターンがコンパイルエラー・警告。
- 原因: マッチの既定束縛モード下で `ref` / `mut` の明示が禁止（`&deg` → `**deg`）。ライフタイム省略規則の変更（`Element<Message>` → `Element<'_, Message>`）。`iced::Text` は Clone 不可。`pick_list` は Display 実装が必要。
- 対策: `ref` を外す・ライフタイムを明示する。Text は再生成する。
- 実例: 2026-03-07 Aether（3 回踏んだ）
- 自動検出: 不可（コンパイラが出す）
- 出典: Aether:18-20, 102-104, 445, Aether/memory/MEMORY.md:46-53

### naga 28 の Capabilities に PUSH_CONSTANT が無い / shaderc は Vulkan SDK が要る
- 症状: コンパイルエラー / 他環境でビルド失敗。
- 原因: naga 28 で削除（push constants は既定でサポート）。shaderc は Vulkan SDK とネイティブビルドを要求する。
- 対策: `Capabilities::empty()`。shaderc の前提は README に書き、可能なら naga（WGSL）で済ませる。
- 実例: 2026-03-07 Aether
- 自動検出: 不可
- 出典: Aether:142, 171-172

### 描画（view）の中でデバイス列挙などのシステム API を呼ぶと FPS が落ちる
- 症状: UI が 5〜6 FPS。update は速く view が 170ms/回。
- 原因: iced の `view()` 内で `cpal::Host::output_devices()` を毎フレーム呼んでいた（1 回 170ms）。
- 対策: 列挙は起動時 / 明示リフレッシュ時に 1 回だけ行いキャッシュする。疑ったら update / view を分けて計測する。
- 実例: 2026-03-08 Aether
- 自動検出: 不可
- 出典: Aether:1331-1348

### iced: 複数のタイマー購読が同時発火して再描画が詰まる
- 症状: UI ラグ。
- 原因: 16ms の FpsTick と RealtimeTick を同時に購読し、各々が update → view → Canvas 再描画。
- 対策: 同目的のタイマーは 1 本にし、前回評価が終わっていなければスキップ（世代番号でスロットル）。静的な Canvas は `canvas::Cache` と世代番号で再描画を抑える。
- 実例: 2026-03-08 Aether
- 自動検出: 不可
- 出典: Aether:1296-1330

### iced::daemon はウィンドウを全部閉じても終了しない
- 症状: メインウィンドウを閉じてもプロセスが残る。
- 原因: daemon は自動終了しない（初期ウィンドウも作らない）。
- 対策: `window::open()` で明示作成し、メインの close_event で `iced::exit()`。
- 実例: 2026-03-22 Aether
- 自動検出: 不可
- 出典: Aether:1426

### iced: Canvas をまたぐ DnD で ButtonReleased が相手の Canvas に届かない
- 症状: 別 Canvas へのドロップが受け付けられない。
- 原因: マウスキャプチャ元の Canvas にしか Released が来ない。
- 対策: ドラッグ中の状態をアプリ側で持ち、ドロップ先は ButtonPressed / カーソル移動で受け付ける。
- 実例: 2026-03 Aether
- 自動検出: 不可
- 出典: Aether:443-444

### release ビルドが「Sized が見つからない」で落ちる = コミット枠切れ / 最終段は 1 コアで止まって見える
- skill tauri-release に記載（`CARGO_BUILD_JOBS=4`、os error 1455、ツールチェーン再インストールは無意味）。
- 実例: 2026-09-02 ftpDeck / 2026-09-03 ftpDeck / 2026-09-23 tauri-release
- 自動検出: 候補 `^(?!.*CARGO_BUILD_JOBS)(?=.*\bcargo\s+(tauri\s+)?build\b[^\n]*--release)`（warn）
- 出典: Notion 3cfe4d4b-751b-8107-85d1-e1d2ad29ffff, skills/tauri-release/SKILL.md, ftpDeck/CLAUDE.md:172

## Go（参考。担当分野が無いのでここに置く）

### tsnet.Server.Up() はログイン完了までブロックする
- 症状: UI から再ログインすると "tailnet not initialised"。
- 原因: Up() を Start() の同期パスで呼び、Start が返らず代入が実行されない。
- 対策: 状態 watch goroutine を先に起動し、Up() は別 goroutine へ。
- 実例: 2026-05-10 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:252-258

### tsnet.ListenPacket は ":port" を受け付けない
- 症状: `address must be a valid IP`。
- 対策: `State.TailscaleIPs[0]` を使い `100.x.x.x:port` で渡す。IP 未割当の race も考慮する。
- 実例: 2026-05-10 SRT-Blue
- 自動検出: 候補 `tsnet[^\n]*ListenPacket\(\s*"udp"\s*,\s*":`
- 出典: SRT-Blue/log/claudeLog.txt:260-266

### 同一 PC で同じアプリを 2 重起動すると tsnet の状態ディレクトリ / ホスト名が衝突する
- 症状: ポート衝突・接続不安定。
- 対策: 役割ごとに状態ディレクトリとホスト名を分け（`tsnet-sender` / `-send`）、同じ役割の二重起動は named mutex で防ぐ。
- 実例: 2026-07-19 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:627-633, SRT-Blue/memory/station-role-scoped-instances.md:12
