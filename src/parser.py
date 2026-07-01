"""把使用者傳來的自然語言訊息解析成一個機票監控設定。

支援的寫法（中英混用皆可），例如：
    從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000
    台北 到 東京 經 香港 來回 2026-07-01 ~ 2026-07-10
    TPE -> KIX 8/15 單程
    台北到大阪 經東京 預算 9000

解析重點：
  * 出發地 / 目的地：「從X到Y」「X到Y」「X->Y」或城市中文名 → IATA 代碼
  * 轉乘點（可選）：「經X」「轉X」「經由X」「中轉X」「via X」
  * 日期：第一個日期 = 去程，第二個 = 回程；沒有第二個視為單程
  * 預算（可選）：「低於N」「預算N」「便宜N」「<N」
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

# 常見城市中文 / 英文名稱 → IATA 代碼。找不到時仍可直接輸入三碼 IATA。
CITY_TO_IATA: dict[str, str] = {
    "台北": "TPE", "臺北": "TPE", "桃園": "TPE", "taipei": "TPE",
    "東京": "TYO", "tokyo": "TYO", "成田": "NRT", "羽田": "HND",
    "大阪": "OSA", "osaka": "OSA", "關西": "KIX", "京都": "KIX",
    "首爾": "SEL", "首尔": "SEL", "seoul": "SEL", "仁川": "ICN",
    "香港": "HKG", "hongkong": "HKG", "hong kong": "HKG",
    "曼谷": "BKK", "bangkok": "BKK",
    "新加坡": "SIN", "singapore": "SIN",
    "上海": "SHA", "shanghai": "SHA", "浦東": "PVG", "浦东": "PVG",
    "北京": "BJS", "beijing": "BJS",
    "高雄": "KHH", "kaohsiung": "KHH",
    "福岡": "FUK", "fukuoka": "FUK",
    "沖繩": "OKA", "沖绳": "OKA", "okinawa": "OKA", "那霸": "OKA",
    "札幌": "CTS", "sapporo": "CTS",
    "名古屋": "NGO", "nagoya": "NGO",
    "倫敦": "LON", "london": "LON",
    "巴黎": "PAR", "paris": "PAR",
    "紐約": "NYC", "newyork": "NYC", "new york": "NYC",
    "洛杉磯": "LAX", "losangeles": "LAX", "los angeles": "LAX",
    "舊金山": "SFO", "sanfrancisco": "SFO", "san francisco": "SFO",
    "雪梨": "SYD", "悉尼": "SYD", "sydney": "SYD",
    "吉隆坡": "KUL", "kualalumpur": "KUL",
    "胡志明": "SGN", "胡志明市": "SGN", "西貢": "SGN",
    "河內": "HAN", "河内": "HAN", "hanoi": "HAN",
    "馬尼拉": "MNL", "manila": "MNL",
    "峇里島": "DPS", "巴里島": "DPS", "bali": "DPS", "denpasar": "DPS",
}


@dataclass
class ParsedWatch:
    origin: str | None = None
    destination: str | None = None
    via: str | None = None          # 多個轉乘點以逗號連接，例如 "HKG,ICN"
    depart_date: str | None = None  # ISO yyyy-mm-dd
    return_date: str | None = None  # ISO yyyy-mm-dd or None = 單程
    threshold: float | None = None
    time_filters: str | None = None  # JSON，例如 {"out_before":"18:00","ret_before":"12:00"}
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class ParseError(ValueError):
    pass


def _resolve_place(token: str) -> str | None:
    """把一個地點詞轉成 IATA 代碼。"""
    token = token.strip()
    if not token:
        return None
    # 已經是三碼 IATA（大寫字母）
    if re.fullmatch(r"[A-Za-z]{3}", token):
        return token.upper()
    key = token.lower()
    if key in CITY_TO_IATA:
        return CITY_TO_IATA[key]
    if token in CITY_TO_IATA:
        return CITY_TO_IATA[token]
    return None


def _parse_one_date(token: str, today: date) -> str | None:
    """把單一日期字串轉成 ISO 格式。年份省略時自動補：若已過則用明年。"""
    token = token.strip()

    # yyyy-mm-dd 或 yyyy/mm/dd
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", token)
    if m:
        y, mo, d = (int(x) for x in m.groups())
        try:
            return date(y, mo, d).isoformat()
        except ValueError:
            return None

    # mm/dd 或 mm-dd 或 m月d日
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})", token)
    if not m:
        m = re.fullmatch(r"(\d{1,2})月(\d{1,2})日?", token)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        try:
            candidate = date(today.year, mo, d)
        except ValueError:
            return None
        if candidate < today:
            try:
                candidate = date(today.year + 1, mo, d)
            except ValueError:
                return None
        return candidate.isoformat()

    return None


def _extract_dates(text: str, today: date) -> list[str]:
    """依出現順序抓出所有日期。"""
    pattern = re.compile(
        r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}"
        r"|\d{1,2}[-/.]\d{1,2}"
        r"|\d{1,2}月\d{1,2}日?"
    )
    out: list[str] = []
    for raw in pattern.findall(text):
        iso = _parse_one_date(raw, today)
        if iso and iso not in out:
            out.append(iso)
    return out


def _extract_threshold(text: str) -> float | None:
    patterns = [
        r"(?:低於|少於|不超過|預算|便宜|budget|under)\s*[:：]?\s*(\d[\d,]*)",
        r"<\s*(\d[\d,]*)",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


_VIA_RE = r"(?:經由|經|轉機?|中轉|via)\s*[:：]?\s*([A-Za-z]{3}|[一-鿿]{2,4})"
# 去程/回程 幾點前/後，例如「去程 18:00 前」「回程 6點以後」
_TIME_RE = re.compile(
    r"(去程|回程)\s*(?:在|於)?\s*(\d{1,2}(?::\d{2})?)\s*點?\s*(以前|之前|前|以後|之後|後)"
)


def _extract_vias(text: str) -> list[str]:
    """抓出所有轉乘點（依出現順序、去重）。"""
    vias: list[str] = []
    for m in re.finditer(_VIA_RE, text):
        v = _resolve_place(m.group(1))
        if v and v not in vias:
            vias.append(v)
    return vias


def _norm_time(raw: str) -> str | None:
    raw = raw.strip()
    if ":" in raw:
        h, mi = raw.split(":")
        h, mi = int(h), int(mi)
    else:
        h, mi = int(raw), 0
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return f"{h:02d}:{mi:02d}"
    return None


def _extract_time_filters(text: str) -> dict:
    """抓出去程/回程的時間限制。回傳如 {"out_before":"18:00","ret_after":"09:00"}。"""
    tf: dict = {}
    for m in _TIME_RE.finditer(text):
        t = _norm_time(m.group(2))
        if not t:
            continue
        leg = "out" if m.group(1) == "去程" else "ret"
        direction = "before" if m.group(3) in ("以前", "之前", "前") else "after"
        tf[f"{leg}_{direction}"] = t
    return tf


def _extract_route(text: str) -> tuple[str | None, str | None]:
    """抓出發地與目的地。"""
    place = r"([A-Za-z]{3}|[一-鿿]{2,4})"

    # 從X到Y / X到Y / X->Y / X→Y
    patterns = [
        rf"從\s*{place}\s*(?:到|去|飛|往|->|→|>)\s*{place}",
        rf"{place}\s*(?:到|去|飛|往|->|→|>)\s*{place}",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            o = _resolve_place(m.group(1))
            d = _resolve_place(m.group(2))
            if o and d:
                return o, d
    return None, None


def parse_message(text: str, today: date | None = None) -> ParsedWatch:
    """解析一整段訊息。回傳的 ParsedWatch.error 不為 None 表示資訊不足。"""
    today = today or date.today()
    if not text or not text.strip():
        return ParsedWatch(error="訊息是空的。")

    # 先把「經X」「去程 18:00 前」等段落抽掉，避免被誤當成目的地或日期
    vias = _extract_vias(text)
    time_filters = _extract_time_filters(text)
    route_text = re.sub(_VIA_RE, " ", text)
    route_text = _TIME_RE.sub(" ", route_text)

    origin, destination = _extract_route(route_text)
    dates = _extract_dates(text, today)
    threshold = _extract_threshold(text)

    via = ",".join(vias) if vias else None
    tf_json = json.dumps(time_filters) if time_filters else None

    is_oneway = bool(re.search(r"單程|oneway|one way", text, re.IGNORECASE))

    depart = dates[0] if dates else None
    ret = None
    if not is_oneway and len(dates) >= 2:
        ret = dates[1]

    missing = []
    if not origin:
        missing.append("出發地")
    if not destination:
        missing.append("目的地")
    if not depart:
        missing.append("出發日期")

    if missing:
        return ParsedWatch(
            origin=origin,
            destination=destination,
            via=via,
            depart_date=depart,
            return_date=ret,
            threshold=threshold,
            time_filters=tf_json,
            error="看不懂這些資訊：" + "、".join(missing)
            + "。範例：『從 TPE 到 NRT 7/1 出發 7/10 回程 低於 12000』",
        )

    return ParsedWatch(
        origin=origin,
        destination=destination,
        via=via,
        depart_date=depart,
        return_date=ret,
        threshold=threshold,
        time_filters=tf_json,
    )
