# protocol の罠（カタログ）

OSC・UDP/TCP・Art-Net/DMX・MIDI/MTC・NatNet/Motive/VMC・FTP/HyperDeck・QLC+/Titan・FreeD・SRT など、通信とプロトコルの罠の全件。

## UDP / ソケット全般

### Windows で同じ UDP ポートを 2 つ bind すると、ユニキャストは片方にしか届かない（6454 の同居）
- 症状: 同じポートの 2 本目の受信口、または先にポートを掴んだ他アプリがあると、bind はエラーにならず黙って何も届かない。Art-Net では蛍光灯 DMX が点かない／不安定。
- 原因: SO_REUSEADDR の UDP ソケット 2 つに 127.0.0.1 宛ユニキャスト 20 通 → 1 つ目 20 / 2 つ目 0（実測）。同一 PC の卓ソフト（MagicQ の mqqt.exe、QLC+）が 6454 を同居 listen していた。
- 対策: 「同じポートを複数で共有して全員が受ける」前提を置かない。受信口を 1 本にして内部で配る。bind 成功を受信できる保証と見なさない。切り分けは NIC IP と DeviceAddress の一致 → `netstat` で該当 NIC:6454 の listen → 受信・適用コンポーネントが両方付いているか → デバッグ値が動くか。
- 実例: 2026-06-06 totolive-202511 / 2026-08-05 2609SuiseiTour26（QLC+ と 6454）/ 2026-09-15 Sequence
- 自動検出: 候補（`set_reuse_address\(true\)|SO_REUSEADDR|ReuseAddress`。マルチキャスト受信では正しい使い方なので誤検知が多い）
- 出典: Seq/log/claudeLog.txt:2678-2680, Seq/README.md:952-954, D---Personal-Project-totolive-202511/memory/dmx_fluorescent_arch.md:19-23, 2609SuiseiTour26/log/claudeLog.txt:808-812

### UDP の相手が居ないと Windows は recv に 10054（ConnectionReset）を返し続ける
- 症状: 相手不在の間 10054 が毎秒出てログを埋める／recv_from がエラーで受信ループが止まる／SocketException(ConnectionReset) の連発。
- 原因: ICMP port unreachable を Windows は次の recv の WSAECONNRESET(10054) として返す（SIO_UDP_CONNRESET）。
- 対策: 10054 を致命扱いせず受信を続ける。IOControl で SIO_UDP_CONNRESET を無効化する。送受信エラーは状態が変わったときだけログする。
- 実例: 2026-02-21 natnet-recorder / 2026-08-05 2609SuiseiTour26 / 2026-09-03 Sequence
- 自動検出: 不可
- 出典: natnet-recorder:372, 2609SuiseiTour26/log/claudeLog.txt:808-812, Seq/log/claudeLog.txt:2020-2021

### 受信専用の UDP ソケットにパケットが来ない（Windows Firewall / Public プロファイル）
- 症状: ハンドシェイクは通るのにデータポート(1511)に 1 パケットも来ない。別 PC からの OSC が届かない。
- 原因: データソケットから一度も送信していないので Firewall の穴が開かない。受信許可規則が無く、Ethernet が Public プロファイルだと既定で遮断。
- 対策: データソケットから相手へ初回送信（ホールパンチ）+ 1 秒間隔の keepalive。UDP 受信を使うアプリは受信規則の有無とネットワークプロファイルを最初に確認する。
- 実例: 2026-02-20 natnet-recorder / 2026-09-15 Sequence
- 自動検出: 不可
- 出典: natnet-recorder:170-190, Seq/log/claudeLog.txt:2682

### Windows のループバックアダプタではマルチキャストできない（10051）
- 症状: Multicast 再生が OS error 10051。
- 原因: loopback にマルチキャスト経路が無い。
- 対策: マルチキャストは LAN インターフェース経由で。同一 PC の検証はユニキャストで行う。
- 実例: 2026-02-24 natnet-recorder
- 自動検出: 不可
- 出典: natnet-recorder:498

### UDP は取りこぼす前提（uOSC のキュー 100 件・受信バッファ未設定）
- 症状: 灯体一覧 1499 台中 113 台しか届かない。書き込みが Unity 側で溢れる。
- 原因: uOscClient の maxQueueSize(100) 超過で古いものから捨てる。SO_RCVBUF 未設定。
- 対策: 欠けを検知して拾い直す経路と、送信側の分割送信を用意する。maxQueueSize を引き上げ + 自前キューで分割送信。受信は自前 UDP 実装で ReceiveBufferSize を 4MB に。
- 実例: 2026-08-05 / 2026-08-27 / 2026-08-30 2609SuiseiTour26
- 自動検出: 不可
- 出典: rules/app.md「通信・プロトコル」, 2609SuiseiTour26/log/claudeLog.txt:913-918, 2311-2317, 2543-2549

