---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
  - "**/*.{shader,hlsl,cginc,compute,shadergraph,shadersubgraph,vfx,mat}"
---
# unity-rendering の罠

全件は ~/.claude/traps-catalog/unity-rendering.md。ここは再発しやすいものだけ。

### 効いている URP Asset は QualitySettings 側
URP Asset を直したのに効かない。原因は現在の Quality レベルの customRenderPipeline が Graphics の既定より優先されること。→ `QualitySettings.renderPipeline` を確かめてから編集する。（実例: 2026-08-16, 09-20 vortex_urp）

### Volume は全プロファイルの override を列挙してから変える
Global Volume の値を変えても変化なし。原因はカメラ別プロファイル（PostProcess_CamN 等）が同じ値を override していること。→ 値を変える前に全 VolumeProfile の override を列挙する。（実例: 2026-09-02 2609SuiseiTour26）

### MaterialPropertyBlock は SRP Batcher を外す
灯体色を MPB 化したらバッチングが壊れて逆効果。overrideMaterial で描くと MPB のレンダラ別の値は無視される。→ 数が多いものはマテリアル複製 + プロパティ ID キャッシュ。MPB は少数だけ。（実例: 2026-08-05 2609SuiseiTour26 / 2026-03-12 EXT_Kamitsubaki_Composite）

### _EmissionColor を書いても光らない
値は入っているのに発光しない。原因はマテリアルの `_EMISSION` キーワードが OFF で、HasProperty は true を返すこと。→ `EnableKeyword("_EMISSION")` と EmissiveIsBlack の解除を一緒に行う。（実例: 2026-09-08 lll-12）

### SetColor はリニア変換されない
同じ DMX 値でライトと発光メッシュの明るさが食い違い白飛びする。原因は Light.color は sRGB→リニア変換されるが `Material.SetColor` はされないこと。→ SetColor 側で `color.linear`（戻すのは `.linear` を外すだけ）。（実例: 2026-08-31 2609SuiseiTour26）

### URP で手動描画するとポストプロセスが乗らない
`camera.Render()` で RT に描くと Bloom が無い。RenderGraph で `activeColorTexture` を読むとポスト前の色。→ `camera.enabled` + `targetTexture` で URP に描かせる。ポスト後は `afterPostProcessColor`。（実例: 2026-02-05 MARQ-Studio / 2026-03 EXT_Kamitsubaki_Composite）

### URP 17 では ScriptableRenderPass.Execute が呼ばれない
自作パスの出力が全ゼロでエラーも無い。原因は Unity 6 / URP 17 が RenderGraph 既定で `RecordRenderGraph` を呼ぶこと。→ `RecordRenderGraph` を実装する。（実例: 2026-03-12 EXT_Kamitsubaki_Composite）

### NiloToon の Volume が色と明るさを変える
ライト 0 でもキャラが光る（charIndirectLightMinColor 0.01 × Multiplier）。強いカラーライトが黄色に転ぶ（mainDirectionalLightMaxContribution=1 が各チャンネルを独立にクランプ）。→ MinColor を override ON で 0、MaxContribution を上げる。（実例: 2026-08-04 2609SuiseiTour26 / 2026-02 2603SuiseiBirthday）

### lilToon は URP 17 の Forward+ を検出できない
カメラの向きや距離でキャラが部分的に暗くなる。原因は `_FORWARD_PLUS` が `_CLUSTER_LIGHT_LOOP` に改名され、lilToon が旧名しか見ないこと。→ `lil_common_macro.hlsl` の検出条件 2 箇所に新名を足す。（実例: 2026-03-25 Ext_Palletproject / 2026-05-31 vortex_urp）

### Kronnect VolumetricLights は Renderer を切っても消えない
カメラ別に消す案が全部空振り。原因は静的一覧から直描きし、enabled も毎フレーム戻すこと。→ コンポーネント自体を無効化するか、global shader int `_ForcedLightInvisible=1`。（実例: 2026-09-01 2609SuiseiTour26 / 2026-09-23 SinkaiFes2026）

### VolumetricLights の負荷は raymarchMinStep で決まる
体積光が重なると重く、消灯中も重い。原因はコストが「投影ピクセル × レイマーチ回数」で明るさに依存しないこと。→ minStep 0.1 → 0.4〜0.5（-57〜64%）。maxSteps は効かない。（実例: 2026-09-23 SinkaiFes2026）

### VolumetricLight に spotAngle を毎フレーム書かない
Zoom を駆動すると gobo が消える。原因は spotAngle が変わるたびにメッシュ再生成・影の再キャプチャが走ること。→ 閾値（例 0.25°）を超えたときだけ書く。（実例: 2026-06-17 Submod_RealtimeLiveUtility）

### 影が遠くで消える
カメラを引くと影が薄れる。原因は URP のシャドウ距離フェードが (1-border)×distance から始まること。→ 影を受ける面の距離を実測して Shadow Distance を決める。Cascade Border=0 は負荷ゼロ。（実例: 2026-09-20 vortex_urp）
