#!/usr/bin/env python3
"""Select and verify the real dependency update used by this experiment."""

import json
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "upstream"
evidence = Path(os.environ["RUNNER_TEMP"]) / "prepared-evidence"
revisions = {
    "parent": "6e47e18dfc29987a39e6ea4d7c179623d67e7238",
    "child": "224cbcd869987295d6a4902419b900091f1a8865",
}
versions = {
    "parent": {"react-intl": "10.1.20", "intl-messageformat": "11.2.13"},
    "child": {"react-intl": "10.2.2", "intl-messageformat": "11.2.15"},
}
operation, role = sys.argv[1:]
assert role in revisions, "unknown preparation role"

if operation == "select":
    subprocess.run(
        ["git", "fetch", "--depth=1", "origin", revisions[role]], cwd=source, check=True
    )
    subprocess.run(
        ["git", "checkout", "--detach", revisions[role]], cwd=source, check=True
    )
elif operation == "verify":
    actual = {}
    for name, expected in versions[role].items():
        actual[name] = json.loads(
            (source / "node_modules" / name / "package.json").read_text()
        )["version"]
        assert actual[name] == expected, (
            f"installed {name} differs from selected revision"
        )
    evidence.mkdir(exist_ok=True)
    (evidence / f"installed-{role}.json").write_text(
        json.dumps(actual, indent=2) + "\n"
    )
    print(json.dumps(actual))
elif operation == "handoff":
    actual_revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source, text=True
    ).strip()
    assert actual_revision == revisions[role], "prepared source differs"
    manifest = json.loads(
        (
            Path(os.environ["RUNNER_TEMP"])
            / "mastodon-prepared/state/deps/manifest.json"
        ).read_text()
    )
    envelope = {
        "schema": 1,
        "repository": "boringcache/benchmark-mastodon",
        "harness_revision": os.environ["GITHUB_SHA"],
        "source_revision": revisions[role],
        "role": role,
        "producer_run": os.environ["GITHUB_RUN_ID"],
        "producer_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "tag": f"mastodon-refresh-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-{role}",
        "compatibility": {
            k: manifest[k]
            for k in ("image_version", "host", "machine", "state_path", "source_path")
        },
        "inputs": manifest["inputs"],
        "checks": [
            "assets:precompile",
            "db:setup",
            "account/status/media_attachment specs",
            "test:js",
        ],
    }
    (evidence / "handoff.json").write_text(json.dumps(envelope, indent=2) + "\n")
elif operation == "receive":
    envelope = json.loads(
        (Path(os.environ["RUNNER_TEMP"]) / "handoff/handoff.json").read_text()
    )
    assert (
        envelope["schema"] == 1
        and envelope["repository"] == "boringcache/benchmark-mastodon"
    )
    assert envelope["harness_revision"] == os.environ["GITHUB_SHA"], (
        "handoff harness differs"
    )
    assert envelope["source_revision"] == revisions[role] and envelope["role"] == role
    assert envelope["producer_run"] == os.environ["PREPARED_PRODUCER_RUN"]
    assert envelope["producer_attempt"] == os.environ["PREPARED_PRODUCER_ATTEMPT"]
    expected_tag = f"mastodon-refresh-{os.environ['PREPARED_PRODUCER_RUN']}-{os.environ['PREPARED_PRODUCER_ATTEMPT']}-{role}"
    assert envelope["tag"] == expected_tag, "handoff tag differs"
    assert envelope["compatibility"]["image_version"] == os.environ["ImageVersion"], (
        "handoff runner image differs"
    )
    assert envelope["compatibility"]["host"] == Path("/etc/os-release").read_text()
    assert envelope["compatibility"]["machine"] == os.uname().machine
    assert envelope["compatibility"]["source_path"] == str(source)
    assert envelope["compatibility"]["state_path"] == str(
        Path(os.environ["RUNNER_TEMP"]) / "mastodon-prepared/state"
    )
    evidence.mkdir(exist_ok=True)
    (evidence / "received-handoff.json").write_text(
        json.dumps(envelope, indent=2) + "\n"
    )
else:
    raise SystemExit(
        "usage: prepared-refresh.py select|verify|handoff|receive parent|child"
    )
