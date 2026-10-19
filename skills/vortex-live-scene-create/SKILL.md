---
name: vortex-live-scene-create
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト。SinkaiFes2026・vortex_urp など）で、ライブシーンを作る・仕込む・点検する。既存のシーンからの複製（CopyAsset・命名・ライトマップ）、System の塊（OSC・CharacterActivator・LookatManager・スイッチャー・MicController・DMX・OptiTrack）・照明・VJ・水・出力カメラの置き方と配線、シーンの YAML を Unity なしで読む点検スクリプト（構成・配線・キャラの表・問題の一覧・基準のシーンとの差）、保存とコミットまで。「〇〇用のライブシーンを作って」「シーンを立ち上げて」「△△のシーンを複製して」「新しい案件のシーンを用意して」「System を入れて配線して」「このシーンと同じ構成にして」「シーンの配線を点検して」「シーンの中身を見せて・調べて」「OSC が届かない・表情や口が動かない」「キャラが番組に写らない・真っ黒」「カメラがキャラを向かない」「キャラの出し入れが効かない」「灯体が卓に反応しない」と言われたとき、キャラを入れた後・Timeline を組んだ後にシーンを点検するときに使う。キャラを入れるのは vortex-character-setup、Timeline は vortex-timeline-setup、プロジェクトの設定は vortex-project-setup。
---

# vortex ライブシーンの作成・仕込み・点検

ライブシーンを既存のシーンから作り、System の塊と部品を置いて配線し、YAML を読む点検スクリプトで確かめてからコミットする。
2026-09-30 に vortex_urp（Animax）で複製の手順を通し、2026-10-19 に SinkaiFes2026 の全シーンと vortex_urp の 2 シーンで点検スクリプトを確かめた。

| 関係する skill | 用途 |
|---|---|
| vortex-project-setup | プロジェクトそのものの設定（レイヤー・Rendering Layer・Player Settings・パッケージ・git）。シーンの外の物 |
| vortex-character-setup | キャラを入れる（NiloToon 変換・CharacterSetup・OSC 配線・確認の映像） |
| vortex-timeline-setup | 収録データで Timeline を組む・スイッチャーの並びとカメラ記録の照合（`camrec.py order`） |
| vortex-timeline-export | 書き出し・録画（出力 Display の撮り方） |
| vortex-led-framing | LED の画角・RT の解像度 |
| unity-scene-merge | シーンを Unity の保存の雑音なしでコミットする |

System の塊の構成・フィールド名・OSC のアドレス・読み違えやすい物は `reference/system.md`。

## 道具

`S=~/.claude/skills/vortex-live-scene-create/scripts`（Unity 不要・読むだけ。Python 3 と PyYAML）

| 道具 | 用途 |
|---|---|
| `scene_audit.py dump <scene> [--root System] [--depth 2] [--chars] [--full]` | ヒエラルキー（有効/無効・レイヤー・コンポーネント・プレハブと上書きの数）。キャラの中とメッシュだけの枝はまとめる |
| `scene_audit.py wiring <scene>` | 配線の一覧: OSC のサーバーとリスナー・`_isOsc`、CharacterActivator の枠、LookatManager、スイッチャー（PGM / PRV の RT・Culling・Volume Mask、入力の並び）、DoF、MicController の枠、DMX と灯体の台数、OptiTrack、有効なカメラ、Volume、キャラ用ライト、出力の Canvas、Timeline、水、ExternalControlManager |
| `scene_audit.py chars <scene> [--tsv]` | キャラの表（有効・レイヤー・Rendering Layer・由来・表情と口の仕組み・ID・OSC の配線・Skeleton・枠・注視・マイク・scale・揺れもの・小物） |
| `scene_audit.py check <scene>... [--min warn]` | 問題を error / warn / info で。無効の System・出ないキャラで見つけたものは info に下げて「※無効」を付ける |
| `scene_audit.py summary <scene>...` | 1 シーン 1 行の表（System・カメラ系の有効、キャラの数、開く OSC のポート、枠、Use Timeline、DoF、PGM のキャラのレイヤー、OptiTrack の IP、Director、件数）。複製元の候補を並べるとき・プロジェクト CLAUDE.md の表を作るとき |
| `scene_audit.py diff <scene> --ref <基準>` | System の塊（ルート名を System に揃えて突き合わせる）・ルートの部品・配線と設定を基準と比べる |
| `scene_audit.py show <scene> <コンポーネント名,...> [--path 部分一致]` | コンポーネントの中身（プレハブの上書きを当て、参照を GameObject のパスに直す）。指摘を YAML で確かめるとき |
| `audit_selftest.py <scene>...` | 点検の規則を変えたら流す。写しに問題を 1 つずつ入れて、期待した規則で拾うか・巻き添えが何かを出す |