### 取りこぼしの再要求や一括要求を一度に投げると、それ自体がバーストになる／相手が ping に答えられず切断
- 症状: 欠番を全部要求して再び溢れる。1499 台ぶんの /vf/params を一度に投げ、Unity が 3 万件の応答を作る間 ping に答えられず切断判定。
- 原因: 窓の無い一括要求。
- 対策: 届いた数を見て窓を増減する再要求にする。一覧の終端は置き換えでなく統合。
- 実例: 2026-08-27 / 2026-08-30 2609SuiseiTour26（FixtureTuner）
- 自動検出: 不可
- 出典: rules/app.md「通信・プロトコル」, 2609SuiseiTour26/log/claudeLog.txt:2334-2345, 2591-2596

### UdpClient.ReceiveAsync().Result は毎パケット確保し、Dispose で待機を抜けない
- 症状: 44Hz × ユニバース数のゴミ。Play のたびに受信スレッドが残る。ソケット閉鎖例外が AggregateException に包まれ catch が効かない。
- 原因: 専用スレッドで同期受信するのに Task を使っている。running フラグだけでは ReceiveAsync を抜けない。
- 対策: Socket.ReceiveFrom + 使い回しバッファ（長さ 65507 = UDP 最大ペイロード。小さいと MessageSize 例外）。停止は Close()。
- 実例: 2026-08-04 / 2026-08-24 2609SuiseiTour26
- 自動検出: 候補（`\.ReceiveAsync\(\)\s*\.Result\b`、.cs。patterns-io 案 P12）
- 出典: 2609SuiseiTour26/log/claudeLog.txt:266-267, 1663-1686

### UDP の bind 失敗を即再試行して Editor が固まる
- 症状: Play 中に Editor 全体が固まる。
- 原因: 6454 の bind 失敗（別プロセス／前回 Play の残留ソケット）で例外 → 即再試行を無限に回す。
- 対策: 失敗は 1 回ログして止める。再試行は間隔を置く。Dispose でソケットを閉じる。
- 実例: 2026-06-01 LiveMultiRecorder（vortex ArtNetReceiver）
- 自動検出: 不可
- 出典: LMR-LOG:180-182

### 「送信先としてだけ使うポート」は bind されないので空きポート探索から見えない
- 症状: 映像が黒/破綻、ffmpeg に `timestamp discontinuity` が連続。無関係な 2 本の TS が 1 ソケットに届いていた。
- 原因: 空きポート探索が OS の bind 状態や使用済みマップしか見ず、送信先ポート（受け手がまだ居ない）を再び払い出した。OS の占有を確認せずに払い出して bind 失敗 → 黙ってカメラが消えた。
- 対策: セッション中に払い出した全ポートを bind 有無に関わらず台帳で管理し、破棄時に返却。払い出し時に OS の占有も確認し、失敗は UI に理由を出す。
- 実例: 2026-08-23 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:893-897, 820-821

### 特定 NIC に bind してもブロードキャストは受かる（同一ホスト実測）
- 症状: 「NIC 指定するとブロードキャストを取りこぼすのでは」という懸念。
- 原因: 実測で否定（ユニキャスト/ディレクテッド/リミテッドの 3 通りとも受信）。別ホストの卓からは未確認。
- 対策: NIC 指定を入れるなら現場で 1 回、実卓から確認する。
- 実例: 2026-09-24 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:430-434

### 受信スレッドから重い処理を直接呼ぶと後続を取りこぼす
- 症状: OSC の合図で収録開始（ファイル生成）している間、続く合図を取りこぼす。開始と停止が同時に走ると順序不定。
- 原因: 受信ループの中で同期実行している。
- 対策: 受信はチャネルへ流すだけにし、実行スレッド 1 本で順に処理する。
- 実例: 2026-08 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:1326-1329

### ブラウザアプリは UDP を開けない
- 症状: （設計）「OSC を受ける Web アプリ」は作れない。
- 原因: ブラウザから UDP ソケットは開けない。
- 対策: 常駐プロセス（Node サーバ / Tauri）を挟む。ユーザーが「Web アプリ」と言っても技術制約を説明して選んでもらう。
- 実例: 2026-09-06 OSC2MIDI
- 自動検出: 不可
- 出典: D---Personal-Project-OSC2MIDI/memory/osc2midi-purpose-and-environment.md:23

## OSC

