---
paths:
  - "**/*.{uproject,uplugin,uasset,umap}"
  - "**/Source/**/*.{h,cpp,cs}"
---

# unreal の罠

全件は ~/.claude/traps-catalog/unreal.md。ここは再発しやすいものだけ。

### C++ ビルドが C3859 や 1455 で落ちる
"could not be compiled" で、UBT ログに C3859 / 1455 / C1076。原因は cl.exe 1 本 4〜6GB × コア数の同時並列（RAM 64GB でも起きる）。→ `%APPDATA%\Unreal Engine\UnrealBuildTool\BuildConfiguration.xml` に `MaxParallelActions=4` と `bAllowUBALocalExecutor=false`（5.6 は `ParallelExecutor.MaxProcessorCount` を無視する）。変えたら Intermediate / Binaries を消す。（実例: 2026-06 totolive_202511）

### 新しい UCLASS は Live Coding で入らない
追加したクラスが出てこない。→ `save_dirty_packages(True, True)` → エディタ終了 → `Build.bat ... -WaitMutex` → 再起動。（実例: 2026-06-06 totolive_202511）

### Sequencer Python の単位と引数順
section の `get_start_frame()` / `set_range()` は display rate、channel の `add_key` は tick（24000）で、混ぜると 400 倍ずれる。`unreal.Rotator()` の位置引数は (roll, pitch, yaw)。キーの無いチャンネルは 0 で、Scale=0 だと消える。spawnable へ Transform トラックを足すとクラッシュする。→ 秒の API、キーワード引数、`set_default()`、possessable を使う。（実例: 2026-06-07 totolive_202511）

### possessable は対象のレベルを開いて操作する
別レベルを開いたまま `add_possessable` すると重複 binding が元の参照を奪い、本番アニメの binding が空になる。→ 対象のレベルを開いてから操作し、binding は表示名でなく中身で特定する。（実例: 2026-06-07 totolive_202511）

### 大きなアニメを Python の反射で触らない
434 秒の mocap への `add_float_curve_keys` が 1 本 8 分超ハングし、24 万フレームの展開はクラッシュした。原因は呼ぶたびの全体再圧縮と反射のコスト。→ C++ の BlueprintFunctionLibrary で一括処理して Python から呼ぶ。（実例: 2026-06-07 totolive_202511）

### Blender 由来のアニメをリターゲットすると 90° 倒れる
ソースが Y-up バインドのため。回転の補正をアニメやリターゲットポーズに入れるとモーションが壊れる。→ 補正なしでリターゲットし、アクター側を回す。5.6 の Retargeter は新規だと `add_default_ops()` が要る。（実例: 2026-06-02 totolive_202511）

### PoseableMesh をボーン名で 1 本ずつ動かさない
`Set/GetBoneTransformByName` は毎回全身ポーズを作り直す（50 ボーン × 60fps で毎秒 6000 回）。→ RefSkeleton を 1 パスで舐めて `BoneSpaceTransforms` へ直接書き、最後に `MarkRefreshTransformDirty()`。（実例: 2026-08-24 MotionForge）
