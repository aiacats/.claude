# Unity プロジェクト共通ルール

このファイルは `~/.claude/rules/unity.md`。SessionStart hook により、Unity プロジェクト（`ProjectSettings/ProjectVersion.txt` が存在する）でのみ context に自動注入される。グローバル CLAUDE.md の原則に加えて、以下を必ず守ること。

## 実装後のデバッグフロー（claude-code-mcp-unity MCP を使用）

1. `force_compilation` / `hot_reload` で再コンパイルをトリガする。
2. **`wait_for_compilation_done` を1回だけ呼んで完了を待つ**（`check_compilation_status` を polling で連打しない。コンソールがログで詰まり、token も無駄になる）。
3. `get_compilation_errors` でエラー内容を取得する。
4. `get_console_logs` でランタイムエラーやログを確認する。
5. `run_tests` でテストを実行する。
6. 必要に応じて `screenshot` でシーンの状態を視覚確認する。
7. エラーが見つかった場合は根本原因を解決し、再度このフローを実行する。

自主レビュー（グローバル CLAUDE.md「実装後の自主レビュー」）の検証コマンドも同フロー: `force_compilation` → `wait_for_compilation_done` → `get_compilation_errors` → `get_console_logs`。

## シーン保存（恒久・全 Unity プロジェクト共通）

**Unity シーンを自分で変更したら必ず自分で保存する**。MCP の `update_component`／オブジェクト追加・削除、Play 検証のための一時改変を含め、シーンに手を入れたら最後に意図した状態へ戻したうえで `save_scene`（MCP）で保存する。保存し忘れると変更が宙ぶらりんになり、次の操作や domain reload で失われたり、dirty 状態の放置で混乱する。ユーザー指示(2026-06-20)。

## Unity MCP のソース所在と更新フロー（恒久）

- **Unity MCP ソース**: `D:\_Personal\Project\unity-mcp`（Unity 側 embed パッケージ名 `com.aiacats.unity-mcp`、GitHub: aiacats/unity-mcp）
- MCP に機能追加・修正が必要になったら、**使用中プロジェクト内の embed パッケージを直接いじるのではなく、必ず上記ソースリポジトリを更新する**。プロジェクト固有 Editor スクリプトで MCP 的な機能（例: 自動 Play、UI キャプチャ等）を暫定実装した場合も、恒久化のため MCP 本体へ移設する。

更新フロー:
1. `D:\_Personal\Project\unity-mcp` のソースを更新（Node サーバー側 + Unity Editor C# 側）。
2. **このリポジトリに限り、自動でコミット & Push してよい**。
3. その後、使用中プロジェクトの UPM（embed `com.aiacats.unity-mcp`）を更新して取り込む（PackageCache から再 embed、または file: 参照先の同期）。Claude 自身がこの取り込みまで行う。
4. 「自動で Play させる機能」など、これまでプロジェクト側 Editor スクリプトに足してきた MCP 的機能は Unity MCP 本体へ入れる。

## Unity 起動時の注意（恒久）

- Claude のターミナルが管理者権限のことがあり、そこから `Start-Process Unity.exe` すると **Unity が管理者起動**になり「Unity is running as administrator」警告が出る。Unity 起動は **Unity Hub から**行う（またはユーザーに依頼する）のが基本。どうしても CLI 起動する場合も管理者昇格を避ける。
- MCP の新ツール追加後は、Claude Code 再起動まで新ツールは呼べない（既存ツールは動く）。

## MCP 有効化

- Unity プロジェクトでは `.claude/settings.local.json` の `enabledMcpjsonServers` に `claude-code-mcp-unity`, `context7` を列挙する（グローバル CLAUDE.md「MCP サーバーのプロジェクト別有効化方針」参照）。
- セットアップは `/setup-unity-mcp` skill が使える。

## このファイルのルールの扱い

- ここに書いてあるのは**既定**であって絶対ではない。合わないと判断したら破ってよい。
  ただし**破ったことと理由を報告に 1 行書く**（黙って破らない）。
- 例外を持つルールには、そのルール自身に例外条件を書いてある。書いていないものは既定どおり従う。

## 命名・導線（恒久）

- **メニュー名・クラス名・namespace・ファイル名は英語**。UI のラベル・コメント・ログ本文・コミットメッセージは日本語。
  ウィンドウタイトルはメニュー名と揃える。
