---
name: vortex-project-setup
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト。SinkaiFes2026・vortex_urp など）の Unity プロジェクトそのものを立ち上げる・設定を揃える・点検する。基準の案件の設定を JSON に写す（snapshot）・2 つの案件の設定の差を「揃える所 / 取り込み物しだい / 案件ごと」に分けて出す（compare）・基準が無くても分かる問題を出す（check: 空の Renderer Feature・Player のビルドだけ止まる Editor の型の使い方・存在しないビルドのシーン・版を固定していない git 参照・使われない define・file: 参照の先が無い・DX12 が先頭なのに AVPro・同名の asmdef・LFS でない大きいファイルなど）、Editor の API で Player Settings・レイヤー・Rendering Layer・Quality の RP アセットを当てる（ProjectSetupApply）、git（LFS の .gitattributes・.gitignore・サブモジュール）・パッケージ（manifest と版の固定）・取り込み物・URP アセットと Renderer・Unity MCP・プロジェクトの CLAUDE.md まで。「新しい案件の Unity プロジェクトを立ち上げて」「〇〇と同じ設定にして」「プロジェクト設定を揃えて」「パッケージを入れて」「設定が基準と違う所を出して」「プロジェクト設定を点検して」「ビルドのシェーダーコンパイルが終わらない」「AVPro が真っ黒」「git のパッケージの版を固定して」と言われたときに使う。シーンを作る・配線するのは vortex-live-scene-create、キャラを入れるのは vortex-character-setup。
---

# vortex プロジェクトの立ち上げと設定

新しい案件の Unity プロジェクトを、既存の vortex 案件（以下「基準」）と同じ設定で立ち上げる。既にある案件の設定を基準に揃える・点検するのにも使う。
基準の値と理由は `reference/settings.md`（SinkaiFes2026 と同じサブモジュールを使う 5 案件を 2026-10-19 に比べた表）。

この skill の担当はプロジェクトそのもの（パッケージ・ProjectSettings・URP アセット・git・MCP）。
シーンは `vortex-live-scene-create`、キャラは `vortex-character-setup`、Timeline は `vortex-timeline-setup`、Unity MCP の入れ方は `/setup-unity-mcp`（ここでは繰り返さない）。

## 道具

`S=~/.claude/skills/vortex-project-setup`

| 道具 | 用途 |
|---|---|
| `$S/scripts/project_audit.py snapshot <プロジェクト> -o <json>` | 設定の要点を JSON にする（Unity 不要）。パッケージ・Player・Editor・レイヤー・Quality・Graphics・URP アセットと Renderer の Feature・ビルドのシーン・`.cs.meta` の実行順・git（LFS・ignore・サブモジュール）・Unity MCP |
| `$S/scripts/project_audit.py compare <A> <B>` | 2 つ（プロジェクトか snapshot の json）を比べ、「vortex で揃える所 / 取り込み物しだい / 案件ごと」に分けて出す。`--json` もある |
| `$S/scripts/project_audit.py check <プロジェクト>` | 基準が無くても分かる問題を ERROR / WARN / INFO で出す。ERROR があれば終了コード 1。`--no-scan` でファイル全体を読む点検を飛ばす |
| `$S/scripts/editor_api.py` | check の editor-api-in-player の中身（.cs の行き先・#if の 3 値評価・Editor の API の使い方）。`scan(<ソース>)` を単体でも呼べる |
| `$S/scripts/test_project_audit.py` | 上の確かめ（一時フォルダに問題の無い案件と問題を入れた案件を作って流す）。スクリプトを直したら流す |
| `$S/templates/Editor/ProjectSetupApply.cs` | Unity 側。`Read` / `Plan(json, sections)` / `Apply(json, sections)` と個別の `Set*`、`RemoveEmptyRendererFeatures`。前後の値を JSON で返す。使い方は先頭のコメント |
| `$S/templates/Editor/ShaderVariantTools.cs`・`ShaderWarmupOnPlay.cs` | シェーダーの先読み（使う組み合わせを集める・Play に入ったら WarmUp）。手順 6.5 |
| `$S/scripts/csc_check.py <プロジェクト> Assembly-CSharp-Editor <.cs>` | Unity を開かずに雛形の型を確かめる（そのプロジェクトの `Library/Bee` の .rsp を借りる。一度 Unity で開いた案件だけ） |
| `$S/reference/settings.md` | 設定 → 基準の値（ファイルの行）→ 他の案件 → 理由 → 区分 |

