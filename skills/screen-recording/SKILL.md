---
name: screen-recording
description: OBS で画面を録画して mp4 にし、共有用 Drive へ上げてリンクを渡す。静止画では伝わらないもの（操作の流れ、動きの違和感、easing、応答の遅れ、再現手順の実演）を見せるときに使う。「録画して」「動画で見せて」「動きを確認したい」と言われたとき、または UI の動きが関わる報告をするときに使う。
---

# 画面の録画（OBS）

止め絵で足りるなら撮らない。**動きが論点のときだけ**録る（操作の流れ、アニメーションの詰まり、
応答が返るまでの間、再現手順の実演）。

## 決まっていること

| 項目 | 値 |
|---|---|
| 実行ファイル | `C:\Program Files\obs-studio\bin\64bit\obs64.exe` |
| **起動時の作業ディレクトリ** | `C:\Program Files\obs-studio\bin\64bit`（**必須**。別の場所から起動すると `Failed to find locale/en-US.ini` で止まる） |
| 保存先 | `C:\Users\komao\Videos` |
| 形式 | **mp4**（ユーザー指示 2026-09-23）。`basic.ini` の `RecFormat2=mp4` |
| 制御 | obs-websocket 5.x / `127.0.0.1:4455` / 認証あり |
| 設定ファイル | `%APPDATA%\obs-studio\plugin_config\obs-websocket\config.json` |

パスワードは上の設定ファイルの `server_password` にある。**スクリプトが自分で読むので、
コマンドラインや会話へ書かない**。

## 手順

```bash
S=~/.claude/skills/screen-recording/scripts

# 1. OBS が起きているか・録画中かを見る
python "$S/obs.py" status

# 2. 起きていなければ、bin/64bit から起動する（cd を忘れない）
#    --minimize-to-tray は付けない。トレイに入ると閉じる手段が無くなる（下の罠）。
(cd "C:/Program Files/obs-studio/bin/64bit" && ./obs64.exe > /dev/null 2>&1 &)
sleep 15

# 3. 録る
python "$S/obs.py" start
#    …ここで対象を操作する…
python "$S/obs.py" stop      # 保存されたファイルのパスが出る
```

撮った mp4 は **自分で確認してから渡す**。狙ったものが映っているか（対象のウィンドウが入っているか、
操作が写っているか）を見る。**`video-analyzer` の `extract_frames` は結果が大きすぎて読めないことがある**
（20 秒強の 1920x1080 で 25 万文字を超えた）。そのときは ffmpeg で 1 枚に並べて見る:

```bash
ffmpeg -v error -y -i "<動画>.mp4" -vf "fps=1,scale=640:-1,tile=4x6" -frames:v 1 sheet.png
```

そのうえで共有用 Drive へ上げてリンクを送る。**上げるのは `deliver-artifact` の `share.py put` で行う**。

```bash
python ~/.claude/skills/deliver-artifact/scripts/share.py put "C:/Users/komao/Videos/<元>.mp4" <名前>.mp4
```

- **`rclone link` を使わない**。リンクを作るときに「リンクを知っている全員」の権限を付けてしまい、
  既定（所有者 + 2 アカウント）より広がる（2026-09-24 に踏んだ）。付けてしまったら
  `share.py private <名前>` で外し、`share.py sharing <名前>` で確かめる。

## 複数のウィンドウを並べて撮る

`obs.py call <RequestType> [JSON]` で任意の obs-websocket リクエストを送れる。専用のシーンを作り、
ウィンドウキャプチャを並べてクロップする（利用者のシーンは触らない。終わったら元のシーンへ戻して消す）。

- 流れ: `GetCurrentProgramScene`（元を控える）→ `CreateScene` → `CreateInput`（`inputKind: window_capture`）
  → `GetSceneItemId` → `SetSceneItemTransform`（`cropLeft/Top/Right/Bottom`・`scaleX/Y`・`positionX/Y`）
  → `SetCurrentProgramScene`。片付けは `SetCurrentProgramScene`（元）→ `RemoveScene` → `RemoveInput`。
