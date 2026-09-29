# git の罠（カタログ）

.gitignore・改行・LFS・submodule・worktree・UPM lock 漏れ、git CLI をラップするツールで踏んだ罠の全件。厳選版は `~/.claude/rules/traps/git.md`。

### .gitignore の先頭 `/` 無しパターンは全階層に当たる（`tools/` がソースを消す）
- 症状: `server/src/tools/` の 7 ファイル（1597 行）が一度もコミットされておらず、clone するとビルド不能。ローカルでは全テスト・配布物作成が通り、`git status` にも出ないので気付けない
- 原因: `/` を含まないディレクトリパターンは任意の階層に一致する
- 対策: ルート直下だけなら `/tools/` と書く。追加後に `git check-ignore -v <path>` と `git ls-files <dir> | wc -l` で確かめる
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `gitignore-unanchored-source-dir`
- 出典: AEMCP/log/claudeLog.txt:378-384, Notion 3dde4d4b-751b-8188-a387-c10c270c55cc

### .gitignore の `*~` が UPM パッケージの Server~ / Samples~ を除外する
- 症状: UPM パッケージの Server~ / Samples~ がコミットされない
- 原因: エディタのバックアップ用 `*~` パターンが、Unity の隠しフォルダ（末尾 `~`）にも当たる
- 対策: 除外から外すか `!*~/` の例外を足す
- 実例: 2026-03-12 unity-mcp
- 自動検出: 候補 `gitignore-tilde`
- 出典: unity-mcp/.claude/claudeLog.txt:37-38

### 親ディレクトリを ignore すると、子の否定（`!`）が効かない
- 症状: `log/` を ignore したまま `!log/claudeLog.txt` を足しても追跡されない
- 原因: git は ignore された親ディレクトリの中を見ない
- 対策: 他の階層の ignore を変えずに `!/log/` `/log/*` `!/log/claudeLog.txt` の順で書く
- 実例: 日付不明（CLAUDE.md の claudeLog 追跡手順）
- 自動検出: 候補（multiline）`^/?log/\s*$[\s\S]*^!.*log/claudeLog\.txt` かつ `/log/\*` が無い（2 段判定が要るため hook 案には出さない）
- 出典: CLAUDE.md「claudeLog.txt を git で追跡するか」

### .gitattributes が無いと CRLF が混入する（.sh が動かない・常に M 表示）
- 症状: Mac のビルドスクリプトの途中ステップが実行されない。正規表現でソースを読むテストがコメントを落とせず引数を飲み込む。Cargo.toml が内容差分ゼロなのに常に modified
- 原因: autocrlf による LF→CRLF 変換
- 対策: `.gitattributes` で `*.sh` `*.command` や正規表現で解析されるソースを `eol=lf` に固定する。パーサ側も CR を行末として扱う
- 実例: 2026-05-10 SRT-Blue / 2026-07-29 SignalHub / 2026-09 DvcMCP
- 自動検出: 不可（.gitattributes の有無はコマンドや編集内容からは確実に判定できない）
- 出典: SRT-Blue/log/claudeLog.txt:217-225, SH/log/claudeLog.txt:889-891, DvcMCP/CLAUDE.md:80-81

### `git lfs migrate import` の直後は作業コピーがポインタのまま
- 症状: LFS 化した直後に Unity が壊れる（VRM / テクスチャが 133B のポインタファイル）
- 原因: migrate は履歴を書き換えるだけで作業コピーを smudge しない
- 対策: migrate 直後に必ず `git lfs checkout`。clone / pull 後にバイナリが空なら `git lfs pull` / `git lfs checkout`。`.meta` は LFS 対象外にする（GUID をテキストで保つ）
- 実例: 2026-06-20 ReLink
- 自動検出: 候補 `lfs-migrate-without-checkout`
- 出典: ReLink/.claude/claudeLog.txt:154-156, ReLink memory git-lfs-setup.md:16

### LFS 管理のシーン・.playable は `git diff` で中身が見えない
- 症状: 保存前の差分確認ができない
- 原因: HEAD 側が LFS ポインタ
- 対策: skill vortex-timeline-setup に記載（`git show HEAD:<path> | git lfs smudge > orig.unity` で取り出して diff）
- 実例: 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026/log/claudeLog.txt:645-648, skills/vortex-timeline-setup/SKILL.md:216, Notion 3e4e4d4b-751b-81f7-bdec-e666fb986055

