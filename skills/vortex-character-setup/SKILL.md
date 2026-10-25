---
name: vortex-character-setup
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、キャラクターモデル（VRM）をライブシーンへ仕込み、確認用の成果物まで出す一連の作業。Drive から VRM を取得 → 配置 → NiloToon 変換（モーダル 2 つ）→ マテリアル変換の抜け漏れチェック → 元のキャラを登録ごと削除 → CharacterSetup（FacialPreset・ID・OscRx_LipSync + FacialManager・OSC 配線）→ テストモーションで全員／1 人ずつの映像を OBS で収録 → 表情表の書き出し → Dropbox へ納品 → シーンを戻す・一時ファイル削除・コミット、まで。「キャラを仕込む」「モデルをセットアップ」「このキャラを入れて」「NiloToon 変換」「マテリアルの抜け漏れ確認」「テストモーションで録って」「1 人ずつ録って」「表情表を出して」と言われたら使う。シーンを新しく作るところは vortex-live-scene-create。
---

# vortex キャラクターセットアップ（仕込み → 映像 → 表情表 → 納品）

Submod_RealtimeLiveUtility（`jp.pjblue.realtime-live-utility`）を使う案件で、キャラを既存のライブシーンと同じ形に仕込み、
**テストモーションの映像（全員・1 人ずつ）と表情表を Dropbox に納品するまで**を 1 セットで行う。
2026-09-30 Animax（3 体）で通した流れをそのまま手順にしている。シーンがまだ無ければ先に `vortex-live-scene-create`。

## 道具

`S=~/.claude/skills/vortex-character-setup/scripts` / `E=~/.claude/skills/vortex-timeline-export`

| 道具 | 用途 |
|---|---|
| `$S/unity/VortexCharTool.cs` | **Unity 側・仕込み**。Open/SaveScene、Inspect（キャラと外からの参照・OSC 配線を書き出す）、DumpArray、Compare、ConvertToNiloToon、RemoveCharacters、SetupCharacter、ApplyFacialPreset、CheckFacial、ImportMotionAsHumanoid、EnsureFolder |
| `$S/unity/VortexCharMic.cs` | **Unity 側・マイク**。CreateMicMouth（口の位置を表情 A で動く頂点から求めて Head/MicMouth を作る）、PlaceMicLike（手本のキャラと同じマイクを同じ側の手に置く）、AddMicTargetLike（MicController の枠を手本から写して足す） |
| `$S/unity/VortexCharCapture.cs` | **Unity 側・撮影**。BuildTimelines（1 人ずつ＋全員）、ShowOnly、ClipRootExtents、SetupCamera、StartFacialCapture、IsCapturing、Cleanup |
| `$E/templates/RecGameView.cs` | 録る Display を映す浮動 Game View（PlaceDisplay）、PlayFromStart |
| `$S/obs_setup_dual.py` | OBS を FHD 2 画面に（モニタ ID を自動取得し、化けない形で渡す。黒画面なら失敗） |
| `$E/scripts/obs_rec.py` | `shot`（OBS の今の画を PNG）/ `restore`（元に戻す） |
| `~/.claude/skills/screen-recording/scripts/obs.py` | `start` / `stop`（録画） |
| `$S/keep_front_until.ps1` | 表情表の撮影中、Unity を前面に保つ（撮影は Editor の更新で進む） |
| `$S/cut_and_check.py` | 録画の左半分を切り出して尺を合わせ、check.py と静止区間で点検 |
| `$S/check_material_conversion.py` | NiloToon 変換の MatCap / Emission / テクスチャの取りこぼし検査 |

Unity 側の 4 つは `Assets/_TempVerify/Editor/` にコピー → `Assets/Refresh` → `Library/ScriptAssemblies/Assembly-CSharp-Editor.dll` の時刻で
コンパイルを確かめてから `invoke_method` で呼ぶ。作業の最後に `_TempVerify` ごと消す。

