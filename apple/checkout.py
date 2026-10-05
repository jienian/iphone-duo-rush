"""Apple 官网辅助下单（Playwright，持久化登录态）。

前置（只需做一次）:  python run.py login --channel apple
  打开 Apple ID 登录页，你在浏览器窗口里手动登录（含双重认证），
  会话保存在 sessions/apple_profile。密码只进苹果官网，不经过本脚本。

抢购流程 run():
  1. wait_until(drop_time) —— 建议提前 5 分钟启动，让浏览器预热
  2. 打开 product_url（10/12 后的 Get Ready 页或 Duo 购买页）
  3. 选择 storage / color / quantity（默认 2 台，苹果每人限购 2 台）
  4. 点击「加入购物袋」→ 打开购物袋 → 点击「结账」
  5. 选择取货方式：pickup=到店自提（默认，珠江新城）/ delivery=送货
  6. 逐页走完支付（使用你账号已保存的支付方式）
  7. 停在「核对订单信息」页：截图 + 推送通知，等你手动点「提交订单」
  8. 仅当 auto_submit=true 时才自动点最后一步（默认关闭！）

注意：10 月 12 日前 Duo 购买页不存在，下面的文本定位器是按苹果官网
一贯文案写的（"加入购物袋" / "结账" / "核对订单信息"）。
--dry-run 会打开页面并逐个校验定位器是否命中，按报告微调即可。
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime

ACCOUNT_HOME = "https://www.apple.com/cn/shop/account/home"
BAG_URL = "https://www.apple.com/cn/shop/bag"

ADD_PATTERNS = [r"加入购物袋", r"添加到购物袋", r"Add to Bag"]
CHECKOUT_PATTERNS = [r"^结账$", r"去结账", r"Checkout"]
PICKUP_PATTERNS = [r"自提", r"到店取货", r"店内取货", r"取货", r"Pickup"]
REVIEW_PATTERNS = [r"核对订单信息", r"提交订单", r"Place Your Order", r"Review Your Order"]
SUBMIT_PATTERNS = [r"^提交订单$", r"下单", r"Place Your Order"]


def _shot(page, shot_dir: str, name: str) -> str:
    os.makedirs(shot_dir, exist_ok=True)
    path = os.path.join(shot_dir, f"apple_{datetime.now():%H%M%S}_{name}.png")
    page.screenshot(path=path)
    print(f"[APPLE] 截图: {path}")
    return path


def _click_first_match(page, patterns, timeout: int = 8000) -> bool:
    for pat in patterns:
        try:
            loc = page.get_by_role("button", name=re.compile(pat))
            if loc.count() > 0:
                loc.first.click(timeout=timeout)
                print(f"[APPLE] 点击按钮: {pat}")
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
        page.goto(ACCOUNT_HOME)
        print("=" * 60)
        print("请在打开的浏览器窗口中手动完成 Apple ID 登录（含双重认证）。")
        print("登录成功后回到终端按回车，登录态会保存在本地。")
        print("=" * 60)
        input("登录完成后按回车继续…")
        ctx.close()
    print(f"[APPLE] 登录态已保存到 {profile_dir}")


def _select_option(page, text: str, label: str) -> bool:
    try:
        loc = page.get_by_text(text, exact=False)
        if loc.count() > 0:
            loc.first.click(timeout=8000)
            print(f"[APPLE] 已选择{label}: {text}")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[APPLE] 选择{label}失败 ({text}): {exc}")
    return False


def _set_quantity(page, qty: int) -> bool:
    """在商品页把数量设为 qty（苹果购买页通常有数量选择器）。"""
    if qty <= 1:
        return True
    ok = False
    try:
        combo = page.get_by_role("combobox").filter(
            has_text=re.compile(r"数量|Quantity")
        )
        if combo.count() > 0:
            combo.first.select_option(str(qty))
            print(f"[APPLE] 数量已设为 {qty}（下拉框）")
            ok = True
    except Exception:  # noqa: BLE001
        pass
    if not ok:
        try:
            # 数量区域内的数字选项：先定位"数量"再点旁边的数字
            qty_section = page.get_by_text(re.compile(r"^数量$|Quantity"))
            if qty_section.count() > 0:
                btn = page.get_by_role("button", name=re.compile(rf"^{qty}$"))
                if btn.count() > 0:
                    btn.first.click(timeout=8000)
                    print(f"[APPLE] 数量已设为 {qty}")
                    ok = True
        except Exception as exc:  # noqa: BLE001
            print(f"[APPLE] 设置数量失败: {exc}")
    if not ok:
        print(f"[APPLE] ⚠️ 未能自动设置数量为 {qty}，请在 dry-run 中确认定位器")
    return ok


def _select_pickup(page, store_names) -> str:
    """在结账流程中选择自提，按门店列表顺序尝试。返回选中的门店名，失败返回空串。"""
    if isinstance(store_names, str):
        store_names = [store_names]
    if not _click_first_match(page, PICKUP_PATTERNS):
        print("[APPLE] 未找到自提选项（可能页面默认已是自提或文案不同）")
        return ""
    time.sleep(2)
    for name in store_names or []:
        if _select_option(page, name, "自提门店"):
            return name
    print(f"[APPLE] ⚠️ 列表门店均未选中：{store_names}，请在 dry-run 中确认门店名称文案")
    return ""


def _select_pickup_date(page, date_text: str) -> str:
    """选择自提日期（如下单时可选）。返回选中的日期文案，失败返回空串。"""
    if not date_text:
        return ""
    try:
        loc = page.get_by_text(re.compile(re.escape(date_text)), exact=False)
        if loc.count() > 0:
            loc.first.click(timeout=8000)
            print(f"[APPLE] 已选择自提日期: {date_text}")
            return date_text
    except Exception as exc:  # noqa: BLE001
        print(f"[APPLE] 选择自提日期失败 ({date_text}): {exc}")
    print(f"[APPLE] ⚠️ 未找到自提日期 {date_text}，请在订单确认页手动确认日期")
    return ""


def dry_run_check(page, shot_dir: str, storage: str, color: str, qty: int) -> None:
    """打开商品页，校验每个定位器是否命中，不做任何购买动作。"""
    print(f"[APPLE] dry-run: {page.url} / 标题: {page.title()}")
    _shot(page, shot_dir, "dryrun")
    for label, text in [("存储", storage), ("颜色", color)]:
        hit = page.get_by_text(text, exact=False).count() > 0
        print(f"[APPLE] dry-run 定位器「{label}={text}」: {'命中' if hit else '未命中'}")
    qty_hit = (
        page.get_by_role("combobox").filter(has_text=re.compile(r"数量|Quantity")).count() > 0
        or page.get_by_role("button", name=re.compile(rf"^{qty}$")).count() > 0
    )
    print(f"[APPLE] dry-run 定位器「数量={qty}」: {'命中' if qty_hit else '未命中（需手动微调）'}")
    for label, pats in [("加入购物袋", ADD_PATTERNS), ("结账", CHECKOUT_PATTERNS)]:
        hit = any(
            page.get_by_role("button", name=re.compile(p)).count() > 0 for p in pats
        )
        print(f"[APPLE] dry-run 定位器「{label}」: {'命中' if hit else '未命中'}")


def run(cfg: dict, notifier, dry_run: bool = False) -> None:
    from playwright.sync_api import sync_playwright

    apple = cfg["channels"]["apple"]
    paths = cfg["paths"]
    profile_dir = os.path.join(paths["session_dir"], "apple_profile")
    shot_dir = paths["screenshots"]
    product_url = apple.get("product_url") or "https://www.apple.com/cn/shop/buy-iphone/iphone-duo"
    auto_submit = bool(cfg.get("auto_submit", False))

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            profile_dir, headless=False, locale="zh-CN"
        )
        page = ctx.new_page()

        if dry_run:
            page.goto(product_url, wait_until="domcontentloaded")
            dry_run_check(page, shot_dir, apple["storage"], apple["color"],
                          int(apple.get("quantity") or 1))
            ctx.close()
            return

        # 预热：提前打开页面，等到点
        page.goto(product_url, wait_until="domcontentloaded")
        _shot(page, shot_dir, "00-warmup")
        from common.timing import wait_until

        wait_until(cfg["drop_time"], label="Apple 预购")
        page.reload(wait_until="domcontentloaded")

        qty = int(apple.get("quantity") or 1)
        _select_option(page, apple["storage"], "存储")
        _select_option(page, apple["color"], "颜色")
        _set_quantity(page, qty)
        _shot(page, shot_dir, "01-config")

        if not _click_first_match(page, ADD_PATTERNS):
            _shot(page, shot_dir, "ERR-no-add-button")
            notifier.send("⚠️ Apple 下单异常", "未找到「加入购物袋」按钮，请手动接管！")
            input("手动接管后按回车退出…")
            ctx.close()
            return
        time.sleep(2)
        _shot(page, shot_dir, "02-added")

        page.goto(BAG_URL, wait_until="domcontentloaded")
        if not _click_first_match(page, CHECKOUT_PATTERNS):
            _shot(page, shot_dir, "ERR-no-checkout")
            notifier.send("⚠️ Apple 下单异常", "已加入购物袋，但未找到「结账」按钮，请手动接管！")
            input("手动接管后按回车退出…")
            ctx.close()
            return

        # 取货方式：自提 or 送货（用户要求：到店自提，珠江新城/天环广场都可）
        fulfillment = (apple.get("fulfillment") or "delivery").lower()
        pickup_chosen = ""
        if fulfillment == "pickup":
            stores = apple.get("pickup_stores") or (
                [apple["pickup_store"]] if apple.get("pickup_store") else []
            )
            print(f"[APPLE] 选择自提方式，门店顺序：{stores}")
            pickup_chosen = _select_pickup(page, stores)
            pickup_date_chosen = _select_pickup_date(page, apple.get("pickup_date") or "")
            _shot(page, shot_dir, "04-pickup")

        # 走完配送/支付步骤，直到出现订单核对页
        print("[APPLE] 正在走结账流程，等待「核对订单信息」页…")
        deadline = time.time() + 300
        last_shot = 0
        while time.time() < deadline:
            try:
                text = page.content()
            except Exception:  # noqa: BLE001
                text = ""
            if any(re.search(pat, text) for pat in REVIEW_PATTERNS):
                break
            if time.time() - last_shot > 5:
                _shot(page, shot_dir, "03-checkout-flow")
                last_shot = time.time()
            time.sleep(1)

        _shot(page, shot_dir, "99-review")
        if fulfillment == "pickup":
            store_note = f"自提（{pickup_chosen}）" if pickup_chosen else "自提【⚠️门店未自动选中，务必手动确认！】"
            date_note = f"{apple.get('pickup_date')}取货" if pickup_date_chosen else "取货日期【⚠️未自动选中，务必手动确认！】"
            fulfill_note = f"{store_note}，{date_note}"
        else:
            fulfill_note = "送货上门"
        notifier.send(
            "🍎 Apple 官网已到订单确认页",
            f"数量 {qty} 台，{fulfill_note}。\n"
            "请立即检查配置/数量/取货方式/金额，无误后手动点「提交订单」完成支付。",
        )
        if auto_submit:
            print("[APPLE] ⚠️ auto_submit=true，5 秒后自动提交订单！Ctrl+C 可取消。")
            time.sleep(5)
            if _click_first_match(page, SUBMIT_PATTERNS, timeout=15000):
                _shot(page, shot_dir, "100-submitted")
                notifier.send("✅ Apple 官网订单已提交", "请到 Apple Store App 确认订单状态。")
            else:
                notifier.send("⚠️ Apple 自动提交失败", "请手动点提交订单！")
                input("手动处理后按回车退出…")
        else:
            input("已停在订单确认页。请手动检查并提交订单，完成后按回车退出…")
        ctx.close()
