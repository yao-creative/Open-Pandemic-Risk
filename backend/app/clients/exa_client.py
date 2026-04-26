from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ExaSearchResult:
    url: str
    title: str | None
    snippet: str | None


class ExaClient:
    def __init__(self, *, api_url: str, api_key: str, timeout_seconds: float) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def search(self, *, query: str, num_results: int) -> list[ExaSearchResult]:
        response = httpx.post(
            self.api_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "numResults": num_results},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results") or []
        result: list[ExaSearchResult] = []
        for row in rows:
            url = row.get("url")
            if not url:
                continue
            result.append(
                ExaSearchResult(
                    url=str(url),
                    title=str(row.get("title")) if row.get("title") else None,
                    snippet=str(row.get("text")) if row.get("text") else None,
                )
            )
        return result
