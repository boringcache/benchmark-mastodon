#!/usr/bin/env python3
"""Record workload timing without interpreting cache telemetry."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

folder = Path(os.environ["RUNNER_TEMP"]) / "prepared-evidence"
folder.mkdir(exist_ok=True)
path = folder / "preparation.json"
if sys.argv[1] == "start":
    data = {
        "variant": os.environ["PREPARED_VARIANT"],
        "source": subprocess.check_output(
            ["git", "-C", "upstream", "rev-parse", "HEAD"], text=True
        ).strip(),
        "workflow_sha": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "runner": os.environ["RUNNER_NAME"],
        "image_version": os.environ.get("ImageVersion"),
        "host": Path("/etc/os-release").read_text(),
        "cpu_count": os.cpu_count(),
        "started_at": time.time(),
        "started_monotonic": time.monotonic(),
    }
else:
    data = json.loads(path.read_text())
    data["setup_seconds"] = time.monotonic() - data.pop("started_monotonic")
    data["ready_at"] = time.time()
    data["source_ready"] = subprocess.check_output(
        ["git", "-C", "upstream", "rev-parse", "HEAD"], text=True
    ).strip()
    data["versions"] = {
        name: subprocess.check_output(command, text=True).strip()
        for name, command in [
            ("ruby", ["ruby", "--version"]),
            ("node", ["node", "--version"]),
            ("bundle", ["bundle", "--version"]),
        ]
    }
path.write_text(json.dumps(data, indent=2) + "\n")
print(json.dumps(data))
