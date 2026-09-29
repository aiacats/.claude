# cloud-sync の罠（カタログ）

rclone・Google Drive（rclone の `gdrive:` / `gdrive-ro:` と Drive MCP）・Dropbox・共有リンクの罠の全件。厳選版（rules/traps）は作らない。受け渡しの手順は skill deliver-artifact。

### `rclone link` は「リンクを知っている全員」の権限を付ける
- skill screen-recording / deliver-artifact に記載（`share.py put` を使う。付けてしまったら `share.py private <名前>` → `share.py sharing <名前>` で確認）。
- 症状: 非公開のつもりが全公開になる（既定は所有者 + komao9160 + mao.komatsu の閲覧のみ）。
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia（screen-recording skill を修正）
- 自動検出: 候補（patterns-io 案 P1。`dropbox:` への `rclone link` は vortex-timeline-export の正規手順なので対象外）
- 出典: skills/screen-recording/SKILL.md, CLAUDE.md「アカウントと権限」, TS:62

### rclone の `gdrive:` と Drive MCP は別アカウント（上げたのに見えない／検索に出ない）
- 症状: MCP で「Requested entity was not found」、検索に出ず「Drive に上がっていない」と誤報告した。
- 原因: `gdrive:` の所有者は mamiyacats99@gmail.com、Drive MCP は komao9160@gmail.com。所有者が mamiyacats99 のファイルは komao9160 へ共有されていなければ MCP から見えない（ファイルが消えたわけではない）。
- 対策: 所有者側の確認・操作は rclone で行う。確認は `rclone lsl gdrive:Builds/<App>` と SessionControl のログ「アップロードしました」、同一性は `rclone hashsum sha256` とローカルの sha256 を比較。
- 実例: 2026-09-15 ftpDeck（2 件記録）/ 2026-09-23 tauri-release
- 自動検出: 不可
- 出典: CLAUDE.md「アカウントと権限」, skills/tauri-release/SKILL.md, ftpDeck/log/claudeLog.txt:515, D---Personal-Project-ftpDeck/memory/drive-builds-check-via-rclone.md:10-14

### rclone `gdrive:`（drive.file スコープ）では人から共有されたファイルが見えない
- 症状: 共有リンクのファイルが 404。
- 原因: drive.file は rclone 自身が作ったファイルしか見えない。
- 対策: 共有ファイルは最初から `gdrive-ro:`（drive.readonly）で `rclone backend copyid gdrive-ro: <fileId> <dir>/`。取る前に Drive MCP の get_file_metadata でサイズを見る（skill vortex-timeline-setup）。それでも取れない数 MB 以上のものは受け取り方をユーザーに聞く（Chrome で落とすなら理由を添えて許可を取る）。
- 旧説: skill vortex-timeline-setup の「404 が出たら別の remote を試す」（順に試して時間を浪費した。gdrive-ro: を最初から使う方が新しい知見）。
- 実例: 2026-09-16 MotionForge / 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 候補（patterns-io 案 P13: `rclone backend copyid gdrive:`）
- 出典: D---Personal-Project-MotionForge/memory/gdrive-download-route.md:8-10, 15, M:D---ProjectBLUE-Project-Ext-TokinoSora-2026-pia/drive-download.md, TS:171, skills/vortex-timeline-setup/SKILL.md:58-63

### Drive MCP の download_file_content は大きなファイルに使えない
- 症状: 数百 MB のファイルが落とせない。
- 原因: base64 で返る。
- 対策: rclone（`gdrive-ro:` copyid）で落とす（304MB の FBX で確認済み）。
- 実例: 2026-09-16 MotionForge / 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: D---Personal-Project-MotionForge/memory/gdrive-download-route.md:11, TS:171

### Drive MCP へ xlsx を base64 で上げると 10,000〜12,000 文字超で欠損する
- 症状: "Invalid conversion requested" / "not a valid base64 string" が 3 回連続。
- 原因: 1 回の tool 呼び出しで base64 全文を転記する際に欠損する。
- 対策: 10,000 文字以内に収める（theme1.xml 除去・共有文字列モード）か CSV を直接入れる。大容量は rclone。
- 実例: 2026-08-25 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26/log/claudeLog.txt:2068-2073, 2118-2125

### 権限を外す操作は Drive MCP に無い
- skill deliver-artifact に記載（`share.py private`）。MCP の `share_file` は付与のみ。直接外すなら rclone の access_token で `DELETE /drive/v3/files/<id>/permissions/<permId>`（`anyone` の permId は `anyoneWithLink`）。
- 出典: CLAUDE.md「アカウントと権限」

