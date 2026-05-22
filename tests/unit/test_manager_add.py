import pytest
from autoteam import manager

class _FakeChatGPT:
    def __init__(self):
        self.browser = True
        self.started = 0
        self.stopped = 0

    def start(self):
        self.browser = True
        self.started += 1

    def stop(self):
        self.browser = False
        self.stopped += 1


class _FakeMailClient:
    def login(self):
        return None


def test_cmd_add_single_no_active_accounts(monkeypatch):
    chatgpt = _FakeChatGPT()
    events = []
    
    # 模拟没有 active 账号
    state = {
        "accounts": [
            {"email": "standby@example.com", "status": "standby"}
        ]
    }

    def fake_load_accounts():
        return [dict(a) for a in state["accounts"]]

    def fake_create(_chatgpt, _mail):
        events.append(("create", None))
        state["accounts"].append({"email": "new@example.com", "status": "active"})
        return "new@example.com"

    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", fake_load_accounts)
    monkeypatch.setattr(manager, "create_new_account", fake_create)
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))
    monkeypatch.setattr(manager, "get_admin_email", lambda: "admin@example.com")

    manager.cmd_add(count=1)

    assert events == [
        ("create", None),
        ("sync_to_cpa", None)
    ]
    # 无 active 账号，不会触发 remove_from_team 移出
    assert len(state["accounts"]) == 2
    assert state["accounts"][-1]["email"] == "new@example.com"


def test_cmd_add_multi_with_eviction(monkeypatch):
    chatgpt = _FakeChatGPT()
    events = []
    
    # 模拟活跃账号，其中 acc2_lowest 剩余额度最少（primary_pct=90 即剩 10，而 acc1 剩 50，acc3 剩 100）
    state = {
        "accounts": [
            {"email": "admin@example.com", "status": "active"}, # 管理员大号，不参与踢人
            {"email": "acc1@example.com", "status": "active", "last_quota": {"primary_pct": 50}}, # 剩 50
            {"email": "acc2_lowest@example.com", "status": "active", "last_quota": {"primary_pct": 90}}, # 剩 10 (最低)
            {"email": "acc3@example.com", "status": "active", "last_quota": {"primary_pct": 0}}, # 剩 100
        ]
    }

    def fake_load_accounts():
        return [dict(a) for a in state["accounts"]]

    def fake_update_account(email, **kwargs):
        events.append(("update", email, kwargs))
        for a in state["accounts"]:
            if a["email"] == email:
                a.update(kwargs)
                break

    def fake_remove(_chatgpt, email, *, return_status=False):
        events.append(("remove", email))
        return "removed" if return_status else True

    # 循环创建新账号的模拟
    created_idx = 0
    def fake_create(_chatgpt, _mail):
        nonlocal created_idx
        created_idx += 1
        new_email = f"new_{created_idx}@example.com"
        events.append(("create", new_email))
        state["accounts"].append({"email": new_email, "status": "active"})
        return new_email

    monkeypatch.setattr(manager, "ChatGPTTeamAPI", lambda: chatgpt)
    monkeypatch.setattr(manager, "CloudMailClient", lambda: _FakeMailClient())
    monkeypatch.setattr(manager, "load_accounts", fake_load_accounts)
    monkeypatch.setattr(manager, "update_account", fake_update_account)
    monkeypatch.setattr(manager, "remove_from_team", fake_remove)
    monkeypatch.setattr(manager, "create_new_account", fake_create)
    monkeypatch.setattr(manager, "sync_to_cpa", lambda: events.append(("sync_to_cpa", None)))
    monkeypatch.setattr(manager, "get_admin_email", lambda: "admin@example.com")

    # 执行添加 2 个账号循环
    manager.cmd_add(count=2)

    # 验证流程：
    # 轮次 1: 找出额度最低的 acc2_lowest，踢掉，状态改为 standby，创建 new_1
    # 轮次 2: 此时活跃的只有 acc1(剩 50) 和 acc3(剩 100) 和 new_1(没有 last_quota 视为剩 100)。所以踢掉剩 50 的 acc1，状态改为 standby，创建 new_2
    assert events == [
        ("remove", "acc2_lowest@example.com"),
        ("update", "acc2_lowest@example.com", {"status": "standby"}),
        ("remove", "acc1@example.com"),
        ("update", "acc1@example.com", {"status": "standby"}),
        ("create", "new_1@example.com"),
        ("create", "new_2@example.com"),
        ("sync_to_cpa", None)
    ]
