---
name: blender-stage
description: Blender で 3D のモデル・部屋・ステージ・セット・家具・小物を作る。BMCP（自作 Blender MCP）でモデリングを始める前に呼ぶ。「〜な部屋を作って」「ステージを作って」「セットを組んで」「この写真みたいな空間を作って」「椅子を作って」「小物を足して」「モデルを作って」と言われたとき、また Unity / UE へ持っていく 3D アセットを Blender で作るときに使う。最初に用途（Unity へ持ち込む / Blender で完結）を聞く手順、寸法の決め方、階層とマテリアルの作法、UV、タイリングするテクスチャの生成、FBX 書き出し、アセットライブラリ（BMCP Assets）への登録、踏んだ罠をまとめてある。「アセットにして」「ライブラリに入れて」と言われたときも使う。
---

# ステージ制作（Blender + BMCP）

部屋やセットを一から組み、後から編集でき、そのままゲームエンジンへ持っていける形に仕上げる。

**補助モジュール**: `scripts/stagelib.py`（形を作る）と `scripts/texlib.py`（テクスチャを作る）。
BMCP の `blender_run_python` から次の形で読み込む。

```python
import importlib, sys
sys.path.insert(0, r"C:\Users\komao\.claude\skills\blender-stage\scripts")
import stagelib as S, texlib as T
importlib.reload(S); importlib.reload(T)
```

## 先に読む（踏んだ罠）

同じ所で毎回詰まる。作り始める前に目を通す。

- **画像を保存する前に色空間を設定すると、真っ黒な PNG になる**
  症状: `images.new` → `pixels.foreach_set` → `save()` で書き出した画像が全部黒。配列は正しく、
  8×8 では成功するので気付きにくい。原因: `colorspace_settings.name` を変えると画素バッファが作り直される。
  対処: **色空間は保存した後に設定**。`Image.scale()` も挟まない（`texlib.save_image` は対処済み）。
  確認は「配列 → 画像バッファ → 保存したファイルの読み直し」の 3 段階で、**RGB とアルファを分けて**見る
  （アルファが 1 なので max だけ見ると成功に見える）。
- **作った直後のオブジェクトを親にすると、子が二重に移動する**
  原因: 親の `matrix_world` がまだ単位行列。対処: `bpy.context.view_layer.update()` を挟んでから
  `matrix_parent_inverse` を取る。**ワールド座標で作った子は親の変換を打ち消す**、
  **親のローカル座標で作った子は単位行列**（`stagelib.parent_to` が両方を引数で選べる）。
  確認は `bound_box` をワールドへ変換して範囲を見る。見た目では気付かない。
- **編集モードの演算子は `run_python` から呼べない**（`bpy.ops.uv.smart_project` など `poll() failed`）。
  UV は **BMCP の `blender_mesh_uv_project`**（box / cylinder / sphere、既定 1m = 1UV）を使う。
  貼り方が揃っているかは `blender_mesh_uv_info` の density（median が 1 前後で min/max が近ければ揃っている）。
  スクリプトの中で貼るなら `stagelib.uv_box_project` / `uv_cylindrical` でも同じ結果になる。
- **移動した直後に `matrix_world` を読まない**。`bpy.context.view_layer.update()` を挟む。
  world 空間の UV 投影・親子付け・座標の計測は、これを忘れると 1 手前の位置で計算される。
- **`blender_capture` に Empty を渡すと画角が潰れる**（大きさが無いため）。メッシュの名前を渡す。
- **室内は `blender_capture` では見えない**（外から撮るため）。中を見るならカメラを室内に置いて
  `bpy.ops.render.render`。**カメラが壁の外にあると真っ黒**になるので、部屋の内側の座標に入れる。
- **Workbench のプレビュー（`blender_capture` の `shading=MATERIAL`）はノードの色を見ない**。
  `material.diffuse_color` にベースカラーを写しておくと、プレビューでも色が分かる。
- **画像を使っていても、Base Color の手前に Mix などが挟まると FBX で色が落ちる**（2026-09-26 band_studio）
  症状: Unity で床・壁・アンプが白く、法線だけ付いている。原因: FBX の書き出しは
  **Principled BSDF に直接つながった画像しか拾わない**（Normal Map ノード経由の法線は拾う）。
  「色 × AO」「× 色味」の Mix(MULTIPLY) を挟むと、画像ごと落ちる。**Mapping ノードの拡大率も出ない**。
  対処: Mix と同じ式（`lerp(A, A*B, fac)`、リニア空間。8bit の sRGB 画像は `pixels` が変換前の値なので自分で直す）で
  1 枚の画像に合成して保存し、Base Color へ直接つなぐ。Mapping が 1 以外なら UV 側へ焼く。
  書き出す前に「Base Color が画像以外から来ているマテリアル」を列挙して潰す。前後のレンダリング差で確かめる。
