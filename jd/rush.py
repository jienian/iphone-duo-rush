"""京东辅助抢购（Playwright，扫码登录，会话持久化）。

前置（只需做一次）:  python run.py login --channel jd
  打开京东扫码登录页，你用京东 App 扫码，会话保存在 sessions/jd_profile。
  账号密码只进京东官网，不经过本脚本。

抢购流程 run():
  1. wait_until(drop_time) —— 建议提前 5 分钟启动，让浏览器预热
  2. 打开商品页 https://item.jd.com/<sku>.html
  3. 点击抢购按钮（"预约抢购"/"立即预订"/"加入购物车"，按文本定位）
  4. 去购物车结算 → 走到京东「核对订单信息」页
  5. 截图 + 推送通知，停下等你手动点「提交订单」
  6. 仅当 auto_submit=true 时才自动提交（默认关闭！）

注意：京东对高频操作限流。本脚本只做"到点点一次"的拟人操作，
不做多线程刷单——刷单会被京东风控拦截甚至冻结下单，得不偿失。
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

LOGIN_URL = "https://passport.jd.com/new/login.aspx"
CART_URL = "https://cart.jd.com/cart.action"

BUY_PATTERNS = [r"预约抢购", r"立即预订", r"立即购买", r"加入购物车"]
SETTLE_PATTERNS = [r"去结算"]
SUBMIT_PATTERNS = [r"提交订单"]


def _shot(page, shot_dir: str, name: str) -> str:
    os.makedirs(shot_dir, exist_ok=True)
    path = os.path.join(shot_dir, f"jd_{datetime.now():%H%M%S}_{name}.png")
    page.screenshot(path=path)
    print(f"[JD] 截图: {path}")
    return path


def _click_first_match(page, patterns, timeout: int = 8000) -> bool:
    for pat in patterns:
        try:
            loc = page.get_by_role("button", name=re.compile(pat))
            if loc.count() > 0:
                loc.first.click(timeout=timeout)
                print(f"[JD] 点击按钮: {pat}")
                return True
            # 有些按钮不是 <button>，退化为文本定位
            tloc = page.get_by_text(pat, exact=False)
            if tloc.count() > 0:
                tloc.first.click(timeout=timeout)
                print(f"[JD] 点击文本: {pat}")
                return True
        except Exception:  # noqa: BLE001
            continue
    return False


def login(profile_dir: str) -> None:
    from playwright.sync_api import sync_playwright

    os.makedirs(profile_dir, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, headless=False, locale="zh-CN"
        )
        page = ctx.new_page()
        page.goto(LOGIN_URL)
        print("=" * 60)
        print("请在打开的浏览器窗口中用京东 App 扫码登录。")
        print("登录成功后回到终端按回车，登录态会保存在本地。")
        print("=" * 60)
        input("登录完成后按回车继续…")
        ctx.close()
    print(f"[JD] 登录态已保存到 {profile_dir}")


def dry_run_check(page, shot_dir: str) -> None:
    print(f"[JD] dry-run: {page.url} / 标题: {page.title()}")
    _shot(page, shot_dir, "dryrun")
    for label, pats in [("抢购按钮", BUY_PATTERNS)]:
        hit = any(
            page.get_by_role("button", name=re.compile(x)).count() > 0
            or page.get_by_text(x, exact=False).count() > 0
            for x in pats
        )
        print(f"[JD] dry-run 定位器「{label}」: {'命中' if hit else '未命中'}")


def run(cfg: dict, notifier, dry_run: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    jd = cfg["channels"]["jd"]
    paths = cfg["paths"]
    profile_dir = os.path.join(paths["session_dir"], "jd_profile")
    shot_dir = paths["screenshots"]
    item_url = f"https://item.jd.com/{jd['sku_id']}.html"
    auto_submit = bool(cfg.get("auto_submit", False))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, headless=False, locale="zh-CN"
        )
        page = ctx.new_page()

        if dry_run:
            page.goto(item_url, wait_until="domcontentloaded")
            dry_run_check(page, shot_dir)
            ctx.close()
            return

        page.goto(item_url, wait_until="domcontentloaded")
        _shot(page, shot_dir, "00-warmup")
        from common.timing import wait_until

        wait_until(cfg["drop_time"], label="京东抢购")
        page.reload(wait_until="domcontentloaded")

        if not _click_first_match(page, BUY_PATTERNS):
            _shot(page, shot_dir, "ERR-no-buy-button")
            notifier.send("⚠️ 京东抢购异常", "未找到抢购按钮（可能还没放开），请手动接管！")
            input("手动接管后按回车退出…")
            ctx.close()
            return
        time.sleep(2)
        _shot(page, shot_dir, "01-clicked")

        page.goto(CART_URL, wait_until="domcontentloaded")
        if _click_first_match(page, SETTLE_PATTERNS):
            print("[JD] 已点去结算，等待订单确认页…")
        time.sleep(3)
        _shot(page, shot_dir, "99-review")
        notifier.send(
            "🛒 京东已到订单确认页",
            "请立即检查收货地址/配置/金额，无误后手动点「提交订单」。",
        )
        if auto_submit:
            print("[JD] ⚠️ auto_submit=true，5 秒后自动提交订单！Ctrl+C 可取消。")
            time.sleep(5)
            if _click_first_match(page, SUBMIT_PATTERNS, timeout=15000):
                _shot(page, shot_dir, "100-submitted")
                notifier.send("✅ 京东订单已提交", "请到京东 App 确认订单状态。")
            else:
                notifier.send("⚠️ 京东自动提交失败", "请手动点提交订单！")
                input("手动处理后按回车退出…")
        else:
            input("已停在订单确认页。请手动检查并提交订单，完成后按回车退出…")
        ctx.close()
