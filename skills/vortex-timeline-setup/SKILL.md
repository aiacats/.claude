---
name: vortex-timeline-setup
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、収録データ（モーション FBX・表情・2Mix の音・ArtNet の DMX・カメラ記録・VJ 映像）から、収録時の番組を再現する Timeline を組む・直す。素材の集め方（Drive・Dropbox の共有フォルダ）、トラックの置き方、OBS プレビュー・番組映像（HyperDeck）との時刻合わせ（音・口・DMX・カメラの切り替え）、スイッチャーの並びとレールのずれ、マイク・キャラの登場・VJ・明暗転、確かめ方までを扱う。「この収録データで Timeline を組んで」「〇〇の Timeline を作って」「音・表情・カメラ・DMX がずれている」「カメラスイッチングが黒い・崩れた」「ループで流せるようにして」「間奏で口がパクパクする」「カメラがリニア・キャラに張り付いて回る」「キャラが画面の外に外れる・カメラが止まる」「キャラ用ライトを暗転から明点させて」と言われたら使う。モーションの見え方（首・内股・親指・膝の跳ね・足のガタつき）は vortex-mocap-fix、書き出しは vortex-timeline-export。
---

# vortex Timeline 仕込み（収録ライブの再現）

収録時に見えていた画（OBS のプレビュー・切り替えた番組映像）と同じ見え方を、Timeline で再現する。
2026-09〜10 の SinkaiFes2026 で固めた（AZKi・春猿火・みなとん・りのん・MZM・きまゆ）。

| 関係する skill | 用途 |
|---|---|
| vortex-mocap-fix | モーション FBX の取り込み・基準の姿勢・膝・足の接地・.anim の作り直し |
| unity-scene-merge | シーンを Unity の保存の雑音なしでコミットする・LFS のシーンのマージ |
| vortex-timeline-export | 書き出し（OBS / Recorder・Export Batch・Solo） |
| unity-view-recording | キャラの見え方を決まった角度で録る |

## 道具

`S=~/.claude/skills/vortex-timeline-setup/scripts`（どれも Unity 不要）

| 道具 | 用途 |
|---|---|
| `tl_dump.py <playable>... --extra <サブモジュール>` | トラック（グループ・種類・ミュート）とクリップ（start・ClipIn・timeScale・参照アセット・Foot IK・Remove Start Offset）の一覧。今の置き方を読む |
| `sync.py audio / mouth / motion / dmx` | 相互相関で時刻のずれを測る（reference/sync.md） |
| `camrec.py names / order / segments / match` | カメラ記録の読み出し・スイッチャーの並びの照合・番組映像のカットとの照合（reference/camera.md） |
| `dbx_shared.py list / get / url` | Dropbox の共有フォルダの一覧・取得・単体 URL（区間読み用） |
| `inspect_dmx.py <.dmx>` | DMX の中身の検分（reference/dmx.md） |
| `dmx_light.py switch / ramp / luma` | 明点・暗転の時刻とフェードの長さ（DMX の一斉の立ち上がり・プレビューの床の明るさ。reference/dmx.md） |
| `facial_gate.py scan / gate` | 歌声が無いのに口が動く区間を探す・その間の口を閉じた複製を作る（reference/facial.md） |
| `camfollow.py lag / fit / offframe / aim / keys` | 番組カメラの追従の遅れ・キャラが画面の外のショット（記録の止まり）・Override の回転量・記録のキーの密度（reference/camera.md） |
| `camera_match/` | 番組映像の絵とレールのずれを合わせる一式（YOLO。reference/camera.md） |

雛形（`~/.claude/skills/vortex-timeline-setup/templates`。案件の `Assets/_TempVerify/` へ写し、MCP の `invoke_method` で呼ぶ。終わったら消す）:

| 雛形 | 置き場 | 用途 |
|---|---|---|
| `ShotRunner.cs` | `_TempVerify/`（Play 中） | Timeline の指定時刻で番組カメラの画を撮る（時刻のまま 3 コマ回してから撮る）。`State()` が `done` か `error: ...` になるまで待つ |
| `Editor/CamFollowProbe.cs` | `_TempVerify/Editor/` | 追従の CSV（`Measure`、Play 中）・区間だけ向きをずらす Override（`SetRotationOverride`、Edit で呼んでシーンを保存）・記録データの付け替え・注視先と Aim Damping の一覧 |

