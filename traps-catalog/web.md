# web の罠（カタログ）

React / Vite / Node / Cloudflare Workers・D1 / CSS / PWA / ブラウザで踏んだ罠の全件。トラブル時に grep で引く。厳選版は `~/.claude/rules/traps/web.md`。

## Cloudflare Workers / D1 / Drizzle / wrangler

### Drizzle の .default("CURRENT_TIMESTAMP") は文字列リテラルが入る
- 症状: created_at 列に "CURRENT_TIMESTAMP" という文字列が保存される。
- 原因: 文字列を渡すと値としてクォートされる。
- 対策: ``.default(sql`(CURRENT_TIMESTAMP)`)``（定数 `NOW` にまとめる）。
- 実例: 2026-06 Shifter / 2026-06-27 RigFlow
- 自動検出: 候補（patterns-app.md の `drizzle-current-timestamp-literal`）
- 出典: Shf/CLAUDE.md, Shifter/memory/shifter-conventions.md:16, RigFlow/CLAUDE.md:73

### D1 は 1 クエリのバインド変数が 100 個まで（本番の量でだけ落ちる）
- 症状: 本番でスケジュール API が失敗して列が崩壊。アサイン 9 行超 / 明細 8 件（8×14=112）の一括 INSERT が FailedQuery。3 件（42）では通る。ローカルの少量データでは出ない。
- 原因: `inArray(全案件ID)` や 列数 × 行数の一括 INSERT がバインド 100 個を超える。
- 対策: IN は 90 件、INSERT は `floor(100 / カラム数)` 行でチャンク分割する（chunk ヘルパ）。大量データで e2e を回す。
- 実例: 2026-06-27 Shifter / 2026-06-27 RigFlow
- 自動検出: 不可（`inArray(` / `.values(` で warn は出せるが誤検知が多い）
- 出典: Shf/log/claudeLog.txt:1615-1640, RigFlow/CLAUDE.md:67, RigFlow/memory/gotchas-build-and-d1.md:14

### wrangler secret put は stdin が空でも Success で空のシークレットを登録する
- 症状: OAuth が「client_secret is missing」で失敗。
- 原因: 非対話実行で値が入らないのに成功を返す。
- 対策: 値をパイプで渡し（画面に出さない）、直後に wrangler tail 等で確かめる。
- 実例: 2026-07-05 RigFlow
- 自動検出: 候補（patterns-app.md の `wrangler-secret-put-no-stdin`）
- 出典: RigFlow/log/claudeLog.txt:298

### wrangler r2 object get / d1 execute は既定でローカル（miniflare）を見る
- 症状: 0 バイトのファイルが出来て「取得できた」と誤認。
- 原因: `--remote` を付けないとローカル。`wrangler r2 object list` は存在しない。
- 対策: 必ず `--remote` / `--local` を明示する。キーを日付など既知の形にして直接 get できるようにする。
- 実例: 2026-08-15 Shifter
- 自動検出: 候補（patterns-app.md の `wrangler-remote-local-unspecified`）
- 出典: Shf/log/claudeLog.txt:2114-2120

### wrangler.jsonc の database_id を変えるとローカル D1 が空の別物になる
- 症状: ローカルで "no such table"（テーブル消失に見える）/ tags クエリ失敗。
- 原因: `.wrangler/state` のローカル D1 は database_id ごとに別ファイル。
- 対策: 差し替え後に `db:migrate:local` + seed を流し、dev サーバーを再起動する。
- 実例: 2026-07-05 RigFlow / 2026-07 Traddist
- 自動検出: 候補 wrangler.jsonc の `database_id` 変更（warn。変更検知は diff が要る）
- 出典: RigFlow/CLAUDE.md:74, Traddist/CLAUDE.md:34, Traddist/log/claudeLog.txt:15

### ローカル dev の D1 が no such table（マイグレーション未適用）
- skill cloudflare に記載（references/d1/gotchas.md）。スキーマ変更後は `db:generate` → `db:migrate:local`、本番は `db:migrate:remote`（drizzle push は使わない）。
- 実例: 2026-06 Shifter
- 出典: Shifter/memory/project-overview.md:26

### @cloudflare/vite-plugin を ^ 指定すると Node 22.13 でビルドが落ちる
- 症状: `npm run build` が `SyntaxError: ... registerHooks`。
- 原因: 1.42+（1.43 で確認）が Node 22.15+ の `module.registerHooks` を要求。環境は Node v22.13.0。
- 対策: `1.40.2` に固定する（Shifter / RigFlow / Traddist で動作）か Node を 22.15+ に上げる。
- 実例: 2026-06-27 RigFlow / 2026-07-03 Traddist
- 自動検出: 候補（patterns-app.md の `cloudflare-vite-plugin-caret`）
- 出典: RigFlow/CLAUDE.md:71, Traddist/log/claudeLog.txt:14, RigFlow/memory/gotchas-build-and-d1.md:12

### @cloudflare/vite-plugin は worker 側・共有定数の変更を HMR しない
- 症状: worker / shared の変更が dev に反映されず別の原因を疑う。
- 対策: worker 側を変えたら dev サーバーを再起動する。
- 実例: 2026-06-15 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:357, Shifter/memory/shifter-conventions.md:26

### .dev.vars の値をクォートで囲むと、自前で読むとクォートごと入る
- 症状: 自作 JWT の署名が合わず dev API が全部 401。
- 原因: `.dev.vars` の SESSION_SECRET がクォート囲みで、スクリプト側で読むとクォートが残る。
- 対策: 手で鍵を使うときはクォートを外す（または値をクォートしない）。
- 実例: 2026-06-13 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:74, Shifter/memory/shifter-conventions.md:23

### 本番 OAuth の invalid_client は client secret の値違い
- 症状: 本番だけ Google ログインがコールバックで失敗。redirect_uri_mismatch と紛らわしい。
- 原因: GOOGLE_CLIENT_SECRET の値が client_id と不一致。authorize は通り、callback の token exchange で 401 "client secret is invalid"。
- 対策: 推測せず `wrangler tail` で実エラーを取る。callback に token exchange の失敗理由を出す診断ログを常設。正しい値を `wrangler secret put` で入れ直す。
- 実例: 2026-06-13 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:179-203, Shifter/memory/project-overview.md:22