`ProjectSetupApply.cs` は案件の `Assets/_TempVerify/Editor/` へ写し、`Library/ScriptAssemblies/Assembly-CSharp-Editor.dll` の時刻でコンパイルを確かめてから
`invoke_method`（typeName `ProjectSetupApply`）で呼ぶ。終わったら `_TempVerify` ごと消す。

## 先に読む（踏んだ罠）

- **Editor ではエラー 0 なのに、Player のビルドだけ CS0246 / CS0234 で止まる**
  原因: Player に入る .cs が、#if UNITY_EDITOR の外で Editor の型（EditorWindow・CustomEditor・AssetDatabase・DefaultAsset など）や、Player に無い名前空間の using（UnityEditorInternal・UnityEditor.SceneManagement）を使っている。
  `using UnityEditor;` だけなら通る（UnityEngine.dll に UnityEditor.Experimental / Analytics の型があり、親の名前空間ができる。SinkaiFes2026 では 35 本あってもビルドは通った）。
  Player に入るかは asmdef が決める: asmdef（asmref）の下なら、その中の Editor フォルダは特別扱いされない。asmdef の無い Assets だけ Editor フォルダの規則。パッケージで asmdef の無い .cs は読まれない。
  → `check` の `editor-api-in-player`（中身は `scripts/editor_api.py`。#if を 3 値で評価: UNITY_EDITOR は偽・案件の define は真・Unity のシンボルと versionDefines は不明で中も見る・
  定義の無いシンボルは偽。コメントと文字列の中は見ない。案件が自分で宣言した同じ名前の型は除く）。EditorWindow・CustomEditor は Editor フォルダか Editor 専用 asmdef へ .meta ごと移し、
  MonoBehaviour の中なら使う所を #if UNITY_EDITOR で囲む。（SinkaiFes2026 02b9a5e7: Guiter の 2 本と ScreenShot_FS。CLAUDE.md に「落ちるはず」とだけあって未確認だった）
  Player に有る UnityEditor の名前空間の一覧（editor_api.PLAYER_EDITOR_NAMESPACES）は Unity 6000.3.5f2 で調べた物。版を上げたら、Player の Assembly-CSharp.rsp の -r: の DLL を走査し直す。

- **起動中の Unity の ProjectSettings を文字で書き換えると、メモリ側の値で保存し直されて戻る**
  症状: EditorBuildSettings・PlayerSettings が戻る。原因: 読み込み済みのアセットはメモリ側が正。→ Unity が開いているなら `ProjectSetupApply`（Editor の API）で書く。
  ファイルを写してよいのは Unity でそのプロジェクトを開く前だけ。（traps unity-editor、実例 2026-08 2609SuiseiTour26）
- **Renderer の Feature 一覧に空要素 `{fileID: 0}` があると、ビルドのシェーダーコンパイルが何時間も終わらない**
  原因: URP の `GatherShaderFeatures` が NRE を出しバリアントの間引きが止まる。コンソールの「is missing RendererFeatures」が合図。
  → `check` の `renderer-empty-feature` → `RemoveEmptyRendererFeatures(<Renderer>, true)`（一覧と `m_RendererFeatureMap` の同じ位置を外す）。
  SinkaiFes2026 では Map がその枠を MKGlow（スクリプトが無い）と覚えていた。
  （SinkaiFes2026 cf636af9（mao/build-plate）: 6.8 時間 → 9.6 分。2026-10-19 の e09508c2（mao/knee-muscle-clamp）でも同じ直し）
- **DX12 だと AVPro Live Camera の映像が真っ黒**。→ Windows の Graphics API は Automatic を外して D3D11 → D3D12。（SinkaiFes2026 738b78dc）
  他の AVPro 製品（DeckLink など）とサブモジュール同梱の DLL だけの案件は未確認なので `check` は WARN にしている。
- **DX11 の案件では、影付きの VolumetricLight が Forward の深度用 Renderer を URP アセットに足す**。混ざると両方のバリアントを作る。
  → 深度用 Renderer の Rendering Path を本線と同じ Forward+ に（`check` の `renderer-mode-mixed`）。（traps-catalog unity-build、2026-09-30 SinkaiFes2026）
- **Active Input Handling を Input System だけ（1）にすると、旧 Input（`UnityEngine.Input`）を呼ぶスクリプトが実行時に例外**。
  SinkaiFes2026 では QuickDeviceMenu が落ちて消した（claudeLog 2026-09-15）。→ 複製元の値に揃え、`check` の `input-legacy-api` で候補を見る。