写す前に、同じクラス名が案件に無いかを grep する（`Assets/_TempVerify`・`_SkillVerify` に古い写しが残っていると CS0101 でコンパイルが止まる）。

## 先に読む（踏んだ罠）

- **テイク番号・名前はシステムごとにずれる**。モーション T002 = DMX t003 = 表情 `…151927` のようにずれた。表情 `T002_KImayu_…` の中身は t003 だった。
  尺（2〜3 秒以内）と相互相関（区間ごとに同じずれが出るか）で組を決める。決められなければユーザーに聞く。
- **時刻の基準はプレビュー**（ユーザーの判断の基準は「収録時に見えていた姿」）。直したら同じ時刻のプレビューのコマと並べて見せる。
  プレビューは固定の引きの画で、カメラの切り替えは番組映像（HyperDeck の mov）にしか無い。
- **表情の口は音より遅れて記録される**（AZKi 0.56 秒）→ ClipIn で前へ。
- **カメラの切り替えは activeId ではなく fade に出る**。番組のカットは記録より約 0.1 秒早かった → カメラのクリップを前へ。
- **スイッチャーの並びが記録と違う番号は真っ黒**になる（原点・画角 0。エラーは出ない）。`camrec.py order` で全組を照合する。
  組ごとに並びが違うと、1 つのシーンでは片方が黒くなる（MZM とみなとん。reference/camera.md）。
- **Override Track は組ごとに合わせる**（AZKi の値は他の組で悪くなった）。レールのずれはカメラごとに 1 本・全尺 1 クリップ・元のトラックより下に置く。
  同じカメラの Override を 2 本のトラックに置くと、重なる区間では後の 1 本だけが効く（区間だけの向きの直しには、そのカメラのレール・FoV も入れる。reference/camera.md）。
- **カメラ記録の再生は、収録時の追従をそのまま写す**（追従を計算し直さない）。「リニア感が強い・張り付いて回る」は収録時の Aim Damping 0 のカメラ。
  再生側で直すかはユーザーに聞く（2026-10-16 は作って戻した。reference/camera.md）。
- **注視先の番号のキャラがいないカメラは、向きが止まる**（収録時もそのまま止まって記録される）。AZKi の 14 番は注視先が 4 番で、AZKi 一人の間は不在
  → 19:37 の 2.6 秒、AZKi が画面の外。`camfollow.py offframe` で探し、区間だけ向きをずらす Override で直す（Edit モードで置いてシーンを保存。reference/camera.md）。
- **画を撮るときは、時刻を動かしてから数コマ回す**。`time = t; Evaluate(); Render()` を続けると、キャラだけ前に撮った時刻のポーズで写る
  （構図の補正量を 2 回誤った。2026-10-16）→ 雛形 `ShotRunner.cs`。
- **間奏で口がパクパクする**のは、表情の記録の口が歌声の無い間も小さく動いているから（AZKi 0.06〜0.28）→ `facial_gate.py`（reference/facial.md）。
- **2 人以上のモーションは Remove Start Offset を Off**（On だと 2 人が中央で重なる。MZM）。立ち位置は FBX の取り込みの keepOriginal*（vortex-mocap-fix）。
- **鳴らない原因がミュートのことがある**: グループのミュート（`tl_dump` で `[Facial MUTED]`）、MetaDmxReceiver の Use Timeline Off、
  MicController 自体が無効（m_Enabled 0。Yamashita）、マイクの枠の Is Enable、握りのプリセットが手と逆（左手用を右手に当てると黙って効かない）。