### @hono/oauth-providers ではドメイン限定（hd / id_token）ができない
- 症状: Google Workspace ドメイン限定ログインを満たせない。
- 対策: 手動 code flow + jose で id_token を検証し、`hd` / email ドメインをサーバで突合する。
- 実例: 2026-06 Shifter
- 自動検出: 不可
- 出典: Shf/CLAUDE.md

### デプロイ直後はシークレットの反映に数秒かかる
- 症状: 本番 E2E がデプロイ直後だけ失敗。
- 対策: デプロイ後に少し待つか再試行してから E2E。
- 実例: 2026-07 Traddist
- 自動検出: 不可
- 出典: Traddist/log/claudeLog.txt:16

### D1 Time Travel の復元ポイントを本番マイグレーション前に控える
- 症状: （予防）本番スキーマ変更の事故時に戻せない。Time Travel は DB 削除・アカウント喪失には無力。
- 対策: `wrangler d1 time-travel info` で bookmark を控えてから `migrate --remote`。別途 R2 / ローカルへのバックアップも持つ。
- 実例: 2026-08-05 / 2026-08-15 Shifter
- 自動検出: 不可（直前の操作を見る状態が要る）
- 出典: Shf/CLAUDE.md, Shf/log/claudeLog.txt:2147-2152

### D1 のレプリカ遅延 + 自動再取得が楽観更新を巻き戻す
- 症状: 個体の居場所を変えても元に戻る。
- 原因: 楽観更新直後にライブ同期 / 復帰で再取得が走り、レプリカの古いデータで上書き → 次の書き込みが古い状態を保存。
- 対策: 書き込み中・直後は自動再取得を見送る書き込みガード（根本には Sessions API 等で read-your-writes）。
- 実例: 2026-07-06 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:1111

### 子リソースの PATCH / DELETE は所有権を WHERE で照合する（D1 はロールバックしない）
- 症状: （予防）ID 推測で他案件の明細を書き換え・削除できる（IDOR）。
- 原因: 「更新してから所有を判定」では D1 は取り消されない。
- 対策: `WHERE id=? AND parent_id=?` で照合して更新する。
- 実例: 2026-06-27 RigFlow
- 自動検出: 不可
- 出典: RigFlow/memory/gotchas-build-and-d1.md:16

### drizzle-kit の列 rename は非対話で失敗する
- 症状: `db:generate` が rename の対話プロンプトで止まる / 失敗。
- 対策: add-only のマイグレーション → drop-only のマイグレーションの 2 段に分ける。
- 実例: 2026-06-15 Shifter
- 自動検出: 不可
- 出典: Shifter/memory/shifter-conventions.md:26

### 定数配列を [...new Set(...)] で算出すると本番ビルドで空配列になった
- 症状: MEMBER_ROLES が本番ビルドで空配列。
- 原因: 動的算出式に `@__PURE__` が付き tree-shaking 対象になった。
- 対策: 共有定数は明示リテラルで書き、テストで一致を確かめる。
- 実例: 2026-06-15 Shifter
- 自動検出: 不可
- 出典: Shifter/memory/shifter-conventions.md:26。旧説: Shf/log/claudeLog.txt:357-358 は「疑い・原因未確定」としていた（メモリでは確定扱い）

### wrangler 生成の型と @cloudflare/workers-types を二重参照しない / R2Bucket は named import できない
- 症状: 型の重複・衝突。Node 用 tsconfig（scripts / test）で R2Bucket 未解決、triple-slash を書くと workers-types が漏れて URL 型が衝突。
- 原因: `worker-configuration.d.ts`（`wrangler types` 生成）がランタイム型を内包する。@cloudflare/workers-types はグローバル ambient 宣言。
- 対策: workers-types を別途参照しない（tsconfig.worker の types は ["node"]）。vars を変えたら `npm run cf-typegen`。Worker 用とスクリプト用で tsconfig を分け、src 専用の env.d.ts で module augmentation。テストは R2 非依存の純粋ヘルパーを別ファイルにして import。
- 実例: 2026-06 Shifter / 2026-06 FlowBot
- 自動検出: 不可
- 出典: Shifter/memory/shifter-conventions.md:19, 33, FlowBot:100-110, FlowBot/memory/flowbot-architecture.md:22

### Worker が Range の無い GET に 206 を返す
- 症状: updater のダウンロードで素の GET に 206。
- 原因: `env.BUCKET.get(key, { range: request.headers })` を無条件に渡していた。
- 対策: Range / 条件付きヘッダが実際に来たときだけオプションを渡す。
- 実例: 2026-08-21 SignalHub
- 自動検出: 候補 `\.get\([^)]*range:\s*request\.headers`（warn）
- 出典: SH/log/claudeLog.txt:1094-1096

### Workers の waitUntil 内の失敗は握り潰される
- 症状: 最終 follow-up（editOriginalResponse）が失敗しても何も出ない。
- 対策: waitUntil の中で try/catch + console.error を明示する。
- 実例: 2026-06 FlowBot
- 自動検出: 不可
- 出典: FlowBot:28

### Discord Interactions は 3 秒以内に応答が必要 / Workers は Gateway を常駐できない
- 症状: （設計）重い処理を同期で返すとタイムアウト。
- 対策: Deferred 応答（type 5）+ `ctx.waitUntil` + `@original` を PATCH。Bot は HTTP webhook 型にする。
- 実例: 2026 FlowBot
- 自動検出: 不可
- 出典: FlowBot/memory/flowbot-architecture.md:13, 18

### 一部リソースの 403 で一括処理全体が落ちる
- 症状: Bot 権限の無いチャンネルが 1 つあるとエクスポート全体が失敗。
- 原因: アーカイブスレッド取得が未ガードで 403 Missing Access を throw。
- 対策: リソース単位で try/catch し、スキップしたことを結果の notes に明記する（黙って捨てない）。
- 実例: 2026-06 FlowBot
- 自動検出: 不可
- 出典: FlowBot:131-137

### 検証スクリプトが空ファイルを ok と判定していた
- 症状: 0 バイトのバックアップに対して integrity ok / FK ok。
- 原因: テーブル 0 件・空ファイルでも各チェックは素通しする。
- 対策: 最小サイズ・テーブル数などの下限ガードを検証器に入れる（検証器自体を空入力で落ちるか試す）。
- 実例: 2026-08-15 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2121-2123

