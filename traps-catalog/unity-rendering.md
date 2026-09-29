# unity-rendering の罠（カタログ）

URP・RenderGraph・シェーダ・NiloToon / lilToon・Volume・ライト / 影・RenderTexture・VolumetricLights 等の描画系の罠の全件。

### 実際に効いている URP Asset は Graphics の既定ではなく QualitySettings の customRenderPipeline
- 症状: URP Asset を直したのに効かない。値が同じだと取り違えにも気付けない。
- 原因: 現在の Quality レベル（5=Ultra）の customRenderPipeline が優先される。
- 対策: `QualitySettings.renderPipeline` を確認してから編集する。
- 実例: 2026-08-16 vortex_urp / 2026-09-20 vortex_urp
- 自動検出: 不可
- 出典: VL:236-240, 1280-1282

### MaterialPropertyBlock を使う Renderer は SRP Batcher から外れる
- 症状: 灯体色を MPB 化するとバッチングが壊れて逆効果。
- 原因: URP の SRP Batcher は MPB と非互換。
- 対策: 灯体数が多い色制御はマテリアル複製 + プロパティ ID キャッシュ。MPB は少数の Renderer だけに使う。
- 実例: 2026-08-05 / 2026-09-02 2609SuiseiTour26
- 自動検出: 不可（少数なら MPB が正解）
- 出典: 2609-LOG:616-617, 3513-3514

### overrideMaterial で描くと MaterialPropertyBlock のレンダラ別の値が無視される
- 症状: Cryptomatte のハッシュが全部 0。
- 原因: SRP Batcher が `DrawRendererList` + overrideMaterial で MPB を無視する。`cmd.DrawRenderer` + override でも同じ。
- 対策: レンダラ別の値は CBUFFER の外に置いたプロパティへ `cmd.SetGlobalFloat` してから `cmd.DrawRenderer` を 1 つずつ呼ぶ。
- 実例: 2026-03-12 / 2026-04-22 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:857-880, 1228-1245 / KMT-MEM/project_multipass_renderer.md

### _EMISSION キーワードが OFF だと _EmissionColor を書いても光らない（HasProperty は true）
- 症状: 値は入っているのに発光しない。
- 原因: URP/Lit の `_EMISSION` がマテリアルで無効。HasProperty は true を返すので気付けない。
- 対策: 書き込み先が `_EmissionColor` のときだけ `EnableKeyword("_EMISSION")` と `globalIlluminationFlags` の EmissiveIsBlack 解除。色乗算は RGB のみ（α を壊さない）。
- 実例: 2026-09-08 lll-12
- 自動検出: 不可（マテリアル側でキーワードが立っていれば正当）
- 出典: LLL-LOG:228-240, 290-297

### リニア色空間: Light.color は sRGB→リニア変換されるが Material.SetColor は変換されない
- 症状: 同じ DMX 値でライトと発光メッシュの明るさが食い違い、中間が 2 倍以上明るく白飛び。
- 原因: DMX 128 → 0.502 をリニアとしてそのまま SetColor（本来 0.216）。
- 対策: SetColor 側で `color.linear`。種別間で揃えるかは要判断（戻すのは `.linear` を外すだけ）。
- 実例: 2026-08-31 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:2767-2796

### URP で camera.Render() を呼ぶとポストプロセス（Bloom）が掛からない
- 症状: RenderTexture へ手動レンダリングすると Bloom 無し。Editor では出てビルドで出ないこともある。
- 原因: `camera.Render()` は URP のポストプロセス経路を通らない。
- 対策: `camera.enabled = true` + `targetTexture` で URP に描かせる（プレビュー用と出力用でカメラを分ける）。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可（Built-in では正当）
- 出典: MARQ-CAU 5 節 / MARQ-LOG:1394-1420

### URP 17 は RenderGraph 既定で ScriptableRenderPass.Execute が呼ばれない
- 症状: 自作パスの出力が全ゼロ（何も描かれない）。エラーなし。
- 原因: Unity 6 / URP 17 では `RecordRenderGraph` が呼ばれ、`Execute` は Compatibility Mode 用。
- 対策: `RecordRenderGraph` を実装する（AddUnsafePass 等）。ImportTexture はカラーとデプスを別 RT に分ける（混在 RT は "Both a color and a depthStencil format are provided" エラー）。ビューポートを明示する。
- 実例: 2026-03-12 EXT_Kamitsubaki_Composite
- 自動検出: 不可（URP 16 以前では Execute が正しい）
- 出典: KMT-LOG:745-770

