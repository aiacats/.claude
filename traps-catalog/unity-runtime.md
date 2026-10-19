# unity-runtime の罠（カタログ）

MonoBehaviour のライフサイクル・偽 null・スレッド・Input・UI Toolkit / uGUI / IMGUI・アニメーション（Humanoid）など、Unity の実行時の罠の全件。

### GetComponent に ?? を使わない
- 症状: null チェックを通ったはずの参照で、後から `MissingComponentException`。
- 原因: Unity の「偽 null」（破棄済み・未取得の UnityEngine.Object）は C# の `??` / `?.` の null 判定を素通りする。
- 対策: `TryGetComponent(out var c)` か `if (c == null)` で判定する。UnityEngine.Object 全般に `?.` を使わない。
- 実例: 2026-09-24 ModelChecker（同じ日に 2 回）
- 自動検出: hook `cs-getcomponent-null-coalesce`
- 出典: rules/unity.md「検証の追加ルール」 / D:\_Personal\Project\ModelChecker\CLAUDE.md:47-48

### 受信スレッドから Debug.Log* を呼ぶとドメインリロードでデッドロックする
- 症状: Play 投入 / ドメインリロードで "Reloading Domain (busy for XX:XX)" のまま停止。別の回は "Access version should be odd when acquiring lock" を 6730 万回吐き、Editor.log が 3.7GB、C: の空き 0。
- 原因: リロード時に Mono が受信スレッドを abort → `ReceiveAsync().Result` が ThreadAbortException → `catch (Exception)` で捕まえて `Debug.LogException` → アンロード中のログのロックをメインスレッドと奪い合う。
- 対策: ワーカースレッドから `Debug.*` を呼ばず ConcurrentQueue 経由でメインスレッドで出す。`catch (ThreadAbortException)` は何もせず即 break。`AssemblyReloadEvents.beforeAssemblyReload` と OnDisable でスレッドを自分で止める。連続エラーに上限を設ける。
- 実例: 2026-08-04 / 2026-08-05 2609SuiseiTour26（ArtNetReceiver）
- 自動検出: 候補 `catch\s*\(\s*(?:System\.Threading\.)?ThreadAbortException[^)]*\)\s*\{[^}]*Debug\.Log`（patterns-unity-play.md `cs-threadabort-log`）
- 出典: 2609-LOG:281-290, 768-818 / M:D---ProjectBLUE-Project-2609SuiseiTour26/play-mode-allowed.md

### OnValidate は Player ビルドで呼ばれない
- 症状: Editor の Play では灯体が動くが、ビルドでは DMX に一切反応しない（_funcList が空）。
- 原因: 初期化の 1 回目を OnValidate が消費する前提の状態機械。ビルドでは Start からの 1 回だけで素通りする。
- 対策: 初期化を OnValidate に依存させない。「OnValidate を通さず Start 相当を 1 回だけ呼ぶ」プローブでビルド経路を再現して検証する。
- 実例: 2026-08-05 2609SuiseiTour26（VirtualFixture）
- 自動検出: 不可
- 出典: 2609-LOG:646-681

### Editor と Player でスクリプト実行順が違い、Start() で取ったサービスが null
- 症状: ビルドでだけ DMX を受けても灯体の色が変わらない（受信はできている）。
- 原因: `Start()` で `ServiceLocator.TryGet<CanvasManager>()` → ビルドでは登録前で null のまま。Start 同士の順序は保証されない。
- 対策: 依存は使う時点で解決する（遅延取得）か、Script Execution Order / `[DefaultExecutionOrder]` で明示する。初期化はイベント駆動にする。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:1592-1610, 1805-1830 / MARQ-CAU:58-86

### [NonSerialized] のハンドラが初期化中の例外で未設定のまま残り、無言で沈黙する
- 症状: DMX を受けても値が一切反映されない。警告なし。
- 原因: Start で先に走る初期化（materials[index] の範囲外など）が例外を出し、後続で作る NonSerialized の Handler が作られない。`_profile == null` の早期 return も同じ症状。
- 対策: 必須の構築を先に、例外源を後にする。範囲外・未設定は警告して null を返すヘルパにまとめる。
- 実例: 2026-08-12 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:1322-1328, 1390-1395

