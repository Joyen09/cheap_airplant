"""把時間限制與轉機點編進 Google Flights 的 tfs 連結。

fast-flights 產生的 tfs protobuf 只含航線/日期等基本欄位。實測反解
Google Flights 頁面產生的 tfs 後，確認每段航程（top-level field 3）還支援：
    f8  = 最早出發小時 (0-23)
    f9  = 最晚出發小時 (0-23)
    f10 = 最早抵達小時 (0-23)
    f11 = 最晚抵達小時 (0-23)
    f15 = 指定轉機機場代碼（repeated string）
本模組在 fast-flights 的輸出位元組上補進這些欄位，讓通知連結
「一開就已套好時間與轉機條件」。
"""
from __future__ import annotations

import base64


def _read_varint(data: bytes, i: int) -> tuple[int, int]:
    val = 0
    shift = 0
    while True:
        b = data[i]
        i += 1
        val |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            return val, i


def _write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        bits = value & 0x7F
        value >>= 7
        if value:
            out.append(bits | 0x80)
        else:
            out.append(bits)
            return bytes(out)


def _field_varint(field: int, value: int) -> bytes:
    return _write_varint((field << 3) | 0) + _write_varint(value)


def _field_bytes(field: int, payload: bytes) -> bytes:
    return _write_varint((field << 3) | 2) + _write_varint(len(payload)) + payload


def _hour(hhmm: str | None, default: int) -> int:
    if not hhmm:
        return default
    try:
        return max(0, min(23, int(hhmm.split(":")[0])))
    except (ValueError, AttributeError):
        return default


def _leg_extras(after: str | None, before: str | None, vias: list[str]) -> bytes:
    """組出要補進單一航段的欄位位元組。"""
    extra = b""
    if after or before:
        extra += _field_varint(8, _hour(after, 0))    # 最早出發
        extra += _field_varint(9, _hour(before, 23))  # 最晚出發
        extra += _field_varint(10, 0)                 # 抵達不設限
        extra += _field_varint(11, 23)
    for v in vias:
        extra += _field_bytes(15, v.encode())
    return extra


def augment_tfs(
    tfs_b64: str,
    time_filters: dict | None = None,
    vias: list[str] | None = None,
) -> str:
    """在 base64 的 tfs 上，於每段航程補進時間限制與轉機點後回傳新 base64。"""
    tf = time_filters or {}
    vias = vias or []
    if not tf and not vias:
        return tfs_b64

    pad = tfs_b64 + "=" * (-len(tfs_b64) % 4)
    raw = base64.urlsafe_b64decode(pad)

    # 每段航程的補充欄位：第一段用去程(out)條件、第二段用回程(ret)條件
    leg_extras = [
        _leg_extras(tf.get("out_after"), tf.get("out_before"), vias),
        _leg_extras(tf.get("ret_after"), tf.get("ret_before"), vias),
    ]

    out = bytearray()
    i = 0
    leg_index = 0
    while i < len(raw):
        start = i
        key, i = _read_varint(raw, i)
        field, wtype = key >> 3, key & 7
        if wtype == 0:
            _, i = _read_varint(raw, i)
            out += raw[start:i]
        elif wtype == 2:
            ln, j = _read_varint(raw, i)
            chunk = raw[j:j + ln]
            i = j + ln
            if field == 3:  # 一段航程 → 補欄位
                extra = leg_extras[min(leg_index, 1)]
                leg_index += 1
                new_chunk = chunk + extra
                out += _field_bytes(3, new_chunk)
            else:
                out += raw[start:i]
        else:  # 其他 wire type 原樣保留（不預期出現）
            out += raw[start:]
            break

    return base64.urlsafe_b64encode(bytes(out)).decode().rstrip("=")
