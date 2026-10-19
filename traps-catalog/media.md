# media の罠（カタログ）

OBS・ffmpeg・コーデック・映像/音声の取り込みと時刻・動画/音声/字幕ファイル・画面録画・映像送出（NDI/Spout）の罠の全件。

## ffmpeg

### ffmpeg の -t は直後の出力にしか掛からない
- 症状: 2 出力のうち片方が 9.7 秒長い。
- 原因: 出力オプションは出力ごとに付く。
- 対策: 各出力の前に -t を付ける。
- 実例: 2026-09-27 SinkaiFes2026
- 自動検出: 候補（`-map` が複数で `-t` が 1 回以下。出力の数を正規表現で数えられないので hook にはしない）
- 出典: SinkaiFes2026/log/claudeLog.txt:880, skills/vortex-timeline-export（各出力の前に -t を付けた例）

### NVENC の有無は -encoders ではなく 1 フレーム通して判定する／CQ 値は実測で決める
- 症状: 一覧に h264_nvenc が出ても GPU/ドライバ次第で使えない。CQ を当て推量で置いたら画質が CPU エンコードと揃わない。
- 原因: ビルドに含まれる ≠ 使える。CQ 値に由来が無かった。
- 対策: 起動時に実際に 1 フレームエンコードして判定し、どちらで動いているかを画面に出す。CQ は SSIM で CRF と突き合わせて決める（実測 CRF 18↔CQ 23 / 21↔26 / 25↔30）。
- 実例: 2026-09-13 / 2026-09-23 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:820, 902

### BtbN の FFmpeg ビルドには HAP エンコーダが入っていない
- 症状: "Unknown encoder 'hap'"。
- 原因: libsnappy が同梱されていない。
- 対策: gyan.dev の full ビルド（.7z）を使う。ライセンスは BtbN の GPL / LGPL を用途で選ぶ。
- 実例: 2026 ffmpegGui / 2026-02-17 XRCaliblator（ライセンス）
- 自動検出: 不可
- 出典: ffmpegGui:32-40, XRCaliblator:34, 45-48

### ffmpeg の HAP 出力にタイムコード/メタデータが混ざるとプレイヤーで再生できない
- 症状: 自作ツールの HAP だけ再生できない（AME の出力は再生できる）。
- 原因: timecode データストリーム・色空間/HDR メタデータの混入。
- 対策: `-map 0:v:0 -an -dn -map_metadata -1` を付ける。
- 実例: 2026 ffmpegGui
- 自動検出: 候補（patterns-io 案 P7: `-c:v hap` を含み `-map_metadata -1` を含まない）
- 出典: ffmpegGui:46-53

### BtbN の ffmpeg autobuild タグは消える → ダウンロードが 404
- 症状: ビルド時・実行時の ffmpeg ダウンロードが 404。
- 原因: BtbN/FFmpeg-Builds は新ビルドが出ると旧 `autobuild-YYYY-MM-DD-HH-MM` タグを削除する。
- 対策: 名前が安定した `latest` タグ（`.../releases/download/latest/ffmpeg-master-latest-win64-gpl.zip`）を使う。中身が変わるので SHA256 固定はできない（厳密にするならその時点で計算して埋めるか自前ミラー）。
- 実例: 2026-07-18 SRT-Blue
- 自動検出: 候補（patterns-io 案 P10: `BtbN/FFmpeg-Builds/releases/download/autobuild-`）
- 出典: D---Personal-Project-SRT-Blue/memory/installer-and-bundled-tools.md:19

### ffmpeg ametadata の `file=pipe\:2` はシングルクォートで囲う
- 症状: filtergraph の解析エラー。
- 原因: filtergraph のエスケープ規則。
- 対策: `file='pipe\:2'` と書く。
- 実例: 2026-07-19 SRT-Blue
- 自動検出: 候補（patterns-io 案 P9）
- 出典: SRT-Blue/log/claudeLog.txt:735

