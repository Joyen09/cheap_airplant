"""以單一 JSON 檔保存狀態，方便在 GitHub Actions 之間提交回 repo 永久保留。

提供的 Watch 物件與 storage.Watch 相同，因此 messages.py / monitor.py 可直接重用。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, fields
from datetime import datetime, timedelta, timezone

from .storage import BASELINE_WINDOW_DAYS, Watch


class JsonStorage:
    def __init__(self, path: str):
        self.path = path
        self.last_update_id: int = 0
        self.next_id: int = 1
        self.last_digest_date: str = ""  # 上次發送每日摘要的日期（台北時區 yyyy-mm-dd）
        self._watches: dict[int, Watch] = {}
        self._history: dict[int, list] = {}  # {watch_id: [[ts, price], ...]}
        self._load()

    # ── 載入 / 儲存 ───────────────────────────────────────────────────────
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.last_update_id = data.get("last_update_id", 0)
        self.next_id = data.get("next_id", 1)
        self.last_digest_date = data.get("last_digest_date", "")
        valid = {f.name for f in fields(Watch)}
        for w in data.get("watches", []):
            self._watches[w["id"]] = Watch(**{k: v for k, v in w.items() if k in valid})
        self._history = {int(k): v for k, v in data.get("history", {}).items()}
        # 舊資料補上每人獨立的編號（依建立順序）
        counters: dict[int, int] = {}
        for w in sorted(self._watches.values(), key=lambda x: x.id):
            if w.user_seq:
                counters[w.chat_id] = max(counters.get(w.chat_id, 0), w.user_seq)
        for w in sorted(self._watches.values(), key=lambda x: x.id):
            if not w.user_seq:
                counters[w.chat_id] = counters.get(w.chat_id, 0) + 1
                w.user_seq = counters[w.chat_id]

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "last_update_id": self.last_update_id,
            "next_id": self.next_id,
            "last_digest_date": self.last_digest_date,
            "watches": [asdict(w) for w in self._watches.values()],
            "history": {str(k): v for k, v in self._history.items()},
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── CRUD ─────────────────────────────────────────────────────────────
    def add_watch(self, chat_id, origin, destination, via, depart_date,
                  return_date, threshold, currency, time_filters=None) -> Watch:
        seq = max((w.user_seq for w in self._watches.values()
                   if w.chat_id == chat_id), default=0) + 1
        watch = Watch(
            id=self.next_id,
            chat_id=chat_id,
            origin=origin,
            destination=destination,
            via=via,
            depart_date=depart_date,
            return_date=return_date,
            threshold=threshold,
            currency=currency,
            lowest_seen=None,
            active=1,
            created_at=datetime.now(timezone.utc).isoformat(),
            time_filters=time_filters,
            user_seq=seq,
        )
        self._watches[watch.id] = watch
        self.next_id += 1
        return watch

    def list_watches(self, chat_id: int, active_only: bool = True) -> list[Watch]:
        return [
            w for w in self._watches.values()
            if w.chat_id == chat_id and (not active_only or w.active)
        ]

    def all_active_watches(self) -> list[Watch]:
        return [w for w in self._watches.values() if w.active]

    def record_observation(self, watch_id: int, price: float) -> None:
        w = self._watches.get(watch_id)
        if not w:
            return
        if w.lowest_seen is None or price < w.lowest_seen:
            w.lowest_seen = price
        w.price_count += 1
        w.price_sum += price
        now = datetime.now(timezone.utc)
        hist = self._history.setdefault(watch_id, [])
        hist.append([now.isoformat(), price])
        del hist[:-1000]  # 最多保留最近 1000 筆，控制檔案大小
        # 常態價 = 滾動視窗內觀測的平均。ts 皆同格式 isoformat，字典序即時間序。
        # （高頻查價時視窗實際上限也受上面 1000 筆的保留數約束）
        cutoff = (now - timedelta(days=BASELINE_WINDOW_DAYS)).isoformat()
        recent = [p for ts, p in hist if ts >= cutoff]
        w.baseline = sum(recent) / len(recent) if recent else None

    def get_history(self, watch_id: int, limit: int = 500) -> list[tuple[str, float]]:
        hist = self._history.get(watch_id, [])[-limit:]
        return [(ts, price) for ts, price in hist]

    def mark_alerted(self, watch_id: int, price: float) -> None:
        w = self._watches.get(watch_id)
        if w:
            w.last_alert_price = price

    def deactivate(self, watch_id: int, chat_id: int) -> bool:
        w = self._watches.get(watch_id)
        if w and w.chat_id == chat_id and w.active:
            w.active = 0
            return True
        return False

    def find_by_seq(self, chat_id: int, seq: int):
        for w in self._watches.values():
            if w.chat_id == chat_id and w.user_seq == seq and w.active:
                return w
        return None

    def deactivate_seq(self, chat_id: int, seq: int) -> bool:
        w = self.find_by_seq(chat_id, seq)
        return self.deactivate(w.id, chat_id) if w else False
