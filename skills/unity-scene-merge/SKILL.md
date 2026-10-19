---
name: unity-scene-merge
description: Unity のシーン（.unity / .prefab / .playable）を、変えたかった所だけの最小差分でコミットする・3 方向マージする。Unity で保存したシーンに、触っていない実行時マテリアル・RenderTexture・ライトや部品の値などの雑音が数千行混ざったとき、MCP や Editor スクリプトでシーンを変えてコミットするとき、LFS のシーンが pull / merge で衝突したとき、作業ツリーの他の変更を残したまま一部だけをコミットしたいときに使う。塊（--- !u!）単位で一覧・取り込み（参照の連鎖と親子の登録を自動で）・参照の検査・3 方向マージを行うスクリプト付き。
---

# Unity シーンの最小差分コミット・3 方向マージ

Unity で保存したシーンを、そのままコミットしない。変えたかった塊（`--- !u!<class> &<fileID>`）だけを、元の版（HEAD）へ写した版を作ってコミットする。

`S=~/.claude/skills/unity-scene-merge/scripts`

| コマンド | 用途 |
|---|---|
| `python "$S/scene_diff.py" fromgit <rev> <パス> <出力>` | git の版を取り出す（LFS なら実体へ戻す）。リポジトリの中で実行する |
| `python "$S/scene_diff.py" list <元> <保存後> [--assets <Assets> <サブモジュール>] [--class 114] [--grep 文字]` | 増えた（NEW）・変わった（MOD）・消えた（GONE）塊の一覧。種類ごとの件数・ヒエラルキーパス・変わった行。`--assets` を渡すと MonoBehaviour をスクリプト名で出す |
| `python "$S/scene_diff.py" show <シーン> <fileID か文字列>...` | 塊の中身。参照の fileID に名前を添える |
| `python "$S/scene_diff.py" take <元> <保存後> <出力> <fileID,...> [--drop fileID,...]` | 指定した塊だけを保存後の版から採る |
| `python "$S/scene_diff.py" refcheck <シーン>...` | 同じファイル内の参照が切れていないか・fileID の重複（あれば終了コード 1） |
| `python "$S/merge3.py" <base> <ours> <theirs> <出力> [--prefer-ours id,...] [--prefer-theirs id,...]` | 塊単位の 3 方向マージ |

`take` は、次の 3 つを自動で行う。そのため、指定するのは「変えた部品」と「新しい GameObject」だけでよい。

- 参照の連鎖: 新しい GameObject の部品、マイクの stripped の塊など、指した fileID が元の版に無ければ、保存後の版から足す。
- 新しい Transform の親（m_Children）への登録。
- ルートなら SceneRoots の m_Roots への登録。

親の塊のほかの変更は採らない。

## 先に読む（踏んだ罠）

- **Unity で保存したまま差分を見ると、数千行の雑音がある**。
  - 原因: 実行時に作られたマテリアルが fileID だけ変わって消えて増える（GONE/NEW の対）。MonoBehaviour の実行時の値、RenderTexture・ライトの値も書き換わる。
  - 実測: Yamashita で 2,500〜4,000 行、Prime_modelSetup で Material 18 対・MonoBehaviour 29（2026-10-12〜15 SinkaiFes2026）。
  - Play した後に保存すると特に多い。そのままコミットすると、他の PC で照明やマテリアルが変わる。
  - 対策: `list` で塊を見て、意図した物だけを `take` する。
- **プレハブのインスタンスの上書き（m_Modifications）は、値を戻しても残る**（rules/traps/unity-editor.md）。`list` で PrefabInstance が MOD なら、中身を `show` で見てから採るか決める。
- **シーンと .playable は LFS**。
  - `git diff` では中身が見えない。`fromgit` で取り出して比べる。
  - pull で両側が変えていると、git は中身でマージできず衝突する（binary）→ 下の「マージ」。
- **Unity が同じシーンを開いたままファイルを書き換えると、Unity がメモリの版で上書きし直す**（次の保存・Play の出入りで）。
  - 書き換えたら、Auto Refresh が無い案件では `AssetDatabase.ImportAsset` か `Assets/Refresh`。続けて MCP の `open_scene` で開き直し、メモリの版を捨てる。
  - 開き直す前に、タイトルの `*`（未保存）を見る。ユーザーが編集中なら触らない。