### ローカル専用の embedded UPM パッケージ（unity-mcp）が packages-lock.json から漏れる
- 症状: gitignore 済みなのに lock に com.aiacats.unity-mcp / newtonsoft-json が載り差分が出続ける。削除しても resolve で復活する
- 原因: Unity は Packages/ 直下の embedded パッケージを manifest 記載の有無に関係なく lock に書く
- 対策: skill setup-unity-mcp に記載（lock からエントリを除いてコミットし、clean フィルタ `~/.claude/tools/strip-unity-mcp-lock.py` で混入を防ぐ）
- 実例: 2026-08-04 2609SuiseiTour26 / 2026-08-25 2609SuiseiTour26
- 自動検出: 候補 `git\s+(add|commit).*packages-lock\.json`（フィルタ設定済みなら無害のため hook 案には出さない）
- 出典: 2609SuiseiTour26/log/claudeLog.txt:198-222, 2194-2207, Notion 3c7e4d4b-751b-8112-bd8f-fe61e64a5e2f

### 親がサブモジュールの新しい API に依存するなら、サブモジュールを先にコミット・push する（vortex）
- 症状: 他の環境でコンパイルが壊れる。解決できない参照が残る
- 原因: 親だけコミットした、またはポインタだけ先に進めた
- 対策: サブモジュールをコミットして push した後に、親のポインタを更新する（サブモジュールへの書き込み可否は CLAUDE.md の方針に従う）
- 実例: 2026-09-06 vortex_urp / 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: vortex_urp log VL:925-927, Ext_Palletproject log PL:80-82

### Unity プロジェクトで `git add -A` し直すと、コミット後に Unity が保存したシーンを取り込む
- 症状: squash の途中で意図しないシーンの版が入る
- 原因: Unity がコミットの後にシーンを保存し直していた。作業ツリーをまとめて add した
- 対策: パスを指定して add する。まとめた後は旧先頭との `git diff` が空であることを確かめる
- 実例: 2026-09-26 Ext_TokinoSora_2026-pia
- 自動検出: 不可（Unity プロジェクト内かどうかをコマンドから判定できない）
- 出典: Ext_TokinoSora_2026-pia log TS:76

### git commit のオプションはパス指定 `--` より前に置く
- 症状: `pathspec '-m' did not match any file(s)`
- 原因: `--` 以降は全てパスとして扱われる
- 対策: `git commit -F <msg> -- <paths>` の順に書く
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 候補 `git-commit-option-after-dashdash`
- 出典: 2609SuiseiTour26/log/claudeLog.txt:224-226

### worktree のブランチに機能が取り残され、配布ビルドに入っていない
- 症状: 実装済みのはずの機能（トラック名のダブルクリック編集）が利用者のビルドに無い
- 原因: 並行 worktree のブランチ（`worktree-clip-export-name`）が master へマージされないまま放置された
- 対策: 検証・コミットが済んだら作業ブランチを master へ入れる（許可済みのプロジェクト）。セッション冒頭で `git branch --no-merged master` を見て取り残しを確かめる
- 実例: 2026-09-13 Sequence
- 自動検出: 不可（セッション開始時の点検としてなら可能）
- 出典: Sequence memory merge-freely.md:13

### submodule はコミットが変わっても中身を上書きしないのに、diff には挙がる
- 症状: 捨てる対象に submodule が出るが stash は何もしない
- 原因: gitlink の扱い
- 対策: 衝突判定の diff は `--ignore-submodules=all`
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:198

### git status が index を書き戻し、.git 監視が反応し続ける／index.lock を取り合う
- 症状: 閲覧するたびに `.git` の監視が反応して取り直しが続く。利用者の git と index.lock を取り合う
- 原因: git status が index の stat 情報を書き戻す
- 対策: 読み取り系は `GIT_OPTIONAL_LOCKS=0` を付けて呼ぶ
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:164