- **BMCP を更新した直後は、起動中の Blender と Claude Code が古い版のまま**（2026-09-26）
  アドオンはリポジトリへのジャンクションなのでファイルは新しいが、**Blender は起動時に読んだモジュールを使い続け**、
  Claude Code も接続時のツール定義を使い続ける。新しい引数（例: `blender_export_fbx` の `hierarchy`）は
  **黙って捨てられる**。実際に、ルートの Empty だけの 10KB の FBX で上書きした。
  対処: 更新したら Blender と Claude Code を起動し直す。すぐ要るなら `objects` に子の名前を全部並べて渡す
  （`[root] + [o for o in root.children_recursive if o.type in ('MESH','EMPTY')]`）。
  書き出したら **バイト数とオブジェクト数を必ず見る**。
- **Base Color の数値はリニア値**（2026-09-25 band_studio）。sRGB のつもりで 0.16 と置くと
  sRGB 0.45 の中間グレーになり、黒いはずのスピーカーグリルが白い板に写った。
  黒い布・樹脂・ゴムは 0.012〜0.03、黒い金属は 0.02 前後。
  **逆に 8bit の画像の `pixels` は sRGB の値のまま**（`texlib.tint` の色は PNG にそのまま入り、sRGB として読まれる）。
  画像に色味を掛けて焼くときは「sRGB → リニア → 掛ける → sRGB」の順にする（Mix(MULTIPLY) はリニアで掛ける）。
  例は `BlenderScenes/scripts/band_instruments.py` の `_tinted_color_image`。
- **`bmesh.ops.create_uvsphere(calc_uvs=True)` は、UV レイヤーが先に無いと UV を作らない**（黙って UV 無しの球になる）。
  先に `bm.loops.layers.uv.new("UVMap")`。`create_cone` / `create_grid` なども同じ。
- **`node_tree.nodes` は参照するたび別のラッパーを返す**。`link.to_node is bsdf` は偽になり、
  リンクを外したつもりで外れていない（「色を変えたのに変わらない」が 2 回起きた）。**名前で比べる**。
- **EEVEE（レイトレ無し）の間接光はライトプローブのベイクで作る**。Volume プローブは**部屋より一回り大きく**取る。
  範囲の外にある面（天井・床そのもの）は間接光を受けず真っ黒になる。ベイクは
  `bpy.ops.object.lightprobe_cache_bake("EXEC_DEFAULT", subset="ALL")`（INVOKE だと run_python の中で進まない）。
  効いているかは、プローブの `intensity` を 1 → 6 にしてレンダリングの画素平均が動くかで見る。
  マテリアルや配置を変えたら焼き直す。
- **Poly Haven の色テクスチャは素材によって名前が違う**（`Diffuse` / `col_01`〜`col_03`）。
  見つからないときに黙って単色へ落とすと「マットでモックっぽい」の原因が分からない形で出る。候補を並べ、全滅は例外にする。
- **オブジェクトを消すとメッシュデータが残る**。同じ名前で作り直すと `.001` が付き、書き出した FBX の
  Geometry 名がビルドのたびにずれる。作り直す関数ではメッシュも消し、最後に `orphans_purge(do_recursive=True)`。
- **厚み 0 の片面ポリゴン（太鼓のヘッド・紙・布）は 1mm でも厚みを付ける**。Unity の背面カリングで裏から消える。
- **Euler の成分を足して回転を合成しない**（Blender の XYZ は Rz·Ry·Rx の順）。
  親の回転の中でさらに回すなら `(Euler(rot).to_matrix().to_4x4() @ 追加の回転).to_euler()`。
- **GLB 由来のメッシュは面ごとに頂点が分かれていることが多い**。そのままサブディビジョンをかけても丸くならず
  膨らむだけ。`remove_doubles` で溶接してから、角の辺にクリースと sharp を立てる。
- **共有中の Blender で `read_homefile` / `open_mainfile` をしない**（2026-09-26）。BMCP の接続先は
  別セッションも使っている。書き出しの検証は `scripts/check_fbx.py` を**別プロセスの Blender** で走らせる。
  成果物のパスを報告する前に、`git log` とファイルの更新時刻で**他のセッションが書き換えていないか**を見る
  （band_studio では、報告した FBX を別セッションが修正版で上書きしていた）。
- **ライティングは用途を聞いてから**。ゲームエンジンへ持っていくなら Blender 側は最小限でよい
  （灯具の位置が分かる程度）。EEVEE の間接光を追い込むのは、Blender で絵を作るときだけ。

## 進め方

