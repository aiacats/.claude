#!/bin/bash
# カメラごとに rail を細かく撮り足す（ズームは記録どおり 1 だけ）。
# usage: bash run_fine.sh <key> <TL_TO_MOV> "<cam>:<rails csv>" ...
S=C:/Users/komao/AppData/Local/Temp/claude/D---ProjectBLUE-Project-SinkaiFes2026/153ade3b-0249-4f15-b901-3b9892330e3d/scratchpad
PY=C:/Users/komao/AppData/Local/Temp/claude/D---ProjectBLUE-Project-SinkaiFes2026/d7b82881-ba84-4f57-b27f-f91cc68130d3/scratchpad/segenv/Scripts/python.exe
key=$1; tl=$2; export DIRECTOR=$3; shift 3
cd $S/work || exit 1
for spec in "$@"; do
  cam=${spec%%:*}; rails=${spec#*:}
  echo "== cam $cam rails $rails"
  KEY=$key TL_TO_MOV=$tl UNITY_HWND=${UNITY_HWND:-132542} POOL_LIMIT_MB=2100 RAILS=$rails ZOOMS=1.0 NOFINE=1 \
    $PY -u ../match_rail.py "$(cat sw_url_$key.txt)" shots_${key}_pick.json match_${key}_fine_$cam.json $cam || exit 1
done
echo ALLDONE