### 画面の無いプロセスから fetch/pull/push すると資格情報待ちで返らない
- 症状: fetch / pull / push が返らない
- 原因: HTTPS/SSH の資格情報入力待ち
- 対策: `GIT_TERMINAL_PROMPT=0` / `GCM_INTERACTIVE=never`、ssh は `-o BatchMode=yes`（利用者が core.sshCommand を決めていない場合のみ）。フック等で返らない場合に備えて取り消し手段を用意する
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:166

### 引数なし git push は利用者設定で行き先が変わる
- 症状: 確認に出した行き先と実際の push 先が食い違う（push.default=matching なら全同名ブランチ、pushRemote で別リモート）
- 原因: 利用者の push 設定
- 対策: `git push <remote> <src>:<dst>` のように行き先を明示し、確認時の計画と実行時の計画を突き合わせる
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:178

### git diff は rename をまとめて新しい名前しか出さない
- 症状: 上流で名前を変えたファイルの手元編集を衝突判定で見落とす
- 原因: rename 検出の既定動作
- 対策: 衝突判定の diff は `--no-renames`
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:189

### stash push -- <path> は index に無いパスに一致せず、stash だけ残して失敗する
- 症状: 片付けに失敗するたび stash が 1 件ずつ増える（`did not match any files`）。staged の削除・rename 元が該当
- 原因: pathspec は index 上のパスと照合される
- 対策: 先に `git reset -- <path>` で index へ戻してから stash push
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:206

### 追跡を設定できない refs/remotes に switch --track すると、ツリーを書き込んだまま元ブランチに残る
- 症状: Checkout 失敗後に退避した変更を戻せない（`Index was not unstashed`）
- 原因: リモート設定が消えた／`--single-branch` で refspec が 1 本だけのとき、追跡の設定失敗より先に index と作業ツリーを書き換える
- 対策: どれかのリモートの fetch refspec 右辺に一致するか先に確かめて断る
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:200

### merge の短い名前は同名タグが優先。完全名だと既定メッセージが `Merge branch 'refs/heads/x'`
- 症状: 意図しないタグをマージする／見慣れないマージメッセージになる
- 原因: ref 解決の優先順位
- 対策: 完全な参照名で渡し、`-m` でメッセージを明示する。`--ff-only` / `--no-ff` も明示する（merge.ff 設定で食い違わせない）
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:215

### -X ours/theirs は内容の衝突にしか効かない（modify/delete は残る）
- 症状: 優先側を選んでもマージが衝突で止まる
- 原因: -X は内容の衝突にしか適用されない
- 対策: `git merge-tree --write-tree` で事前に試し、残る衝突があれば始めない。止まったら `merge --abort`
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:211

### パス無しの git reset はマージ途中の MERGE_HEAD まで消す
- 症状: unstage all でマージ途中の状態が消える
- 原因: パス無し reset は HEAD を含めて状態を戻す
- 対策: まとめての unstage は `git reset -- .`
- 実例: 2026-09-24 SessionControl
- 自動検出: 候補 `['"]reset['"]\s*\]`（git をラップするコード内。精度が低いため hook 案には出さない）
- 出典: SessionControl/CLAUDE.md:223

### 捨てる前に早送りできるか確かめないと、変更だけ失って pull されない
- 症状: 分岐時に discard → `merge --ff-only` 失敗で手元の変更だけ消える
- 原因: 判定と破壊操作の順序
- 対策: fetch 後に早送り可否を判定する。捨てる操作もいったん stash に退避し、成功で drop・失敗で pop
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:184, :190

### check-ref-format は不正な名前で 1 ではなく 128 で終わる
- 症状: 不正判定が漏れる
- 原因: git のエラー終了コード
- 対策: 終了コードは 0 か否かで判定する。先頭 `-` は先に断る
- 実例: 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:218

### --progress を付けても 2 秒経つまで進捗が出ない
- 症状: 3000 ファイルの switch で進捗が一度も出ない
- 原因: git の既定の進捗遅延
- 対策: `GIT_PROGRESS_DELAY=0`。stderr の進捗行（`\r` 区切り）はエラー文から取り除く
- 実例: 2026-09-27 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:227

### upstream が消えたブランチは porcelain v2 で branch.ab が出ない
- 症状: 「Nothing to push」と誤表示
- 原因: git の出力仕様（実測）
- 対策: `branch.upstream` あり・`branch.ab` 無しで「upstream が消えている」と判定する
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:183