0. **最初に「どこで使うか」を聞く**（`AskUserQuestion`）。ここで作り方が変わるので、手を動かす前に確かめる。

   | 答え | 作り方の違い |
   |---|---|
   | **Unity へ持ち込む**（既定） | 画像テクスチャ・Empty の階層・1m = 1UV・非一様スケール無し。ライティングは最小限（位置が分かる程度）。最後に FBX |
   | **Blender で完結**（静止画・動画） | ライティングとカメラを詰める。マテリアルは手続き型のままでよい。UV も見た目が成立すれば足りる |
   | **両方** | Unity 前提で作り、見栄え用のライトとカメラを別コレクションに足す（書き出しからは外す） |

   併せて聞く: **寸法**（広さ・高さ。実寸 m）と**含める設備・小物**。
   素材はクレジット表記の要らないもの（CC0 か自作）だけを使う（ユーザーの方針。Poly Pizza の多くは CC-BY で表記が要るので使わない）。
   形は手続きで作り、テクスチャは自前生成か CC0（Poly Haven）だけにする
   （band_studio は途中で全差し替えになった。組み方の例は `BlenderScenes/scripts/band_instruments.py`）。
   参照画像があるなら「何を踏襲して、何を変えるか」を 1 行で決めてから作る。
1. **寸法と中身を先に決める**。数値が決まらないまま形を作らない（後から全部ずれる）。
2. **躯体 → 造作 → 設備 → 小物 → 照明 → カメラ** の順に、段階ごとに `run_python` を分ける
   （1 回が 1 つの Undo ステップになる。失敗しても戻せる）。
3. **段階ごとにレンダリングして見る**。形が出てから質感へ進む。寸法の間違いは早いほど安い。
4. **最後に点検**（下のチェックリスト）→ 保存 → 必要なら FBX。
5. **アセットライブラリへ登録する**（下の節。確認は取らない。グローバルの恒久方針）。

## アセットライブラリへ登録する

自分で作った**機材・家具・小物は 1 点ずつ**、**マテリアルは 1 つずつ**、ライブラリ **BMCP Assets**
（`D:\_Personal\Project\BlenderAssets`、git LFS）へ登録する。部屋一式と細かい部品は登録しない。
外部アセット（CC-BY など）を含むものは登録しない。

- **1 点 = 1 つの階層**にしておく。置き場所の Empty（`INST_*` など）の下に、本体もスタンドも入れる。
  兄弟に置いたスタンドは一緒に登録できない（band_studio で `group_stands()` を足した）。
- 登録は BMCP のツールで行う。1 アセット = 1 ファイル（`<カタログ>/<名前>.blend`）で、同じ名前なら上書き。

  ```python
  blender_asset_publish_objects(root="INST_DrumKit", name="DrumKit_5pc", catalog="Instruments/Drums",
                                tags=["drums"], description="...")      # root を原点・無回転にして書き出す
  blender_asset_publish_materials(materials=["M_Inst_Chrome", ...], catalog="Materials/Instruments")
  blender_asset_list()                                                  # 中身の確認
  ```
  画像はパックされ、プレビュー（256px。画像を持つマテリアルは画像を貼った球）が付く。
  元のシーンは書き出し後に元へ戻る（親子・変換・名前・パック・アセットの印）。
- 名前は英語で「種類_仕様」（`GuitarAmp_Combo_1x12`、`Synth_49_OnStand`）。カタログは
  `Instruments/…` `Furniture/…` `Props/…` `Materials/<用途>`。
- **登録したらプレビューを並べて自分で見る**（別プロセスの Blender で）:
  `"<blender.exe>" -b --factory-startup -P scripts/asset_sheet.py -- <ライブラリ> <出力.png> [カタログ]`。
  空のプレビューは赤いマスになる。
- 最後に BlenderAssets を git でコミットする（`.blend` と画像は LFS）。
  **一括で登録し直すと、中身の変わっていない機材・マテリアルの `.blend` もすべて変更扱いになる**（保存し直しでバイトが変わる。
  2026-09-27 に 48 ファイル）。直した機材のファイルだけ `git add` し、残りは `git checkout -- .` で戻す。
  戻すときに `unable to unlink ... Invalid argument` が出たら一時的なロックなので、少しおいて `git restore` し直す。
- 初回だけのライブラリ登録（`blender_asset_library_register`）は設定を保存する。**GUI の Blender が
  開いていると、その Blender が終了時に古い設定で上書きする**ので、閉じているときに行う。

### 階層の作り方

コレクション（Blender の整理用）と **Empty の親子（書き出し先の階層用）の二重**にする。
FBX にコレクションは出ないので、Empty が無いと Unity で平らな一覧になる。

