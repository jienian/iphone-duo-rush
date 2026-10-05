"""Push notifications: Bark + Server酱.

Graceful by design: if no keys are configured, every send() just prints
to the console and returns. Nothing here stores or transmits credentials
other than the keys you put in your own (git-ignored) config.yaml.
"""
from __future__ import annotations

import urllib.parse

import requests

TIMEOUT = 10


class Notifier:
    def __init__(self, bark_key: str = "", server_chan_key: str = ""):
        self.bark_key = (bark_key or "").strip()
        self.server_chan_key = (server_chan_key or "").strip()

    @property
    def configured(self) -> bool:
        return bool(self.bark_key or self.server_chan_key)

    def send(self, title: str, body: str = "") -> None:
        # Always echo to console — the fallback channel.
        print(f"[NOTIFY] {title}")
        if body:
            print(body)
        if self.bark_key:
            try:
                url = (
                    "https://api.day.app/"
                    f"{self.bark_key}/"
                    f"{urllib.parse.quote(title)}/"
                    f"{urllib.parse.quote(body or ' ')}"
                )
                requests.get(url, timeout=TIMEOUT)
            except Exception as exc:  # noqa: BLE001 - notification must not crash the rush
                print(f"[NOTIFY] Bark 推送失败: {exc}")
        if self.server_chan_key:
            try:
                requests.post(
                    f"https://sctapi.ftqq.com/{self.server_chan_key}.send",
                    data={"title": title, "desp": body},
                    timeout=TIMEOUT,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[NOTIFY] Server酱推送失败: {exc}")