- シーンがプロジェクトの外にあるとき（`unity-scene-merge` の `scene_diff.py fromgit` で取り出した HEAD の版など）は `--project <Unity プロジェクト>`。
- GUID → パスの表は `%TEMP%/vortex-scene-audit/guids-*.json`。毎回フォルダをたどり、大きさか更新時刻が変わった .meta だけ読み直す。
  初回は .meta を全部読むので 1〜2 分（SinkaiFes2026 は 3.5 万件で 104 秒、vortex_urp は 49 秒）。2 回目からはシーン 1 つ 1.5〜3 秒（76 MB のシーンで 2.3 秒）。
- レイヤー名・Rendering Layer 名は `ProjectSettings/TagManager.asset` から読む。キャラ用は名前が chara で始まる物（Chara / Character / Charactor）。

## 先に読む（踏んだ罠）

- **OSC の配線はシーンの Inspector の永続リスナー**（uOscServer `onDataReceived`）。キャラ・部品を足したら、そのシーンのリスナーにも足す。
  コードで AddListener しない（他のシーンで二重に動く）。Unity MCP の update_component では永続コールを編集できない（traps-catalog/vortex.md）。
  Editor スクリプトで `UnityEditor.Events.UnityEventTools.AddPersistentListener` を呼ぶ（vortexCharacterSetup.cs と VortexCharTool が使う API）。
  キャラを消すとリスナーが None で残る（`check` の osc.listener-broken。SinkaiFes2026 の Timeline 系 2 シーンと Grand_modelSetup_Azki）。
- **同じポートの OSC サーバーを 2 つ開かない**。uOSC / OscJack は ReuseAddress を付けないので 2 つ目は bind に失敗して何も受けない。
  SinkaiFes2026 の Grand_modelSetup 系は `OSC` と `OSC_Mic` が両方 8001 だった（Grand_modelSetup は 2721ccb5 で 1 つにまとめた。_Azki・_kuni・_yamamoto は 2026-10-19 時点で両方有効のまま）。
- **DofMidiControl をプレハブのまま置くと `_switcher` が空**で、LateUpdate が毎フレーム例外（Grand_modelSetup）。置いたら Switcher・Brain・Volume を結ぶ。
  Volume のレイヤーはプレハブの 24 / 25 のまま（番組カメラの Volume Mask と対）。SinkaiFes2026 の test 系（test・test_Azuki・test_Switching*）と Timeline 系は
  7 / 8 に上書きされていて、DoF が掛からない（test_Azuki・Timeline 系は DofMidiControl 自体も無効）。
- **カメラ系（System/Camera）を無効にしたまま CharacterActivator の `_cameraSwitcher` を残すと**、開始時とキャラの出し入れで
  VirtualCameraGenerator.ApplyValues が NullReferenceException（Awake 前の vcam の Initialize を呼ぶ。`_vcamOffset` は Awake で作る）。test・Prime_modelSetup など。
  スイッチャーが有効でも、入力カメラや vcam を 1 つ無効にすると同じ例外になる。
- **CharacterActivator の Lookat Bone_hip が空の予備キャラは On/Off しない**。登場・退場のエフェクトが空だと、開始時と切り替えのたびに Error が出る。
- **CharacterActivator はキャラのルートの有効を変えない**（切り替えるのは子の Renderer・hip・secondary）。ルートを無効のまま枠に入れても出ない。
  Timeline で出すなら Activation Track でルートを有効にする（Prime_modelSetup のきまゆ）。
- **別の枠のキャラは開始時に一緒に出る**（各枠の予備 [0] を出す）。同じ演者の衣装違い（Else / ElseLirE）を別の枠に入れると、同じ ID・Skeleton で 2 体が並ぶ。
  ただし Play On Awake の Director の Character Activation トラックが受け持つ枠は、全員消えて始まる（test_Azuki の ElseLirE）。
- **LFS のポインタのままのシーン・プレハブは読めない**。`scene_audit.py` はシーンや TagManager がポインタなら止まり、プレハブ・モデル・Timeline なら scene.lfs-pointer を出す。`git lfs pull` してから流す。
- **番組カメラ（PGM / PRV）の Culling Mask にキャラのレイヤーが無いと番組に写らない**。SinkaiFes2026 の modelSetup 系の PGM / PRV は Chara が無い（Default のキャラだけ写る）。
  CharacterSetup のウィンドウは GameObject のレイヤーを設定しない。