## 案件の既定を先に読む（この skill の既定より優先）

この skill の既定は 2026-09-30 の Animax（vortex_urp 系）で決めたもの。案件ごとに、プロジェクトのメモリ（キャラ仕込みの既定）と CLAUDE.md（シーン構成）を先に読み、食い違えば案件の方に従う。
食い違いが見つかったら、どちらに揃えるかをユーザーに聞く（黙ってどちらかに寄せない）。

| 項目 | Animax（この skill の既定） | SinkaiFes2026（2026-10 時点のシーンの実態） |
|---|---|---|
| 置き場 | `02_vortex_character/<収録日_案件名>/<キャラ>/` | `02_vortex_character/<キャラ or 事務所>/` |
| 仕込み先 | 案件のライブシーン | `ShinkaiFes2026_<Grand|Prime>_modelSetup*.unity`（個人版 `_kuni` などがある。仕込み先は指定されたシーンだけ） |
| 表情・口パク | FacialManager + OscRx_LipSync（Osc_XBox） | 同じ（AZKi だけ vortex_FacialController）。メモリの既定（2026-09-16）は「vortex_FacialController・プリセット無し」で、シーンの実態と違う → 仕込む前に聞く |
| ID | 同時に出る別人に 0,1,2… | 既定 0（パレプロ 7 人の組は 0〜6） |
| GameObject のレイヤー / Rendering Layer | （シーンに合わせる） | Chara / Character（`SetupCharacterEx` が既存のキャラから読む） |
| スケルトン名 | Skeleton1 | 多くは Skeleton1。Prime_modelSetup では 11 体が Motive 側のキャラ名（Fuwari・Mikoto など）。収録・本番の Motive の名前をユーザーに聞く |
| マイク | なし | ハンド `SKM9000_uni_LayerFix.prefab`（手の骨の子）・`Head/MicMouth`・MicController の枠・握り `Pose/<Grand|Prime>/<名>_Mic.asset`、ヘッドセット `dpa(NiloToon).prefab`（Head の子） |
| テストモーション | `03_vortex_live/04_Test/Motion/` | `03_vortex_live/05_Test/Motion/230519_TestMotion.fbx`・`MotionCheck.playable` |
| マテリアルの直し | 報告だけ | 報告だけ（直すのはユーザーの判断。人が直した型: 顔 `_IsFace`・Matcap 加算・眉のステンシル・法線を切る） |
| git | 作業ブランチにコミット | ステージだけ（コミットしない） |

## 聞くこと / 聞かないこと

**最初に聞く（無ければ始められない）**
1. モデルの場所（Drive のリンクか手元のパス）と、仕込み先のシーン（指定されたシーンだけ。他へ広げない）
2. テストモーションの場所（プロジェクトに無ければ）。**同名でも中身が違うことがある**（ハッシュで比べる）
3. 元からいるキャラを消すか（「元のキャラは削除」と言われていなければ聞く）

**案件ごとに聞く（AskUserQuestion、推奨を先頭に）**
- 口パク・表情の形: 推奨は **最近のシーン（Iori・ProBlueFes）と同じ OscRx_LipSync + FacialManager**。
  複製元が古いシーンだと uLipSync + FacialManager のことがある。skill 旧版の vortex_FacialController を使うシーンは 2026-09 時点で無い。
- ID（`OscRx_LipSync.characterID` = `FacialManager.oscFacialID`）: 同時に出る別人は 0,1,2… と振る（ProBlueFes）。衣装違いの同一人物は全員 0（Iori）。
  推奨は Drive のフォルダの並び順。
- 表情の機器（`_deviceType`）: 推奨 `Osc_XBox`（ProBlueFes・Iori）。ShoreLine は `Osc_StreamDeck`。
- 元キャラの登録（CharacterActivator の枠・LookatManager・MeshActivator・PoseController・Micoffset_*）: 推奨は「全部外して新しく登録」。

**決まっている既定（聞き直さない）**

