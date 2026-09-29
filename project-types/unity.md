# Unity プロジェクトの作業方針

SessionStart hook（`hooks/project-context.mjs`）が、`ProjectSettings/ProjectVersion.txt` を持つプロジェクトでだけ差し込む。
罠は `rules/traps/unity-*.md`（.cs 等を開くと読まれる）と `traps-catalog/unity-*.md`（grep で引く）。

## 実装後のデバッグフロー（Unity MCP）

1. `force_compilation` / `hot_reload` で再コンパイルする。
2. **`wait_for_compilation_done` を 1 回だけ呼んで待つ**（`check_compilation_status` を連打しない）。
3. `get_compilation_errors` → `get_console_logs` → `run_tests` → 必要ならキャプチャ（Unity MCP の screenshot は v1.2.0 で廃止。win-gui `capture_window` で撮る）。
4. エラーがあれば根本原因を直して、1 からやり直す。自主レビューの検証もこの流れ。
- ドメインリロード直後の「エラー 0 件」は信用しない。`Library/ScriptAssemblies/*.dll` の更新時刻で、実際に再ビルドされたかを確かめる。
- Runtime asmdef 配下を触ったら、UnityEditor 参照が `#if UNITY_EDITOR` で囲まれているかを grep で見る。大きな変更やビルドの前は `build_player` で Player ビルドまで通す。
- Submodule・パッケージを変えたら、Runtime と Editor の両アセンブリを確かめる。

## シーンと Editor の扱い

- **シーンを自分で変えたら、自分で保存する**（MCP の `update_component`・オブジェクトの追加削除・Play 検証の一時改変を含む）。
  最後に意図した状態へ戻してから `save_scene`。
- **Unity の起動・再起動は自分で行う**（ユーザーに頼まない）。`Unity.exe -projectPath <パス>` を**非管理者で**起動する
  （管理者のシェルから起動すると「running as administrator」になる。昇格しているなら非管理者で起動する手段を取る）。
  起動の前に、そのプロジェクト用の仮想デスクトップを作る（例外は CLAUDE.md §7）。閉じるときは `CloseMainWindow()`、タイトルの `*` で未保存を先に見る。
- **Play しないと確かめられないものは、確認を取らずに Play して確かめる**（`enter_play_mode`。「未検証」で止めない）。
  終えたら Play を止め、シーンを意図した状態に戻す。
- どの Unity が何を開いているかは `Get-CimInstance Win32_Process -Filter "Name='Unity.exe'"` の `-projectPath` で確かめる。
  ダイアログを押す前にも確かめる（別プロジェクトのダイアログを押しかねない）。

## Unity MCP

- ソース: `D:\_Personal\Project\unity-mcp`（Unity 側 embed パッケージ名 `com.aiacats.unity-mcp`、GitHub: aiacats/unity-mcp）。
- 機能の追加・修正は**ソースのリポジトリを更新する**。このリポジトリに限り、**自動でコミット & push してよい**。
  その後、使用中プロジェクトの embed を更新して取り込むところまで自分でやる。
  プロジェクト側の Editor スクリプトに足してきた MCP 的な機能（自動 Play など）は、本体へ移す。
- 有効化: `.claude/settings.local.json` の `enabledMcpjsonServers` に `claude-code-mcp-unity`, `context7`。セットアップは `/setup-unity-mcp`。
- 新しいツールは Claude Code を再起動するまで呼べない（既存のツールは動く）。

## 作る前に確かめること

- **同等のツールが既に無いか探す**（`Submod_RealtimeLighting`、`Submod_RealtimeLiveUtility`、他案件の `Assets/vortex/`）。
  あれば「移植する / 導線だけ足す」を先に提案する。
- **取り込んだパッケージは改造しない**（`Content/_ImportPackage/` 配下や他社製パッケージ）。外から橋渡しするコンポーネントを 1 ファイル足して解決する。fork / embed は最後の手段。
- 既存のワークフロー（灯体の配置・パッチ・Profile・`VF_*` 本体）には手を入れず、新しい機能は外付けで足す。

## 変更の範囲