### Git Bash から OSC アドレスを渡す（MSYS のパス変換で化ける）
- 症状: `/recorder/camera/start/0` が `C:/Program Files/Git/recorder/camera/start/0` になって送られる。送信は成功、受信側は該当アドレスが無いので黙って捨てる。
- 原因: MSYS2 が `/` 始まりの引数を POSIX パスとみなして Windows パスへ変換する。
- 対策: `MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'` を付ける。送信スクリプトで実際に送ったアドレスを print する。sys.argv は全部文字列なので、int を送るなら `i:3` のような型の接頭辞を送信スクリプトに持たせる。powercfg / taskkill / cmd など OSC 以外の同症状は traps-catalog/windows-shell.md。
- 実例: 2026-09-05 vortex_urp / 2026-09-06 OSC2MIDI / 2026-09-24（rules/app.md に追記）
- 自動検出: hook `osc-address-msys`
- 出典: rules/app.md「通信・プロトコル」, Notion 3d2e4d4b-751b-819b-b956-f631b1545ea1, 3d3e4d4b-751b-8156-aaad-f3ffd459b4ed

### OSC の受信ハンドラは自分宛でないメッセージでも全部呼ばれる
- 症状: リスナーを足すほど受信側が重くなる。
- 原因: uOSC の `onDataReceived` は全 OSC メッセージで呼ばれる。ハンドラ内の処理は「リスナー数 × 受信レート」に増幅される（FacialManager が 5 体 × 18 本 = 最大 90 回の文字列比較を全メッセージで回していた）。
- 対策: 冒頭でプレフィックス判定して早期リターンする。比較用アドレスは初期化時に組み立ててキャッシュする。GC の観点（Ordinal・補間・Debug.Log・計測）は traps-catalog/unity-gc.md。
- 実例: 2026-09-06 vortex_urp
- 自動検出: hook `cs-culture-string-compare`（GC 側）
- 出典: rules/unity.md「OSC 受信の作法」, rules/app.md「通信・プロトコル」, Notion 3d3e4d4b-751b-8114-908b-f20e662afb9a

### uOSC の values を (float) でキャストすると int 受信で例外になり受信ループが詰まる
- 症状: 受信が 1 フレーム 1 通しか処理されない。GC の大半が StackTraceUtility。
- 原因: uOSC は型タグ i を int で箱詰めする。`(float)values[n]` は int を受けると InvalidCastException、uOscServer は例外を捕まえないのでループが止まる。
- 対策: int / float の両方を受ける取り出し（OscArgs.TryGetFloat / TryGetInt）を使う。詳細は traps-catalog/unity-gc.md。
- 実例: 2026-09-14 SinkaiFes2026
- 自動検出: 候補（`\((float|int)\)\s*\w+\.values\[`。unity-gc 側で扱う）
- 出典: SinkaiFes2026/log/claudeLog.txt:128-157

### uOSC は受信 IF を指定できない／送信元アドレスが Message に無い／double を扱えない
- 症状: OSC の受信 IF を設定 UI で選ばせても効かない。返信先が分からない。
- 原因: uOSC は IPv6Any で全 IF を受信し、特定 IP へ bind する機能が無い。Message に送信元が載らない。onDataReceived はメインスレッドで呼ばれる（Unity API を直接触ってよい）。
- 対策: OSC はポートだけ設定させる。返信先は hello で明示させる。IF 指定や大きな受信バッファが要るなら自前 UDP 受信にする。
- 実例: 2026-06-02 LiveMultiRecorder / 2026-07 ExtOsc / 2026-08 2609SuiseiTour26
- 自動検出: 不可
- 出典: LMR-LOG:452, EXTOSC-LOG:211, 2609SuiseiTour26/log/claudeLog.txt:913-918

### 書き込み後の読み直し応答は遅れて届き、1 つ前の値で表示が戻る
- 症状: 連続操作中に表示が戻る。
- 原因: Unity は set のたびに読み直して返し、送信キュー越しに遅れて届く。
- 対策: 送信通数を数えて最後の 1 通への応答だけ反映する。応答が 2 回届く現象もあったので、値の同一性で判定する方が堅い。
- 実例: 2026-08-30 / 2026-09-08 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26/log/claudeLog.txt:2716-2719, 3640-3644

## Art-Net / DMX

### Art-Net は「状態」: 変化が無くても一定レートで送り続ける
- 症状: 送出が途絶えると受信ノードが出力を失効させる。
- 原因: Art-Net はイベントではなく状態。
- 対策: 再生中は全ユニバースを一定レートで送る（倍速時も 60fps）。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Art-Net）

### Art-Net のヘッダ: OpCode はリトルエンディアン、Length はビッグエンディアン
- 症状: 自作の送信スクリプトで受信側が反応しない。
- 原因: ヘッダ内でエンディアンが混在している。
- 対策: OpCode(0x5000) は LE、Length は BE で詰める。テスト送信は全ユニバース（例: 0..13）へ送る（0..7 だけで 690 灯体を取りこぼした）。
- 実例: 2026-09-06 lll-12
- 自動検出: 不可
- 出典: LLL-LOG:88, 105-112

