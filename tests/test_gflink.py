import base64

from src.gflink import _read_varint, augment_tfs

# fast-flights 產的基準 tfs：HKG⇄TPE 9/18-9/20，無任何條件
BASE = "GhoSCjIwMjYtMDktMThqBRIDSEtHcgUSA1RQRRoaEgoyMDI2LTA5LTIwagUSA1RQRXIFEgNIS0dCAQFIAZgBAQ"


def _decode(data):
    """回傳 {(leg_index, field): value} 方便斷言。"""
    result = []
    i = 0
    while i < len(data):
        key, i = _read_varint(data, i)
        field, wtype = key >> 3, key & 7
        if wtype == 0:
            val, i = _read_varint(data, i)
            result.append((field, val))
        elif wtype == 2:
            ln, i = _read_varint(data, i)
            result.append((field, bytes(data[i:i + ln])))
            i += ln
    return result


def _legs(tfs_b64):
    raw = base64.urlsafe_b64decode(tfs_b64 + "=" * (-len(tfs_b64) % 4))
    return [dict_of(v) for f, v in _decode(raw) if f == 3]


def dict_of(chunk):
    d = {}
    for f, v in _decode(chunk):
        d.setdefault(f, []).append(v)
    return d


def test_no_filters_returns_unchanged():
    assert augment_tfs(BASE, None, None) == BASE


def test_time_and_via_encoded_per_leg():
    out = augment_tfs(BASE, {"out_after": "19:00", "ret_after": "15:00"}, ["PEK"])
    legs = _legs(out)
    assert len(legs) == 2
    # 去程：19 後（f8=19），最晚到午夜（f9=23 = cutoff 24:00），轉機 PEK（f15）
    assert legs[0][8] == [19] and legs[0][9] == [23]
    assert legs[0][10] == [0] and legs[0][11] == [23]
    assert legs[0][15] == [b"PEK"]
    # 回程：15 後
    assert legs[1][8] == [15] and legs[1][9] == [23]
    assert legs[1][15] == [b"PEK"]


def test_before_filter_offset_by_one():
    # 「12:00 以前」→ 最晚出發 cutoff=12:00 → f9=11（Google 的 f9 是 cutoff-1）
    out = augment_tfs(BASE, {"out_before": "12:00"}, ["HKG", "ICN"])
    legs = _legs(out)
    assert legs[0][8] == [0] and legs[0][9] == [11]
    assert legs[0][15] == [b"HKG", b"ICN"]
    # 回程沒設時間 → 不加時間欄位，但轉機點照加
    assert 8 not in legs[1]
    assert legs[1][15] == [b"HKG", b"ICN"]


def test_before_18_not_shifted_to_19():
    # 迴歸：選 18:00 前不能編成顯示 19:00 前
    out = augment_tfs(BASE, {"out_before": "18:00"}, [])
    legs = _legs(out)
    assert legs[0][9] == [17]   # cutoff 18:00 → f9=17（+1=18:00）


def test_original_fields_preserved():
    out = augment_tfs(BASE, {"out_after": "09:00"}, [])
    legs = _legs(out)
    assert legs[0][2] == [b"2026-09-18"]
    assert legs[1][2] == [b"2026-09-20"]
