"""Drop-time waiting utilities.

Accuracy note (read this): the wait loop trusts your SYSTEM CLOCK.
A clock that is 3 seconds slow means you click 3 seconds late.
- macOS: 系统设置 → 通用 → 日期与时间 → "自动设置" 保持开启。
- Linux: run chrony or ntpd (`timedatectl` should show "System clock synchronized: yes").
- Windows: 时间设置里开启"自动设置时间"。
Start `run.py rush` ~5 minutes before drop time so the browser is warm.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone


def parse_drop_time(s: str) -> datetime:
    s = s.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")
    if dt.tzinfo is None:
        # Naive input: assume local timezone rather than guessing UTC.
        dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return dt


def seconds_until(drop: datetime) -> float:
    return (drop.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()


def wait_until(drop_time: str, tick: float = 0.2, label: str = "drop") -> None:
    """Sleep until drop_time; coarse sleep, then fine ticks in the last 2s."""
    drop = parse_drop_time(drop_time)
    remaining = seconds_until(drop)
    if remaining <= 0:
        print(f"[TIMING] {label} 时间已过 ({drop_time})，立即继续。")
        return
    print(f"[TIMING] 等待 {remaining:.1f}s，目标 {drop} …")
    while True:
        remaining = seconds_until(drop)
        if remaining <= 2.0:
            break
        time.sleep(min(remaining - 2.0, 5.0))
    while seconds_until(drop) > 0:
        time.sleep(tick)
    print(f"[TIMING] 到达 {label} 时间。")