### 終了時の自動保存が空データで上書きする（Dispose と OnApplicationQuit の順序）
- 症状: 保存して再起動すると配置がすべて消えている。
- 原因: `ServiceLocator.Clear()` が IDisposable を Dispose → CanvasManager がクリア → その後 `OnApplicationQuit` の AutoSave が空リストを保存。別件で同期処理がリストを先に Clear してから破棄済みの依存を読んでいた。
- 対策: Dispose は各自の OnDestroy で行う（OnApplicationQuit の後）。保存は新リストに集めてから差し替え、依存が破棄済みなら同期をスキップ、空データで既存セーブを上書きしない。
- 実例: 2026-02-05 / 2026-03 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:1251-1275, 2577-2600 / MARQ-CAU 9 節

### FindObjectsByType(..., FindObjectsSortMode.None) の順序は不定
- 症状: 取得した一覧の並びが毎回変わる。登録順で振った ID・保存キーが別の灯体を指す。担当ライトが実行ごとに入れ替わる。
- 原因: 仕様として順序不定。
- 対策: ヒエラルキー（シーン番号 + GetSiblingIndex 列）でソートしてから ID を振る。
- 実例: 2026-08-12 SpotLightController / 2026-08-30 2609SuiseiTour26
- 自動検出: 不可（順序を使わない用途では None が正当で、誤検知が多い）
- 出典: 2609-LOG:2671-2685, 1407-1408

### FindObjectOfType は非アクティブを拾わない／Resources.FindObjectsOfTypeAll はシーン外のプレハブ資産まで拾う
- 症状: 非アクティブの LookatController が LookatManager に登録されない（警告も出ない）。逆に資産上のプレハブまで駆動対象になる。
- 原因: API の仕様差。
- 対策: `FindObjectsByType(FindObjectsInactive.Include, ...)` で使い分ける。見つからないときは警告を出す。
- 実例: 2026-08-04 2609SuiseiTour26 / 2026-09-16 SinkaiFes2026（vortexCharacterSetup。skill vortex-character-setup にも記載）
- 自動検出: 不可（正当な用途が多い）
- 出典: 2609-LOG:264-265 / SINKAI-LOG:384

### Transform.eulerAngles の getter は書いた三つ組を返さない
- 症状: (100,0,0) を書くと (80,180,180) が返る。書き込み後に読み直して表示するツールで、X が ±90 を跨ぐときや負値のときだけ触っていない軸が飛ぶ。
- 原因: 実体は Quaternion で、getter は正規化し直した表現を返す。
- 対策: 回転は四元数（なす角）で同一判定し、自分が書いた向きを表示側で保持する。同じ回転なら表示を更新しない。
- 実例: 2026-09-08 2609SuiseiTour26（FixtureTuner）
- 自動検出: 不可
- 出典: 2609-LOG:3630-3656 / Notion 3d5e4d4b-751b-817e-8514-d6aba2729030

### Prefab はシーン上のオブジェクトへの参照を持てない
- 症状: Camera[] で指定する設計が、Prefab しか触れない運用で使えない。
- 原因: Prefab → シーン参照は保存できない。
- 対策: 名前・階層パス・カテゴリ名などの文字列で指定し、実行時に解決する。解決できない綴り違いは一度だけログを出す。
- 実例: 2026-09-01 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:2839-2857

### UnityEvent の永続コールはアセンブリ名で型を指す（移植・asmdef 変更で黙って切れる）
- 症状: 移植後の LightControler.prefab の UnityEvent が旧アセンブリ RealtimeLiveUtilityURP を指したまま動かない。
- 原因: シリアライズされた `m_TargetAssemblyTypeName` にアセンブリ名が入る。
- 対策: 移植・asmdef 改名の後は `m_TargetAssemblyTypeName` を grep して結線を確認する。
- 実例: 2026-08-04 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:268-269