### rclone の token・obscure したパスワードを画面やログへ出す
- 症状: 資格情報の漏えい経路になる。エラー文に `pass=<難読化>` が混じる。
- 原因: rclone の obscure は元に戻せる。rclone.conf の refresh token は平文。`rclone config dump` は token を出力する。
- 対策: rclone.conf は秘密ファイル扱いにし、ログへ出す前に redact する。アプリ専用の rclone.conf を使い、利用者の設定と混ぜない。token を借りるときも画面・ログへ出さない。資格情報はコマンドライン引数ではなく環境変数で渡す。
- 実例: 2026-09-05 SessionControl / 2026-09-13 ftpDeck
- 自動検出: 候補（patterns-io 案 P3: `rclone config (dump|show)`）
- 出典: ftpDeck/CLAUDE.md:122, ftpDeck/log/claudeLog.txt:873, SessionControl/log/claudeLog.txt:243, CLAUDE.md「アカウントと権限」

### rclone config は対話式で、非 TTY では EOF。reconnect は 3 問答えないと token が保存されない
- 症状: 認証が成功しても token が保存されない（2 回踏んだ）。
- 原因: Claude Code のシェルは TTY でない。
- 対策: 作成は `rclone config create gdrive drive scope=drive.file`（非対話）。reconnect は `printf "y\ny\nn\n" | rclone config reconnect gdrive:`。
- 実例: 2026-09-05 SessionControl（2 回）
- 自動検出: 候補（patterns-io 案 P2）
- 出典: SessionControl/log/claudeLog.txt:215, 273

### drive.file で client_id を変えると、旧クライアントで作ったファイルが見えない
- 症状: directory not found。以前アップロードしたファイルが rclone から見えず、消せない。
- 原因: drive.file の「そのアプリが作成したファイル」はアプリ = client_id 単位。
- 対策: client_id は変えない。変えるなら前に移行計画を立てる。残ったものは Drive の Web UI で消す。
- 実例: 2026-09-05 SessionControl（2 件記録）
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:285, D---Personal-Project-SessionControl/memory/sessioncontrol-phase0.md:29-30

### rclone 共用 client_id は 2026 年中に停止する（`gdrive-ro:` も対象）
- 症状: （予告）ある日からアップロードや `gdrive-ro:` が黙って失敗し始める。
- 原因: rclone 側の告知。
- 対策: 自前の OAuth クライアント ID を作って `rclone config update` で差し替える（https://rclone.org/drive/#making-your-own-client-id）。公開ステータスは「本番環境」にする（次項）。
- 実例: 2026-09-05 SessionControl / 2026-09-16 MotionForge
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:237, 270, D---Personal-Project-MotionForge/memory/gdrive-download-route.md:12-13

### Google OAuth クライアントを「テスト」にすると refresh token が 7 日で失効する
- 症状: アップロードが毎週壊れる。
- 原因: 公開ステータス「テスト」の OAuth クライアントは refresh token が 7 日で失効する。
- 対策: 本番環境で公開したままにする。
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: D---Personal-Project-SessionControl/memory/sessioncontrol-phase0.md:28

### rclone RC の待ち時間を一律 30 秒にすると、ブラウザ承認が間に合わない
- 症状: 接続先の追加が 30 秒で切れる。
- 原因: 用途を区別しないタイムアウト。
- 対策: 人の操作を待つ呼び出しだけ長いタイムアウトにする。
- 実例: 2026-09-13 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:858

### rclone RC のジョブ状態の取得に失敗したまま諦めるとジョブが残る
- 症状: rclone 側にジョブが残留する。
- 原因: 後始末の漏れ。
- 対策: job/status が失敗したら job/stop してから諦める。
- 実例: 2026-09-13 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:871

### rclone copyto が転送中のファイル書き換えと競って失敗し、再試行が無いと上がらずに終わる
- 症状: ビルドしても成果物が Drive に上がらない（画面上は待機中に見える）。
- 原因: 書き込み途中のファイルを転送した。再試行が無かった。
- 対策: 転送失敗時は size と mtime が一定時間変わらないことを確かめてから再試行する（3 回まで）。上限を超えるなら書き換えが続いているので監視イベント側に任せる。テストは `rclone config create <name> local` のローカルリモートで Google 認証なしに通せる。監視側（chokidar）の罠は web/node 分野。
- 実例: SessionControl
- 自動検出: 不可
- 出典: Notion 3e4e4d4b-751b-8100-9eb9-ecb04bc2e723

### `share.py put` の名前に拡張子を付けないと Drive 上で拡張子の無いファイルになる
- skill deliver-artifact に記載（スクリプト側で元の拡張子と日付を補うよう修正済み）。
- 実例: 2026-09-24
- 出典: skills/deliver-artifact/SKILL.md「名前と掃除」, CLAUDE.md「踏んだ罠はその場で反映する」
