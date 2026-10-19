---
name: vortex-mocap-fix
description: 収録モーション（モーキャプの FBX）を Unity に Humanoid で取り込み、キャラに当てたときの見え方の不具合を直して確かめる（vortex 系ライブ案件の Timeline 用）。首がずっと上を向く・頭が横に傾く・内股・親指が開く・膝が数コマ跳ねる・膝が反る・着いている足がガタつく・立ち位置がずれる・スカートが振り回される・2 人分の骨格が入った FBX で別人を拾う、と言われたとき、新しい収録 FBX を取り込むとき、間引いた .anim を作る・作り直すときに使う。基準の姿勢を合わせる BodyRestFix、カーブの道具 ClipCurveTools、Timeline を 1 コマずつ走査する MotionScan（Unity 側の雛形）と、集計・グラフの Python 付き。
---

# 収録モーションの取り込み・直し・確かめ

2026-10-12〜16 の SinkaiFes2026（AZKi・エルセ・MZM の Anjo/Kosaka・春猿火・きまゆ）で固めた。
Timeline に組む手順そのものは vortex-timeline-setup。

`T=~/.claude/skills/vortex-mocap-fix/templates`・`S=~/.claude/skills/vortex-mocap-fix/scripts`

| 道具 | 置き方 | 用途 |
|---|---|---|
| `$T/Editor/BodyRestFix.cs` | 案件の `Assets/_TempVerify/Editor/` へ（ClipCurveTools と一緒に） | 基準の姿勢の合わせ込み（胴・首・頭・脚・親指）、.anim の書き出し・入れ直し、演者とキャラの角度の比較 |
| `$T/Editor/ClipCurveTools.cs` | 同上 | マッスルの最大と 1 超えの割合、カーブの書き出し・比較、足の目標の CSV、圧縮の切り替え、Timeline のクリップの差し替え・Foot IK、2 人分の骨格の付け替え、間引き |
| `$T/Editor/PoseCompareRender.cs` | 同上 | 2 本のクリップを同じ時刻で当てて並べた画像（全身・手の寄り）。Edit モード、別の一時シーンで描く |
| `$T/Editor/RawThumb.cs` | 同上 | Generic の写しの生の骨で親指を測る（Avatar を通さない物差し） |
| `$T/MotionScan.cs` | `Assets/_TempVerify/`（Editor の外。Play 中に呼ぶ） | Timeline を 1/fps ずつ Evaluate して脚の骨を書き出す、録画と同じ刻みで進める、Foot IK・クリップの差し替え（Play 中） |
| `$S/make_fbx_meta.py <fbx>` | FBX を置く前に | 圧縮 Off・Humanoid の .meta を先に作る |
| `$S/leg_scan.py stats / events` | | 膝の跳ね・接地中の足首とつま先の急な動きを数える |
| `$S/goal_jitter.py` | | 足の IK の目標を元の FBX と比べる・急な動きの多い区間を選ぶ |
| `$S/plot_contact.py` | | 着いている足の足首の揺れを直す前・後で重ねたグラフ（報告の画像） |
| `$S/foot_slide.py <A.bin> <B.bin> [A,B]` | | 着いている足の滑り（接地中につま先が水平に動いた道のり）と膝の内向き・曲がりを 2 本で比べる（Foot IK の Off / On を決める） |

膝直しはサブモジュールの `KneeHyperextensionClamp`（メニュー Assets/vortex/Animation/Clamp Knee Hyperextension、入口 `CreateClampedCopyAtPath`）。
2026-10-15 時点ではサブモジュールの手元のブランチ mao/knee-muscle-clamp（e2d6d889、未 push）にだけある。
今のチェックアウトに無ければ `git -C <サブモジュール> show e2d6d889:Submod_RealtimeLiveUtility/Packages/jp.pjblue.realtime-live-utility/Script/Editor/EditSupport/Animation/KneeHyperextensionClamp.cs` を _TempVerify/Editor へ写して使う。