### 返り値が UniTask のメソッドは UnityEvent（onClick）に直接配線できない
- 症状: Inspector に候補として出ない。
- 原因: 永続リスナーは void メソッドしか受けない。
- 対策: void のラッパー（例: `FadeInDefault()`）を用意する。
- 実例: 2026-07-11 vortex_urp
- 自動検出: 不可
- 出典: VL:19-20

### UniTask を WhenAny に渡した後、同じ UniTask を再び await すると死ぬ
- 症状: `InvalidOperationException: Not yet completed, UniTask only allow to use await.` で State ループが死ぬ。以降は入力が一切効かない。
- 原因: UniTask は 1 回しか await できない。WhenAny が awaiter を消費する。Preserve でも防げない。
- 対策: 2 回以上 await するなら `.AsTask()` で Task にして `Task.WhenAny` を使う。
- 実例: 2026-05 vortex_urp（operator-experience）
- 自動検出: 不可（WhenAny 単体は正当）
- 出典: M:D---ProjectBLUE-Project--vortex-vortex-urp/feedback_unitask_double_await.md

### 実行時に書き換える値を ScriptableObject に書かない
- 症状: ビルド後に値が永続化されず、読み直しで巻き戻る。
- 原因: ScriptableObject アセットはビルドでは保存されない。
- 対策: 保存先は `Application.persistentDataPath`。例外: Inspector に出ている実体と一致させること自体が目的なら書いてよい（Volume の `sharedProfile` など）。その場合も Editor では `EditorUtility.SetDirty` を呼び、ビルドでは揮発する前提で保存側を用意する。
- 実例: 2026-09-02 2609SuiseiTour26（Volume パラメータの読み書き）
- 自動検出: 不可
- 出典: rules/unity.md「設計の癖」 / Notion 3cfe4d4b-751b-81e9-98ec-c6f86c78a769

### マテリアルアセットを Play 中に直接 SetTexture / SetColor すると .mat に差分が出る
- 症状: Play するたびに .mat が git 差分になる。共有する Renderer 全部に効く。ロードした Texture2D が解放されずリーク。
- 原因: `renderer.sharedMaterial` やアセットへ直接書き込んでいる。
- 対策: 実行時はインスタンスか MaterialPropertyBlock に書く（SRP Batcher との兼ね合いは unity-rendering 参照）。ロードしたテクスチャは差し替え時に Destroy。
- 実例: 2026-09-16 PRBL_Gacha
- 自動検出: 不可
- 出典: GACHA-MEM/gacha-code-flow-and-traps.md:208-209

### リフレクションで拾う実装はフィールド名変更・IL2CPP の stripping で黙って壊れる
- 症状: 対象に入っているのに効かない。コンパイルエラーにならず実行時まで気付かない。
- 原因: リフレクションは名前変更を検知できない。IL2CPP へ切り替えると managed stripping で項目が黙って消える（現状は Mono + stripping 無効を実測）。
- 対策: 拾えなかった対象は捨てずに警告を出す。IL2CPP にするなら `link.xml` か `[Preserve]`。
- 実例: （rules/unity.md の設計注意）
- 自動検出: 不可
- 出典: rules/unity.md「設計の癖」

### Edit モードで PlayableGraph を手動評価しても Humanoid の骨に書き込まれない
- 症状: `SetTime` + `Evaluate` しても Hips の回転差 0°。GUI で再生すると動いて見える。
- 原因: Edit モードの手動評価では Humanoid の骨へ書かれないことがある。
- 対策: Edit モードでクリップを当てるなら `AnimationClip.SampleAnimation`（Humanoid でも効く。実測 16.4°）。テストで「当てた直後に動いたか」を測る。
- 実例: 2026-09-24 ModelChecker
- 自動検出: 不可
- 出典: rules/unity.md「検証の追加ルール」 / Notion 3e5e4d4b-751b-8129-9554-dfe2df9574c0

### フレームレート依存の加算（Time.deltaTime 無し）
- 症状: Gobo 回転が 120fps で 60fps の倍速。
- 原因: 1 フレームあたり固定角を加算している。
- 対策: 度/秒 × deltaTime。見た目互換の係数は由来をコメントに残す。
- 実例: 2026-08-05 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:689-714