### ArtPollReply は 1 通 4 ポートまで
- 症状: 多ユニバースで一部しか見えない。
- 原因: 仕様上 1 通 4 ポート。
- 対策: BindIndex を増やして複数通送る。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Art-Net）

### Unity_ArtNetRecorder の .dmx はヘッダ無し・時刻が等間隔でない
- 症状: 60fps を仮定すると時刻がずれる。
- 原因: 整数ミリ秒の Stopwatch を受信ループで読む（0ms の重複・550ms の飛びが混在）。先頭時刻は 0 とは限らない。マジックが無い。
- 対策: 記録時刻をそのまま絶対時刻に使う。キーフレームは経過時間で。毎パケット範囲検査して誤ファイルを弾く。
- 実例: 2026-08-30 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Unity ArtNetRecorder の .dmx）, Notion 3cce4d4b-751b-8151-a78f-e8a90742bf5c

### 差分記録のキーフレームを「予定時刻」で立てると、空のテイクで 1 つも書かれない
- 症状: 短いテイクがシークで一切復元できない。
- 原因: `frame % 間隔 == 0` の回がたまたま中身空で、記録ごと省かれた。
- 対策: キーフレーム要求を保留し、最初に中身が出たフレームで書く。読み手はキーフレームが無い場合に先頭から積み上げる。
- 実例: 2026-08 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（落とし穴）, Seq/log/claudeLog.txt:221-240

### 差分送信の Art-Net 再生はループ時にバッファを戻さないと、2 周目が前周の最終値から始まる
- 症状: ループ後の最初の値がおかしい。
- 原因: ReadAndSend は差分だけ更新する。部分的な Universe しか含まない収録では受信側に前周の値が残る。
- 対策: 巻き戻すときに `ResetBuffers()` を呼ぶ。必要なら blackout を送る。
- 実例: 2026-08-27 Unity_ArtNetRecorder
- 自動検出: 不可
- 出典: AL:33-35, 49-51

### vortex: Art-Net の受信長を見ずに 512 固定でコピーし、隣の領域を読む
- 症状: 一部チャンネルだけ送る卓で、隣の領域や前のパケットの残骸を読む（unsafe なので例外にならない）。
- 原因: ArtNetPacketUtillity.GetDmx が受信長を見ず dst.Length ぶん MemCpy していた。
- 対策: srcLength を渡し、届いた分だけ写す（2609 で修正済み 273d8be。他案件の submodule は要確認）。
- 実例: 2026-08-24 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26/log/claudeLog.txt:1677-1683

### vortex: ArtNetReceiver が送信元 IP を捨てて universe ごとに後着勝ち
- 症状: 複数卓が同じユニバースを送ると混ざる。全 FixtureController が全灯体を駆動する。
- 原因: metaDmxArray[universe] へ上書き。LightDeviceAssembly が全灯体を無条件に収集。
- 対策: [sourceIndex][universe] 化と DmxSource 許可リスト（2609 で実装済み）。電飾バッファ（DmxEmissiveBuffer）は先頭ソース固定だった点にも注意。
- 実例: 2026-08-04 / 2026-08-12 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26/log/claudeLog.txt:236-240, 1404-1405

### vortex: ArtNetReceiver は IPAddress.Any 固定で、Bind IP の設定がどこにも効いていない
- 症状: 設定 UI で Art-Net の受信 IP を選べるのに挙動が変わらない。
- 原因: submodule 版の受信器に、外から bind 先を渡す口が無い。lll-12 で `_bindAddress` を追加済み。他案件の submodule は未対応の可能性。
- 対策: 設定を足す前に、受信器まで値が届くかを確認する。NIC 指定を使うなら lll-12 版の MetaDmxReceiver/ArtNetReceiver を移植する。
- 実例: 2026-06-02 LiveMultiRecorder / 2026-09-24 lll-12
- 自動検出: 不可
- 出典: LMR-LOG:466-477, LLL-LOG:402-420

### vortex: MetaDmx には seq / timestamp が無く、パケットの到着を検出できない
- 症状: 受信メーターで、値が固定のルックだと「途切れ」扱いになる。
- 原因: MetaDmx は Universe + byte[512] のみ。鮮度は変化検出でしか取れない。
- 対策: 到着検出が要るなら受信器側に到着時刻を持たせる（submodule 変更）。現状は仕様として表示に明記する。
- 実例: 2026-06-02 LiveMultiRecorder
- 自動検出: 不可
- 出典: LMR-LOG:483-499