## CSS・レイアウト

### 共通の hover / 汎用セレクタが状態クラスの塗りを詳細度で上書きする
- 症状: ON のボタンがホバー中だけ OFF と同じ見た目。ピン留め列だけ今日のハイライトが消える。`.input{width:100%}` が後勝ちで固定幅を上書きし 1 文字折返し。数値入力が横に伸びてスライダーが潰れる。
- 原因: `button:hover:not(:disabled)`（0,2,1）> `.mini-button.armed`（0,2,0）。`.grid td.is-pinned{background}`（0,2,1）が today を上書き。`input[type='text'] {flex:1}`（0,1,1）> `.number-field`（0,1,0）。同詳細度の後勝ち。
- 対策: 状態ごとのホバー色を同じかそれ以上の詳細度で定義するか、ホバーは `box-shadow: inset 0 0 0 100vmax rgba(255,255,255,.09)` を重ねる。共通規則に `:not(.on)` を付ける。`input.number-field` のように型セレクタを足す。計算済みスタイル / 画素値で確認する。
- 実例: 2026-06-15 Shifter / 2026-07 ExtOsc / 2026-09-02 Sequence
- 自動検出: 候補 `button:hover[^{]*\{[^}]*background\s*:`（warn）
- 出典: Notion 3cfe4d4b-751b-8119-9d49-ce6bdf4cf498, Seq/log/claudeLog.txt:1407-1415, Shf/log/claudeLog.txt:292, 312, EXTOSC-LOG:30-31

### flex / grid の子は既定 min-width:auto で中身の幅まで広がる
- 症状: スマホでモーダル右端が見切れ、`overflow-x:auto` を付けても効かない。grid の列が `minmax(64px,1fr)` で横スクロール。長いパスでボタンが枠外にはみ出す。
- 原因: flex / grid アイテムの `min-width:auto` が子（テーブル・入力欄）の min-content を親へ伝える。
- 対策: 縮めたいアイテムに `min-width:0`、grid 列は `minmax(0,1fr)`。入力側 `flex:1 1 auto; min-width:0`、ボタン側 `flex:0 0 auto`。
- 実例: 2026-06-12 Claudes / 2026-06-21 ReLink / 2026-07-23 Shifter / 2026-08 SignalHub
- 自動検出: 候補 `minmax\(\s*[1-9]\d*px\s*,\s*1fr\)`（warn）
- 出典: Shf/log/claudeLog.txt:1849-1856, SH/log/claudeLog.txt:939-942, Claudes:294-297, ReLink:229-231

### 日本語（CJK）のラベルやボタンが 1 文字ずつ縦に折れる
- 症状: 名前列が 1 文字幅に潰れて縦書き状態。「日を選/定」「追/加」と折返し。「参照…」ボタンの文字が縦並び。
- 原因: CJK は任意位置で改行でき min-content が 1 文字幅になる。隣の nowrap 列や入力欄に押し潰される。
- 対策: 名前やラベルに `word-break: keep-all`、ボタンは `white-space: nowrap; flex-shrink: 0`（Unity USS も `flex-shrink:0`）。
- 実例: 2026-06-12 Claudes / 2026-06-15 Shifter / 2026-06-21 ReLink / 2026-07-11 Shifter / 2026-07-27 ExtOsc
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:1829-1832, 312-315, EXTOSC-LOG:115-130, Claudes:294-297

### スクロール枠や sticky の高さを当て推量の定数で引くとヘッダが隠れる
- 症状: スクロール後に二段ヘッダが見えなくなる（ページ全体がスクロールし、sticky ツールバーが表ヘッダを覆う）。リロードで直る。ジャンプ先のタイトルが固定ヘッダに隠れる。
- 原因: `calc(100vh - ... - 96px)` の 96px が実寸（下余白 72px + ツールバー展開時 150px 前後）と合わない。sticky top を 28px 固定（実高 30px）。scroll-margin を 100px と想定（実測 165px。チップの折り返しで可変）。
- 対策: 式で組むか、ResizeObserver で実測して CSS 変数に流す。
- 実例: 2026-07-06 RigFlow / 2026-07-29 Shifter / 2026-08-17 Shifter
- 自動検出: 候補 `calc\(\s*100vh\s*-[^)]*\d+px`（warn）
- 出典: CLAUDE.md:69-72, Shf/log/claudeLog.txt:1928-1940, 2279-2296, RigFlow/log/claudeLog.txt:1138

### sticky は tr ではなく th にかかる / 被覆は elementFromPoint で判定する
- 症状: 再現スクリプトが「常にヘッダが浮いている」「常に正常」と誤判定。
- 原因: `<tr>` の rect は子の sticky ずらしを反映しない。枠内座標で測ると枠ごと覆われても検出できない。
- 対策: 貼り付き判定は `<th>`、ビューポート基準 + `document.elementFromPoint` で「その座標に何が見えているか」を見る。
- 実例: 2026-08-17 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2300-2312

### hidden 属性は display:flex などに負ける
- 症状: 非表示のはずの行が初期表示で出る。
- 原因: `[hidden]` は UA スタイルの display:none でしかなく、作者 CSS の display 指定に負ける。
- 対策: `[hidden] { display: none !important; }` を全体に 1 つ置く。
- 実例: 2026-08-21 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:1098-1102

### td に display:flex を当てると表の列モデルから外れて段崩れする
- 症状: 操作列だけ行区切り線が段差状にズレる。
- 対策: td は table-cell のまま、flex は内側の div へ。
- 実例: 2026-07-05 RigFlow
- 自動検出: 候補 td に当たるセレクタでの `display:\s*flex`（warn）
- 出典: RigFlow/log/claudeLog.txt:974

### 表の列に最小幅が無いと width:100% の input 列がほぼ 0 幅に潰れる
- 症状: モバイルで総称・メーカー列が見えない。
- 原因: input は内容幅を持たない。
- 対策: 列単位の min-width。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:437

### flex: 1 1 Npx（grow 有効）で折り返し行が幅次第で崩れる
- 症状: ツールバー・候補パネルの折り返し行が幅次第で崩れる（繰り返し発生）。
- 原因: grow が効いて想定以上に伸びる。推測で CSS を直し、実描画を見ずにデプロイしていた。
- 対策: 固定幅 + `min-width:0` を基本にする。デプロイ前に狭幅（~360px）と広幅の両方で実描画を確認する。
- 実例: 2026-06-15 Shifter
- 自動検出: 候補 `flex:\s*1\s+1\s+\d+px`（warn）
- 出典: Shifter/memory/verify-css-layout-visually.md:10-17