### Mono の Path.GetDirectoryName("") は ArgumentException
- 症状: 初回に「…」ボタンで例外。
- 原因: .NET と違い Mono は空文字で例外を投げる。
- 対策: 空なら既定フォルダを使う。
- 実例: 2026-09-14 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:159

### クリップ未ロードの AudioSource で time を書くとエラー
- 症状: 音声なしでループさせると、巻き戻すたびにエラー。
- 原因: clip が null のまま `AudioSource.time` へ書き込んでいる。
- 対策: clip の有無を確認してから操作する。
- 実例: 2026-08-27 Unity_ArtNetRecorder
- 自動検出: 不可
- 出典: AL:13-14

### Input System はスキャンコード無しの keybd_event を検出しない
- 症状: 自動テストで Esc / F1 を送っても何も起きず「実装が動いていない」ように見える。Alt+F4 だけは効くので切り分けを誤る。win-gui の key_press も Game View に届かない。
- 原因: Input System はスキャンコードを見る。Alt+F4 はウィンドウメッセージ経由。
- 対策: `KEYEVENTF_SCANCODE` + bScan で送る。win-gui では届かないので、フラグの直接操作か invoke_method でハンドラを呼ぶ。
- 実例: 2026-08-25 2609SuiseiTour26 / 2026-09-25 SinkaiFes2026
- 自動検出: 不可（送信側スクリプトの判定は windows-shell 側）
- 出典: 2609-LOG:2156-2161 / SINKAI-LOG:840 / Notion 3c7e4d4b-751b-813d-a42b-f219c2e53aaf

### Active Input Handling が New 専用だと旧 Input API が InvalidOperationException
- 症状: デモスクリプト（AVPro QuickDeviceMenu 等）が毎フレーム例外 → GC 16KB/frame。
- 原因: activeInputHandler=1（New 専用）。
- 対策: 旧 Input を使うサードパーティのデモ UI は外すか Input System 版へ。asmdef 配下なら InputSystem の参照を足す。
- 実例: 2026-08-25 2609SuiseiTour26 / 2026-09-15 SinkaiFes2026
- 自動検出: 不可（旧 Input のプロジェクトでは正当）
- 出典: SINKAI-LOG:184, 214-222, 257 / 2609-LOG:2144-2146

### Input System の Value アクションは 0 で canceled、Disable でも canceled が飛ぶ
- 症状: MIDI CC を 0 にしても黒にならない。canceled を拾うと、機器の再初期化のたびに 0 が届いて黒に跳ぶ。
- 原因: Value 型は既定値に戻ると canceled。Disable も値 0 で canceled を発火する。
- 対策: PassThrough にして performed だけ購読する。検証時は Editor を前面に（Run In Background OFF）。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:309-311 / Notion 3dce4d4b-751b-81f0-9b2e-d9d1ac58dd3e

### Gamepad.all のインデックスは接続順に依存する
- 症状: 本番で抜き差しすると担当のパッドが入れ替わる。
- 原因: インデックス方式で指定している。
- 対策: 固定したいなら製品名やシリアルで照合する。
- 実例: 2026-08-16 RemoteLive
- 自動検出: 不可
- 出典: RL(RemoteLive):37-38

### Rewired のジョイスティック自動割り当ては並び順で先頭のプレイヤーに取られる
- 症状: 目的のコントローラ（CineCamDroneController）が全く反応しない。エラーも出ない。
- 原因: autoAssignJoysticks=1 で Facial0〜10 が除外されておらず、パッドが Facial0 に割り当てられた。DivideController は player が null のときしかエラーを出さない。
- 対策: 目的外のプレイヤーを自動割り当てから外す。または Input System の `devices` で対象の 1 台に絞る。
- 実例: 2026-08-16 RemoteLive
- 自動検出: 不可
- 出典: RL(RemoteLive):5-13