道具は Editor のスクリプトなので、MCP の `invoke_method`（typeName にクラス名）で呼ぶ。写したら `Library/ScriptAssemblies/*.dll` の時刻でコンパイルを確かめ、使い終わったら消す。
写す前に、同じクラス名が案件に無いかを grep する（`Assets/_TempVerify`・`_SkillVerify` に古い写しが残っていると CS0101 でコンパイルが止まる）。
`MotionScan.ScanLegs` は Play 中だけ（Edit モードの PlayableGraph は Humanoid の骨に書かない）。`State()` が `done ...` か `error: ...` になるまで待つ。

## 症状 → 原因 → 直し方

| 症状 | 原因 | 直し方 |
|---|---|---|
| 全編で首が上を向く・頭が横に傾く | 収録 FBX の Avatar の基準の姿勢（T ポーズ）で首・頭が前（横）へ倒れている。マッスルは基準からの差なので、演者がまっすぐでも傾いて記録される（MZM 首 −28°） | BodyRestFix.Run で基準の姿勢の背骨・胸・首・頭をキャラに合わせ、演者との平均の差を offsets で詰める |
| 内股・膝が内へ入る | 基準の姿勢で脚が外へ 4〜5° 開き、つま先が外を向いている（エルセ） | Run の legs = true |
| 拳から親指が突き出す・親指が開く | 基準の姿勢の親指の向きが違う（AZKi: 指と同じ向き・中の節で 35° 曲がり。キャラはまっすぐ 42°） | AlignThumbChain（3 節それぞれ）→ TransplantCurves で親指のカーブだけ差し替え |
| Foot IK On で膝が 2〜4 コマだけ反対へ跳ねる。Off だと膝が常に反る | クリップの膝のマッスル（Lower Leg Stretch）が上限 1 を超え（春猿火 左 34%・最大 1.19）、FK の膝が逆に折れる。IK がときどき反った側の解を選ぶ | MuscleStats で読む → 膝直し（1 以下の複製）→ Timeline を差し替えて Foot IK On。Foot IK を切って済ませない（ユーザーの方針） |
| 着いている足が 1 コマで数 mm ガタつく（元の FBX では起きない） | 間引いた .anim の Root と足の目標をマッスルと同じ許容（0.002）で間引いた（RootQ 0.2° で足元 4 mm）。または、圧縮して取り込んだ（キーがまばらな）FBX に毎フレーム前提の間引きを掛けた | FBX を圧縮 Off で取り込み直し → RebuildCurves（Root・足手の目標 1e-4・RootQ 5e-5・脚のマッスル 1e-4）。GUID は変わらない |
| 2 人を並べると 1 人だけ立ち位置・向きがずれる | Humanoid の既定は、ルートを 1 フレーム目からの差分で扱う | クリップの keepOriginalOrientation / PositionXZ / PositionY を On（収録の座標のまま） |
| 2 人が中央で重なる | Timeline のクリップの Remove Start Offset が On | Off |
| スカートが横へ流れる・振り回される | keepOriginalOrientation でルートが収録の向きに回り（平均 37°/秒）、VRMSpringBone の Center がルートの子だと基準ごと振られる | シーン側の上書きで Center を空に（ワールド基準。振れの p95 32° → 17°） |
| 別の人が動く・腕だけ別人 | FBX に 2 人分の骨格があり、自動の Humanoid が別の人を拾った（AZKi の FBX にエルセ） | ClipCurveTools.RemapHuman（接頭辞を付け替え、圧縮 Off で取り込み直し） |
| 動きが入っていない骨に対応付いている | 動きが HumanIK の制御リグ（`SKL_azuki_Ctrl:*`）にだけ入っていて、モデルの骨（`jnt_*`）は動かない | TransformCurves でどの骨格にキーがあるかを見て、Humanoid をそちらへ対応付ける |
| MotionForge で見せた動画で、腕が胴に食い込む（Unity では起きない） | MotionForge の表示: A ポーズがレストのモデル（Anjo5th・Kosaka5th）を「送出していない」演者に当てると、T ポーズとの差の補正が掛からず腕が約 40° 下がる | 送出 On（Inspector の Retarget「Send ... as the character」）で見せる。収録データと Unity（Humanoid が T ポーズ化する）は問題ない（2026-10-14） |
| 右手の指がクリップどおりに動かない | MicController の握りのプリセット（Override）がマイクのクリップの間ずっと上書きしている | 直さなくてよい（見えない）。プリセットの手（24〜38 左・39〜53 右）とキャラの手が合っているかだけ見る |