### RenderGraph でポストプロセス後の色は afterPostProcessColor
- 症状: キャプチャした画に Bloom が乗っていない。
- 原因: `activeColorTexture` はポストプロセス前のまま。
- 対策: `resourceData.afterPostProcessColor` を読む。
- 実例: 2026-03 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:1164-1172

### ScriptableRendererFeature の static Instance がドメインリロード後に null
- 症状: Play 開始時に Feature の Instance が null で処理を始められない。
- 原因: リロードで static が消え、`Create()` が MonoBehaviour.Start より後。
- 対策: Feature の OnEnable で Instance を戻し、使う側は遅延で探す（`m_RendererDataList` のリフレクションは URP 更新で壊れうる）。
- 実例: 2026-03-12 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:837-855

### HDR の RenderTexture を ReadPixels すると白飛び
- 症状: 出力映像が全面真っ白／Bloom が過剰。
- 原因: ARGBHalf の >1.0 をそのまま読む。
- 対策: ARGB32 の一時 RT へ Blit してから ReadPixels。読むのはレンダリング完了後（LateUpdate 以降）。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU 6 節 / MARQ-LOG:1491-1515

### Sprites/Default は色を 0-1 にクランプするので Bloom の光漏れが出ない
- 症状: Bloom は掛かっているのに glow が見えない。
- 原因: HDR 値（>1）を出せないシェーダ。加えて Volume の threshold が高い。
- 対策: クランプしない Unlit HDR シェーダを使う。HDR パイプライン（RP Asset / RT 形式 / camera.allowHDR）を一通り確認する。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:1340-1390

### SkinnedMeshRenderer を BakeMesh + DrawMesh で描くと位置ズレを繰り返す
- 症状: 他パスとジオメトリがずれる。行列を直すと別モデルで壊れる（3 回行ったり来たり）。
- 原因: BakeMesh の出力空間が rootBone の有無・向き・親のスケールに依存する。
- 対策: BakeMesh をやめ、`cmd.DrawRenderer` で URP 標準のスキニング経路を通す。
- 実例: 2026-04-22 EXT_Kamitsubaki_Composite
- 自動検出: 不可
- 出典: KMT-LOG:1225-1245

### 自作 URP シェーダの罠 3 点（[Toggle] shader_feature / COLOR セマンティクス / DepthOnly パス）
- 症状: (1) 既定 ON なのに Dimmer が効かない (2) Bloom 前提の HDR 発光が潰れる (3) Depth Prepass 構成で深度に出ず体積光が素通り。
- 原因: (1) マテリアル生成直後はキーワードが立たない (2) Varyings の COLOR は 0-1 にクランプされる環境がある (3) DepthOnly / DepthNormals パスが無い。
- 対策: [ToggleUI] + uniform 分岐、TEXCOORD で運ぶ、3 パス用意する。
- 実例: 2026-08-05 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:865-876

### DecodeHDREnvironment は Core.hlsl だけでは宣言されない
- 症状: `undeclared identifier 'DecodeHDREnvironment'`。
- 原因: 関数は core の `EntityLighting.hlsl` にある。
- 対策: `#include "Packages/com.unity.render-pipelines.core/ShaderLibrary/EntityLighting.hlsl"`。
- 実例: 2026-05-05 PRBL_Gacha
- 自動検出: 不可
- 出典: GACHA-LOG:30-34

### 共有 CBUFFER(UnityPerMaterial) に変数を足すと include 先全部のレイアウトが変わる
- 症状: 同じ .hlsl を使う別シェーダの SRP Batcher 互換が崩れうる。
- 原因: CBUFFER は同一 .hlsl を include する全シェーダで共有。
- 対策: 追加はシェーダ群全体に効く前提で行い、トグル用 float も同じ CBUFFER へ入れてレイアウトを揃える。
- 実例: 2026-05-05 PRBL_Gacha
- 自動検出: 不可
- 出典: GACHA-LOG:1-10

### uGUI 用シェーダや SV_VertexID の全画面三角形シェーダは Graphics.Blit と互換がない
- 症状: PROGRAM の合成が実カメラを出力しない。
- 原因: uGUI のマテリアルを `Graphics.Blit(null, ...)` で使っていた。RenderFeature 用の SV_VertexID シェーダは Blit の頂点入力と合わない。
- 対策: 標準の頂点入力（POSITION / TEXCOORD）で書き直し、実行時のマテリアルとテクスチャをコードで bind する。
- 実例: 2026-07-11 vortex_urp（Switching.shader）
- 自動検出: 不可
- 出典: VL:67-72

