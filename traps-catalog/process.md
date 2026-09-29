# process の罠（カタログ）

Windows のプロセス管理（kill・孤児・PID 再利用）、GPU/メモリ枯渇、SendInput/入力、スリープ復帰、MIDI ループバックなど OS 挙動で踏んだ罠の全件。厳選版は `~/.claude/rules/traps/process.md`。

### コマンドラインの部分一致でプロセスを落とすと、他プロジェクトや自分のシェルまで落ちる
- 症状: `*server\dist\index.js*` で絞って止めたら、MemoryObserver のデーモンや他セッションの AEMCP / BMCP の MCP サーバーまで停止した。別の回は、絞り込み文字列を引数に持つ自分の bash.exe / powershell も一致して落ち、後続の `Start-ScheduledTask` が走らずデーモンが止まったまま
- 原因: 同じ構成（`server\dist\index.js`, `run-hidden.vbs`）のプロジェクトが多い。検索文字列はそれを実行しているシェル自身のコマンドラインにも含まれる
- 対策: プロセス名（node.exe / wscript.exe）で絞り、かつプロジェクト名を含む絶対パスで絞る。止める前に対象を列挙して確認する。止めた後は `(Get-ScheduledTask).State` と新しいログで起動を確かめる
- 実例: 2026-09-13 SessionControl / 2026-09-23 SessionControl / 2026-09-26 SessionControl
- 自動検出: 候補 `kill-by-commandline-without-name`
- 出典: SessionControl/log/claudeLog.txt:870, :1117, SessionControl memory auto-deploy.md:20-24, rules/app.md（SessionControl 再起動手順）

### ウィンドウタイトルでプロセスを同定して閉じない（WindowsTerminal は前面タブのタイトルを出す）
- 症状: `Claude Code - <プロジェクト>` と表示されていても、実体は複数タブを抱えたターミナルで、閉じると他プロジェクトのセッションを巻き添えにする
- 原因: WindowsTerminal は前面タブのタイトルをウィンドウタイトルに出す
- 対策: 閉じる前に `ProcessName` と `StartTime` を確認する。`MainWindowTitle` だけで同定しない
- 実例: 2026-09-23（lll-12 / ftpDeck / SinkaiFes2026 を巻き込みかけた）
- 自動検出: 候補 `kill-by-window-title`
- 出典: CLAUDE.md「Claude Code / Unity の再起動」

### kill してもツリーの本体が残る（chocolatey shim・uv→venv ランチャー・npm ラッパー・WebView2）
- 症状: 取り消しで `proc.kill()` / `exec.CommandContext` の cancel をしても本物の ffmpeg が生き残りパイプを握り、以後の呼び出しが無応答・publish が止まらない。MCP クライアントがサーバーを閉じるたびに Python ワーカが残る。Claude Code の TaskStop 後も vite が 5173 を掴んだまま。`taskkill /F /IM app.exe` 後に再起動したアプリの窓が出ない
- 原因: 握っている PID は親だけ。chocolatey の `bin\ffmpeg.EXE` は shim で本体が子。node → uv → venv の python.exe（ランチャー）→ 本体の 4 段で stdin の EOF が届かず、`proc.kill()` は uv しか止めない。`npm run dev` の子（vite）が残る。`/T` 無しの taskkill は子の msedgewebview2.exe を残し `%APPDATA%\<exe名>\EBWebView` をロックしたままにする
- 対策: `taskkill /F /T /PID`（または Job Object）でツリーごと止める（Unix はプロセスグループへ SIGKILL）。stderr は別スレッドで読み切る。ワーカには親 PID を渡し `WaitForSingleObject` で親の終了を待って自分も終わる。残骸は `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` の親子で、本体側（元 Python のパス）を見る。dev サーバーは `netstat -ano | grep :<port>` で PID を特定
- 実例: 2026-07-03 Traddist（vite）/ 2026-07-18 SRT-Blue（WebView2）/ 2026-07-19 SRT-Blue（ffmpeg）/ 2026-09-23 DvcMCP（ffmpeg・uv）
- 自動検出: 候補 `taskkill-im-without-tree`
- 出典: DvcMCP/CLAUDE.md:64-67, :73-77, SRT-Blue/log/claudeLog.txt:637-641, SRT-Blue memory wails-hidden-window-trap.md:21, Traddist/log/claudeLog.txt:30, Notion 3e4e4d4b-751b-81fd-866e-d869ba6c9cad

