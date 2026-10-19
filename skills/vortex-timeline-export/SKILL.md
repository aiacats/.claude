---
name: vortex-timeline-export
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、シーンの Timeline を動画（mp4）にして Dropbox へ上げる。「書き出して」「一回書き出して上げて」「Timeline を動画にして」「確認用に録って」「Display 4 を 4K で録って」と言われたとき、vortex-timeline-setup で Timeline を組んだあとに中身を見せるときに使う。録る Display と解像度の決め方、Unity を再生して OBS で画面録画する手順（4K 1 画面 / FHD 2 画面）、Recorder での書き出し（代わりの手段）、中身の確認、Dropbox への受け渡し、Unity が落ちたときの復旧までを扱う。
---

# vortex Timeline 書き出し

シーンにある Timeline（PlayableDirector）を、番組の出力（Display）のまま mp4 にして渡すまでの手順。

**本線は「Unity を再生して、その画面を OBS で録る」**（ユーザーの想定どおりの流れ。実時間で終わる）。
Unity Recorder での書き出しは、画面が使えないときの代わり（実時間の約 0.5 倍で遅く、Play 終了で落ちやすい）。

**いきなり全尺を回さない。** 画面の置き方・映り込み・解像度を OBS のスクリーンショットで確かめてから録る。
全尺は 1 本 15〜20 分。途中で間違いに気付くと、その分がまるごと無駄になる。

## 道具

`S=~/.claude/skills/vortex-timeline-export/scripts`

| 道具 | 用途 |
|---|---|
| `templates/RecGameView.cs` | **Unity 側**。案件の `Assets/_TempVerify/Editor/` へコピーして使う一時スクリプト。`PlaceDisplay`（Display を映す浮動 Game View を置き、描画の実寸を返す）/ `SetNoCameraWarning` / `PlayFromStart`（Timeline を頭から 1 回再生）/ `CloseAll` |
| `obs_rec.py` | **OBS 側**。`setup-4k` / `setup-dual` / `shot` / `edges`（上端・下端に Unity の枠やタスクバーが残っていないか）/ `restore`（setup 前の状態へ戻す） |
| `taskbar_autohide.ps1 on\|off\|get` | 録画中だけタスクバーを自動で隠す（4K 1 画面のとき必須） |
| `rec_watch.py <UnityのPID> <秒>` | 録画中の見張り。Unity のエラー・録画停止・ファイルが伸びないのを検知して終わる |
| `check.py <mp4...> --out <dir>` | 解像度・尺・中間フレームの輝度幅を出し、確認用 PNG を保存。無地なら終了コード 1 |
| `active_cameras.py <scene> --project <root>` | 実際に描いているカメラと、その出力 RT・画面に出している RT を出す（Unity 不要） |
| `preset.py` | Recorder 用プリセットの録画元と範囲を書き換える（手順 R） |

ほかに使うもの: `screen-recording` の `obs.py start/stop`、`windows-gui-testing` の `gui.ps1`（窓を Win32 で動かす・前面に出す）。

## 0. 始める前に確かめる（毎回）

1. **モニタの自動オフが「なし」になっているか**（`powercfg /q SCHEME_CURRENT SUB_VIDEO VIDEOIDLE` の AC が 0）。
   この PC ではモニタが一度スリープして復帰すると、その後 Unity・OBS・dwm が同時に GPU を失い続けた（罠 10）。
   「なし」でなければ `powercfg /change monitor-timeout-ac 0`（Git Bash からは MSYS がスラッシュを変換するので powershell 経由で）。
   既に一度スリープしていたら（System ログの Kernel-Power 566）、録る前に PC を再起動する。
2. **MCP の接続先**。`Library/ClaudeCodeMCP/endpoint.json` の `processId` が今の Unity か。
   別プロジェクトの Unity と 8090/8091 を分け合っていることがある。Unity を起動し直すと入れ替わる。
3. Unity・OBS は**メインのデスクトップ**で動かす（ユーザー指示 2026-09-27。仮想デスクトップでも録れたが既定はメイン）。
4. **DMX の Timeline を照明に乗せるなら、`MetaDmxReceiver`（LightControler）の Use Timeline が On か**。
   2026-10-05 以降（Submod mao/dev2 77e0a457〜）は手動のチェックだけで決まり、再生しても自動では切り替わらない。
   Off のまま録ると照明の無い動画になる。録り終えたら元の値に戻す。

