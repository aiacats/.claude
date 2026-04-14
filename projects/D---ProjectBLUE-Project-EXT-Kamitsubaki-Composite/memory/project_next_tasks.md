---
name: 次回対応予定タスク
description: OfflineRenderRecorderのTimeline統合リファクタ（FrameRange切替・Director自動検出・RecordingSettings全体）
type: project
---

OfflineRenderRecorderのTimeline統合を簡素化するリファクタが必要。

**Why:** ユーザーから3つの要望:
1. FrameRange: Inspector指定 vs Timeline Clip 切り替え
2. TimelineDirector: シリアライズ変数から削除、Timeline Track/Clipがあれば自動検出
3. RecordingSettings全体: Timeline Clipが存在する場合、Clipの設定（解像度オーバーライド等）をRecordingSettings全体に適用

ユーザーの発言「上記はRecordingSettings全体にいえることです」= Timeline Clipがある場合はClipの設定が全面的に優先される設計にする。

**How to apply:**
- `_director` SerializedFieldを削除し、PlayableDirectorを自動検出
- Timeline Clipが存在する場合はClipのフレーム範囲・解像度オーバーライドを使用
- Inspector上でTimeline使用/手動フレーム指定を切り替えるUI
- MultiPassRecorderBehaviour/Clip/Track の連携を確認してから実装