| 項目 | 既定 |
|---|---|
| 置き場 | `Assets/02_vortex_character/<収録日_案件名>/<キャラ名ローマ字>/`（例 `261007_Animax/KanzakiElena/`）。VRM の元のファイル名のまま置く |
| テストモーション | `Assets/03_vortex_live/04_Test/Motion/<元のファイル名>.fbx`、Humanoid・ループ（ImportMotionAsHumanoid） |
| 表情プリセット | 標準 `FacialPreset.asset`（`VortexCharTool.DefaultPresetPath`）。LB/RB の `BlinkR`/`BlinkL` はモデルの `Blink_R`/`Blink_L` に自動で直る |
| 瞬き | 2500〜3000ms（プリセットの値） |
| OptitrackSkeletonAnimator | `Skeleton1`（既定のまま） |
| 立ち位置 | 原点・スケール 1（CharacterActivator で切り替える運用。本番の立ち位置は別途） |
| マテリアル変換の取りこぼし | **勝手に直さない**。報告して判断を仰ぐ（見た目が変わる） |
| 映像の撮り方 | 番組出力ではなく**正面の固定カメラ＋確認用ライト**（下の「映像」）。ユーザー承認済み |
| 1 人ずつの画角 | **カメラはワールド X=0（センター）**、身長が画面の約 45%（heightRatio 0.45）、高さ 0.4m から体の中心を見上げる |
| 納品先 | Dropbox `Claude/<案件名>_<収録日>/`（映像）と その下の `FacialChart/`（表情表） |
| git | 作業ブランチにコミット。push は指示があったときだけ（2026-09-30 は指示あり） |

## 0. 始める前に

- `log/claudeLog.txt` の末尾と、プロジェクトメモリに案件の前提（ID 表など）が無いかを読む。
- Unity の接続先: `Library/ClaudeCodeMCP/endpoint.json` の `processId` が今の Unity か。
- **MCP を呼ぶ直前に毎回 `focus_window` で Unity を前面に出す**。背面だと `get_play_state` まで timeout する。
  **timeout しても Unity 側では後から実行される**。再送せず、成果物（ファイル・ログ）で実行済みかを確かめてから次を投げる。並列に投げない。
- シーンに未保存の変更が無いこと（最後に「保存せず開き直し」で片付けるので、先に保存しておく）。

## 1. 取得と配置

- Drive: `mcp__claude_ai_Google_Drive__search_files`（`parentId = '<フォルダ ID>'`）で中身を見る。
  取得は `rclone backend copyid gdrive-ro: <fileId> <dir>/`（`gdrive:` は共有ファイルが 404）。権限が無ければ共有を頼む。
- **Drive 由来の日本語名は濁点・半濁点が分かれている（NFD）ことがある**（`ぴ` = `ひ` + U+309A）。
  bash の `cp "…たぴ…"` や一覧から回す `rm` は黙って外れる → glob（`cp "$D"/三神*.vrm`）か Python で扱い、MCP へは実バイト列（`\u3072\u309a`）で渡す。
- 置いたら `Assets/Refresh`。VRM の prefab ができるまで待つ（背面の Unity では prefab ができない → 前面に出す）。

## 2. NiloToon 変換（1 体ずつ）

`VortexCharTool.ConvertToNiloToon("<…>.prefab")`。途中で NiloToon 本体のモーダルが 2 つ出て、MCP は timeout する。
1. 全画面 `screenshot` で見つけ、「**Yes, convert the materials to NiloToon.**」
2. 「Material Upgrader … overwrite existing materials」→ **Proceed**（上書きされるのはツールが複製した `(NiloToon)(Materials)` 側）
3. `(NiloToon).prefab` ができたのを確かめてから次の 1 体（並列に投げると後から二重に実行され、` 1` 付きの prefab とマテリアルができる。できたら消す。
   消すファイルは参照されていないかを GUID で確かめ、日本語パスなので Python の `os.remove`）
