---
name: win-gui MCP server
description: WinGuiMcp の場所と用途。Windows GUI 自動化（クリック/OCR/テンプレートマッチ等）が必要な時に利用
type: reference
originSessionId: 8ef2e761-a8af-4aea-a2c6-76fca81e526b
---
WinGuiMcp はフレームワーク非依存の Windows GUI デバッグ用 MCP サーバー（.NET 9製、18ツール）。

- 実行ファイル: `D:\_Personal\Project\WinGuiMcp\publish\WinGuiMcp.exe`
- ソース: `D:\_Personal\Project\WinGuiMcp\src\WinGuiMcp\`
- Claude Code 登録名: `win-gui`（user スコープ）
- ツール名前空間: `mcp__win-gui__*`
- 主要ツール: find_window, focus_window, screenshot, find_text, find_image, click, click_text, drag, drag_text, type_text, key_press, scroll, wait_for_text, wait_for_window, launch_app, kill_app, get_pixel_color, list_windows
- 用途: SendInput ベースの自動 GUI テストが Dock.Avalonia の動的レイアウトで座標特定困難だったため作成。OCR/テンプレートマッチで動的UIをデバッグ可能