### カメラのビューポートを x オフセットすると URP で余分にずれる／Blitter は OnEnable の時点では未初期化
- 症状: LED 出力が 10px 余分にずれる。OnEnable で NRE。Scene ビューの描画でも出力が黒く塗られる。
- 原因: URP のビューポートの扱いと Blitter の初期化タイミング。描画コールバックは Scene ビューのカメラでも呼ばれる。
- 対策: 専用の RT に全面を描き、`Blitter.BlitQuad` で等倍に貼る。コマンドは初回の描画の後に作る。対象のカメラを含む描画だけで処理する。
- 実例: 2026-09-28 Ext_TokinoSora_2026-pia（LED チャート）
- 自動検出: 不可
- 出典: TS:336-339

### LateUpdate の途中で Camera.Render した鏡には MagicaCloth の揺れが反映されない
- 症状: 鏡に映る髪の揺れが遅れる。
- 原因: MagicaCloth の UpdateLocation の既定は全 LateUpdate の後。鏡をその前に描いていた。
- 対策: beginContextRendering で行列を設定し、反射カメラを通常のカメラとして描く（source の depth-1）。
- 実例: 2026-09-28 Ext_TokinoSora_2026-pia（DisplayMirror）
- 自動検出: 不可
- 出典: TS:326-328

### URP のシャドウ距離フェードは (1-border)×distance から始まる
- 症状: カメラを引くと影が薄れて消える（Shadow Distance 50 / Cascade Border 0.2 なら 40m から消え始める）。
- 原因: 影を受ける面が Shadow Distance の外にあり、手前の距離帯はフェード区間を通過していた。
- 対策: 影を受ける面の距離を実測して Shadow Distance を決める。Cascade Border=0 は負荷ゼロ（float 2 つが変わるだけ）。
- 実例: 2026-09-20 vortex_urp（Heikou_Cam 49m）
- 自動検出: 不可
- 出典: VL:1265-1300

### shadowCastingMode=On の数は見かけ。ShadowDistance 外は元から影パスに入っていない
- 症状: 客席 26 個の影を切っても Shadow casters 562 のまま、CPU 変化なし。
- 原因: 50m 以遠は影処理の対象外。
- 対策: 影の最適化は Statistics の Shadow casters とカスケード数で判断する。
- 実例: 2026-09-24 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:795-804

### メッシュ統合で Frustum Culling を失い逆に重くなる
- 症状: Batches は -1,044 だが Tris 19.5M → 51.7M、CPU 55 → 82ms。
- 原因: 巨大な 1 メッシュは一部でも映れば全頂点を処理する。
- 対策: 統合は画面内に収まる塊単位で。事前に頂点数の多いものを除外。統合前後を Statistics で比較する。
- 実例: 2026-09-24 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:765-777

### Volume を Global Volume だけ変えても効かない（カメラ別プロファイルが同じ値を override）
- 症状: Global Volume の charRimLightMultiplier を 0 にしても変化なし。
- 原因: カメラ別の PostProcess_CamN など 5 プロファイルすべてが override していた。
- 対策: 値を変える前に全 VolumeProfile の override を列挙する。
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:3420-3423, 3468-3470

### URP の Volume パラメータを型に依存せず読み書きする（override と SetDirty）
- 症状: 型を並べる実装が増え続ける／overrideState を触らないと反映されない／Editor で変更が消える。
- 原因: VolumeComponent のパラメータは overrideState と値の組。sharedProfile はアセット。
- 対策: `VolumeParameter<T>` をリフレクションで扱い、overrideState も書く。sharedProfile に書くなら Editor で `EditorUtility.SetDirty`。
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: Notion 3cfe4d4b-751b-81e9-98ec-c6f86c78a769

### NiloToon: charIndirectLightMinColor の下限 × charIndirectLightMultiplier でライト 0 でもキャラが光る
- 症状: ライトを 1 灯も点けていないのにキャラだけほんのり明るい（Cube は真っ黒）。
- 原因: NiloToonCharRenderingControlVolume の MinColor 0.01（既定・override OFF）が Multiplier 26.12 倍される。Multiplier を 0 にしても下限クランプが後段なので効かない。
- 対策: charIndirectLightMinColor を override ON で (0,0,0)。
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:132-163