### ffmpeg ametadata のファイル出力はバッファされ、数 KB 溜まるまで出ない
- 症状: メーターが 3-4 秒に 1 回しか更新されない。kill するとバッファ分が失われる。
- 原因: avio 出力のバッファリング。
- 対策: `ametadata=...:direct=1` を付ける。
- 実例: 2026-07-19 SRT-Blue
- 自動検出: 候補（patterns-io 案 P8）
- 出典: SRT-Blue/log/claudeLog.txt:762-767

### 同じ pipe:2 に複数の ametadata / -stats を書くと行が混線する
- 症状: 行が文字化けし、断片行がログに漏れる。
- 原因: 別ストリームが同じ fd に任意位置で書く。-stats は CR 区切り、ametadata は LF。
- 対策: ametadata は 1 つに集約する。ログはホワイトリスト（本物の診断らしい行だけ）で拾う。行分割は `\r` と `\n` の両方に対応する。
- 実例: 2026-07-19 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:661, 743-744

### dshow のライブ音声は既定で ~0.3 秒チャンク
- 症状: Web カメラのマイクのメーターだけ遅い（~3Hz）。
- 原因: dshow の既定バッファ。
- 対策: `-audio_buffer_size 20`（ms）。
- 実例: 2026-07-20 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:769-774

### DirectShow で pixel_format を決め打ちすると OBS Virtual Camera が開けない
- 症状: "I/O error" でカメラを開けない。
- 原因: yuyv422 固定にしていたが、OBS Virtual Camera は NV12。
- 対策: pixel_format を指定しない（デバイス既定に任せる）。デバイス列挙は dshow のログではなく ICreateDevEnum で行う。
- 実例: 2026-02-17 XRCaliblator
- 自動検出: 不可
- 出典: XRCaliblator:86-88, 51-55

### 排他の USB カメラは getUserMedia と ffmpeg で同時に開けない
- 症状: プレビュー中は送信できない（I/O error）。
- 原因: デバイスの排他。
- 対策: ffmpeg が単一所有して tee で低解像度 MJPEG をプレビュー配信する。送信開始時に getUserMedia を解放する。
- 実例: 2026-07-19 SRT-Blue
- 自動検出: 不可
- 出典: SRT-Blue/log/claudeLog.txt:643-648

### ffmpeg の `volume` フィルタの enable は 1024 サンプル単位で切り替わる
- 症状: 試験素材の音の立ち上がりが最大 21ms 遅れ、正解データが 0.56 フレームずれた。
- 原因: フィルタのフレーム（1024 サンプル）単位で切り替わる。
- 対策: 試験素材は `aevalsrc` の式で作る。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 候補（`volume=[^"']*enable=`。試験素材以外では正しい使い方なので hook にはしない）
- 出典: DvcMCP/CLAUDE.md:70-71

## 取り込み（Media Foundation / DirectShow / 音声 API）

### Media Foundation: 同期 ReadSample はデバイス停止で返らない
- 症状: 停止処理が固まる。
- 原因: 同期の `ReadSample` がブロックしたまま戻らない。
- 対策: 非同期の読み手（IMFSourceReaderCallback）にし、停止要求を定期的に見る。
- 実例: 2026-09 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（映像）

### Media Foundation: 符号化器の起動に約 0.27 秒かかり、テイクの頭が欠ける
- 症状: どのテイクも頭が欠ける。
- 原因: エンコーダ生成が遅い。
- 対策: 収録開始前に先に知らせ、差さるまでのフレームを控える（Pending）。
- 実例: 2026-09 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（映像）

### NV12 の行ストライド/行数パディング（1080→1088 行）で色がずれる
- 症状: 1080p で色だけずれる（色差 PSNR 49dB→19dB）。
- 原因: 行長 > 幅、行数が揃えられている NV12 を、詰まった NV12 として渡した。
- 対策: 渡す前に詰め直す。
- 実例: 2026-09-23 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（映像）, Seq/log/claudeLog.txt:2856