4. `python $S/check_material_conversion.py Assets/02_vortex_character/<案件フォルダ>` → 「問題なし」を確かめる

## 3. 元のキャラを外す（指示があるとき）

1. `VortexCharTool.Inspect(<scratch>/inspect.txt)` で、キャラと外からの参照（OSC 配線・CharacterActivator・LookatManager・MeshActivator・PoseController・MicOffset）を把握
2. `VortexCharTool.RemoveCharacters("*", true)`（全員＋Micoffset_*）。配列の中の参照は**いちばん外側の要素ごと**消す（空の枠を残さない）
3. `DumpArray("CharacterActivator","_characters")` / `DumpArray("LookatManager","_lookatTargets")` で、キャラ以外の枠（Live2D・Between など）が残っていることを確かめる

## 4. 仕込む

`VortexCharTool.SetupCharacterEx("<…(NiloToon).prefab>", <id>, "", "Osc_XBox", "", "", "", "<スケルトン名>")` を 1 体ずつ（旧 `SetupCharacter` の 4 引数も同じ処理）。
- 後ろの 4 つ: OSC の配線先（空なら、既にキャラが配線されている uOscServer）・GameObject のレイヤー・Rendering Layer（空なら既存のキャラの多数派）・スケルトン名（空なら Skeleton1）。
  決められないとき（キャラ用のサーバーが 2 つある・シーンにキャラが 1 人もいない）は、何も作らずに `error:` と候補を返す。候補を見て渡し直す。
  CharacterSetup のウィンドウを `CreateInstance` で作ると Rendering Layer が 0（Default）のままになり、Character のライトだけを受ける案件でキャラが真っ黒になっていた。
  ウィンドウは GameObject のレイヤーも設定しない（番組カメラの cullingMask がキャラのレイヤーで絞っている案件では写らない）。
  レイヤーを既存のキャラから写すのは、キャラ単位で過半数が同じときだけ。割れているシーン（Grand_modelSetup は Chara 3・Default 3）では、分布を返して止まるので `layerName` を渡す。
  CharacterActivator・LookatManager は、System の塊ごと無効のシーンでも、無効の物を含めて探して登録する（ウィンドウの自動検出は無効の物を拾わず、登録が黙って抜けていた）。
  プレハブのルートに VRMBlendShapeProxy（BlendShapeAvatar 付き）と Humanoid の Animator が無ければ、作る前に断る。同じキャラ（名前かプレハブ）が既にいれば断る
  （MCP が timeout した後に送り直しても 2 体目を作らない。入れ直すなら `DeleteCharacter` してから）。
  キャラ・CharacterActivator / LookatManager の登録・OSC の配線は 1 つの Undo（Ctrl+Z 1 回で全部戻り、Redo で全部戻る。2026-10-19 に保存して開き直すまで確かめた）。
  途中で例外が出たら、それまでの変更を戻して `error: setup failed and was rolled back` を返す（作りかけのキャラを残さない）。
- 仕込んだら、シーンの点検（vortex-live-scene-create の `scene_audit.py check` と `chars`）で、そのキャラの OSC 配線・レイヤー・枠・ID の重複を確かめる。
  ID・スケルトン名が同時に出るキャラと重なっていれば warn になる（演者ごとに決める値なので、ユーザーに聞く）。
- CharacterSetup の本来の処理（配置・Optitrack・rendering layer・CharacterActivator・LookatManager 登録）＋ **FacialPreset 適用**
  ＋ uLipSync 系と AudioSource を外す ＋ OscRx_LipSync 追加 ＋ FacialManager の `_oscLipSync`・ID・機器 ＋ OSC サーバーへ 2 件配線。
- **FacialPreset を渡さずに CharacterSetup を反射で呼ぶと、表情の枠が全部空のまま保存される**（エラーは出ない。Play 開始時に
  MorphControl の ArgumentOutOfRange が出て、表情表も空になる）。もし空で保存してしまったら `ApplyFacialPreset("", "Osc_XBox")`。