### ランタイム IMGUI は Editor と見た目が変わる（wordWrap 既定 ON・CalcSize 不足）
- 症状: Editor では 1 行の「CH 1」が実行時・ビルドで 2 行に折り返して枠から溢れる。末尾が欠ける。
- 原因: EditorStyles.label は wordWrap OFF だが GUI.skin.label は ON。CalcSize が数 px 足りず TextClipping.Clip で切れる。
- 対策: wordWrap=false を明示、実測 + TextClipping.Overflow。セル高は lineHeight から算出。Skin を注入する。
- 実例: 2026-08-25 / 2026-08-28 2609SuiseiTour26
- 自動検出: 不可
- 出典: 2609-LOG:2188-2192, 2423-2425 / Notion 3c7e4d4b-751b-8152-b9ee-fe1801e1e960

### IMGUI（OnGUI）は Display 1 にしか描けない
- 症状: Game ビューを Display 3 / 4 にすると IMGUI のオーバーレイや AVPro GUIDisplay が見えない。ビルドで Display 4 に UI を出せない。
- 原因: OnGUI は主ディスプレイ固定。
- 対策: 他ディスプレイには UI Toolkit（PanelSettings.targetDisplay）か Canvas を使う。
- 実例: 2026-09-15 / 2026-09-25 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:187, 818-826

### Canvas.targetDisplay が別 Display の Overlay UI は、そのディスプレイを映す Game ビューでしかクリックできない
- 症状: ボタンが「押せない」。実際は別の Game ビューをクリックしていた。
- 原因: Overlay のクリックは対象ディスプレイを映す Game ビューにしか届かない。
- 対策: 押すビューの Display を確認する。レイアウト変更による座標ずれも疑う。
- 実例: 2026-07-11 vortex_urp
- 自動検出: 不可
- 出典: VL:50-57

### Canvas が Constant Pixel Size・RawImage 3840x2160 固定だと、FHD の Game View では中央切り出しになる
- 症状: 「Display 4 が寄っている」。エラーは出ない。
- 原因: 解像度に追従しない Canvas 設定。
- 対策: 書き出し・確認は実解像度（4K）で行うか、Scale With Screen Size にする。
- 実例: 2026-09-27 SinkaiFes2026（skill vortex-timeline-export の罠 7 にも記載）
- 自動検出: 不可
- 出典: SINKAI-LOG:882-883

### Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf") は Unity 2022.1 以前では null
- 症状: コードで生成した uGUI の Text がすべて見えない。
- 原因: "LegacyRuntime.ttf" は 2022.2 以降の名前。2022.1 以前は "Arial.ttf"。
- 対策: Unity のバージョンに合わせた名前で引く。取れなければエラーにする。
- 実例: 2026-06-15 Unity_ArtNetRecorder
- 自動検出: 不可（ProjectVersion との照合が要る）
- 出典: AC:74-81

### UI Toolkit のランタイム PanelSettings にテーマが無いと、テキストだけ描画されない
- 症状: Play 中、パネルの図形は出るが Label / Button の文字が一切出ない。
- 原因: themeStyleSheet が null（Resources の .tss 未作成）で既定フォントが供給されない。
- 対策: `@import url("unity-theme://default");` の .tss を作って割り当てる。ランタイム生成の PanelSettings は必ずテーマを確認する。
- 実例: 2026-06-21 ReLink
- 自動検出: 不可
- 出典: RL(ReLink)\.claude\claudeLog.txt:206-216, 223-226

### UXML に USS をリンクし忘れると崩れて見える
- 症状: UI Toolkit の画面が未スタイルで崩れて見える。
- 原因: UXML ↔ USS が未リンク。
- 対策: UXML のリンクとコードの `styleSheets.Add` で確実に適用する。レイアウト崩れはまずスタイル未適用を疑う。
- 実例: 2026-06 ReLink
- 自動検出: 不可
- 出典: D---Personal-Project-ReLink/memory/conduit-architecture.md:13 / CLAUDE.md（2026-06-01 の例）

### UI Toolkit でアイコンフォントは -unity-font ではなく -unity-font-definition
- 症状: Lucide の play を出したはずが別のグリフになる。□にならないので効いていると誤認する。警告も出ない。
- 原因: 継承された FontAsset（TextCore）が `-unity-font: url(ttf)` に勝つ。
- 対策: `-unity-font-definition: url("Fonts/lucide.ttf")`。グリフは C# で `\uXXXX` エスケープで持ち、コードポイントは fonttools で cmap を確認する。
- 実例: 2026-06-01 LiveMultiRecorder
- 自動検出: 候補 `(?<![\w-])-unity-font\s*:`（patterns-unity-play.md `uss-unity-font`）
- 出典: LMR-MEM/uitoolkit-custom-font-definition.md / LMR-LOG:417-419

