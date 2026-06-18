from extract_events import normalize_event, deduplicate_events


def test_normalize_event_self_assessed_eps():
    obj = {
        "stock_id": "1101",
        "company_name": "台泥",
        "market": "上市",
        "industry": "水泥工業",
        "announcement_date": "2026-06-16",
        "fact_date": "2026-06-16",
        "title": "自結 EPS 公告",
        "content": "公司自結EPS 1.25元，稅後純益 1000000 元。",
        "source": "mops_api_t05st01",
    }
    event = normalize_event(obj)
    assert event is not None
    assert event.event_type == "self_assessed_eps"
    assert event.signal_strength == "A"
    assert event.eps_value == 1.25


def test_deduplicate_keeps_better_row():
    base = {
        "stock_id": "1101",
        "company_name": "台泥",
        "market": "上市",
        "industry": "水泥工業",
        "announcement_date": "2026-06-16",
        "fact_date": "2026-06-16",
        "title": "自結 EPS 公告",
        "content": "公司自結EPS 1.25元。",
        "source": "mops_api_t05st01",
    }
    e1 = normalize_event(base)
    e2 = normalize_event({**base, "content": "公司自結EPS 1.25元，稅後純益 1000000 元。"})
    events = deduplicate_events([e1, e2])
    assert len(events) == 1
    assert events[0].content.endswith("稅後純益 1000000 元。")