### flex-basis 固定の要素には resize が効かない
- 症状: サイドバーを広げられない。
- 原因: `flex: 0 0 200px` が `resize: horizontal` の width を上書きする。
- 対策: `flex: 0 0 auto` + state の幅を inline style、ドラッグ境界を自前で置く。
- 実例: 2026-06-12 Claudes
- 自動検出: 候補 同じルール内に `flex:\s*0 0 \d+px` と `resize:`（warn）
- 出典: Claudes:209-215

### grid-template-rows の行位置は条件付きの子があると 1 行ずれる
- 症状: 注記バーが無いとき転送キューとステータスバーが画面外へ。
- 原因: 暗黙の行配置。
- 対策: flex + 子に比率を持たせる（子の増減で崩れない）。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:52

### 継承した text-transform・存在しない CSS 変数・汎用クラス名の衝突
- 症状: ツールチップの中身が大文字化・背景が透ける。`.hint` が別の段落にも当たり 1 行に潰れる。
- 原因: 親の `text-transform: uppercase` を継承。`--surface` 等の未定義変数。クラス名の衝突。
- 対策: 打ち消しを明示し、実在の変数だけを使い、コンポーネント固有のクラス名にする。
- 実例: 2026-09-23 ftpDeck
- 自動検出: 候補 `var(--x)` が :root で未定義（ファイル横断が要る）
- 出典: ftpDeck/log/claudeLog.txt:919

### フォントに無い記号（U+23FB など）で豆腐が出る
- 症状: ボタンが ▯ になる。
- 原因: Windows 既定フォントに無い記号。
- 対策: 記号はアイコンライブラリ（lucide-react）で描く。
- 実例: 2026-08 Sequence
- 自動検出: 候補 `[⌀-⏿⬀-⯿]`（.tsx/.jsx で warn）
- 出典: Seq/CLAUDE.md, Seq/log/claudeLog.txt:840-846

### 絵文字アイコンは色（Foreground / color）で塗れない
- dotnet カタログ「絵文字アイコンは Foreground で色が変わらない」を参照（カラー絵文字はフォント側の色）。

### JSX の改行は空白 1 つになり、日本語の文に余計な空白が入る
- 症状: 「読み書き帯域は 変わりません」。
- 対策: 日本語の文は 1 本の文字列にする。
- 実例: 2026-09-23 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:928

### 空白を含む id はアンカー / fragment を壊す
- 症状: ジャンプ不発。
- 原因: "タグ 名称" を id にしていた。
- 対策: インデックスやスラッグで id を作る。
- 実例: 2026-07-06 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:1141

### アンカージャンプが止まるように見えたら、まずスクロール限界を実測する
- 症状: 目次ジャンプが毎回同じ位置で止まる。
- 原因: `scrollY == scrollHeight - innerHeight` で末尾近くは持ち上がらない（正常）。
- 対策: 仮説を立てる前に scrollY / scrollHeight / innerHeight を測る。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/CLAUDE.md:76

### file:// で開いた CSS はキャッシュが強い
- 症状: 静的ハーネスで CSS 修正が反映されない。
- 対策: `?v=<時刻>` のキャッシュバスターを付ける。
- 実例: 2026-06-15 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:316-318

## React・状態・非同期

### React StrictMode の二重マウントで購読・プロセス生成が二重になる
- 症状: 進捗イベントが重複表示。shell が二重生成され、片方の close と別の write が衝突。
- 原因: 開発時の StrictMode が effect を mount → unmount → mount する。
- 対策: effect で購読 / 生成したものは cleanup で必ず解除する。async の listen は cancelled フラグで解決後に即解除（Tauri の listen は tauri カタログ）。プロセス起動などの副作用は effect の外に出すか冪等にする。
- 実例: 2026-06-05 AvolitesRemote / 2026-06-11 Claudes
- 自動検出: 候補 `useEffect\(\s*\(\)\s*=>\s*\{[^}]*\b(listen|subscribe|spawn|invoke)\(`（return が無いとき。複数行で判定が難しい）
- 出典: AvolitesRemote:45-46, Claudes:146

### 同じ children 配列に同じ key を並べると照合が壊れる
- 症状: 別のエディタが 7 回繰り返し描画される。型検査・単体テストは通る。
- 原因: 静的 JSX の兄弟も key で照合される。
- 対策: 役割ごとに一意の key（`input:${id}`）。視覚変更はキャプチャで確認する。
- 実例: 2026-09-03 Sequence
- 自動検出: 不可
- 出典: Notion 3d0e4d4b-751b-814f-8fb9-ce70a7e4fdea

### effect / コールバックが閉じ込めた古い state で判断・保存する
- 症状: 書き出し中なのにポーリングが 250ms に落ちたまま。列幅を保存するとロールフィルタが古い値に戻る（逆も）。
- 原因: effect 内で古い `status` を参照し `status.export` が常に null。別々のコールバックが古い state をクロージャで持ったまま全体を PUT。
- 対策: 取得直後の値で次の間隔を決める（ref か戻り値）。各値の最新を ref に持ち、保存は 1 本に統合する。
- 実例: 2026-06 Shifter / 2026-09-17 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2750-2751, Shifter/memory/shifter-conventions.md:32

### 編集中の入力欄を外部値で上書きすると 1 文字打つ間に消える
- 症状: 再生中に時刻欄へ打ち込むと、打つそばから上書きされる。
- 原因: 絶えず変わる外部値を常に反映する制御コンポーネント。
- 対策: フォーカス中（ref で保持）は外の値で上書きしない。
- 実例: 2026-09-04 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2464-2465

### 状態ポーリング基準で連打を処理すると打鍵数どおりに進まない
- 症状: `.` を 3 回押して 2 フレームしか進まない。
- 原因: キーハンドラが状態ポーリング由来の位置（停止中 4Hz）を基準にしていた。
- 対策: 送った値を即座に反映する ref を基準にする。
- 実例: 2026-08-30 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:446-451