- `CheckFacial()` で全員 `assigned=20 missing=[]`、ID・機器が想定どおりかを確かめる → `SaveScene()` → `git add` で仕込んだものだけステージ。
- 見た目の点検は次の映像で兼ねる（Play で ArgumentOutOfRange が出ないことも見る）。

## 4.5 マイク（案件で使うとき。SinkaiFes2026）

手本は、同じシーンにいる同じ側の手でマイクを持つキャラ。どれも Edit モード・基準の姿勢（T ポーズ）で呼ぶ。
1. `VortexCharMic.CreateMicMouth("<キャラのパス>", 0.3, "")` → `Head/MicMouth`（表情 A で動く頂点の重心を、唇の表面まで前へ出した点。向きは顔の前）。
   人が置いた MicMouth と比べるときは 3 つ目に既存の MicMouth のパスを渡す（ずれを cm で返す。置き直す前に比べる）。0.3 は「動きが最大の 3 割以上の頂点」（頬などのわずかな動きを除く）。
   - 精度（2026-10-19、人が置いた 6 体と `CompareMouths` で比べた）: AZKi 0.1・りのん 0.5・きまゆ 1.3 cm（唇の表面に置いたもの）。
     エルセ 4.4・Anjo 6.0・Kosaka 7.4 cm は、人が唇より 4〜7 cm 前に置いていた分（高さの差は 1〜3 cm）。前に出すかは、ユーザーに聞くか Mouth Distance で合わせる。
   - 頂点の位置は、骨の重みで自分でスキニングして求める。`SkinnedMeshRenderer.BakeMesh` は無効（非表示）のキャラでは骨の姿勢を反映せず、14 cm ずれた。
   - シーンのキャラの口をまとめて比べる: `VortexCharMic.CompareMouths("<MicController のパス>", 0.3, "centroid,p75,p90,p100")`（シーンは変えない）。
2. `VortexCharMic.PlaceMicLike("<手本のマイクのパス>", "<キャラのパス>")` → 同じプレハブを同じ側の手の骨の子へ（手からのずれと向きを、キャラのルートの向きで写す）。
3. `VortexCharMic.AddMicTargetLike("<MicController のパス>", <手本の枠>, "<キャラ>", "<マイク>", "<MicMouth>", "<握りのプリセット>", "")`
   → 寄せ方（Auto・半径・口からの距離・オフセット）は手本のまま、参照だけ差し替えた枠。手・手首の骨は空にする（実行時に Animator から埋まる）。
   握りのプリセットは手（左右）と合わないと黙って効かない。手本と逆の手なら、その手のプリセットを渡す（無ければ断る）。
   渡したプリセット（空なら手本のもの）の骨の番号（左手 24〜38・右手 39〜53）がマイクの手と合わなければ断る。
- 2 と 3 は、同じプレハブが既にその手にある・同じ Animator の枠が既にあるときは断る（送り直しで二重にしない）。
  マイクの大きさは手本の世界での大きさに、レイヤーは手本の同じ位置の物に合わせる（番組カメラに写るかが手本と同じになる）。
  パスは今のシーンで 1 つに決まること（同じパスが 2 つあれば not found と同じ扱い）。
4. 握り（指の角度）・マイクの持ち方・口からの距離は見た目の判断。Play で収録モーションを流し、口元の画を撮って見せ、ユーザーに決めてもらう。

## 5. 映像（テストモーション）

番組出力（Display 3 の Output-Canvas）は `RT_Output` に誰も書かず黒く、ライブ用ライトは DMX 無しで消灯している（vortex-timeline-export 罠 13）。
なので **Play 中だけ空き Display 6 に正面の一時カメラ（Camera_PGM の設定を写す＝ポストプロセス込み）と確認用ライトを置いて、OBS で録る**。

