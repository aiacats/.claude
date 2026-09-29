# after-effects の罠（カタログ）

After Effects（ExtendScript・CEP・aerender・Media Encoder）と AEMCP で踏んだ罠の全件。実測はすべて AE 26.5x89。

### ExtendScript の正規表現で文字クラスに素の `/` があると JSX 全体が無応答になる
- 症状: evalScript が返らなくなり、以後 `1+1` すら返らない。以後の全 RPC が 15 秒ずつ詰まり、AE 再起動まで直らない。原因の行から遠い症状しか出ず、ファイルを二分して探した。
- 原因: ES3 のスキャナが `[...]` の中の `/` でリテラルを打ち切る（RegularExpressionClass 未実装）。`/[\\/]+$/` は不可、`/[\/]+$/` は可。Node の vm を使った契約テストは通してしまう。
- 対策: パス区切りの処理は正規表現を避けて charAt で書く。書くなら `[\/]` と必ずエスケープする。Node vm のテストとは別に、実機での往復テスト（probe）を回す。
- 実例: 2026-09-16 AEMCP（host.jsx に未終端の正規表現も同日）
- 自動検出: 候補 `ae-jsx-regex-slash-in-class`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:94-106 / AEMCP\log\claudeLog.txt:32-34, 635-643 / Notion 3dde4d4b-751b-810c-a9e5-c24cec87ab66

### ExtendScript で任意の文字をキーに添字アクセスすると演算子の Function が返る
- 症状: ハイフンを含む文字列を返すと evalScript の戻り値が空。`Object of type Function found where...`。
- 原因: 演算子オーバーロード対応で `obj["-"]` が組み込み演算子の Function になる。
- 対策: 文字の分岐は charCodeAt で比較する（hasOwnProperty も可）。往復テストにハイフン・演算子文字を含める。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:122-128, 140-145 / AEMCP\log\claudeLog.txt:40-45 / Notion 3dde4d4b-751b-814f-9262-c440bbbed619

### ExtendScript に JSON が無い／ポリフィルを条件付きで入れると古い実装が残る
- 症状: JSON 未定義エラー。JSX を直したのに直らない。
- 原因: ES3 相当のエンジンで JSON が無い。エンジンはパネルを再読込しても生き続けるので、`if (typeof JSON.stringify !== 'function')` で守ると旧実装が残る。
- 対策: json2.jsx を無条件で先に読み込む。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `ae-json-polyfill-conditional`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:129-134, 146-150

### evalScript の戻り値は ASCII に閉じる
- 症状: 非 ASCII を含む戻り値が境界で壊れる。
- 原因: 戻り値は文字列でプロセス境界を越える。
- 対策: 非 ASCII は `\uXXXX` へ落とし、JSX 側と JS 側で対にする。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:131-134, 151-152

### ExtendScript の省略可能な引数に undefined を渡すと拒否される
- 症状: `addSolid(..., undefined)` などがエラーになる。
- 原因: ExtendScript は「引数なし」と「undefined」を区別する。
- 対策: 省略するときは引数自体を渡さない。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:93-94

### e.source は評価したスクリプト全体でエラー位置が分からない
- 症状: エラー位置が分からない（先頭 500 文字が返る）。
- 原因: `source` は連結した JSX 全体。
- 対策: `e.line` を使って前後の行を返す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\log\claudeLog.txt:212-214

### setValueAtTime を 1 キーずつ呼ぶとキー数の二乗で遅い
- 症状: 100 キー 170ms / 1000 キー 10 秒 / 5000 キーは 60 秒待っても返らない（MCP 往復込み）。
- 原因: 1 キーごとのコストがキー数に比例する。イージングのために nearestKeyIndex を 1 個ずつ呼ぶのも二乗（1000 キーで 713ms）。
- 対策: 数値系（OneD / TwoD / ThreeD / COLOR とその空間版）は `setValuesAtTimes` で一括（1000 キー 30ms）。TextDocument とマーカーは 1 個ずつしか置けないので型で分岐する。キー時刻は置き終わってから 1 回読み、二分探索で引く（後からより早いキーを足すと index が全部ずれる）。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可（TextDocument の 1 個ずつは正しいので誤検知になる）
- 出典: AEMCP\CLAUDE.md:104-117 / Notion 3dde4d4b-751b-81cc-99c0-c0db592795af

