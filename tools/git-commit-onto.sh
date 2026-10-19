#!/bin/bash
# 手元のコミット SRC が触ったファイルだけを、別のブランチ BASE（ふつうはリモートの先頭）の上に載せたコミットを作る。
# 作業ツリー・インデックス・手元のブランチは触らない（一時インデックスで組む）。LFS のファイルも blob（ポインタ）ごと写すので実体は読み書きしない。
# 手元のブランチがリモートと別の歴史（道具のコミットを手元にだけ置く等）でも、作業の中身だけを push できる（SinkaiFes2026 で 2026-10-14〜15 に 10 回）。
#
# 使い方（リポジトリの中で）: bash ~/.claude/tools/git-commit-onto.sh <SRC> <BASE>
#   → 最後の行に作ったコミットの SHA。確かめてから git push origin <SHA>:refs/heads/<ブランチ>
#   LFS の実体が origin に無ければ push の前に git lfs push origin <SHA>（--dry-run で数を見られる）。
#
# 安全のため、変更・削除するファイルの BASE 側の中身が SRC の親と同じでなければ止める（BASE 側で別の人が変えていたら CONFLICT）。
# 追加（A）のファイルは BASE に同じパスがあっても上書きする。コミットのメッセージ・作者は SRC のものを使う。
set -e
SRC=$1
BASE=$2
if [ -z "$SRC" ] || [ -z "$BASE" ]; then sed -n 2,13p "$0"; exit 2; fi
git rev-parse --verify -q "$SRC^{commit}" > /dev/null || { echo "no commit $SRC"; exit 2; }
git rev-parse --verify -q "$BASE^{commit}" > /dev/null || { echo "no commit $BASE"; exit 2; }
export GIT_INDEX_FILE=$(mktemp -u)
trap 'rm -f "$GIT_INDEX_FILE"' EXIT
git read-tree "$BASE"
while IFS=$'\t' read -r meta path; do
  status=$(echo "$meta" | awk '{print $5}')
  oldblob=$(echo "$meta" | awk '{print $3}')
  if [ "$status" != "A" ]; then
    onbase=$(git rev-parse "$BASE:$path" 2>/dev/null || echo none)
    old=$(git rev-parse "$SRC^:$path")
    if [ "$onbase" != "$old" ]; then echo "CONFLICT $path (base ${onbase:0:8}, parent of $SRC ${oldblob:0:8})"; exit 1; fi
  fi
  if [ "$status" = "D" ]; then
    git update-index --force-remove "$path"; echo "removed $path"
  else
    mode=$(echo "$meta" | awk '{print $2}')
    git update-index --add --cacheinfo "$mode,$(git rev-parse "$SRC:$path"),$path"; echo "staged $path"
  fi
done < <(git show --format= --raw --no-renames --no-abbrev "$SRC")
tree=$(git write-tree)
new=$(GIT_AUTHOR_NAME="$(git log -1 --format=%an "$SRC")" GIT_AUTHOR_EMAIL="$(git log -1 --format=%ae "$SRC")" \
      GIT_AUTHOR_DATE="$(git log -1 --format=%aI "$SRC")" git commit-tree "$tree" -p "$BASE" -m "$(git log -1 --format=%B "$SRC")")
git diff --stat "$BASE" "$new" | tail -3
echo "$new"
