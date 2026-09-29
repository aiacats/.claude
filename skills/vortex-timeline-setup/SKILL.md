---
name: vortex-timeline-setup
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、収録データを Timeline としてシーンへ仕込む。Google Drive のリンクか手元のパスを受け取り、取得 → 中身の検分 → Assets へ配置 → Timeline と PlayableDirector の生成 → ループ再生の実証、までを行う。ArtNet の .dmx、モーション(AnimationClip)、音声(AudioClip) が対象。「この収録データを仕込んで」「Timeline を組んで」「ArtNet のデータを再生できるようにして」「ループで流せるようにして」と言われたら使う。
---

# vortex Timeline 仕込み

収録データ 1 本を、指定シーンで再生できる形にするまでの手順。
**リンクを 1 つ渡されたら、この手順だけで完了まで持っていける**ように書いてある。

## 毎回ユーザーに聞くこと / 聞かないこと

**聞くのはこれだけ**（無いと判断できないもの）。

1. 仕込み先のシーン。**指定が無ければ「今 Unity で開いているシーン」**に入れる（勝手に他のシーンへ広げない）
2. ループさせるか（**既定はループする**。明示されたらそれに従う）

**決定済みの既定値。聞き直さない。**

| 項目 | 既定 |
|---|---|
| `.dmx` の置き場所 | `Assets/RecordedData/`（既存の収録データ置き場） |
| Timeline アセットの置き場所 | `Assets/03_vortex_live/<案件フォルダ>/`（既存の `.playable` と同じ場所） |
| Timeline / アセットの名前 | `Timeline_<データ名>`。収録との対応が追えることを優先し、長くなっても縮めない |
| フレームレート | 60（データの実測値と一致するか検分で確認する） |
| PlayableDirector | 新規 GameObject を作る。`Play On Awake` オン |
| Wrap Mode | `Loop` |
| クリップの開始位置 | 0 秒 |

**判断を仰ぐのはここだけ**: コミットの可否、既存の Timeline や PlayableDirector を書き換えるとき、
本番シーンへの適用。取得・配置・生成・検証そのものはユーザーにやらせない。

## 0. 前提を確認する

```
mcp__claude-code-mcp-unity__get_play_state        # 疎通確認
powershell -NoProfile -Command "Get-Process | Where-Object { $_.MainWindowTitle -like '*Unity 6*' } | ForEach-Object { $_.MainWindowTitle }"
```

ウィンドウタイトルが `<プロジェクト> - <シーン名> - ...` なので、**開いているシーン名はここで分かる**。
MCP にシーン名を返すツールは無い。

## 1. データを手に入れる

**まず手元を探す。** ユーザーが既に落としていることが多い。

```bash
ls -la "C:/Users/komao/Downloads/"*.dmx
```

無ければ Drive から取る。**リンクを渡されたら、必ず先にメタデータでサイズを見る。**

```
mcp__claude_ai_Google_Drive__get_file_metadata(fileId=<リンクの id>, excludeContentSnippets=true)
```

- **`download_file_content` は使わない。** base64 で返るので、100MB を超えるファイルはコンテキストを破壊する
- 取得は `rclone` で行う。remote が複数あるので、**404 が出たら別の remote を試す**
  （アカウントが違うと共有ファイルが見えない。実測: `gdrive:` で 404 → `gdrive-ro:` で成功）

```bash
rclone listremotes
rclone backend copyid gdrive-ro: <fileId> "<保存先ディレクトリ>/"
```

手元のものと Drive のものが両方ある場合は `md5sum` で同一性を確かめ、**ユーザー指定のパスを使う**。

## 2. 中身を検分する（Assets に置く前に）

148MB の `.dmx` は取り込みに数分かかる。**壊れたファイルを入れて数分待つのは無駄**なので先に見る。

```bash
python ~/.claude/skills/vortex-timeline-setup/scripts/inspect_dmx.py "<path>.dmx"
```

パケット数・収録時間・fps・ユニバース番号・形式の整合性が出る。
**「余りなし」でなければ取り込んでも例外で失敗する**ので、その時点でユーザーに報告して止まる。

ここで出た収録時間は、あとで Timeline のクリップ長と突き合わせる。

## 3. Assets へ置いて取り込ませる

```bash
cp "<path>.dmx" "<project>/Assets/RecordedData/"
```

- `.dmx` は **ScriptedImporter（`DmxRecordDataImporter.cs`）が `DmxRecordData` へ自動変換する**。
  変換スクリプトを書く必要はない。置くだけ
- `*.dmx` は `.gitattributes` で **LFS 対象**に設定済み

**このプロジェクトは Auto Refresh が無効**。置いただけでは取り込まれないので明示的に呼ぶ。

```
mcp__claude-code-mcp-unity__execute_menu_item(menuPath="Assets/Refresh")
```

取り込めたかは型で確かめる（名前で探すと見つからないことがある）。

