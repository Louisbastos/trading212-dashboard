from __future__ import annotations
import certifi
import requests

LIVE_BASE = "https://live.trading212.com/api/v0"
DEMO_BASE = "https://demo.trading212.com/api/v0"


class T212Client:
    def __init__(self, api_key: str, demo: bool = False):
        self.base = DEMO_BASE if demo else LIVE_BASE
        self.session = requests.Session()
        self.session.verify = certifi.where()
        self.session.headers.update({"Authorization": api_key})

    def _get(self, path: str, params: dict = None):
        resp = self.session.get(f"{self.base}{path}", params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_portfolio(self) -> list[dict]:
        return self._get("/equity/portfolio")

    def get_cash(self) -> dict:
        return self._get("/equity/account/cash")

    def get_account_info(self) -> dict:
        return self._get("/equity/account/info")

    def get_dividends(self, limit: int = 50) -> list[dict]:
        result = self._get("/history/dividends", {"limit": limit})
        return result.get("items", result) if isinstance(result, dict) else result

    def get_transactions(self, limit: int = 50) -> list[dict]:
        result = self._get("/history/activity", {"limit": limit})
        return result.get("items", result) if isinstance(result, dict) else result
