# unity-import の罠（カタログ）
FBX / VRM / テクスチャ / モデルの取り込み・ModelImporter・Blender 由来の差。トラブル時に grep で引く。

### Blender 由来の FBX はルートの回転を上書きすると倒れる
- 症状: モデルが縦に倒れる（部屋の奥行きが高さになる）
- 原因: `bakeAxisConversion: 0` のままだとルートに -90° の軸変換（X=270）が入っている。`SetPositionAndRotation(..., Quaternion.identity)` で消える
- 対策: 位置だけ設定する。上書きしたら `PrefabUtility.RevertPropertyOverride`（m_LocalRotation / m_LocalEulerAnglesHint）で戻す
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia / 2026-09-24 BMCP（防音室の書き出し）
- 自動検出: 候補 edit `SetPositionAndRotation\([^,]+,\s*Quaternion\.identity\)`（Blender 由来以外では正しい書き方なので未採用）
- 出典: rules/unity.md「FBX をスクリプトで取り込む・置くとき」/ TS:17-18 / BMCP\log\claudeLog.txt:264-265

### Blender の FBX の金属度は URP で 0 になる（クロームが白い樹脂に見える）
- 症状: Metallic=1 のクロームが質感なし。Unity 側 `_Metallic=0`、_Smoothness は正しい
- 原因: Blender（io_scene_fbx）は Metallic を `ReflectionFactor`、Roughness を Shininess に書く。URP の `FBXMaterialDescriptionPreprocessor`（順序 -980）は Shininess から滑らかさを作るが ReflectionFactor を読まない
- 対策: 順序 -970 の `OnPreprocessMaterialDescription` で ReflectionFactor を `_Metallic` へ（Ext_TokinoSora_2026-pia `vortex.EditorTools.BlenderFbxMetallic` を移植）。対象は ModelImporter.userData に `vortex:BlenderMetallic` を含む FBX だけ。全 FBX に効かせない（既存の見た目が一斉に変わる）。金属に部屋を映すにはボックス投影の Reflection Probe を焼く
- 旧説: 対象の印をアセットのラベルで持つ（誤り。ラベルは取り込み設定の外で、変えても再インポートされず .meta だけ pull した PC で古い結果が残る。userData が正）
- 実例: 2026-09-26 / 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: rules/unity.md / Notion 3e7e4d4b-751b-8143-a3b3-f71d39cae6a1（ラベルの記述が古い）/ TS:116-118, 128-129 / skill blender-stage にも記載

### FBX の埋め込みテクスチャは自動で展開されない（マテリアルが真っ白）
- 症状: 取り込んだだけではマテリアルが白い
- 原因: 埋め込みテクスチャは展開されない
- 対策: `ModelImporter.ExtractTextures(<フォルダ>)` → `*_Normal` を `TextureImporterType.NormalMap` に → FBX を ForceUpdate で再インポート → `_BaseMap` / `_BumpMap` が埋まったか確かめる
- 実例: 2026-09-24 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: rules/unity.md / TS:17-18

### Unity で白くなる原因が Blender 側（Base Color の手前の Mix・Mapping・手続き型ノード）
- 症状: 床や壁が真っ白（法線マップは出ている）
- 原因: FBX の書き出しは Base Color に直結した Image Texture しか拾わない
- 対策: traps-catalog/blender.md と skill blender-stage に記載（ベイクして直結）
- 実例: 2026-09-26 Ext_TokinoSora_2026-pia（BandStudio）
- 自動検出: 不可
- 出典: TS:84-88

### 厚み 0 の片面ポリゴンが Unity で裏から消える
- skill blender-stage に記載（背面カリング。1mm でも厚みを付ける）

### .vrm を取り込んでも背面の Unity では Prefab が作られない
- 症状: テクスチャだけ展開され Prefab ができない
- 原因: UniVRM の Prefab 生成は delayCall 頼みで、背面の Editor では回らない
- 対策: Unity を前面（win-gui focus_window）にしてから `AssetDatabase.ImportAsset` し直す
- 実例: 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: Notion 3e5e4d4b-751b-81fd-bdcb-e33c057af362 / traps-catalog/unity-editor.md「背面の Unity は…」

### VRM のランタイムロードは非フォーカスだと SkinningBake で止まる
- 症状: `Vrm10.LoadPathAsync` が例外もログも無く終わらない
- 原因: `RuntimeOnlyAwaitCaller` がフレーム進行に依存し非フォーカスで間引かれる。capture_window は非フォーカスのまま撮れるので気付かない
- 対策: ロード検証前に focus_window。ログが SkinningBake で止まっていたらフォーカス漏れを疑う
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-MEM/vrm-preview-load-focus-gotcha.md:137-141

### VRM のランタイムロードが URP でマゼンタ
- 症状: ロード成功してもマゼンタ
- 原因: `materialGenerator` が null（自動）で Built-in 用が選ばれる／URP MToon が無い
- 対策: `LoadPathAsync` の `materialGenerator` に URP 用を明示
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-MEM/vrm-preview-load-focus-gotcha.md:143

### UniVRM の LoadAsync の asmdef 参照（CS0012 IAwaitCaller）
- traps-catalog/unity-build.md に記載

### com.autodesk.fbx（FBX SDK）は Player で解決できない
- traps-catalog/unity-build.md に記載

### PreviewRenderUtility で書き出した画像を取り込むと NPOT が 2048² に拡縮される
- traps-catalog/unity-editor.md に記載（NPOT を None に）
