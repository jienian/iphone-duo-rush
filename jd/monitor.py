"""京东库存监控：轮询 c0.3.cn/stock。

Endpoint: https://c0.3.cn/stock
Query: skuId=<SKU> & area=<AREA_ID> & buyNum=1 & ch=1 [& venderId=.. & cat=..]

area 格式: 省_市_区_镇，例如广州 "1_72_2799_0"。
响应可能是 JSON，也可能是 JSONP（jQueryxxx({...})），parse() 都会处理。
stockState: 33 = 有货，34 = 无货（以 StockStateName 为准做二次确认）。

说明: 单次查询 + 10 秒轮询是正常用户量级。京东对高频请求限流严格，
不要把间隔设到 5 秒以下，否则 IP 可能被临时封禁，反而误事。
"""
from __future__ import annotations

import json
import re
import time

import requests

STOCK_URL = "https://c0.3.cn/stock"
TIMEOUT = 15
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
REFERER = "https://item.jd.com/"


def fetch(sku_id: str, area_id: str, vender_id: str = "", cat: str = "") -> dict:
    params = {
        "skuId": sku_id,
        "area": area_id,
        "buyNum": 1,
        "ch": 1,
    }
    # venderId/cat 非必填；若目标商品页能看到对应值，填上更稳
    # （Apple 自营社区常用 venderId=1000000154）
    if vender_id:
        params["venderId"] = vender_id
    if cat:
        params["cat"] = cat
    resp = requests.get(
        STOCK_URL,
        params=params,
        headers={"User-Agent": UA, "Referer": REFERER, "Accept": "*/*"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return parse(resp.text)


def parse(raw: str) -> dict:
    """剥掉可能的 JSONP 包裹，返回 {"<sku>": {"stockState": 33, ...}}"""
    text = raw.strip()
    m = re.match(r"^[a-zA-Z0-9_.$]+\((.*)\)\s*;?\s*$", text, re.S)
    if m:
        text = m.group(1)
    data = json.loads(text)
    return data.get("stock") or {}


def is_in_stock(entry: dict) -> bool:
    if not entry:
        return False
    try:
        state = int(entry.get("stockState", 0))
    except (TypeError, ValueError):
        return False
    name = str(entry.get("StockStateName") or "")
    return state == 33 or "有货" in name


def watch(
    sku_id: str,
    area_id: str,
    interval: int,
    notifier,
    once: bool = False,
    vender_id: str = "",
    cat: str = "",
) -> None:
    if not sku_id:
        print("[JD] sku_id 未配置（商品页 URL 中 ?sku= 后数字），跳过监控。")
        print("[JD] 填写方法见 README.md「10 月 12 日清单」。")
        return
    was_in_stock = False
    while True:
        try:
            stock = fetch(sku_id, area_id, vender_id, cat)
        except Exception as exc:  # noqa: BLE001
            print(f"[JD] 查询失败: {exc}")
            if once:
                return
            time.sleep(interval)
            continue
        entry = stock.get(str(sku_id)) or {}
        ok = is_in_stock(entry)
        ts = time.strftime("%H:%M:%S")
        print(
            f"[JD {ts}] sku={sku_id} stockState={entry.get('stockState')} "
            f"({entry.get('StockStateName')})"
        )
        if ok and not was_in_stock:
            notifier.send(
                "🛒 iPhone Duo 有货提醒（京东）",
                f"sku {sku_id} 状态变为有货（{entry.get('StockStateName')}）\n"
                f"商品页: https://item.jd.com/{sku_id}.html\n立即下单！",
            )
        was_in_stock = ok
        if once:
            return
        time.sleep(interval)
