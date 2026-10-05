"""Apple 中国官网库存监控：轮询 fulfillment API。

Endpoint: https://www.apple.com/cn/shop/fulfillment-messages
Query: pl=true & mt=regular & parts.0=<PART_NUMBER> & location=<ZIP> [& store=Rxxx]

响应 JSON 关键结构:
  body.content.pickupMessage.stores[] -> {
      "storeName": "...",
      "partsAvailability": { "<PART>": {
          "pickupDisplay": "available" | "unavailable",
          "pickupSearchQuote": "...", "pickupType": "..." } } }
  body.content.deliveryMessage -> 配送文案/选项（结构可能变化，原样返回）

说明: 这个接口是苹果官网前端自己调用的公开接口，单次查询 + 10~15 秒
轮询间隔属于正常用户行为量级。不要缩短到 1~2 秒——会被限流，
且对抢购成功率没有任何帮助（瓶颈在服务端队列，不在你的轮询频率）。
"""
from __future__ import annotations

import time

import requests

FULFILLMENT_URL = "https://www.apple.com/cn/shop/fulfillment-messages"
# 备用端点（社区验证过的另一路查询方式；主接口变化时用）:
#   https://www.apple.com/cn/shop/retail/pickup-message?pl=true&location=<Rxxx>&parts.0=<PART>
#   解析 body.stores[].partsAvailability.<PART>.buyability.isBuyable
PICKUP_URL = "https://www.apple.com/cn/shop/retail/pickup-message"
TIMEOUT = 15
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch(part_number: str, location_zip: str, store_id: str = "") -> dict:
    params = {
        "pl": "true",
        "mt": "regular",
        "parts.0": part_number,
        "location": location_zip,
    }
    if store_id:
        params["store"] = store_id
    resp = requests.get(
        FULFILLMENT_URL,
        params=params,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def parse(data: dict, part_number: str) -> dict:
    """解析 fulfillment 响应 -> {"stores": [...], "delivery": ...}"""
    content = (data.get("body") or {}).get("content") or {}
    pickup = content.get("pickupMessage") or {}
    stores = []
    for store in pickup.get("stores") or []:
        avail = (store.get("partsAvailability") or {}).get(part_number) or {}
        stores.append(
            {
                "store": store.get("storeName") or store.get("storeId"),
                "display": avail.get("pickupDisplay"),
                "quote": avail.get("pickupSearchQuote"),
            }
        )
    return {"stores": stores, "delivery": content.get("deliveryMessage")}


def any_available(parsed: dict) -> list:
    # 社区经验规则: pickupDisplay != "unavailable" 即视为有货
    return [s for s in parsed["stores"] if (s["display"] or "") not in ("", "unavailable")]


def fetch_alt(part_number: str, store_id: str) -> dict:
    """备用 pickup-message 端点。"""
    params = {"pl": "true", "location": store_id, "parts.0": part_number}
    resp = requests.get(
        PICKUP_URL,
        params=params,
        headers={"User-Agent": UA, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def parse_alt(data: dict, part_number: str) -> dict:
    stores = []
    for store in (data.get("body") or {}).get("stores") or []:
        avail = (store.get("partsAvailability") or {}).get(part_number) or {}
        buyable = (avail.get("buyability") or {}).get("isBuyable")
        stores.append(
            {
                "store": store.get("storeName") or store.get("storeNumber"),
                "display": "available" if buyable else "unavailable",
                "quote": avail.get("pickupSearchQuote"),
            }
        )
    return {"stores": stores, "delivery": None}


def _check_once(part_number: str, location_zip: str, store_id: str) -> dict:
    parsed = parse(fetch(part_number, location_zip, store_id), part_number)
    if not parsed["stores"] and store_id:
        # 主接口无门店数据时，尝试备用端点
        parsed = parse_alt(fetch_alt(part_number, store_id), part_number)
    return parsed


def watch(
    part_numbers,  # str | list[str]：要盯的全部配置（Duo 共 8 个版本可全盯）
    location_zip: str,
    store_id: str,
    interval: int,
    notifier,
    once: bool = False,
    sustained_rounds: int = 3,
) -> None:
    """DING果式监控：轮询 fulfillment 接口，检测到有货约 1 秒内推送。

    持续放货判定（来自 DING果 的经验）：
    - 第 1 轮阳性 -> 普通提醒（一闪而过的库存，别太难受）
    - 连续 sustained_rounds 轮阳性 -> 升级为"持续放货"强提醒（真机会，立刻下单）
    - 之后每 4 轮再提醒一次；转阴则计数清零
    每个 part 独立计数，互不干扰。
    """
    if isinstance(part_numbers, str):
        part_numbers = [part_numbers]
    part_numbers = [p for p in (part_numbers or []) if p]
    if not part_numbers:
        print("[APPLE] part_number 未配置（10 月 12 日后填入），跳过监控。")
        print("[APPLE] 填写方法见 README.md「10 月 12 日清单」。")
        return
    consec: dict = {p: 0 for p in part_numbers}
    while True:
        for part in part_numbers:
            try:
                parsed = _check_once(part, location_zip, store_id)
            except Exception as exc:  # noqa: BLE001 - 监控循环不能因单次请求失败退出
                print(f"[APPLE] 查询失败 {part}: {exc}")
                continue
            avail = any_available(parsed)
            ts = time.strftime("%H:%M:%S")
            if avail:
                consec[part] += 1
                n = consec[part]
                names = "、".join(s["store"] for s in avail[:5])
                print(f"[APPLE {ts}] {part} 有货（连续第 {n} 轮），门店 {len(avail)}/{len(parsed['stores'])}")
                if n == 1:
                    notifier.send(
                        "🍎 iPhone Duo 有货提醒（Apple 官网）",
                        f"{part} 在 {len(avail)} 家门店可自提：{names}\n"
                        "可能是短暂放货，点进去看一眼；若连续多轮有货会再强提醒。",
                    )
                elif n == sustained_rounds:
                    notifier.send(
                        "🚨 iPhone Duo 持续放货！（Apple 官网）",
                        f"{part} 已连续 {n} 轮检测到有货，这是真机会！\n"
                        f"门店：{names}\n立刻打开 Apple Store App / 官网下单！",
                    )
                elif n > sustained_rounds and (n - sustained_rounds) % 4 == 0:
                    notifier.send(
                        "🍎 iPhone Duo 仍有货（Apple 官网）",
                        f"{part} 持续有货中（第 {n} 轮）：{names}",
                    )
            else:
                if consec[part] >= sustained_rounds:
                    print(f"[APPLE {ts}] {part} 放货结束（曾连续 {consec[part]} 轮有货）")
                elif consec[part] > 0:
                    print(f"[APPLE {ts}] {part} 转无货（之前连续 {consec[part]} 轮）")
                consec[part] = 0
        if once:
            return
        time.sleep(interval)
