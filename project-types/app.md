# アプリ開発（Tauri / Web / CLI）の作業方針

SessionStart hook（`hooks/project-context.mjs`）が、`package.json` か `src-tauri/` を持つプロジェクトでだけ差し込む。
罠は `rules/traps/{tauri,rust,web,python,dotnet,protocol}.md`（該当ファイルを開くと読まれる）と `traps-catalog/`（grep で引く）。

## 技術スタックの既定

指定が無ければこれを選ぶ。理由なく別のものを持ち込まない。**GUI が要らないなら Tauri にしない**（CLI やスクリプトで済むものを 1 アプリに仕立てない）。

| 種別 | 既定 |
|---|---|
| デスクトップアプリ | Tauri 2（Rust + React + TypeScript + Vite）。配布物は 1 つの exe で完結させる |
| Web サービス | Cloudflare Workers（Hono + D1 + Drizzle）+ React SPA |
| Python | uv（`uv run ...`） |
| アイコン | **lucide-react**（React 系は 1 個目のアイコンの時点で入れる。インライン SVG で済ませない。アイコンだけのボタンには `title` と `aria-label`） |

新しいアプリは既存の自作プロジェクトの構成に揃える（Tauri は Shifter / Sequence が手本）。
利用者に追加のドライバ・常駐ソフト・ランタイム（loopMIDI、Tailscale の別途導入、Node など）を要求しない。必要なものは exe に同梱する。
収録補助などの周辺ツールはメインの Unity に載せず、単体の軽量アプリにする（Unity のアセットを直接扱うものは Editor 拡張）。

## プロジェクト固有 CLAUDE.md の構成

新規でも既存の手直しでも、この 4 節に揃える。

1. **1 行の説明 + スタック** — 詳しい設計背景は README.md へ
2. **検証コマンド** — コピペで動く形で
3. **アーキテクチャ要約** — ディレクトリ責務の表 + **依存方向**（例:『依存は `ipc → core → {io, record}`。逆流させない』）
4. **触る前に必ず確認すること** — 罠を「症状 → 原因 → 対策」で。回帰テストがあればテスト名を添える。
   直った罠は消すか README へ移す。全プロジェクトに通じる罠は `~/.claude/traps-catalog/` へ上げる。

## 検証

- 複数ファイルを直してから、最後に 1 回まとめて検証する。
- 既定の検証セット。プロジェクト CLAUDE.md にあればそちらを優先し、**`package.json` / `Cargo.toml` に実在するものだけ**流す。

```bash
npm run typecheck                                          # TypeScript
npm run build                                              # 型検査 + バンドル
npm test                                                   # フロントの単体テスト（vitest）
cargo check --manifest-path src-tauri/Cargo.toml --all-targets
cargo test  --manifest-path src-tauri/Cargo.toml --lib
```

- GUI を持つものは、**起動してキャプチャで確かめる**までが修正（win-gui / playwright）。

## Tauri

- **Tauri コマンドは 1 箇所へ集める**。小さいうちは `src-tauri/src/commands.rs`、増えたら `commands/`（`ipc/` でも可）へ分ける。
  依存方向は `コマンド層 → 各モジュール`。逆流させない。
- 時間のかかりうるコマンドは `async fn` + `tauri::async_runtime::spawn_blocking`（同期コマンドは UI スレッドで走る。hook `tauri-sync-command` が知らせる）。
- **高頻度のイベントは UI へ生で流さない**。受信と配信のスレッドを分け、溜まった分をまとめて渡す。
  **配信レートは用途ごとに決め、根拠をコメントに残す**（数値の読み取りは実測 10Hz で足りた。波形・メータ・タイムコードは測ってから決める）。
- **ウィンドウの位置と大きさを覚える**。最小化中（サイズ 0）の値は保存しない。モニタ構成が変わって画面外を指すなら復元しない。
- 保存先の使い分け: 設定・プリセットは**アプリデータ**、人へ配る書き出しは **exe と同じ場所**。
- ログは画面に出した行を `log/yymmdd-hhmmss.log` にも残す。先頭行にビルドの素性（日時・コミット）を書く。
  置き場所: dev は `current_dir` から上へ `package.json` を探してプロジェクトルート/`log`、配布 exe は exe の隣の `log`（`src-tauri/` 配下には書かない）。
- `identifier` は **`jp.<組織>.<アプリ名>`**（`jp.aiacats.*` / `jp.vortex.*`）。揃えるのは新規だけ。既存の `com.*` は据え置く（変えると設定とウィンドウ位置が消える）。
- 複数 OS へ配るものは `build-win.bat` / `build-mac.command` に「テスト → 型検査 → バンドル」をまとめる。自動更新が要るなら SignalHub の `updater.rs` が手本。
- **リリースビルドと配布は `tauri-release` skill**。exe は `gdrive:Builds/<アプリ名>` へ上げるが、自分で `rclone copy` はせず、
  SessionControl デーモンの監視に登録して、ビルドするだけで上がる形にする（登録手順も skill）。

## UI

- **ブラウザで開くアプリには再読み込みボタンを必ず置く**（exe にしない HTML ベースのもの。Tauri は対象外）。
  ホーム画面に追加した standalone 表示にはブラウザの更新ボタンが無く、SSE / WebSocket が切れたときの逃げ道にもなる。
  ヘッダー右端に lucide-react の `RotateCw` を 16px、34×34 のアイコンボタンで。`title` と `aria-label` は「Reload」。中身は `window.location.reload()`。
- **縦に伸ばさない**。関連する値は 1 行へ集める（min/max/lerp を 1 行、Universe/開始 ch を 1 行）。
- 1 画面に収まらなくなったら、グループの折りたたみ + 件数バッジ + 絞り込みをセットで入れる。収まっているうちは入れない。
- 桁違いに数が違うものは、タブや画面を分ける（灯体 1499 と Volume 5）。
- 本文・名前・説明は折り返して見切れさせない。ヘッダ・ツールバー・ボタン・プルダウン・状態表示は 1 行に収まる幅を確保し、
  それでも溢れる状態文は省略記号 + ツールチップにする（2 行に折り返させない）。
- 起動直後は接続を待たずに画面を出し、接続中であることを表示する（真っ黒な画面で待たせない）。
  収録中・受信中の波形やメーターは、終わってからではなく随時描く。平滑化しすぎない。
- スマホ幅では、一覧に名前と主要な 1〜2 項目だけを出し、残りは行を開くトグルへ入れる。横スクロールさせない。ラベルと値は横に並べる。
- **状態は 1 箇所へ集める**（`App.tsx` か hooks）。子コンポーネントは描画に徹する。
  フロントの構成は既存に揃える: `src/App.tsx`（状態）/ `api.ts`（または `lib/`。バックエンド呼び出しの薄い層）/ `components/` / `hooks/` か `stores/` / `types.ts`。
- 取り違えると一番まずい情報（接続先・書き込み先）は、設定画面を開かなくても見える位置に置く。

## 通信

- 両側で対になる定義（アドレス表・型・引数の個数）は、片方だけ変えると黙って壊れる旨を**両方のファイルの冒頭コメント**に書き、対応表を README に持つ。
- **UDP は取りこぼす前提**で作る。欠けを検知して拾い直す経路と、送信側の分割送信を用意する。相手が応答を返せなくなるほどの要求を一度に投げない（窓で区切る）。
- 外部プロトコルは原典（SDK のヘッダ・公式ソース）で照合する。旧コードのコメントを盲信しない。