```
SoundproofRoom (Empty)        ← ルート。位置・向きはここで動かす
├── GRP_Shell (Empty)  … 01_Shell コレクション
├── GRP_Acoustic       … 02_Acoustic
├── GRP_Fixtures       … 05_Fixtures
│   └── PianoBench (Empty) … 家具ひとまとまりも Empty でくくる
└── …
```

- 名前は**部位 + 連番**（`Wall_Front` `Panels_Left` `PianoBench_Leg_01`）。英語・半角。
- 原点は**意味のある場所**に置く（壁は床側の端、扉は蝶番、家具は接地面の中心）。後から動かしやすい。
- **モディファイアは残す**（`Array` で枚数と間隔、`Bevel` で角、`Subdivision` で滑らかさ）。
  FBX に出すときに焼かれるので、Blender 側は編集できる状態のままでよい。

### マテリアルと UV

- 名前は `M_<用途>`（`M_Wall_Plaster` `M_Floor_Carpet` `M_Wood_Light`）。画像は `T_<素材>_<種類>`。
- **UV は「1m = 1UV」で統一**する。テクスチャ 1 枚が実寸 1m 角に対応し、密度が全部そろう。
  角ばった物は `uv_box_project`、回転体は `uv_cylindrical`。
- テクスチャは `texlib` で**タイリングする画像を生成**して貼る。手続き型ノードのままだと
  **FBX に出せずエンジン側で単色になる**。生成した PNG は `.blend` の隣の `textures/` に置き、
  最後に `bpy.ops.file.make_paths_relative()` で相対参照にする。

## Unity へ出す

```python
# BMCP のツール: blender_export_fbx
path       = "<出力先>.fbx"
preset     = "unity"                   # FBX_SCALE_ALL / -Z 前・Y 上
collection = "<ルートのコレクション>"      # 子コレクションの中身も含む（objects に名前を並べなくてよい）
options = {"path_mode": "COPY", "embed_textures": True,
           "use_tspace": True, "use_mesh_modifiers": True,
           "mesh_smooth_type": "EDGE",   # FACE だと「滑らかな面どうしの境目の角」が表現できない
           "object_types": ["EMPTY", "MESH"]}   # ライト・カメラ・プローブは出さない
```

- 書き出す前に: **Mapping ノードの倍率を UV へ焼く**（`band_instruments.bake_uv_tiling()`）。
  **Base Color の手前の Mix は画像へ焼く**（上の「先に読む」）。
- **書き出したら読み込み直して確かめる**。共有中の Blender ではなく別プロセスで:
  `"<blender.exe>" -b --factory-startup -P scripts/check_fbx.py -- <FBX>`。
  `textured_by_image` に色テクスチャのマテリアルが全部並ぶこと、寸法・件数・UV を見る。
- **Unity（URP）では金属度が 0 になる**（2026-09-27 band_studio）。Blender は Metallic を FBX の
  `ReflectionFactor` に入れるが、URP の `FBXMaterialDescriptionPreprocessor` はこれを読まない
  （滑らかさは `Shininess` から正しく作る）。症状: クロームのスタンドが白い樹脂のように質感が無い。
  対処: URP の後（順序 > -980）の `OnPreprocessMaterialDescription` で `ReflectionFactor` を `_Metallic` へ入れる。
  他ツールの FBX では意味が違い、既存の Blender 製 FBX の見た目も変わるので**ラベルで対象を限る**
  （実装例: Ext_TokinoSora_2026-pia の `Assets/vortex/Editor/Import/BlenderFbxMetallic.cs`）。
  金属を部屋に馴染ませるには、部屋いっぱいのボックス投影の **Reflection Probe を焼いて**置く（無いと既定の空が映る）。
- Unity 側: **Bake Axis Conversion を有効**にすると root に -90 回転が付かない。
  ライトマップを焼くなら **Generate Lightmap UVs**（UV2 は Blender では作っていない）。

## 終わる前のチェックリスト

- [ ] 非一様スケールが残っていない（`o.scale` が全て 1。回転は残ってよい）
- [ ] 全メッシュに UV がある（`o.data.uv_layers`）
- [ ] マテリアルが全メッシュに付いている。命名は `M_*`
- [ ] 画像の参照が相対パス（`//textures/...`）で、ファイルが存在する
- [ ] 孤立頂点・n-gon を確認（円柱の蓋の n-gon は可。エンジンが三角化する）
- [ ] Base Color に画像が直接つながっている（Mix 経由は FBX で落ちる）。Mapping の倍率は 1
- [ ] 床へのめり込み・宙に浮いた物が無い（`bound_box` の最低 z を全メッシュで見る）
- [ ] 室内カメラからのレンダリングを**自分で見た**
- [ ] `.blend` を保存した
- [ ] 作った機材・小物とマテリアルをアセットライブラリへ登録し、プレビューの一覧を見た
