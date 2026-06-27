from src.json_storage import JsonStorage


def test_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    store = JsonStorage(path)
    w = store.add_watch(
        chat_id=555, origin="TPE", destination="NRT", via="HKG",
        depart_date="2026-07-01", return_date=None, threshold=12000, currency="TWD",
    )
    store.last_update_id = 42
    store.last_digest_date = "2026-06-27"
    store.record_observation(w.id, 10000)
    store.record_observation(w.id, 9500)  # 新低
    store.mark_alerted(w.id, 9500)
    store.save()

    reloaded = JsonStorage(path)
    assert reloaded.last_update_id == 42
    assert reloaded.last_digest_date == "2026-06-27"
    assert reloaded.next_id == 2
    watches = reloaded.list_watches(555)
    assert len(watches) == 1
    assert watches[0].origin == "TPE"
    assert watches[0].via == "HKG"
    assert watches[0].lowest_seen == 9500
    assert watches[0].price_count == 2
    assert watches[0].price_sum == 19500
    assert watches[0].last_alert_price == 9500


def test_loads_old_json_without_new_fields(tmp_path):
    # 舊格式（沒有 price_count 等新欄位）也要能載入
    path = str(tmp_path / "old.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            '{"last_update_id": 5, "next_id": 2, "watches": ['
            '{"id": 1, "chat_id": 7, "origin": "TPE", "destination": "NRT",'
            ' "via": null, "depart_date": "2026-07-01", "return_date": null,'
            ' "threshold": 12000, "currency": "TWD", "lowest_seen": 9000,'
            ' "active": 1, "created_at": "2026-06-27T00:00:00+00:00"}]}'
        )
    store = JsonStorage(path)
    w = store.list_watches(7)[0]
    assert w.lowest_seen == 9000
    assert w.price_count == 0          # 用預設值
    assert w.last_alert_price is None


def test_deactivate_scoped_to_chat(tmp_path):
    store = JsonStorage(str(tmp_path / "s.json"))
    w = store.add_watch(555, "TPE", "NRT", None, "2026-07-01", None, None, "TWD")
    # 別人的 chat 不能刪
    assert store.deactivate(w.id, chat_id=999) is False
    assert store.deactivate(w.id, chat_id=555) is True
    assert store.list_watches(555) == []