### Media Foundation の到着時刻は揺れる。サンプル時刻を使う
- 症状: 33〜64ms の遅延揺れ。
- 原因: 到着時刻を使っていた。
- 対策: サンプル時刻（100ns 単位で QPC と同じ時計）を使う。1 秒以上離れていたら別時計として警告する。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（映像）

### DirectShow 専用の仮想カメラは Media Foundation に出ない
- 症状: 古い OBS Virtual Camera 等が一覧に無い。
- 原因: DirectShow にしか登録されない。
- 対策: 仕様として README に明記する。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/README.md:960-961

### cpal は WASAPI 共有モードのみ／共有モードはレートを選べない／ASIO は単一クライアント
- 症状: 44.1/48kHz の選択が効かない。DAW と同時に ASIO を使えない。
- 原因: 共有モードは Windows のミックスレート固定。ASIO ドライバは通常排他。ASIO SDK は再配布不可。
- 対策: 排他モードが要るなら `wasapi` クレート。ASIO は feature で分ける。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（音声）, Seq/README.md:942-944

### 再生速度を変えるだけでは音程が変わる
- 症状: 倍速再生で音が使い物にならない。
- 原因: タイムストレッチ無しのレート変更。
- 対策: 等速のときだけ鳴らす（または伸縮処理を入れる）。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（再生速度）

## 時刻・同期

### 時計を 2 系統混ぜると長時間収録で徐々にずれる
- 症状: 長時間でしか出ないずれ。
- 原因: ライブラリ提供のタイムスタンプ（midir のコールバック時刻など）を QPC と混ぜた。
- 対策: 受信直後・パース前に単一の monotonic 時計を取る。
- 実例: Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（時刻の扱い）

### QPC の絶対値をファイルに保存すると、再起動後に別の場所へ着地する
- 症状: アプリ再起動後、音声だけがタイムラインの別位置へ置かれる。
- 原因: QPC の基準は OS 起動ごとに変わる。
- 対策: ファイルに残す時刻はセッション相対にする。
- 実例: 2026-08 Sequence
- 自動検出: 不可
- 出典: Seq/CLAUDE.md（クロックマップに QPC の絶対値）

### 時間の格子をサンプル数へ丸めて積み上げるとドリフトする
- 症状: 16kHz で 1/120 秒 hop（133.3 サンプル）を丸めて積み、20 秒で 1 フレームずれた。
- 原因: 丸め誤差の累積。
- 対策: 各窓の中心を時刻から毎回丸めて求める。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP/CLAUDE.md:67-70

## 解析（音声・映像・字幕）

### 大津の方法の argmax は平らな最大の端（雑音側）を選ぶ／RMS 窓の半幅で無音が狭く見える
- 症状: 無音しきい値が雑音側に寄る。無音区間が 1 フレーム遅れて見える。
- 原因: argmax は平坦部の先頭を返す。RMS のぼけ。
- 対策: 平坦区間の中央を採る。ぼけ幅ぶん戻す。
- 実例: 2026-09-23 DvcMCP
- 自動検出: 不可
- 出典: DvcMCP/log/claudeLog.txt:23-25

### 音の立ち上がり検出で MAD を散らばりに使うと打楽器で潰れる
- 症状: 何でも拾う／サビに引っ張られて A メロを取りこぼす。
- 原因: 全体 1 しきい値は大音量部に引き上げられ、スパイク状の信号では MAD が 0 に潰れる。
- 対策: 局所の中央値を平常値とし、散らばりは「最大値 - 中央値」にする。
- 実例: 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP/log/claudeLog.txt:693-699