### NiloToon の mainDirectionalLightMaxContribution=1 はチャンネルごとにクランプし、強いカラーライトが黄色に転ぶ
- 症状: オレンジ（R=5, G=2.5, B=0）のライトが (1,1,0) = 黄色になる。
- 原因: `min(1, lightColor)` を各チャンネル独立に掛けるため比率が壊れる。
- 対策: Volume の Main Directional Light Max Contribution を上げる（10 など）。上げると白飛びしやすくなる。
- 実例: 2026-02/03 2603SuiseiBirthday_Realtime
- 自動検出: 不可
- 出典: SB:48-58

### NiloToon Cinematic Rim（3D Classic Style）はマテリアルの 2D リム設定では消えない
- 症状: _DepthTexRimLightUsage=0 にしても縁に青ライン（位置で色が変わる）。
- 原因: NiloToonCinematicRimLightVolume の strengthRimMask3D_ClassicStyle が追加ライト寄与をリム形状にマスクする実装。2D リムとは別系統。
- 対策: Volume 側を下げる（全プロファイル）、Rendering Layer で外す、MPB で _GlobalAdditionalLightMultiplier を Renderer 単位に 0（NiloToonCinematicRimSuppressor）。ドキュメント PDF は現行パッケージに無く、他案件の PackageCache に残っている。
- 実例: 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:3443-3514

### Edit モードの初回描画では NiloToon のキャラが半透明に写る
- 症状: 最初の 1 枚だけキャラが透ける。
- 原因: NiloToon の初期化より前に描画している。
- 対策: 2 回目以降に撮る。
- 実例: 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:178

### lilToon は URP 17（Unity 6）で Forward+ のキーワード改名を検出できず、画角の端で暗くなる
- 症状: カメラの向きや距離を変えると lilToon のキャラが部分的に暗くなる。追加ライトがあると顕著。
- 原因: `_FORWARD_PLUS` が `_CLUSTER_LIGHT_LOOP` に改名された。lilToon は旧名しか見ておらず LIL_ADDITIONAL_LIGHT_MODE=4（頂点でクラスタを引く）になる。
- 対策: `lil_common_macro.hlsl` の検出条件 2 箇所に `USE_CLUSTER_LIGHT_LOOP` / `_CLUSTER_LIGHT_LOOP` を足す（embed したパッケージで）。
- 実例: 2026-03-25 Ext_Palletproject / 2026-05-31 vortex_urp
- 自動検出: 不可
- 出典: PC:1-22 / VC:241-248

### lilToon は追加ライトの shadowAttenuation を使わない（Point / Spot の影を受けない）
- 症状: スポットライトの影がキャラに落ちない。
- 原因: lilGetAdditionalLights が distanceAttenuation しか掛けていない。URP Asset の追加ライトシャドウも無効だった。
- 対策: ループ内で `* light.shadowAttenuation` を掛け、`m_AdditionalLightShadowsSupported=1` にする（embed した lilToon を直接改修するので差分の管理が要る）。
- 実例: 2026-05-31 vortex_urp
- 自動検出: 不可
- 出典: VC:260-276

### UnityChanToonShader urp-2.3.0 は URP 17.3 と非互換
- 症状: `GetAdditionalLightShadowSamplingData` の引数不一致 / `_ENVIRONMENTREFLECTIONS_OFF` の重複宣言。
- 原因: 外部シェーダパッケージの URP バージョン非互換。
- 対策: 対応版へ更新する（自前修正はしない）。
- 実例: 2026-05-05 PRBL_Gacha
- 自動検出: 不可
- 出典: GACHA-LOG:34

### Standard → URP 変換で Transparent を Premultiply にすると、ガラスが白く曇る
- 症状: 窓ガラスが白く見える。
- 原因: `_Blend=1`（Premultiply）と PreserveSpecular が効いていた。
- 対策: Standard の Transparent は Alpha（`_Blend=0`）へ移し、PreserveSpecular を 0 にする。変換後は `LitShader.ValidateMaterial` を呼ぶ。
- 実例: 2026-09-27 Ext_TokinoSora_2026-pia（DANCEROOM）
- 自動検出: 不可
- 出典: TS:173, 184

### TMP Essential Resources とフォントアセットが無いと TMP のラベルが空欄になる
- 症状: 表のラベルが出ない（m_mesh が未割り当て）。
- 原因: TMP_SDF シェーダと TMP Settings、Prefab が参照する NotoSansJP SDF が無い。
- 対策: ugui 同梱の unitypackage から Essential Resources を取り込み、フォントは GUID ごとコピーする。
- 実例: 2026-09-28 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: TS:305-306