### setTemporalEaseAtKey の KeyframeEase の個数は値の次元数と一致しない
- 症状: 個数違いで例外。握りつぶすとイージングが黙って効かず直線補間になる。
- 原因: 実測 ThreeD_SPATIAL(Position)=1 / ThreeD(Scale)=3 / OneD=1 / COLOR=1（空間プロパティは速度 1 本）。
- 対策: propertyValueType ごとの表（util.jsx の easeCount）で個数を決め、失敗を握りつぶさない。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:84-90 / AEMCP\log\claudeLog.txt:286-296 / Notion 3dde4d4b-751b-81d7-8b0f-dd15dd3d145f

### キーのあるプロパティ（Source Text 等）に setValue すると例外
- 症状: "Can not call setValue() on a property with keyframes."。値が同じでも出る。1 つの try に入れていると他の書式も巻き添えで skipped。
- 原因: API 仕様。実装が値を読んで無条件に書き戻していた。
- 対策: `numKeys > 0` を先に見て分ける。時刻指定なら `setValueAtTime`（キーがあっても通る）。変更が無ければ setValue 自体を呼ばない。
- 実例: 2026-09-16 AEMCP / 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\log\claudeLog.txt:419-423, 811-815 / Notion 3dde4d4b-751b-81de-9e29-c1b04302b6d9

### Property.value は再生ヘッド時刻の値
- 症状: 再生ヘッドを動かしただけでスナップショットの差分が出る。
- 原因: キーのあるプロパティの `.value` は現在時刻での値。
- 対策: `valueAtTime(layer.inPoint)` など時刻を固定して読む。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\log\claudeLog.txt:780-786

### テキストアニメーター: Range Selector が無い・パスに Selectors 段が要る・Shape と Mode の取り違え
- 症状: "The range has no values" で落ちる／`Text/Animators/Animator 1/Range Selector 1/Offset` が解決できない／選択範囲が反転するだけで例外が出ない。
- 原因: `addProperty('ADBE Text Animator')` は Range Selector 無しで生まれる（UI で足すと自動で付く）。正しいパスは `.../Animator 1/Selectors/Range Selector 1/Offset`。Shape=`ADBE Text Range Shape`、Mode=`ADBE Text Selector Mode`（Add/Subtract）。
- 対策: `ensureRangeSelector`（`numProperties === 0` なら `addProperty('ADBE Text Selector')`）。matchName 表を 1 箇所に持つ。文字送りは Selector Mode=2(Ramp Up)、Max/Min Ease=100、Offset を -100→0。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `ae-text-animator-path-without-selectors`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:78-86 / AEMCP\log\claudeLog.txt:207-210 / Notion 3dde4d4b-751b-8151-b02c-e4f35b71027b, 3dde4d4b-751b-819d-a786-e72cc9f10bd2

### アニメーターの Properties グループは追加可能なものを全部持つ
- 症状: 列挙すると 103 件出て、使われているものが分からない。
- 原因: 未使用のプロパティも子として存在する。
- 対策: `isModified` で判別する。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:91-92

### テキスト幅は sourceRectAtTime でしか分からない／ボックステキストのあふれは返らない
- 症状: 文字数で幅を推測すると外れる。ボックステキストは 100 文字でも 3000 文字でも同じ高さを返す。
- 原因: sourceRectAtTime はボックスからあふれた行を返さない。
- 対策: 測る間だけボックスを「文字数×行送り」まで高くして測り、try/finally で戻す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:138-139 / AEMCP\log\claudeLog.txt:402-416, 487-491 / Notion 3dde4d4b-751b-81a2-8bee-c66946a2457b

### 作成直後の layer.index は常に 1
- 症状: 連続作成したレイヤーの番号が全部 1。
- 原因: 新規レイヤーは上に積まれ、番号はずれていく。
- 対策: 同定は `layer.id`（`comp.layerByID` は無いので走査）。番号は作り終えてから読み直す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:140-141 / AEMCP\log\claudeLog.txt:216-218

### app.fonts.allFonts はファミリーごとの入れ子配列
- 症状: postScriptName が全件 "undefined"。エラーが出ずフィルタが空振りする。
- 原因: `allFonts[i]` は FontObject ではなく配列。
- 対策: 二重ループで回す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `ae-allfonts-flat-access`（patterns-dcc.md）
- 出典: AEMCP\log\claudeLog.txt:202-205 / Notion 3dde4d4b-751b-8199-a432-eeab64442125

### app.project.save(file) は別名保存
- 症状: バックアップのつもりで呼ぶと、以後の保存先がそのファイルに変わる。
- 原因: コピー保存ではない。
- 対策: 元に戻すには元のパスへ保存し直す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `ae-project-save-as`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:95-96

