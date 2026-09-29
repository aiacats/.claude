---
paths:
  - "**/*.{cs,unity,prefab,asmdef,asmref,asset,controller,anim,playable,uxml,uss}"
  - "**/ProjectSettings/**"
  - "**/Packages/manifest.json"
---
# unity-build の罠
全件は ~/.claude/traps-catalog/unity-build.md。ここは再発しやすいものだけ。

### Player ビルドを壊さない
エディタではエラー 0 なのに Player ビルドだけ CS0246 / CS0103 で落ちる。原因は Runtime アセンブリ内の UnityEditor 依存（同居させた CustomEditor、自動 using の `Codice.*` / `Mono.Cecil`、ガード外の `EditorApplication.isPlaying`）がエディタ用コンパイルでは解決されること。→ UnityEditor の型は Editor 専用アセンブリへ。Runtime に書くなら using からクラス末尾まで `#if UNITY_EDITOR`、再生判定は `Application.isPlaying`。using をガードの中へ入れて外で使うのも CS0103。（実例: 2026-09-13 SinkaiFes2026 / 2026-08-27 Unity_ArtNetRecorder / 2026-09-06 lll-12）

### UnityEditor を参照する DLL の .meta は Editor 限定に
スクリプトは全部ガード済みなのに "UnityEditor.dll assembly is referenced by user code"。原因は VRMSkirtTool.dll などの .meta が `Any: enabled 1`。→ .dll.meta を Any:0 / Editor:1。`Library/Bee/artifacts/rsp/*.rsp` か `grep -la UnityEditor` で DLL を探す。（実例: 2026-06-01 LiveMultiRecorder / 2026-09-13 SinkaiFes2026）

### ビルド失敗の真因は "scripts had compiler errors" の直前
コンソールは Missing Prefab や Rewired の GUID 警告で埋まるが、どれもビルドを止めない。→ Editor.log の `Error building Player because scripts had compiler errors` の直前の `error CS` を見る。（実例: 2026-09-06 lll-12 / 2026-06-01 LiveMultiRecorder）

### 同名 asmdef の二重でコンパイルが止まり「エラー 0」に見える
ScriptAssemblies がある時刻から更新されていない。原因はサブモジュール切替や二重配置で同じパッケージが Assets と Packages に入ること。→ 取り込み後は `Library/ScriptAssemblies/*.dll` の時刻を確かめ、片方を消す。Runtime と Editor の両アセンブリを検証する。（実例: 2026-09-13 / 09-23 SinkaiFes2026 / 2026-08-18 vortex_urp）

### Shader.Find はビルドで null になる
Editor では動くがビルドでマゼンタや初期化失敗。原因は参照・Resources・Always Included Shaders のどれにも無いシェーダが外れること。逆に `Resources/` 配下は未使用でも同梱され、壊れた Built-in シェーダでビルドが落ちる。→ シェーダを SO / マテリアルで参照するか Always Included へ。（実例: 2026-02 MARQ-Studio / 2026-09-13 lll-12）

### manifest.json を外で書き換えても再解決されない
足したパッケージが来ない、消したパッケージのエラーが残る。→ 追加は `packages-lock.json` を消して force_compilation、削除は lock 削除 + 再起動。先頭に BOM があるとパース自体が失敗する（`Char: 65279`）。（実例: 2026-06-01 LiveMultiRecorder / 2026-05-12 Submod_RealtimeLiveUtility）

### 同梱 Roslyn の単体コンパイルは偽陰性がある
Roslyn は通ったのに Unity で CS0246。原因は asmdef の参照条件を再現しないこと。UnityEditor.dll を参照に入れると CS0433。→ Unity を開いたら force_compilation で確かめ直す。（実例: 2026-08-27 Unity_ArtNetRecorder / 2026-09-23 vortex_urp）

### Succeeded でも通ったとは限らない・初回は 1 時間かかる
Build result が Succeeded でもシェーダエラーは残る（Unity はそれで失敗させない）。初回のシェーダバリアント生成は 40〜70 分で止まって見える。→ exe を起動して Player ログとキャプチャで確かめる。初回は background で投げ 5 分ごとに Editor.log を見る。（実例: 2026-08-24 2609SuiseiTour26 / 2026-06-01 LiveMultiRecorder）