## 1. 録る Display と解像度を決める

- 案件の出力は Display ごとに Canvas（ScreenSpaceOverlay）の RawImage で RT を表示している。**録るのは Display**（RT を直接ではない）。
- **その Display の Canvas が前提にしている解像度で録る**。Canvas が `Constant Pixel Size` で RawImage が固定サイズなら、
  Game View がそれより小さいと**中央だけが切り出され、寄った画に見える**（エラーは出ない。罠 7）。
  `get_component_properties` で `CanvasScaler.m_UiScaleMode` と RawImage の `RectTransform.m_SizeDelta` を見る。
- この案件（ShinkaiFes2026）の実測:

| Display | 中身 | Canvas / RawImage | 録る解像度 |
|---|---|---|---|
| 3 | カメラスイッチング（PGM/PRV 合成） | `System_GrandStage/Camera/Canvas/Output-Canvas/RawImage` 1920x1080 | FHD |
| 4 | 固定の全景（LED 前のステージ） | `Main Camera (1)/Canvas/RawImage` 3840x2160 | **4K** |

- 確認用でも**解像度は Canvas に合わせる**（FHD で足りるかどうかは中身次第。Display 4 を FHD で録ったら寄ってしまい、4K で録り直した）。

## 2. 映したくないものを消す

- **キャラごとに Timeline を分けているなら、各 Timeline に Activation トラックを持たせる**
  （クリップは 0 秒〜全長、`postPlaybackState = Revert`）。再生中の Timeline のキャラだけが出る。
- シーンに**最初から有効なキャラ**が残っていると全部に映り込む。書き出し用に複製したシーンで無効化して保存する。
- `RecGameView.PlayFromStart` は他の Director を止め、ループを実行中だけ切る。
- **出演者ごとの Timeline が並ぶシーン**（SinkaiFes2026 の Yamashita。使わない組の GameObject は無効）では
  `RecGameView.PlaySolo("<Director 名>", <開始秒>)`。書き出しの Solo（ExportSolo）でその組の Director とキャラだけを Play 中に有効にし、
  OptitrackSkeletonAnimator も止める（PlayFromStart の GameObject.Find は無効の Director を拾えない）。シーンは書き換えない。

## 3. OBS で録る（本線）

### 3-1. Unity 側

1. `templates/RecGameView.cs` を `Assets/_TempVerify/Editor/` へコピー → `AssetDatabase.ImportAsset` →
   `Library/ScriptAssemblies/Assembly-CSharp-Editor.dll` の更新時刻でコンパイルを確かめる
   （Unity が背面だと Refresh で拾わない）。
2. `invoke_method RecGameView.PlaceDisplay` で窓を置く。戻り値の `targetSize` が録りたい解像度か確かめる。
   - **4K 1 画面**: `PlaceDisplay(4, 0, -47, 3840, 2181)` → `targetSize=(3840, 2160)`
   - **FHD 2 画面**: `PlaceDisplay(3, 0, 100, 1920, 1101)` と `PlaceDisplay(4, 1920, 100, 1920, 1101)`
3. `SetNoCameraWarning(false)`（Canvas だけの Display に出る警告を消す）。
4. **4K 1 画面だけ**: Unity は窓を y&lt;0 に置けないので、Win32 で上へずらしてツールバーを画面の外へ出す。
   ```bash
   G=~/.claude/skills/windows-gui-testing/scripts/gui.ps1
   powershell -NoProfile -ExecutionPolicy Bypass -File "$S/taskbar_autohide.ps1" on      # 先にタスクバーを隠す
   powershell -NoProfile -ExecutionPolicy Bypass -File "$G" pin <RecDisplay4 の窓> -7 -78 3856 2246
   ```
   - 窓のハンドルは win-gui `list_windows` のタイトル `RecDisplay4`（初回は `Game` のこともある）。
     **一覧に出ないことがある**（2026-10-15、Win32 のタイトルが空だった）。そのときは EnumWindows で Unity の PID・タイトル空・
     主画面いっぱいの窓を探す（GetWindowText・IsWindowVisible・GetWindowRect。.ps1 は ASCII だけで書く）。
   - 78 は 4K での実測（窓の上端 → 描画の開始）。-7 / 3856 は Windows の見えない枠の分。
   - **タスクバーを切り替えると窓が y=0 に戻される**。必ずタスクバーを先に、pin を後に。
   - 常に最前面の常駐窓（時計など）と Unity の `SettingsPrompt` は別モニタへ退避する（`gui.ps1 pin` → `unpin`）。
     元の位置を控えておき、終わったら戻す。
     窓の位置がどのモニタにも入らない値（例: 時計 VTS が -1900,10）だと、主画面の下端中央に描かれて録画に映る（2026-10-15）。
     副モニタの内側の座標へ明示して置き直す（`gui.ps1 pin <hwnd> -1900 850 268 138`）。`shot` で消えたか確かめる。
