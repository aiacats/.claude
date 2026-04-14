---
name: ノード二重生成バグ（解決済み・検証完了）
description: コラボレートモードでStartServer+StartClientにより同一インスタンスでノードが二重生成される問題 → カスタムspawnハンドラーで解決・動作確認済み
type: project
---

## 問題（解決済み・2026-04-01検証完了）

コラボレートモードでノードを作成すると、同じノードが二重に生成されていた。

**根本原因**: `AdminRoomManager`が`StartServer()`でサーバー起動後、同一インスタンスから`ConnectToServer()`→`StartClient()`でクライアント接続。Mirrorはこれをホストモードではなくリモートクライアントとして処理し、`NetworkServer.Spawn()`時にサーバー側オブジェクトとクライアント側コピーの両方が同じシーンに生成されていた。

## 解決策

`NetworkNodeManager.RegisterSpawnablePrefabs()`にカスタム`SpawnHandlerDelegate`を登録。サーバーが同一インスタンスで稼働中の場合、`NetworkServer.spawned`から既存オブジェクトを返して再利用。リモートクライアントでは通常通り`Instantiate`。

**How to apply:** ネットワーク同期オブジェクト（ノード、接続線）の新規追加時はNetworkNodeManagerのカスタムspawnハンドラー経由でprefab登録すること。