- **ライブ用の設定のまま新しいシーンへ持ち込むとキャラが真っ黒**。キャラ用の Rendering Layer を含むライト（Character Directional Light）を一緒に置く。
- **MetaDmxReceiver の Use Timeline が On のままだと、ライブの Art-Net を灯体へ流さない**。Timeline の DMX を流すシーンだけ On（`check` は Timeline に結び付いていれば info）。
- **RT_Output には誰も書かない**（VirtualCameraSwitcher の Blit はコメントアウト）。RawImage は SwitchTexture.mat で RT A / B を混ぜる。マテリアル無しで RT_Output を映すと黒い（vortex_urp の Animax）。
- **LookatManager の `_activeTargets` は実行時の一覧**。そこに残った None や消したキャラは害が無い（Awake で作り直す）。点検するのは `_lookatTargets`。
- **複製は `AssetDatabase.CopyAsset`**。ファイルのコピーで作ると GUID が重複する。ベイク済みのライティングがあるシーンは、ライトマップのフォルダも複製して参照を張り替える。
- **Unity で保存したシーンには数千行の雑音が混ざる** → unity-scene-merge で要る塊だけコミットする。
- **本番のシーンは保存しない**（案件の決まり。SinkaiFes2026 は Grand / Prime）。検証は test 系で行い、終わったらシーンを開き直して変更を捨てる。

## 聞くこと

1. **会場と用途**: どのステージか（SinkaiFes2026 なら Grand / Prime）、何に使うシーンか（本番 / キャラの仕込み用 / 照明の仕込み用 / 検証・収録 / Timeline の再現）。
2. **複製元**: 名前で言われたら `04_Scenes/` を探して候補を示す（年違い・`_kuni` などの個人用の派生があるので確かめる）。
   決まらなければ、候補を `summary` で並べ、`diff --ref` で System の揃い具合を見て、問題の少なさで選ぶ。
3. **出力**: 番組を出す Display（Output-Canvas）、操作画面（SwitcherUI-Canvas）、LED・プレビューの出力カメラと RT。
4. **受信**: OptiTrack の ServerAddress / LocalAddress（その日の PC の IP）、DMX（Art-Net の universe・卓の台数・Use Timeline）、OSC のポート（既定 8001・パッドは 9100）。
5. **ライブか Timeline か**: ライブなら Use Timeline Off・OSC の配線が要る。Timeline の再現なら Director と Use Timeline On（vortex-timeline-setup）。
6. **日付と案件名**（vortex_urp の命名のとき）: `YYMMDD`、複数日は `260415-0417` のように範囲。案件名は既存に合わせた英字。

## 命名とフォルダ（既存に合わせる）

| 案件 | シーン | 例 |
|---|---|---|
| vortex_urp | `Assets/04_Scenes/<YYMMDD>_<案件名>.unity` | `261007_Animax`・`260922_ProBlueFes` |
| SinkaiFes2026 | `Assets/04_Scenes/ShinkaiFes2026_<Grand / Prime>[_<用途>].unity` と検証用の `test_*` | `ShinkaiFes2026_Grand_modelSetup`・`_LightSetupScene`・`ShinkaiFes2026_Timeline Yamashita`・`test_Azuki` |

vortex_urp のキャラは `Assets/02_vortex_character/<YYMMDD>_<案件名>/<キャラ名ローマ字>/`、案件の素材は `Assets/03_vortex_live/<YYMMDD>_<案件名>/`（要るときに作る）。

シーンの種類と中身（実例 SinkaiFes2026。案件の値はプロジェクトの CLAUDE.md の「シーン構成」）:

| 種類 | 中身 |
|---|---|
| 本番（`_Grand` / `_Prime`） | ステージの環境だけ（System の塊は無い） |
| キャラの仕込み用（`*_modelSetup*`） | キャラの置き場。System は無効か一部だけ有効。キャラを取り出す元 |
| 照明の仕込み用（`*_LightSetupScene*`） | 灯体と照明だけ |
| 検証・収録（`test*`） | System が有効。ビルドや Timeline の元 |

## 手順

### 0. 前提

- Unity の接続先が今のプロジェクトか（`Library/ClaudeCodeMCP/endpoint.json` の processId とウィンドウタイトル）。
- プロジェクトの CLAUDE.md の「シーン構成」を読む（どのシーンで何を有効にしているか・止めるもの）。
- 複製元に `scene_audit.py check` を掛け、元からある問題を控える（新しいシーンで増えた物と見分けるため）。

### 1. 複製する

1. ベイク済みのライティングがあるかを見る（`grep "m_LightingDataAsset" <複製元>.unity`）。`{fileID: 0}` なら単純な複製でよい。
   参照があるなら、ライトマップのフォルダも複製し、参照の張り替えが要る（ユーザーに確認）。