### ParentProcessId はプロセスの素性判定に使えない（PID 再利用）
- 症状: 普通に起動した AE の親が dynamiclinkmanager.exe に見え、誤判定で機能が黙って死ぬ
- 原因: ParentProcessId は作成時の数値のまま。起動元が終了すると同じ PID を別プロセスが取る
- 対策: CommandLine / ExecutablePath / CreationDate など自身の情報で判定する。判定できないときの倒し方を決めておく
- 実例: 2026-09-16 AEMCP / 2026-09-17 AEMCP
- 自動検出: 不可（子の列挙など正当な用途がある）
- 出典: AEMCP/CLAUDE.md:146-151, AEMCP/log/claudeLog.txt:751-756, Notion 3dde4d4b-751b-817e-8be5-fb8594767f01
- 旧説: 「親プロセス名で判定するのが曖昧さが無い」（Notion 3dde4d4b-751b-8127）（誤り）

### Windows ConPTY は孫プロセスが残る限り EOF を返さない／子だけ管理者昇格できない
- 症状: claude を exit しても終了を検知できない（MCP を使うプロジェクトでだけ起きる）。擬似コンソール内の子プロセスだけ管理者で起動できない
- 原因: claude が起動した MCP サーバー等の孫が PTY ハンドルを保持する。昇格は ShellExecute runas 経由になり擬似コンソールへアタッチできない
- 対策: 終了検知を PTY EOF に依存させず、直接の子の `try_wait()` を別スレッドで見る。kill は `taskkill /T /F`。昇格が要るならアプリ全体を requireAdministrator で起動し、子に昇格トークンを継承させる（Tauri は windows-app-manifest.xml + build.rs の WindowsAttributes）
- 実例: 2026-06 Claudes / 2026-06-11 Claudes / 2026-06-20 Claudes
- 自動検出: 不可
- 出典: Claudes:44-47, 66-80, 412-427

### MSYS の孫プロセスがパイプを握り、close を待つと返らない
- 症状: git を取り消しても 20 秒返らない
- 原因: フックを走らせる sh の孫（sleep 等）は MSYS の作りで親子関係が外れ、`taskkill /T` が届かず stdout のパイプを握る
- 対策: 子プロセスの完了は `exit` イベントで決着させる（`close` を待たない）。実測 exit 2.8s / close 20s
- 実例: 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/CLAUDE.md:171

### 外部プロセスの stdout はパイプ相手だとブロックバッファリングされる
- 症状: 進んでいてもログが数十行たまるまで出ない。「1 行しか出ていない = 止まっている」と誤認する
- 原因: パイプ接続時の stdio バッファリング（aerender、ffmpeg の avio 出力も同類）
- 対策: 進行は出力ファイルの有無・プロセスのメモリ/CPU で判断する。ffmpeg の `ametadata` なら `direct=1`
- 実例: 2026-07-19 SRT-Blue / 2026-09-17 AEMCP
- 自動検出: 不可
- 出典: AEMCP/CLAUDE.md:124-126, SRT-Blue/log/claudeLog.txt:762-767

### ファイル・ディレクトリを他プロセスが握っていて削除・rename が EBUSY / Permission denied
- 症状: `claude rm` / worktree 削除、テスト後片付けの rmdir が EBUSY。Unity を閉じても `git mv Runtime ...` が Permission denied。MCP 経由の削除が Device or resource busy で、Unity 終了直後もロックが残る
- 原因: 検証用に起動した常駐プロセス（相対パス起動でコマンドラインにパスが出ない）や close 後も走っていた git が cwd を握っていた。ディレクトリ内の DLL（websocket-sharp.dll など）がどこかのプロセスにロードされたまま（中の 1 つでも開いていると rename は塞がれる）。Unity がファイルを開いている
- 対策: 自分が起動した常駐プロセスは作業の終わりに止める。犯人は起動時刻・jobs ディレクトリから特定する。ディレクトリの rename はファイル単位の mv ループに切り替える（718 件とも成功。親の .meta は別途 git mv）。Unity のファイルは Unity を終了して少し待ってから消す
- 実例: 2026-05 Submod_RealtimeLiveUtility / 2026-05-31 vortex_urp / 2026-09-13 SessionControl / 2026-09-24 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:812, :1063, SL:326-331, VC:257

### 他のプロセスが CPU を使い切ると子プロセスの起動そのものが数分かかる
- 症状: `claude agents --json --all did not respond within 30000ms` が毎分出る
- 原因: Unity のシェーダーコンパイル 12 本以上が CPU を使い切っていた。アプリの不具合ではない
- 対策: タイムアウトが出たらまず他プロセスの負荷を確認する
- 実例: 2026-09-25 SessionControl
- 自動検出: 不可
- 出典: SessionControl/log/claudeLog.txt:1075

