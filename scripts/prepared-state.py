#!/usr/bin/env python3
"""Mastodon-specific capture and activation for the prepared-state experiment."""

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / "upstream"
state = Path(os.environ["RUNNER_TEMP"]) / "mastodon-prepared/state"
evidence = Path(os.environ["RUNNER_TEMP"]) / "prepared-evidence"
operation = sys.argv[1]


def output(*args):
    return subprocess.check_output(args, text=True, cwd=source).strip()


def inputs():
    names = [
        "Gemfile",
        "Gemfile.lock",
        "package.json",
        "yarn.lock",
        ".ruby-version",
        ".nvmrc",
        ".yarnrc.yml",
        "streaming/package.json",
    ]
    names += [
        str(p.relative_to(source))
        for p in sorted((source / ".yarn/patches").glob("*"))
        if p.is_file()
    ]
    return {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in names
    }


def exports(values, paths):
    for value in [*values.values(), *paths]:
        assert "\n" not in str(value) and "\r" not in str(value)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.writelines(f"{key}={value}\n" for key, value in values.items())
    with open(os.environ["GITHUB_PATH"], "a") as stream:
        stream.writelines(f"{path}\n" for path in paths)


if operation == "plan":
    tag = "mastodon-prepared-" + os.environ["GITHUB_RUN_ID"]
    config = root / ".boringcache.toml"
    with config.open("a") as stream:
        for name, path in [("dependencies", state / "deps"), ("environment", state)]:
            stream.write(
                f'\n[entries.prepared-{name}]\ntag = "{tag}-{name}"\npath = "{path}"\n\n[profiles.prepared-{name}]\nentries = ["prepared-{name}"]\n'
            )
    state.parent.mkdir(exist_ok=True)
elif operation == "capture":
    state.mkdir()
    deps = state / "deps"
    deps.mkdir()
    for name, origin in [
        ("bundle", source / "vendor/bundle"),
        ("node_modules", source / "node_modules"),
        ("streaming_node_modules", source / "streaming/node_modules"),
        ("yarn", source / ".yarn"),
        ("corepack", Path.home() / ".cache/node/corepack"),
    ]:
        if origin.exists():
            shutil.copytree(origin, deps / name, symlinks=True)
    assert (deps / "bundle").is_dir() and (deps / "node_modules").is_dir()
    manifest = {
        "inputs": inputs(),
        "image_version": os.environ["ImageVersion"],
        "state_path": str(state),
        "source_path": str(source),
        "host": Path("/etc/os-release").read_text(),
        "machine": os.uname().machine,
    }
    (deps / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    runtime = state / "runtime"
    runtime.mkdir()
    ruby = Path(
        output("ruby", "-rrbconfig", "-e", 'puts RbConfig::CONFIG.fetch("prefix")')
    )
    node_binary = shutil.which("node")
    assert node_binary, "Node executable missing"
    node = Path(node_binary).resolve().parent.parent
    shutil.copytree(ruby, runtime / "ruby", symlinks=True)
    shutil.copytree(node, runtime / "node", symlinks=True)
    packages = state / "packages"
    packages.mkdir()
    before = dict(
        line.split("\t", 1)
        for line in (evidence / "packages-before.tsv").read_text().splitlines()
    )
    installed = dict(
        line.split("\t", 1)
        for line in output(
            "dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"
        ).splitlines()
    )
    selected = {
        name: version
        for name, version in installed.items()
        if before.get(name) != version
    }
    if selected:
        subprocess.run(
            [
                "apt-get",
                "download",
                *[f"{name}={version}" for name, version in sorted(selected.items())],
            ],
            cwd=packages,
            check=True,
        )
    (state / "packages.json").write_text(json.dumps(selected, indent=2) + "\n")
    subprocess.run(
        ["du", "-sb", str(deps), str(runtime), str(packages)],
        check=True,
        stdout=(evidence / "state-sizes.txt").open("w"),
    )
    print(
        f"Captured dependencies, runtimes, and {len(selected)} exact package payloads"
    )
elif operation == "activate":
    variant = os.environ["PREPARED_VARIANT"]
    deps = state / "deps"
    manifest = json.loads((deps / "manifest.json").read_text())
    assert manifest["inputs"] == inputs(), "preparation inputs differ"
    assert manifest["image_version"] == os.environ["ImageVersion"], (
        "runner image differs"
    )
    assert (
        manifest["host"] == Path("/etc/os-release").read_text()
        and manifest["machine"] == os.uname().machine
    )
    assert manifest["state_path"] == str(state) and manifest["source_path"] == str(
        source
    ), "installation paths differ"
    values = {
        "BUNDLE_PATH": str(source / "vendor/bundle"),
        "BUNDLE_FROZEN": "true",
        "BUNDLE_DEPLOYMENT": "true",
        "BUNDLE_WITH": "test",
        "COREPACK_HOME": str(deps / "corepack"),
    }
    paths = []
    if variant == "environment":
        packages = sorted((state / "packages").glob("*.deb"))
        expected_packages = json.loads((state / "packages.json").read_text())
        assert len(packages) == len(expected_packages), (
            "system package payloads missing"
        )
        if packages:
            subprocess.run(
                [
                    "sudo",
                    "dpkg",
                    "--force-confold",
                    "--install",
                    *[str(p) for p in packages],
                ],
                check=True,
            )
        wrappers = state.parent / "bin"
        wrappers.mkdir()
        ruby = state / "runtime/ruby"
        ruby_dirs = sorted((ruby / "lib/ruby").glob("[0-9]*"))
        assert len(ruby_dirs) == 1
        ruby_libraries = [ruby_dirs[0], *ruby_dirs[0].glob("*linux*")]

        def wrapper(name, argv):
            path = wrappers / name
            path.write_text(
                "#!/bin/sh\nexec " + shlex.join([str(a) for a in argv]) + ' "$@"\n'
            )
            path.chmod(0o755)

        wrapper(
            "ruby",
            [
                "env",
                f"LD_LIBRARY_PATH={ruby}/lib",
                "RUBYLIB=" + ":".join(str(p) for p in ruby_libraries),
                ruby / "bin/ruby",
            ],
        )
        for script in sorted((ruby / "bin").iterdir()):
            if script.is_file():
                with script.open("rb") as stream:
                    shebang = stream.readline(512)
                if shebang.startswith(b"#!") and b"ruby" in shebang:
                    wrapper(script.name, [wrappers / "ruby", script])
        assert (wrappers / "bundle").is_file()
        paths = [str(state / "runtime/node/bin"), str(wrappers)]
    for name, dest in [
        ("bundle", source / "vendor/bundle"),
        ("node_modules", source / "node_modules"),
        ("streaming_node_modules", source / "streaming/node_modules"),
    ]:
        origin = deps / name
        if origin.exists():
            assert not dest.exists(), f"destination already populated: {dest}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(origin, dest)
    if (deps / "yarn").exists():
        shutil.copytree(
            deps / "yarn", source / ".yarn", dirs_exist_ok=True, symlinks=True
        )
    exports(values, paths)
    (evidence / "activation.json").write_text(
        json.dumps({"variant": variant, "exports": values, "paths": paths}, indent=2)
        + "\n"
    )
else:
    raise SystemExit("usage: prepared-state.py plan|capture|activate")
