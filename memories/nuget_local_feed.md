---
name: ローカルNuGetフィード設定
description: 自作ライブラリの共有に使用するローカルNuGetフィードの場所と設定方法
type: reference
---

自作NuGetパッケージの共有用ローカルフィード。

- **フィードパス**: `D:\_Personal\NuGetLocal\`
- 各プロジェクトの `nuget.config` に `<add key="local" value="D:\_Personal\NuGetLocal" />` を追加して利用

**How to apply:** 新しいプロジェクトで自作ライブラリ（WinUITestKit等）を使う場合、プロジェクトルートに nuget.config を作成してローカルフィードを追加する。
