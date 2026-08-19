"""健康评分与指标解析 — 单一事实来源，供健康评分/趋势/汇总共用。"""
from __future__ import annotations

import re
from typing import Any


def _status(value: float, warn_at: float, danger_at: float) -> str:
    """单项健康状态：healthy（绿）/ warning（黄）/ danger（红）。"""
    if value >= danger_at:
        return "danger"
    if value >= warn_at:
        return "warning"
    return "healthy"


# 评分平滑：最近 N 次采集均值，避免单次抖动（如 CPU spike）导致评分/通知误报
_SCORE_WINDOW = 5
_score_history: dict[str, list[int]] = {}


def smooth_score(server_id: str, score: int | None) -> int | None:
    """记录并返回平滑后评分（最近 N 次均值）。score=None（未采集）时不记录。"""
    if score is None:
        return None
    hist = _score_history.setdefault(server_id, [])
    hist.append(score)
    if len(hist) > _SCORE_WINDOW:
        hist.pop(0)
    return round(sum(hist) / len(hist))


def parse_cpu_pct(cpu_raw: str) -> float | None:
    """从 CPU 检查输出提取使用率百分比。"""
    m = re.search(r"LoadPercentage[= ]*(\d+)", cpu_raw)
    if m:
        return float(m.group(1))
    m2 = re.search(r"(\d+\.?\d*)\s*id", cpu_raw)
    if m2:
        return round(100 - float(m2.group(1)), 1)
    return None


def _memory_score(mem_pct: float) -> float:
    """内存评分（数据库友好）。

    数据库服务器内存占用高是正常现象（buffer pool / cache 本就占满），
    原线性算法 `100 - 使用率*1.5` 会让 60% 内存的库只得 10 分，明显不合理。
    改为分段：<80% 满分；80-90% 开始扣；90-95% 明显扣；>95% 视为接近耗尽。
    """
    if mem_pct < 80:
        return 100.0
    if mem_pct < 90:
        return 100.0 - (mem_pct - 80) * 3.0  # 80%→100, 90%→70
    if mem_pct < 95:
        return 70.0 - (mem_pct - 90) * 8.0  # 90%→70, 95%→30
    return max(0.0, 30.0 - (mem_pct - 95) * 6.0)  # 95%→30, 100%→0


def parse_mem_pct(mem_raw: str) -> float | None:
    """从内存检查输出提取使用率百分比，兼容 Windows 与 Linux 格式。

    Windows: TotalMB=31905 FreeMB=7685 UsedMB=24220
    Linux /proc/meminfo: MemTotal / MemAvailable（用可用内存更贴近真实使用率）
    Linux free -h:       Mem:  7.6G  2.1G ...
    """
    wm = re.search(r"TotalMB=(\d+).*?FreeMB=(\d+).*?UsedMB=(\d+)", mem_raw)
    if wm:
        total_m = int(wm.group(1))
        used_m = int(wm.group(3))
        return round(used_m / total_m * 100, 1) if total_m > 0 else 0.0
    mt = re.search(r"MemTotal:\s*(\d+)", mem_raw)
    ma = re.search(r"MemAvailable:\s*(\d+)", mem_raw)
    if mt and ma:
        total_k, avail_k = int(mt.group(1)), int(ma.group(1))
        if total_k > 0:
            return round((total_k - avail_k) / total_k * 100, 1)
    fm = re.search(r"Mem:\s+([\d.]+)([GMK])i?\s+([\d.]+)([GMK])i?", mem_raw)
    if fm:
        total = float(fm.group(1))
        used = float(fm.group(3))
        if total > 0:
            return round(used / total * 100, 1)
    return None


def parse_session_count(data: dict[str, Any]) -> int | None:
    perf = data.get("db_queries", {}).get("performance", {})
    sessions = perf.get("session_count", {})
    if sessions.get("rows") and sessions["rows"]:
        try:
            return int(sessions["rows"][0][0])
        except (ValueError, IndexError, TypeError):
            return None
    return None