### 字幕の時刻書式（VTT の時省略・ミリ秒なし SRT）で 0 件が「成功」で返る
- 症状: 取り込み 0 件なのに成功扱いで、気付かず次工程へ進む。
- 原因: `hh:mm:ss[.,]mmm` の固定長パターン。
- 対策: 時とミリ秒を任意にし、0 件はエラーにする。同時刻の LRC 行はまとめる。
- 実例: 2026-09-16 AEMCP
- 自動検出: 不可
- 出典: AEMCP/log/claudeLog.txt:386-401

### 画像の判定は目視でなく画素値で測る
- 症状: 縮小キャプチャの四隅を「明るい」と誤読（実測 1）。可視化のため brightness を上げたら別要因の白飛びで判定が全部無意味に。
- 原因: 目視の偽陰性・偽陽性。可視化のための設定変更が別要因を混ぜる。
- 対策: 画素値を機械測定する。可視化のために設定を大きく変えない。
- 実例: 2026-08-24 / 2026-09-01 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609SuiseiTour26/log/claudeLog.txt:1602-1604, 2952-2955

### MediaPipe FaceLandmarker はアニメ顔を検出できない（0%）
- 症状: 顔検出率が 0%。重なったキャラを撮ると表情推定の基底に 2 人分が混ざる。
- 原因: MediaPipe は実写で学習したモデル。シーン内で 2 体が同じ座標に重なっていた。
- 対策: `lbpcascade_animeface` を使う（約 88%）。ベイクの前にキャラを離すか非表示にする。
- 実例: 2026-06-21 Ext_Haruluna（FacialDetector）
- 自動検出: 不可
- 出典: SL:1613-1616, 1664-1670

## 映像送出（NDI / Spout）

### Bloom でアルファが壊れる／プリマルチプライの不整合で NDI に黒フチ
- 症状: 透明背景が不透明になる。NDI 受信側で発光体の周囲に黒いフチ（Spout と Editor では出ない）。
- 原因: ポストプロセスが α を上書きする。`Blend SrcAlpha OneMinusSrcAlpha` で透明背景へ描くと α²。プリマルチプライのまま NDI（ストレート α 前提）へ送った。>1.0 の RGB が NDI の sRGB/UYVA 変換でエッジを壊す。
- 対策: シェーダは `Blend One OneMinusSrcAlpha` + RGB 事前乗算。ポストプロセス後に α を復元し RGB÷α でストレート化、送出前に `min(rgb, 1)`。
- 実例: 2026-03-07 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:2448-2500, MARQ-CAU 12 節

### Klak Spout/NDI: AddComponent した Sender はリソース未設定で NRE、sourceTexture が null だと Sender が作られない
- 症状: Spout ON で `Blitter.GetMaterial()` の NRE。直してもエラー無しで他アプリから見えない。
- 原因: `SpoutResources`（HideInInspector）が未設定。captureMethod=Texture で sourceTexture が null の間は CaptureFrame が即 return し、ネイティブ Sender が一度も作られない。
- 対策: Resources の SpoutResources/NdiResources を割り当て、有効化の時点で sourceTexture を先に入れる。低遅延が要るなら NDI は Camera キャプチャモード（実測 20-33ms → 10-17ms）。
- 実例: 2026-02-25 / 2026-03-21 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:2057-2095, 2299-2320, 2745-2770

## OBS / 画面録画（skill に記載）

### OBS の起動・終了の罠（作業ディレクトリ・sentinel・トレイ）
- skill screen-recording に記載（`bin/64bit` 以外から起動すると `Failed to find locale/en-US.ini`、強制終了で `.sentinel/run_*` が残り次回セーフモード = WebSocket 無効、`--minimize-to-tray` で閉じられない）。
- 実例: 2026-09-23〜27 screen-recording / vortex-timeline-export
- 自動検出: 候補（patterns-io 案 P4 `--minimize-to-tray`、P6 強制終了で sentinel を消さない）
- 出典: skills/screen-recording/SKILL.md「踏んだところ」

