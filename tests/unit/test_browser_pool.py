import threading
import time
import json
from pathlib import Path
import pytest
from autoteam.browser_pool import get_pooled_browser, close_thread_browser, close_all_pooled_browsers, _active_instances
from autoteam.codex_auth import _get_codex_session
from autoteam.accounts import delete_account, update_account, load_accounts, add_account
from autoteam.admin_state import load_admin_state, save_admin_state, clear_admin_state, STATE_FILE
from autoteam.api import _PlaywrightExecutor


def test_browser_pool_reuse_and_thread_isolation():
    # Clear any existing instances to have a clean test
    close_all_pooled_browsers()
    assert len(_active_instances) == 0

    # 1. Test same thread reuse
    b1 = get_pooled_browser()
    b2 = get_pooled_browser()
    assert b1 is b2
    assert b1.is_connected()
    assert len(_active_instances) == 1

    # 2. Test thread isolation
    thread_browsers = []
    errors = []

    def thread_worker():
        try:
            tb = get_pooled_browser()
            thread_browsers.append(tb)
            # Ensure it is also reused in the subthread
            tb2 = get_pooled_browser()
            assert tb is tb2
        except Exception as e:
            errors.append(e)
        finally:
            close_thread_browser()

    t = threading.Thread(target=thread_worker)
    t.start()
    t.join()

    assert len(errors) == 0
    assert len(thread_browsers) == 1
    # The subthread browser must be different from main thread browser
    assert thread_browsers[0] is not b1

    # Clean up main thread browser
    close_thread_browser()
    assert len(_active_instances) == 0


def test_http_session_reuse():
    s1 = _get_codex_session()
    s2 = _get_codex_session()
    assert s1 is s2
    # Check that HTTPAdapter for pool concurrency is configured
    adapter = s1.get_adapter("https://")
    assert adapter._pool_connections == 50
    assert adapter._pool_maxsize == 50


def test_granular_database_ops(monkeypatch, tmp_path):
    # Isolated test database path
    test_db_json = tmp_path / "accounts.json"
    monkeypatch.setattr("autoteam.accounts.ACCOUNTS_FILE", test_db_json)
    
    # 1. Test add_account
    add_account("test_opt@withfei.com", "mypassword")
    accounts = load_accounts()
    assert len(accounts) == 1
    assert accounts[0]["email"] == "test_opt@withfei.com"
    assert accounts[0]["password"] == "mypassword"
    assert accounts[0]["status"] == "pending"

    # 2. Test update_account
    update_account("test_opt@withfei.com", status="active", auth_file="dummy.json")
    accounts = load_accounts()
    assert accounts[0]["status"] == "active"
    assert accounts[0]["auth_file"] == "dummy.json"

    # 3. Test delete_account
    delete_account("test_opt@withfei.com")
    accounts = load_accounts()
    assert len(accounts) == 0


def test_admin_state_caching(monkeypatch, tmp_path):
    # Isolated state file path
    test_state_json = tmp_path / "state.json"
    monkeypatch.setattr("autoteam.admin_state.STATE_FILE", test_state_json)
    
    # Initialize
    test_state_json.write_text(json.dumps({"email": "admin@withfei.com", "session_token": "token123"}), encoding="utf-8")
    
    # First load
    s1 = load_admin_state()
    assert s1["email"] == "admin@withfei.com"
    assert s1["session_token"] == "token123"

    # Second load - should hit cache (and mtime is the same)
    s2 = load_admin_state()
    assert s1 is s2

    # Save state -> invalidates cache
    save_admin_state({"email": "admin@withfei.com", "session_token": "token456"})
    s3 = load_admin_state()
    assert s3["session_token"] == "token456"

    # Clear state -> invalidates cache
    clear_admin_state()
    s4 = load_admin_state()
    assert s4.get("session_token") == ""


def test_playwright_executor_concurrency():
    executor = _PlaywrightExecutor()
    try:
        # Run a simple function concurrent test
        results = []
        def task_func(val):
            time.sleep(0.05)
            results.append(val)
            return val * 2

        # Start concurrent submissions
        futures = []
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as test_pool:
            f1 = test_pool.submit(executor.run, task_func, 10)
            f2 = test_pool.submit(executor.run, task_func, 20)
            
            assert f1.result() == 20
            assert f2.result() == 40
            
        assert set(results) == {10, 20}
    finally:
        executor.stop()


def test_create_optimized_context():
    from autoteam.config import create_optimized_context
    close_all_pooled_browsers()
    browser = get_pooled_browser()
    context = create_optimized_context(browser)
    try:
        page = context.new_page()
        ua = page.evaluate("navigator.userAgent")
        assert "Chrome" in ua
        assert "146.0.0.0" not in ua  # 校验老旧硬编码 UA 已被移除
        
        # 校验 stealth 注入脚本成功抹去了 webdriver 自动化特征
        webdriver = page.evaluate("navigator.webdriver")
        assert webdriver is None
    finally:
        context.close()
        close_thread_browser()


def test_thread_local_logging_prefix(caplog):
    import logging
    from autoteam import set_thread_log_prefix, update_thread_log_prefix, get_thread_log_prefix
    
    test_logger = logging.getLogger("autoteam.test_logging_prefix")
    
    caplog.clear()
    with caplog.at_level(logging.INFO):
        # 1. Test base prefix
        set_thread_log_prefix("[Worker-1]")
        assert get_thread_log_prefix() == "[Worker-1]"
        test_logger.info("hello world")
        assert len(caplog.records) == 1
        assert caplog.records[0].message == "[Worker-1] hello world"
        
        # 2. Test update prefix
        update_thread_log_prefix("myemail")
        assert get_thread_log_prefix() == "[Worker-1:myemail]"
        test_logger.info("status ok")
        assert len(caplog.records) == 2
        assert caplog.records[1].message == "[Worker-1:myemail] status ok"
        
        # 3. Message that already contains prefix should not be duplicated
        test_logger.info("[Worker-1:myemail] status ok")
        assert len(caplog.records) == 3
        assert caplog.records[2].message == "[Worker-1:myemail] status ok"

        # 4. Reset prefix
        set_thread_log_prefix("")
        test_logger.info("done")
        assert len(caplog.records) == 4
        assert caplog.records[3].message == "done"

