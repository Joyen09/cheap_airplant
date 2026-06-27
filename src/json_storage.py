"""以單一 JSON 檔保存狀態，方便在 GitHub Actions 之間提交回 repo 永久保留。

提供的 Watch 物件與 storage.Watch 相同，因此 messages.py / monitor.py 可直接重用。
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone

from .storage import Watch


class JsonStorage:
    def __init__(self, path: str):
        self.path = path
        self.last_update_id: int = 0
        self.next_id: int = 1
        self._watches: dict[int, Watch] = {}
        self._load()

    # ── 載入 / 儲存 ───────────────────────────────────────────────────────
    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as f:
            data = json.load(f)
        self.last_update_id = data.get("last_update_id", 0)
        self.next_id = data.get("next_id", 1)
        for w in data.get("watches", []):
            self._watches[w["id"]] = Watch(**w)

    def save(self) -> None:
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        payload = {
            "last_update_id": self.last_update_id,
            "next_id": self.next_id,
            "watches": [asdict(w) for w in self._watches.values()],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── CRUD ─────────────────────────────────────────────────────────────
    def add_watch(self, chat_id, origin, destination, via, depart_date,
                  return_date, threshold, currency) -> Watch:
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

    def update_lowest_seen(self, watch_id: int, price: float) -> None:
        if watch_id in self._watches:
            self._watches[watch_id].lowest_seen = price

    def deactivate(self, watch_id: int, chat_id: int) -> bool:
        w = self._watches.get(watch_id)
        if w and w.chat_id == chat_id and w.active:
            w.active = 0
            return True
        return False
