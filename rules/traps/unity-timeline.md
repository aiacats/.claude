---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
---
# unity-timeline の罠

全件は ~/.claude/traps-catalog/unity-timeline.md。ここは再発しやすいものだけ。

### PlayableDirector.Resume() は graph が無いと何もしない
Paused のまま時間が進まない（エラーなし）。原因は一度も再生していない director には PlayableGraph が無いこと。→ `playableGraph.IsValid()` で分岐し、無ければ `Play()` してから time を戻す。（実例: 2026-09-05 vortex_urp）

### トラックのバインドはミキサーで受ける
Timeline 再生で一部しか動かない。原因はバインド（playerData）がミキサーに渡り、クリップの ProcessFrame では null になること。→ `CreateTrackMixer` をオーバーライドしてミキサー側で駆動する。（実例: 2026-06-18 Submod_RealtimeLiveUtility）

### 自作クリップの clipCaps を None にしない
Split すると右側が頭から再生し直される。原因は ClipIn を宣言しないと clip-in が 0 固定になること。→ `ClipCaps.ClipIn | ClipCaps.SpeedMultiplier` にし、`input.GetTime()` でサンプリング。（実例: 2026-06-18 Submod_RealtimeLiveUtility）

### 毎フレーム記録したカーブがカクつく
収録中は滑らかなのに再生でカクつく。原因は `new Keyframe(t, v)` のタンジェント 0 と、四元数の q / -q の符号反転。→ 直前キーとの Dot が負なら反転、タンジェントは隣のキーへの傾き。（実例: 2026-06-18 Submod_RealtimeLiveUtility）

### URP で Recorder の入力を選ぶ
ActiveCamera 入力は開始時に失敗する（Built-in 専用）。RT 入力から PNG / EXR 連番を録るとアルファ 0 で全面透明になる。→ TargetCamera / RenderTexture 入力を使い、RT 入力なら JPEG か動画で録る。（実例: 2026-09-23 vortex_urp）

### 書き出しの終端を時間や frameCount で判定しない
Loop の Timeline を無限に録る、「失敗 0 件」なのにフレームが欠ける。原因は時間判定が終端を跨ぐことと、Game View が裏だと描画されないのに frameCount だけ進むこと。→ `SetRecordModeToFrameInterval` で Recorder に止めさせ、Game View を前に出し、`Time.renderedFrameCount` が進まなければ打ち切る。（実例: 2026-09-23 vortex_urp）

### Cinemachine 2 の Brain はレイヤーで候補を絞る
vcam を足すと PGM / PRV を奪う、または拾われない。原因は vcam のレイヤーと出力カメラの cullingMask で候補が絞られること。→ 番組外のカメラは専用レイヤーか Priority 0 にする。（実例: 2026-08 vortex_urp）

### Foot IK On で膝が数フレームだけ反対へ跳ねる
Foot IK Off で跳ねは消えるが膝が常に反る。原因はクリップの膝のマッスル（Lower Leg Stretch）が上限 1 を超え、FK の膝が逆折れしていること（IK がときどき反った側の解を選ぶ）。→ Foot IK を切らず、マッスルを 1 以下に抑える。まずクリップのマッスルの最大値を読む。（実例: 2026-10-14 SinkaiFes2026 春猿火・MZM）

### 2 人以上の収録モーションは Remove Start Offset を Off
On（既定）だと 2 人とも舞台の中央に重なる（エラーなし）。原因はクリップの最初のルートを打ち消して原点から始めること。→ 複数人のクリップは Off、FBX は keepOriginal*。（実例: 2026-10-14 SinkaiFes2026 MZM）

### Timeline を動かした直後に撮ると、キャラだけ前の時刻のポーズ
カメラの位置・向きはその時刻なのに、キャラの腕・脚が 1 枚前の時刻の形で写る（エラーなし）。原因はスキンメッシュの形が次のコマで更新されること（Evaluate では骨だけ動く）。→ その時刻のまま数コマ回して `WaitForEndOfFrame` で撮る（skill vortex-timeline-setup の `ShotRunner.cs`）。最初の 1 枚を参照映像と並べて確かめる。（実例: 2026-10-16 SinkaiFes2026）
