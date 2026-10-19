# カメラ記録とスイッチング（Camera Record Track・Override・スイッチャー）

## 記録の中身

- 収録時の `Recorder_camera` の .anim（`<名前>_camera_<日時>.anim`、YAML で 1〜2 GB）。中身は 3 つだけ。
  - 全カメラの位置・回転・FoV のカーブ。ノードは `Cameras/<番号>_<カメラ名>`。
  - `activeId`（PGM の番号）・`reserveId`（PRV の番号）。
  - `fade`（0→1 で PGM と PRV が入れ替わる）と、PGM / PRV のレンズ。
- レール上の位置・ドリーの速さは記録されない（ワールドの位置・回転・FoV だけ）。
- 再生（Camera Record Track → スイッチャー `System_GrandStage/Camera/VirtualCamera` の VirtualCameraSwitcher）は、
  カーブを「`Cameras/<番号>_<今のシーンのカメラ名>`」のノードで受ける。
  - 番号の並び・名前が記録と違う番号は、カーブが当たらず番組カメラが原点・画角 0 になる（真っ黒）。

## スイッチャーの並びを記録と照合する

```bash
python "$S/camrec.py" order <カメラ記録.anim> <シーン.unity>     # 番号ごとに OK / NG
python "$S/camrec.py" segments <カメラ記録.anim> --ids 13,14 --clip <start>,<clipIn>,<ts>   # その番号が番組に出る区間と合計秒
```
- 1 回目の読み取りは 2 GB で約 30 秒。結果は %TEMP%/camrec_cache に置き、2 回目からはすぐ返る。
- 組（収録日）ごとにスイッチャーの並びが違うことがある（SinkaiFes2026: MZM だけ 13・14 番が別のカメラ）。
  1 つのシーンで複数の組を流すなら、どちらかが黒くなる。
  - SinkaiFes2026 では、MZM に合わせるとみなとんの 13・14 番が 22 か所・134 秒、戻すと MZM が 43 か所・183 秒黒くなり、同じ日に 2 往復した（経緯はプロジェクトの CLAUDE.md）。
  - どの組を写すかはユーザーが決める（書き出す組が変わるたびに聞く）。
  - 両方を写すには、再生側をカメラ名で当てる直しが要る（差分の控え: SinkaiFes2026_Media/camera-record-names.patch）。
    2026-10-15 にユーザーはシーンの並びの直しを選んだ。往復が続くなら、名前で当てる直しを改めて提案する。
- 並びを変えたら、`order` で全組を照合し、黒くなる組と秒数を報告する。

## 切り替えのタイミング（ClipIn・timeScale）

- 番組の切り替えは activeId ではなく fade に出る。瞬時のカットは fade が 1 キーで 0↔1 に跳ぶ。ディゾルブは約 1 秒かけて動く（映像の差分では拾えないので数えない）。
- 番組映像（HyperDeck・SW の mov）のカットと、記録の fade の跳びを突き合わせる。

  ```bash
  python "$S/camrec.py" match <カメラ記録.anim> "<番組映像の URL か パス>" --audio <2Mix> --audio-at <2Mix の start> \
      --clip <start>,<clipIn>,<ts> --at 300,1200 --dur 20
  ```
  - 窓ごとに、音で「映像 → Timeline」を測る → 映像のカットを Timeline の時刻にする → 一番近い記録の切り替えとのずれを出す。
  - 出力の `now:` が今の置き方のずれ（+ = 映像のカットが記録より遅い）。`to match` が合わせ直す clipIn・timeScale。
  - 番組映像は Dropbox の単体ファイルの URL（dl=1）を渡すと、窓の区間だけを読む（AZKi の 85.9 GB の mov で 20 秒 × 2 窓が 2 分）。
    共有フォルダの中のファイルは `dbx_shared.py url` で単体の URL を得る。
- 確かめた実績（AZKi、2026-10-15）: 映像 → Timeline は −0.131 / −0.133 秒（10/12 の測定 −0.132 秒）。
  今の置き方（clipIn 1.6157・ts 1.0000356）でのずれは平均 0.0 ms・最大 15.7 ms（10/12 の 15 カット最大 15.8 ms と一致）。