### 短いジョブは running>0 を一度も観測しないまま終わる
- 症状: 小さいファイルの転送完了後に一覧が自動更新されない。
- 原因: 状態更新の間隔より短い。
- 対策: 状態のエッジではなく「完了件数が増えたか」で判定する。操作直後は即座に取り直す。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:57

### 古い応答が新しい画面に出る / 終了後に古いステータスで上書きされる
- 症状: 前の操作の結果が表示される。同フレームの二度押し。終了したのに「実行中 / 待機」に戻る。
- 原因: 非同期応答の順序。監視スレッドが exited の後に running / idle を送る競合。
- 対策: 要求に通し番号を振って古い応答を捨てる。二度押しは ref で判定する。exited を終端状態とし、以後のステータスを無視する。
- 実例: 2026-06 Claudes / 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:982, Claudes:48-49

### 行キャッシュの署名に含まれない項目は、編集しても古いオブジェクトが残る
- 症状: 案件名を編集してもカードが古いまま。カスタム項目を保存しても開き直すと消える（リロードで戻る）。
- 原因: 行の再利用判定（rowSignature）が表示項目だけ / id だけで、memo が再描画しない、または古い行オブジェクトをモーダルに渡し続ける。
- 対策: キャッシュされた表示用オブジェクトを編集 UI の状態源にしない。id だけ持ち、描画時に最新データから引く。署名には表示に出る全項目を含める。
- 実例: 2026-06-16 Shifter / 2026-08-20 Shifter（2 回）
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:923-926, 2406-2424

### 表示用の多重化構造を集計に流用すると重複して数える
- 症状: 同じ案件カードがスタジオ列に 2 枚。React の key も重複。
- 原因: `projectsByColumn.values()` を全走査。
- 対策: 重複なしの一次リストを別に持ち、集計はそちらを使う。
- 実例: 2026-08-21 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2481-2495

### useMemo(() => today(), []) で日付が初回マウント時に固定される
- 症状: 開いたまま日付をまたぐと「今日」のハイライトが更新されない。
- 対策: 次の深夜 0 時に setTimeout で更新 + visibilitychange / focus で再同期するフックにする。TZ は +9h して getUTC* で読む（マシン TZ 非依存）。
- 実例: 2026-06-23 Shifter
- 自動検出: 候補（patterns-app.md の `react-usememo-today`）
- 出典: Shf/log/claudeLog.txt:1183-1189

### 業務日付を UTC 変換すると前日 / 翌日にずれる
- 症状: （予防）日付が 1 日ずれる。
- 原因: `toISOString()` などで UTC 化。
- 対策: 業務日付は JST 固定の `YYYY-MM-DD` 文字列のまま扱う。監査タイムスタンプだけ UTC。
- 実例: 2026-06 Shifter
- 自動検出: 候補 `toISOString\(\)\.(slice|substring|split)\(`（warn。誤検知あり）
- 出典: Shf/CLAUDE.md, Shifter/memory/shifter-conventions.md:15

### 同じ量を 2 か所で丸めると向きが食い違う（round と floor）
- 症状: 60/30/24fps でフレーム送りしても 3 回に 1 回表示が変わらない（25/50 では起きない）。
- 原因: 移動側 `Math.round(i*1e9/fps)`、表示側 `Math.floor(ns*fps/1e9)`。1e9 を割り切れない fps で境界の 1ns 手前に落ちる。`+1e-6` のごまかしが原因を隠していた。
- 対策: 頭 = `ceil(i*1e9/fps)` と定義し、変換は 1 関数（frameStartNs）に集約する。イプシロンで誤魔化さない。全フレーム往復テスト。
- 実例: 2026-09-01 Sequence / 2026-09-02 Sequence
- 自動検出: 不可
- 出典: Notion 3cee4d4b-751b-813d-a3b5-d8b1c2218203, Seq/log/claudeLog.txt:1035-1058

### 非同期で届く要約を「現在の表示範囲」で割り直すと遅れてついてくる
- 症状: 横スライドすると波形がクリップから遅れてついてくる。
- 原因: 要約（バケット配列）がどの範囲を等分したかを返しておらず、描画側が現在範囲で割った。
- 対策: 要約に「作った範囲（fromNs / toNs / buckets）」を同梱し、描く側はその範囲で配置する。
- 実例: 2026-09-02 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:1162-1172

### 毎フレームの計測値をフレームワークの reactive に流さない
- 症状: （予防）VU メータを reactive 変数で回すと無限更新ループや描画の引きずりの原因になる。
- 対策: rAF ループから DOM を直接書く。
- 実例: 2026-07-18 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/memory/ui-overhaul-variants.md:26

### Svelte のループ中で reactive な配列を参照すると 1 件目しか処理されない
- 症状: ALL STOP が 1 つ目しか止めない。
- 原因: ループ内の処理で `live` が更新され、反復対象が変わる。
- 対策: 対象をループ前にスナップショット（コピー）する。
- 実例: 2026-07 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:547

### 同じ option を選び直すと非制御 select は change を発火しない
- 症状: 2 回目以降、同じプリセットを選んでも入らない。
- 対策: `value=""` の制御要素にし、反映後に見出しへ戻す。
- 実例: 2026-09-16 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:607

### 選択起点を階層移動後も保持して undefined 参照
- 症状: Shift クリックで例外。
- 原因: 別リストへ持ち越したインデックス。
- 対策: パスが変わったら起点を捨てる。
- 実例: 2026-09-03 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:137

### ReactMarkdown は単一改行を連結する
- 症状: textarea で改行した箇条書きが 1 行に潰れる（データは改行を保持）。
- 対策: ユーザー入力の textarea には `remark-breaks`。著者が書く Markdown には付けない。
- 実例: 2026-08-15 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2156-2168

### 失敗を .catch(() => {}) で握り潰すと原因に辿り着けない
- 症状: 「ダブルクリックしても何も起きない」だけが見える。
- 原因: openPath の失敗を握り潰していた（真因は Tauri のスコープ不足）。
- 対策: 失敗はトースト / ログへ必ず出す。
- 実例: 2026-06-12 Claudes
- 自動検出: 候補（patterns-app.md の `js-empty-catch`）
- 出典: Claudes:217-225

### エラー種別をメッセージ文字列で判定すると静かに壊れる
- 症状: Windows 予約名のときだけ 500。
- 対策: 専用のエラー型を作り instanceof で判定する。
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:420