```
mcp__claude-code-mcp-unity__find_assets(filter="t:DmxRecordData")
```

## 4. Timeline を組む

**`Window/vortex/Timeline/Timeline Composer`** を使う。手で Timeline を作らない。

```
mcp__claude-code-mcp-unity__execute_menu_item(menuPath="Window/vortex/Timeline/Timeline Composer")
```

このツールは **アセットを 1 つ指定すれば Track の種類とバインド先を自動で解決する**
（`[TrackClipType]` / `[TrackBindingType]` 属性とクリップ側のフィールド型から導いている）。
`.dmx` なら Dmx Track とシーン内の `MetaDmxReceiver` が自動で当たる。

win-gui での操作（ウィンドウは独立して出る。位置は `list_windows` で取る）:

1. **アセットを入れる** — 行の右端の `◎`（ピッカー）をクリック → 検索欄にデータ名の一部 → 結果を**ダブルクリック**
   - Project 側で選んでから「Project の選択を追加」でもよい
2. **フォルダ** — テキスト欄に `Assets/03_vortex_live/<案件>` を直接入力する。
   「選択」ボタンのフォルダダイアログは**モーダルで Unity ごと止まる**ので使わない（後述）
3. **Track / バインド / 長さ**が自動で埋まっているのを確認する。
   長さが手順 2 の検分値と一致していること
4. **Wrap Mode が `Loop`** になっていること（既定）
5. 「Timeline を作成」→ 確認ダイアログで内容を見てから実行

生成物とログを確認する。

```bash
grep -E "m_Duration|recordData|m_Framerate" "<作った>.playable"
```

## 5. 検証する（ここまでやって「できた」）

**コードを読んで「合っているはず」で報告しない。実際に再生して確かめる。**

```
mcp__claude-code-mcp-unity__save_scene
mcp__claude-code-mcp-unity__enter_play_mode
```

1. **再生されているか** — Inspector の PlayableDirector の `Current Time` が進んでいること。
   `get_component_properties` では実行時の time は取れないので、**Inspector を画面キャプチャして読む**
2. **データが流れているか** — 数秒あけて Scene ビューを 2 回撮り、**灯体の色が変わっている**こと
3. **ループするか** — 全長を待たずに済ませる。`time` を「全長 − 3 秒」にセットし、少しあけて読む

```
# instanceId は get_gameobject_info の components から取る。
# objectPath は名前が長い/空白を含むと解決に失敗するので instanceId を使う
mcp__claude-code-mcp-unity__set_object_properties(instanceId=<PlayableDirector の id>, data={"time": <全長-3>})
```

読み直した `Current Time` が**小さい値に戻っていればループ成立**。
`Hold` なら全長で止まり、`None` なら停止するので、小さい値はループでしか説明がつかない。

4. Console のエラーが 0 件であること

Play を抜けて、シーンを保存する。

## 仕組みの要点（つまずいたらここを見る）

| 事柄 | 中身 |
|---|---|
| 収録データの型 | `DmxRecordData`（ScriptableObject、`[PreferBinarySerialization]`）。`.dmx` から自動生成 |
| Track | `inc.stu.SyncSystem.DmxTrack`。`[TrackClipType(DmxClip)]` / `[TrackBindingType(MetaDmxReceiver)]` |
| バインド先 | シーン上の `MetaDmxReceiver`。そこから `OnMetaDmx`(UnityEvent) で `FixtureController` / `LEDController` へ配られる |
| **ループ** | **PlayableDirector の `wrapMode = Loop` で行う。** `DmxClip.clipCaps` は `ClipIn｜Blending` だけで `Looping` を持たず、`DmxMixerBehaviour` も時刻を wrap しないため、**クリップ側の Extrapolation ではループしない** |
| 再生中の ArtNet | `DmxMixerBehaviour.OnGraphStart` が `MetaDmxReceiver.IsTimeline(true)` を呼び、**実受信は止まる**（収録データが優先される）。現場で「卓から効かない」と言われたらここを疑う |
| `.dmx` の形式 | `[uint32 seq][double time(ms)][uint32 numUniverses]` + N×`[uint32 universe][512byte]` の繰り返し。ヘッダー無し |

## モーション FBX とフェイシャルを並べるとき（2026-09-26 実測）

1 演者 1 テイクを「モーション + フェイシャル + DMX」の 3 トラックで並べる場合。

| 素材 | 置き場所・型 | Track / バインド先 |
|---|---|---|
| モーション `.fbx`（数百 MB） | `Assets/RecordedData/`。**Humanoid で取り込み直す**（`animationType=Human`、`avatarSetup=CreateFromThisModel`）。`Avatar.isHuman` が true か確かめる | `AnimationTrack` → キャラの `Animator` |
| フェイシャル `animation_<名前>_<日時>.asset` | `Assets/RecordedData/`（収録時にできる）。型は `vortex.VRMBlendShapeRecordData`（`_duration` を持つ） | `VRMBlendShapeTrack` → `VRMBlendShapeProxy`。クリップ `VRMBlendShapeClip` の `_recordData` へ入れる |
| DMX `.dmx` | 既存の `.dmx` と同じ場所（この案件は `Assets/03_vortex_live/<案件>/`） | `DmxTrack` → `MetaDmxReceiver`。クリップ `DmxClip` の `recordData` |