5. Play に入る（`enter_play_mode` はドメインリロードで応答が切れる。`/mcp/tools/get_play_state` を 10 秒おきに見て待つ）。

### 3-2. OBS 側

```bash
python "$S/obs_rec.py" setup-4k        # または setup-dual --top 147（FHD 2 画面。147 は y=100 に置いたときの描画上端）
python "$S/obs_rec.py" shot <scratch>/check.png
python "$S/obs_rec.py" edges <scratch>/check.png   # 4K 1 画面のとき。NG ならツールバーかタスクバーが残っている
```
- 初回は `--monitor-id` が要る（既存の `ClaudeRec_Monitor` 入力があれば引き継ぐ）。
  利用者の既存の「画面キャプチャ」入力の monitor_id は、この PC では主画面（DISPLAY1）のものだった（2026-10-15 に EnumDisplayDevices で照合）。
  前日にそれを渡して真っ白だったのは ID 違いではない（原因は未特定。Git Bash の引数で `\\?\` が化けた可能性 = 罠 15）。
  **ID は Git Bash の引数で渡さず、Python から `subprocess.call([sys.executable, "<obs_rec.py>", "setup-4k", "--monitor-id", r"\\?\DISPLAY#..."])` で渡す**と通った。
  主画面の ID は Win32 の `EnumDisplayDevices(<\\.\DISPLAYn>, 0, ref dd, 1)`（1 = EDD_GET_DEVICE_INTERFACE_NAME）の `DeviceID`（`\\?\DISPLAY#...#{e6f07b5f-...}`）。
  .ps1 で書くなら BOM 付きか ASCII だけにする。`shot` が真っ白・真っ黒なら、まずモニタ違いを疑う。
  **OBS の `GetInputPropertiesListPropertyItems` でモニタ一覧を取らない**（OBS が固まって落ちた。罠 11）。
- `shot` の PNG を**自分で開いて**、映るべきキャラだけが映っているか・画角・余計な窓が無いかを見る。
  `RecGameView.PlayFromStart` で一度流して、キャラが出た状態で見ること（Timeline 前は板しか映らない）。

### 3-3. 録る

```bash
python ~/.claude/skills/screen-recording/scripts/obs.py start
```
直後に `invoke_method RecGameView.PlayFromStart("<Director 名>")`。
`rec_watch.py <UnityのPID> <尺>` を `run_in_background` で投げ、Monitor で末尾を 1 分おきに読む
（Monitor は 5 分で切れるので張り直す）。尺が終わったら `obs.py stop`（保存先が出る）。

### 3-4. 切り出す

- 4K 1 画面: `ffmpeg -i <録画> -t <尺> -c copy <名前>.mp4`
- FHD 2 画面: 左右を切り出す。**`-t` は直後の出力にしか効かない**ので、出力ごとに付ける。
  ```bash
  ffmpeg -i <録画> -filter_complex "[0:v]crop=1920:1080:0:0[l];[0:v]crop=1920:1080:1920:0[r]" \
    -map "[l]" -t <尺> -c:v h264_nvenc -preset p5 -cq 20 -an D3.mp4 \
    -map "[r]" -t <尺> -c:v h264_nvenc -preset p5 -cq 20 -an D4.mp4
  ```
- ffmpeg は `~/tools/ffmpeg-7.1-full_build/bin/`。

