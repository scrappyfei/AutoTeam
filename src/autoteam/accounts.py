"""账号池管理 - 持久化存储所有账号状态 (SQLite 备份)"""

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path

from autoteam.admin_state import get_admin_email
from autoteam.mail_provider import build_account_mail_fields, get_mail_provider_name
from autoteam.textio import read_text, write_text

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
ACCOUNTS_FILE = PROJECT_ROOT / "accounts.json"

_accounts_lock = threading.RLock()
_initialized_dbs = set()
_db_init_lock = threading.Lock()

# 账号状态
STATUS_ACTIVE = "active"  # 在 team 中，额度可用
STATUS_EXHAUSTED = "exhausted"  # 在 team 中，额度用完
STATUS_STANDBY = "standby"  # 已移出 team，等待额度恢复
STATUS_PENDING = "pending"  # 已邀请，等待注册完成
STATUS_AUTH_PENDING = "auth_pending"  # 已在 team 中，但 Codex 认证未就绪


def _normalized_email(value):
    return (value or "").strip().lower()


def _is_main_account_email(email):
    return bool(_normalized_email(email)) and _normalized_email(email) == _normalized_email(get_admin_email())


def is_account_disabled(acc: dict | None) -> bool:
    acc = acc or {}
    return bool(acc.get("disabled", False))


def _normalize_account(acc: dict) -> dict:
    normalized = dict(acc or {})
    normalized["disabled"] = bool(normalized.get("disabled", False))
    service_id = normalized.get("mail_service_id")
    normalized["mail_service_id"] = (
        str(service_id).strip() if service_id is not None and str(service_id).strip() else None
    )
    return normalized


def _get_db_path():
    return str(ACCOUNTS_FILE.parent / "accounts.db")


def _get_db():
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path, timeout=30)
    # 启用 WAL 模式实现高并发读写
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(db_path):
    with _accounts_lock:
        conn = sqlite3.connect(db_path, timeout=30)
        try:
            # 检查表是否存在
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
            table_exists = bool(cur.fetchone())

            need_migration = True
            if table_exists:
                # 检查是否包含 'data' 列
                cur = conn.execute("PRAGMA table_info(accounts)")
                columns = {row["name"] for row in cur.fetchall()}
                if "data" in columns:
                    need_migration = False
                else:
                    # 旧 schema，重建它以应用新的 (email, data) 架构
                    conn.execute("DROP TABLE accounts")
                    conn.commit()

            conn.execute("CREATE TABLE IF NOT EXISTS accounts (email TEXT PRIMARY KEY, data TEXT)")
            conn.commit()

            # 如果存在老版本 accounts.json，自动执行数据迁移
            if need_migration and ACCOUNTS_FILE.exists():
                try:
                    text = read_text(ACCOUNTS_FILE).strip()
                    if text:
                        data = json.loads(text)
                        if isinstance(data, list):
                            migrated_count = 0
                            for acc in data:
                                if isinstance(acc, dict) and "email" in acc:
                                    email = _normalized_email(acc["email"])
                                    cur = conn.execute("SELECT 1 FROM accounts WHERE email = ?", (email,))
                                    if not cur.fetchone():
                                        data_str = json.dumps(acc, ensure_ascii=False)
                                        conn.execute("INSERT INTO accounts (email, data) VALUES (?, ?)", (email, data_str))
                                        migrated_count += 1
                            conn.commit()
                            if migrated_count > 0:
                                logger.info("[DB] 成功从 accounts.json 导入 %d 个账号到 SQLite DB", migrated_count)

                    # 备份旧的 accounts.json 为 .json.bak
                    backup_file = ACCOUNTS_FILE.with_suffix(".json.bak")
                    if not backup_file.exists():
                        ACCOUNTS_FILE.rename(backup_file)
                        logger.info("[DB] accounts.json 已重命名备份为 accounts.json.bak")
                except Exception as me:
                    logger.error("[DB] 从 accounts.json 迁移数据到 DB 失败: %s", me)
        finally:
            conn.close()


def _init_db_once():
    db_path = _get_db_path()
    if db_path in _initialized_dbs:
        return
    with _db_init_lock:
        if db_path not in _initialized_dbs:
            _init_db(db_path)
            _initialized_dbs.add(db_path)


def load_accounts():
    """加载账号列表"""
    _init_db_once()
    with _accounts_lock:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT data FROM accounts")
            rows = cur.fetchall()
            accounts = []
            for row in rows:
                try:
                    acc = json.loads(row["data"])
                    accounts.append(_normalize_account(acc))
                except Exception:
                    pass
            return accounts
        finally:
            conn.close()


