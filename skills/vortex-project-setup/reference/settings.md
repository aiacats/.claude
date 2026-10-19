# vortex 系プロジェクトの設定（2026-10-19 時点）

基準は SinkaiFes2026（`D:\_ProjectBLUE\Project\SinkaiFes2026\ShinkaiFes2026`、HEAD e09508c2）。行番号はその時点のファイル。
比べた相手は同じサブモジュール（Submod_RealtimeLiveUtility）を使う 5 案件:
vortex_urp（`_vortex\vortex_urp\unity_vortex_urp`）・Ext_Palletproject・Ext_TokinoSora_2026-pia・EXT_Kamitsubaki_Composite・LiveMultiRecorder。
値はどれも `scripts/project_audit.py snapshot` で取り、SinkaiFes2026 の分はファイルの該当行で確かめた。表を作り直すときも snapshot から作る。

区分:
- **共通** … 6 案件（か、理由のある例外を除いた全部）で同じ。新しい案件もこの値にする
- **複製元** … 案件ごとに違うが、シーン・プレハブがその値を前提にしている。シーンを複製する元の案件に揃える
- **取り込み物** … 入れたアセット・パッケージで決まる。値を写すのではなく、同じ物を入れる
- **案件** … 案件ごとに決めてよい（迷ったら複製元に揃える）

## Player（ProjectSettings/ProjectSettings.asset）

| 設定 | SinkaiFes2026 の値（行） | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| Windows の Graphics API | D3D11 → D3D12、Automatic Off（538〜540 `m_APIs: 0200000012000000`・`m_Automatic: 0`） | vortex_urp・Pallet 同じ / TokinoSora D3D11 だけ / Kamitsubaki D3D12 → D3D11 で Automatic / LiveMultiRecorder 指定なし（Automatic） | DX12 だと AVPro Live Camera の映像が真っ黒（コミット 738b78dc、Pallet README 2026-03-23）。TokinoSora は DX12 で Editor が起動直後に落ちるため D3D11 だけ（TokinoSora CLAUDE.md 2026-10-12） | 共通（AVPro を使う案件） |
| Color Space | Linear（50 `m_ActiveColorSpace: 1`） | 全部 Linear | 理由の記録は無い。6 案件とも同じ | 共通 |
| Run In Background | On（86 `runInBackground: 1`） | LiveMultiRecorder だけ Off | 背面で Update が止まり、OSC・Art-Net・MoCap の受信と AVPro の更新も止まる（traps unity-editor「非フォーカスの Unity は…」。SinkaiFes2026 も 2026-09-15 には 0 だった: claudeLog「AVPro の差分調査」） | 共通 |
| Visible In Background | On（109） | 全部 On | – | 共通 |
| Fullscreen Mode | FullScreenWindow（111 `fullscreenMode: 1`） | 全部同じ | – | 共通 |
| 既定の解像度 | 1024×768（45〜46）・Default Is Native Resolution On（84）・Resizable Off（99） | vortex_urp 1920×1080、ほかは 1024×768 | 窓で出すには 4 項目をまとめて変える（traps-catalog unity-build「Player 設定の解像度は 4 項目セット」） | 案件 |
| Active Input Handling | Input System だけ（947 `activeInputHandler: 1`） | vortex_urp・Pallet は Both（2）、ほかは Input System | Input System だけだと旧 Input の QuickDeviceMenu が例外になり、SinkaiFes2026 では消した（claudeLog 2026-09-15）。旧 Input を使う物が残るなら Both。check の `input-legacy-api` が候補を出す | 複製元 |
| Api Compatibility Level | .NET Standard 2.1（945 `apiCompatibilityLevel: 6`） | vortex_urp・Pallet は .NET Framework（3）、ほかは .NET Standard 2.1 | 理由の記録は無い（AVPro には影響しないと判断: claudeLog 2026-09-15） | 案件 |
| Scripting Backend（Standalone） | Mono（853〜854 に Standalone の行が無い = 既定の Mono2x） | 全部 Mono | IL2CPP にするとリフレクション頼みの項目が黙って消える（traps-catalog unity-build） | 共通 |
| Scripting Define（Standalone） | `MAGICACLOTH2;UNITY_POST_PROCESSING_STACK_V2;DOTWEEN;GLTFAST_FORCE_DEFAULT_IMPORTER_OFF;URP_COMPATIBILITY_MODE;UNITY_PIPELINE_URP`（844） | 案件ごとに違う（vortex_urp は BAKERY_INCLUDED・CREST_OCEAN・ODIN_INSPECTOR・VLB_URP・USE_URP など） | 取り込み物が足す。KWS_HD_MODULE_INSTALLED・KWS_URP は参照 0 件で e09508c2 で外した。DOTWEEN は今も参照 0 件（check の INFO） | 取り込み物 |
| GPU Skinning・Player Log | On・On（102・94） | 全部同じ | – | 共通 |

