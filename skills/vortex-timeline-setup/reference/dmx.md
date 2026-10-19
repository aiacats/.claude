# DMX（ArtNet の .dmx）と照明の明暗転

## .dmx を取り込んで Timeline に置く（2026-09-26 に固めた手順）

1. 中身を検分する（Assets に置く前）。148 MB の .dmx は取り込みに数分かかるので、壊れた物を入れて待たない。
   ```bash
   python "$S/inspect_dmx.py" "<path>.dmx"
   ```
   パケット数・収録時間・fps・ユニバース番号・形式の整合性が出る。「余りなし」でなければ取り込みが例外で失敗するので、報告して止まる。
2. `Assets/RecordedData/`（または案件の収録データ置き場）へコピー → `Assets/Refresh`（Auto Refresh が無効の案件）。
   ScriptedImporter（`DmxRecordDataImporter.cs`）が `DmxRecordData` に変換する。取り込めたかは `find_assets(filter="t:DmxRecordData")`。
   `*.dmx` は LFS。
3. Timeline に置く。`Window/vortex/Timeline/Timeline Composer` があれば、アセットを 1 つ入れるとトラックの種類とバインド先（MetaDmxReceiver）が自動で決まる。
   - フォルダの「選択」ボタン（OpenFolderPanel）はモーダルで Unity ごと止まる。テキスト欄に直接入力する。
   - Composer はサブモジュールのブランチによって無い。無ければ一時 Editor スクリプトで TimelineAsset を作り、`TrackBindingType` 属性からバインド先を引く。
4. `MetaDmxReceiver`（LightControler）の Use Timeline を On にして保存。Off のままだと Timeline を再生しても灯体は動かない（ライブの Art-Net が流れる）。
   ライブで卓から操作するシーンでは Off に戻す（On のまま保存してビルドすると卓が効かない。traps-catalog/vortex.md）。

| 事柄 | 中身 |
|---|---|
| 型 | `DmxRecordData`（ScriptableObject、`[PreferBinarySerialization]`） |
| トラック | `DmxTrack`（`[TrackClipType(DmxClip)]` / `[TrackBindingType(MetaDmxReceiver)]`） |
| 配り先 | `MetaDmxReceiver` → `OnMetaDmx`（UnityEvent）→ `FixtureController` / `LEDController` |
| ループ | PlayableDirector の wrapMode = Loop で行う。`DmxClip` は Looping を持たず、クリップの Extrapolation ではループしない |
| 形式 | `[uint32 seq][double time(ms)][uint32 numUniverses]` + N ×`[uint32 universe][512 byte]`。ヘッダー無し |

ループの確かめ: Play 中に Director の time を「全長 − 3 秒」にして、少しあけて読み、小さい値に戻っていればループ。
灯体に信号が流れたかは、数秒あけて撮った 2 枚で灯体の色が変わっていること。

## DMX の上から、特定のライトだけを暗転・明点させる（Light Intensity Track）

- MZM（2026-10-15）は収録の DMX でキャラ用ライト（`Character Directional Light`、VF_DRGB）が全編 255 の点きっぱなしで、他の照明が冒頭 61 秒暗転していてもキャラだけが照らされていた。
- VF_DRGB など DMX の灯体は Light の色（調光 × RGB）だけを Update で書き、強さ（intensity）は触らない。
  そこでサブモジュールの `LightIntensityTrack`（mao/light-intensity-track）で、Light の強さにクリップの区間だけ倍率を掛ける。
  - 区間に入ったときの強さを元として控える。
  - 区間を出た瞬間・一時停止・停止で、元の強さへ戻す。
- 色 × 強さを読むもの（案件の CharacterBloomByLight。NiloToon Bloom の Post-Bloom Result をキャラ用ライトに合わせて下げるポスプロの暗転）は、何もしなくても追従する。
- 明点の時刻とフェードの長さは、DMX から取る（`dmx_light.py`。時刻は `--dmx-at` に DMX のクリップの start,clipIn を渡すと Timeline の秒になる）。
  ```bash
  python "$S/dmx_light.py" switch <.dmx> --dmx-at 2.8,2.6667 --exclude 0:4-7      # 一斉に 0 から上がる瞬間（MZM: 61.53 秒に 302 ch）
  python "$S/dmx_light.py" ramp <.dmx> --dmx-at 2.8,2.6667 --exclude 0:4-7 --at 61.53   # その ch の上がり方 → 直線で上がり始め・終わり
  python "$S/dmx_light.py" luma <プレビュー.mp4> --p2t 0.15 --thr 30                  # 床（下の 1/3）が暗い区間（DMX と突き合わせる）
  ```
  - MZM は最大値が 61.45〜63.45 秒の直線（2.00 秒・127/秒）で上がった。10/15 に手で読んだ値（61.46〜63.43、Ease 1.97 秒）と 0.02 秒以内。
  - `--exclude` は上書きする灯体の ch（キャラ用ライト = universe 0 の 0 始まり 4〜7）。switch はその ch の値の幅も出す（MZM は全編 255）。
  - プレビューの床の明るさでも同じ時刻になった（61.3 秒から約 2 秒）。プレビューで暗い区間は 0〜61.8・296〜326・745〜786 秒（`luma`。帯の p5 18・p50 63 を見て閾値 30）。
  - 照明の合計で「暗い区間」を探す方法は使えない。Pan・Tilt・色など調光以外の ch が暗転中も 0 にならず、合計がほとんど変わらない（MZM で中央値の 5% を下回る区間が 0 個）。
- 既存の `LightDimmerTrack`（LightEmissionDimmerControl）は、DMX が色を書く灯体には使えない。Play 開始時の色 × 明るさで、色を毎フレーム書き戻す（DMX の色の変化が消える）。
- Timeline への置き方: DMX グループにトラックを 1 本。
  - クリップは 0 秒〜点き終わる時刻・level 0・Ease Out = フェードの長さ。
  - Ease の曲線は直線（`mixOutCurve = AnimationCurve.Linear(0,1,1,0)`。DMX の調光の直線に合わせる）。
- **ライトを Animation Track で動かさない**。書き出しの Solo は Animation Track のバインド先を「キャラ」とみなし、他の組を書き出すときにシーン直下の置き場（`Lighting (2)`）まで遡って無効にする。
- 確かめ方: Play で区間の中・フェードの途中・後の `Light.intensity` と、CharacterBloomByLight の `_factor`・`_applied` を読む（MZM: 30 秒で 0・0、62.445 秒で 0.5）。

## DMX が無いときの明暗転（Light Dimmer Track）

- きまゆ（Prime_modelSetup、2026-10-15）は DMX の記録が無く、DMX の灯体も RimLight（非アクティブ）だけだった。
  効いているのは `LightControl`（発光の Renderer 7 個）と `LightControl_Chara`（キャラ用 Light 7 灯、下限 0.15）。
  どちらも `LightEmissionDimmerControl`（MIDI CC 84）。
- サブモジュールの `LightDimmerTrack`（mao/light-dimmer-track 4c40f463）を 1 対象 1 トラックで置き、明るさのクリップで暗転・明転を組んだ。
  - 区間を抜けた瞬間だけ手放す。無効の間は書かない。
- 時刻と明るさはプレビューから決めた。
  - 床の発光の明るさを 30 Hz で測り、暗転・明転の時刻を拾った（今は `dmx_light.py luma` で同じことができる。--crop で床の写る帯を選ぶ）。
  - 中間の明るさは、Play で明るさを 0〜1 に振って同じ画角で撮り、全灯・暗転の 2 点で物差しを揃えて突き合わせた（A 0.44・B 0.52）。