- **.playable.meta の GUID が作り直されると、シーンから Timeline の参照が切れる**（2026-10-14、作業ツリーで 4 組とも）。git のコミット時の GUID に戻す。
- **検証で触った Timeline の設定（Foot IK など）を戻し忘れる**（2026-10-14、比較で False にしたまま残った）。アセットを書き換える確認は、終わったら `tl_dump` で元と比べる。
- **Unity で保存したシーンには数千行の雑音が混ざる** → unity-scene-merge で要る塊だけコミットする。
- **Play を抜けた直後に Unity が落ちることがある**（Unity 6.3・DX11、`ReleaseD3D11Buffer`）。Play の前に保存を済ませ、起動し直したときの Recovering Scene Backups は検証だけなら No。
  Unity Bug Reporter がダイアログに重なっていたら先に閉じる（No が Bug Reporter に落ちた）。
- **Dropbox の共有フォルダは全体を落とさない**（数百 GB）。`dbx_shared.py list` で中身を見て要る物だけ取る。区間だけ見るなら `url` で単体の URL を得て ffmpeg の `-ss`。
  サブパスは先頭の `/` 無しで渡す（Git Bash が `/OBS` を `C:/Program Files/Git/OBS` に書き換える）。

## 手順

### 0. 前提

- 仕込み先のシーン（指定が無ければ今開いているシーン）。MCP の接続先が今のプロジェクトか（`Library/ClaudeCodeMCP/endpoint.json` の processId とウィンドウタイトル）。
- プロジェクト CLAUDE.md の「シーン構成」を読む（キャラのパス・Director・受信系・止めるもの）。
- 収録モーションで確かめるときは、キャラの OptitrackSkeletonAnimator を Play 中だけ無効にする（受信が無いとポーズを上書きする）。

### 1. 素材を集める

| 素材 | ありか | 置き場（例） |
|---|---|---|
| モーション FBX | Drive の共有リンク | `Assets/RecordedData/`（取り込みは vortex-mocap-fix） |
| 表情 `animation_<名前>_<日時>.asset` | 収録時に案件の中にできている | `Assets/RecordedData/` |
| 2Mix（L/R の wav）・Vo | Dropbox の収録フォルダ `SoundData/` | `Assets/RecordedData/` |
| DMX `Art-Net N - <日付>_<組>_tNNN.dmx` | 収録フォルダ | `Assets/RecordedData/` |
| カメラ記録 `<名前>_camera_<日時>.anim` | 収録時に案件の中にできている | `Assets/RecordedData/` |
| OBS プレビュー（mp4） | Dropbox の収録フォルダ `OBS/` | リポジトリの外（例 `SinkaiFes2026_Media/preview/`） |
| 番組映像（HyperDeck の mov、57〜246 GB） | Dropbox の `HyperDeck_*/` | 落とさない。URL で区間だけ読む |
| VJ 映像 | Drive（ProRes） | リポジトリの外。HAP にして読む（下のトラック表） |

- Drive は `get_file_metadata` で大きさを見てから `rclone backend copyid <remote>: <fileId> <dir>/`（404 なら別の remote）。`download_file_content` は使わない（base64 でコンテキストが壊れる）。
- 手元に既にあるか先に探す。プロジェクトのメモリに参考映像の置き場があれば、そこを引く。

### 2. Timeline を組む

置き場は既存の `.playable` と同じフォルダ、名前は既存に揃える（例 `Kimayu-Timeline`）。ルートに PlayableDirector（Play On Awake・Loop）。
1 つのシーンに複数の組の Director を置くなら、使う組だけ有効にする（書き出しは Solo）。