## 4. 中身を確かめる

```bash
python "$S/check.py" <mp4...> --out <scratch>/check     # 解像度・尺・無地でないか + 中間フレームの PNG
ffmpeg -hwaccel cuda -i <mp4> -vf "fps=10,freezedetect=n=0.001:d=3" -an -f null -      # 3 秒以上止まった区間
ffmpeg -ss 300 -t 60 -hwaccel cuda -i <mp4> -vf "scale=960:-2,mpdecimate" -an -f null -   # 60 秒中の変化コマ数
```
- PNG は必ず自分で開く。静止区間は絵を抜いて、白い板だけのカットなど**正当な静止か**を見る。
- 変化コマが 3,600 に対して 1,800 前後なら、Unity の描画は実質 30fps（4K で GPU 100% のとき実測）。報告に書く。

## 5. Dropbox へ上げる

```bash
rclone copyto "<mp4>" "dropbox:Claude/SinkaiFes2026/Timeline_<キャラ>_<テイク>_<中身>_<方式>_<yymmdd>.mp4"
rclone link  "dropbox:Claude/SinkaiFes2026/<同じ名前>"
```
- 動画の渡し先は **Dropbox**（ユーザー指示 2026-09-26）。リンク共有での公開もユーザー承認済み（動画のみ）。
- 数 GB あるので `run_in_background` で投げる。名前の例: `Timeline_Minaton_T001_Fixed_D4_4K_OBS_260927.mp4`

## 6. 後片付け

1. `obs_rec.py restore`（キャンバス・番組シーンを setup 前へ戻し、`ClaudeRec_*` を消す）
2. `taskbar_autohide.ps1 off`、退避した常駐窓を元の位置へ
3. `RecGameView.CloseAll()`、Play を抜ける、`Assets/_TempVerify/Editor/RecGameView.cs` を消す
4. `C:\Users\komao\Videos` の元録画を消す（切り出した mp4 は Dropbox に上げ終えてから）
5. モニタの自動オフは「なし」のまま（戻さない）

## R. Recorder で書き出す（代わりの手段）

画面が使えない（別作業で画面を占有できない等）ときだけ。実時間の約 0.5 倍で、**書き出し後の Play 終了で落ちやすい**（罠 3・9）。

案件の書き出しシステム（サブモジュール `Script/Editor/Export/`）を使う:
`TimelineExporterWindow.ExportAllInScene(presetPath)` がシーン内の Director を全部、プリセットで書き出す。
- 録画元が RenderTexture なら `preset.py <preset> --rt <guid> --test 300`（5 秒）→ `ImportAsset` → `ExportAllInScene`。
  RT の解像度で録られる（プリセットの Resolution は効かない）。録る RT は `active_cameras.py` で確かめる（罠 1・2）。
- Game View を録るなら `SourceKind=GameView`、`_gameViewDisplay` と `_resolution` を Canvas に合わせる（手順 1）。
  プリセットの `_description` に `: ` を含めるなら引用符で囲む（YAML として読めなくなる）。
- **`ImportAsset` を必ず挟む**（Auto Refresh が無効な案件では古い設定のまま録る）。
- 5 秒テストで `check.py` → 全尺。進み具合は `Recordings/` のファイルサイズで見る。
- `Recordings/` はコミットに混ぜない。

## B. 本番用を Timeline Exporter でまとめて書き出す（Batch・Solo）

納品用の ProRes をまとめて書き出すときの、案件の書き出しシステム（サブモジュール `Script/Editor/Export/`、2026-10-14 に足した機能）。

- プリセット: `Export/ExportPreset_<組>_D4_4K`・`_SW_FHD`（ProRes 422 HQ、範囲はモーションの尺）。ステージによって FHD だけ・録る Display が違う（SinkaiFes2026 の Prime は FHD・Display 3）。
- Batch: `Export/ExportBatch_<名前>.asset`（Timeline とプリセットの組の一覧）を Timeline Exporter の Batch 欄に入れて Add → Check → Export。
  Solo On のジョブは、その Timeline と、Animation トラックが指すキャラだけを Play 中に有効にし、他の組を無効にする（シーンは書き換えない。シーン上で無効の Director でもよい）。
  点検: Solo なら無効の Director は Info、キューの外で有効なキャラ付きの Director は警告。