def parse_disk_pct(disk_raw: str) -> float | None:
    """从磁盘检查输出提取最高占用盘使用率，兼容 Windows 与 Linux 格式。

    Windows: C 30.2GB/62.9GB
             D 7.7GB/7.7GB
    Linux df -h: Filesystem Size Used Avail Use% Mounted on
                  /dev/sda1  40G  15G  23G  40% /
    """
    top = parse_disk_top(disk_raw)
    return top[0] if top else None


def parse_disk_top(disk_raw: str) -> tuple[float, str, str] | None:
    """磁盘解析（多盘感知）：返回 (最高使用率, 最高盘标识, 全部盘明细串)。

    - Windows 盘标识为盘符（如 E），明细为 "C 48.0%, D 92.0%"
    - Linux 盘标识为挂载点（如 /），明细为 "/ 73.0%, /boot 40.0%"
    排除光驱(/dev/sr*)与 tmpfs 等伪文件系统；无有效数据返回 None。
    """
    if not disk_raw:
        return None
    win_re = re.compile(r"^([A-Za-z])\s+([\d.]+)GB/([\d.]+)GB$")
    lines = [ln.strip() for ln in disk_raw.strip().splitlines() if ln.strip()]
    rows: list[tuple[str, float]] = []
    if lines and all(win_re.match(ln) for ln in lines):
        for ln in lines:
            m = win_re.match(ln)
            used, total = float(m.group(2)), float(m.group(3))
            if total > 0:
                rows.append((m.group(1), round(used / total * 100, 1)))
    else:
        # Linux df -h：只统计 /dev/ 开头的真实块设备，排除光驱(/dev/sr*)、tmpfs 等
        for ln in lines:
            parts = ln.split()
            if len(parts) < 6:
                continue
            fs, use, mount = parts[0], parts[4], parts[5]
            if not fs.startswith("/dev/") or "/sr" in fs:
                continue
            m = re.match(r"(\d+(?:\.\d+)?)%$", use)
            if m:
                rows.append((mount, float(m.group(1))))
        if not rows:
            # 回退：所有行中的百分比（Use% 列后跟挂载点）
            for m in re.finditer(r"(\d+(?:\.\d+)?)%\s+(\S+)\s*$", disk_raw, re.M):
                rows.append((m.group(2), float(m.group(1))))
    if not rows:
        return None
    label, pct = max(rows, key=lambda r: r[1])
    detail = ", ".join(f"{lbl} {p}%" for lbl, p in rows)
    return pct, label, detail


def parse_slow_sql_count(data: dict[str, Any]) -> int | None:
    """返回慢 SQL 条数；查询报错时返回 None（不参与评分，避免按满分掩盖故障）。"""
    slow = data.get("db_queries", {}).get("performance", {}).get("slow_sql", {})
    if slow.get("error"):
        return None
    return len(slow.get("rows", [])) if slow.get("rows") else 0


def parse_deadlock_count(data: dict[str, Any]) -> int | None:
    """返回死锁数；查询报错时返回 None（不参与评分）。"""
    deadlock = data.get("db_queries", {}).get("performance", {}).get("deadlock_count", {})
    if deadlock.get("error"):
        return None
    if deadlock.get("rows") and deadlock["rows"]:
        try:
            return int(deadlock["rows"][0][0])
        except (ValueError, IndexError, TypeError):
            return 0
    return 0


def extract_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """提取趋势点：CPU/内存/连接数/慢SQL 数。"""
    point: dict[str, Any] = {"ts": data.get("timestamp", "")}
    cpu_raw = data.get("os_info", {}).get("cpu", {}).get("output", "") or ""
    cpu = parse_cpu_pct(cpu_raw)
    if cpu is not None:
        point["cpu_pct"] = cpu
    mem_raw = data.get("os_info", {}).get("memory", {}).get("output", "") or ""
    mem = parse_mem_pct(mem_raw)
    if mem is not None:
        point["mem_pct"] = mem
    sess = parse_session_count(data)
    if sess is not None:
        point["sessions"] = sess
    slow = parse_slow_sql_count(data)
    point["slow_sql_count"] = slow
    return point


