---
name: Kill before build/test
description: ビルドやテスト前に必ず既存のMocapSimulatorプロセスをkillする
type: feedback
originSessionId: 16837d83-ef3a-4ddf-baaa-c98e7e50f38e
---
ビルドやテスト実行前に、必ず既存の MocapSimulator.exe プロセスを kill してから実行する。

**Why:** exe がロックされてビルドエラー (MSB3027) になる。何度もリトライで時間を浪費した。

**How to apply:** `taskkill /F /IM MocapSimulator.exe` を dotnet build / dotnet publish / dotnet test の前に必ず実行する。