- 容量の見積もり（点検に出る）: ProRes のデータレート（Apple の目標値 × 画素比 × fps 比）をドライブごとに合計し、5% の余裕込みで空きと比べる。足りなければ Error。
  実測は 4K 225 MB/s・FHD 57 MB/s（4 組 8 本で約 1.2 TB）。
- After Export: 別プロセスの FFmpeg で mp4 にして格納先へ（進捗の窓が出る。失敗なら理由を出して Enter 待ち）。FFmpeg が無ければ窓のボタンで %LOCALAPPDATA%\vortex\ffmpeg に入れる。
  格納先が書き出し先と同じだと mp4 が消えていた（fd3fcfe6 で修正）。手元の mp4 は消さない（ユーザー指示）。
- 書き出す前に、録る Display のカメラが有効か確かめる（Yamashita は Display 4 の Main Camera (1)・(3) と volume が無効で、D4 が真っ黒だった）。
- 確認用の倍速再生は `Window/vortex/Timeline/Timeline Speed`（x1 / x1.5 / x2。Play と Edit のプレビュー。Exporter の実行中は触らない）。

## 踏んだ罠

1. **`RT_Output` は誰も書かない**（2026-09-26）。`VirtualCameraSwitcher` の Blit がコメントアウトされていて、録ると黒い動画になる。
2. **複製したシーンではカメラ系が丸ごと無効なことがある**（2026-09-26）。`System_GrandStage/Camera` が非アクティブだった。
3. **Recorder で書き出した後の Play 終了で Unity が落ちる**（`c0000005`、2026-09-26〜27 に繰り返し）。
   録画ファイルは閉じ終わっているので中身は無事。OBS 方式で手で Play を抜ける分には落ちなかった
   （ただし Unity を**終了**するときに落ちたことはある。録画確定後なので影響なし）。
   落ちたら: Unity を `-projectPath` で起動し直す → **「Recovering Scene Backups」は `gui.ps1 focus <hwnd>` → Enter（Yes）**。
   待たずにすぐ押す（押すまで起動が止まる）。Unity Bug Reporter は送らずに閉じる。
4. **Recorder の中止**は `ExportRunner` の `Cancel(reason)`。インスタンスは
   `typeName="UnityEditor.ScriptableSingleton`1[[vortex.EditorTools.ExportRunner, vortexUtility.Editor]]"`, `methodName="get_instance"`。
5. **複数キャラを同じ位置に置いた Timeline 群**は、Activation トラックが無いと全員重なって映る。
6. 書き出したサイズがテストで**2 本とも完全に同じ**なら、中身が無地だと疑う。
7. **Canvas の前提解像度より小さい Game View で録ると、中央だけが切り出されて寄る**（手順 1。2026-09-27）。
8. **Fullscreen Editor（`FullscreenEditor.Fullscreen.MakeFullscreen`）での全面化は白いまま描かれなかった**。4K は手順 3-1 の「窓を上へずらす」で出す。
9. **Recorder の後に Unity を起動し直すと MCP のポートが入れ替わる**ことがある。`endpoint.json` の `processId` を見てから叩く。
10. **この PC はモニタのスリープ→復帰の後、Unity・OBS・dwm が同時に GPU を失い続けた**
    （`Failed to present D3D11 swapchain due to device reset/removed`。TDR の記録は出ない。2026-09-26〜27）。
    モニタの自動オフを「なし」にし、再起動してからは 18 分・16 分の 4K 録画が通った。
    ただし 09:38（スリープ無し）にも 1 回、待機中に同じ現象が出ていて、その秒に C: の Search 3079 が出ていた。
    原因は確定していない。**止まったら慌てず、Unity と OBS を閉じて PC を再起動する**のが確実。
11. **OBS に `GetInputPropertiesListPropertyItems`（モニタ一覧）を投げたら OBS 本体が落ちた**（WebSocket だけ生き残り、
    `SaveSourceScreenshot` が返らなくなる）。窓のタイトルが「OBS has crashed!」なら強制終了 →
    `%APPDATA%\obs-studio\.sentinel\run_*` を消して起動し直す。
