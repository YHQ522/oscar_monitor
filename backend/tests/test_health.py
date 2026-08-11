"""健康评分与指标解析测试。"""
from __future__ import annotations

from app.services.health import (
    calc_health_score,
    parse_cpu_pct,
    parse_mem_pct,
    parse_session_count,
    parse_slow_sql_count,
)


def test_parse_cpu_linux():
    # idle 87.5% → 使用率 12.5%
    assert parse_cpu_pct("load average: 1.20, 0.80, 0.50; %Cpu(s): 12.5 us, 87.5 id") == 12.5
    assert parse_cpu_pct("LoadPercentage=35") == 35.0


def test_parse_cpu_empty():
    assert parse_cpu_pct("") is None


def test_parse_mem_win():
    assert parse_mem_pct("TotalMB=16000 FreeMB=8000 UsedMB=8000") == 50.0


def test_memory_score_segmented():
    """内存分段评分：数据库高内存占用（<80%）不扣分；接近耗尽才大幅扣分。"""
    from app.services.health import _memory_score

    assert _memory_score(50) == 100.0   # 50% 正常
    assert _memory_score(79) == 100.0   # 79% 仍满分
    assert _memory_score(85) == 85.0    # 80-90 开始扣
    assert _memory_score(90) == 70.0
    assert _memory_score(95) == 30.0    # 95% 明显扣
    assert _memory_score(100) == 0.0    # 耗尽 0 分


def test_parse_session():
    data = {"db_queries": {"performance": {"session_count": {"rows": [["42"]]}}}}
    assert parse_session_count(data) == 42


def test_parse_slow_sql():
    data = {"db_queries": {"performance": {"slow_sql": {"rows": [[1.0, "select"], [2.0, "update"]]}}}}
    assert parse_slow_sql_count(data) == 2


def _sample_data() -> dict:
    return {
        "os_info": {
            "cpu": {"output": "load average: 1.0, 1.0; %Cpu(s): 20.0 us, 80.0 id"},
            "memory": {"output": "TotalMB=1000 FreeMB=400 UsedMB=600"},
        },
        "db_queries": {
            "performance": {
                "session_count": {"rows": [["10"]]},
                "slow_sql": {"rows": [[1.0, "s"], [2.0, "t"]]},
                "deadlock_count": {"rows": [["0"]]},
            }
        },
    }


def test_health_score_range():
    score, details = calc_health_score(_sample_data())
    assert 0 <= score <= 100
    assert {"cpu", "memory", "sessions", "slow_sql", "deadlocks"} <= set(details.keys())


def test_health_score_empty():
    score, details = calc_health_score({})
    assert score == 100


def test_health_score_os_only():
    """仅系统采集（未勾 performance）：慢SQL/死锁不计入，评分只基于系统项。"""
    score, details = calc_health_score(
        _sample_data(),
        enabled_categories=[],
        enabled_os_checks=["cpu", "memory"],
        skip_db=True,
    )
    assert score is not None
    assert "slow_sql" not in details
    assert "deadlocks" not in details
    assert {"cpu", "memory"} <= set(details.keys())


def test_health_score_no_weight():
    """什么都不勾选：无有效权重 → score=None（未采集）。"""
    score, _ = calc_health_score(
        _sample_data(),
        enabled_categories=[],
        enabled_os_checks=[],
        skip_db=True,
    )
    assert score is None


def test_health_score_full():
    """全量勾选 performance：慢SQL/死锁正常计入。"""
    _, details = calc_health_score(
        _sample_data(),
        enabled_categories=["performance"],
        enabled_os_checks=["cpu", "memory"],
    )
    assert "slow_sql" in details
    assert "deadlocks" in details