### Crest の水中エフェクトは _CameraOpaqueTexture を使う（Opaque Downsampling 2x で画面全体がぼやける）
- 症状: 水中で画面がぼやける（鮮鋭度 1/5）。
- 原因: UnderwaterURP が SampleSceneColor を元画像にし、PC_RPAsset の Opaque Downsampling が 2x Bilinear。
- 対策: Opaque Downsampling=None。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:363-371

### MassiveClouds（Atmos）の空は、カメラに MassiveCloudsUniversalRPCameraTarget が無いと描かれない
- 症状: Camera_PGM / PRV の RT に空と雲が出ず、静的なスカイボックスが写る。ライトの色だけ変わる。
- 原因: RenderPass がこのコンポーネントの無いカメラで early return する。
- 対策: 出力カメラに付ける。ただし MassiveClouds のパスが増え、負荷とリークの経路も増える。
- 実例: 2026-08-16 vortex_urp
- 自動検出: 不可
- 出典: VL:222-240

### Kronnect VolumetricLights: Renderer.enabled / forceRenderingOff では消えない
- 症状: カメラ別に体積光を消そうとした案が全て空振り。
- 原因: VolumetricLightsPostProcessBase が静的一覧 volumetricLights を回して cmd.DrawRenderer で直描きする。Mesh.cs が enabled を毎フレーム真に戻す。alwaysOn=1 なら LateUpdate が戻す。
- 対策: コンポーネント自体を無効化する（OnDisable で一覧から外れる）。一括で消すなら global shader int `_ForcedLightInvisible=1`。レイヤー分けは Light ごと消える（RequireComponent(Light)）ので不可。
- 実例: 2026-09-01 / 2026-09-02 2609SuiseiTour26 / 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: 2609-LOG:2804-2807, 2925-2931, 3132-3136 / SINKAI-LOG:530

### VolumetricLights のコストは「投影ピクセル × レイマーチ回数」で明るさに依存しない。minStep が一番効く
- 症状: 体積光が重なると fps が落ちる（57 個で GPU 4.5ms）。消灯中でも重い。
- 原因: ZTest Always / Cull Front で overdraw。ステップ幅 rs = minStep + log(距離)/quality で、短いレイは minStep 支配。maxSteps=200 は 150m 超でしか効かない。Render Feature 未登録で downscale 経路も無効。
- 対策: raymarchMinStep 0.1 → 0.4〜0.5（-57〜64%、見た目差 1.8%。0.5 で 1.71ms）。プレハブは他案件に波及するのでシーンインスタンスへオーバーライドする（Window/vortex/Lighting/Volumetric Light Tuning）。
- 実例: 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:518-632 / Notion 3e4e4d4b-751b-81d0-8e0b-eb224e621392

### VolumetricLight の spotAngle を毎フレーム書くとメッシュを作り直し、gobo cookie が消える
- 症状: Zoom の駆動を入れると gobo が出なくなる。
- 原因: `CheckMesh()` が `spotAngle != generatedSpotAngle` のたびに、メッシュ再生成・マテリアル更新・影の再キャプチャを走らせる。DMX の微振動でも毎フレーム起きる。
- 対策: 差が閾値（例: 0.25°）を超えたときだけ書く。
- 実例: 2026-06-17 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:1373-1382

### VolumetricLight の penumbra は UpdateMaterialProperties を呼ばないと反映されず、毎フレーム呼ぶとメッシュ再生成が走る
- 症状: 値を変えても見た目が変わらない／毎フレームだと重い。enabled の出し入れでも Init（Shader.Find×3 + メッシュ再生成）。
- 原因: パッケージの実装。
- 対策: 量子化した段が変わったときだけ更新する。状態が変わったときだけ書く。
- 実例: 2026-08-24 / 2026-09-02 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1525-1527, 3142-3154

### VolumetricLights の Commons.hlsl の深度テクスチャ宣言が URP と合わず、ビームが床を貫通する
- 症状: ボリュームライトのビームが床を突き抜ける。
- 原因: `UNITY_DECLARE_DEPTH_TEXTURE` / `SAMPLE_DEPTH_TEXTURE` が URP では型が合わない。
- 対策: `Texture2D _CameraDepthTexture` を宣言し、`.Load(int3(uv*_ScreenParams.xy,0))` で読む。Cookie の fallback（activeCookie）も併せて適用する（未コミットのまま消えかけた）。
- 実例: 2026-05 Submod_RealtimeLiveUtility
- 自動検出: 不可
- 出典: SL:400-408, 536-541

