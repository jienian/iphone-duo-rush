#!/usr/bin/env python3
"""iPhone Duo 双渠道抢购助手。

用法:
  python run.py check-config            # 校验配置
  python run.py login --channel apple  # Apple ID 手动登录一次（会话持久化）
  python run.py login --channel jd     # 京东 App 扫码登录一次
  python run.py monitor [--once] [--channel apple|jd]
                                       # 库存监控（循环；--once 只查一次）
  python run.py rush --channel apple|jd|both [--dry-run]
                                       # 到点自动走单（默认停在订单确认页）

先装依赖:  pip install -r requirements.txt
再装浏览器: python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

from common.notify import Notifier  # noqa: E402
from common.timing import parse_drop_time  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.yaml")
EXAMPLE_PATH = os.path.join(ROOT, "config.example.yaml")


def _abspath(p: str) -> str:
    p = (p or "").strip()
    return p if os.path.isabs(p) else os.path.join(ROOT, p)


def load_config(path: str = CONFIG_PATH) -> dict:
    if not os.path.exists(path):
        print(f"未找到 {path}，先执行: cp config.example.yaml config.yaml")
        sys.exit(2)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_config(cfg: dict) -> int:
    """返回 0=可用, 1=有警告(占位未填), 2=配置错误。"""
    errors, warnings = [], []
    try:
        parse_drop_time(str(cfg.get("drop_time", "")))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"drop_time 格式错误: {exc}")

    apple = (cfg.get("channels") or {}).get("apple") or {}
    jd = (cfg.get("channels") or {}).get("jd") or {}
    apple_parts = list(apple.get("part_numbers") or [])
    if apple.get("part_number"):
        apple_parts.insert(0, apple["part_number"])
    if apple.get("enabled") and not apple_parts:
        warnings.append("apple.part_number/part_numbers 为空：10 月 12 日后按 README 填入（监控/下单会跳过 Apple 渠道）")
    if jd.get("enabled") and not str(jd.get("sku_id") or ""):
        warnings.append("jd.sku_id 为空：按 README 填入京东 sku（监控/下单会跳过京东渠道）")

    notify = cfg.get("notify") or {}
    if not Notifier(notify.get("bark_key"), notify.get("server_chan_key")).configured:
        warnings.append("notify 未配置 Bark/Server酱：通知只会打印到控制台（抢购时你必须盯着屏幕）")

    if cfg.get("auto_submit"):
        warnings.append("⚠️ auto_submit=true：脚本会自动提交订单并扣款，请确认这是你想要的！")

    paths = cfg.get("paths") or {}
    for key in ("session_dir", "screenshots"):
        if not paths.get(key):
            errors.append(f"paths.{key} 未配置")

    for w in warnings:
        print(f"[WARN] {w}")
    for e in errors:
        print(f"[ERROR] {e}")
    if errors:
        print("配置错误，请修复后重试。"); return 2
    if warnings:
        print("配置可用，但有上述警告。"); return 1
    print("配置 OK。"); return 0


def cmd_monitor(cfg: dict, channel: str, once: bool) -> None:
    notifier = Notifier(
        (cfg.get("notify") or {}).get("bark_key"),
        (cfg.get("notify") or {}).get("server_chan_key"),
    )
    from apple import monitor as apple_mon
    from jd import monitor as jd_mon

    jobs = []
    apple = (cfg.get("channels") or {}).get("apple") or {}
    jd = (cfg.get("channels") or {}).get("jd") or {}
    if channel in ("apple", "both") and apple.get("enabled"):
        parts = list(apple.get("part_numbers") or [])
        if apple.get("part_number"):
            parts.insert(0, apple["part_number"])
        jobs.append(threading.Thread(
            target=apple_mon.watch,
            kwargs=dict(
                part_numbers=parts,
                location_zip=apple.get("location_zip") or "",
                store_id=apple.get("store_id") or "",
                interval=int(apple.get("poll_interval_sec") or 15),
                notifier=notifier, once=once,
            ),
            daemon=True,
        ))
    if channel in ("jd", "both") and jd.get("enabled"):
        jobs.append(threading.Thread(
            target=jd_mon.watch,
            kwargs=dict(
                sku_id=str(jd.get("sku_id") or ""),
                area_id=jd.get("area_id") or "",
                interval=int(jd.get("poll_interval_sec") or 10),
                notifier=notifier, once=once,
                vender_id=str(jd.get("vender_id") or ""),
                cat=str(jd.get("cat") or ""),
            ),
            daemon=True,
        ))
    if not jobs:
        print("没有启用的渠道（或渠道 ID 未填）。先跑 python run.py check-config")
        return
    for j in jobs:
        j.start()
    try:
        for j in jobs:
            j.join()
    except KeyboardInterrupt:
        print("\n监控已停止。")


def cmd_login(cfg: dict, channel: str) -> None:
    session_dir = cfg["paths"]["session_dir"]
    if channel == "apple":
        from apple.checkout import login
        login(os.path.join(session_dir, "apple_profile"))
    else:
        from jd.rush import login
        login(os.path.join(session_dir, "jd_profile"))


def cmd_rush(cfg: dict, channel: str, dry_run: bool) -> None:
    notifier = Notifier(
        (cfg.get("notify") or {}).get("bark_key"),
        (cfg.get("notify") or {}).get("server_chan_key"),
    )
    apple = (cfg.get("channels") or {}).get("apple") or {}
    jd = (cfg.get("channels") or {}).get("jd") or {}
    if channel in ("apple", "both") and apple.get("enabled"):
        if not apple.get("part_number") and not dry_run:
            print("[APPLE] part_number 未填，跳过。")
        else:
            from apple.checkout import run as apple_run
            apple_run(cfg, notifier, dry_run=dry_run)
    if channel in ("jd", "both") and jd.get("enabled"):
        if not str(jd.get("sku_id") or "") and not dry_run:
            print("[JD] sku_id 未填，跳过。")
        else:
            from jd.rush import run as jd_run
            jd_run(cfg, notifier, dry_run=dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description="iPhone Duo 双渠道抢购助手")
    ap.add_argument("--config", default=CONFIG_PATH, help="配置文件路径（默认 ./config.yaml）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check-config", help="校验配置文件")

    p_login = sub.add_parser("login", help="手动登录一次，持久化会话")
    p_login.add_argument("--channel", choices=["apple", "jd"], required=True)

    p_mon = sub.add_parser("monitor", help="库存监控")
    p_mon.add_argument("--once", action="store_true", help="只查询一次就退出")
    p_mon.add_argument("--channel", choices=["apple", "jd", "both"], default="both")

    p_rush = sub.add_parser("rush", help="到点自动走单")
    p_rush.add_argument("--channel", choices=["apple", "jd", "both"], default="both")
    p_rush.add_argument("--dry-run", action="store_true",
                        help="只打开商品页校验定位器，不做任何购买动作")

    args = ap.parse_args()
    cfg = load_config(args.config)
    # 统一用绝对路径，避免换目录运行时写散
    cfg["paths"]["session_dir"] = _abspath(cfg["paths"].get("session_dir"))
    cfg["paths"]["screenshots"] = _abspath(cfg["paths"].get("screenshots"))

    if args.cmd == "check-config":
        sys.exit(check_config(cfg))
    if args.cmd == "login":
        cmd_login(cfg, args.channel)
    elif args.cmd == "monitor":
        cmd_monitor(cfg, args.channel, args.once)
    elif args.cmd == "rush":
        cmd_rush(cfg, args.channel, args.dry_run)


if __name__ == "__main__":
    main()
