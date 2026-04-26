from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode


@dataclass
class EndpointStats:
    endpoint: str
    count: int
    publication_min: str | None
    publication_max: str | None


def _fetch_json(url: str) -> dict:
    payload = subprocess.run(["curl", "-sS", url], check=True, capture_output=True, text=True).stdout
    return json.loads(payload)


def _extract_stats(endpoint: str) -> EndpointStats:
    query = urlencode({"$top": 100})
    payload = _fetch_json(f"{endpoint}?{query}")
    values = payload.get("value", [])
    count = int(payload.get("@odata.count", len(values)))

    publication_dates = []
    for row in values:
        for key in ("PublicationDateAndTime", "PublicationDate"):
            value = row.get(key)
            if value:
                publication_dates.append(value)
                break

    if publication_dates:
        parsed = [datetime.fromisoformat(ts.replace("Z", "+00:00")) for ts in publication_dates]
        publication_min = min(parsed).isoformat()
        publication_max = max(parsed).isoformat()
    else:
        publication_min = None
        publication_max = None

    return EndpointStats(
        endpoint=endpoint,
        count=count,
        publication_min=publication_min,
        publication_max=publication_max,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe WHO DON/Emergencies API coverage.")
    parser.add_argument("--out", type=Path, default=Path("ml/data/who_api_probe.json"))
    args = parser.parse_args()

    endpoints = [
        "https://www.who.int/api/news/dons",
        "https://www.who.int/api/news/emergencies",
        "https://www.who.int/api/news/outbreaks",
    ]
    stats = [_extract_stats(endpoint) for endpoint in endpoints]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([asdict(item) for item in stats], indent=2), encoding="utf-8")

    for item in stats:
        print(
            f"endpoint={item.endpoint} count={item.count} "
            f"publication_min={item.publication_min} publication_max={item.publication_max}"
        )


if __name__ == "__main__":
    main()