- **Run In Background が Off だと、背面で Update・OSC・Art-Net・MoCap の受信・AVPro の更新が止まる**。→ On。（traps unity-editor、claudeLog 2026-09-15）
- **realtime-live-utility は Cinemachine 2.9.7 前提**。3 系では大量エラー。`file:` の参照は `Packages/` からの相対で、サブモジュールの置き場で決まる。
  旧い案件（Pallet・Kamitsubaki）は `.../Assets/LiveSystem` を指している。（traps-catalog vortex、2026-03-04 EXT_Kamitsubaki_Composite）
- **git のパッケージをブランチ（`#upm`・`#master`）や版なしで参照すると、取り込み直すたびに中身が変わる**。→ `packages-lock.json` の hash で `#<hash>` に固定する
  （`check` の `git-unpinned` が書き方まで出す）。manifest の git 参照より `Packages/` の埋め込みが勝つ（`git-overridden-by-embedded`。vortex_urp の lilToon・unity-mcp）。
- **manifest.json を外で書き換えても Unity は再解決しない**。追加は `packages-lock.json` を消して force_compilation、削除は lock を消して Unity を開き直す。BOM があると読めない。（traps unity-build）
- **R3 の本体は NuGet**（git の com.cysharp.r3 は Unity 用の包みだけ）。今のサブモジュールのパッケージが `packages.config` と `Packages/R3.1.3.0` などを持っているので、案件で入れ直さない。（traps-catalog unity-build）
- **サブモジュールの切り替えや二重の取り込みで、同名の asmdef がコンパイルを止め「エラー 0」に見える**。→ `check` の `asmdef-duplicate`、コンパイル後は `Library/ScriptAssemblies/*.dll` の時刻を見る。（traps unity-build、2026-09-13 SinkaiFes2026 の Rewired）
- **Editor でエラー 0 でも Player ビルドだけ落ちる**（Runtime の UnityEditor 依存、UnityEditor を参照する DLL の .meta が Any）。→ `check` の `dll-editor-in-player`、最後に Player ビルドまで通す。
  サブモジュールはそのままではスタンドアロンビルドできなかったことがある。（traps unity-build、2026-06-01 LiveMultiRecorder・2026-09-13 SinkaiFes2026）
- **`.gitignore` は先頭 / で固定する**（`tools/` が全階層に当たった）。**lfs migrate の後は `git lfs checkout`**。**.sh は eol=lf**。**サブモジュールを先に push**。（traps git）
  `check` の `gitignore-unanchored`・`sh-eol`、GitHub の 100 MiB の上限は `large-in-git`（index の blob の大きさで見るので、LFS の物は数えない）。
- **ProjectSettings の .asset を LFS に入れている案件では `git diff` で設定の差が見えない**（SinkaiFes2026・Pallet）。→ 変える前後に `snapshot` を取って `compare` で見る。
- **URP の Compatibility Mode（RenderGraph を使わない）は SinkaiFes2026 だけ On**（2026-09-15 78312661、理由の記録なし）。URP 17.3 は define `URP_COMPATIBILITY_MODE` が無いと Off として扱う。
  On / Off で自作の RenderPass の呼ばれ方が変わる（traps unity-rendering「URP 17 では Execute が呼ばれない」）。新しい案件ではユーザーに聞く。
- **`.cs.meta` の実行順しか snapshot に出ない**。MicController（-1）・Recorder_VRMBlendShapeProxy（-100）・vortex_GamepadOscReceiver（-32000）はコードの `[DefaultExecutionOrder]`。
- **初回の `snapshot` / `check` は遅いことがある**: 初めて開くファイル 1 つに数 ms かかる環境で、SinkaiFes2026 の .meta の読み込みが 70 秒（2 回目は 1.5 秒、2026-10-19 実測）。
  `check` は .cs も読むので 1〜3 分（`--no-scan` なら数秒）。所要時間は snapshot の `scanSeconds` に出る。
- **`git check-attr` は日本語や空白のパスを引用符付きで返す**。スクリプトでは `-z` で受けている（直す前は LFS の .mov を「LFS でない」と誤検出した）。

## 聞くこと（AskUserQuestion。推奨を先頭に）

1. **基準の案件**: シーンを複製する元と同じ案件にする（レイヤー・Rendering Layer の番号をシーンが前提にしている）。
   候補は SinkaiFes2026（2026-10 時点で一番新しい）と vortex_urp（`D:\_ProjectBLUE\Project\_vortex\vortex_urp`）。どちらにするかはユーザーに聞く。
