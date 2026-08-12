#!/usr/bin/env python3
"""Verify Mastodon's server and streaming image benchmark plan."""

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)

def main() -> int:
    try:
        command = tomllib.loads((ROOT / ".boringcache.toml").read_text())["adapters"]["docker"]["command"]
        require(command[:4] == ["bash", "-euo", "pipefail", "-c"], "Docker plan must be argv-safe")
        shell = command[4]
        for fragment in ("upstream/Dockerfile", "upstream/streaming/Dockerfile", "--platform linux/amd64", "MASTODON_VERSION_PRERELEASE", "MASTODON_VERSION_METADATA=", "SOURCE_COMMIT"):
            require(fragment in shell, f"Docker plan changed: {fragment}")
        upstream = (ROOT / "upstream/.github/workflows/build-container-image.yml").read_text()
        for fragment in ("- linux/amd64", "- linux/arm64", "file: ${{ inputs.file_to_build }}", "MASTODON_VERSION_PRERELEASE", "MASTODON_VERSION_METADATA", "SOURCE_COMMIT", "push-by-digest=true"):
            require(fragment in upstream, f"upstream image workflow changed: {fragment}")
        caller = (ROOT / "upstream/.github/workflows/build-nightly.yml").read_text()
        require("file_to_build: Dockerfile" in caller and "file_to_build: streaming/Dockerfile" in caller, "nightly workload selection changed")
        action = (ROOT / ".github/actions/mastodon-docker-benchmark/action.yml").read_text()
        require("dockerfile=upstream/Dockerfile" in action, "server baseline no longer uses upstream Dockerfile")
        require('dockerfile="scenarios/mastodon-${COMPILER_CACHE}/Dockerfile"' in action, "compiler-cache scenario selection changed")
        require("dockerfile=upstream/streaming/Dockerfile" in action, "streaming plan changed")
        require(action.count("steps.scope.outputs.dockerfile") == 3, "provider Dockerfile selection drifted")
        require(action.count("steps.scope.outputs.docker_tool_cache") == 2, "BoringCache compiler-cache projection drifted")
        require(action.count("SOURCE_COMMIT=${{ steps.scope.outputs.source_sha }}") == 3, "provider commit arg drifted")
    except (KeyError, OSError, RuntimeError, tomllib.TOMLDecodeError) as error:
        print(f"Mastodon recipe mismatch: {error}", file=sys.stderr)
        return 1
    print("Verified Mastodon server/streaming amd64 plans.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