- **テイク番号はシステムごとにずれる。尺で照合する。** 途中で止めた短いテイク（例: 55 秒）を数えるかどうかで、
  モーション `T002` = DMX `t003` = フェイシャル `…151927` のようにずれていた。
  3 つの尺（FBX のクリップ長 / `_duration` / `inspect_dmx.py` の収録時間）が 2〜3 秒以内で揃う組を採る。
  番号が合わないときはユーザーに組み合わせを確認する
- クリップの `recordData` 系フィールドは private。一時 Editor スクリプトで `SerializedObject` 経由で入れ、
  入れた後に `clip.duration = asset.duration` で長さを合わせる（既定クリップは 1 秒で作られる）
- **キャラごとに Timeline を分けたら `Play On Awake` はオフ**にする。両方が起動時に鳴ると DMX が同じ `MetaDmxReceiver` を取り合う。
  表示の切り替えは各 Timeline に **Activation トラック**（0 秒〜全長、`postPlaybackState = Revert`）を持たせる
- **キャラはセットアップ済みの個体を持ってくる。** セットアップ用シーン（`ShinkaiFes2026_Grand_modelSetup` など）の
  `<名前>(NiloToon)_setupped` を、プレハブのリンクを保ったままコピーする（手順は `rules/unity.md`「別シーンへ複製する」）。
  コピー元で**非アクティブ**のことが多い。日本語名は YAML で `\uXXXX` になるので grep では見つからない（同所）
- 動きの確認は骨の値で取れる: `Animator.GetBoneTransform(HumanBodyBones)` の instanceId に対し
  `Transform.get_rotation` を数秒おいて 2 回。フェイシャルは `SkinnedMeshRenderer.GetBlendShapeWeight`（口の `A` など）
- 収録時のカメラ（`<名前>_Cam_T00x_camera_<日時>.anim`）も同じ場所にある。頼まれなければ載せない
- 書き出して見せるときは `vortex-timeline-export` スキルへ

## 踏みやすい罠（すべて実測で踏んだ）

- **Timeline Composer はブランチによって無いことがある**（サブモジュールの別ブランチにしか入っていない）。
  `Window/vortex/Timeline/Timeline Composer` が無ければ、一時 Editor スクリプトで `TimelineAsset` を作り、
  `TrackBindingType` 属性からバインド先の型を引いて組む。組み終えたらスクリプトは消す

- **`EditorUtility.OpenFolderPanel` を開いたままにすると Unity のメインスレッドが止まり、MCP が軒並みタイムアウトする。**
  HTTP は 200 を返すのに処理だけ返らないのが目印。**「MCP が応答しない」ときは真っ先にモーダルダイアログを疑い、画面を撮る。**
  Unity のメニューをクリックしたつもりが、裏で開いていたダイアログに吸われていることがある
- **Auto Refresh が無効。** スクリプトを足しても自動でコンパイルされない。
  `force_compilation` か `Assets/Refresh` を明示的に呼び、**`Library/ScriptAssemblies/*.dll` の更新時刻とソースの更新時刻を比べて**実際にビルドされたか確かめる。
  ドメインリロード直後の「エラー 0 件」は信用しない
- **EditorWindow の状態はドメインリロードで消える。** コンパイルを挟むと入力し直しになるので、
  ツールの設定はコンパイルが落ち着いてから入れる
- **win-gui の座標クリックは、手前に別アプリの窓があるとそちらに吸われる。**
  `focus_window` だけでは足りないことがある。対象ウィンドウを重ならない位置へ `drag` してから押す
- **シーンの検証でシリアライズされるフィールドを一時的に書き換えない。**
  プレハブインスタンスは値を元に戻してもオーバーライドとして記録が残り、以後プレハブ側の変更が効かなくなる。
  やむを得ず触ったら保存せず `git checkout` で戻す
- **シーンと `.playable` は Git LFS 管理。** `git diff` では中身が見えない。
  差分を見るときは `git show HEAD:<path> | git lfs smudge > orig.unity` で取り出して diff する

## 報告に必ず入れるもの

- 収録データの実測値（パケット数・長さ・fps・ユニバース）
- 生成物のパス（`.dmx` / `.playable` / シーン上の GameObject 名）
- **ループが成立したことの根拠**（time をどこにセットして、いくつに戻ったか）
- 灯体に信号が流れたことの根拠（キャプチャ比較）
- コミットしていないものの一覧