2. `AssetDatabase.CopyAsset` で複製する（MCP の `invoke_method`、`typeName=UnityEditor.AssetDatabase`、`methodName=CopyAsset`）。
   ```
   CopyAsset("Assets/04_Scenes/<複製元>.unity", "Assets/04_Scenes/<新しい名前>.unity")
   ```
   `.meta` の guid が複製元と違うこと、中身が同一なこと（`cmp`）を確かめる。
3. 新しいシーンを開く（MCP `open_scene`）。複製元のシーンは保存しない。

### 2. 要らない物を外す

- 前の案件のキャラ（vortex-character-setup の `VortexCharTool.Inspect` で外からの参照を控え、`RemoveCharacters` で登録ごと消す）。
- 前の案件の Timeline の Director、使わない出力カメラ、案件だけの演出。
- 消したら `check` で osc.listener-broken・act.target-none・lookat.none（消した物の残り）が出ていないかを見る。

### 3. 部品を置く・配線する

置き場と結ぶフィールドは `reference/system.md` の表。仕上がりの目安は、同じ会場・用途の基準のシーンとの `diff` が「意図した差だけ」になること。

| 部品 | 確かめること |
|---|---|
| System の塊 | 1 つだけ。OSC のサーバーは 1 ポート 1 つ。`_isOsc` と OSC のリスナーが対になっている |
| カメラ系 | スイッチャーの Brain・RT A / B・入力の並び（Timeline で再生するなら記録と照合）。PGM / PRV の Culling Mask にキャラのレイヤー、Volume Mask に DoF の Volume のレイヤー |
| DofMidiControl | Switcher・Brain・Volume を結ぶ。OSC のリスナーに `OnReceived` |
| 照明 | LightControler の Use Timeline（ライブは Off）、OnMetaDmx → FixtureController。キャラ用ライト（Rendering Layer がキャラ用） |
| 水・VJ・ステージ | Crest の WaterRenderer の Camera（空なら Camera.main）、VJ の入力（AVPro / HAP） |
| 出力 | Output-Canvas の Display とマテリアル、LED の出力カメラの RT と Canvas の Display |
| OptiTrack | ServerAddress / LocalAddress を聞いた値に |

キャラを入れるのは vortex-character-setup（`VortexCharTool.SetupCharacterEx` が CharacterActivator・LookatManager の登録と OSC の配線までする。レイヤー・Rendering Layer も渡せる）。

### 4. 点検する（ここまでやって「できた」）

1. `python $S/scene_audit.py check <新しいシーン>` で error と warn が 0、または残す理由を言えること。info は目を通す。
2. `python $S/scene_audit.py diff <新しいシーン> --ref <基準のシーン>` で、差が意図した物だけであること。
3. Play で Console に新しいエラーが出ないこと（MCP `get_console_logs`）。OSC・DMX は実際に送って確かめる（卓・送信アプリ、`~/.claude/tools/artnet-send.py`）。

`check` の主な規則（`vortex_checks.py`）:

重さは、無効の物で見つけたら info に下がる（「※無効」）。キャラの規則は「Play で出うるキャラ」だけ warn で、出ないキャラは info
（出うる = シーンで有効 / Activation Track が無効なルートを有効にする / 有効な CharacterActivator の枠で出せる。
CharacterActivator はルートの有効を変えないので、ルートが無効なキャラは、無効なのが Lookat Bone_hip そのものだけのときに限って出せる）。

