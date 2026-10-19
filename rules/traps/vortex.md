---
paths:
  - "**/vortex/**"
  - "**/Submod_RealtimeLiveUtility/**"
  - "**/Submod_RealtimeLighting/**"
  - "**/VF_*"
  - "**/OscRx_*"
---
# vortex の罠

全件は ~/.claude/traps-catalog/vortex.md。ここは再発しやすいものだけ。vortex-* skill の手順中の罠は各 skill を見る。

### 灯体が警告なしで動かない
DMX を受けても一部の ch が効かない。原因は VF_* 基底の黙った分岐: Profile は名前でなく添字で AddModeList に対応、Profile 無し・isLerp OFF は lerpPacket=0、モード名が重複すると TryAdd が ch を落とす（VF_Aura 26ch → 16ch）。→ Profile を AddModeList と同順にし（Generate Values from Script）、正規化 ch は isLerp ON、新灯体はモード名の一意性を確認。（実例: 2026-08-12, 08-25 2609SuiseiTour26）

### OSC の配線はシーンの Inspector にある
リファクタ後に OSC を送っても CameraSwitcher が動かない。原因は uOscServer.onDataReceived の配線が各シーンの永続リスナーで、実行時の AddListener を消すと無配線になること。→ 欠けたシーンに Inspector で足す（コードで購読すると他シーンで二重発火）。リファクタ後は各シーンの登録数を突き合わせる。（実例: 2026-07-11 vortex_urp）

### ArtNetReceiver は submodule 版に穴がある
複数卓の同一ユニバースが混ざる（送信元 IP を捨てて後着勝ち）、Bind IP を選んでも効かない（IPAddress.Any 固定）、一部 ch だけ送る卓で残骸を読む（512 固定コピー）。バインド失敗を即再試行して Editor が固まる。→ 2609SuiseiTour26 / lll-12 の修正版を移植する。（実例: 2026-08-04 2609SuiseiTour26 / 2026-09-24 lll-12 / 2026-06-01 LiveMultiRecorder）

### サブモジュールを先に push してからポインタを進める
他の環境でコンパイルが壊れる。原因は親だけコミットした、またはポインタだけ先に進めたこと。→ サブモジュールをコミット・push した後に親のポインタを更新。（実例: 2026-09-06 vortex_urp / 2026-09-14 Ext_Palletproject）

### OscRx_LipSync は Script Execution Order 24100
検証用に口の値を書いても 0 に戻る。原因は OscRx_LipSync が後から上書きすること。→ 検証用の注入は 30000 など後の順序、本番の付け替えは LateUpdate。（実例: 2026-09-27 Ext_TokinoSora_2026-pia）

### ライブ用の設定のまま新シーンへ持ち込むとキャラが真っ黒
キャラがシルエットになる。原因はキャラが Rendering Layer=Character のみで標準の Directional Light が当たらず、ライブ用 Volume の間接光も 0 なこと。→ Rendering Layer=Character のキャラ用ライトを一緒に置く。（実例: 2026-09-24 Ext_TokinoSora_2026-pia）

### Minis（MIDI）は入力ポートが無いと黙る
CharacterActivator などが MIDI に無反応。原因は loopMIDI 未起動で入力ポートが 0 だと Minis が InputDevice を作らないこと。→ 先に loopMIDI を起動（Unity の再起動は不要）。（実例: 2026-09-14 Ext_Palletproject）

### Override 系トラックは元トラックより下に置く
CameraRecordOverrideTrack が効かない。原因は Timeline が上から評価し、下の CameraRecordTrack が上書きすること。→ Override を下に置く。（実例: 2026-08-20 vortex_urp）

### リロードだけで出る改行差分をコミットしない
git に M が出るが中身の差分が無い。原因はドメインリロードで Crest の hlsl と codecoverage の Settings.json が再生成されること。→ リロード由来と報告し、コミットに含めない。（実例: 2026-09-14 Ext_Palletproject）

### ビルドでだけ全灯体が DMX に無反応
Editor では動くのにビルドで何も光らない（受信は開いている・エラーなし）。原因は submodule 版 VirtualFixture がモードを RefleshAttributeList の 2 回目で組み、ビルドでは OnValidate が無く 1 回しか呼ばれないこと。→ Start で `_profileState = Exist` にしてから呼ぶ（339876fc）。確認は `~/.claude/tools/artnet-send.py` で Art-Net を送り画面の輝度を比べる。（実例: 2026-10-01 SinkaiFes2026）

### 灯体が Art-Net に反応しないなら MetaDmxReceiver の Use Timeline を見る
受信は開いていてパケットも届くのに灯体が変化しない（エラーなし）。原因は DMX Timeline のプレビュー後に Use Timeline: On のまま保存され、ライブ受信を流さないこと。→ LightControler の Use Timeline を Off にして保存。Submod mao/dev2 77e0a457 以降は手動のチェックだけで決まる。（実例: 2026-10-05 vortex_urp）

### カメラ記録の再生で一部のカメラだけ真っ黒
番組カメラが原点・画角 0 になる（エラーなし）。原因は記録のカーブが「番号_収録時のカメラ名」で、再生側（CameraRecordSampler）は今のシーンのスイッチャーの並びと名前で当てること（収録後に並びや名前が変わった番号が外れる）。→ 記録の .anim のカーブ名とシーンの `_inputCameras` の並び・名前を比べ、シーン側を記録に合わせる（位置・向き・画角は記録の値なので、名前さえ合えばどの chief でもよい）。名前で当てる再生側の修正案は SinkaiFes2026_Media/camera-record-names.patch（未採用）。照合は skill vortex-timeline-setup の `camrec.py order`。並びを変えたら全組を照合する（MZM に合わせたらみなとんが黒くなった）。（実例: 2026-10-12 / 2026-10-15 SinkaiFes2026）
