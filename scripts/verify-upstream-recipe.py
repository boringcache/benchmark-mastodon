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
        plan = tomllib.loads((ROOT / ".boringcache.toml").read_text())
        command = plan["adapters"]["docker"]["command"]
        require(command[:7] == ["docker", "buildx", "build", "--file", "__DOCKERFILE__", "--platform", "linux/amd64"], "Docker plan changed")
        for fragment in ("MASTODON_VERSION_PRERELEASE=__PRERELEASE__", "MASTODON_VERSION_METADATA=", "SOURCE_COMMIT=__SOURCE_SHA__", "__IMAGE__"):
            require(fragment in command, f"Docker plan changed: {fragment}")
        require(plan["adapters"]["sccache"]["tag"] == "mastodon-sccache-local", "sccache plan changed")
        activation = (ROOT / "scripts/activate-docker-plan.py").read_text()
        for fragment in ("scenarios/mastodon-sccache/Dockerfile", "upstream/streaming/Dockerfile", 'tool-cache = ["sccache"]', '"--push"'):
            require(fragment in activation, f"Docker plan activation changed: {fragment}")
        upstream = (ROOT / "upstream/.github/workflows/build-container-image.yml").read_text()
        for fragment in ("- linux/amd64", "- linux/arm64", "file: ${{ inputs.file_to_build }}", "MASTODON_VERSION_PRERELEASE", "MASTODON_VERSION_METADATA", "SOURCE_COMMIT", "push-by-digest=true"):
            require(fragment in upstream, f"upstream image workflow changed: {fragment}")
        caller = (ROOT / "upstream/.github/workflows/build-nightly.yml").read_text()
        require("file_to_build: Dockerfile" in caller and "file_to_build: streaming/Dockerfile" in caller, "nightly workload selection changed")
        action = (ROOT / ".github/actions/mastodon-docker-benchmark/action.yml").read_text()
        require("inputs.workload == 'server' && 'upstream/Dockerfile'" in action, "server baseline no longer uses upstream Dockerfile")
        require("'upstream/streaming/Dockerfile'" in action, "streaming plan changed")
        require(action.count("SOURCE_COMMIT=${{ steps.scope.outputs.source_sha }}") == 1, "Actions/cache commit arg drifted")
        require(action.count("Activate the BoringCache Docker plan") == 1, "BoringCache plan activation drifted")
    except (KeyError, OSError, RuntimeError, tomllib.TOMLDecodeError) as error:
        print(f"Mastodon recipe mismatch: {error}", file=sys.stderr)
        return 1
    print("Verified Mastodon server/streaming amd64 plans.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