### vortex: Universe 繰り上げ判定の off-by-one（> 511 と > 512）
- 症状: Universe の末尾にちょうど収まる灯体まで次の Universe に送られ、末尾の ch が無駄になる。
- 原因: 収まる条件は s+count<=512。`nextChannel + count > 511` だと ==512 でも繰り上げる。AutoCountUp は満杯のときに ch だけ 1 に戻し、Universe を据え置いていた。
- 対策: `> 512` にする。満杯のときは Universe を繰り上げる。
- 実例: 2026-06-17 Submod_RealtimeLiveUtility（VirtualFixtureListWindow / LightingRepachChannel）
- 自動検出: 候補（`>\s*511\b`。一般の比較にも当たるので hook にはしない）
- 出典: SL:1298-1309

### vortex: VF_* の同じ packet を「シェーダー値（0〜0.5）」と「度数」の二用途に使うとスケールが合わない
- 症状: Zoom の packet は変化するのに spotAngle が 1 のまま動かない。
- 原因: VFP の Zoom は min -0.05 / max 0.5 / isLerp=1 で _ConeWidth 用のレンジ。それを spotAngle へ流用し 1 にクランプされていた。
- 対策: 0〜1 の lerpPacket と、専用の角度レンジ（_zoomMinAngle / _zoomMaxAngle）で度数を作る。
- 実例: 2026-06-17 Submod_RealtimeLiveUtility（VF_MobingBeam_E3）
- 自動検出: 不可
- 出典: SL:1356-1366

### vortex: Timeline を再生すると実受信の Art-Net が止まる（DmxMixerBehaviour）
- skill vortex-timeline-setup に記載（再生中の ArtNet の行）。原因（OnGraphStart が無条件に IsTimeline(true)）と修正は unity-timeline 分野。
- 出典: LLL-LOG:392-400, 436-440

## MIDI / MTC / HID

### Windows には標準のループバック MIDI が無い。loopMIDI のポートは常駐中しか存在しない
- 症状: MIDI 出力先が GS Wavetable Synth だけ／loopMIDI を入れたのに 0 本。Unity の Minis が InputDevice を作らず MIDI 系が黙って反応しない（Editor.log に `MidiInWinMM::initialize: no MIDI input devices`）。
- 原因: OS 標準の仮想ポートが無い。loopMIDI の仮想ポートは loopMIDI.exe の常駐中しか存在せず、未起動だと midiOutGetNumDevs にも出ない。
- 対策: 疎通確認・テストの前に loopMIDI の常駐を確かめる（`midiInGetNumDevs>0`）。ポートは番号ではなく名前で保存し、再スキャン導線と「loopMIDI を起動して」の案内を出す。既存の `loopMIDI Port` は他用途の可能性があるので専用ポートを作る。Minis は再スキャンするので Unity の再起動は不要。
- 実例: 2026-09-06 OSC2MIDI / 2026-09-14 Ext_Palletproject
- 自動検出: 不可
- 出典: Notion 3d3e4d4b-751b-8107-be87-c81ebd27b8fe, D---Personal-Project-OSC2MIDI/memory/osc2midi-purpose-and-environment.md:16-17, PL:21-30

### Windows 11 25H2 の WinMIDI Services(midisrv) が loopMIDI のポートを見失う
- 症状: loopMIDI の仮想ポートが Stream Deck / DAW から見えなくなる。
- 原因: midisrv が teVirtualMIDI 系の動的ポート追加を検出し損ねる（MS 公式の known issue）。
- 対策: MidiSrv を Disabled にする可逆スクリプト（tools/midisrv-toggle）。Windows Update で Manual に戻ることがあるので月次点検。Midi2 API を使うアプリは同じ機械で動かなくなる。
- 実例: 2026-05-04 StreamDeckMIDI
- 自動検出: 不可
- 出典: StreamDeckMIDI:3-11, 37-42

### Windows MIDI Services の SDK は NuGet.org に無い
- 症状: `Microsoft.Windows.Devices.Midi2` が restore できない。
- 原因: NuGet.org 未公開（2026-05 時点）。
- 対策: microsoft/MIDI の GitHub releases から nupkg を落としてローカル feed に登録する。
- 実例: 2026-05-03 StreamDeckMIDI
- 自動検出: 不可
- 出典: D---Personal-Project-StreamDeckMIDI/memory/winmidi_services_notes.md:11

### MTC のクォーターフレームは確定時に 2 フレーム進める
- 症状: 走行中だけ常に 2 フレーム遅れて追従する（停止中のフルフレーム SysEx では合っている）。
- 原因: クォーターフレームは 1/4 フレームごとに 1 通。8 通 = 2 フレームぶんの時間がかかる。
- 対策: 8 通目で組み上がった時刻に +2 フレーム（繰り上げ処理）。フルフレーム SysEx は補正不要。歯抜けと SysEx の判定に注意。
- 実例: 2026-09-03 Sequence
- 自動検出: 不可
- 出典: Notion 3d0e4d4b-751b-812d-bf08-eca1160ddc4d

