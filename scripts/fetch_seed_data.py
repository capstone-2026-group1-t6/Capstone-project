"""Downloads and pre-processes the public seed dataset(s) into data/seed/.

Per the proposal's data-source plan: MIT/public-domain seed datasets only,
~1,000-5,000 chunks each. Fill in DATASET_URL below once the team picks the
specific seed corpus (e.g. a public engineering-wiki dump or similar).
No proprietary data, no scraped data, no paid APIs.
"""

import json
from pathlib import Path

SEED_DIR = Path(__file__).resolve().parent.parent / "data" / "seed"

# TODO(Yusra): replace with the actual chosen public dataset URL + license.
DATASET_URL = ""
DATASET_LICENSE = "MIT"  # or CC-BY / public-domain — must be recorded here


def main() -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)

    if not DATASET_URL:
        print("DATASET_URL is not set yet. Writing a tiny placeholder corpus")
        print("so the pipeline and tests have something to run against.")
        placeholder = [
            {
                "chunk_id": "placeholder-0001",
                "text": "Placeholder chunk. Replace with real seed data before eval.",
                "source": "placeholder",
            }
        ]
        (SEED_DIR / "corpus.jsonl").write_text(
            "\n".join(json.dumps(row) for row in placeholder), encoding="utf-8"
        )
        return

    raise NotImplementedError("Wire up the real download once DATASET_URL is set.")


if __name__ == "__main__":
    main()