## Editor（EditorSettings.asset）

| 設定 | SinkaiFes2026 の値（行） | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| Enter Play Mode Options | On・0（27〜28） | 全部同じ | 0 は EnterPlayModeOptions.None で、何も外さない = ドメインもシーンも読み直す（既定と同じ動き）。値は Unity 6000.3.5f2 の UnityEditor.CoreModule で確かめた | 共通 |
| Asset Serialization | Force Text（7 `m_SerializationMode: 2`） | 全部同じ | シーンの差分・マージ（skill unity-scene-merge）が前提にする | 共通 |

## Tags and Layers（TagManager.asset）

| 設定 | SinkaiFes2026 の値（行） | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| Layers | 3 Chara・6 BG・7 VcamA・8 VcamB・9 Program（11〜17。4 Water・5 UI は Unity の既定） | vortex_urp: 6 Character・7 Object・8 alfa・9 FS・10 Camera_Main… 31 まで / Pallet: 6 Charator・7 Light・8 Stream… / TokinoSora: 3 Character・6〜9 CameraA〜MainCam・27〜29 QuadView / Kamitsubaki: 3 Character・6 Ignore_A / LiveMultiRecorder: 無し | カメラのカリングマスクやオブジェクトのレイヤーはシーン・プレハブに番号で保存される。複製元と番号を変えると写る物が変わる | 複製元 |
| Rendering Layers | 0 Default・1 Character・2 Object・7 LightIgnore（44〜52。3〜6 は Unity の仮の名前 Light Layer N） | vortex_urp 1 Charactor（綴り違い）・2 Object・7 LightIgnore / Pallet 1 Charactor / TokinoSora 1 Character・2 Object / Kamitsubaki・LiveMultiRecorder は未使用 | キャラは Character のライトだけを受ける（SinkaiFes2026 CLAUDE.md「Lighting (1)/Base/Character Directional Light」）。番号で保存されるのでレイヤーと同じく複製元に揃える | 複製元 |

## Quality・Graphics（QualitySettings.asset・GraphicsSettings.asset）

| 設定 | SinkaiFes2026 の値（行） | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| Quality レベル | Mobile・PC、Windows の既定は PC（QualitySettings 10・64・130） | vortex_urp だけ 6 段（Windows は Ultra）、ほかは Mobile・PC | URP のテンプレートのまま | 案件 |
| RP アセット | PC = `Assets/00_Settings/PC_RPAsset.asset`（QualitySettings 105）、Graphics の既定も同じ（GraphicsSettings 40） | 置き場は案件ごと（vortex_urp・Pallet は `Assets/Settings/Vortex Universal Render Pipeline Asset.asset`） | 効くのは Quality 側の値（traps unity-rendering「効いている URP Asset は QualitySettings 側」） | 案件 |
| URP の Compatibility Mode（RenderGraph を使わない） | On（UniversalRenderPipelineGlobalSettings.asset 309 `m_EnableRenderCompatibilityMode: 1`）+ define URP_COMPATIBILITY_MODE | **他の 5 案件は Off** | 2026-09-15 のコミット 78312661（作者 pjblue「volume調整とレンダーアセットの調整」）で 0 → 1。理由の記録は無い。URP 17.3 は define が無いと Off として扱う（RenderGraphSettings.cs の `#if URP_COMPATIBILITY_MODE`）。On のときだけ ScriptableRenderPass.Execute が呼ばれる（traps unity-rendering「URP 17 では Execute が呼ばれない」の裏返し） | 案件（新しい案件で揃えるかはユーザーに聞く） |

## URP アセット・Renderer

