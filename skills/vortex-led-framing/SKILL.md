---
name: vortex-led-framing
description: vortex 系ライブ案件（Submod_RealtimeLiveUtility を使う Unity URP プロジェクト）で、LED チャート（図面/PDF/画像）から LED の画角セットアップを行う。RenderTexture とカメラの解像度・アスペクト合わせ、キャラの見え方から画角(FoV)と距離の決定、チャート画像とテストパターンによる検証まで。「LED の画角」「チャート合わせ」「LED セットアップ」「ChartSync」と言われたら使う。
---

# vortex LED 画角セットアップ

`Window/vortex/ChartSync` が中核。LED の実寸・画素数とキャラの見え方から、カメラの画角・距離・RT を合わせる。

## 前提となる決めごと

- **CG 1m = LED 1000mm**。ChartSync は LED の物理サイズ(mm)をそのままワールド座標に対応させる。
- 見え方の基準は**キャラの身長**。「LED 上で身長を何 mm に見せるか」から必要な写り幅を逆算する。
- 計算式（`ChartSyncWindow.cs:181-223`）:
  - `visibleHeight = キャラ実寸(m) × LED高さ(mm) ÷ 目標身長(mm)`
  - `distance = (visibleHeight / 2) ÷ tan(FoV / 2)`
  - FoV ≤ 0 なら Orthographic（`orthographicSize = visibleHeight / 2`）
- **LED の実寸・画素数を保存する仕組みが無い**。チャートを読んで毎回手入力する。
  入力値は作業ログに必ず残すこと（次回の再現に必要）。

## 1. チャートから数値を読み取る

図面 / PDF / 画像を読み、次を確定する。読み取れない項目はユーザーに確認する（推測で埋めない）。

| 項目 | 用途 |
|---|---|
| LED の画素数（横×縦） | RenderTexture と GameView の解像度 |
| LED の実寸（横×縦 mm） | 写る範囲の計算 |
| LED 上でのキャラの身長（mm） | 画角と距離の決定 |
| 足元の基準位置 | キャラの立ち位置（`_baseCharacter` の足元が写りの下端になる） |

読み取った値と、その根拠（図面のどこか）を報告に書く。

## 2. RenderTexture とカメラを合わせる

`Window/vortex/ChartSync` に入力して Apply する。Apply がやること（`ChartSyncWindow.cs:132-242`）:

1. 指定した RenderTexture の解像度を LED の画素数へ書き換える
2. Game View に `LED <W>x<H>` のカスタム解像度を追加して選択する
3. カメラの FoV・位置・向き（`LookAt`）を設定する
4. カメラの `targetTexture` に RenderTexture を設定する

**確認すること**:
- RT のアスペクトと LED の実寸のアスペクトが一致しているか（ズレていると縦横に伸びる）。
  一致しない場合はチャートの読み取りを疑う。
- カメラが **Physical Camera** のままだと、`fieldOfView` を入れても焦点距離・センサーサイズ側の値が残る
  （実測: Prime の Main Camera は `m_projectionMatrixMode: 1` / sensor 21.946x16.002 / focalLength 30.94）。
  Physical Camera を切るか、FoV と焦点距離の対応をそろえる。ChartSync はここを触らない。
- Cinemachine 経由のカメラは Lens 側（`CameraSwitcher.cs:212-234`）が優先される。ChartSync とは別系統。

## 3. チャート画像を出して確認する

ChartSync の **Generate Chart** が `Assets/_test/LED_Chart_<W>x<H>.png` を生成する
（`ChartSyncWindow.cs:247-325`）。1px = 1mm で、外枠と「幅 300mm × 目標身長」の赤枠が入る。
このチャートを LED のマテリアルへ貼り、実際の見え方と突き合わせる。

- `Assets/_test` は git 追跡外の一時置き場。**作業後に消す**。
- 既存の手作りチャート: `Assets/03_vortex_live/SinkaiFes2026/1080p_bottom_400mm_blue_transparent.png`（400mm/600mm）。
- テストパターン: `Script/Runtime/VJ/ProjectorTestPattern.png` / `testPattern_1.1.1.png`。
  ドット等倍・伸び・切れの確認に使う。

## 4. 検証（目視で終わらせない）

- `Window/vortex/CameraScreenshot`（`CameraScreenshotWindow.cs:53`）で対象カメラを PNG 出力する。
  解像度は LED と同じ値（Custom）にする。
- 出した PNG を自分で読み、次を確認する:
  - キャラの身長が目標 mm どおりか（チャートの赤枠と合うか）
  - 足元が下端に接しているか
  - 縦横比が崩れていないか（テストパターンの正方形が正方形か）
- 数値でも確かめる。チャートの枠の画素位置を測れば、`目標身長 × 画素数 ÷ LED実寸` と一致するはず。
- Before / After を撮って並べる。確認が済んだ画像は削除する。

## 5. 後片付けと報告

- 一時チャート（`Assets/_test/`）と検証用 PNG を削除する。
- 触ったファイルだけを `git add` でステージングする。**コミットはしない**。
  無関係な既存変更を巻き込まない（`git status --short` を作業前後で見比べる）。
- `log/claudeLog.txt` に、**入力した数値（LED 画素数・実寸・目標身長・FoV）と、結果のカメラ位置・距離**を残す。
  保存する仕組みが無いので、ログが唯一の再現手段になる。

## 詰まりやすい点

- LED メッシュ側のマテリアルに RT が繋がっていないことがある
  （実測: `M_Screen_LED.mat` の `_BaseMap` は空で、`LIVE2D_Tower.prefab` の `SM_Screen_LED` は URP Lit）。
  画角が正しくても LED に映らない場合は、まずマテリアルの接続を疑う。
- 使われていない RenderTexture が残っていることがある（実測: `GeandMainLED.renderTexture` は未参照）。
  どの RT が実際にカメラの `targetTexture` になっているかをシーンで確認してから触る。
- Game View の解像度は Reflection でカスタム追加している（`ChartSyncWindow.cs:346-408`）。
  Unity のバージョンが変わると失敗しうる。追加されたか必ず目視する。
- ChartSync の入力は保存されない。ウィンドウを閉じると既定値（1500x1000px / 4500x3000mm）に戻る。
