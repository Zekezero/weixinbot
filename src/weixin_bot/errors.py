"""weixin_bot 异常层级"""

from __future__ import annotations


class WeixinError(Exception):
    """weixin_bot 基础异常"""


class AuthError(WeixinError):
    """认证相关错误（QR 登录失败、Token 无效等）"""


class ApiError(WeixinError):
    """微信 ilink API 调用错误"""

    def __init__(self, message: str, ret: int = 0, errcode: int = 0, errmsg: str = "") -> None:
        self.ret = ret
        self.errcode = errcode
        self.errmsg = errmsg
        super().__init__(message)


class SessionExpiredError(ApiError):
    """会话过期（errcode=-14），需要重新登录"""


class CdnError(WeixinError):
    """CDN 上传/下载错误"""


class MediaError(WeixinError):
    """媒体处理错误（转码失败、MIME 检测等）"""