### TS 5.7 で new Uint8Array(len) が BufferSource に渡せない
- 症状: 型エラー（SharedArrayBuffer を含む型になる）。
- 原因: TS 5.7 の型付き配列のジェネリクス化。
- 対策: `new ArrayBuffer(len)` を作ってから `new Uint8Array(buf)` で被せる。
- 実例: 2026-09 MemoryObserver（Web Push の鍵）
- 自動検出: 不可
- 出典: MemoryObserver/log/claudeLog.txt:17-18

### tsconfig.node.json に noEmit を入れると composite と衝突する（TS6310）
- 症状: TS6310。
- 原因: composite は emit を止められない。
- 対策: 出力先を node_modules/.tmp へ逃がす。
- 実例: 2026-08-05 2609SuiseiTour26
- 自動検出: 候補（patterns-app.md の `tsconfig-composite-noemit`）
- 出典: 2609SuiseiTour26/log/claudeLog.txt:953-954

## 入力・ブラウザ API・端末

### キーボードショートカットを event.code だけで判定すると合成入力で発火しない
- 症状: 数字キー / Space のショートカットが自動化ツール経由で効かない。
- 原因: スキャンコードを伴わない入力では code が解決されない。
- 対策: `event.key` も見る。
- 実例: 2026-07 ExtOsc
- 自動検出: 候補 `e(vent)?\.code\s*===`（warn）
- 出典: EXTOSC-LOG:28-29

### HTML5 Drag and Drop はモバイルのタッチで発火しない / setPointerCapture は 2 回目以降取りこぼす
- 症状: スマホで並べ替えが効かない。Pointer Events 化後も 2 回目から効かない。
- 対策: Pointer Events で実装し、`pointermove/up/cancel` は毎ドラッグ window に add / remove。グリップに `touch-action:none`。ドロップ先は `elementFromPoint`。
- 実例: 2026-06-24 Shifter
- 自動検出: 候補 `\bdraggable\b|onDragStart|setPointerCapture`（warn）
- 出典: Shf/log/claudeLog.txt:1334-1361

### showPicker?.() だけに頼ると未対応環境で黙って何も起きない
- 症状: スマホでカレンダーアイコンをタップしても反応しない。
- 原因: 隠した date input を開く手段が `showPicker()` だけで、`?.()` で例外も出ない。
- 対策: 透明な input を枠全面に重ね、タップの当たり先を input 自体にする。同じ値を続けて選ぶ場合に備え選択後に値をクリア。
- 実例: 2026-08-23 Shifter
- 自動検出: 候補（patterns-app.md の `js-showpicker-optional`）
- 出典: Shf/log/claudeLog.txt:2520-2545

### 無効な deviceId で getUserMedia すると既定カメラに黙って落ちる
- 症状: テストパターンのタイルに Web カメラ映像が出た。
- 原因: deviceId を `ideal` 扱いで渡すとフォールバックする。
- 対策: 番兵値のデバイスは getUserMedia から除外する（`exact` 指定も検討）。
- 実例: 2026-07 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:718

### ブラウザアプリは UDP を開けない
- protocol カタログ「ブラウザアプリは UDP を開けない」に記載（常駐プロセスを挟む）。
- 実例: 2026-09-06 OSC2MIDI

### xterm.js の attachCustomKeyEventHandler で return false してもブラウザ既定動作は止まらない
- 症状: Shift+Enter が送信扱いになる / Ctrl+V で二重貼り付け。送るシーケンスを何度変えても直らない。
- 原因: return false は xterm 内部処理だけ止め、隠し textarea への既定入力（Enter の CR、ペースト）が漏れる。
- 対策: 自前処理する分岐では `e.preventDefault()` を必ず呼ぶ。切り分けは CR を含まないマーカー文字だけ送って「送信されるか」を見る。
- 実例: 2026-06-13 Claudes（数日かけて 5 通りのシーケンスを試した）
- 自動検出: 不可（分岐単位の判定が要る）
- 出典: Claudes:337-352, 377-380

### xterm.js のキーハンドラはマウント時に 1 回登録で HMR が効かない
- 症状: 修正したのに挙動が変わらない。
- 対策: 検証は必ず新しいペイン / セッションで行う。
- 実例: 2026-06-13 Claudes
- 自動検出: 不可
- 出典: Claudes:350-351

### Claude Code（Ink）の改行は ESC+CR（meta+Enter）
- 症状: 端末エミュレータから Shift+Enter で改行を入れたい。
- 原因: Ink は stdin 先頭の ESC を meta 修飾とみなし、meta+Enter を改行に割り当てている。
- 対策: `"\x1b\r"` を送る（+ 上の preventDefault）。`\\\r` は PTY 一括書き込みで submit される。
- 実例: 2026-06-12, 2026-06-13 Claudes
- 自動検出: 不可
- 出典: Claudes:177-184, 346-348