def save_accounts(accounts):
    """保存账号列表"""
    _init_db_once()
    with _accounts_lock:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT email FROM accounts")
            db_emails = {r["email"] for r in cur.fetchall()}

            input_emails = set()
            for acc in accounts:
                if isinstance(acc, dict) and "email" in acc:
                    email = _normalized_email(acc["email"])
                    input_emails.add(email)

                    normalized_acc = _normalize_account(acc)
                    data_str = json.dumps(normalized_acc, ensure_ascii=False)

                    conn.execute("INSERT OR REPLACE INTO accounts (email, data) VALUES (?, ?)", (email, data_str))

            # 删除 DB 中不存在于 input_emails 里的账号
            for db_email in db_emails:
                if db_email not in input_emails:
                    conn.execute("DELETE FROM accounts WHERE email = ?", (db_email,))

            conn.commit()
        finally:
            conn.close()


def find_account(accounts, email):
    """按邮箱查找账号"""
    for acc in accounts:
        if acc["email"] == email:
            return acc
    return None


def add_account(
    email,
    password,
    cloudmail_account_id=None,
    *,
    mail_provider=None,
    mail_account_id=None,
    mail_service_id=None,
):
    """添加新账号"""
    _init_db_once()
    email = _normalized_email(email)
    with _accounts_lock:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT 1 FROM accounts WHERE email = ?", (email,))
            if cur.fetchone():
                return  # 已存在

            if mail_account_id is None:
                mail_account_id = cloudmail_account_id
            resolved_mail_provider = mail_provider or (get_mail_provider_name() if mail_account_id is not None else "")
            mail_fields = (
                build_account_mail_fields(mail_account_id, provider=resolved_mail_provider, service_id=mail_service_id)
                if mail_account_id is not None
                else {
                    "mail_provider": resolved_mail_provider,
                    "mail_service_id": mail_service_id,
                    "mail_account_id": None,
                    "cloudmail_account_id": cloudmail_account_id,
                }
            )

            acc = {
                "email": email,
                "password": password,
                **mail_fields,
                "status": STATUS_PENDING,
                "auth_file": None,
                "quota_exhausted_at": None,
                "quota_resets_at": None,
                "created_at": time.time(),
                "last_active_at": None,
                "auth_retry_count": 0,
                "auth_last_error": None,
                "auth_last_error_detail": None,
                "auth_last_failed_at": None,
                "auth_retry_after": None,
                "auth_retry_paused": False,
                "disabled": False,
            }

            data_str = json.dumps(acc, ensure_ascii=False)
            conn.execute("INSERT INTO accounts (email, data) VALUES (?, ?)", (email, data_str))
            conn.commit()
        finally:
            conn.close()


def update_account(email, **kwargs):
    """更新账号字段"""
    _init_db_once()
    email = _normalized_email(email)
    with _accounts_lock:
        conn = _get_db()
        try:
            cur = conn.execute("SELECT data FROM accounts WHERE email = ?", (email,))
            row = cur.fetchone()
            if not row:
                return None

            acc = json.loads(row["data"])
            acc.update(kwargs)

            normalized_acc = _normalize_account(acc)
            data_str = json.dumps(normalized_acc, ensure_ascii=False)

            conn.execute("UPDATE accounts SET data = ? WHERE email = ?", (data_str, email))
            conn.commit()
            return normalized_acc
        finally:
            conn.close()


def delete_account(email):
    """物理删除指定邮箱的账号"""
    _init_db_once()
    email = _normalized_email(email)
    with _accounts_lock:
        conn = _get_db()
        try:
            conn.execute("DELETE FROM accounts WHERE email = ?", (email,))
            conn.commit()
        finally:
            conn.close()


def get_active_accounts():
    """获取所有活跃账号"""
    return [
        a
        for a in load_accounts()
        if a["status"] == STATUS_ACTIVE and not _is_main_account_email(a.get("email")) and not is_account_disabled(a)
    ]


def get_standby_accounts():
    """获取所有待命账号（已移出 team，可能额度已恢复）"""
    accounts = load_accounts()
    now = time.time()
    standby = []
    for a in accounts:
        if _is_main_account_email(a.get("email")):
            continue
        if is_account_disabled(a):
            continue
        if a["status"] == STATUS_STANDBY:
            resets_at = a.get("quota_resets_at")
            if resets_at is None:
                a["_quota_recovered"] = True
            else:
                a["_quota_recovered"] = now >= resets_at
            standby.append(a)
    standby.sort(key=lambda x: (not x.get("_quota_recovered", False), x.get("quota_exhausted_at") or 0))
    return standby


def get_next_reusable_account():
    """获取下一个可重用的 standby 账号（优先额度已恢复的）"""
    standby = get_standby_accounts()
    if standby:
        return standby[0]
    return None
