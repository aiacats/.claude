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

### 複数人の収録モーションを Humanoid で並べると、1 人だけ立ち位置がずれる
- 症状: 同じ収録の 2 人を Timeline に並べると、片方だけ立ち位置・向きが参考映像とずれる（数十 cm〜1m 以上）。親にもトラックにもオフセットは無い
- 原因: Humanoid のクリップの既定（Root Transform Position XZ / Y / Rotation の Based Upon が Original でない）は、ルートを「1 フレーム目からの差分」で扱う。1 フレーム目が原点・正面でない人（舞台奥や斜め向きから始まる人）だけ、移動が回され・ずらされる
- 対策: ModelImporterClipAnimation の keepOriginalOrientation / keepOriginalPositionXZ / keepOriginalPositionY を true にして取り込み直す（収録の座標のまま並ぶ）。確かめるのは腰のワールド位置と RootT の値の一致
- 実例: 2026-10-12 SinkaiFes2026（Else の t004、1500 秒で 1.3m ずれ）
- 副作用: Rotation を Original にすると、キャラのルートが収録時の向きに合わせて回る（Else は平均 37°/秒・p95 96°/秒。腰の 30°/秒より速い。Apply Root Motion を Off にしても Timeline がルートを動かす）。
  VRMSpringBone の Center がルートの子（BasePosition など）だと、基準ごと振り回されて揺れもの（スカート）が横へ流れる。
  → Center を空にする（ワールド基準。振れの p95 が 32° → 17°）。共有プレハブは触らず、シーン側の上書きで入れた（2026-10-12 SinkaiFes2026）
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-12 07:55・18:10・18:40

### FBX の再取り込みで Unity が ReduceKeyframes で落ち、起動し直しても同じ取り込みで落ちる
- 症状: 取り込み設定を変えて再取り込みすると、クラッシュのスタックが ReduceKeyframes<Quaternionf>（ReduceKeyframesJobified）で落ちる。起動すると同じ取り込みが走ってまた落ちる
- 原因: キーフレーム削減（アニメーションの圧縮）の job の不具合。長い（25 分級）Humanoid のクリップで起きた
- 対策: Unity を止めたまま、その FBX の .meta の animationCompression を 0（Off）にしてから起動する。起動後は「importer crashed on it last time」で空のアセットになっているので、ImportAsset(ForceUpdate) で取り込み直す
- 実例: 2026-10-12 SinkaiFes2026（261002_Shinkai_Else_t004.fbx）
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-12 07:55

### 収録モーションのキャラが、全編を通して首を上げたまま・横に傾けたまま・内股のままになる
- 症状: Humanoid で当てたキャラが、演者は前を見ている場面でも顎を上げている／頭が片側へ傾いている／膝が内へ入る（内股）。マッスルの平均が他の演者より 0.3〜0.5 大きい。カーブを読んでも「データの通り」に見える。
- 原因: 収録モーションの FBX の骨格の基準の姿勢（Avatar の humanDescription.skeleton）が、キャラの基準の姿勢とずれている（首・頭が前や横へ倒れている、脚が外へ開きつま先が外を向いている）。マッスルは基準の姿勢からの差なので、演者がまっすぐ立つとその分だけ反対へ動いたと記録され、基準がまっすぐなキャラにずれがそのまま出る。
- 対策: FBX の基準の姿勢の背骨・胸・首・頭（必要なら太もも・すね・つま先の向き）を、当てるキャラの基準の姿勢と同じ傾きにして `ModelImporter.humanDescription` に書き、取り込み直す。
  - 骨の並びの違い（キャラにだけ UpperChest がある）や、Unity が体の向き（RootQ）を腰・胸の位置から決めることで数度のずれが残る → 演者（FBX 自身の骨格で再生）とキャラの再生中の平均の差を補正として足し、2〜3 回詰める。つま先の向きは補正の 2.8 倍動いた（比で割って足す）。
  - 胸を回すと子の腕も回り、腕・指のマッスルの軸が変わる（指の開きが最大 1.9 動いた）→ 胴を回した後で肩の世界の向きを元に戻す。胸のねじれは上腕でなく鎖骨の根元で測る。
  - 回す軸は肩（胴・首）の左右から取る。腰の左右だと胴のねじれの分だけ首に左右の傾きが混ざった。脚・腕の角度は下を向くと ±180° をまたぐので、真下からの角度か向きの成分で比べる。
  - 確かめ方: キャラと演者の角度の平均を比べる。Foot IK On なら足の IK の目標（RootT + RootQ × FootT）が動いていないか、Off なら足の高さの変化を見る。最後に収録時のプレビュー映像と並べる。
  - 親指も同じ: 収録の骨格は基準の姿勢で親指が指と同じ向き・手のひらの面に寝ていることが多く、キャラは斜めに開いている → 全編で親指が開き、拳から親指だけ横へ突き出す。
    付け根だけ回すと収録の骨格の中の節の曲がりが残るので、3 節それぞれの向きを手の枠（手首・中指・人差し指・小指の付け根の位置）でキャラに合わせ、残る一定の差を補正で詰める。
    合わせると付け根のマッスルが ±1 を大きく超える（−3 まで）が、Play 中の Timeline でも切り詰められずにそのまま効く。
  - マイクの握りのプリセット（MicController の Grip、Override）が全編効いている手は、クリップの指が見えないので直さなくてよい。先にシーンで何が指を決めているかを確かめる。