### UI Toolkit の flex 行で長い文字列がボタンを押し出す
- 症状: 長いパスで入力欄が縮まず、ボタンが枠外へ出る。
- 原因: flex 子の min-width 既定が auto。
- 対策: 入力欄に `min-width: 0` + flex-shrink、ボタンに `flex-shrink: 0`。
- 実例: 2026-06-21 ReLink
- 自動検出: 不可
- 出典: RL(ReLink)\.claude\claudeLog.txt:228-230

### UI Toolkit の flex 中央寄せは、子が親より大きいと中央にならない
- 症状: キャンバスを 4K にするとビューポート中央に来ない。
- 原因: `align-items` / `justify-content: center` は子がはみ出すと片側に寄る。
- 対策: `position: absolute; left/top: 50%` + transform で -size/2 オフセット。
- 実例: 2026-02-04 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:1040-1055

### UI Toolkit の worldBound は transform の scale を反映しない
- 症状: ズーム時にクリック位置と判定がずれる。中心から離れるほどずれる。
- 原因: worldBound で位置を取りつつズームを二重に掛けていた／worldBound が transform を正しく反映しない。
- 対策: `WorldToLocal` / `LocalToWorld` で変換する。
- 実例: 2026-02-04 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU 8 節 / MARQ-LOG:1010-1060

### UI Toolkit のルートで TrickleDown の KeyDown を StopPropagation すると子パネルのキー操作が死ぬ
- 症状: Hierarchy で上下キーを押すと別機能（ピクセル移動）が発動し、一覧の選択が動かない。
- 原因: キャプチャフェーズで先に処理して伝搬を止めている。
- 対策: フォーカスがパネル内ならルートの処理をスキップする（`focusController.focusedElement` で判定）。
- 実例: 2026-02-26 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:2368-2385

### Graphics.CopyTexture はサイズ一致・非 MSAA が必須で、失敗しても毎フレーム警告を吐くだけ
- 症状: 映像が通らない。Editor.log に mismatching texture sizes が 2180 件。
- 原因: WebCamTexture が要求解像度（4K）より小さい 1080p を返した／コピー先 RT が MSAA 8。
- 対策: サイズ・MSAA の一致が保証できなければ `Graphics.Blit`。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可（一致していれば正当）
- 出典: SINKAI-LOG:281-290

### AVPro Live Camera は D3D12 で真っ黒（エラーも出ず「有効」扱い）
- 症状: StartDevice 成功・GetLastFrameUploaded も進むのにテクスチャが黒。
- 原因: ネイティブが GetNativeTexturePtr に直接書く方式で D3D12 非対応。Graphics API 自動 = DX12。
- 対策: PlayerSettings で D3D11 を先頭に固定する。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:182-199

### AVProLiveCameraMaterialApply の既定プロパティは _MainTex（URP は _BaseMap）
- 症状: 映像がマテリアルに乗らない。URP シェーダは隠し _MainTex を持つのでエラーも出ない。
- 原因: 既定値が Built-in 前提。
- 対策: `_BaseMap` / `_EmissionMap` を指定する。Emission 乗算なら `_EmissionColor` が黒でないことも確認。
- 実例: 2026-09-15 SinkaiFes2026
- 自動検出: 不可
- 出典: SINKAI-LOG:209-210, 253-254

### Win32 GetOpenFileName がカレントディレクトリを変えて Unity が落ちる
- 症状: ネイティブのファイルダイアログを使うとエディタがクラッシュ／エラー。
- 原因: GetOpenFileName は既定でワーキングディレクトリを変更し、Unity がそれを検知して壊れる。
- 対策: `OFN_NOCHANGEDIR (0x8)` を付け、try/finally で CWD を保存・復元する。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 候補（patterns-unity-play.md `cs-getopenfilename-cwd`）
- 出典: MARQ-LOG:1766-1800