- `window_capture` の `window` は `"タイトル:クラス:exe"`（タイトル中の `:` は `#3A`）。
  **同じ exe が複数動いているもの（Unity.exe など）は `priority: 1`（タイトル優先）にする**。exe で絞ると別プロジェクトの窓を掴む。
  クラス名はウィンドウハンドルから `GetClassNameW` で取る（Unity は `UnityContainerWndClass`、Tauri は `Tauri Window`）。
  `method: 2`（Windows Graphics Capture）なら他の窓に隠れていても写る。
- 並べた結果は `SaveSourceScreenshot`（`sourceName` にシーン名、`imageFilePath` に保存先）で撮って、録る前に確かめる。

## 踏んだところ（先に読む）

- **作業ディレクトリ違いで起動しない**。`Failed to find locale/en-US.ini` のダイアログが出て、
  プロセスは残るが何も初期化されない（WebSocket も開かない）。必ず `bin/64bit` から起動する。
- **終わらせ方**。`StopRecord` してから閉じる。ウィンドウがあれば普通に閉じればよいが、
  前面化できない・トレイに入っている等で閉じられないことがある。そのときは
  **強制終了 → 起動中の印を消す**で、クラッシュ扱いを避けられる。

  ```bash
  powershell -NoProfile -Command "Get-Process obs64 | Stop-Process -Force"
  rm -f "$APPDATA/obs-studio/.sentinel/"run_*     # 起動中の印。残すとクラッシュ扱いになる
  ```

  `%APPDATA%\obs-studio\.sentinel\run_<GUID>` が「いま動いている」印で、正常終了すると
  OBS が自分で消す。強制終了すると残り、次の起動で
  「セーフモードで実行 / 通常モードで実行」を聞かれる（**セーフモードでは WebSocket が無効**）。
  消してから起動すればダイアログは出ない（実測で確認）。
  ダイアログが出てしまったら「通常モードで実行」を押す（`win-gui` で掴んでクリック）。
- **`CloseMainWindow()` も `WM_CLOSE` も効かないことがある**。前面に出せないと閉じない。
  粘らずに上の「強制終了 → 印を消す」へ切り替える。
- **`--minimize-to-tray` で起動すると閉じられなくなる**。トレイに入ると
  `MainWindowHandle` が 0 になり、`CloseMainWindow()` も `taskkill`（/F 無し）も効かない。
  残る手は強制終了だけで、それをすると次の起動でクラッシュ扱いのダイアログが出る。
  **付けずに起動して、終わったらウィンドウを普通に閉じる**。
- **CLI に停止の引数が無い**。`--startrecording` で始めることはできるが、止めるのは
  WebSocket（このスキル）かホットキー。
- **WebSocket が無効だと接続を拒否される**。`config.json` の `server_enabled` を確認する。
  有効化するときは `auth_required` を `true` のままにして、パスワードを生成して入れる
  （認証を外すと、同じネットワークの誰でも録画やシーン切り替えができてしまう）。
  設定を変えたら OBS を起動し直す。**利用者の設定を変えたことは報告に 1 行書く**。

## 何を映すか

- 全画面ではなく**対象のウィンドウ**を映す（OBS の「ウィンドウキャプチャ」）。
  余計なもの（別の作業・通知・個人情報）が映ると共有できない。
- 撮る前に対象を前面へ出しておく。`win-gui` の `SetWindowPos` で最前面に固定すると、
  操作中に他の窓が被らない。
- 長回ししない。論点が写る最小限にする（数十秒）。長い録画は見る側の負担が大きい。

## 後片付け

用が済んだ録画は**手元（`C:\Users\komao\Videos`）と Drive の両方から消す**。
残すのはユーザーが「取っておいて」と言ったものだけ。
