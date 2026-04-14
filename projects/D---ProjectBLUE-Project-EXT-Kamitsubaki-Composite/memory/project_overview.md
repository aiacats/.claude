---
name: プロジェクト概要
description: EXT_Kamitsubaki_Composite プロジェクトの基本情報と構成
type: project
---

Unity 6 (6000.3.7f1) URP プロジェクト。カミツバキスタジオ向けのリアルタイムライブ＋コンポジット用環境。

**Why:** ライブパフォーマンス収録とVFXコンポジットの両方に対応する統合環境。

**How to apply:**
- NiloToon シェーダー使用（トゥーンレンダリング、アウトラインパス、Cinematic Rim Light）
- CameraSwitcher系でライブ的なカメラワーク制御
- DMX/OSC でリアルタイム照明・トリガー制御
- MultiPassRenderer でオフラインEXR出力（コンポジット用）
- サブモジュール: Submod_RealtimeLiveUtility（書き込み禁止）
- VRM 0.x ベースのキャラクター管理