- **作業ツリーに、まだコミットしない別の変更が同じシーンにある**ことがある（2026-10-14 MZM のマイク）。
  - 最小差分の版を作業ツリーに書かずに、インデックスへだけ入れる:
    `git update-index --cacheinfo 100644,$(git hash-object -w --path="<シーン>" <最小差分の版>),"<シーン>"`
  - `--path` を付けると .gitattributes の LFS の clean を通る（HEAD と同じ中身なら HEAD と同じ blob になることを確かめた）。
- **`take` は保存後の版の塊をそのまま採る**。採った塊の中にも雑音の行（実行時の値）が混ざることがある。採る前に `show` で中身を見る。

## 手順（変えた所だけコミットする）

1. **元の版を取っておく**。Unity で保存する前に `fromgit HEAD <パス> head.unity`（作業ツリーに未コミットの変更があるなら、その版をコピー）。
2. Unity で変更して保存する（MCP の `save_scene` など）。
3. `list head.unity <シーン> --assets <Assets> <サブモジュール>` で一覧する。意図した塊の fileID を拾う。
   - 例: MicController の MOD、新しい MicMouth の GameObject、Kimayu-Timeline の GameObject、キャラの GameObject の m_IsActive。
   - 雑音の目安: Material の NEW/GONE の対、名前に `(Clone)` の付く物、触っていない MonoBehaviour・Light・RenderTexture。
4. `take head.unity <シーン> out.unity <fileID,...>` → 出力の「pulled in」「listed ... under」を読み、意図しない物が無いか見る。
5. `refcheck out.unity`（終了コード 0）。`list head.unity out.unity` で、残った差分が意図した物だけか見る。
6. 置き換える: `out.unity` をシーンのパスへコピー → ImportAsset / Refresh → `open_scene` で開き直す。
   Play で効いているか確かめる（コードを読んで「入ったはず」で終えない）。
   作業ツリーを変えたくないなら、上の `update-index` でインデックスへだけ入れる。
7. コミット。作業ツリーを置き換えたなら `git commit -- <シーン>` でパスを指定。
   **`update-index` でインデックスへだけ入れたときは、パスを付けずに `git commit`**（他に staged が無いことを `git diff --cached --name-only` で確かめる）。
   `git commit -- <パス>` は作業ツリーの版を採り直すので、雑音入りのシーンがコミットされる（2026-10-19 Ext_TokinoSora_2026-pia。amend で直した）。
   コミットしたら `fromgit HEAD` → `list head.unity` で、意図した塊だけになっているか確かめる。

## マージ（pull で .unity / .playable が衝突したとき）

```bash
cd <リポジトリ>
B=$(git merge-base HEAD MERGE_HEAD)
python "$S/scene_diff.py" fromgit $B "<パス>" base.unity
python "$S/scene_diff.py" fromgit HEAD "<パス>" ours.unity
python "$S/scene_diff.py" fromgit MERGE_HEAD "<パス>" theirs.unity
python "$S/merge3.py" base.unity ours.unity theirs.unity merged.unity
python "$S/scene_diff.py" refcheck merged.unity
cp merged.unity "<パス>" && git add "<パス>"
```

- 土台は theirs（リモート）の並び。ours で変えた・足した・消した塊を載せる。
  両側が同じ塊を変えていて、theirs の変更が ours に含まれる（ours が上位集合）なら ours を採る。
- 本物の衝突は、全部を挙げて何も書かずに止まる。ours / theirs それぞれの変わった行が出るので、塊ごとに `--prefer-ours` / `--prefer-theirs` で決めてやり直す。
  決め方に迷ったらユーザーに聞く（どちらかの作業が消える）。
- 合わせた後、Unity で開いて読み込めるか・Play で確かめる。マージの前に `git tag backup/<ブランチ>-pre-merge-<yymmdd>` を打っておく。

## 確かめた実績

- `take`: 2026-10-15 の Prime_modelSetup（Kimayu の Timeline・MicMouth・キャラの有効化・MicController）を、7 つの fileID の指定だけで作り直した。当時手で組んでコミットした版とバイト単位で一致した（部品・親の m_Children・SceneRoots は自動）。
- `merge3`: 2026-10-14 の Yamashita のマージ 2 件（コミット側・作業ツリー側）で、当時の結果とバイト単位で一致した。合成した衝突（同じ塊の別の行を両側が変更）では、書かずに終了コード 1 で止まった。
- `fromgit` → `git hash-object --path` が HEAD の blob と一致した（LFS の clean を通る）。