1. Edit モード: `VortexCharTool.ImportMotionAsHumanoid(<fbx>)` → `VortexCharCapture.ClipRootExtents(<fbx>)`（`minX,maxX,minZ,maxZ` を控える）
2. Edit モード: `VortexCharCapture.BuildTimelines(<fbx>, "Assets/_TempVerify", 1.2)` → Director `MotionTest_Director_0..` と `_All`
   （OptitrackSkeletonAnimator を無効化。シーンは保存しない）
3. `RecGameView.PlaceDisplay(6, 0, 100, 1920, 1101)` → `targetSize=(1920,1080)` を確かめる → `SetNoCameraWarning(false)` → Play
4. `python $S/obs_setup_dual.py --top 147`（luma が 0 だけなら失敗）
5. カメラ:
   - 1 人ずつ: `SetupCamera(5, 1, 0, minX, maxX, maxZ, 0.45, 0.4)` → `camera at (0.00, 0.40, 6.84)`（**X は必ず 0**）
   - 全員: `SetupCamera(5, <人数>, 1.2, minX, maxX, maxZ, 0, 0.4)`（移動範囲が全部収まる距離）
6. 1 本ずつ: `ShowOnly(i)`（全員は -1）→ `obs.py start` → `PlayFromStart("MotionTest_Director_i")`（全員は `_All`）→
   途中で `obs_rec.py shot` を 2〜3 回撮って、余計な窓が入っていないか・画面から切れていないかを見る → 尺＋数秒で `obs.py stop`
7. `python $S/cut_and_check.py <録画> <名前>.mp4 --duration <尺の秒>` → OK と静止区間を確かめる
   （終わりの T ポーズは揺れ物が少ないキャラだと静止判定になる。絵を抜いて見る）
8. 名前: `Motion_<案件>_TestMotion_<Front|キャラ名ローマ字_Solo>_FHD_OBS_<yymmdd>.mp4`

**角度・画角を詰めるときは、同じポーズ（Timeline 終了後の T ポーズ）で角度だけ変えた比較画像を出す**。
傾きだけ変えても見下ろし角は「カメラの高さ / 距離」で決まるので、見た目はほとんど変わらない（2026-09-30 に指摘された）。

## 6. 表情表

Play 中のまま:
1. `VortexCharTool.EnsureFolder("Assets/_TempVerify","FacialChart")` とキャラごとのフォルダ
2. `VortexCharCapture.StartFacialCapture(i, "Assets/_TempVerify/FacialChart/<ローマ字>")`
3. `powershell -File $S/keep_front_until.ps1 -TitlePrefix "<プロジェクト名> - " -Folder <出力フォルダ> -TimeoutSec 240`
   → 表情ごとの画像（VRM 標準なら 18 枚）と表 `<キャラ名>_setupped.png`（3508x2480）ができる
4. 表の画を開いて、14 枠に顔と名前が入っているか見る（十字キーの上・左・右は空欄で正常。Neutral は十字キー下だけに載る仕様）
   - 撮り直し・2 体目では、keep_front_until.ps1 が前回の表のファイルを見て即「done」になる。`IsCapturing()` が False になるまで待つ。
   - 表の枠はキャラのルートの vortex_FacialController か FacialManager から読む。どちらも無いキャラ（例: Pia のリオナ）は、
     割り当てを付けた FacialManager を Play 中に足して `enabled=false`（Start を走らせない）にすれば撮れる。
     ルートに Animator が無いモデル（Ext_TokinoSora_2026-pia のそら・リオナ）は、StartFacialCapture・BuildTimelines が子の Humanoid の Animator を探す（2026-10-26 に直した。以前は MissingComponentException）。
     無表情のクリップ名が Neutral でない（Default など）と全枠に載るので、無表情は十字キー下だけに入れる（2026-10-19 Ext_TokinoSora_2026-pia）。

## 7. 納品（Dropbox）