2. **名前と置き場**: git ルート `D:\_ProjectBLUE\Project\<案件名>`、Unity プロジェクトはその下の 1 フォルダ（SinkaiFes2026 は `ShinkaiFes2026`）。GitHub のリポジトリを作るか（作るのも push もユーザーの指示があってから）。
3. **取り込み物**: 基準の `snapshot` の埋め込み（`packages.embedded`）と `Assets/` 直下のフォルダの一覧を見せ、要る物と入手元を聞く。
   有料の物（Crest・AVPro・HoloPackage など）は勝手に写さない。サブモジュールが持っている物（NiloToon・OptiTrack・Beautify・VolumetricLights・MagicaCloth2・DOTween・R3 の本体）は入れない。
4. **決まっていない設定**（reference/settings.md の区分が「案件」の物）: LFS の形（`*.asset` を LFS にするか、`*.prefab`・`*.vrm` を LFS にするか）、URP の Compatibility Mode、Api Compatibility、MSAA。
5. 決まっている既定（聞き直さない）: Unity は基準と同じ版（2026-10 時点 6000.3.5f2）、Windows の Graphics API は D3D11 → D3D12、Linear、Run In Background On、Mono、Forward+、Enter Play Mode On・0、Force Text、git のパッケージは hash で固定。

## 手順

### 0. 基準を読む

```bash
python $S/scripts/project_audit.py snapshot <基準> -o <scratchpad>/base.json
python $S/scripts/project_audit.py check <基準>
```
基準そのものの ERROR / WARN は写さない（直した値で作る）。基準の CLAUDE.md・README の「プロジェクト設定」の記述も読む。

### 1. プロジェクトを作る

- 仮想デスクトップを作ってから Unity を起動する（CLAUDE.md §7）。クラッシュとダイアログの待ち受けも立てる（project-types/unity.md）。
- 新しく作るなら、**Unity で開く前に**基準から骨組みを写す: `ProjectSettings/`（`ProjectVersion.txt`・`*.asset`・`*.json`・`Packages/`）、`Packages/manifest.json`・`packages-lock.json`、
  URP アセット・Renderer・Global Settings・Volume Profile を `.meta` ごと（GUID を保つので Quality・Graphics の参照がそのまま繋がる）。
  `Library`・`Temp`・`Logs`・`UserSettings`・`*.csproj`・`*.sln` は写さない。
  写した後で Product Name を直す（`SetProductInfo`）。**この写し方で新しい案件を立ち上げたことはまだ無い（未確認）**。
  ProjectSettings.asset の `productGUID` も同じ値になる。影響は未確認。
- 起動: `Unity.exe -projectPath <Unity プロジェクト> -logFile <Unity プロジェクト>\Logs\editor-session.log`（Editor.log は他の Unity と共有されるため）。

### 2. git

- `git init`（既存のリポジトリならブランチを切るか聞く）・`git lfs install`。
- `.gitattributes` は基準を写し、聞いた LFS の形に直す。100 MiB を超える .vrm は個別の行を足す（SinkaiFes2026 は 2 つ）。
- `.gitignore`: Unity 側は基準の `ShinkaiFes2026/.gitignore`（`/[Ll]ibrary/` など先頭 /）を写す。ルートは `/log/` のように先頭 / で書く。書いたら `git check-ignore -v` で確かめる。
- サブモジュール: `git submodule add -b mao/dev2 https://github.com/ProjectBLUE-000/Submod_RealtimeLiveUtility.git Submod_RealtimeLiveUtility`（ブランチは案件で聞く）。
  サブモジュールへのコミット・push はユーザーの指示があるときだけ。
- `log/claudeLog.txt` と プロジェクトの `CLAUDE.md` は git に乗せない（`.gitignore` に勝手に足さず untracked のまま。claudeLog を追跡するかは最初に聞く）。

### 3. パッケージ

- manifest は基準を写し、`check` の `git-unpinned` が出す `#<hash>` で git 参照を固定する（タグがあればタグでもよい）。
- `jp.pjblue.realtime-live-utility` は `file:<Packages/ からの相対>/Submod_RealtimeLiveUtility/Packages/jp.pjblue.realtime-live-utility`。
  Unity プロジェクトが git ルートの 1 つ下なら `file:../../…`、git ルート直下なら `file:../…`（LiveMultiRecorder）。
