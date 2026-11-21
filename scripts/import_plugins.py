"""Import installed AstrBot plugin metadata into the marketplace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def main() -> int:
    """Import valid plugin records from an AstrBot plugin directory.

    Returns:
        Zero after writing all valid plugin records to market.json.

    Raises:
        ValueError: If market.json or a plugin metadata file is invalid.
    """
    parser = argparse.ArgumentParser(
        description="Import installed AstrBot plugins into market.json."
    )
    parser.add_argument(
        "plugins_dir",
        type=Path,
        help="Path to the AstrBot data/plugins directory.",
    )
    args = parser.parse_args()

    plugins_dir = args.plugins_dir.resolve()
    if not plugins_dir.is_dir():
        raise ValueError(f"Plugin directory does not exist: {plugins_dir}")

    project_dir = Path(__file__).resolve().parent.parent
    market_path = project_dir / "market.json"
    market = json.loads(market_path.read_text(encoding="utf-8"))
    metadata = market.get("$meta")
    if not isinstance(metadata, dict):
        raise ValueError("market.json must contain a $meta object")

    records: dict[str, dict] = {}
    skipped: list[str] = []
    allowed_fields = (
        "author",
        "name",
        "version",
        "repo",
        "desc",
        "display_name",
        "short_desc",
        "download_url",
        "logo",
        "tags",
        "category",
        "support_platforms",
        "astrbot_version",
        "social_link",
        "updated_at",
        "i18n",
        "pinned",
        "stars",
        "download_count",
    )

    for metadata_path in sorted(plugins_dir.glob("*/metadata.yaml")):
        plugin = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        if not isinstance(plugin, dict):
            raise ValueError(f"Metadata must be an object: {metadata_path}")

        name = str(plugin.get("name") or "").strip()
        author = str(plugin.get("author") or "").strip()
        repo = str(plugin.get("repo") or "").strip()
        if not name or not author or not repo:
            missing = [
                field
                for field, value in (("name", name), ("author", author), ("repo", repo))
                if not value
            ]
            skipped.append(
                f"{metadata_path.parent.name} (missing {', '.join(missing)})"
            )
            continue

        plugin_id = f"{author}/{name}"
        if plugin_id.casefold() in {item.casefold() for item in records}:
            raise ValueError(f"Duplicate plugin ID: {plugin_id}")
        records[plugin_id] = {
            field: plugin[field]
            for field in allowed_fields
            if field in plugin and plugin[field] is not None
        }

    output = {"$meta": metadata}
    output.update(dict(sorted(records.items(), key=lambda item: item[0].casefold())))
    market_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"Imported {len(records)} plugin records from {plugins_dir}")
    for item in skipped:
        print(f"Skipped {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
