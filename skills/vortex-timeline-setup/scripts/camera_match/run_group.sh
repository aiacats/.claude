#!/bin/bash
# 1 組分の粗い照合（rail -0.5〜0.5 を 0.1 刻み × ズーム 7 段、ショットごとに近傍を細かく）。
# レールを持たないカメラ（1・6・7・8）と、記録の位置から何も写らない 13・14 は外す。
# usage: bash run_group.sh <key> <TL_TO_MOV>
S=C:/Users/komao/AppData/Local/Temp/claude/D---ProjectBLUE-Project-SinkaiFes2026/153ade3b-0249-4f15-b901-3b9892330e3d/scratchpad
PY=C:/Users/komao/AppData/Local/Temp/claude/D---ProjectBLUE-Project-SinkaiFes2026/d7b82881-ba84-4f57-b27f-f91cc68130d3/scratchpad/segenv/Scripts/python.exe
key=$1; tl=$2
cd $S/work || exit 1
python ../pick_test.py $key 0,2,3,4,5,9,10,11,12,15 6 shots_${key}_rail.json || exit 1
KEY=$key DIRECTOR=$3 TL_TO_MOV=$tl UNITY_HWND=${UNITY_HWND:-132542} POOL_LIMIT_MB=2100 \
  $PY -u ../match_rail.py "$(cat sw_url_$key.txt)" shots_${key}_rail.json match_$key.json
echo ALLDONE $?
