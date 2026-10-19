#!/usr/bin/env python3
"""ArtNet 収録データ(.dmx)の中身を、Unity へ取り込む前に確かめる。

Assets に置くと ScriptedImporter が 148MB を数分かけて展開するので、
その前にここで「壊れていないか」「何分あるか」を見ておく。

使い方:
    python inspect_dmx.py "<path>.dmx"

出す情報:
    パケット数 / 収録時間 / フレームレート / ユニバース番号 / 形式の整合性

形式（DmxRecordDataImporter.cs と対応）:
    [uint32 sequence][double time(ミリ秒)][uint32 numUniverses]
      × numUniverses: [uint32 universe][512 バイトの DMX 値]
    これが末尾まで繰り返す。ヘッダーは無い。
"""

import os
import struct
import sys

# Windows の既定コードページ(cp932)だと日本語が化けるので、出力を UTF-8 に固定する
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

HEADER = 16          # sequence(4) + time(8) + numUniverses(4)
UNIVERSE_BLOCK = 516  # universe(4) + data(512)


def read_packet_header(f, offset):
    f.seek(offset)
    raw = f.read(HEADER)
    if len(raw) < HEADER:
        return None
    return struct.unpack('<IdI', raw)


def inspect(path):
    size = os.path.getsize(path)
    if size < HEADER:
        return f"ファイルが小さすぎます（{size} バイト）"

    lines = []
    with open(path, 'rb') as f:
        first = read_packet_header(f, 0)
        if first is None:
            return "先頭パケットを読めません"
        seq, time_ms, universes = first

        if universes <= 0 or universes > 64:
            # Config.MaxUniverse = 64
            return f"numUniverses が {universes} で、あり得ない値です。形式が違う可能性があります"

        packet = HEADER + universes * UNIVERSE_BLOCK
        count, remainder = divmod(size, packet)

        lines.append(f"ファイル       : {os.path.basename(path)}")
        lines.append(f"サイズ         : {size:,} バイト")
        lines.append(f"1 パケット     : {packet:,} バイト（ユニバース {universes} 系統）")
        lines.append(f"パケット数     : {count:,}")

        if remainder:
            lines.append(f"⚠ 余り {remainder} バイト。ユニバース数が途中で変わるか、ファイルが途切れています")
            lines.append("  → そのまま Unity に入れると ScriptedImporter が例外を出して取り込めません")
        else:
            lines.append("形式の整合性   : OK（余りなし）")

        last = read_packet_header(f, (count - 1) * packet)
        if last is None:
            return "\n".join(lines) + "\n最終パケットを読めません"
        _, last_time_ms, _ = last

        duration = last_time_ms / 1000.0
        lines.append(f"収録時間       : {duration:.2f} 秒（{int(duration) // 60} 分 {int(duration) % 60:02d} 秒）")
        if duration > 0:
            lines.append(f"フレームレート : {count / duration:.2f} fps")

        # ユニバース番号（先頭パケットから）
        f.seek(HEADER)
        numbers = []
        for _ in range(universes):
            numbers.append(struct.unpack('<I', f.read(4))[0])
            f.read(512)
        lines.append(f"ユニバース番号 : {numbers}")

        # 先頭が全部ゼロだと「収録は回っていたが信号が来ていない」ことがある
        f.seek(HEADER + 4)
        if not any(f.read(512)):
            lines.append("⚠ 先頭パケットの 1 系統目が全チャンネル 0 です（暗転から始まっているだけなら正常）")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"見つかりません: {path}")
        return 1
    print(inspect(path))
    return 0


if __name__ == '__main__':
    sys.exit(main())