- 道具: skill vortex-mocap-fix の templates/Editor/BodyRestFix.cs（Run / Play / ExtractClip / WorldDiff / GoalDiff、親指は AlignThumbChain / ThumbSeries / TransplantCurves）。
- 実例: 2026-10-15 SinkaiFes2026 MZM（Anjo・Kosaka。基準の姿勢の首が −28°、Anjo は頭が横に 20°）・エルセ（脚が外へ 4〜5°・つま先が外へ 10° → 全編で内股。親指が 11° 起きる）・AZKi（左の親指が演者より 36° 開く → 3 節合わせで ±0.5°）。直して演者と ±0.8° 以内。
- 出典: SinkaiFes2026 claudeLog 2026-10-15

### キーの削減を切って取り込んだ長い FBX のクリップを .anim にすると「Object size is too large」
- 症状: FBX の中のクリップを `Object.Instantiate` → `AssetDatabase.CreateAsset` で .anim にすると、`Error writing object ... Object size is too large` → `Unable to write objects to temporary file` で作れない（膝直しのような複製を作る道具も同じ所で失敗する）。
- 原因: 長い収録（19 分・130 カーブ）を Animation Compression = Off で取り込んでいるため、毎フレームのキー（1,700 万個）がそのまま 1 つのオブジェクトに載り、書き出しの上限を超える。削減 On で取り込むと長い FBX は削減の処理で Unity が落ちる（同じカタログの別項）。
- 対策: エディタのカーブ（`AnimationUtility.GetEditorCurve`）を許容誤差で間引いてから `SetEditorCurves` で新しい .anim に書く（マッスル 0.002・RootT 0.5mm で 1,772 万 → 164 万キー、735MB）。skill vortex-mocap-fix の BodyRestFix の `ExtractClip(fbx, out, thin: true)`（既存の .anim に入れ直すなら `RebuildCurves`）。膝直しなどはその .anim に掛ける。
  **Root と IK の目標（RootT/Q・*FootT/Q）をマッスルと同じ許容で間引くと足の接地がガタつく**（次の項）。今の ExtractClip はそこだけ細かくする（ReduceEps）。
- 実例: 2026-10-14 SinkaiFes2026（エルセ）/ 2026-10-15 SinkaiFes2026（Kimayu t003）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-15 10:15

### キーを間引いて作った .anim で、Foot IK On の足の接地がガタつく（1 コマで数 mm 跳ねる）
- 症状: 収録モーションの .anim（膝直し・腕の移植などで作り直したもの）を Timeline で流すと、床に着いている足やつま先が細かくガタつく。元の FBX のクリップでは起きない。膝も時々跳ねる。
- 原因 1: Root と足の IK の目標（RootT/RootQ・LeftFootT/Q・RightFootT/Q）をマッスルと同じ許容（0.002）で間引いた。足の位置 = RootT + RootQ × FootT なので、RootQ の 0.002（約 0.2°）が腰から 1 m 下の足で約 4 mm になり、カーブごとに別々の折れ線の誤差が足元で揺れになる（AZKi・きまゆで足の目標が平均 2.5 mm・最大 8 mm ずれ、接地中の 1 コマ 2 mm 超の動きが元の 6〜100 倍）。
- 原因 2: 「毎フレームのキーを直線で結ぶ」間引き（ReduceLinear）を、圧縮して取り込んだ FBX（キーがまばらで、間の形を接線で持つ）に掛けた。残したキーの間が直線になり形が崩れる（AZKi で足の目標が最大 84 mm ずれた）。キーの値だけで誤差を確かめるので、間引きの検査では見つからない。
- 原因 3（Foot IK Off のキャラ）: 足の位置は股関節からのマッスルの積み重ねで決まるので、脚のマッスル（太もも・すね・足首・つま先）の 0.002（太ももで約 0.15°）も足首で 2〜3 mm の折れ線になる（エルセ。Root を直しただけでは 4 割しか減らなかった）。
- 対策: FBX を Animation Compression = Off で取り込み直し（毎フレームのキー）、Root と IK の目標は細かい許容で間引く（RootT・*FootT 1e-4、RootQ 5e-5、*FootQ 5e-4。足の目標の誤差 最大 0.3 mm、揺れは元と同じ）。Foot IK Off なら脚のマッスル 16 本も 1e-4。ほかのマッスルは 0.002 のままでよい。移植や直しを掛けたカーブ以外を入れ直せば、作り直しの手順をやり直さずに済む。膝直しを掛けたクリップなら、入れ直す膝のカーブは間引く前に 1 以下に抑える。
  切り分け: 元の FBX のクリップを Play 中だけ Timeline に差し替えて同じ数を数えると、元のデータの揺れ（下限）が分かる。
  確かめ方: 足の目標（RootT + RootQ × FootT）を 1/60 秒ごとに元の FBX と比べ、接地中（速さ 0.15 m/s 未満）の 2 階差分が 2 mm を超えるコマを数える。最後は Timeline を 1 コマずつ Evaluate して足首・つま先の骨で同じものを数える。
  道具: skill vortex-mocap-fix（BodyRestFix の ReduceEps・IsDense・RebuildCurves。まばらなカーブには掛けずに断る。走査は MotionScan と leg_scan.py / goal_jitter.py）。
- 実例: 2026-10-15 SinkaiFes2026（AZKi: 足首の急な動き 4,800 → 60 回・膝の跳ね 11 → 0 回。エルセ・きまゆも同じ間引きで 6〜100 倍。MZM は間引いていないので無事）
- 自動検出: 不可（クリップの Root・足のカーブのキー数が元の数 % なら疑う）
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-15 16:00