- メニューの置き場所は用途で決める。
    - Editor ウィンドウ … `Window/vortex/<カテゴリ>/...`（Lighting / Camera / Character / Debug など）。
      既存 87 件はほぼフラットに並んでいて、これ以上積み上げると探せなくなる。新規はカテゴリ配下へ置く。
    - 選択オブジェクトへの操作 … `GameObject/vortex/...`（Hierarchy の右クリックに出る）
    - アセットへの操作 … `Assets/vortex/...`（Project の右クリックに出る）
    - `Tools/Vortex/...` は旧系統（11 件）。新規では使わない。
- プロジェクト名・人名・案件名に由来する命名は使わない。namespace は `vortex` / `vortex.EditorTools`。
- 既存の命名規則に乗せる: 灯体 `VF_*` / OSC 受信 `OscRx_*` / Editor ウィンドウ `*Window`。

## 作る前に確認すること（恒久）

- **同等のツールが既に無いか探す**。探す先は `Submod_RealtimeLighting`、`Submod_RealtimeLiveUtility`、
  他案件の `Assets/vortex/`。あれば「移植する / 導線だけ足す」を先に提案する。
  （実例: `Window/vortex/Rendering Layer Manager` が既にあるのに、同等品を新規に書きかけた）
- **取り込みパッケージは改造しない**。`Content/_ImportPackage/` 配下や Packages の他社製パッケージは、
  外から橋渡しするコンポーネントを 1 ファイル足して解決する。fork / embed は最後の手段
  （「2 行のために全体を抱えない」）。
- 既存ワークフロー（灯体の配置・パッチ・Profile・`VF_*` 本体）には手を入れず、新機能は外付けで足す。

## 不要になったもの（恒久）

- 基本は**削除する**。ただし削除前に一度確認を取り、何が代替になるのかを添える。

## 変更をどこまで広げるか（恒久）

- **指示された対象だけに閉じる**。似た実装が他にもある場合は、横展開するかをユーザー判断に返す。
- 影響範囲は**件数で示してから**適用する（例:「VF_RGB = 1440 台、VF_DRGB = 44 台」）。
- 見え方に関わる既定値を変えたときは、**戻し方**も併せて書く（例:「`.linear` を外すだけ」）。

## Editor 拡張の作法（恒久）

- **Undo 必須**。`Undo.RecordObjects` / `Undo.RegisterCreatedObjectUndo`、
  Prefab インスタンスは `PrefabUtility.RecordPrefabInstancePropertyModifications` も呼ぶ。
- 破壊的な一括操作は、**対象件数・現在値（混在は「混在」と出す）・適用後**を見せてから押させる。
- 一括系の既定は「**非アクティブも含める**」。ただし非アクティブは**意図的に切ってある**ことが多いので、
  件数は「アクティブ N / 非アクティブ M」と**分けて出す**。何を巻き込むかを押す前に見せる。
  同じ対象を二重に数えない（親子を同時選択しても重複排除）。
- 数百件を相手にするツールは「**選択以下だけ**」に絞れる導線を必ず持たせる。シーン全体を出すと辿り着けない。
- ウィンドウは**初期サイズを明示**し、長くなりうる文字列は折り返す（見切れさせない）。
- 検証用に作ったもの（GameObject・一時メニュー・一時スクリプト）は**必ず消してから報告する**。

## 設計の癖（恒久・守ること）

- **対象が増え続けるところは、型を並べて分岐しない**。リフレクションと命名規則で自動収集し、
  灯体や VolumeComponent が増えてもツール側を改修せずに済ませる。**適用するのはそこだけ**。
  分岐が数個で、これ以上増えないと分かっているものまでリフレクションにしない（読めなくなるだけ）。
    - リフレクションは**フィールド名を変えてもコンパイルエラーにならない**。壊れは実行時まで遅れる。
      拾えなかった対象は黙って捨てず**警告を出す**（「対象に入っているのに効かない」を検知できる形にする）。
    - **Runtime で使うなら managed stripping に注意**。現状は Mono + stripping 無効（実測）なので
      問題ないが、IL2CPP へ切り替えると項目が黙って消える。切り替えるなら `link.xml` か `[Preserve]` が要る。
- モード名などの**表記ゆれは読み取り側で正規化**する（`Colour_R` / `ColourR` / `Red`）。既存の `VF_*` は触らない。
- 実行時に書き換える値は原則 **ScriptableObject に書かない**（ビルド後に永続化されず、読み直しで巻き戻る）。
  保存先は `Application.persistentDataPath`。
    - **例外**: Inspector に出ている実体と一致させること自体が目的なら書いてよい
      （例: Volume の `sharedProfile`。同じプロファイルを共有する他の Volume にも効くのが正しい挙動）。
      その場合も Editor では `EditorUtility.SetDirty` を呼び、ビルドでは揮発する前提で保存側を用意する。