| 設定 | SinkaiFes2026 の値（行） | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| Renderer List | [0] `Assets/03_vortex_live/SinkaiFes2026/vortex ShootingProp AO URP.asset`、[1] サブモジュールの `.../VolumetricLights/Resources/Shaders/VolumetricLightsDepthRenderer.asset`（PC_RPAsset 19〜21） | vortex_urp [0][1] とも AO URP・[2] Depth / Pallet AO URP ×2 / ほかは PC_Renderer 1 つ | Depth は影付きの VolumetricLight が DX11 のときに足す（traps-catalog unity-build「VolumetricLights が DX11 で…」） | 取り込み物 |
| Rendering Path | 本線・Depth とも Forward+（本線 165・Depth 51 `m_RenderingMode: 2`） | 全部 Forward+ | 同じ RP アセットで Forward が混ざると両方のバリアントを作る（同上）。check の `renderer-mode-mixed` | 共通 |
| 本線の Renderer Features | SSAO（Off）・Screen Space Shadows（Off）・NiloToonAllInOne・Beautify（138〜142） | vortex_urp は + MKGlow | 空要素 `{fileID: 0}` があるとビルドの間引きが止まる（e09508c2 と origin/mao/build-plate の cf636af9 で外した。ビルド 6.8 時間 → 9.6 分）。一覧から外れた Feature の塊（ProgramOutRenderFeature・MKGlow・旧 NiloToon、どれもスクリプト無し）はファイルに残るが使われない | 取り込み物 |
| Depth Texture・Opaque Texture | On・On（PC_RPAsset 23〜24） | 全部 On | – | 共通 |
| HDR | On（27） | 全部 On | – | 共通 |
| MSAA | 1（= 無し、29） | vortex_urp・Pallet 4、Kamitsubaki 8、TokinoSora・LiveMultiRecorder 1 | – | 案件 |
| Light Layers・SRP Batcher・Render Scale・GPU Resident Drawer | On・On・1・Off（77・73・30・87） | 全部同じ | Light Layers は Rendering Layer でキャラ用ライトを分けるのに要る | 共通 |

## パッケージ（Packages/manifest.json・packages-lock.json）

| 設定 | SinkaiFes2026 の値 | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| jp.pjblue.realtime-live-utility | `file:../../Submod_RealtimeLiveUtility/Submod_RealtimeLiveUtility/Packages/jp.pjblue.realtime-live-utility` | vortex_urp・TokinoSora 同じ / Pallet・Kamitsubaki は旧い置き場 `.../Assets/LiveSystem` / LiveMultiRecorder は `file:../Submod_…`（Unity プロジェクトが git ルート直下） | Packages/ からの相対。サブモジュールの置き場で決まる | 共通（パスは置き場しだい） |
| Cinemachine | 2.9.7 | Kamitsubaki 3.1.6、LiveMultiRecorder 無し | サブモジュールの package.json が 2.9.7 を要求。3 系では大量エラー（traps-catalog vortex「realtime-live-utility を別プロジェクトへ入れると…」） | 共通 |
| Input System・URP・Newtonsoft | 1.17.0・17.3.0・3.2.2 | 全部同じ | サブモジュールの package.json の依存 | 共通 |
| Timeline・Recorder | 1.8.10・5.1.4 | Pallet だけ 1.8.11・5.1.5 | package.json は Timeline 1.8.10 | 共通 |
| uOSC・uLipSync | git のコミットに固定（`#3788ab28…`・`#ece32727…`、e09508c2） | ほかは `#upm`（ブランチ）、LiveMultiRecorder の uOSC は scopedRegistry の 2.2.0 | ブランチは取り込み直すたびに中身が変わる（taste「外部依存は版を固定」）。固定する値は packages-lock.json の hash | 共通（固定する） |
| UniVRM 4 つ（gltf・univrm・vrm・vrmshaders） | `#427e04db…`（v0.100.1 の lock の hash、e09508c2） | vortex_urp v0.99.4、ほかは v0.100.1 | – | 案件（揃えるなら v0.100.1） |
| ほかの git 参照（R3・UniTask・NuGetForUnity・LEDScreenShader・OSC-Jack-Expansion・lilToon） | コミットに固定（e09508c2） | ほかの案件は版の指定なし・`#master` が多い | 同上 | 共通（固定する） |
| scopedRegistries | Keijiro（registry.npmjs.com、scope jp.keijiro） | 全部 Keijiro（LiveMultiRecorder は Hekomi も） | klak.hap 0.1.20（VJ の HAP）・klak.ndi 2.1.6・minis 1.0.10・osc-jack 2.0.0 | 取り込み物 |
| 埋め込み（Packages/ 直下） | com.waveharmonic.crest 5.9.5（有料・水）・com.mibdev.fullscreen-editor | 全案件に fullscreen-editor。vortex_urp・Pallet は lilToon・unity-mcp なども埋め込み（manifest の git 参照より埋め込みが勝つ: check の `git-overridden-by-embedded`） | 有料の物は入手元をユーザーに聞く | 取り込み物 |
| NuGet（R3 本体ほか） | サブモジュールのパッケージに `packages.config`（R3 1.3.0・Microsoft.Bcl.TimeProvider 8.0.0 ほか 5 つ）と `Packages/R3.1.3.0` などが入っている。案件の `Assets/packages.config` は空 | – | git の com.cysharp.r3 は Unity 用の包みだけで、本体は NuGet（traps-catalog unity-build「R3.Unity はコアの R3 が別途要る」） | 共通（サブモジュールが持つ） |

