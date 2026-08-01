from hiris.app.proxy.dashboard_backups import (
    save_backup, latest_backup, MAX_BACKUPS_PER_DASHBOARD,
)


def test_latest_backup_is_none_when_nothing_saved(tmp_path):
    assert latest_backup(str(tmp_path), "casa-mia") is None


def test_save_then_latest_roundtrip(tmp_path):
    cfg = {"views": [{"title": "Home"}]}
    save_backup(str(tmp_path), "casa-mia", cfg)
    assert latest_backup(str(tmp_path), "casa-mia") == cfg


def test_latest_returns_most_recent(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "B"}]}


def test_keeps_at_most_three_per_dashboard(tmp_path):
    import json, os
    for i in range(5):
        save_backup(str(tmp_path), "casa-mia", {"views": [{"title": str(i)}]})
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    assert len(data["casa-mia"]) == MAX_BACKUPS_PER_DASHBOARD
    # i piu' vecchi vengono scartati: resta la coda 2,3,4
    assert [b["config"]["views"][0]["title"] for b in data["casa-mia"]] == ["2", "3", "4"]


def test_dashboards_are_isolated(tmp_path):
    save_backup(str(tmp_path), "casa-mia", {"views": [{"title": "A"}]})
    save_backup(str(tmp_path), "altra-casa", {"views": [{"title": "B"}]})
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": [{"title": "A"}]}
    assert latest_backup(str(tmp_path), "altra-casa") == {"views": [{"title": "B"}]}


def test_corrupt_file_does_not_raise(tmp_path):
    import os
    with open(os.path.join(str(tmp_path), "dashboard_backups.json"), "w", encoding="utf-8") as fh:
        fh.write("{not json")
    assert latest_backup(str(tmp_path), "casa-mia") is None
    save_backup(str(tmp_path), "casa-mia", {"views": []})   # non deve sollevare
    assert latest_backup(str(tmp_path), "casa-mia") == {"views": []}
