# Aether Project Memory

## Project Overview
- Vulkan (ash) + Rust + iced ベースのリアルタイム映像制作ソフトウェア
- After Effects / Notch 代替を目指すプロ向けツール
- クローズドソース

## Key Decisions
- Rendering: `ash` (Vulkan直接) — 最大限のGPU制御
- GUI: `iced` 0.13 — ダークテーマ、エンジニアチック
- 優先軸: Notch的リアルタイムノード処理優先
- 3D: フル3D（メッシュ、ライティング、PBR）
- Edition: Rust 2024

## Workspace Structure
```
crates/
  aether-core/    — 共通型（ID, Color, DataType, Error）
  aether-nodes/   — ノードグラフエンジン（factory, evaluation含む）
  aether-engine/  — Vulkanレンダリングエンジン（buffer, compute, renderer）
  aether-gui/     — icedアプリケーション（app, theme, views/）
```

## Current Phase
- 全基盤機能完了 + TouchDesigner的機能群 + パフォーマンス最適化
- 61ノードタイプ（Pixel/Calc/Object + CHOP + Lights + PostFX + Component + Plugin）
- Dirty Flag差分評価 + rayon並列評価 + Image メモ化キャッシュ
- Expression Engine（再帰下降パーサー、27関数）
- Vulkan Graphics Pipeline（ラスタライザ、Blinn-Phong）
- Console/Profiler/RenderQueue パネル
- 全24ノードタイプのGPUコンピュートシェーダ実装完了
- 次: SpoutOut実接続、NDI統合、より高度な3Dレンダリング

## Architecture Notes
- plugin_host: Arc<parking_lot::Mutex<PluginHost>>（スレッド間共有）
- renderer: Arc<parking_lot::Mutex<Option<Renderer>>>（非同期初期化）
- evaluator: Arc<parking_lot::Mutex<GraphEvaluator>>（永続化、prev_cache維持）
- export: std::thread::spawn + shared progress + iced::time::every Subscription
- evaluate_full(): graph引数は &mut NodeGraph（dirty clear用、呼び出し側はowned clone）
- 並列評価: topological_sort_bucketed() → rayon par_iter per bucket
- GraphicsPipeline: オフスクリーンVulkanラスタライザ（SceneUBO: MVP+4灯）
- cache/prev_cache: HashMap<NodeId, Arc<Vec<NodeValue>>>（メモ化ヒット時ゼロコスト）
- GPUバッファ: BufferPool（power-of-2バケット）+ DEVICE_LOCAL + ステージング転送
- ダブルバッファフェンス: CachedPipeline.fences[2] + frame_index(Cell)

## Known Issues (Rust 2024)
- パターンマッチングで暗黙borrowのderef不可（`&deg` → `**deg`）
- lifetime elision警告: `Element<Message>` → `Element<'_, Message>`
- iced::Text widgetはClone不可 → 直接再生成で対応

## iced 0.13 Notes
- Canvas::Program<Message> で type State = () を使用中
- pick_listはDisplay trait実装が必要
- button::secondary, button::danger でスタイル指定
