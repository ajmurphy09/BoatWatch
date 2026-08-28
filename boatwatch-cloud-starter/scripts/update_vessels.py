from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "vessels.json"

def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def build_mock():
    # This makes the cloud site deployable before an AIS provider is connected.
    # Next step: replace this with the live provider adapter.
    return {
        "generated_at": utc_now(),
        "mode": "mock",
        "watch_area": {"label": "Great Lakes demo area"},
        "vessels": [
            {
                "name": "MARK W. BARKER",
                "type": "Bulk carrier",
                "distance_mi": 8.2,
                "speed_kn": 10.8,
                "course_deg": 32,
                "length_ft": 639,
                "last_seen": utc_now(),
            },
            {
                "name": "STEINEM",
                "type": "Work vessel",
                "distance_mi": 12.6,
                "speed_kn": 6.1,
                "course_deg": 91,
                "length_ft": 92,
                "last_seen": utc_now(),
            },
        ],
    }

def main():
    provider = os.getenv("BOATWATCH_PROVIDER", "mock")
    if provider != "mock":
        raise SystemExit(
            f"Provider {provider!r} is not wired yet. Leave BOATWATCH_PROVIDER unset for the first deployment."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_mock(), indent=2) + "\n")
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