### 「排他で掴むから共存できない」と実測せずに書いた（Stream Deck の HID）
- 症状: UI 文言とエラーメッセージに誤った前提を書き、訂正が要った。
- 原因: Windows の HID は共有オープンできる。問題は接続ではなく描画の奪い合い（後に書いた方が勝つ）。
- 対策: 制約は実測してから設計と文言に取り込む。
- 実例: 2026-08 SignalHub
- 自動検出: 不可
- 出典: rules/app.md「通信・プロトコル」, SH/log/claudeLog.txt:1001-1027

## NatNet / Motive / VMC

### NatNet のメッセージ ID を古い文書で書いた（NAT_REQUEST=7 は誤り）
- 症状: Motive へのコマンドが実行されず、空の MESSAGESTRING が返る。
- 原因: NatNet v1.x 時代の ID。正しくは REQUEST=2 / RESPONSE=3 / MESSAGESTRING=8 / UNRECOGNIZED_REQUEST=100。
- 対策: 外部プロトコルは SDK のヘッダ・公式ソースで照合する。旧コードのコメントを盲信しない。送るだけでなく応答を受けて解析する。
- 実例: 2026-04-26 SignalHub
- 自動検出: 候補（`\bNAT_REQUEST\b\s*(?::\s*\w+\s*)?=\s*7\b`。patterns-io 案 P11）
- 出典: rules/app.md「通信・プロトコル」, SH/log/claudeLog.txt:660-716

### NatNet の Ping は Remote Command ではなく NAT_CONNECT
- 症状: `Ping` に UNRECOGNIZED_REQUEST が返る。
- 原因: UNRECOGNIZED_REQUEST は未知の msg_id だけでなく未知のコマンド文字列でも返る。生存確認は NAT_CONNECT(0) → NAT_SERVERINFO(1)。
- 対策: Ping は CONNECT 経路に分岐する。
- 実例: 2026-04-26 SignalHub
- 自動検出: 不可
- 出典: SH/log/claudeLog.txt:720-775

### NatNet: フレーム側のボーン ID は `(スケルトンID<<16)|ボーンID` の合成値
- 症状: フレームは届いているのに姿勢が丸ごと T ポーズ。ログにも何も出ない。
- 原因: 定義（MODELDEF）は素の ID、フレームは合成値。完全一致で突き合わせて全部外れた。単体リジッドボディの ID は合成されていない（デコードを掛けると 65536 以上で壊れる）。
- 対策: スケルトン内ボーンだけ下位 16bit を取る（NatNet_DecodeID 相当）。追従ボーン数を画面に出す。
- 実例: 2026-09-03 / 2026-09-13 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Motive / NatNet）, Seq/log/claudeLog.txt:2107-2130, 2402-2409, Notion 3d0e4d4b-751b-8149-af69-dd12547802b0

### NatNet: キープアライブは配信方式によらず送る（約 10 秒で切られる）
- 症状: 約 10〜11 秒ごとにフレームが途絶え、再接続を繰り返す。
- 原因: こちら側の transport 設定でキープアライブ送信を決めていた。サーバがユニキャスト、こちらがマルチキャスト設定だと送らずに切断される。配信方式はサーバが決める。
- 対策: 常に 1 秒間隔で NAT_KEEPALIVE を送る。ソケットはコマンド/データを 1 本に統合し、0.0.0.0 に bind。
- 実例: 2026-02-20 natnet-recorder / 2026-09-03 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:1990-2012, natnet-recorder:170-190, Notion 3d0e4d4b-751b-8177-8ceb-d89d25191f8c

### NatNet: 接続は 1 本だけ。トラックごとにクライアントを立てると 2 本目以降が受けられない
- 症状: 2 本目以降のモーショントラックが何も受けない。
- 原因: 全員が同じデータポートを掴み、応答が 1 ソケットにしか届かない。
- 対策: 接続は 1 本、購読で配る。受信口の複製を配らない。
- 実例: 2026-09-13 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Motive / NatNet）

### NatNet はモデル記述が届いてからリグと容量を決める
- 症状: 実アクターではなく既定リグに乗り、マーカーが 8 個に切り捨てられる。
- 原因: 接続前の値でリグとバッファを構築していた。
- 対策: 記述の到着を検出してリグ・バッファを差し替える。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:71

### NatNet 4.1 未満は未対応のデータ型を安全に飛ばせない
- 症状: 推測で読み進めると以降のデータが全部ずれる。
- 原因: セクション長は 4.1 以降にしか無い。
- 対策: 4.1 未満でフォースプレート等を含む構成は明示的にエラーにする。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（Motive / NatNet）