### 多コア機で CPU 使用率からビルドの進行を判断すると誤る
- 症状: ビルドが止まったと判断して 2 回打ち切ったが、.bat は次の行へ進んで `[OK] Build complete` を出した
- 原因: 32 論理コアでは 1 コア全開でも全体の約 3%。`Get-Process` の `.CPU` 差分も当てにならない
- 対策: skill tauri-release に記載（成果物の日時と rustc の起動時刻の入れ替わりで見る）
- 実例: 2026-09-23 ftpDeck
- 自動検出: 不可
- 出典: ftpDeck/log/claudeLog.txt:956, skills/tauri-release/SKILL.md:49-50

### CPU 使用率を os.cpus() の累積時間差で出すとタスクマネージャーと一致しない／typeperf の改行は 1 サンプル遅れる
- 症状: 16 スレッド全開でも 12.7%（タスクマネージャーは 87%）。typeperf を行単位で読むと 1 秒遅れる
- 原因: 累積時間差は `% Processor Time`、タスクマネージャーは `% Processor Utility`（ターボ込み）。typeperf は値の後ろの改行を次のサンプルの頭で出す
- 対策: `typeperf "\Processor Information(_Total)\% Processor Utility" -si 1` を読む（英語カウンタ名で日本語 Windows でも通る）。100 超は 100 で止める。`"時刻","値"` の組が揃った時点でパースする
- 実例: 2026-09 MemoryObserver
- 自動検出: 不可
- 出典: MemoryObserver/log/claudeLog.txt:97-102

### コミットチャージは Win32_OperatingSystem から取れない（FreeVirtualMemorySize が空）
- 症状: FreeVirtualMemorySize が空 → 0 → 「上限いっぱい」の嘘の値
- 原因: 環境によって当該プロパティが空を返す
- 対策: `Win32_PerfRawData_PerfOS_Memory` の `CommittedBytes` / `CommitLimit` をバイトで読む（英語固定で言語非依存）。limit<=0 は取得失敗扱い
- 実例: 2026-09-22 MemoryObserver
- 自動検出: 候補 `FreeVirtualMemorySize`（warn）
- 出典: MemoryObserver/CLAUDE.md:46-48, Notion 3e3e4d4b-751b-8163-bca6-d478baec6691

### ロック可能物理メモリの枯渇で GPU デバイスロスト・無関係なプロセスが一斉に落ちる
- 症状: 重いシーンを開くと Unity が 887a0005 デバイスロスト、csc が 1453 でコンパイル停止、Winsock ENOBUFS、NVIDIA Overlay も落ちる。空きメモリは 49GB あっても起きる
- 原因: OS 全体の Resident Available 枯渇。カーネルドライバがページをロックしたまま（ドライバのハンドルリーク疑い: RunSwUSB）
- 対策: 非管理者 PowerShell で SetProcessWorkingSetSize(最小 80MB) を試し、1450 で失敗すれば確定（lockcheck.ps1）→ OS 再起動
- 実例: 2026-09-22 SinkaiFes2026 / 2026-09-23 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026/log/claudeLog.txt:455-465, 492-495, Notion 3e3e4d4b-751b-8162-ac7f-d31914f73822

### モニタのスリープ復帰後に Unity・OBS・dwm が GPU を失い続ける（この PC）
- 症状: 書き出し中・待機中・起動直後のどれでも `Failed to present D3D11 swapchain due to device reset/removed`。TDR 記録なし
- 原因: 未確定。再起動後にモニタが一度自動オフ→復帰した状態（Kernel-Power 566 と一致）が契機。解像度・負荷・ドライバ版とは無関係。スリープ無しの回に C: の Search 3079 と同時刻の発生も 1 回ある
- 対策: 長時間録画の前にモニタ自動オフを「なし」にする（AC は無効化済み。Git Bash からは powershell 経由で `powercfg`）。一度スリープしていたら録る前に再起動する。録画の手順は skill vortex-timeline-export に記載
- 実例: 2026-09-26 SinkaiFes2026 / 2026-09-27 SinkaiFes2026
- 自動検出: 不可
- 出典: SinkaiFes2026/log/claudeLog.txt:909-917, SinkaiFes2026 memory gpu-loss-after-monitor-sleep.md, skills/vortex-timeline-export/SKILL.md:35-37, :177-180

