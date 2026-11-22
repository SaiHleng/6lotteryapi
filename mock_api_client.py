"""Mock API client that talks to Google Apps Script."""

from __future__ import annotations

import aiohttp
from dataclasses import dataclass
from typing import Optional


@dataclass
class MockRound:
    round_id: str
    status: str
    result: Optional[str]
    opened_at: str
    closes_at: str
    settled_at: Optional[str]


class MockAppsScriptClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def health(self) -> dict:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}?action=health", allow_redirects=True) as resp:
                return await resp.json()

    async def get_current_round(self) -> MockRound:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}?action=current", allow_redirects=True) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"API Error: {data['error']}")
                return MockRound(
                    round_id=str(data["round_id"]),
                    status=data["status"],
                    result=data.get("result"),
                    opened_at=str(data.get("opened_at", "")),
                    closes_at=str(data.get("closes_at", "")),
                    settled_at=data.get("settled_at"),
                )

    async def get_result(self, round_id: str) -> MockRound:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                f"{self.base_url}?action=result&round_id={round_id}",
                allow_redirects=True
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"API Error: {data['error']}")
                return MockRound(
                    round_id=str(data["round_id"]),
                    status=data["status"],
                    result=data.get("result"),
                    opened_at=str(data.get("opened_at", "")),
                    closes_at=str(data.get("closes_at", "")),
                    settled_at=data.get("settled_at"),
                )
