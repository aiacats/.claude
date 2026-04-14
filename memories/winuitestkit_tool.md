---
name: WinUITestKit - UI自動テストツール
description: Windowsデスクトップアプリの自動UIテストライブラリ。実装後のUI動作検証に積極的に使用する。
type: feedback
---

Windowsデスクトップアプリ（Unity/Avalonia/WPF等）の実装後、UI操作の自動検証にWinUITestKitを積極的に使用する。

**Why:** GUIアプリのマウス操作・描画確認を自動化でき、手動確認に頼らず品質を担保できる。スクリーンショット撮影+画像読み取りで視覚的な確認も可能。

**How to apply:**
- 実装後の動作確認フェーズで、UIテストプロジェクトを作成して自動検証を行う
- 対象アプリが.exeとしてビルド・実行可能であれば、フレームワーク問わず使える
- Unityプロジェクトの場合はビルド済み.exeに対してE2Eテストとして使用

## ツールの場所

- **ソースコード**: `D:\_Personal\Project\WinUITestKit\`
- **NuGetパッケージ**: `D:\_Personal\NuGetLocal\WinUITestKit.*.nupkg`
- **ローカルNuGetフィード**: `D:\_Personal\NuGetLocal\`

## プロジェクトでの導入手順

### 1. nuget.config を追加（プロジェクトルート）
```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <packageSources>
    <add key="nuget.org" value="https://api.nuget.org/v3/index.json" />
    <add key="local" value="D:\_Personal\NuGetLocal" />
  </packageSources>
</configuration>
```

### 2. テストプロジェクトを作成
```bash
dotnet new console -o ProjectName.UITest
dotnet add ProjectName.UITest package WinUITestKit
```

### 3. テストコードを記述
```csharp
using WinUITestKit;

var config = new TestConfig
{
    AppPath = "path/to/app.exe",
    WindowTitle = "Window Title",
    LogDirectory = "log/",
    OutputDirectory = "test-results/",
};

var steps = new List<TestStep>
{
    new("操作名", "screenshot_name", async hwnd =>
    {
        var (cx, cy) = WindowHelper.GetPointInWindow(hwnd, 0.5, 0.5);
        await InputHelper.Drag(cx, cy, cx + 200, cy, MouseButton.Right);
    }),
};

var result = await new TestRunner(config, steps).RunAsync();
return result.IsPass ? 0 : 1;
```

## 提供API

- `InputHelper.Click(x, y, button)` — マウスクリック
- `InputHelper.Drag(sx, sy, ex, ey, button, steps, withShift)` — ドラッグ操作
- `InputHelper.Scroll(x, y, clicks)` — マウスホイール
- `InputHelper.KeyPress(vk)` — キー押下
- `WindowHelper.FindAppWindow(title, timeout)` — ウィンドウ検索
- `WindowHelper.GetPointInWindow(hwnd, relX, relY)` — 相対座標→画面座標変換
- `WindowHelper.CaptureScreenshot(hwnd, path)` — スクリーンショット保存
- `TestRunner.RunAsync()` — テスト実行（起動→操作→SS→ログ確認→レポート）

## 技術的注意点

- x64のINPUT構造体は `FieldOffset(8)` でユニオンを配置（4バイトパディング）
- 4Kディスプレイでは `SetProcessDPIAware()` が必須
- OpenGL/DirectX描画のキャプチャには `CopyFromScreen`（BitBlt）を使用
