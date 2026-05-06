"""QR 码登录 + Token 管理 + 账号持久化"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from weixin_bot.api import WeixinAPI
from weixin_bot.client import DEFAULT_BASE_URL, WeixinClient
from weixin_bot.errors import AuthError

logger = logging.getLogger("weixin_bot.auth")

MAX_QR_REFRESH_COUNT = 3


# ── 账号持久化 ────────────────────────────────────────


def _normalize_account_id(account_id: str) -> str:
    """规范化账号 ID 为文件名安全格式"""
    return account_id.strip().lower().replace("@", "-").replace(".", "-")


def _accounts_dir(state_dir: Path) -> Path:
    return state_dir / "accounts"


def _account_file(state_dir: Path, account_id: str) -> Path:
    return _accounts_dir(state_dir) / f"{_normalize_account_id(account_id)}.json"


def save_account(
    state_dir: Path,
    account_id: str,
    token: str,
    base_url: str = "",
    user_id: str = "",
) -> None:
    """保存账号凭证到本地"""
    accounts_dir = _accounts_dir(state_dir)
    accounts_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "token": token,
        "baseUrl": base_url or DEFAULT_BASE_URL,
        "userId": user_id,
        "savedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }

    filepath = _account_file(state_dir, account_id)
    filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # POSIX: 限制文件权限
    if sys.platform != "win32":
        os.chmod(filepath, 0o600)

    # 更新账号索引
    index_file = state_dir / "accounts.json"
    accounts: list[str] = []
    if index_file.exists():
        try:
            accounts = json.loads(index_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            accounts = []
    if account_id not in accounts:
        accounts.append(account_id)
    index_file.write_text(json.dumps(accounts, indent=2), encoding="utf-8")

    logger.info("账号凭证已保存: %s", _normalize_account_id(account_id))


def load_account(state_dir: Path, account_id: str) -> dict[str, str] | None:
    """加载已保存的账号凭证"""
    filepath = _account_file(state_dir, account_id)
    if not filepath.exists():
        return None
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
        if data.get("token"):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("加载账号凭证失败: %s (%s)", filepath, exc)
    return None


def delete_account(state_dir: Path, account_id: str) -> None:
    """删除账号凭证"""
    filepath = _account_file(state_dir, account_id)
    if filepath.exists():
        filepath.unlink()
    # 更新索引
    index_file = state_dir / "accounts.json"
    if index_file.exists():
        try:
            accounts = json.loads(index_file.read_text(encoding="utf-8"))
            accounts = [a for a in accounts if a != account_id]
            index_file.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
        except (json.JSONDecodeError, OSError):
            pass


def list_accounts(state_dir: Path) -> list[str]:
    """列出所有已保存的账号"""
    index_file = state_dir / "accounts.json"
    if not index_file.exists():
        return []
    try:
        return json.loads(index_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


# ── QR 码登录 ────────────────────────────────────────


async def qr_login(
    client: WeixinClient,
) -> dict[str, str]:
    """QR 码扫描登录

    Returns:
        dict with keys: token, accountId, baseUrl, userId
    """
    api = WeixinAPI(client)
    refresh_count = 0

    # 获取 QR 码
    qr_data = await api.get_bot_qrcode()
    qrcode = qr_data.get("qrcode", "")
    if not qrcode:
        raise AuthError("获取二维码失败: 返回数据中无 qrcode 字段")

    _display_qr(qr_data)

    # 当前轮询 base_url（IDC 重定向可能改变）
    poll_base_url: str | None = None

    while True:
        try:
            status_data = await api.get_qrcode_status(qrcode, base_url=poll_base_url)
        except Exception as exc:
            # 网络错误（如 Cloudflare 524）继续轮询
            logger.warning("轮询二维码状态网络错误: %s", exc)
            continue

        status = status_data.get("status", "")

        if status == "confirmed":
            token = status_data.get("bot_token", "")
            account_id = status_data.get("ilink_bot_id", "")
            base_url = status_data.get("baseurl", "") or DEFAULT_BASE_URL
            user_id = status_data.get("ilink_user_id", "")

            if not token:
                raise AuthError("登录确认但未返回 token")

            logger.info("登录成功: account=%s", account_id)
            return {
                "token": token,
                "accountId": account_id,
                "baseUrl": base_url,
                "userId": user_id,
            }

        elif status == "scaned_but_redirect":
            # IDC 重定向
            redirect_host = str(status_data.get("redirect_host", "") or "").strip()
            if redirect_host:
                poll_base_url = f"https://{redirect_host}"
                logger.info("IDC 重定向: %s", poll_base_url)

        elif status == "expired":
            refresh_count += 1
            if refresh_count > MAX_QR_REFRESH_COUNT:
                raise AuthError(f"二维码过期超过 {MAX_QR_REFRESH_COUNT} 次，登录失败")

            logger.info("二维码已过期，正在刷新 (%d/%d)...", refresh_count, MAX_QR_REFRESH_COUNT)
            qr_data = await api.get_bot_qrcode()
            qrcode = qr_data.get("qrcode", "")
            if not qrcode:
                raise AuthError("刷新二维码失败")
            _display_qr(qr_data)
            poll_base_url = None  # 重置 IDC 状态

        elif status in ("wait", "scaned"):
            # 正常等待
            pass

        else:
            logger.debug("未知二维码状态: %s", status)


def _display_qr(qr_data: dict[str, Any]) -> None:
    """在终端显示 QR 码

    关键：QR 码内容必须是 qrcode_img_content (URL)，而非 qrcode (token)。
    - qrcode: 仅用于轮询 get_qrcode_status 的 token
    - qrcode_img_content: 实际需要编码为 QR 码让微信扫描的 URL
    """
    img_url = qr_data.get("qrcode_img_content", "")

    if not img_url:
        print(f"\n⚠ 未获取到二维码链接，请检查网络连接\n")
        return

    # 尝试使用 qrcode 库在终端渲染
    try:
        import qrcode  # type: ignore[import-untyped]

        qr = qrcode.QRCode(border=1)
        qr.add_data(img_url)  # 编码的是 URL，不是 token
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        pass

    # 始终显示链接（终端 QR 码可能渲染不全）
    print(f"\n如二维码显示异常，请在浏览器中打开以下链接扫码：\n{img_url}\n")
    print("请使用微信扫描上方二维码登录\n")


# ── 便捷函数 ────────────────────────────────────────


def is_logged_in(state_dir: Path, account_id: str) -> bool:
    """检查指定账号是否已登录"""
    return load_account(state_dir, account_id) is not None


def logout(state_dir: Path, account_id: str) -> None:
    """登出指定账号"""
    delete_account(state_dir, account_id)
    # 清理 sync buffer
    sync_file = state_dir / "sync" / f"{_normalize_account_id(account_id)}.buf"
    if sync_file.exists():
        sync_file.unlink()
    logger.info("已登出: %s", account_id)