- プレビュー（OBS の mp4）は固定の引きの画で、カットが写っていない（Yamashita の 4 組）。カットは番組映像にしか無い。
- 番組のカットは記録の切り替えより約 0.1 秒早かった（MZM −0.095・春猿火 −0.130・りのん −0.095 → カメラのクリップをその分前へ）。

## レールのずれ（Override Track）

- `CameraRecordOverrideTrack`（サブモジュール）。クリップの Rail Offset はレール全長に対する割合で、記録の位置の最近点からレールに沿ってずらし、注視先を狙い直す。FoV のオフセットも持てる。
- レールのずれは、カメラごとに 1 本・全尺 1 クリップ（`Override CamNN <名前>`）。同じトラックにクリップを重ねるとブレンドされて重みが割れる。
  元の Camera Record Track より下に置く（上だと上書きされて効かない。traps-catalog/vortex.md）。
- **同じカメラの Override を 2 本のトラックに置くと、重なる区間では後に評価される 1 本だけが効く**。ミキサーは「記録値 + 自分のトラックのオフセット」でカメラを上書きする
  （CameraRecordOverrideTrack.cs の ApplyToBrain）。区間だけ向きを直す (aim) のトラックを足すときは、そのカメラのレール・FoV の値もクリップに入れる
  （`CamFollowProbe.SetRotationOverride` が重なる全尺のクリップから写す）。
- Override は回転（`rotationOffset`、カメラのローカルの yaw / pitch）も持てる。区間だけのクリップで、記録の向きが止まった所を直す（下の「追従の見え方・記録の止まり」）。
- 値は組ごとに違う（SinkaiFes2026 では AZKi の値が他の 3 組で合わず、春猿火・りのんは記録のままが最良だった。各組の値はプロジェクトの CLAUDE.md）。
  ショットごとにパンのずれがばらつくカメラ（SinkaiFes2026 の Cam05）は、1 つの値で直せない。

### 合わせ方（番組映像の絵と照合する）

- 方法: ショットの中ほどの時刻で、番組映像のコマと、Unity で rail × ズームの候補を撮った絵を比べる。
  - 点数 = キャラの重なり（YOLOv8 の人物マスクの IoU）+ 0.5 × キャラ以外の輪郭の一致（正規化相互相関）。
    キャラの大きさだけでは、ドリーで寄ったのかズームで寄ったのかが分からないため、トラスや床の線で見分ける。
  - カメラごとに、全ショットの点数の合計が最大の rail を採る。ショットごとの中央値より安定した。
- 一式（2026-10-14 に 4 組で動かした版。パス・Director 名・組の値は書き換えて使う。今回は再実行していない）:
  `scripts/camera_match/`
  - `shots.py`（記録 → ショットの一覧）
  - `shots_pick.py` / `pick_test.py`（カメラごとに長い順に選ぶ）
  - `match_rail.py`（撮影と採点）
  - `joint_key.py`（カメラごとの合計）
  - `run_group.sh` / `run_fine.sh`（粗く → 細かく）
  - `CamProbe.cs`（Unity 側。Play 中に候補を撮る。案件の Assets/_TempVerify/ へ）
  - `OverrideWrite.cs`（カメラごとの Override Track を書く。_TempVerify/Editor/ へ）
- 要るもの: Python の venv に `ultralytics`（YOLOv8m-seg の重み yolov8m-seg.pt を同じ場所に）・opencv・numpy。番組映像の URL。1 ショット約 26 秒。
- この PC では長く回すとロックできる物理メモリが減り、GPU を失う（traps-catalog/process.md）。`match_rail.py` は非ページプールの量で止まる見張り付き。
- 合わせる前に `camrec.py order` で並びを照合する。10/14 に MZM の 13・14 番が「記録の位置から撮っても何も写らない」と見え、レールでは直せない別の問題と判断して外した。
  翌日、原因はスイッチャーの並びが記録と違うことだと分かった（カーブが当たらず原点・画角 0）。

