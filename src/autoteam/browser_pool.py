"""Thread-local browser pool for Playwright to avoid launch overhead in concurrent environments."""

import logging
import threading
from playwright.sync_api import sync_playwright
from autoteam.config import get_playwright_launch_options

logger = logging.getLogger(__name__)

_thread_local = threading.local()
_active_instances = []
_instances_lock = threading.Lock()


class PooledBrowserInstance:
    def __init__(self, playwright, browser):
        self.playwright = playwright
        self.browser = browser


def get_pooled_browser():
    """获取当前线程绑定的 Playwright 浏览器实例，如果不存在或已关闭则重新初始化。"""
    instance = getattr(_thread_local, "instance", None)
    if instance:
        try:
            if instance.browser.is_connected():
                return instance.browser
        except Exception:
            pass
        logger.info("[BrowserPool] 检测到当前线程的浏览器实例已断开，准备重新初始化")
        close_thread_browser()

    logger.info("[BrowserPool] 正在初始化当前线程 %s 的 Playwright 浏览器实例...", threading.get_ident())
    p = sync_playwright().start()
    try:
        browser = p.chromium.launch(**get_playwright_launch_options())
        instance = PooledBrowserInstance(p, browser)
        _thread_local.instance = instance
        with _instances_lock:
            _active_instances.append(instance)
        return browser
    except Exception:
        try:
            p.stop()
        except Exception:
            pass
        raise


def close_thread_browser():
    """关闭当前线程绑定的浏览器。"""
    instance = getattr(_thread_local, "instance", None)
    if instance:
        logger.info("[BrowserPool] 关闭当前线程 %s 的浏览器实例", threading.get_ident())
        try:
            instance.browser.close()
        except Exception:
            pass
        try:
            instance.playwright.stop()
        except Exception:
            pass
        with _instances_lock:
            if instance in _active_instances:
                _active_instances.remove(instance)
        delattr(_thread_local, "instance")


def close_all_pooled_browsers():
    """关闭所有线程池中的浏览器实例（用于程序关闭或重置时）。"""
    with _instances_lock:
        if not _active_instances:
            return
        logger.info("[BrowserPool] 正在清理所有线程绑定的浏览器实例 (数量: %d)...", len(_active_instances))
        for instance in list(_active_instances):
            try:
                instance.browser.close()
            except Exception:
                pass
            try:
                instance.playwright.stop()
            except Exception:
                pass
        _active_instances.clear()