### GPU ドライバーの不調で、新しく GPU を使うアプリが起動直後に落ちる
- 症状: Blender（nvoglv64.dll）、Unity（CreateD3D12GfxDevice 内の nvwgf2umx.dll）、OBS が次々に落ちる。EEVEE の背景レンダーが exit 127
- 原因: ドライバー側の状態の不調
- 対策: OS を再起動する（前に claudeLog へ引き継ぎを書く）
- 実例: 2026-09-27 Ext_TokinoSora_2026-pia
- 自動検出: 不可
- 出典: Ext_TokinoSora_2026-pia log TS:92-100, 161

### SendInput でナビゲーションキーが届かない（wScan=0 でテンキー扱い）
- 症状: Home/End/PageUp/PageDown/矢印が GLFW/SDL アプリに届かない（VK_HOME → テンキー7）。文字キーは届く
- 原因: wScan=0 だと MapVirtualKey でテンキーのスキャンコードに化ける。KEYEVENTF_EXTENDEDKEY が無い
- 対策: MapVirtualKey でスキャンコードを埋め、拡張キー集合に KEYEVENTF_EXTENDEDKEY を付ける。WinGuiMcp は `SendVirtualKey()`（d311d33）で修正済み。publish が古いと直っていない
- 実例: 2026-08-24 MotionForge
- 自動検出: 不可
- 出典: MotionForge/log/claudeLog.txt:690, Notion 3c6e4d4b-751b-811c-a9d5-f630b713cd68

### Unity Input System はスキャンコード無しの keybd_event を検出しない
- 症状: 注入した Esc が一度も検出されない。Alt+F4 は効くので注入は届いていると誤判断する
- 原因: Input System はスキャンコードで解決する。Alt+F4 は DefWindowProc 経由
- 対策: `KEYEVENTF_SCANCODE` + 実スキャンコード（Esc=0x01）で送る。Player の Quit 確認は 2 秒以上待つ
- 実例: 2026-08-25 2609SuiseiTour26
- 自動検出: 候補 `keybd_event\([^,]+,\s*0\s*,`（.ps1 .py .cs、warn）
- 出典: Notion 3c7e4d4b-751b-813d-a42b-f219c2e53aaf

### Windows には標準のループバック MIDI が無い（loopMIDI は常駐中だけ）
- 症状: 出力ポートが GS Wavetable Synth だけ／loopMIDI を入れたのに 0 本／MIDI 出力先ポートが見つからない
- 原因: OS 標準の仮想ポートが無い。loopMIDI のポートは loopMIDI.exe 常駐中しか存在しない
- 対策: 疎通確認・テストの前に loopMIDI の常駐を確認する。ポートは名前で保存し、再スキャンの導線と案内を出す。既存の `loopMIDI Port` は他用途の可能性があるので触らず専用ポートを作る
- 実例: 2026-09-06 OSC2MIDI
- 自動検出: 不可
- 出典: OSC2MIDI memory osc2midi-purpose-and-environment.md:16-17, Notion 3d3e4d4b-751b-8107-be87-c81ebd27b8fe

### Windows 11 25H2 の WinMIDI Services(midisrv) が loopMIDI のポートを見失う
- 症状: loopMIDI の仮想ポートが Stream Deck / DAW から見えなくなる
- 原因: midisrv が teVirtualMIDI 系の動的ポート追加を検出し損ねる（MS 公式 known issue）
- 対策: MidiSrv を Disabled にする可逆スクリプト（tools/midisrv-toggle）。Windows Update で Manual に戻ることがあるので月次点検。Midi2 API を使うアプリは同機で動かなくなる
- 実例: 2026-05-04 StreamDeckMIDI
- 自動検出: 不可
- 出典: StreamDeckMIDI:3-11, 37-42

### タスクスケジューラ経由の .vbs が node の終了を待たないと再起動ポリシーが効かない
- 症状: デーモンが落ちてもタスクが再起動しない
- 原因: run-hidden.vbs が起動して即終了するので、タスクは「正常終了」とみなす
- 対策: `WScript.Shell.Run(cmd, 0, True)` で終了まで待つ
- 実例: 2026-09-05 SessionControl
- 自動検出: 候補 `\.Run\([^)]*,\s*0\s*\)`（.vbs、warn）
- 出典: SessionControl/log/claudeLog.txt:78

### Windows ファイアウォールの Public プロファイルで受信が届かない
- 症状: 別 PC からの OSC が届かない可能性（受信許可規則なし・Ethernet が Public）
- 原因: 受信許可のファイアウォール規則が無い。Public ネットワークでは既定で遮断
- 対策: UDP 受信を使うアプリは受信規則の有無とネットワークプロファイルを最初に確認する
- 実例: 2026-09-15 Sequence
- 自動検出: 不可
- 出典: Seq/log/claudeLog.txt:2682