## Script Execution Order

| 対象 | 値 | 書き方 | 区分 |
|---|---|---|---|
| OscRx_LipSync | 24100 | サブモジュールの `.cs.meta` の `executionOrder`（6 案件とも同じ。snapshot の `executionOrder` に出る） | 共通 |
| MicController・Recorder_VRMBlendShapeProxy・vortex_GamepadOscReceiver | -1・-100・-32000 | コードの `[DefaultExecutionOrder]`（`.cs.meta` は 0）。**snapshot には出ない** | 共通 |
| Crest（WaterRenderer 200 など）・MagicaCloth・DynamicBone・NiloToon・AVPro | 各アセットの `.cs.meta` | 取り込み物が持つ | 取り込み物 |

## git

| 設定 | SinkaiFes2026 の値 | 他の案件 | 理由・出典 | 区分 |
|---|---|---|---|---|
| LFS（.gitattributes） | `*.unity`・`*.playable`・`*.anim`・`*.asset`・`*.fbx`・`*.png`・`*.wav`・`*.mp4`・`*.mov`・`*.dll`・`*.dmx` など 77 パターン。`*.vrm` は 2 つだけ個別、`*.prefab` は LFS でない | `*.asset` を LFS にしているのは SinkaiFes2026・Pallet だけ（vortex_urp・TokinoSora・Kamitsubaki は `merge=unityyamlmerge eol=lf`）。`*.prefab`・`*.vrm` は vortex_urp・TokinoSora が LFS（Kamitsubaki は .vrm だけ）。LiveMultiRecorder は .gitattributes が無い | `*.asset` が LFS だと ProjectSettings も git diff で中身が見えない。50〜100 MiB の .vrm・.prefab が SinkaiFes2026 で 22 本 git の中身に入っている（check の `large-in-git`、GitHub は 100 MiB 超を断る） | 案件（新しい案件の形はユーザーに聞く） |
| `.meta` | `merge=unityyamlmerge eol=lf` | LiveMultiRecorder 以外は同じ | – | 共通 |
| .gitignore | Unity 側 `ShinkaiFes2026/.gitignore` は `/[Ll]ibrary/` など先頭 / で固定。ルートは `log`・`AlphaRendering` が先頭 / 無し | – | 先頭 / が無いと全階層に当たる（traps git）。今は深い所に同名の物が無いので害は出ていない（check の `gitignore-unanchored` は 0 件） | 共通（先頭 / で書く） |
| .git/info/exclude | `/ShinkaiFes2026/Assets/Plugins/ClaudeCodeMCP/`・`.meta`・`/.mcp.json`・`/.claude/settings.local.json` など | – | Unity MCP を個人環境だけに置く（/setup-unity-mcp の personal） | 共通 |
| サブモジュール | `Submod_RealtimeLiveUtility`、.gitmodules の branch = mao/dev2 | 他の案件は branch 指定なし | 新機能は mao/dev2（SinkaiFes2026 メモリ） | 案件 |

## Unity MCP

| 設定 | SinkaiFes2026 の値 | 他の案件 | 区分 |
|---|---|---|---|
| 置き場と版 | `Assets/Plugins/ClaudeCodeMCP` 1.6.0（git から外す） | vortex_urp 1.6.0・Pallet 1.5.4・LiveMultiRecorder 1.5.4 は `Packages/` 埋め込み、TokinoSora は Assets 1.5.4、Kamitsubaki は無し | 案件（入れ方は /setup-unity-mcp） |
| .mcp.json | `MCP_UNITY_HTTP_URL` 無し | Kamitsubaki だけ有り（別の Unity を掴む元。check の `mcp-fixed-url`） | 共通（書かない） |
