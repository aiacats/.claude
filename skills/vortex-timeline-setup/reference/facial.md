# 表情（VRMBlendShapeTrack）の記録と再生

## 仕組み

- 記録: `Recorder_VRMBlendShapeProxy` が、VRMBlendShapeProxy の各クリップの値を毎フレーム `animation_<名前>_<日時>.asset`（`vortex.VRMBlendShapeRecordData`、`_duration` 付き）に書く。
- 再生: `VRMBlendShapeTrack` → キャラの `VRMBlendShapeProxy`。クリップ `VRMBlendShapeClip` の `_recordData` に記録を入れる。
- 表情の書き手はキャラで違う。
  - AZKi など新しいキャラ: `vortex_FacialController`（パッド・LateUpdate で適用）+ `OscRx_LipSync`。
  - 旧キャラ: `FacialManager`（Update）。
- パッドの入力そのものは記録されない（記録は表情・カメラ・モーションだけ）。

## 踏んだ罠

- **口が音より遅れて記録される**（AZKi 0.56 秒・春猿火 約 0.28 秒）。表情のクリップの ClipIn で前へずらす。測り方は reference/sync.md の「表情」。
- **記録が表情だけ 1 フレーム遅れる・Timeline の再生を FacialController が上書きする**（2026-10-09〜10）。
  - 原因: Recorder は LateUpdate（-100）で読むが、FacialController の適用はその後。再生中は FacialController が LateUpdate で書き戻す。
  - サブモジュール 247615eb で直した。記録はフレームの終わり（WaitForEndOfFrame）で読む。再生中は `VRMBlendShapePlaybackGate` で FacialController が適用を休む。
- **画面では目を閉じているのに、記録に入っていない**（AZKi の RT = Metoji の目閉じ。2026-10-14）。
  - 原因: UniVRM は同じクリップへ 1 フレームに 2 回書くと、メッシュへは合計、`GetValue`（記録が読む値）へは最後の値になる。
    FacialController が RT の表情で Metoji = 押し込み量 → 続けて自動まばたきで Metoji = 0 と書いていた。
  - 直し: クリップごとに合計して 1 回だけ書く（サブモジュール c6efd0ae、mao/facial-write-once）。rules/traps/unity-runtime.md にも記録。
  - **収録の前に、この直しがチェックアウトに入っているかを確かめる**（`git -C <サブモジュール> merge-base --is-ancestor c6efd0ae HEAD`）。
    2026-10-19 時点で c6efd0ae は origin/mao/facial-write-once にしか無く、mao/dev2・作業中の mao/light-intensity-track・親の参照（38b9c813）には入っていない。
    入っていないまま録ると、RT の目閉じがまた記録から漏れる（後から `recover_rt_blink.py` で戻すことになる）。
  - 表情を調べるときは、`GetValue` とメッシュの重み（`SkinnedMeshRenderer.GetBlendShapeWeight`）の両方を見る。
    片方だけで「出ていない」と判断して直すと外す（ad1be3d5 は GetValue だけを見て直し、半押しが 2 倍に見えるようになった）。
- **既に録った記録から、漏れた目閉じを戻す**: 記録の Neutral（= 1 − 表情の最大。1 回だけ書かれるので正しい）から、
  記録に残る表情（Joy・Sorrow・ボタンのクリップ）で説明できない分を RT の量とみなして Blink に足す。
  SinkaiFes2026 の `tools/recover_rt_blink.py`。元の記録は残し、`*_RTBlink.asset` の複製を作って Timeline を差し替えた。
  確かめは映像の目閉じの時刻（復元値 1.0、直前 0）と、自動まばたきが復元区間に入っていないこと。
- 旧キャラの FacialManager も、同じクリップへ重ねて書く箇所があり、記録と見た目がずれうる（未確認）。

## 確かめ方

- Play で Timeline を止め、表情の値を時刻を変えて読む（Metoji のメッシュの重みなど）。プレビューの同じ時刻の顔と並べる。
- 再生中は `VRMBlendShapePlaybackGate` で FacialController が休むので、パッドの確認は Timeline を止めてから。

## 歌声が無い間の口を閉じる（2026-10-16 AZKi）

- 症状: 間奏・曲の合間で、口が小さく開閉する（ユーザー「歌声が無いのにパクパク」）。記録の口（A〜O の合計）が、歌声の無い間も 0.06〜0.28 動いていた。
  AZKi は 1:05・6:55〜7:02・7:45〜7:50・17:23 など。
- 直し方: 2Mix から歌声だけを分け、歌声が −50 dB 未満の間の口を 0 にした複製を作って、Timeline のクリップを差し替える（元の記録は残す）。
  1. 歌声を分ける（Demucs の htdemucs。CPU で 29.6 分の曲に 13 分 45 秒。GPU 版の torch は入れていない）:
     ```bash
     uv venv segenv --python 3.11
     uv pip install --python segenv/Scripts/python.exe torch==2.14.1 demucs==4.1.0 soundfile==0.14.0   # 2026-10-16 に動いた組（CPU 版の torch）
     segenv/Scripts/python.exe -m demucs --two-stems vocals -n htdemucs -o sep --int24 <2Mix.wav>   # → sep/htdemucs/<名前>/vocals.wav
     ```
     出力は 44.1 kHz になる（入力 48 kHz でも）。自前で読むなら周波数をファイルから取る（48 kHz と決め打ちしてグラフが 8.8% ずれた）。`facial_gate.py` はファイルから読む。
  2. 探す・確かめる:
     ```bash
     python "$S/facial_gate.py" scan <表情.asset> sep/htdemucs/<名前>/vocals.wav --facial-at <表情 start,clipIn> --audio-at <2Mix start,clipIn>
     ```
     `--show a-b` でその区間を 0.5 秒ごとに（口の値と歌声の dB）。
  3. 複製を作る: `facial_gate.py gate ...`（既定 −50 dB・前後の余白 0.15 秒・フェード 0.1 秒）→ `<元>_VoGate.asset`。
     初めは新しい GUID。作り直すと、既にある複製の GUID を引き継ぐ（Timeline の参照が切れない）。
     2Mix より前・後のコマ（歌声のファイルの外）は口を 0 にし、その数を出す（AZKi は 2Mix の始まる 7.83 秒より前の 468 コマ）。
     Timeline のクリップの記録の参照を差し替える（`CamFollowProbe.SwapRecordData(<Timeline>, <元>, <複製>)`。Play 中ならグラフも作り直す）。
  4. 確かめる。**gate と同じ閾値の scan で 0 件になるのは当たり前**（同じ判定で閉じたので）。それでは確かめにならない:
     - `tl_dump.py` で、表情のクリップの参照が `_VoGate` を指していること。
     - 緩い閾値の scan（`--mouth 0.02 --min-len 0.5`）で残りを見て、残った区間を `--show` で読む。
     - Play で、閉じた区間（AZKi なら 6:57）と歌い出しの直前・直後の口を見る（歌い出しが切れていないこと）。
  - AZKi の結果: 口の値の 3666 個（口の合計の 0.40%）が変わり、既定の scan の区間は 14 → 0。歌っている間の口は変わらない（境目の 0.15 秒の余白の外）。
- 先に RT の目閉じを戻した複製（`*_RTBlink`）があれば、それに掛ける（`*_RTBlink_VoGate`）。