- 対象の同定は**実行時 ID ではなくヒエラルキーパス**で行う（対象が増減しても他を巻き込まない）。

## OSC 受信の作法（恒久・実測で踏んだ）

uOSC の `onDataReceived` に登録したハンドラは、**自分宛でないメッセージも含めて全 OSC メッセージで呼ばれる**。
リスナー数 × 受信レートの回数だけ走るので、ハンドラ内の割り当ては受信レートぶんに増幅される。

- **`StartsWith` / `EndsWith` / `IndexOf` には必ず `StringComparison.Ordinal` を指定する**。
  指定しないと既定はカルチャ依存比較で、Unity の Mono では**呼ぶたびにヒープを確保する**。
  早期リターンに使っていると、アドレスが一致しないメッセージでも毎回確保する。
- **比較用のアドレス文字列はハンドラ内で組み立てない**。`Awake` / `OnValidate` で事前計算してフィールドに持つ。
  ハンドラ内の `$"/cinecam/position/{id}"` や `prefix + "/play/"` は、そのまま毎メッセージの割り当てになる。
  ID やプレフィックスが Inspector で変わりうるなら、`_builtFrom` のような「組み立て元」を持って
  変化したときだけ作り直す。
- **`Debug.Log($"...")` はフラグでガードする**。フラグが false でも、引数の文字列補間は先に評価される。
- 受信ハンドラは**冒頭でプレフィックス判定して早期リターン**する。
  自分に関係ないアドレスで、後続の `if / else if` を延々と回さない
  （実例: FacialManager が 5 体 × 18 本 = 最大 90 回の文字列比較を全メッセージで回していた）。
- **`Message.values` は `object[]`** なので、値の取り出しでボクシング解除が要る。
  ここは uOSC の設計上避けられない。`values[0]` を何度も触らず一度ローカルへ。

実測（2026-09-06, vortex_urp。1500 msg/s を 22 秒、300 フレーム平均）:
`StartsWith` に Ordinal を付け、アドレスを事前計算しただけで
**OSC 由来の GC が 23,585 → 12,524 byte/frame（47% 減）**。

### Unity で GC を測るとき

- **`ProfilerRecorder(ProfilerCategory.Memory, "GC Allocated In Frame")` を Play 中に読む**のが確実。
  実負荷をかけて前後比較する。
- **使えないもの**: `GC.GetTotalMemory()` の差分は分解能が足りず小さい割り当てを取りこぼす。
  `GC.GetAllocatedBytesForCurrentThread()` は **Unity の Mono では常に 0 を返すスタブ**。
  どちらも「0 バイト」という誤った結論を出すので、これで判断しない。
- **Deep Profile でないと、リスナーのメソッドは呼び出し元のサンプルに合算される**。
  `uOscServer.Update()` が重く見えても、中身は uOSC ではなくリスナー側のことがある
  （uOSC のパースは別スレッドで走るので、そもそも Update() には乗らない）。
- 保存済みの `.data` が巨大で Profiler ウィンドウが固まる場合は、
  `ProfilerDriver.LoadProfile` + `ProfilerDriver.GetHierarchyFrameDataView` で
  `HierarchyFrameDataView.columnGcMemory` を集計する Editor スクリプトを書けば中身を取れる。
- uOSC の GameObject を Inspector で選択していると `uOscServerEditor` が全メッセージを
  Queue に貯める。計測時は**選択を外す**。

## 検証の追加ルール（恒久）

- **ドメインリロード直後の「エラー 0 件」を信用しない**。MCP のトラッカーはリセットされる。
  `force_compilation` を挟むか、`Library/ScriptAssemblies/*.dll` の更新時刻で実際に再ビルドされたかを確かめる。
- Submodule / パッケージを変更したら **Runtime と Editor の両アセンブリ**を検証する。
- **Unity Editor が閉じているときは、同梱 Roslyn で単体コンパイルできる**。
  `Editor/Data/NetCoreRuntime/dotnet.exe` + `Editor/Data/DotNetSdkRoslyn/csc.dll` に、
  `Editor/Data/Managed/UnityEngine/*.dll` と `NetStandard/ref/2.1.0/netstandard.dll` を `-r:` で渡す
  （パスに空白があるのでレスポンスファイル `@file` を使う）。
  ただし **asmdef の参照条件までは再現しないので偽陰性がある**（Roslyn は通ったのに Unity 側で
  CS0246、という踏み方を実際にしている）。Unity を開いたら `force_compilation` で必ず確認し直す。
- **win-gui の `click_text` は日本語 OCR が効かない**。座標クリックを使う。