- サブモジュールの `package.json` の依存（Cinemachine 2.9.7・Input System 1.17.0・Timeline 1.8.10・URP 17.3.0・Newtonsoft 3.2.2 など）を下回らない版にする
  （SinkaiFes2026 は Animation Rigging 1.4.0・Mathematics 1.3.3 で、package.json の 1.3.0・1.3.2 より上）。Cinemachine は 3 系にしない。
- Unity が開いているときに manifest を変えたら、`packages-lock.json` を消して force_compilation（削除なら Unity を開き直す）。
- `testables` は検証の間だけ足して戻す（SinkaiFes2026 CLAUDE.md）。

### 4. 取り込み物

- 聞いた物だけを入れる。基準の案件から写すなら、フォルダを `.meta` ごと（GUID を保つ）。Asset Store の物はユーザーのアカウントで入れてもらう必要があるかを聞く。
- 入れたら `check` の `asmdef-duplicate`・`guid-duplicate`・`define-unused` を見る（同じ物を Assets とパッケージの両方に入れていないか）。

### 5. ProjectSettings

Unity が開いている状態で、`ProjectSetupApply` で当てる:
```
invoke_method ProjectSetupApply.Plan ["<scratchpad>/base.json", "all"]     # 変える所だけを返す（変えない）
invoke_method ProjectSetupApply.Apply ["<scratchpad>/base.json", "all"]    # 当てて SaveAssets
invoke_method ProjectSetupApply.Read []                                     # 当てた後の値
```
- `all` は define を含まない。define は取り込み物を入れた後に、要る物だけ `SetDefines` / `AddDefines` で（無いアセットの define を足すとコンパイルが壊れる）。
- レイヤー・Rendering Layer は空きか同じ名前の枠だけ書き、別の名前が入っている枠は `conflict` で返す。上書きは `SetLayer(index, name, true)`。Unity の仮の名前（Light Layer N）は写さない。
- Graphics API の先頭を変えると、エディタの API は Unity を開き直したときに変わる。Active Input Handling も開き直しが要る。Color Space を変えるとテクスチャを全部取り込み直す。
- Unity 6000.3.5f2（SinkaiFes2026）で確かめたのは `Plan`（自分の snapshot → 差 0・vortex_urp の snapshot → change 24 / conflict 5 / error 2）と `SetLayer`・`RemoveEmptyRendererFeatures(…, false)`。
  `Apply` をまとめて流すこと、Graphics API を変えたときにダイアログが出るかは未確認。MCP が timeout したら全画面の screenshot でダイアログを探す（traps mcp-external）。
- **書いたら `git diff ProjectSettings` を見る**。TagManager を保存すると、メモリにだけあった物も一緒に書かれる（SinkaiFes2026 では `SetLayer` 1 回で、
  プレハブ（MonsterzMate の Anjo5th・Kosaka5th など）が使い、TagManager には無いタグ `Ignore Bone` がファイルに出た）。頼んでいない差は `git checkout` で戻す。
- Enter Play Mode Options は効き目で比べる（Options が無効なら Options の値に関係なくドメインとシーンを読み直す）。Unity 6.3 はファイルが Enabled 1 / Options 0 でも API が False/0 を返す。

### 6. URP アセットと Renderer

- 手順 1 で写した RP アセットを Quality（`SetQualityRenderPipeline("PC", <path>)`）と Graphics の既定（`SetDefaultRenderPipeline(<path>)`）に当てる。効くのは Quality 側。
- Renderer の空要素は `RemoveEmptyRendererFeatures(<Renderer>, false)` で見てから `true`。
- Renderer の Rendering Path を Forward+ に揃える（深度用も）。Compatibility Mode は聞いた値に（Global Settings の Render Graph の項目。この雛形には入れていない）。

### 6.5 シェーダーの先読み（Play 中にシェーダーのコンパイルで止まるとき）

非同期のシェーダーコンパイルが On でも、Blit で描くもの（URP の CoreBlit・UberPost、NiloToon の Uber Post、Crest の水中）と `#pragma editor_sync_compilation` のシェーダーは
同期でコンパイルされ、Play 中に初めて使う組み合わせで止まる（traps-catalog unity-editor「非同期のシェーダーコンパイルが On でも…」）。
→ 使う組み合わせを ShaderVariantCollection に集め、Play に入ったときに WarmUp する。SinkaiFes2026 の 8a44afb5 が手本（止まり 2 回・最大 180 ms → 0 回・最大 40 ms）。

