#!/bin/bash
# Notion ナレッジベース送信スクリプト
# Usage: notion-knowledge.sh <title> <technology> <project> <problem_detail> <solution>

set -euo pipefail

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

CONFIG_FILE="$HOME/.claude/.notion-config"
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Error: Config file not found: $CONFIG_FILE" >&2
  exit 1
fi
source "$CONFIG_FILE"

# 環境変数経由で python3 に渡す（MSYS2/Git Bash での日本語引数文字化け回避）
# JSON生成からHTTPリクエストまで全てPython内で完結させ、
# シェル変数展開による日本語・特殊文字の破損を防止する
export NK_TITLE="$1"
export NK_TECHNOLOGY="$2"
export NK_PROJECT="$3"
export NK_PROBLEM_DETAIL="$4"
export NK_SOLUTION="$5"
export NK_DB_ID="$NOTION_KNOWLEDGE_DB_ID"
export NK_API_KEY="$NOTION_API_KEY"

python3 -c "
import json, os, sys, urllib.request, urllib.error

title = os.environ['NK_TITLE']
technology = os.environ['NK_TECHNOLOGY']
project = os.environ['NK_PROJECT']
problem_detail = os.environ['NK_PROBLEM_DETAIL']
solution = os.environ['NK_SOLUTION']
db_id = os.environ['NK_DB_ID']
api_key = os.environ['NK_API_KEY']

data = {
    'parent': {'database_id': db_id},
    'properties': {
        'Title': {
            'title': [{'text': {'content': title}}]
        },
        'Technology': {
            'multi_select': [{'name': t.strip()} for t in technology.split(',') if t.strip()]
        }
    },
    'children': [
        {
            'object': 'block',
            'type': 'heading_2',
            'heading_2': {'rich_text': [{'text': {'content': 'Project'}}]}
        },
        {
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {'rich_text': [{'text': {'content': project}}]}
        },
        {
            'object': 'block',
            'type': 'heading_2',
            'heading_2': {'rich_text': [{'text': {'content': '\u554f\u984c\u8a73\u7d30'}}]}
        },
        {
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {'rich_text': [{'text': {'content': problem_detail}}]}
        },
        {
            'object': 'block',
            'type': 'heading_2',
            'heading_2': {'rich_text': [{'text': {'content': 'Solution'}}]}
        },
        {
            'object': 'block',
            'type': 'paragraph',
            'paragraph': {'rich_text': [{'text': {'content': solution}}]}
        }
    ]
}

payload = json.dumps(data, ensure_ascii=False).encode('utf-8')

req = urllib.request.Request(
    'https://api.notion.com/v1/pages',
    data=payload,
    headers={
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json; charset=utf-8',
        'Notion-Version': '2022-06-28'
    },
    method='POST'
)

try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode('utf-8'))
        url = body.get('url', '')
        print(f'Notion に送信しました: {url}')
except urllib.error.HTTPError as e:
    error_body = e.read().decode('utf-8')
    print(f'Error (HTTP {e.code}): {error_body}', file=sys.stderr)
    sys.exit(1)
"