（指示された対象だけに閉じる、は `rules/taste/general.md`「進め方・報告」）
- 影響範囲は**件数で示してから**適用する（例:「VF_RGB = 1440 台、VF_DRGB = 44 台」）。
- 見え方に関わる値（既存キャラ・マテリアル・Volume）は、検証の間だけ変えて戻し、採否はユーザーに返す。
  採用された変更には**戻し方**も書く（例:「`.linear` を外すだけ」）。
- 不要になった既存のものは基本的に削除するが、削除の前に一度確認を取り、何が代わりになるかを添える。

## 命名と導線

- メニュー名・クラス名・namespace・ファイル名・画面に出るラベルは英語。ウィンドウタイトルはメニュー名と揃える。
- メニューの置き場所:
    - Editor ウィンドウ … `Window/vortex/<カテゴリ>/...`（Lighting / Camera / Character / Debug など）。既存はほぼフラットなので、新規はカテゴリ配下へ。
    - 選択オブジェクトへの操作 … `GameObject/vortex/...` / アセットへの操作 … `Assets/vortex/...`
    - `Tools/Vortex/...` は旧系統。新規では使わない。
- プロジェクト名・人名・案件名に由来する名前は使わない。namespace は `vortex` / `vortex.EditorTools`。
- 既存の命名規則に乗せる: 灯体 `VF_*` / OSC 受信 `OscRx_*` / Editor ウィンドウ `*Window`。

## Editor 拡張の作法

- **Undo 必須**（`Undo.RecordObjects` / `Undo.RegisterCreatedObjectUndo`。Prefab インスタンスは `PrefabUtility.RecordPrefabInstancePropertyModifications` も）。
- 破壊的な一括操作は、**対象件数・現在値（混在なら「混在」）・適用後**を見せてから押させる。
- 一括系の既定は「非アクティブも含める」。ただし件数は「アクティブ N / 非アクティブ M」と分けて出す。親子を同時に選んでも二重に数えない。
- 数百件を相手にするツールには、「選択以下だけ」に絞る導線を必ず持たせる。
- ウィンドウは初期サイズを明示し、長くなりうる文字列は折り返す。
- 検証用に作ったもの（GameObject・一時メニュー・一時スクリプト）は、消してから報告する。

## 設計

- **対象が増え続けるところは、型を並べて分岐しない**。リフレクションと命名規則で自動収集する（灯体や VolumeComponent が増えてもツールを改修しない）。
  分岐が数個で増えないと分かっているものまでリフレクションにしない。拾えなかった対象は黙って捨てず警告を出す。
- モード名などの表記ゆれは読み取り側で正規化する（`Colour_R` / `ColourR` / `Red`）。既存の `VF_*` は触らない。
- 対象の同定は、実行時 ID ではなくヒエラルキーパスで行う。
- **実行時に書き換える値は、原則として ScriptableObject に書かない**（ビルド後は永続化されず、読み直しで巻き戻る）。保存先は `Application.persistentDataPath`。
  例外は、Inspector に出ている実体と一致させること自体が目的のもの（Volume の `sharedProfile` など。同じプロファイルを共有する他の Volume にも効くのが正しい）。
  その場合も Editor では `EditorUtility.SetDirty` を呼び、ビルドでは揮発する前提で保存側を用意する。
- 参照の自動解決・今の値を Inspector に出す、などの作り方の好みは `rules/taste/general.md`「作り方」。
- 本番用ビルドには、キー（F1 / F2 など）で開閉するオーバーレイを持たせ、IP・FPS・受信状態・現場依存の設定（受信 NIC など）を出す。
  既定は非表示。設定は `persistentDataPath` に保存する。

## GC スパイクを起こさないか確認する

**Unity のシステムを実装したら、再生時に GC スパイクの要因にならないかを必ず確かめ、報告に「GC の観点で見た結果」を 1 行入れる。**
動くことと、毎フレーム走らせて問題ないことは別。まず**どれだけの頻度で走るか**（Update 系・受信ハンドラ・入力量に比例するループ）を見て、
頻度 × 割り当てで判断する。やりがちな割り当てと測り方は `rules/traps/unity-gc.md`。
