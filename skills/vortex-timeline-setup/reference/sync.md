# 時刻合わせ（音・表情・DMX・モーション・VJ）

収録時の画（OBS プレビュー・番組映像）と同じ時刻に、各クリップを置く。道具は `scripts/sync.py`（Unity 不要）。

## 時刻の約束

- Timeline の時刻 T、プレビューの時刻 P、番組映像（HyperDeck・SW の mov）の時刻 S。
- クリップの中の時刻 x は `T = start + (x − clipIn) / timeScale`。`tl_dump.py` で今の start・clipIn・timeScale を読む。
- **基準はプレビュー（収録時に見えていた画）**。音（2Mix）をプレビューの音に合わせて T ⇔ P の対応を決め、他はそれに合わせる。
- プレビューの時計は音源とわずかに伸び縮みする（AZKi +32 ppm、春猿火 +54 ppm、りのん −24 ppm）。30 分で数十 ms なので、
  窓を 5 か所取って直線で当てはめる（`sync.py audio` が ppm と残差を出す）。

## 音（2Mix）

```bash
python "$S/sync.py" audio <プレビュー.mp4> <2Mix.wav または L.wav+R.wav> --b-at <2Mix の start>[,clipIn]
```
- 出力の `T−P` が全窓で 0 付近なら合っている（AZKi: −0.026〜+0.016 秒）。
- 2Mix は L/R の別ファイルで来ることがある。Timeline には L/R を結合したステレオを 1 本置く（AZKi・きまゆ）か、2 本の Audio Track に同じ位置で置く（Yamashita の 4 組）。
- 同じ組でも 2Mix の版が違うことがある（MZM: SoundData は ver2、Timeline は Take01）。プレビューと相関が高い方を採る。
- Vo（歌だけ）の wav が無音のことがある（きまゆ: 平均 −91 dB）。中身を確かめてから使う。

## 表情（口の遅れ）

```bash
python "$S/sync.py" mouth "<表情.asset>[+<2 人目.asset>]" <2Mix> --audio-at <2Mix の start>,<clipIn> --facial-at <表情の start>,<clipIn> --search=-3,3
```
- `--search` は `=` を付けて渡す（負の数が引数と見なされる）。
- 表情の記録は、口が音より遅れて記録される（AZKi 0.56〜0.57 秒、春猿火 約 0.28 秒）。出力の「facial clip: start − clipIn」になるよう ClipIn を入れる。
- 2 人で 1 本の 2Mix なら、2 人の表情を `+` でつないで口の合計で合わせる。
- どの記録がどのテイクかは、名前（T002 など）が当てにならない。候補ごとに相関を測り、区間ごとに同じ lag が出る方を採る
  （きまゆ: `T002_KImayu_20260923180257` が t003。7 区間とも同じ lag、もう 1 本は区間ごとにばらばら）。

## DMX

```bash
python "$S/sync.py" dmx <.dmx> <プレビュー.mp4> --p2t <T−P> --crop 0,0,0.05,0.75 --search=-5,5
```
- 画面全体の明るさは LED・VJ の映像に引っ張られて相関が出ない。灯体が写る帯を `--crop`（画面に対する割合）で選ぶ。
  AZKi は左端 5%・上 75%。
- 差分（明るさの変化）どうしの相関なので値は小さい（0.05〜0.1）。2 番目の山との比で見る（AZKi: 0.078 対 0.041、lag −0.067 秒 = 10/12 の測定 0.07 秒と一致）。
- DMX が無い組（きまゆ）は、プレビューの床の発光の明るさから暗転・明転の時刻を拾い、Light Dimmer Track で組んだ（reference/dmx.md）。

## モーション

- モーション（FBX）はふつう Timeline の 0 秒・ClipIn 0 で、プレビューと同じ時刻（AZKi・MZM・きまゆで確認）。
- 確かめるなら、プレビューのキャラの動きと、Unity で同じ画角を録った映像の動きの量を比べる。
  ```bash
  python "$S/sync.py" motion <プレビュー.mp4> <Unity の録画.mp4> --at 300 --dur 60 --guess <見込み> --range 3
  ```
  Unity の音が OBS に入らないときもこれで合う（MZM: 録画 = プレビュー + 0.55 秒、3 区間で一致）。
- 頭の高さと髪の上端の相関でも測れた（きまゆ: 0.00〜+0.03 秒、5 区間）。横方向は揺れものの遅れが乗るので使わない。

## VJ 映像

- VJ の動画に音が入っていれば、2Mix と相互相関して置く位置を出す（AZKi: VJ の 0 秒 = 2Mix の 1267.149 秒 = Timeline 1274.4189 秒。60 秒・200 秒で ±6 ms）。
  `sync.py audio <VJ.mov> <2Mix> --b-at <2Mix の start>` の `T` がそのまま Control Track のクリップの start。

## 組ごとの実測（SinkaiFes2026、2026-10）

| 組 | プレビュー → Timeline | 表情 | カメラ記録 | その他 |
|---|---|---|---|---|
| AZKi | T ≈ P（2Mix 7.27） | ClipIn 0.56 | ClipIn 1.6157・ts 1.0000356（番組 mov: T = S − 0.132） | DMX 0（+0.07）・VJ 1274.4189・エルセの登場 1309.4 |
| MZM | T = P + 0.15（0.134〜0.172） | — | 前へ 0.095 秒 | Remove Start Offset Off（On だと 2 人が中央で重なる） |
| 春猿火 | T = P + 2.258（+54 ppm） | 口 0.28 秒遅れ（未反映） | 前へ 0.130 秒 | |
| りのん | SW: T = S + 300.589（−24 ppm） | — | 前へ 0.095 秒 | プレビュー・DMX は t003、他は T002 の名前 |
| みなとん | SW: T = S − 0.042（−25 ppm） | — | 0.009 秒（入れていない） | |
| きまゆ | T = P（2Mix は 6.28 秒進める） | ClipIn 10.90 | — | DMX 無し → Light Dimmer |
