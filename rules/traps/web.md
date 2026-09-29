---
paths:
  - "**/*.{ts,tsx,js,jsx,mjs}"
  - "**/package.json"
  - "**/vite.config.*"
  - "**/wrangler.{toml,json,jsonc}"
---

# web の罠

全件は ~/.claude/traps-catalog/web.md。ここは再発しやすいものだけ。

### Drizzle の default に CURRENT_TIMESTAMP を文字列で渡さない
created_at に "CURRENT_TIMESTAMP" という文字列が入る。原因は文字列が値としてクォートされること。→ ``.default(sql`(CURRENT_TIMESTAMP)`)``。（実例: 2026-06 Shifter / 2026-06-27 RigFlow）

### D1 のバインド変数は 1 クエリ 100 個まで
本番の量でだけ一括 INSERT や `inArray` が失敗する（ローカルの少量では通る）。→ IN は 90 件、INSERT は `floor(100 / 列数)` 行でチャンク分割し、大量データで e2e を回す。（実例: 2026-06-27 Shifter / 2026-06-27 RigFlow）

### wrangler の既定の落とし穴
`r2 object get` が 0 バイトを取って「取れた」に見える。`secret put` が非対話で空のシークレットを登録して Success を返す。→ `--remote` / `--local` を必ず明示し、secret は値をパイプで渡して直後に確かめる。（実例: 2026-07-05 RigFlow / 2026-08-15 Shifter）

### database_id を変えるとローカル D1 が別物になる
"no such table" でテーブルが消えたように見える。原因はローカル D1 が database_id ごとの別ファイルなこと。→ `db:migrate:local` と seed を流し直して dev を再起動。（実例: 2026-07-05 RigFlow / 2026-07 Traddist）

### cloudflare の vite-plugin を固定する
`npm run build` が `registerHooks` の SyntaxError。原因は 1.42 以降が Node 22.15+ を要求し、環境が 22.13 なこと。また worker 側・共有定数の変更は HMR されない。→ `^` を外して固定（か Node を上げる）、worker 側を変えたら dev を再起動。（実例: 2026-06-27 RigFlow / 2026-07-03 Traddist）

### 共通の hover や型セレクタが状態の塗りを上書きする
ON のボタンがホバー中だけ OFF に見える、固定幅が効かない。原因は `button:hover:not(:disabled)`（0,2,1）や `input[type=text]`（0,1,1）が状態クラスより詳細度で勝つこと。→ 状態側を同等以上の詳細度で書くか、ホバーは inset の box-shadow を重ねる。計算済みスタイルで確かめる。（実例: 2026-06-15 Shifter / 2026-07 ExtOsc / 2026-09-02 Sequence）

### flex / grid の子と日本語は縮まない・縦に折れる
モーダルの右端が見切れ `overflow-x` も効かない、ラベルやボタンが 1 文字ずつ縦に並ぶ。原因は子の既定 `min-width:auto` と、CJK の min-content が 1 文字幅なこと。→ 縮める側に `min-width:0`（grid は `minmax(0,1fr)`）、ラベルは `word-break: keep-all`、ボタンは `white-space: nowrap; flex-shrink: 0`。（実例: 2026-06-12 Claudes / 2026-07-11 Shifter / 2026-07-27 ExtOsc）

### StrictMode の二重マウント
購読やイベントが二重になり、shell が 2 つ生成される。原因は開発時の effect の mount → unmount → mount。→ 購読は cleanup で必ず解除し、プロセス起動などの副作用は effect の外に出すか冪等にする。（実例: 2026-06-05 AvolitesRemote / 2026-06-11 Claudes）

### 古いクロージャの state で判断・保存する
保存すると別の設定が古い値に戻る、ポーリング間隔が切り替わらない。原因は effect / コールバックが古い state を閉じ込めて全体を PUT していること。→ 最新値は ref に持ち、保存は 1 本にまとめる。（実例: 2026-06 Shifter / 2026-09-17 Sequence）

### 同じ key を兄弟に並べると照合が壊れる
別のコンポーネントが繰り返し描画される（型検査・単体テストは通る）。原因は静的 JSX の兄弟も key で照合されること。→ 役割ごとに一意の key。（実例: 2026-09-03 Sequence）

### SPA フォールバックは /api と /assets に効かせない
API の打ち間違いが HTML 200 になる、古いハッシュの JS を要求した画面が真っ白。→ /api は 404 JSON、無い静的アセットは 404、フォールバックはナビゲーション要求だけ。（実例: 2026-09-05 SessionControl / 2026-09-26 MemoryObserver）

### 空の catch で失敗を握り潰さない
「押しても何も起きない」しか見えない。原因は失敗を空の catch で捨てていたこと（真因は Tauri のスコープ不足）。→ トーストかログへ必ず出す。（実例: 2026-06-12 Claudes）