### PTY + TUI: 起動直後の DSR（ESC[6n）を取りこぼすと TUI が永久待機する
- 症状: ペインが真っ黒（カーソルのみ）で入力もできない。PTY 出力は最初の 4 バイトで止まる。
- 原因: claude（Ink）が起動時に ESC[6n を送り応答を待つ。フロントのリスナが付く前に emit され xterm が応答しない。
- 対策: バックエンドで出力をバッファし、リスナ取り付け後にスナップショットを再生する（tmux 方式）。
- 実例: 2026-06-11 Claudes
- 自動検出: 不可
- 出典: Claudes:109-126

### ANSI 除去の範囲を列挙で絞ると残骸が混ざる
- 症状: ログに "X"・"7"・"=" が散らばる。
- 対策: CSI 終端は 0x40-0x7E、2 バイトエスケープは 0x20-0x7E、文字集合指定 `ESC ( B` も処理する。
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:356

### ソースにリテラルの制御バイトが埋め込まれる
- 症状: 正規表現の文字クラスに生の 0x00〜0x1F が入っていた（編集の副産物）。git / エディタで壊れうる。
- 原因: 置換・生成時にエスケープが実バイトへ化けた。
- 対策: `\x00-\x1f` のエスケープ表記で書く。書いた後に `grep -P '[\x00-\x08\x0b\x0c\x0e-\x1f]'` で確認する。
- 実例: 2026-06 FlowBot
- 自動検出: 候補 `[\x00-\x08\x0B\x0C\x0E-\x1F]`（テキストソース全般。windows-shell の「シェルに埋め込まない」と同根）
- 出典: FlowBot:106-107

## サーバー（Node / Hono / Express）・SSE・監視

### SPA フォールバックが無い /api/* や /assets/* に index.html を 200 で返す
- 症状: API の打ち間違いが HTML 200 になり原因が見えない。古いハッシュの JS を要求された画面が真っ白（HTML が JS として読まれる）。
- 対策: /api 配下は 404 JSON、無い静的アセットは 404。フォールバックはナビゲーション要求だけ。
- 実例: 2026-09-05 SessionControl / 2026-09-26 MemoryObserver
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:67, MemoryObserver/log/claudeLog.txt:167

### Hono の param は既にデコード済み（二重 decodeURIComponent で 500）
- 症状: % を含む名前で URIError → 500。
- 対策: 二重デコードしない。
- 実例: 2026-09-05 SessionControl
- 自動検出: 候補（patterns-app.md の `hono-param-double-decode`）
- 出典: SessionControl/log/claudeLog.txt:180

### Express 5 で app.get('*') がエラー
- 症状: 起動時にルート定義エラー。
- 原因: Express 5 の path-to-regexp 変更。
- 対策: `app.get('/{*splat}', ...)`。
- 実例: 2026-03-13 VolumeController
- 自動検出: 候補 `\.(get|use|all)\(\s*['"]\*['"]`（Express 5 のときだけ正しい。4 系で誤検知）
- 出典: VC-LOG:14-15

### pkg は Node の subpath imports（#decode）を解決できない
- 症状: pkg で固めた exe が起動時にエラー（node-osc）。
- 原因: pkg が `#` 付き subpath imports 非対応。バンドル先を変えると `__dirname` 相対の静的パスがずれる。
- 対策: esbuild で先にバンドルし、出力を元の場所に置く。GUI が要るなら Tauri へ（実際に移行）。
- 実例: 2026-03-13 VolumeController
- 自動検出: 不可
- 出典: VC-LOG:31-36

### EventSource はヘッダを付けられず、502 等で閉じると再接続しない
- 症状: デーモン再起動後、画面を開き直すまで値が来ない。古いトークンだと 3 秒ごとに張り直し続け入口へ戻れない。
- 原因: SSE の仕様（エラー終了後の自動再接続なし・ヘッダ不可）。
- 対策: トークンは SSE だけ `?token=`（他 API では受けない）。閉じたら自前で数秒後に作り直し、その前に Bearer で 1 回確認して 401 なら打ち切る。
- 実例: 2026-09-26 MemoryObserver
- 自動検出: 不可
- 出典: MemoryObserver/CLAUDE.md:103-106, MemoryObserver/log/claudeLog.txt:158-166, 183

### 状態取得が SSE を流し、画面がそれを受けて取り直す無限ループ
- 症状: リポジトリを開いたまま取り直しが止まらない。
- 原因: 読み取りが変更通知を出していた。
- 対策: 読み取りでは通知しない。通知は書き込み後と監視だけ。
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:175

### SSE 接続数 11 で MaxListenersExceededWarning
- 原因: EventEmitter の既定上限 10。
- 対策: 用途を確認して `setMaxListeners(0)`。
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:72

### chokidar 4 は glob 非対応・後から作ったパスを通知しない・Windows で EPERM で止まる
- 症状: 監視が永久に始まらない。ビルド中に `EPERM: operation not permitted, watch` の後、そのルールだけ二度と通知が来ない（画面は待機中）。
- 原因: chokidar 4 の仕様。error を記録するだけで捨てていた。
- 対策: glob の固定部分から監視ディレクトリを割り出し picomatch で照合。存在を定期確認して出来次第 watch。error で監視を閉じて張り直し（待ち時間は awaitWriteFinish + デバウンスから導く）、張り直し時に同期して取りこぼしを拾う。テストは ready を待つ。
- 実例: 2026-09-05 SessionControl / 2026-09-23 SessionControl
- 自動検出: 候補 `\.on\(\s*['"]error['"]\s*,[^)]*log`（warn）
- 出典: SessionControl/CLAUDE.md:117-130, Notion 3e4e4d4b-751b-8100-9eb9-ecb04bc2e723

### ビルド成果物は複数回書き換えられ、転送と競る
- cloud-sync カタログ「rclone copyto が転送中のファイル書き換えと競って失敗し…」に記載（size / mtime の静止を待って再試行）。
- 実例: 2026-09-23 SessionControl

### Vite はポート使用中なら黙って次のポートへ移る
- 症状: E2E が別アプリを叩く / 想定ポートで繋がらない。
- 原因: 別プロジェクトの dev サーバーが 5173 を占有していた。
- 対策: 起動ログのポートを読み `E2E_BASE_URL` で明示する。`strictPort` を検討する（Tauri の 1420 は tauri カタログ）。
- 実例: 2026-07 Traddist（RigFlow が占有）
- 自動検出: 不可
- 出典: Traddist/log/claudeLog.txt:134

### Google スプレッドシートの CSV エクスポートは 307 リダイレクト
- 症状: `export?format=csv&gid=<gid>` の取得で中身が取れない。
- 原因: 307 でリダイレクトされる（WebFetch は自動追従しない）。
- 対策: リダイレクト先を再フェッチする。
- 実例: 2026-06-13 Shifter
- 自動検出: 不可
- 出典: Shifter/memory/project-overview.md:14

## PWA・Service Worker・iOS

### Service Worker で /api/* をキャッシュ・フォールバックすると認証やデータを壊す / 利用者が旧 JS のまま
- 症状: デプロイ後も古い画面。（予防）認証やデータの古い応答、フォールバック HTML が API 応答になる。
- 対策: `/api/*` は SW で非キャッシュ・非フォールバック。デプロイ後はリロード（必要ならタブを閉じて再訪）を案内する。
- 実例: 2026-06 Shifter
- 自動検出: 不可
- 出典: Shf/CLAUDE.md, Shf/log/claudeLog.txt:1906, Shifter/memory/shifter-conventions.md:17

### Service Worker: respondWith が投げると ERR_FAILED / 深いプロファイルパスで caches.open 失敗 / 強制再読み込みは SW を素通り
- 症状: キャッシュ不可時にナビゲーション自体が失敗。検証用 Chrome のプロファイルを scratchpad 配下に置くと caches.open が「Unexpected internal error」。token → Cookie の 303 経路を外枠で返すと未認証。SW のキャッシュが効いているか確かめられない。
- 原因: SW と CacheStorage の仕様・パス長（260 文字）。ハードリロード（CDP の既定 `Page.reload ignoreCache`）は SW をバイパスする。
- 対策: キャッシュ不可ならネットワークへ回す。検証プロファイルは `%TEMP%\scp-*` のような浅いパス。認証リダイレクト経路は素通し。SW の検証は通常の再読み込み（uiprobe の `--soft`）か CDP の Fetch.enable で。
- 実例: 2026-09-26 MemoryObserver / 2026-09-26 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:238-252, MemoryObserver/CLAUDE.md:87-89

### manifest / アイコン / sw.js は認証情報なしで取得される
- 症状: 全経路で認証すると 401 でインストールできない。
- 対策: その数ファイルだけ明示的に公開パスとして列挙する。
- 実例: 2026-09-05 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:365

### iOS のホーム画面 PWA は Safari と Cookie / ストレージを共有しない
- 症状: 起動のたびに 401 で復帰できない。
- 対策: トークンは localStorage + `Authorization: Bearer`。manifest の start_url にトークンを埋める経路と、トークン入力画面（TokenGate）を置く。
- 実例: 2026-09 MemoryObserver
- 自動検出: 不可
- 出典: MemoryObserver/CLAUDE.md:109-117

### iOS の Tailscale は起動直後に VPN を張り直すので、入れ物を毎回ネットワークから取ると真っ黒
- 症状: PWA 起動直後に画面が真っ黒のまま。
- 原因: Service Worker がキャッシュを持たず HTML / JS を tailnet 越しに取りに行く。
- 対策: SW で入れ物（HTML / ハッシュ付き assets / アイコン）を stale-while-revalidate。/api と manifest はキャッシュしない。
- 実例: 2026-09-26 MemoryObserver
- 自動検出: 不可
- 出典: MemoryObserver/CLAUDE.md:98-102

### iOS PWA の safe-area（black-translucent でヘッダが潜る / 半透明の下部ナビがタップを吸う）
- 症状: ホーム画面追加時にヘッダが iOS ステータスバーと重なる。下部ナビ付近のタップが効かない。
- 原因: `status-bar-style=black-translucent` で内容がステータスバー下に潜るのに、ヘッダ高さが固定。透過ナビ。
- 対策: 高さ・sticky top・スクロール枠の計算すべてに `env(safe-area-inset-top)` を足し、ステータスバー裏に背景を置く。下部ナビは不透明。
- 実例: 2026-06-25 Shifter / 2026-07 Traddist
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:1365-1369, Traddist/log/claudeLog.txt:105

### iOS ホーム画面追加で manifest が無いと、追加時のページ以外がスコープ外になる
- 症状: 在庫タブ以外で上部に「リンク」（✕ + URL バー）が出る。
- 対策: manifest.webmanifest に scope="/"・start_url="/"・display=standalone。変更後はホーム画面へ再追加が要る。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:397

### Web Push は HTTPS 必須、iOS はホーム画面追加 PWA のみ
- 症状: 通知を有効にできない。
- 対策: tailscale serve 等で HTTPS 化、iOS は PWA 化を案内する。
- 実例: 2026-09 MemoryObserver / Traddist
- 自動検出: 不可
- 出典: MemoryObserver/CLAUDE.md:62

### 再読み込みボタンがデータ再取得だけでデプロイ後のコードを読み直さない / 押すと評価結果が返らない
- 症状: デプロイした新版が反映されない。検証で押したボタンの戻り値が取れない。
- 原因: ボタンが triggerAppRefresh（データのみ）だった。reload で実行コンテキストが壊れる。
- 対策: 中身は `window.location.reload()`。検証は「押してページ遷移が起きたか」で見る（SessionControl の `scripts/uiprobe.mjs --click <セレクタ>`）。
- 実例: 2026-07-05 RigFlow
- 自動検出: 不可
- 出典: RigFlow/log/claudeLog.txt:782, rules/app.md:126-135

## E2E（Playwright）

### 固定日付の e2e は時間経過で腐る
- 症状: 変更と無関係に 21 件失敗。
- 原因: spec が固定日を書いており、表示窓から外れた。
- 対策: `dateFromToday(offset)` のような今日基準の相対日を使う。
- 実例: 2026-08-05 Shifter
- 自動検出: 候補 e2e/*.spec.ts の `["'\x60]20\d\d-\d\d-\d\d["'\x60]`（warn）
- 出典: Shf/log/claudeLog.txt:1973-1979

### 永続化される設定を無条件に click すると実行順依存になる
- 症状: 単独では通り全体実行では落ちる。
- 原因: トグルがサーバ側の個人設定に永続化され、前のテストの状態で逆に倒れる。
- 対策: 現在値を読んで必要なときだけ押すヘルパ（ensureToolbarToggleOn）。
- 実例: 2026-08-20 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2353-2358

### 件数を絶対値で検証し、finally が無いと失敗が自己増殖する
- 症状: 一度落ちると以後ずっと落ちる。
- 原因: 「バッジが 0 になる」を期待。失敗時に作ったデータが残り総数が増え続ける。タイムアウトで finally が走らないと残留も起きる。
- 対策: 前後比較（before-1）で判定し、finally で必ず後片付け。残留が出たら掃除から入る。
- 実例: 2026-08-20 / 2026-08-21 Shifter
- 自動検出: 不可
- 出典: Shf/log/claudeLog.txt:2360-2366, 2500-2506

### セレクタが複数要素に一致して strict mode violation
- 症状: E2E が strict mode violation。
- 原因: 汎用クラスの再利用、同じ文言が見出しと凡例の 2 要素にある。UI 改名時のテスト追従漏れも同時に起きやすい。
- 対策: `getByRole('heading', { name })` などロールで絞る。開いている状態のクラスで限定する。ラベルは完全一致で書く。
- 実例: 2026-07-03 Traddist / 2026-08-20 Shifter
- 自動検出: 不可
- 出典: Traddist/log/claudeLog.txt:31, Shf/log/claudeLog.txt:2368-2374