## 取り込み（最初に必ず）

1. **FBX を置く前に `make_fbx_meta.py` で .meta を作る**（圧縮 Off・Humanoid・このモデルから作る）。
   - 長い FBX を既定（削減あり）で取り込むと、削減の処理で Unity が落ち、起動し直しても同じ取り込みで落ちる（エルセ）。
   - 削減ありのクリップはキーがまばらで、後で間引くと足がガタつく（AZKi）。
   置き先のパスを渡して .meta を先に作り、それから FBX を置く（Auto Refresh が無効の案件なら、FBX を置いた直後に作って Refresh でもよい）。
2. 取り込みは 1 本 20〜30 分（AZKi の CH10016: 初回約 30 分、圧縮 Off での取り直し約 20 分）。Unity が見えていないデスクトップにあると、さらに遅い。進み具合は Editor.log か CPU で見る。
3. Avatar を確かめる: `ClipCurveTools.AvatarInfo`（valid・human・Hips の骨名）。
   2 人分の骨格・制御リグなら上の表のとおり付け替える。
4. 2 人以上を並べるなら keepOriginal*（立ち位置）。Apply Root Motion の On / Off は Timeline の再生では差が無かった（Timeline がルートを動かす）。
5. 膝のマッスルを読む: `ClipCurveTools.MuscleStats(<FBX か .anim>, "", 60)`。1 を超えていれば膝直しが要る。
6. 基準の姿勢のずれを測る: `BodyRestFix.Rest(<FBX>)` と `Rest(<キャラのプレハブ>)` を比べる（首・胸・太もも・すね・つま先・親指）。
   演者とキャラの再生中の平均の差は `BodyRestFix.Play(<キャラ>, <クリップ>, 0.25)`。

## .anim を作る・作り直す

- FBX のクリップをそのまま複製すると「Object size is too large」で保存できない（削減 Off の取り込みのため）→ 間引いて書き出す。
  - 新しく作る: `BodyRestFix.ExtractClip(<FBX>, <出力.anim>, true)`
  - 既存の .anim に入れ直す（GUID・Timeline の参照を保つ）: `BodyRestFix.RebuildCurves(<FBX>, <.anim>, <残す名前の頭>, <1 以下にする名前>)`。
    手で直したカーブ（AZKi の左腕・左手の 27 本）は、残す名前の頭に `Left Arm ;Left Forearm ;Left Hand ;LeftHand.` のように渡す。
  - 中身を丸ごと入れ替える: `ReplaceClipContent(<新.anim>, <旧.anim>)`。**新の方は終わると消える**（中身を旧へ写し、旧の GUID を残すため）。
    どちらも .anim だけを受ける（FBX を渡すと FBX ごと消えるので、雛形が断る）。カーブの一部だけ: `TransplantCurves`。
- 許容（`BodyRestFix.ReduceEps`、AZKi の全編で足の目標の誤差 0.3 mm 以内・揺れが元と同じになることを確かめた値）:

  | カーブ | 許容 |
  |---|---|
  | マッスル | 0.002（可動域の 0.1%） |
  | 脚のマッスル（Upper/Lower Leg・Foot・Toes） | 1e-4 |
  | Root・足と手の目標の位置 | 1e-4 |
  | RootQ | 5e-5 |
  | 足と手の目標の向き | 5e-4 |

  Foot IK Off のキャラは、足の位置が股関節からの積み重ねで決まるので、脚のマッスルも細かくする。