### NatNetLib の Connect は非ループバック時に必ず 1510 に broadcast ソケットを張る
- 症状: 同一 PC の仮想サーバーに接続すると "Error initializing broadcast socket"。
- 原因: SDK は Unicast/Multicast に関係なく 1510 を bind する（127.0.0.1 のときだけスキップ）。Windows の SO_REUSEADDR は双方の設定が要るので共有できない。
- 対策: 仮想サーバー側のコマンドポートを別にし、Unity 側 `Connect(..., port)` を合わせる。データソケットはエフェメラル。
- 実例: 2026-02-24 natnet-recorder
- 自動検出: 不可
- 出典: natnet-recorder:504-524

### NatNet の service20 応答トークンは全ゼロ／同一 PC 接続は Motive でも loopback モードが要る
- 症状: NatNetLib が接続を拒否（~3ms で connection reset）。
- 原因: 非ゼロのトークンを返していた。同一 PC 接続は Motive でも loopback モードが必要。
- 対策: 実機の Wireshark キャプチャ（Npcap Loopback Adapter）と突き合わせてから実装する。127.0.0.1 + Unicast の 3ms 切断は未解決。
- 実例: 2026-02-21 natnet-recorder
- 自動検出: 不可
- 出典: natnet-recorder:385-420, 560

### Motive / FBX / BVH のボーン命名体系を 1 つの表に混ぜない
- 症状: 体のボーンがほとんど当たらない／混ぜると肩と上腕が入れ替わる／BVH 骨格で腕が 1 本ぶんずれて送出。
- 原因: `Chest` や `LeftShoulder` が体系ごとに別の骨を指す。Mecanim 表記（`Left Thumb Proximal`）と HumanBodyBones 名（`LeftThumbProximal`）も違う。
- 対策: 体系ごとに表を持ち、実骨格に最も当たる体系を自動選択してログへ出す。VMC は HumanBodyBones 名。
- 実例: 2026-09-03 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（VMC）, Notion 3d0e4d4b-751b-8123-9178-cf280687d52c

### Motive（右手系）→ Unity（左手系）の変換と T ポーズキャリブレーション
- 症状: 捻れた姿勢で送出される。
- 原因: 座標系の違い（既定は Z 反転）。キャリブレーション無しでは原理的に捻れる。
- 対策: 変換を入れ、UI で T ポーズキャリブレーションを案内する。Skeleton Coordinates = Local。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（VMC / Motive）

### 位置（配列インデックス）で相手を解決すると 1 人抜けた瞬間に全員ずれる
- 症状: VMC 受信で IndexOutOfRange。アクターが抜けると以降が別人のフレームになる。
- 原因: 受信で初めて宣言される相手を、事前に確保した配列の位置で扱った。
- 対策: id で宛先スロットを解決し、無ければ false を返す。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:539

## 要求 / 応答・制御プロトコル

### 相関 ID の無い要求/応答プロトコルで、タイムアウト後の遅延応答が次の要求に誤相関する
- 症状: 以降の応答がすべて 1 つずつずれ続ける。同時コマンドで応答がずれる。
- 原因: 単一 pending 方式で、タイムアウト後に届いた旧応答を次の要求の応答として消費した（QLC+ の WebSocket は request id 無しで、応答と push が同じソケットに来る）。待ち行列への登録と送信が別ロックだった。
- 対策: 相手が FIFO で応答する性質を使い inflight キューで管理する。タイムアウトしたエントリも `timedOut` 付きで残して孤児応答を消費・破棄。送信は直列化し、書き込みロックを保持したまま登録。切断時は全 inflight を reject。タイムアウト時はソケットを閉じて読み取りタスクを解放。回帰テストで固定。
- 実例: 2026-06-03 QLCMCP（2 回記録）/ 2026-09-03 ftpDeck
- 自動検出: 不可
- 出典: QLCMCP:44-52, D---Personal-Project-QLCMCP/memory/fifo-correlation-decision.md:11-24, ftpDeck/log/claudeLog.txt:123-130

### HyperDeck の応答は中身ではなく位置で区切る（待ち手のいない応答を通知にすると増殖）
- 症状: `clips get` の本体（`1: clip...`）で応答が 5 つに割れ、通知 → 取り直し → また割れる、で毎秒 400 回超・ログ 1 分 78 万行。
- 原因: 「行頭が数字なら新しい応答」という判定。
- 対策: 1 行目が応答行、`:` で終われば空行まで本体。待ち手のいない応答は通知にせず記録して捨てる。
- 実例: 2026-09-02 / 2026-09-06 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/CLAUDE.md:77, Notion 3cfe4d4b-751b-81df-8202-eccd2a6233f5

### FTP の MLSD 対応は FEAT の MLST で判定する（RFC 3659 7.8）
- 症状: 規格準拠のサーバで常に LIST に落ちる。
- 原因: FEAT に載るのは MLST（MLSD は載らない）。
- 対策: MLST または MLSD があれば MLSD 対応と判定する。
- 実例: 2026-09-02 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:50, Notion 3cfe4d4b-751b-81e5-b409-c55640281a30