### OBS に GetInputPropertiesListPropertyItems を投げると本体が落ちる
- skill vortex-timeline-export に記載（罠 11。WebSocket だけ生き残り SaveSourceScreenshot が返らなくなる）。
- 実例: 2026-09-27 SinkaiFes2026
- 自動検出: 候補（patterns-io 案 P5）
- 出典: skills/vortex-timeline-export/SKILL.md 罠 11

### OBS の window_capture を exe で絞ると、同じ exe の別プロジェクトの窓を掴む
- skill screen-recording に記載（`priority: 1` = タイトル優先）。
- 出典: skills/screen-recording/SKILL.md「複数のウィンドウを並べて撮る」

### video-analyzer の extract_frames は結果が大きすぎて読めないことがある
- skill screen-recording に記載（20 秒強の 1920x1080 で 25 万文字超。ffmpeg の tile で 1 枚に並べる）。
- 出典: skills/screen-recording/SKILL.md

### モニタのスリープ復帰後に Unity・OBS・dwm が GPU を失い続ける／4K 録画で GPU 100%
- skill vortex-timeline-export に記載（罠 10・12。原因は未確定。止まったら Unity と OBS を閉じて PC を再起動）。
- 実例: 2026-09-26〜27 SinkaiFes2026
- 出典: skills/vortex-timeline-export/SKILL.md 罠 10・12, SinkaiFes2026/log/claudeLog.txt:909-917

### NVENC の CQ と CRF の対応は素材で変わる
- 症状: 「CRF 18 ↔ CQ 23」（2026-09 ftpDeck の実測）を当てはめたら、暗い背景にグラデーションと光の CG（ライブの書き出し）で SSIM が明らかに低かった。
- 原因: NVENC の CQ と x264 / x265 の CRF は尺度が違い、対応は素材の性質（暗部・グラデーション・ノイズ）で変わる。
- 対策: 書き出す素材に近いもので SSIM を測って決める。AutoLive（1280x720 のステージ）では x264 CRF 18 ↔ h264_nvenc CQ 12、x265 CRF 23 ↔ hevc_nvenc CQ 20。同じ画質で NVENC のファイルは 5〜8 倍。
- 実例: 2026-10-09 AutoLive（apps/autolive/src/export/ffmpeg.rs）

### 映像を標準入力から流すと -shortest が効かず、音が最後まで残る
- 症状: 生の RGBA を標準入力へ流し、曲を 2 本目の入力にして `-af apad -shortest` を付けたのに、1.5 秒の映像に 3.09 秒の音が入った（終了コード 0）。
- 原因: 標準入力（rawvideo）の映像では -shortest が音の側を切らなかった（ffmpeg 7.1 で実測）。apad で音が無限になるので、むしろ伸びる。
- 対策: 長さを式で決める。`-af apad=whole_dur=<フレーム数/fps>` と出力の `-t <同じ秒>`。範囲の頭は入力の前の `-ss`（PCM ならサンプル単位で合う）。曲の終わりを越えても無音で埋まる。テストは音の頭の位置と長さを ffprobe・デコードで見る。
- 実例: 2026-10-11 AutoLive（apps/autolive/src/export/ffmpeg.rs、tests/render_cli.rs）

### Demucs（htdemucs）で分けた歌声は 44.1 kHz になる
- 症状: 48 kHz の 2Mix から分けた vocals.wav を 48 kHz として読んだら、表情の記録の口と並べたグラフが後ろほどずれた。
- 原因: htdemucs のモデルは 44.1 kHz で、出力は入力の周波数によらず 44.1 kHz で書かれる。
- 対策: 周波数はファイルから読む（soundfile.info・ffprobe）。skill vortex-timeline-setup の `facial_gate.py` は ffprobe で読む。
- 実例: 2026-10-16 SinkaiFes2026（AZKi の 2Mix_AzKi_08.wav 48 kHz → vocals.wav 44.1 kHz・PCM_24）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-16 00:30