def calc_health_score(
    data: dict[str, Any],
    enabled_categories: list[str] | None = None,
    enabled_os_checks: list[str] | None = None,
    skip_db: bool = False,
) -> tuple[int | None, dict[str, Any]]:
    """计算健康评分 0-100，返回 (score, details)。

    传入服务器采集配置（enabled_categories / enabled_os_checks / skip_db）时，
    只对「已勾选的采集项」计权重；未采集项不进入评分（避免虚高）。
    未传配置时保持旧行为（有数据即计入，慢SQL/死锁无条件计入）。
    无任何有效权重（明确配置但什么都不采）→ 返回 score=None（视为“未采集”）。
    """
    details: dict[str, Any] = {}
    total_weight = 0
    weighted_score = 0

    # 离线快照（采集完全失败）：直接返回无分，前端据此显示离线
    if data.get("status") == "offline":
        details["offline"] = {"value": data.get("error") or "离线", "score": 0, "status": "danger"}
        return None, details

    def os_on(key: str) -> bool:
        return enabled_os_checks is None or key in enabled_os_checks

    def perf_on() -> bool:
        if skip_db:
            return False
        if enabled_categories is None:
            return True
        return "performance" in enabled_categories

    # CPU (25) — 需勾选系统采集项 cpu
    if os_on("cpu"):
        cpu_pct = parse_cpu_pct(data.get("os_info", {}).get("cpu", {}).get("output", "") or "")
        if cpu_pct is not None:
            cpu_score = max(0.0, 100 - cpu_pct * 1.2)
            details["cpu"] = {"value": f"{cpu_pct}%", "score": round(cpu_score), "status": _status(cpu_pct, 60, 80)}
            weighted_score += cpu_score * 25
            total_weight += 25

    # Memory (25) — 需勾选系统采集项 memory（分段评分，数据库高内存占用不扣分）
    if os_on("memory"):
        mem_pct = parse_mem_pct(data.get("os_info", {}).get("memory", {}).get("output", "") or "")
        if mem_pct is not None:
            mem_score = _memory_score(mem_pct)
            details["memory"] = {"value": f"{mem_pct}%", "score": round(mem_score), "status": _status(mem_pct, 80, 90)}
            weighted_score += mem_score * 25
            total_weight += 25

    # Disk — 需勾选系统采集项 disk；仅做状态展示（首页资源徽章），不参与评分
    if os_on("disk"):
        disk_top = parse_disk_top(data.get("os_info", {}).get("disk", {}).get("output", "") or "")
        if disk_top is not None:
            disk_pct, disk_label, disk_detail = disk_top
            details["disk"] = {
                "value": f"{disk_pct}%",
                "score": 100,
                "status": _status(disk_pct, 80, 90),
                "label": disk_label,
                "detail": disk_detail,
            }

    # Sessions (20) — 需勾选数据库类别 performance
    if perf_on():
        sess = parse_session_count(data)
        if sess is not None:
            sess_score = max(0.0, 100 - sess * 0.5)
            details["sessions"] = {"value": str(sess), "score": round(sess_score), "status": _status(sess, 20, 60)}
            weighted_score += sess_score * 20
            total_weight += 20

    # Slow SQL (15) — 需勾选 performance（查询报错时不虚增满分）
    if perf_on():
        slow_count = parse_slow_sql_count(data)
        if slow_count is not None:
            slow_score = max(0.0, 100 - slow_count * 10)
            details["slow_sql"] = {"value": f"{slow_count} 条", "score": round(slow_score), "status": _status(slow_count, 1, 6)}
            weighted_score += slow_score * 15
            total_weight += 15

    # Deadlocks (15) — 需勾选 performance（查询报错时不虚增满分）
    if perf_on():
        dl_count = parse_deadlock_count(data)
        if dl_count is not None:
            dl_score = 100.0 if dl_count == 0 else max(0.0, 100 - dl_count * 20)
            details["deadlocks"] = {"value": str(dl_count), "score": round(dl_score), "status": _status(dl_count, 1, 3)}
            weighted_score += dl_score * 15
            total_weight += 15

    if total_weight == 0:
        # 明确传了采集配置但无任何有效权重 → 视为“未采集”，不参与评分
        if enabled_categories is not None or enabled_os_checks is not None:
            return None, details
        return 100, details
    score = round(weighted_score / total_weight)
    return max(0, min(100, score)), details