### comp.saveFrameToPng は非同期
- 症状: 呼び出し直後のファイルが 0 バイト。
- 原因: 書き込みが非同期（数秒）。
- 対策: 書き込み完了を待つ。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:135-136

### コンポの背景色はフレーム書き出しに乗らない
- 症状: 書き出した PNG の背景が透明・黒。
- 原因: 背景色はプレビュー用。
- 対策: 背景ソリッドを敷く。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\log\claudeLog.txt:710-711

### 「オーディオをキーフレームに変換」はビューアのコンポにしか効かない
- 症状: 別コンポを開いたまま実行するとエラーも出さず何も作らない。
- 原因: メニューコマンドで、ビューア中のコンポと選択レイヤーが対象。
- 対策: openInViewer + 選択を一時的に変えてから executeCommand し、後で戻す。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:142-143 / AEMCP\log\claudeLog.txt:705-707

### 複数の evalScript をまたいで Undo グループが保たれるか確認できない
- 症状: 検証手段が無い（executeCommand(Undo) も Ctrl+Z も測定に使えない）。
- 原因: —
- 対策: 1 回の evalScript（batch）にまとめる。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:118-120

### renderQueue.render() を evalScript から呼ぶと AE ごと固まる
- 症状: 書き出しが終わるまで返らず AE が固まる。
- 原因: 同期レンダー。
- 対策: aerender を別プロセスで走らせる（`-comp` 無しならキューを上から処理）。
- 実例: 2026-09-17 AEMCP
- 自動検出: 候補 `ae-renderqueue-render`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:161-164

### MCP サーバーから起動した aerender が環境変数不足で無言停止
- 症状: "aerender version 26.5x89" の 1 行のまま 10 分以上停止（CPU 0・4.4MB）。
- 原因: MCP の stdio クライアントが子の環境変数を 12 個へ絞り、CommonProgramFiles 系 3 つが落ちる。
- 対策: 子プロセスへ CommonProgramFiles 系をレジストリ（CommonFilesDir）から補って渡す。AEMCP は `aerenderEnvironment()` で対処済み。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:147-154 / AEMCP\log\claudeLog.txt:580-594 / Notion 3dde4d4b-751b-81e8-a3dd-dcdb532aa2d8

### aerender の stdout はパイプだとブロックバッファされる／進捗行の書式
- 症状: 進んでいるのにログが出ず止まって見える。進捗の解析が null のまま。日本語コンポ名が化ける。
- 原因: パイプ相手のブロックバッファリング。行頭に "PROGRESS: " が付き、Duration が Frame Rate より先に出る。出力は OEM コードページ。
- 対策: 出力ファイルやプロセスのメモリで進行を判断する。書式は実物で確かめる。コンポ名は積んだときに控えたものを使う。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:155-157 / AEMCP\log\claudeLog.txt:681-686

### aerender / AME は出力先フォルダを作らない
- 症状: aerender は "Directory does not exist" で 1 項目目から停止。AME の addDLToBatch は理由なく null を返す。
- 原因: 出力先の親フォルダが未作成。
- 対策: 投げる前にフォルダを作る（AEMCP の ae_render / ae_ame_render は対処済み）。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:127-129, 158-160, 186-187

### AME: addCompToBatch は最初のコンポしか使えない／フォーマット名は表示言語依存
- 症状: 狙ったコンポが書き出されない。"AAC オーディオ" などの名前が言語で違い、環境によって形式指定が通らない。
- 原因: API 仕様。フォーマット名がローカライズされる。
- 対策: `addDLToBatch` + `CompItem.dynamicLinkGUID`。フォーマット名は `getFormatList()` で取るか、配布は `.epr` のプリセットで指定する。BridgeTalk は `BridgeTalk.pump()` で evalScript 内で待てる。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:130-164, 183-189 / MEM(AEMCP)\aemcp-status.md:37-39

