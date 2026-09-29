# process の罠

全件は ~/.claude/traps-catalog/process.md。ここは再発しやすいものだけ。

### コマンドラインの部分一致でプロセスを落とさない
`*dist\index.js*` で絞ると他プロジェクトのデーモンや MCP サーバー、絞り込み文字列を引数に持つ自分のシェルまで落ちる。→ プロセス名と、プロジェクト名を含む絶対パスの両方で絞り、対象を列挙してから止める。（実例: 2026-09-13 / 2026-09-26 SessionControl）

### ウィンドウタイトルで同定して閉じない
WindowsTerminal は前面タブのタイトルを出すので、`Claude Code - <案件>` の窓を閉じると他のタブのセッションも巻き添えになる。→ `ProcessName` と `StartTime` で確かめてから閉じる。（実例: 2026-09-23）

### kill してもツリーの本体が残る
`proc.kill()` や `taskkill /IM` の後も、chocolatey の shim の先の ffmpeg、uv → venv ランチャーの先の python、npm の先の vite、WebView2 の子が生き残り、パイプ・ポート・プロファイルを握り続ける。→ `taskkill /F /T /PID` でツリーごと止め、stderr は別スレッドで読み切る。（実例: 2026-07-19 SRT-Blue / 2026-09-23 DvcMCP）

### ParentProcessId で親を同定しない
Windows は PID を再利用するので、親が終わると無関係なプロセスが親に見える。→ CommandLine / ExecutablePath / CreationDate で判定する。（実例: 2026-09-16 AEMCP）

### パイプ越しの出力はたまるまで出ない
パイプに繋いだ子の stdout はブロックバッファされ、動いていても止まって見える。→ 進行は出力ファイルや CPU/メモリで判断する。（実例: 2026-07-19 SRT-Blue / 2026-09-17 AEMCP）

### 無関係なアプリが一斉に落ちる（GPU を失う）
887a0005 デバイスロスト・csc 1453・ENOBUFS が空きメモリ十分でも出る。原因はロック可能物理メモリの枯渇（SetProcessWorkingSetSize(80MB) が 1450 で確定）。モニタのスリープ復帰後に Unity・OBS・dwm が GPU を失い続けたこともある。→ どちらも OS 再起動（前に claudeLog へ引き継ぎ）。（実例: 2026-09-22 / 2026-09-27 SinkaiFes2026）

### SendInput はスキャンコードが要る
wScan=0 だと Home/End/矢印がテンキー扱いで GLFW/SDL に届かず、Unity Input System は注入キーをまったく検出しない（Alt+F4 だけ効くので届いていると誤解する）。→ MapVirtualKey でスキャンコードを埋め、拡張キーには KEYEVENTF_EXTENDEDKEY。（実例: 2026-08-24 MotionForge / 2026-08-25 2609SuiseiTour26）

### 削除や rename が EBUSY / Permission denied
自分が起動して止め忘れた常駐プロセスや、DLL をロードしたままのプロセスが cwd やファイルを握っている（Unity は終了直後もしばらくロックが残る）。→ 起動したものは作業の終わりに止める。ディレクトリの rename はファイル単位の mv に切り替える。（実例: 2026-05 Submod_RealtimeLiveUtility / 2026-09-24 SessionControl）
