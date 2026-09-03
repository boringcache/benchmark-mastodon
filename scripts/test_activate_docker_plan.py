#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ActivateDockerPlanTest(unittest.TestCase):
    def activate(self, *, workload: str, tool_cache: str, push: str) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / ".boringcache.toml"
            plan.write_text((ROOT / ".boringcache.toml").read_text())
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "activate-docker-plan.py"),
                    "--workload",
                    workload,
                    "--tool-cache",
                    tool_cache,
                    "--source-sha",
                    "a" * 40,
                    "--prerelease",
                    "nightly.2026-09-03",
                    "--push",
                    push,
                    "--image",
                    "ghcr.io/acme/mastodon:boringcache",
                    "--plan",
                    str(plan),
                ],
                check=True,
            )
            return tomllib.loads(plan.read_text())

    def test_server_sccache_publication_is_a_direct_cli_plan(self) -> None:
        docker = self.activate(workload="server", tool_cache="true", push="true")["adapters"]["docker"]
        self.assertEqual(docker["command"][:3], ["docker", "buildx", "build"])
        self.assertEqual(docker["tool-cache"], ["sccache"])
        self.assertIn("scenarios/mastodon-sccache/Dockerfile", docker["command"])
        self.assertIn("ghcr.io/acme/mastodon:boringcache", docker["command"])
        self.assertIn("--push", docker["command"])

    def test_streaming_keeps_the_plain_local_plan(self) -> None:
        docker = self.activate(workload="streaming", tool_cache="false", push="false")["adapters"]["docker"]
        self.assertNotIn("tool-cache", docker)
        self.assertIn("upstream/streaming/Dockerfile", docker["command"])
        self.assertIn("mastodon-streaming-benchmark:local", docker["command"])
        self.assertNotIn("--push", docker["command"])


if __name__ == "__main__":
    unittest.main()