### AME の Dynamic Link で 2 つ目の AE が起動し、MCP が空の AE に繋がる
- 症状: AME 書き出し直後から「プロジェクトが空の AE」を操作する。BridgeTalk が undefined（app.version は正常なので紛らわしい）。AME を終了しても DL 用 AE が残り、GUI 側の ExtendScript エンジンが固まったままになることがある。
- 原因: DL 用の AfterFX.exe でも CEP 拡張が読み込まれ、bridge ファイルが 2 つできる。
- 対策: CommandLine で判定する（GUI 版は実行ファイルのパス、DL 版は ` -m` だけ）。DL 版ではブリッジを書かない。判定できないときは DL 扱いにしない。AEMCP は extension/src/hostinfo.js で対処済み。
- 旧説: 親プロセス名（dynamiclinkmanager.exe）で判定するのが曖昧さが無い（誤り。PID 再利用で無関係な親が見える。Notion 3dde4d4b-751b-817e が訂正）
- 実例: 2026-09-16 AEMCP / 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:130-146, 168-180 / Notion 3dde4d4b-751b-8127-a51c-e323b7638d40, 3dde4d4b-751b-817e-8be5-fb8594767f01

### process.ppid で同じ AE かを判別できない
- 症状: サービスとパネルで ppid が違う。
- 原因: 1 つの AE の下に CEF ブラウザプロセスが複数できる。
- 対策: 親を AfterFX.exe まで辿る。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:179-189, 204-213

### CEP マニフェストの ScriptPath を使うと evalScript が永久に返らない
- 症状: パネルは起動するが、以後の evalScript が返らない。CEP ログに PlugPlugEvalScriptFn の returned が出ないまま InitContent。
- 原因: CEP が JSX を勝手に評価し、返らないままエンジンを掴む。
- 対策: ScriptPath を使わず、ソースを連結して 1 回の evalScript で流す。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `cep-manifest-scriptpath`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:171-173, 194-196 / AEMCP\log\claudeLog.txt:35-38 / Notion 3dde4d4b-751b-81ae-a788-d1674d0a8cdd

### CEP の StartOn のイベント名は完全修飾名
- 症状: `applicationActivate` と書くとマニフェスト解析は通るが発火しない。
- 原因: `com.adobe.csxs.events.ApplicationActivate` が正。
- 対策: 完全修飾で書く。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `cep-manifest-event-unqualified`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:174-175, 197-198 / Notion 3dde4d4b-751b-81ae-a788-d1674d0a8cdd

### 不可視で起動した CEP 拡張は後からパネルを開いても真っ白
- 症状: DOM もスタイルも正常なのに描画されない。
- 原因: AutoVisible=false + StartOn で起動した拡張。
- 対策: 常駐サービス（不可視）と UI パネル（可視）を別の拡張に分ける。サービスを reload してもパネルは古いままな点にも注意。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:176-178, 199-201 / AEMCP\log\claudeLog.txt:229-232

### CEP パネルの例外はどこにも出ない
- 症状: 無言で動かない。
- 原因: CEP は window のエラーを表に出さない。
- 対策: `window.addEventListener('error')` でログファイルへ落とす。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:202-203

### 未署名の CEP 拡張には PlayerDebugMode=1／署名の確認は 0 に戻して行う
- 症状: 拡張が読み込まれない。開発中は PlayerDebugMode=1 なので署名が効いているか確かめられない。
- 原因: CEP は署名の無い拡張を読み込まない。
- 対策: 開発は `HKCU\Software\Adobe\CSXS.12\PlayerDebugMode=1`。調査は `LogLevel=6` + `%TEMP%\CEP12-AEFT.log`。配布は ZXPSignCmd の自己署名で足り、PlayerDebugMode=0 で読み込まれるかを確かめる。Node 同梱の SEA は esbuild で cjs 必須（ESM だと起動しない）。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:194-197, 218-220 / Notion 3dde4d4b-751b-810b-aff5-c2894089573c

### AE を強制終了すると次回起動が描画されないモーダルで止まる
- 症状: プロセス 157MB・CPU 0 秒のまま無反応。窓もログも出ない。
- 原因: 描画されないモーダルダイアログ（#32770）が起動をブロックする。きっかけは Stop-Process -Force での強制終了。
- 対策: その窓へ WM_CLOSE を送る（AEMCP の launch-ae.ps1 が検出する）。AE を強制終了しない。
- 実例: 2026-09-16 AEMCP
- 自動検出: 候補 `kill-aftereffects`（patterns-dcc.md）
- 出典: AEMCP\CLAUDE.md:212-226 / AEMCP\log\claudeLog.txt:59-64 / Notion 3dde4d4b-751b-8175-be0f-f129305c7fd6

### AE は起動時の作業ディレクトリに HAP-log.txt を吐く
- 症状: リポジトリにゴミファイルが出る（AEMCP のルートに HAP-log.txt が残っている）。
- 原因: 起動時の cwd に書く。
- 対策: リポジトリを作業ディレクトリにして AE を起動しない。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP\CLAUDE.md:227
