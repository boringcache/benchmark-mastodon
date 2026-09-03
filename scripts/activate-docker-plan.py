#!/usr/bin/env python3
"""Resolve workload and GitHub publication values in the committed Docker plan."""

import argparse
import json
import re
import tomllib
from pathlib import Path

PLAN = Path(__file__).resolve().parents[1] / ".boringcache.toml"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise SystemExit(f"committed Mastodon plan no longer contains {old!r}")
    return source.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", choices=("server", "streaming"), required=True)
    parser.add_argument("--tool-cache", choices=("true", "false"), required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--prerelease", required=True)
    parser.add_argument("--push", choices=("true", "false"), required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--plan", type=Path, default=PLAN)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha):
        raise SystemExit("source SHA must be a full lowercase commit SHA")
    if not re.fullmatch(r"nightly\.[0-9]{4}-[0-9]{2}-[0-9]{2}", args.prerelease):
        raise SystemExit("prerelease must use nightly.YYYY-MM-DD")
    if args.tool_cache == "true" and args.workload != "server":
        raise SystemExit("the sccache scenario is available only for the server image")

    dockerfile = (
        "scenarios/mastodon-sccache/Dockerfile"
        if args.tool_cache == "true"
        else "upstream/Dockerfile"
        if args.workload == "server"
        else "upstream/streaming/Dockerfile"
    )
    image = (
        args.image
        if args.push == "true"
        else f"mastodon-{args.workload}-benchmark:local"
    )

    source = args.plan.read_text()
    source = replace_once(source, '"__DOCKERFILE__"', json.dumps(dockerfile))
    source = replace_once(source, "MASTODON_VERSION_PRERELEASE=__PRERELEASE__", f"MASTODON_VERSION_PRERELEASE={args.prerelease}")
    source = replace_once(source, "SOURCE_COMMIT=__SOURCE_SHA__", f"SOURCE_COMMIT={args.source_sha}")
    source = replace_once(source, '"__IMAGE__"', json.dumps(image))
    if args.tool_cache == "true":
        source = replace_once(
            source,
            'metadata-hints = ["benchmark=mastodon", "upstream-job=build-image-amd64"]',
            'metadata-hints = ["benchmark=mastodon", "upstream-job=build-image-amd64"]\ntool-cache = ["sccache"]',
        )
    if args.push == "true":
        source = replace_once(source, '  "upstream",\n]', '  "--push",\n  "upstream",\n]')
    tomllib.loads(source)
    args.plan.write_text(source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
