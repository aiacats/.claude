---
name: MocapSimulator Architecture Decision
description: Avalonia UI + OpenTK で構築するモーションキャプチャカメラ配置シミュレーターの技術選定と設計方針
type: project
originSessionId: 1bae8ebf-557a-4e5e-9409-fed7100eb0d8
---
## 概要

OptiTrack等のMoCap用カメラの配置を仮想空間上でシミュレーションし、マーカーの捕捉可能範囲を可視化するデスクトップアプリケーション。UIはUnity Editorをリファレンスとする。

## 技術スタック（確定）

- **UIフレームワーク**: Avalonia UI 12.0（クロスプラットフォーム: Win/Mac/Linux）
- **3D描画**: OpenGL ES 3.0（ANGLE/D3D11バックエンド, Avalonia OpenGlControlBase）
- **ドッキングパネル**: Dock.Avalonia 12.0 + **Dock.Avalonia.Themes.Fluent 12.0**
- **数学ライブラリ**: OpenTK.Mathematics 4.9.4
- **言語**: C# / .NET 8
- **パターン**: MVVM (CommunityToolkit.Mvvm)

## 重要なAPI注意点

- シェーダーは `#version 300 es` + `precision highp float;` を使用（ANGLE/D3D11のため）
- `IRootDock` → `Dock.Model.Controls` namespace
- `Orientation` / `Alignment` → `Dock.Model.Core` namespace
- DockControlに `Factory` プロパティのバインドが必要
- `DockFluentTheme` を `Application.Styles` に追加必須
- `[ObservableProperty]` は Dock.Model 型（IRootDock等）には使えない → 手動実装
- `GlConsts`にGL_LINES等が不足 → カスタム定数クラス `GL` で補完

## プロジェクト構造

```
MocapSimulator/
├── Controls/      - OpenGLビューポートコントロール
├── Dock/          - DockFactory
├── Models/        - データモデル
├── Rendering/     - GL描画（Shader, Camera, Grid, Room, Gizmo）
├── Services/      - LogService等
├── ViewModels/    - MVVM ViewModel群
└── Views/         - AXAML Views
```

## 実装フェーズ

1. ✅ 基盤 — 3Dビューポート（カメラ制御+グリッド）、部屋表示、UI骨格、ログ
2. カメラ — MoCapカメラ配置、視錐台描画、選択/Gizmo操作
3. 分析 — 被覆率可視化（半透明プロジェクション方式）
4. UI/UX — メニュー、プロジェクト保存/読込、カメラプリセット

**How to apply:** 次フェーズではこの構造に基づいてMoCapカメラ機能を追加する。
