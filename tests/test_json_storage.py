from src.json_storage import JsonStorage


def test_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    store = JsonStorage(path)
    w = store.add_watch(
        chat_id=555, origin="TPE", destination="NRT", via="HKG",
        depart_date="2026-07-01", return_date=None, threshold=12000, currency="TWD",
    )
    store.last_update_id = 42
    store.update_lowest_seen(w.id, 9500)
    store.save()

    reloaded = JsonStorage(path)
    assert reloaded.last_update_id == 42
    assert reloaded.next_id == 2
    watches = reloaded.list_watches(555)
    assert len(watches) == 1
    assert watches[0].origin == "TPE"
    assert watches[0].via == "HKG"
    assert watches[0].lowest_seen == 9500


def test_deactivate_scoped_to_chat(tmp_path):
    store = JsonStorage(str(tmp_path / "s.json"))
    w = store.add_watch(555, "TPE", "NRT", None, "2026-07-01", None, None, "TWD")
    # 別人的 chat 不能刪
    assert store.deactivate(w.id, chat_id=999) is False
    assert store.deactivate(w.id, chat_id=555) is True
    assert store.list_watches(555) == []