### 機器とのセッションを黙って切ると機器側に残る
- 症状: 機器側にセッションが残留する。
- 原因: 切断手順の省略。
- 対策: 相手を替えるときは QUIT を通す。
- 実例: 2026-09-06 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:395

### 認証情報入り URL（ftp://user:pass@）がエラー文の途中にも出る／コマンドライン引数は他プロセスから読める
- 症状: ログと画面に機器のパスワードが平文で出た。rclone の RC 認証情報を引数で渡していた。
- 原因: redact が文字列の先頭だけを見ていた。引数は他プロセスから見える。
- 対策: ログ・画面へ出す前に文字列全体を走査して伏せる。資格情報は環境変数で渡す。
- 実例: 2026-09-13 ftpDeck
- 自動検出: 候補（`(log|println|info|warn|error)!?\([^)]*://[^)]*@`。誤検知が多いので hook にはしない）
- 出典: ftpDeck/log/claudeLog.txt:839, 873, 879

### 送受信で時間基準が違う（自前 Stopwatch の相対 tick）
- 症状: Pipeline latency が 395115949 ms。
- 原因: 送信側と受信側で時刻の基準が違った。
- 対策: 双方 `Stopwatch.GetTimestamp()` に統一する。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:49

### 受信レート = 1/間隔 を平均すると過大になる／起動直後の過渡値を公称レートとして掴む
- 症状: 240Hz が 251Hz と表示。起動直後の 162Hz を「普段のレート」と学習して偽アラーム。
- 原因: 1/x は凸なので平均の逆数と逆数の平均が違う。移動平均の立ち上がり。
- 対策: 間隔を平均してから逆数にする。公称レートは連続 2 サンプル一致で採用する。
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:53, 841

### Avolites Titan Web API の癖（set 本文は JSON・正式名一致・モード名の末尾空白）
- 症状: 500 エラー（"Unable to find value for parameter currentDmxSpacing" / "予期しない文字 'C'" / "Mode does not exist in show" / "Failed to get fixture from personality library"）。
- 原因: currentDmxSpacing は必須。set の POST 本文は JSON で文字列はクォート必須。Manufacturer・Model・Mode は正式名と完全一致（"Sinkai (User)"、"DRGB " の末尾空白）。FixtureModes は v16 でシリアライズ不可。Park しても UserNumber は解放されない。CurrentUserNumber は複合型 AcwUserNumber。
- 対策: 真因は WebAPI/rolledexceptionlog.log で確認する。名前は FixtureManufacturers/FixtureNames API で解決、モードは末尾空白付きでリトライ。
- 実例: 2026-06-05〜06 AvolitesRemote
- 自動検出: 不可
- 出典: AvolitesRemote:113-120, 141, 198-206, 262-271

### QLC+ の Virtual Console の Playback フェーダーは 0% スタート
- 症状: Chase を起動しても出力が 0。
- 原因: VC の Playback スライダーの初期値が 0%。
- 対策: 置かない。マスター調光は Grand Master に集約する。
- 実例: 2026-06-03 QLCMCP
- 自動検出: 不可
- 出典: QLCMCP:91-94

### FreeD の Position スケール係数は資料で /64 と /640 が混在
- 症状: 位置が 10 倍ずれる可能性。
- 原因: 仕様書による差。
- 対策: 実機で確認し、根拠をコメントに残す（未検証）。
- 実例: 2026-02 freed-decorder
- 自動検出: 不可
- 出典: freed-decorder:55-56

## SRT / 配信

### SRT over Tailscale は送受両方向で MTU 対策が要る
- 症状: 接続はするが映像を流した途端に切れる。mpv が黒画面でトラック未検出、サーバの bytesSent が配信の十数倍（大量再送）。
- 原因: SRT 既定ペイロード 1316（サーバ送出 ~1360B）が tailnet の MTU 1280 を超える。`pkt_size` は自分が送る側にしか効かない。
- 対策: publish は `pkt_size=1128`、read は `mss=1200`（MSS は両者の最小でネゴ）。人に配る URL にも付ける。
- 実例: 2026-07-19 / 2026-08-23 SRT-Blue
- 自動検出: 候補（`srt://` で `mss=` を含まない。Tailscale 経由かはコードから分からないので hook にはしない）
- 出典: SRT-Blue/log/claudeLog.txt:652-655, SRT-Blue/README.md:467

### mediamtx の `all_others` は既定で publisher を受理する
- 症状: prefix を間違えた publish が黙って成功し、discovery にだけ出ない。
- 原因: 設定コメントの「拒否」と違い、既定で受理される。
- 対策: 拒否したいなら明示的に認証/無効化の設定を書く。
- 実例: 2026-08-23 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:825
