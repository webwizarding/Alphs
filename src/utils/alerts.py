from __future__ import annotations
import asyncio
import json
import time
import urllib.request


class DiscordAlerter:
    def __init__(self, webhook_url: str, min_interval_sec: int = 2):
        self.webhook_url = webhook_url
        self.min_interval_sec = min_interval_sec
        self._last_ts = 0.0
        self._disabled = False

    async def send(self, title: str, content: str, fields: list[dict] | None = None, color: int = 0x2F3136) -> None:
        if not self.webhook_url:
            return
        if self._disabled:
            return
        now = time.time()
        if now - self._last_ts < self.min_interval_sec:
            return
        self._last_ts = now
        embed = {
            "title": title,
            "description": content,
            "color": color,
            "fields": fields or [],
        }
        payload = {
            "embeds": [embed],
            "tts": False,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.webhook_url, data=data, headers={"Content-Type": "application/json"})
        try:
            await asyncio.to_thread(urllib.request.urlopen, req)
        except Exception:
            self._disabled = True