| トラック | バインド先 | 要点 |
|---|---|---|
| Animation Track（Motion） | キャラの Animator（Humanoid） | 0 秒・ClipIn 0 が基本。Foot IK は On（膝のマッスルを 1 以下にしたクリップで）。Remove Start Offset は 2 人以上なら Off |
| VRM Blend Shape Track（Facial） | キャラの VRMBlendShapeProxy | 口の遅れを ClipIn で（reference/facial.md） |
| Audio Track | （なし） | 2Mix。L/R を結合したステレオ 1 本か、L/R を同じ位置に 2 本 |
| Dmx Track | MetaDmxReceiver（LightControler） | Use Timeline を On（reference/dmx.md） |
| Camera Record Track | `System_GrandStage/Camera/VirtualCamera`（VirtualCameraSwitcher） | `System_GrandStage/Camera` が無効のシーンがある。ClipIn・timeScale は番組映像のカットで（reference/camera.md） |
| Camera Record Override Track × カメラ数 | 同上 | レールのずれ: カメラごとに 1 本・全尺 1 クリップ・元のトラックより下。記録の向きが止まった所: 区間だけのクリップを別のトラック `(aim)` に（reference/camera.md） |
| Mic Track | MicController | クリップの `_targetIndex` が MicController の targets の番号。キャラごとに枠（Auto・握りのプリセット・口の位置 MicMouth） |
| Character Activation Track | CharacterActivator | 途中から出るキャラ（AZKi のエルセは 1309.4 秒から。登場のエフェクトの 1.6 秒前） |
| Activation Track | キャラのルート | シーンでは無効のままのキャラを Timeline の間だけ有効に（きまゆ） |
| Control Track（VJ） | HapPlayer（KlakHap） | VJ 動画は HAP（`ffmpeg -map 0:v:0 -an -dn -map_metadata -1 -c:v hap -format hap -chunks 4`）。位置は VJ の音と 2Mix の相関。区間の外は VJ 面が黒。DX11 前提。他の PC には動画ファイルが要る |
| Light Dimmer Track | LightEmissionDimmerControl | DMX が無いときの明暗転（reference/dmx.md） |
| Light Intensity Track | Light（キャラ用ライトなど） | DMX を流したまま、ライトの強さに倍率を掛けて暗転・明点を重ねる（DMX は色だけを書くので取り合わない。reference/dmx.md）。ライトを Animation Track で動かさない（書き出しの Solo がライトの置き場ごと無効にする） |

アセットのフィールドが private のトラック（記録データの参照など）は、一時 Editor スクリプトで `SerializedObject` 経由で入れ、`clip.duration` を記録の長さに合わせる（既定のクリップは 1 秒）。
置いたら `tl_dump.py` で、start・ClipIn・参照・ミュートを一覧して確かめる。

### 3. 時刻を合わせる

reference/sync.md。音 → 表情 → DMX → カメラの順。どれも「プレビュー（または番組映像）の時刻 → Timeline の時刻」を音で決めてから測る。

### 4. カメラを合わせる

reference/camera.md。`camrec.py order`（並び）→ `match`（切り替えのタイミング）→ 必要なら Override（レールのずれ）。

### 5. 確かめる（ここまでやって「できた」）

- Play で Director を進め、要所の時刻で見る。Director の time は `invoke_method`（PlayableDirector の `set_time` → `Evaluate`、止めるなら `Pause`）。
- プレビューの同じ時刻のコマと並べる（立ち位置・入れ替わり・下半身・マイクの腕・目閉じ・照明）。プレビュー側は MicController がマイクの腕を口元へ上げている。
- カメラは SW の画面（Display 3）を撮る。番号の区間（`camrec.py segments`）から時刻を選び、番組カメラの位置・画角が 0 でないこと。
  番組映像と並べるコマは `ShotRunner.cs` で撮る。全編でキャラが画面の外のショットが無いかは `camfollow.py offframe`（CSV は CamFollowProbe.Measure。60 fps で 1020 秒ぶんが約 52 秒）。
- 表情は、歌声の無い間に口が動いていないか `facial_gate.py scan`（歌声は Demucs で分ける。reference/facial.md）。
- 動きの破綻（膝の跳ね・足のガタつき）は vortex-mocap-fix の走査で数える。
- Console のエラーが、以前からあるもの以外に増えていないこと。

### 6. コミット

- シーンは unity-scene-merge で要る塊だけ。.playable・.anim・.asset・シーンは LFS。
- push の仕方・どのブランチに載せるかは案件の決まり（プロジェクトの CLAUDE.md・メモリ）に従う。push はユーザーの指示があるときだけ。

## 報告に入れるもの

- 使った素材のパスと、組の決め方の根拠（尺・相関）。
- 各クリップの置き方（start・ClipIn・timeScale）と、その根拠になった測定値（相関・窓ごとのずれ・ppm）。
- 確かめた時刻と、プレビューとの比較画像。
- スイッチャーの並びの照合結果（黒くなる組・秒数があればそれも）。
- 一時的に変えた設定（Use Timeline・Foot IK・OptiTrack）と、元に戻したか。コミットしていないもの。
