---
name: tauri-release
description: Tauri アプリ（ftpDeck / Sequence / SignalHub など）のリリースビルドを作り、Google Drive への配布まで確かめる。テスト・型検査・バンドル・ハッシュ照合を一度に通す。「リリースビルドして」「ビルドして配布して」「最新版を上げて」と言われたとき、機能を実装し終えて配布用のビルドが要るときに使う。
---

# Tauri アプリのリリースと配布

```bash
R=~/.claude/skills/tauri-release/scripts/release.py
python "$R" <プロジェクトのパス>            # dev を止める → ビルド → Drive の一致を確認
python "$R" <プロジェクトのパス> --jobs 2   # メモリが厳しいときは更に絞る
python "$R" <プロジェクトのパス> --skip-build  # 既にあるビルドの配布だけ確かめる
```

**ビルドは数分かかる。`run_in_background: true` で投げて、出力を追うこと。**
前面で待つと 5 分ルール（グローバル CLAUDE.md）に抵触する。

## 流れ

1. **そのプロジェクトの dev を止める**。`tauri dev` やアプリ本体が動いていると、
   ビルドスクリプトが出力ファイルを掴めず、`build-script-build (exit code 1)` で落ちる。
   原因が分かりにくいので、先に止める。
2. **`build-win.bat` を走らせる**。中身は「アプリを落とす → 同梱ツールの取得 →
   npm test → cargo test --release --lib → npm run typecheck → cargo tauri build」。
   個別に叩かず、この 1 本に通す（順番と失敗時の打ち切りが決めてある）。
3. **`CARGO_BUILD_JOBS` を絞る**（既定 4）。`release` プロファイルは `lto = true` /
   `codegen-units = 1` で 1 プロセスのメモリが大きく、論理プロセッサ数ぶん並列に走ると
   コミット枠を超える。症状は「`Sized` トレイトが見つからない」等の**標準ライブラリごと
   壊れたようなエラー**で、真因は出力の上の方に 1 行だけ出る
   （`failed to mmap file … ページング ファイルが小さすぎるため`）。
4. **出来た exe のハッシュを取り、Drive 側と突き合わせる**。SessionControl デーモンが
   `src-tauri/target/release/*.exe` を監視していて、`gdrive:Builds/<アプリ名>` へ自動で上げる。
   **手で上げ直さない**。

## 確かめ方

- デーモンのログ: `D:\_Personal\Project\SessionControl\log\<最新>.log` の
  「成果物を監視します: <名前>」と「アップロードしました (<名前>)」。
- Drive 側: `rclone hashsum sha256 gdrive:Builds/<名前>/`。手元の sha256 と一致すること。
  スクリプトがここまでやる。
- **Google Drive の MCP からは見えない**。`gdrive:` は別アカウントなので、確認は rclone で行う
  （一度「上がっていない」と誤報告した）。

## 止まって見えるが止まっていない（2026-09-23 に 2 回打ち切った）

`cargo tauri build` の最終段は **`codegen-units = 1` + `lto = true` の単一スレッド**で、
数分かかる。**コア数が多い PC ほど「止まって見える」**ので、次を守る。

- **「CPU 0%」で判断しない**。32 論理コアなら 1 コア全開 = 全体の約 3%。
  `Get-Process` の `.CPU`（累積秒）は当てにならず、実際に動いていても差分が 0.3 秒/15 秒に見えた。
  見るなら `Get-Counter '\Processor(_Total)\% Processor Time'` で、
  **1 コアぶん（100 ÷ 論理コア数 %）を下回っていないか**を見る。
- **生きている証拠は rustc の起動時刻**。`Get-CimInstance Win32_Process` で
  `CreationDate` を見て、別の rustc に入れ替わっていれば進んでいる。
- 経過時間は時計で確かめる。やり取りの回数と実時間は一致しない
  （2 分しか経っていないのに「30 分止まっている」と誤判断した）。
- **打ち切ると .bat は次の行へ進み、`[OK] Build complete` を出してしまう**。
  そのため成功したように見えるが、bundle の日時は古いまま。
  **成果物の日時を見るまで完了と判断しない**。

## 踏んだところ（先に読む）

- **`cmd //c` に相対パスの .bat を渡すと見つけられない**。`cd` してから渡しても効かない。
  フルパスで渡す。失敗しても `echo` の終了コードで `exit=0` に見えるので、
  **`[OK] Build complete` が出たかで判定する**。
- **.bat の中の `scripts\fetch-...` が壊れることがある**。書き換えツールを通すと `\f` が
  改ページ文字になり、`can't open file 'scripts\x0cetch-tools.py'` で落ちる。
  **区切りをスラッシュにする**（`"%~dp0scripts/fetch-tools.py"`）。
- **dev が動いていると落ちる**（上記 1）。`build-win.bat` はアプリは落とすが、
  `tauri dev` の node / cargo watcher までは落とさない。
- **tauri.conf.json の `bundle.resources` に入れ忘れると、同梱物が dev にも配布物にも入らない**。
  起動ログで「あり / なし」を出しておくと気づける。
- バンドルは msi と nsis の両方が出る。**インストーラの大きさは同梱物で跳ねる**
  （ftpDeck は rclone + ffmpeg を入れて 2.8MB → 66.5MB）。

## ビルドの前後にやること

- 前: 検証を通す（`npm test` / `npm run typecheck` / `cargo test --lib` / `cargo check --all-targets`）。
  スクリプトの中でも走るが、落ちるならビルド前に直す方が早い。
- 後: **画面で動作を確かめる**（`windows-gui-testing` skill）。ビルドが通ったことと
  動くことは別。
- 報告: スクリーンショットを添える（`deliver-artifact` skill）。配布物そのものは Drive に
  上がっているので、リンクを送るなら `gdrive:Builds/<名前>` ではなく共有フォルダへ置き直す。

## mac

`build-mac.command` が対になっている。ただし**同梱物（rclone / ffmpeg）は Windows 用しか
用意していないプロジェクトがある**。mac で配るなら、`scripts/fetch-tools.py` の対象と
`tauri.conf.json` の resources を先に見ること。