```bash
rclone copyto <mp4> "dropbox:Claude/<案件>_<収録日>/<名前>.mp4"
rclone copy <FacialChart/<ローマ字>> "dropbox:Claude/<案件>_<収録日>/FacialChart/<ローマ字>" --exclude "*.meta"
# 表は直下にも FacialChart_<ローマ字>.png として置く（_tmp へ include "*_setupped.png" で上げて moveto）
rclone link "dropbox:Claude/<案件>_<収録日>"
```
動画・画像のリンク共有はユーザー承認済み。

## 8. 後片付け

1. `obs_rec.py restore`
2. Play 中に `VortexCharCapture.Cleanup("")`（撮影ウィンドウと浮動 Game View を閉じる）→ Play を抜ける
3. Edit モードで `Cleanup("<シーンのパス>")` → `dirty=False` で開き直ったこと（Timeline・無効化を捨てる。全員センターに戻る）
4. `AssetDatabase.DeleteAsset("Assets/_TempVerify")`（Unity がフォルダを掴んでいて `rm` は EBUSY になる）→ コンパイル確認
5. `C:\Users\komao\Videos` の元録画を消す（切り出しを Dropbox に上げてから）
6. `git status` で、ステージが仕込んだものだけか確かめる（Unity の再インポートで出る prefab・meta・RenderTexture の差分は含めない）→ コミット
7. `log/claudeLog.txt` に、仕込んだキャラ・ID・マテリアル検査・納品リンク・起きた問題を追記

**Play を抜けたときに Unity が落ちることがある**（2026-09-30 に 1 回。`%LOCALAPPDATA%\Temp\Unity\Editor\Crashes`）。
成果物と保存済みシーンは無事。`Unity.exe -projectPath` で起動し直し、「Recovering Scene Backups」は Yes（`Assets/_Recovery` へ退避するだけ）、
今回のクラッシュで開いた Unity Bug Reporter は送らずに閉じる（別の日時のものは触らない）。

## 報告に入れるもの

- 仕込んだキャラ・ID・機器・表情の割り当て（CheckFacial の結果）・マテリアル検査
- 映像: 各ファイルの解像度・尺・サイズ・静止区間、途中の画、Dropbox のリンク
- 表情表: 3 枚の表の画像、Dropbox のリンク
- シーンの変更（外した登録の一覧）とコミット・push の有無
- 起きた問題（timeout・モーダル・クラッシュ）と復旧

## 詰まりやすい点（まとめ）

| 症状 | 原因 | 対策 |
|---|---|---|
| MCP が全部 timeout | Unity が背面 / モーダル | `focus_window`、全画面 `screenshot` でモーダルを探す。再送しない |
| ` 1` 付きの prefab・マテリアル | timeout 後に再送した要求が後から実行 | 1 件ずつ、成果物で確認してから次 |
| 表情表が空・Play で ArgumentOutOfRange | FacialPreset を渡さず CharacterSetup | SetupCharacter に preset を渡す / ApplyFacialPreset |
| 表情表で NRE | `CreateFacialImage.prefab`・`_MouthClose` は旧形式 | `_String.prefab`（VortexCharCapture が使う） |
| 撮影ウィンドウで欄が無い | VST パッケージに同名の `BlendShape_Screenshot` | `_facialImageObj` を持つ方（VortexCharCapture が選ぶ） |
| 表情表の撮影が進まない | Editor の更新が止まっている | keep_front_until.ps1 |
| 映像が全面ボケ | PGM 専用 Volume の DoF | Volume は Default だけ（SetupCamera が設定） |
| OBS が真っ黒 | Git Bash がモニタ ID の `\\?\` を畳む | obs_setup_dual.py |
| OBS 録画が 1 秒で止まる | `Error writing packet: Invalid argument` | 録り直す（`obs.py stop` が 501 なら疑う） |
| キャラが画の中央に来ない | カメラを移動範囲の中央へ寄せた | カメラは X=0（SetupCamera が固定） |
| 別アプリの窓が画に入る | 他セッションのアプリが前面へ | 収録中に shot で確かめ、入ったら録り直す |
