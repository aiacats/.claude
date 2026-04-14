#!/bin/bash
# Notion ナレッジベース読み込みスクリプト
# Usage:
#   notion-knowledge-read.sh list [technology]    # 一覧表示（Technology絞り込み可）
#   notion-knowledge-read.sh read <page_id>       # ページ詳細読み込み
#   notion-knowledge-read.sh search <keyword>     # キーワード検索

set -euo pipefail

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

CONFIG_FILE="$HOME/.claude/.notion-config"
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: Config file not found: $CONFIG_FILE" >&2
  exit 1
fi
source "$CONFIG_FILE"

COMMAND="${1:-list}"

case "$COMMAND" in
  list)
    TECHNOLOGY="${2:-}"

    if [[ -n "$TECHNOLOGY" ]]; then
      FILTER="{\"filter\":{\"property\":\"Technology\",\"select\":{\"equals\":\"$TECHNOLOGY\"}},\"sorts\":[{\"timestamp\":\"created_time\",\"direction\":\"descending\"}]}"
    else
      FILTER="{\"sorts\":[{\"timestamp\":\"created_time\",\"direction\":\"descending\"}]}"
    fi

    curl -s -X POST "https://api.notion.com/v1/databases/$NOTION_KNOWLEDGE_DB_ID/query" \
      -H "Authorization: Bearer $NOTION_API_KEY" \
      -H "Content-Type: application/json" \
      -H "Notion-Version: 2022-06-28" \
      -d "$FILTER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('results', [])
if not results:
    print('知見が見つかりませんでした。')
    sys.exit(0)
for r in results:
    props = r['properties']
    title = ''.join(t['plain_text'] for t in props.get('Title', {}).get('title', []))
    tech_sel = props.get('Technology', {}).get('select')
    tech = tech_sel['name'] if tech_sel else '-'
    page_id = r['id']
    created = r['created_time'][:10]
    print(f'[{created}] [{tech}] {title}')
    print(f'  ID: {page_id}')
    print()
"
    ;;

  read)
    PAGE_ID="${2:?ページIDを指定してください}"

    # ページプロパティ取得
    curl -s "https://api.notion.com/v1/pages/$PAGE_ID" \
      -H "Authorization: Bearer $NOTION_API_KEY" \
      -H "Notion-Version: 2022-06-28" | python3 -c "
import json, sys
data = json.load(sys.stdin)
props = data['properties']
title = ''.join(t['plain_text'] for t in props.get('Title', {}).get('title', []))
tech_sel = props.get('Technology', {}).get('select')
tech = tech_sel['name'] if tech_sel else '-'
print(f'# {title}')
print(f'Technology: {tech}')
print()
"

    # ページコンテンツ取得
    curl -s "https://api.notion.com/v1/blocks/$PAGE_ID/children" \
      -H "Authorization: Bearer $NOTION_API_KEY" \
      -H "Notion-Version: 2022-06-28" | python3 -c "
import json, sys
data = json.load(sys.stdin)
for block in data.get('results', []):
    btype = block['type']
    if btype == 'heading_2':
        text = ''.join(t['plain_text'] for t in block[btype].get('rich_text', []))
        print(f'## {text}')
    elif btype == 'paragraph':
        text = ''.join(t['plain_text'] for t in block[btype].get('rich_text', []))
        print(text)
    elif btype == 'heading_3':
        text = ''.join(t['plain_text'] for t in block[btype].get('rich_text', []))
        print(f'### {text}')
    elif btype == 'bulleted_list_item':
        text = ''.join(t['plain_text'] for t in block[btype].get('rich_text', []))
        print(f'- {text}')
    print()
"
    ;;

  search)
    export NK_KEYWORD="${2:?検索キーワードを指定してください}"

    curl -s -X POST "https://api.notion.com/v1/databases/$NOTION_KNOWLEDGE_DB_ID/query" \
      -H "Authorization: Bearer $NOTION_API_KEY" \
      -H "Content-Type: application/json" \
      -H "Notion-Version: 2022-06-28" \
      -d "{\"sorts\":[{\"timestamp\":\"created_time\",\"direction\":\"descending\"}]}" | python3 -c "
import json, sys, os
keyword = os.environ['NK_KEYWORD'].lower()
data = json.load(sys.stdin)
results = data.get('results', [])
found = False
for r in results:
    props = r['properties']
    title = ''.join(t['plain_text'] for t in props.get('Title', {}).get('title', []))
    tech_sel = props.get('Technology', {}).get('select')
    tech = tech_sel['name'] if tech_sel else '-'
    if keyword in title.lower() or keyword in tech.lower():
        page_id = r['id']
        created = r['created_time'][:10]
        print(f'[{created}] [{tech}] {title}')
        print(f'  ID: {page_id}')
        print()
        found = True
if not found:
    print(f'No results for: {keyword}')
"
    ;;

  *)
    echo "Usage:" >&2
    echo "  $0 list [technology]     一覧表示" >&2
    echo "  $0 read <page_id>        ページ詳細" >&2
    echo "  $0 search <keyword>      キーワード検索" >&2
    exit 1
    ;;
esac