| 規則 | 重さ | 中身 |
|---|---|---|
| osc.port-dup | error | 同じポートの OSC サーバーが 2 つ以上開く |
| osc.listener-broken / osc.listener-off / osc.listener-dup | warn | リスナーの先が None / Off / 同じ物が 2 回 |
| osc.unwired | warn | 表情・口パクを OSC で受けるのに、リスナーに入っていない（FacialManager は機器が Osc_* のときだけ） |
| osc.unwired-server-off / osc.server-off | warn | 配線はあるが、配線先の uOscServer が開かない（無効・autoStart Off） |
| osc.isosc-unwired | warn | `_isOsc` が On なのにリスナーに無い |
| act.target-none / act.hip-none / act.effect-none / act.hip-outside / act.slot-empty / act.target-dup | warn | CharacterActivator の枠の None・Bone_hip の空・エフェクトの空・hip が別の物・空の枠・同じキャラが 2 か所 |
| act.switcher-inactive / act.vcam-inactive | warn | `_cameraSwitcher` が無効の GameObject / 入力カメラ・vcam が無効か None（どちらも開始時に vcam の NRE） |
| act.unregistered | warn | 有効なのに枠に入っていないキャラ |
| lookat.none / lookat.unregistered / lookat.hip-mismatch / lookat.inactive / lookat.dup | warn / error | 注視先の空・キャラの登録漏れ・出し入れの hip と注視先がずれる・LookatManager が無効 / 2 つ |
| sw.input-none / sw.input-few / sw.brain-none / sw.preview-none | error | スイッチャーの Start が例外になる設定 |
| sw.rt-none / sw.rt-mismatch | warn | RT A / B が空（プレビューが出ない）/ PGM・PRV のカメラの RT と合わない |
| sw.cull-chara | warn | 番組カメラにキャラのレイヤーが無い |
| sw.output-unwritten | warn | 誰も書かない RT_Output をそのまま映している |
| dof.switcher-none | error | DofMidiControl の `_switcher` が空（毎フレーム例外） |
| dof.volume-none / dof.brain-none | warn | Volume が片方でも空（両方の DoF を取らない）/ Brain が空（ピントの距離が 0） |
| dof.vol-mask | warn | DoF の Volume のレイヤーがカメラの Volume Mask に無い |
| light.chara-none | warn | キャラ用の Rendering Layer を含むライトが無い |
| char.layer / char.rl | warn | キャラの Renderer が Default レイヤーのまま / Rendering Layer にキャラ用が無い |
| char.id-dup ほか *-dup | warn | 開始時に一緒に見えるキャラで ID・Skeleton・パッドのラベルが同じ（一緒に見えなければ info）。数えるのは GameObject |
| char.skeleton-other | warn | OptiTrack の Skeleton 名が別のキャラの名前 |
| char.opti-client / char.opti-client-off / char.opti-avatar | warn | OptiTrack のクライアントが無い・無効 / Avatar が空 |
| char.vfc-label / char.vfc-no-receiver / char.lipsync-proxy | warn | パッドのラベルが空・受信側が無い / 口パクの proxy が空 |
| mic.grip-hand / mic.auto-missing / mic.animator-none / mic.mics-none | warn | 握りのプリセットの手が逆・Auto の口とマイクが空・Animator が全部空・マイクに None |
| dmx.use-timeline / dmx.no-fixture / dmx.dup | warn | Use Timeline が On で Timeline にも結び付いていない / 灯体へ流さない / 2 つ目は bind に失敗 |
| tl.asset-missing / tl.multi-awake | error / warn | Director の Timeline が無い（無効でも warn）/ Play On Awake が 2 つ以上 |
| scene.missing-script / scene.missing-prefab / scene.missing-prefab-nested | warn / error / warn | Missing Script / シーンの Missing Prefab / プレハブの中の Missing Prefab |
| scene.lfs-pointer | error | 元のプレハブ・モデル・Timeline・握りのプリセットが LFS のポインタのまま（その分の点検が飛ぶ。シーンや TagManager がポインタなら止まる） |

### 5. 保存とコミット

- MCP `save_scene`。本番のシーンは保存しない。
- unity-scene-merge で要る塊だけをコミットする（`scene_diff.py take`）。新しいシーンなら `.unity` と `.meta` だけをステージする。
- ブランチは案件の決まり（例 `mao/Reality-Animax2026`）。`git branch --show-current` で確かめてからコミットする。push はユーザーの指示があるときだけ。

## Unity MCP での操作の注意

- MCP を呼ぶ直前に `focus_window` で Unity を前面に出す（背面だと timeout する）。**timeout しても Unity 側では後から実行される**ので、同じ操作を送り直さない。結果は `dump_scene_hierarchy` や `scene_audit.py` で確かめる。
- Unity のヒエラルキーをその場で見るなら `dump_scene_hierarchy`、保存済みのシーンの配線を見るなら `scene_audit.py`（Unity を開かずに全シーンを比べられる）。
- `scene_audit.py` が読むのは保存済みのファイル。Unity で変えた後は `save_scene` してから流す（本番のシーンは保存しないので、写しを作って読む）。
- 他のシーンは開いたまま変更しない。複製直後のシーンでカメラ系が無効のことがある（映像を録るなら vortex-timeline-export）。

## 報告に入れるもの

- 作ったシーンのパスと複製元、`.meta` の guid が違うこと。
- `check` の件数（error / warn / info）と、残した warn の理由。`diff --ref` の基準と、残った差の説明。
- 配線した物（OSC のリスナー・枠・注視先・スイッチャー・DMX・OptiTrack の IP）と、Play で確かめたこと・確かめていないこと。
- コミットしたもの・していないもの（本番のシーンを触っていないこと）。
