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


def test_per_user_numbering(tmp_path):
    store = JsonStorage(str(tmp_path / "s.json"))
    a1 = store.add_watch(111, "TPE", "NRT", None, "2026-07-01", None, None, "TWD")
    b1 = store.add_watch(222, "TPE", "KIX", None, "2026-07-01", None, None, "TWD")
    a2 = store.add_watch(111, "TPE", "HKG", None, "2026-07-01", None, None, "TWD")
    # 各自從 1 開始編，不受別人影響
    assert (a1.user_seq, a2.user_seq) == (1, 2)
    assert b1.user_seq == 1
    # 刪掉 #1 後新建是 #3（編號不重複使用），deactivate_seq 只認自己的
    assert store.deactivate_seq(111, 1) is True
    assert store.deactivate_seq(222, 2) is False
    a3 = store.add_watch(111, "TPE", "BKK", None, "2026-07-01", None, None, "TWD")
    assert a3.user_seq == 3
    assert store.find_by_seq(111, 2).id == a2.id


def test_backfill_old_data_without_user_seq(tmp_path):
    # 舊 JSON（沒有 user_seq）載入後要自動補上每人 1..n
    path = str(tmp_path / "old.json")
    import json
    watches = []
    for i, chat in enumerate([7, 7, 9, 7], start=1):
        watches.append({
            "id": i, "chat_id": chat, "origin": "TPE", "destination": "NRT",
            "via": None, "depart_date": "2026-07-01", "return_date": None,
            "threshold": None, "currency": "TWD", "lowest_seen": None,
            "active": 1, "created_at": "x",
        })
    with open(path, "w") as f:
        json.dump({"last_update_id": 0, "next_id": 5, "watches": watches}, f)
    store = JsonStorage(path)
    assert [w.user_seq for w in sorted(store.list_watches(7), key=lambda x: x.id)] \
        == [1, 2, 3]
    assert store.list_watches(9)[0].user_seq == 1