### Screen.GetDisplayLayout と EnumDisplayMonitors はモニタ順が違う
- 症状: 出力先ドロップダウンのモニタ名と実際に出るモニタが食い違う。
- 原因: 表示名は Unity API、実出力は Win32 で列挙しており、インデックスが別物を指す。
- 対策: 表示・出力とも同じ API（EnumDisplayMonitors + MONITORINFOEX + EnumDisplayDevices）に統一する。
- 実例: 2026-03-21 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-LOG:2641-2660

### DIB の biHeight が正だと上下反転
- 症状: `SetDIBitsToDevice` でウィンドウへ出した映像が上下逆。
- 原因: biHeight 正 = ボトムアップ。`ReadPixels` の並びと合わない。
- 対策: `biHeight = -height`（トップダウン）。
- 実例: 2026-02-05 MARQ-Studio
- 自動検出: 不可
- 出典: MARQ-CAU 10 節 / MARQ-LOG:1491-1515

### 他分野・skill に置いたもの
- Cinemachine 2 の Brain がレイヤーで候補を絞る → traps-catalog/unity-timeline.md
- 高い Script Execution Order（OscRx_LipSync）が検証用コンポーネントの値を上書き、UDP バインド失敗の高速ループ → traps-catalog/vortex.md
- LookatManager に非アクティブのキャラが登録されない → skill vortex-character-setup に記載（上の FindObjectOfType 項目が一般則）

---
出典の略記: 2609-LOG = D:\_ProjectBLUE\Project\2609SuiseiTour26\log\claudeLog.txt / SINKAI-LOG = D:\_ProjectBLUE\Project\SinkaiFes2026\log\claudeLog.txt / VL = D:\_ProjectBLUE\Project\_vortex\vortex_urp\log\claudeLog.txt / MARQ-LOG = D:\_ProjectBLUE\Project\MARQ\MARQ-Studio\.claude\claudeLog.txt / MARQ-CAU = D:\_ProjectBLUE\Project\MARQ\MARQ-Studio\CLAUDE-UnityCaution.md / LMR-LOG = D:\_ProjectBLUE\Project\LiveMultiRecorder\.claude\claudeLog.txt / LMR-MEM = C:\Users\komao\.claude\projects\D---ProjectBLUE-Project-LiveMultiRecorder\memory / GACHA-MEM = C:\Users\komao\.claude\projects\D---ProjectBLUE-Project-PRBL-Gacha\memory / RL(RemoteLive) = D:\_ProjectBLUE\Project\_vortex\RemoteLive\log\claudeLog.txt / RL(ReLink) = D:\_Personal\Project\ReLink / AC・AL = D:\_ProjectBLUE\Project\_thirdParty\Unity_ArtNetRecorder の .claude\claudeLog.txt・log\claudeLog.txt / M:<name> = C:\Users\komao\.claude\projects\<name>\memory

### 無効（非表示）のキャラに SkinnedMeshRenderer.BakeMesh を掛けると、骨の姿勢が反映されない
- 症状: Edit モードで BakeMesh した頂点から口の位置を求めたら、無効のキャラ（Timeline で出すために非表示で置いてある）だけ 12〜14 cm 下・後ろにずれた。有効のキャラは 0.1〜1 cm。エラーは出ない。
- 原因: 無効の SkinnedMeshRenderer は骨の行列を更新しないので、BakeMesh が今の骨の姿勢を反映しない（実測。ドキュメントには無い）。
- 対策: 要る頂点だけ、`smr.bones[i].localToWorldMatrix * mesh.bindposes[i]` を boneWeights で重み付けして自分でスキニングする（有効・無効に関係なく今の骨の位置になる）。または一時的に有効にしてから焼く（シーンを変えるので避けた）。
- 実例: 2026-10-19 SinkaiFes2026（vortex-character-setup の VortexCharMic.CreateMicMouth。きまゆ・Anjo・Kosaka が無効で 14 cm → 1.3 cm）
- 自動検出: 不可
- 出典: SinkaiFes2026 log/claudeLog.txt 2026-10-19