- キーが毎フレームに無い（圧縮して取り込んだ）FBX からは、どちらも書かずに断る。FBX の圧縮を Off にして取り込み直す（`ClipCurveTools.SetCompression(<FBX>, 0)`、約 20 分）。
  作り終えたら .meta を元に戻してよい（`git checkout`。Library のキャッシュで戻りはすぐ）。Timeline が使うのは .anim。
- 素朴な間引き（全区間の見直し）は一定値のカーブで O(n²) になり、Unity が 20 分止まった。`ClipCurveTools.ReduceLinear` を使う。
- 作り直す前の .anim は、案件の外（例 `SinkaiFes2026_Media/backup/`）にコミットの SHA 付きで控える。1 GB 前後あるので LFS の容量にも注意。

## 基準の姿勢を合わせる（BodyRestFix）

1. FBX の .meta を元（直す前）に戻す（毎回、元から掛ける）。
2. `Run(<FBX>, <キャラのプレハブ>, true, "<offsets>", <脚も>, <親指も>)` → FBX が取り込み直される。
3. `ExtractClip` か `RebuildCurves` で .anim を作り、膝直しを掛ける。
4. `Play(<キャラ>, <クリップ>, 0.25)` で演者（FBX 自身の骨格）とキャラの角度の平均の差を見る → 差を offsets に足して 2〜3 回詰める。
   offsets の例（Kosaka）: `spinePitch=5.1;chestPitch=3.3;chestRoll=1.1;chestYaw=0.1;neckPitch=3.2;neckRoll=1.0;headPitch=3.3;headRoll=0.2`。Pitch は正 = 後ろへ倒れる。
5. 画で確かめる: `PoseCompareRender` で直す前・後を並べ、収録時の OBS プレビューの同じ時刻と並べる（ユーザーの基準は「収録時に見えていた姿」）。

- 胸を回すと子の腕も回り、腕・指のマッスルの軸が変わる → 胴を回した後で肩の世界の向きを元に戻す（道具がやる）。胸のねじれは鎖骨の根元で測る。
- 脚・腕の角度は ±180° をまたぐので、向きの成分で比べる。つま先は補正の約 2.8 倍動く（行き過ぎに注意）。
- キャラに頭の先の骨が無いと頭は合わせられない（エルセ）。
- 親指: 付け根だけ合わせると中の節の曲がりが残る → 3 節それぞれ（AlignThumbChain）。物差しは Avatar を通すと 2〜3° 動く → RawThumb の生の骨で確かめる。
  付け根のマッスルは −1 を超える（AZKi 最小 −3.1）が Animator は切り詰めない。±1 に収める処理を親指に掛けない（開いた位置へ戻る）。
- 演者自身がそう動いている所（左の親指を 49° 開く、首を 11° 上げる）は直さない。数値で演者と合っていれば、見え方はプレビューと並べて確かめる。

## 確かめる（走査）

1. `$T/MotionScan.cs` を `_TempVerify/` へ写す → Play（OptitrackSkeletonAnimator は止める）→
   `MotionScan.ScanLegs(<Director>, <キャラのパス>, 0, <全長>, 60, <bin>)` → `State()` が `done` になるまで待つ（全編 1200 秒で約 30 秒）。
   直す前・後を同じ条件で（クリップの差し替えは Play 中の `SwapClipInPlay`、Foot IK は `SetFootIK`。どちらもアセットを書き換えるので終わったら戻す）。