1. `$S/templates/Editor/ShaderVariantTools.cs` を `_TempVerify/Editor/` へ写す。`ClearTracked()` → Play →
   `Sweep("<Director の名前>", 0, <尺>, 5, 3)` を Timeline ごとに（`State()` で進み具合）→ ライブ用のシーンも Play で流す → `SaveTracked("<案件>/Shaders/<案件>.shadervariants")`。
   記録は Editor 全体の物なので、他のシーンを開いた分も入る。`ClearTracked` してから集める。
2. `$S/templates/Editor/ShaderWarmupOnPlay.cs` を案件の `Scripts/Editor/` に置き、`CollectionPath` を 1 で作った物に書き換える（メニュー Window/vortex/Rendering/Shader Warmup On Play で切り替え）。
3. 確かめる: キャッシュがある状態で `WarmUpTimed(<path>)` が 1 秒未満。効き目を見るなら、よく使うシェーダーに一時的に 1 行足してキャッシュを外し、`Sweep` の `stalls>100ms` を有り・無しで比べる（足した行は git checkout で戻す）。
   Editor の WarmUp が未コンパイルの組み合わせを先にコンパイルすることは `MechanismTest("warmup")`（対照は `"none"`）で確かめられる。
- ビルドの Graphics 設定の Preloaded Shaders には、たぶん入れなくてよい。ビルドではシェーダーはコンパイル済みで、初めて使うときは GPU へ渡すだけ（SinkaiFes2026 2026-10-19 の Development ビルドで Log Shader Compilation を On: 再生中に渡したのは 205 個・計 43 ms、キャラ 1 体を初めて出すときで最大 4.6 ms。1 コマ 16.7 ms に届かない）。測り方: Graphics 設定の Log Shader Compilation を On にして Development ビルド → Player.log の「Uploaded shader variant to the GPU driver … time: N ms」を、起動中と再生中に分けて足す。終わったら Off に戻す（保存で ProjectSettings.asset に m_BuildTargetBatching の既定が書かれるので、git diff を見て戻す）。

### 7. Unity MCP・プロジェクトの CLAUDE.md

- Unity MCP は `/setup-unity-mcp`（SinkaiFes2026 は Assets/Plugins に置き `.git/info/exclude` で外す personal の形）。`.mcp.json` に `MCP_UNITY_HTTP_URL` を書かない。
- `.claude/settings.local.json` の `enabledMcpjsonServers` に `claude-code-mcp-unity`・`context7`。
- プロジェクトの `CLAUDE.md` を作る（git に乗せない）。検証コマンド・アーキテクチャ（Assets の各フォルダの責務・サブモジュール）・シーン構成・触る前に確認が要る領域・よく使う MCP と skill。
  SinkaiFes2026 の CLAUDE.md の節立てが手本。

### 8. 確かめる（ここまでやって「できた」）

1. `python $S/scripts/project_audit.py check <新しい案件>` で ERROR 0。WARN・INFO は理由を付けて報告に残す。
2. `python $S/scripts/project_audit.py compare <scratchpad>/base.json <新しい案件>` で、「vortex で揃える所」の差が意図した物（聞いて変えた物）だけ。
3. コンパイル: `hot_reload` か `force_compilation` → `wait_for_compilation_done` → `get_compilation_errors`。
   「エラー 0」は `Library/ScriptAssemblies/*.dll`（Runtime と Editor の両方）の時刻で再ビルドを確かめてから信じる。
4. Player ビルド（`build_player` か案件の BatchBuild）。初回のシェーダーコンパイルは長い。Editor.log の `After scriptable stripping` が `After built-in stripping` より減っているか、
   `error CS` が無いかを見る。exe を起動して Player.log とキャプチャで確かめる（Succeeded でもシェーダーのエラーは残る: traps unity-build）。
5. `_TempVerify` を消す。基準の案件のシーン・設定は保存していないこと。

## 報告に入れるもの

- 基準の案件と、`compare` の件数（揃える所 / 取り込み物 / 案件）と、揃える所の差の中身
- `check` の結果（作業の前と後）と、直した物・残した物（理由つき）
- `ProjectSetupApply` の結果（`applied` / `conflict` / `error` の行）
- 入れた取り込み物と入手元、聞いて決めた設定（LFS の形・Compatibility Mode など）
- コンパイル（dll の時刻）とビルドの結果。Unity で確かめていない物は「未確認」と書く
- git: コミットしたか・push はしていないこと・サブモジュールのブランチ
