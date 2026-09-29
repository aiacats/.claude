---
paths:
  - "**/*{osc,Osc,OSC,artnet,ArtNet,Artnet,dmx,Dmx,DMX,midi,Midi,MIDI,udp,Udp,UDP,natnet,NatNet,freed,FreeD,srt,Srt,SRT}*"
---
# protocol の罠

全件は ~/.claude/traps-catalog/protocol.md。ここは再発しやすいものだけ。

### Git Bash から OSC アドレスを渡す
`/fader/1` が `C:/Program Files/Git/fader/1` に化けて送られ、送信は成功、受信側は黙って捨てる。原因は MSYS のパス変換。→ `MSYS_NO_PATHCONV=1` を付け、送った文字列を print して確かめる。（実例: 2026-09-05 vortex_urp / 2026-09-06 OSC2MIDI）

### OSC の受信ハンドラは自分宛でなくても全部呼ばれる
uOSC の `onDataReceived` は全メッセージで呼ばれ、処理はリスナー数 × 受信レートに増える。→ 冒頭でプレフィックス判定して早期リターン、比較用アドレスは初期化時に作る（GC は unity-gc）。（実例: 2026-09-06 vortex_urp）

### Windows で同じ UDP ポートを共有すると片方にしか届かない
SO_REUSEADDR で 2 つ bind してもエラーは出ず、ユニキャストは 1 つ目にだけ届く（実測 20/0）。同一 PC の卓ソフトが 6454 を掴んでいても同じ。→ 受信口は 1 本にして内部で配る。`netstat` で listen を確かめる。（実例: 2026-06-06 totolive-202511 / 2026-09-15 Sequence）

### UDP の相手が居ないと recv が 10054 を返し続ける
ICMP port unreachable を Windows は次の recv の ConnectionReset として返し、受信ループが止まるかログが埋まる。→ 10054 は致命扱いせず続ける（SIO_UDP_CONNRESET を無効化）。（実例: 2026-02-21 natnet-recorder / 2026-08-05 2609SuiseiTour26 / 2026-09-03 Sequence）

### 受信専用ソケットに何も来ない
一度も送信していない UDP ソケットは Firewall の穴が開かず、Public プロファイルでは受信規則が無いと遮断される。→ データソケットから相手へ初回送信 + keepalive、受信規則とプロファイルを最初に確かめる。（実例: 2026-02-20 natnet-recorder / 2026-09-15 Sequence）

### UDP は取りこぼす。一括要求もしない
uOSC の送信キューは 100 件で古い順に捨て、1499 件中 113 件しか届かなかった。欠番の一括再要求や大量要求は相手が ping に答えられず切断判定になる。→ 分割送信・欠け検知と拾い直し・窓で区切った要求。（実例: 2026-08-27 / 2026-08-30 2609SuiseiTour26）

### 相関 ID の無い要求/応答はタイムアウト後にずれ続ける
遅れて届いた旧応答を次の要求の応答として消費し、以後 1 件ずつずれる。→ 送信中の要求を FIFO で持ち、タイムアウト分も残して孤児応答を捨てる。区切りは行の中身でなく位置で決める。（実例: 2026-06-03 QLCMCP / 2026-09-02 ftpDeck の HyperDeck）

### 外部プロトコルの定数は原典で照合する
NatNet の `NAT_REQUEST=7` は v1.x の名残（正は 2）で、コマンドが空応答になった。FTP の MLSD 対応は FEAT の MLST で判定。→ SDK のヘッダ・RFC で照合し、応答を受けて確かめる。（実例: 2026-04-26 SignalHub / 2026-09-02 ftpDeck）

### NatNet は keepalive を常に送り、接続は 1 本、ボーン ID は合成値
keepalive を設定次第で省くと約 10 秒で切られる。トラックごとに接続すると 2 本目以降が受けない。フレームのボーン ID は `(skel<<16)|bone` で、完全一致だと黙って T ポーズ。→ 常に 1 秒間隔で送る・購読で配る・下位 16bit で引く。（実例: 2026-09-03 / 2026-09-13 Sequence）

### loopMIDI のポートは常駐中しか無い
Windows に標準のループバック MIDI は無く、loopMIDI 未起動だとポート 0 本で MIDI 系が黙って反応しない（Unity の Minis も）。→ テスト前に常駐とポート数を確かめ、ポートは名前で保存する。（実例: 2026-09-06 OSC2MIDI / 2026-09-14 Ext_Palletproject）

### 自作の Art-Net 送信で受信側が反応しない・値が失効する
ヘッダは OpCode(0x5000) がリトルエンディアン、Length がビッグエンディアンと混在する。Art-Net は状態なので、送出が途絶えると受信ノードが出力を失効させる。→ エンディアンを分けて詰め、再生中は全ユニバースを一定レートで送り続ける。テスト送信は全ユニバースへ。（実例: 2026-09-06 lll-12 / Sequence）

### 受信スレッドで重い処理をすると後続を取りこぼす
OSC の合図で収録開始（ファイル生成）している間に続く合図を落とし、開始と停止の順序も崩れた。→ 受信はチャネルへ流すだけにし、実行スレッド 1 本で順に処理する。（実例: 2026-08 Sequence）
