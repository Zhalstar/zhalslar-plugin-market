"""Validate the AstrBot marketplace and update its cache fingerprint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def main() -> int:
    """Validate market.json and regenerate market-md5.json.

    Returns:
        Zero when the marketplace is valid and the fingerprint is written.

    Raises:
        ValueError: If the marketplace does not follow the AstrBot schema.
    """
    project_dir = Path(__file__).resolve().parent.parent
    market_path = project_dir / "market.json"
    md5_path = project_dir / "market-md5.json"
    market_bytes = market_path.read_bytes()
    market = json.loads(market_bytes.decode("utf-8"))

    if not isinstance(market, dict):
        raise ValueError("market.json must contain a JSON object")

    metadata = market.get("$meta")
    if not isinstance(metadata, dict):
        raise ValueError("market.json must contain a $meta object")
    if metadata.get("schema_version") != 1:
        raise ValueError("$meta.schema_version must be the integer 1")

    required_fields = ("author", "name", "version", "repo", "desc")
    seen_ids: set[str] = set()
    for plugin_id, record in market.items():
        if plugin_id == "$meta":
            continue
        if not isinstance(record, dict):
            raise ValueError(f"{plugin_id}: plugin record must be an object")

        for field in required_fields:
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{plugin_id}: {field} must be a non-empty string")

        author = record["author"].strip()
        name = record["name"].strip()
        expected_id = f"{author}/{name}"
        if plugin_id != expected_id:
            raise ValueError(f"{plugin_id}: root key must equal {expected_id}")
        if expected_id.lower() in seen_ids:
            raise ValueError(f"{plugin_id}: duplicate case-insensitive plugin ID")
        seen_ids.add(expected_id.lower())

        if "/" in author or "/" in name:
            raise ValueError(f"{plugin_id}: author and name cannot contain slashes")
        if not record["repo"].startswith("https://github.com/"):
            raise ValueError(f"{plugin_id}: repo must be an HTTPS GitHub URL")
        if "download_url" in record and not str(record["download_url"]).startswith(
            "https://"
        ):
            raise ValueError(f"{plugin_id}: download_url must use HTTPS")
        for field in ("tags", "support_platforms"):
            if field in record and (
                not isinstance(record[field], list)
                or not all(isinstance(item, str) for item in record[field])
            ):
                raise ValueError(f"{plugin_id}: {field} must be an array of strings")

    digest = hashlib.md5(market_bytes, usedforsecurity=False).hexdigest()
    md5_path.write_text(
        json.dumps({"md5": digest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Validated {len(market) - 1} plugin records. MD5: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
