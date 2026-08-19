"""告警通知服务 — Webhook / 邮件推送，带去抖与健康分阈值。

触发条件（config.json / OSCAR_* 环境变量配置）：
- notify_enabled = true
- 健康分低于 notify_on_health_below，或本次采集存在错误
- 同一服务器距上次通知超过 notify_min_interval 秒（去抖，默认 300）
"""
from __future__ import annotations

import json
import logging
import smtplib
import threading
import time
import urllib.request
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any

from ..config import Settings, get_settings

logger = logging.getLogger("oscar_monitor.notify")

_WEBHOOK_TIMEOUT = 8
_EMAIL_TIMEOUT = 15


def collect_errors(result: dict[str, Any]) -> list[str]:
    """从采集结果中提取错误信息列表（OS 检查 + 数据库查询 + elog 严重错误）。"""
    errors: list[str] = []
    os_info = result.get("os_info", {}) or {}
    for key, val in os_info.items():
        if isinstance(val, dict) and val.get("error"):
            errors.append(f"{key}: {val['error']}")
    # 数据库错误日志（elog）中的严重错误行（ERROR/FATAL/PANIC）计入告警
    elog = os_info.get("db_log_errors", {}) or {}
    for r in elog.get("rows") or []:
        if len(r) >= 4 and str(r[2]).upper() in ("ERROR", "FATAL", "PANIC"):
            errors.append(f"elog/{r[0]}: {r[1]} {r[3]}")
            if len(errors) >= 10:
                break
    db_queries = result.get("db_queries", {}) or {}
    for cat, queries in db_queries.items():
        for qname, qr in (queries or {}).items():
            if isinstance(qr, dict) and qr.get("error"):
                errors.append(f"{cat}/{qname}: {qr['error']}")
    return errors[:10]


class Notifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._last_sent: dict[str, float] = {}
        self._lock = threading.Lock()

    # ── 触发判定 ──
    def should_notify(self, server: dict[str, Any], score: int | None, has_error: bool) -> bool:
        """判定是否应发送；去抖记账在发送成功后进行（_mark_sent），避免发送失败也消耗去抖。"""
        s = self.settings
        if not s.notify_enabled:
            return False
        # 无有效评分（未采集任何可计权重的指标）：仅在存在采集错误时通知
        if score is None:
            return has_error
        if score >= s.notify_on_health_below and not has_error:
            return False
        sid = server.get("id", "")
        now = time.time()
        with self._lock:
            last = self._last_sent.get(sid, 0)
            if now - last < max(60, s.notify_min_interval):
                return False
        return True

    def _mark_sent(self, server_id: str) -> None:
        with self._lock:
            self._last_sent[server_id] = time.time()

    def check_and_send(self, server: dict[str, Any], result: dict[str, Any], score: int, has_error: bool) -> None:
        """采集完成后调用。满足条件则发送通知；任何异常都不影响主流程。"""
        try:
            if not self.should_notify(server, score, has_error):
                return
            errors = collect_errors(result)
            subject = self._build_subject(server, score, has_error)
            body = self._build_body(server, result, score, errors)
            sent_any = False
            if self.settings.notify_webhook_url:
                if self.send_webhook(self.settings.notify_webhook_url, self._webhook_payload(server, subject, body)):
                    sent_any = True
            if self.settings.notify_email_to:
                if self.send_email(subject, body):
                    sent_any = True
            if sent_any:
                # 发送成功后记录去抖时间点
                self._mark_sent(server.get("id", ""))
            else:
                logger.warning("告警触发但发送失败/未配置渠道: %s", subject)
        except Exception:  # noqa: BLE001
            logger.exception("发送告警通知失败: %s", server.get("name"))

    # ── 消息构建 ──
    def _build_subject(self, server: dict[str, Any], score: int, has_error: bool) -> str:
        name = server.get("name") or server.get("ssh_host", "")
        if has_error:
            return f"[oscar-monitor] {name} 采集异常"
        return f"[oscar-monitor] {name} 健康分过低 ({score})"

    def _build_body(self, server: dict[str, Any], result: dict[str, Any], score: int, errors: list[str]) -> str:
        name = server.get("name") or server.get("ssh_host", "")
        host = server.get("ssh_host", "")
        lines = [
            f"服务器: {name} ({host})",
            f"类型: {server.get('db_type', '')}",
            f"时间: {result.get('timestamp', '')}",
            f"健康分: {score}/100",
        ]
        if errors:
            lines.append("")
            lines.append("错误详情:")
            lines.extend(f"  - {e}" for e in errors)
        return "\n".join(lines)

    def _webhook_payload(self, server: dict[str, Any], subject: str, body: str) -> dict[str, Any]:
        return {
            "title": subject,
            "message": body,
            "server": server.get("name") or server.get("ssh_host", ""),
            "server_id": server.get("id", ""),
            "source": "oscar-monitor",
        }

    # ── 渠道 ──
    def send_webhook(self, url: str, payload: dict[str, Any]) -> bool:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_WEBHOOK_TIMEOUT) as resp:
                return 200 <= resp.status < 300
        except Exception as e:  # noqa: BLE001
            logger.warning("Webhook 发送失败: %s", e)
            return False

    def send_email(self, subject: str, body: str) -> bool:
        s = self.settings
        if not (s.notify_email_smtp_host and s.notify_email_to):
            return False
        from_addr = s.notify_email_from or s.notify_email_smtp_user or "oscar-monitor"
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = formataddr((str(Header("oscar-monitor", "utf-8")), from_addr))
        msg["To"] = s.notify_email_to
        try:
            if s.notify_email_smtp_port == 465:
                server = smtplib.SMTP_SSL(s.notify_email_smtp_host, s.notify_email_smtp_port, timeout=_EMAIL_TIMEOUT)
            else:
                server = smtplib.SMTP(s.notify_email_smtp_host, s.notify_email_smtp_port, timeout=_EMAIL_TIMEOUT)
                server.starttls()
            if s.notify_email_smtp_user:
                server.login(s.notify_email_smtp_user, s.notify_email_smtp_pass)
            server.sendmail(
                from_addr,
                [t.strip() for t in s.notify_email_to.split(",") if t.strip()],
                msg.as_string(),
            )
            server.quit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("邮件发送失败: %s", e)
            return False

    def send_test(self) -> dict[str, Any]:
        """发送测试通知，返回各渠道结果（供配置页测试按钮使用）。"""
        result: dict[str, Any] = {}
        if self.settings.notify_webhook_url:
            ok = self.send_webhook(
                self.settings.notify_webhook_url,
                {"title": "[oscar-monitor] 测试通知", "message": "这是一条来自 oscar-monitor 的测试通知。", "source": "oscar-monitor"},
            )
            result["webhook"] = {"ok": ok, "msg": "发送成功" if ok else "发送失败"}
        if self.settings.notify_email_to:
            ok = self.send_email("[oscar-monitor] 测试通知", "这是一条来自 oscar-monitor 的测试通知。")
            result["email"] = {"ok": ok, "msg": "发送成功" if ok else "发送失败"}
        if not result:
            result["msg"] = "未配置任何通知渠道"
        return result


_notifier: Notifier | None = None


def get_notifier(settings: Settings | None = None) -> Notifier:
    """返回全局通知器单例。settings 仅首次初始化时使用；
    配置变更请调用 reinit_notifier 显式重建（避免每次采集重建导致去抖失效）。"""
    global _notifier
    if _notifier is None:
        _notifier = Notifier(settings or get_settings())
    return _notifier


def reinit_notifier(settings: Settings | None = None) -> Notifier:
    """配置变更后重建通知器（去抖状态随重建重置，属预期）。"""
    global _notifier
    _notifier = Notifier(settings or get_settings())
    return _notifier