## 追従の見え方・記録の止まり（2026-10-16 AZKi）

- 再生は、記録の位置・向き・画角を毎コマ書き戻すだけ（Brain は無効、注視や追従を計算し直さない）。見え方は収録時のライブの追従そのもの。
  - AZKi の記録は 75 キー/秒（他の組 61〜62、みなとん 31）。値が動くのにタンジェント 0 のキーは 0%。記録の粗さでカクつくのではない（`camfollow.py keys`）。
- 「妙にリニア感が強い・張り付いて回る」（ユーザー、AZKi だけ）: 収録時のシーンの注視の減衰（Aim Damping）が 9・10・12 番で 0 だった（`CamFollowProbe.DumpLookat`）。
  - `camfollow.py lag` で、遅れ（相互相関）と画面の横の揺れを見る。AZKi の 9 番は揺れ 0.009（ほぼ画面の同じ位置に張り付く）・パン 13.9°/秒。
  - 番組カメラの向きの動きの角張り（角加速度 / 角速度。2026-10-16 の使い捨ての計算で、今の `camfollow.py` には無い）は AZKi 19.2・MZM 32.6 で、AZKi の方が角張ってはいない。
    違いは追従の遅れの有無。
  - 再生側で、追うカメラだけに指数の遅れを足す Follow Lag（Camera Record のクリップ）を作ったが、ユーザー「ラグ感の話は戻して良い」で戻した。
    サブモジュールの stash「Follow Lag（ユーザー指示で戻した 2026-10-16）」に残してある。記録のままにするのが今の方針（変えるなら聞く）。
- 記録の向きが止まってキャラが画面の外（19:37 の 14 番、2.6 秒）:
  - 原因: 14 番（Cam3 FF 2）の注視先の番号 4 のキャラが、AZKi 一人の間はいない。注視先が無いカメラは向きが動かず、そのまま記録される。
  - 探し方: `CamFollowProbe.Measure`（Play 中、キャラは Animation Track の番号 `#0` でも指せる）→ `camfollow.py offframe <csv> --until <キャラが増える時刻>`。
    外の割合 100%・向きの変化 0.00° のショットが止まり。AZKi は 0〜1309 秒でこの 1 つだけ。
  - 直し方: Play を抜けて（Edit モードで）`CamFollowProbe.SetRotationOverride(<Timeline>, <カメラ番号>, "開始:終了:yaw:pitch;...")` を呼び、
    区間だけ向きをずらす Override Track（`Override CamNN <名前> (aim)`）を置く → シーンを保存する（トラックのバインドはシーンにある。Play 中に結んだバインドは Play を抜けると消え、書き出しでは効かない）。
    シーンのコミットは unity-scene-merge で Director の塊だけ。そのあと Play で確かめる。
    量は `camfollow.py aim` の「yaw to center」を目安に、番組映像の同じコマと並べて決める（AZKi: −5.0° を目安に −4.1° を採った。1192.9〜1194.6 秒は −0.8°）。
    並べるコマは `ShotRunner.cs` で撮る（時刻を動かした直後の Render はキャラが前の時刻のポーズ）。
  - Remove Start Offset（AZKi・エルセとも On）を Off にしても直らない（試して戻した）。
- 記録とモーションの時刻のずれの疑いは `camfollow.py fit --cams <番号>`。Δ > 0 = カメラが Δ 秒遅れて追う（ライブの追従ならこちら）、
  Δ < 0 = カメラがキャラより先に動く（追従では起きない）。`lag` の符号も同じ（+ = 遅れて追う）。
  - AZKi の 9・10 番は全 14 ショットで Δ −0.067 秒・τ 0、`lag` は 9 番 −0.27 秒・10 番 +0.08 秒。カメラがキャラより 67 ms ほど先に動く形で当てはまる。
    カメラ記録（番組映像のカットで置いた）とモーション（プレビューの時刻で 0 秒）の時刻が 0.07 秒ほどずれている疑いがある。未確定で、直していない（2026-10-19 にレビューで読み違いに気付いた）。