### VolumetricLightsBundle の Builtin フォルダに残った Builtin 専用シェーダが URP ビルドでエラー
- 症状: Hidden/VolumetricLights/CopyExact（カーネル無し）/ VolumetricLight（GetCameraPositionWS 未定義）のシェーダエラー 9〜27 件。
- 原因: Builtin フォルダへ URP 版を上書きした際に Builtin 専用ファイル（Resources/Shaders と OnRenderImage 系 PostProcess）が残り、Resources にあるためビルドに含まれる。
- 対策: 残骸 10 ファイルを除去する（サブモジュール c2cd8707）。
- 実例: 2026-08-24 2609SuiseiTour26 / 2026-09-13 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:80-98 / 2609-LOG:1762-1764

### VolumetricLightBeam: VLBConfigOverride.asset の m_RenderPipeline が BuiltIn のまま
- 症状: 起動時 "It looks like the 'Render Pipeline' is not correctly set in the config."、ビルドで VLB_BUILTIN define が付き、生成シェーダが Built-in 版。
- 原因: 判定側 URP と設定側 BuiltIn の不一致（define は結果であって原因ではない）。
- 対策: Config.AutoSelectRenderPipeline と同じ順で renderPipeline=URP → SetDirty → RefreshShaders → SaveAssets → SetScriptingDefineSymbols。
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1819-1852

### メッシュの裏表（ワインディング）
- 症状: 自作メッシュが見えない／裏だけ見える。
- 原因: 頂点順が逆でカリングされる。Unity の表は視点から見て時計回りで、表側は Cross(b-a, c-a) の向き（unity-editor の項目と同じ規約）。
- 対策: 頂点順を確認し、両面が要るなら Cull Off か逆順インデックスを追加する。
- 旧説: MARQ-CAU 7 節の「反時計回りが表」（誤りの疑い。採らない）
- 実例: 2026-02 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU 7 節

### 他分野・skill に置いたもの
- RenderTexture.Release だけではリーク、NiloToon Bloom の毎フレーム確保 → traps-catalog/unity-gc.md
- Recorder の URP RT 入力で PNG が透明 → traps-catalog/unity-timeline.md
- Graphics.CopyTexture の条件、AVPro の D3D12 / _MainTex → traps-catalog/unity-runtime.md
- 出力カメラ 3 台の三重描画、MeshCombiner の非アクティブ統合、Gobo のぼかし、ライブ用 Volume と Rendering Layer のまま新シーンへ持ち込む → traps-catalog/vortex.md
- NiloToon 変換で MatCap が入らない → skill vortex-character-setup に記載
- LED メッシュのマテリアルに RT が繋がっていない → skill vortex-led-framing に記載
- Blender FBX の金属度が URP で 0 → fbx-import の担当

---
出典の略記: 2609-LOG = D:\_ProjectBLUE\Project\2609SuiseiTour26\log\claudeLog.txt / SINKAI-LOG = D:\_ProjectBLUE\Project\SinkaiFes2026\log\claudeLog.txt / VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt / VC = D:\_ProjectBLUE\Project\_vortex\vortex_urp\.claude\claudeLog.txt / SL = D:\_ProjectBLUE\Project\_vortex\Submod_RealtimeLiveUtility\Submod_RealtimeLiveUtility\.claude\claudeLog.txt / TS = D:\_ProjectBLUE\Project\Ext_TokinoSora_2026-pia\log\claudeLog.txt / PC = D:\_ProjectBLUE\Project\Ext_Palletproject\Ext_PalletProject\.claude\claudeLog.txt / SB = D:\_ProjectBLUE\Project\2603SuiseiBirthday\2603SuiseiBirthday_Realtime\.claude\claudeLog.txt / MARQ-LOG = D:\_ProjectBLUE\Project\MARQ\MARQ-Studio\.claude\claudeLog.txt / MARQ-CAU = D:\_ProjectBLUE\Project\MARQ\MARQ-Studio\CLAUDE-UnityCaution.md / KMT-LOG = D:\_ProjectBLUE\Project\EXT_Kamitsubaki_Composite\EXT_Kamitsubaki_Composite\.claude\claudeLog.txt / KMT-MEM = C:\Users\komao\.claude\projects\D---ProjectBLUE-Project-EXT-Kamitsubaki-Composite\memory / GACHA-LOG = D:\_ProjectBLUE\Project\PRBL_Gacha\log\claudeLog.txt / LLL-LOG = D:\_ProjectBLUE\Project\lll-12\log\claudeLog.txt