2. `python "$S/leg_scan.py" stats before.bin after.bin`。目安（Foot IK On）:

   | 指標 | 元の FBX のまま流した値 | 崩れていた値 |
   |---|---|---|
   | 膝の跳ね 15 mm 以上 | 0〜5 コマ | 数十〜200 コマ（反る跳ねは 70〜135 mm） |
   | 接地中の足首の 2 mm 超 | 数十 | 数千 |

   跳ねが IK 由来か元データ由来かは `leg_scan.py events <IK On の bin> <IK Off の bin>`。
   Foot IK の Off / On を決めるときは、同じ区間を両方で走査して `python "$S/foot_slide.py" off.bin on.bin`。
   - 接地 = つま先が低く（各足の下位 30% + 2 cm）、水平の速さ 0.3 m/秒未満が 0.2 秒以上続く区間。滑り = その中でつま先が水平に動いた道のり。
     判定は緩く、すり足や踏み替えも 1 回の接地に入る（1 回で 1 m の「滑り」もある）。同じ区間の 2 本を比べるためにだけ使い、値そのものを品質の基準にしない。
   - エルセ（1312〜1550 秒、基準の姿勢を直した後）: 滑り 毎秒 60〜63 mm（Off）→ 13〜15 mm（On）、膝の跳ね 0 / 0、
     膝の内向き 平均 4 → 13 mm、膝の曲がり 平均 15° → 26°。つま先の軌跡と前からの脚の画像を見せて、ユーザーが On を選んだ（2026-10-16）。
   - 基準の姿勢を直したら、Foot IK を Off にしていた理由（内股・膝が内へ入る）が消えていないかを、この比較で確かめ直す。
3. 足の目標そのもの（Unity の再生を通さない）: `ClipCurveTools.GoalCsv(<クリップ>, 60, <csv>)` を元の FBX と .anim で書き、
   `python "$S/goal_jitter.py" 1 <FBX.csv> <anim.csv>`（`--windows` で録画する区間を選ぶ）。
4. 直した所以外が動いていないこと: `BodyRestFix.WorldDiff`（主な骨の位置の差）・`GoalDiff`・`ClipCurveTools.DiffScan`。
5. 見せる: unity-view-recording で同じ区間を直す前・後で録り、上下に並べる（足元は `MakeAnchor` で世界に固定した点を見る。足に付けると揺れが消える）。
   録画と Timeline の時刻を合わせるなら `StepSegments`。グラフは `plot_contact.py`。動画は Dropbox、比較のグラフは画像で添える。

## 残っている問題（2026-10-16）

- Kosaka の左膝の 30 mm 前後の揺れ 42 件（817〜829・966〜976 秒など）は、マッスルと関係なく残る（Foot IK Off でも同じ大きさが 5 件）。
- 太もも・膝下の捻り（Upper/Lower Leg Twist）が逆向きに入れ替わる所（合計は滑らか）を平滑にする道具は作りかけ（サブモジュールの stash「WIP knee: AnimationClipCopy refactor」）。
- MotionForge で区間を直した .anim への差し替えも試したが、跳ねの大きさが 1〜4 割減るだけで採らなかった。
- きまゆの .anim は Root・足の目標をマッスルと同じ許容（0.002）で間引いたまま（足の目標が平均 2.5 mm・最大 8 mm ずれる）。ユーザー判断で直していない（2026-10-15）。
- 基準の姿勢を測って直したのは MZM の 2 人・エルセ・AZKi の親指だけ。首の基準の姿勢のずれ（Neck→Head）は春猿火 −15.9°・AZKi −13.4° と大きいが、測り直し・直しは提案だけで未着手
  （みなとん −3.8°。再生中の頭の平均は春猿火 −8.9°・AZKi −9.7°）。きまゆも胸の前後 11°・ねじれ 9° ずれたまま（マイクの Auto で顔が見える所まで合わせた）。

## 報告に入れるもの

- 原因の根拠（基準の姿勢の角度・マッスルの最大と割合・足の目標のずれ）と、直した後の同じ指標。
- 走査の前・後の数（膝の跳ね・接地中の急な動き）と、元の FBX との比較。
- 直す前・後の比較（画像・動画）と、収録時のプレビューとの比較。
- 作った・差し替えた .anim と Timeline の差分（m_Clip・m_ApplyFootIK だけか）、バックアップの場所、.meta を戻したか。
