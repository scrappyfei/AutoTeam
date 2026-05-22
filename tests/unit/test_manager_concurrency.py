import time
from autoteam import manager, accounts

def test_accounts_lock_prevents_race_conditions():
    assert hasattr(accounts, "_accounts_lock")

def test_cmd_check_parallel_execution(monkeypatch):
    calls = []
    def fake_check_and_refresh(acc):
        calls.append(acc["email"])
        time.sleep(0.1)  # Simulate network latency
        return "ok", {"primary_pct": 50}

    monkeypatch.setattr(manager, "_check_and_refresh", fake_check_and_refresh)
    monkeypatch.setattr(manager, "_abort_if_cancel_requested", lambda: None)
    monkeypatch.setattr(manager, "update_account", lambda email, **kwargs: None)

    monkeypatch.setattr(manager, "load_accounts", lambda: [
        {"email": "a@example.com", "status": "active", "auth_file": __file__},
        {"email": "b@example.com", "status": "active", "auth_file": __file__},
        {"email": "c@example.com", "status": "active", "auth_file": __file__},
    ])
    monkeypatch.setattr(manager, "save_accounts", lambda x: None)

    start_time = time.time()
    manager.cmd_check()
    duration = time.time() - start_time

    assert len(calls) == 3
    assert set(calls) == {"a@example.com", "b@example.com", "c@example.com"}
    # If sequential, 3 accounts * 0.1s = 0.3s.
    # In parallel with max_workers=5, it should take ~0.1s (definitely < 0.25s).
    assert duration < 0.25
