# git の罠

全件は ~/.claude/traps-catalog/git.md。ここは再発しやすいものだけ。

### .gitignore は先頭 / で固定する
`tools/` は全階層に当たり、`server/src/tools/` が一度もコミットされていなかった（ローカルでは全部通る）。親を ignore すると子の `!` も効かない。→ 直下だけなら `/tools/`。書いたら `git check-ignore -v`。（実例: 2026-09-16 AEMCP）

### lfs migrate の後は checkout
`git lfs migrate import` は作業コピーを smudge せず、Unity がポインタを読んで壊れる。→ 直後に `git lfs checkout`。.meta は LFS に入れない。（実例: 2026-06-20 ReLink）

### サブモジュールを先に push する
親だけ、またはポインタだけ先に進めると他の環境でコンパイルが壊れる。→ サブモジュールをコミット・push してから親のポインタを進める。（実例: 2026-09-06 vortex_urp / 2026-09-14 Ext_Palletproject）

### .sh は eol=lf で固定する
.gitattributes が無いと CRLF が混入し、.sh の途中ステップが黙って飛ぶ。→ `*.sh` `*.command` を `eol=lf`。（実例: 2026-05-10 SRT-Blue / 2026-09 DvcMCP）