12. 4K の画面録画では **GPU が 100% に張り付き、Unity の描画は実質 30fps 前後**になる（OBS の出力は 60fps のまま同じコマが 2 枚ずつ並ぶ）。
    確認用なら動きは追える。60fps が要るなら Recorder（手順 R）。
13. **vortex_urp の番組出力 Display 3（Output-Canvas）も黒い**（2026-09-30）。罠 1 と同じく `RT_Output` に誰も書かない。
    PGM の `RT_CameraA` に差し替えても、ライブ用ライトが DMX 無しでは消灯しているので影絵になる。
    キャラの動きの確認なら、Play 中だけ空き Display（例 6）に正面の一時カメラ＋全 Rendering Layer の白色 Directional を置いて録る（ユーザー承認済みの形）。
    カメラ距離はクリップの `RootT.x/z` の範囲（`AnimationUtility.GetEditorCurve`）から、全移動が 16:9 に収まるように式で決める。
    キャラを並べるのは Timeline の AnimationTrack の `trackOffset=ApplyTransformOffsets` と `position`（シーンの配置は触らない）。
    `OptitrackSkeletonAnimator` はポーズを上書きするので一時的に無効にし、終わったらシーンを保存せず開き直す。
    - **ポストプロセスを掛ける**（ユーザー指摘 2026-09-30）: 一時カメラに `Camera_PGM` の Camera と UniversalAdditionalCameraData を
      `EditorUtility.CopySerialized` で写す。ただし PGM 専用 Volume（レイヤー 24）の DoF は PGM の焦点のままなので全体がボケる。
      VolumeLayerMask は Default だけにする（MCP の update_component では `{"m_VolumeLayerMask": {"value": 1}}`）。
    - **寄り・角度の好み**（2026-09-30 Animax）: 1 人ずつなら「身長が画面の約 45%」（距離 = 1.65/0.45/2/tan(FoV/2)）。
      角度はほぼ水平が好まれ、最終は高さ 0.4m から体の中心を見上げる形。傾きだけ変えても、見下ろし角は「高さ / 距離」で決まるので見た目はほとんど変わらない。
      角度を詰めるときは、同じポーズ（Timeline 終了後の T ポーズ）のまま角度だけ変えた比較画像を出す。
    - 1 人ずつ録るなら、キャラごとに Timeline と Director を作り、Play 中に他のキャラを `SetActive(false)` して順に録る（1 回の Play で済む）。
    - **Unity が前面に無いと MCP が時間切れになる**（get_play_state まで）。MCP を呼ぶ直前に毎回 `focus_window` する。
14. **録画中に別アプリの窓が前面へ出てくることがある**（2026-09-30、ftpDeck の Settings）。尺が短くても、収録中に 1 回 `obs_rec.py shot` で写りを確かめる。
    `RecGameView.CloseAll` はタイトルが `Game` に戻った浮動 Game View を拾わないので、閉じ残しは「ドッキングしていない GameView」を閉じる。
15. **`obs_rec.py setup-* --monitor-id` を Git Bash から渡すと `\\?\` が `\?\` に化けて画が真っ黒**（2026-09-30）。
    `restore` はキャプチャ入力を消すので、次の setup で ID が要る。ID は OBS の既存の画面キャプチャ入力（GetInputSettings）か、
    `EnumDisplayDevices(..., EDD_GET_DEVICE_INTERFACE_NAME)` で取り、Python から `SetInputSettings` で入れる。setup 後に shot の輝度が 0 でないかを見る。
16. **OBS 録画が開始 1 秒で止まることがある**（`process_packet: Error writing packet: Invalid argument`、2026-09-30）。
    `obs.py stop` が 501 を返したらこれ。OBS のログで確かめ、録り直せば通る。OBS に「録画エラー」ダイアログが残る。

## 報告に入れるもの

- 録った Display・解像度とその根拠（Canvas の前提解像度）
- 各ファイルの解像度・尺・サイズ（`check.py`）、中間フレームの画像、静止区間と変化コマ数
- Dropbox のリンク
- 途中で落ちた / 復旧した場合はその経緯
- 一時的に変えた設定（タスクバー・退避した窓・OBS）と、元に戻したかどうか
- シーンに加えた変更と、コミットしていないもの
