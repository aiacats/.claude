---
paths:
  - "**/*.{mp4,mov,mkv,wav,flac,srt,ass}"
  - "**/*{ffmpeg,FFmpeg,Ffmpeg,obs,Obs,OBS}*"
---
# media の罠

全件は ~/.claude/traps-catalog/media.md。ここは再発しやすいものだけ。OBS の起動・終了は skill screen-recording。

### ffmpeg の -t は直後の出力にしか掛からない
2 出力のうち片方だけ 9.7 秒長くなった。原因は出力オプションが出力ごとに付くこと。→ 各出力の前に `-t` を付ける。（実例: 2026-09-27 SinkaiFes2026）

### NVENC は一覧に出ても使えるとは限らない
`-encoders` に h264_nvenc があっても GPU/ドライバ次第で失敗する。CQ を当て推量で置くと画質が CPU 版と揃わない。→ 起動時に 1 フレーム通して判定し、どちらで動くかを出す。CQ は SSIM で実測（CRF 18↔CQ 23 / 21↔26 / 25↔30）。（実例: 2026-09-13 / 2026-09-23 ftpDeck）

### HAP が作れない・再生できない
BtbN のビルドには HAP エンコーダが無い（Unknown encoder 'hap'）。タイムコードや色空間メタデータが混ざった HAP はプレイヤーで再生できない。→ gyan.dev の full ビルドを使い、`-map 0:v:0 -an -dn -map_metadata -1` を付ける。（実例: 2026 ffmpegGui）

### BtbN の autobuild タグは消えて 404 になる
新ビルドが出ると旧 `autobuild-YYYY-MM-DD-HH-MM` タグが削除され、同梱用のダウンロードが落ちる。→ `releases/download/latest/` を使う（中身は変わる）。（実例: 2026-07-18 SRT-Blue）

### 時計を混ぜると長時間収録で徐々にずれる
ライブラリのタイムスタンプを QPC と混ぜる、MF の到着時刻を使う（33〜64ms 揺れる）、QPC の絶対値をファイルに残す（再起動で基準が変わる）、のどれもずれの原因になった。→ 受信直後に単一の monotonic 時計を取る。MF はサンプル時刻。保存はセッション相対。（実例: 2026-08 / 2026-09 Sequence）

### 時間の格子をサンプル数へ丸めて積み上げるとドリフトする
16kHz で 1/120 秒 hop を丸めて積み、20 秒で 1 フレームずれた。ffmpeg の `volume` の enable も 1024 サンプル単位で切り替わる。→ 各窓の位置は時刻から毎回丸める。試験素材は `aevalsrc` で作る。（実例: 2026-09-23 DvcMCP）

### DirectShow のカメラが開けない・一覧に出ない
pixel_format を yuyv422 に決め打ちすると NV12 の OBS Virtual Camera が I/O error。DirectShow 専用の仮想カメラは Media Foundation に出ない。排他の USB カメラは getUserMedia と ffmpeg で同時に開けない。→ pixel_format を指定しない。所有者を 1 つにして tee で配る。（実例: 2026-02-17 XRCaliblator / 2026-07-19 SRT-Blue / Sequence）

### NV12 の行パディングで色だけずれる
1080p の NV12 は行長 > 幅、行数 1088 に揃えられていることがあり、詰まった NV12 として渡すと色差だけ崩れる（PSNR 49dB→19dB）。→ 渡す前に詰め直す。（実例: 2026-09-23 Sequence）

### Media Foundation の同期 ReadSample はデバイス停止で返らない
停止処理が固まる。同期の `ReadSample` がブロックしたまま戻らないため。→ 非同期の読み手（IMFSourceReaderCallback）にし、停止要求を定期的に見る。（実例: 2026-09 Sequence）

### ffmpeg ametadata の出力が遅れる・解析エラーになる
ファイル/パイプ出力は avio でバッファされ数 KB 溜まるまで出ない（メーターが 3-4 秒に 1 回）。`file=pipe\:2` は引用符が無いと filtergraph の解析エラー。→ `file='pipe\:2':direct=1`。pipe:2 に書く ametadata は 1 つに集約する。（実例: 2026-07-19 SRT-Blue）
