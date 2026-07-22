# benchmark-mastodon

Isolated Mastodon benchmark runner for BoringCache vs GitHub Actions cache.

This repo exists separately from the central benchmarks publisher so Mastodon can have:

- a pinned upstream source commit
- isolated GitHub Actions cache usage
- one per-repo BoringCache workspace name: `boringcache/benchmark-mastodon`
- independent benchmark runs triggered by upstream sync commits and manual dispatches

## Source Model

- upstream app source lives in the pinned `upstream/` submodule
- workflows build the upstream Dockerfile with `upstream/` as the Docker context

Pinned upstream source:

- see committed `upstream/` submodule on `main`

## Scenarios

- `cold`
- `warm1`

Fresh lane runs a no-prior-cache cold build plus one warm rerun on the same pinned source tree. Rolling lane records the upstream commit build as-is after each upstream sync against the prior rolling cache and skips `warm1`.

The benchmark has two Docker surfaces:

- `mastodon-docker`: main Mastodon image from
  `scenarios/mastodon-sccache/Dockerfile`, generated from
  `upstream/Dockerfile` plus the static optional `sccache` secret contract used
  by Docker tool-cache lanes.
- `mastodon-streaming`: streaming service image from `upstream/streaming/Dockerfile`.

Rolling dispatch runs the combined main Docker benchmark and the streaming Docker pair on every upstream sync commit. The retired dependency-directory package-CAS benchmark set has been removed.

BoringCache uses its managed BuildKit backend as the single product lane and compares it with GitHub Actions Cache. The main Docker benchmark also runs a managed BuildKit + `sccache` composition because Mastodon's main image compiles libvips and FFmpeg from source. The `sccache` hook is static in the measured Dockerfile and optional at runtime, so tool-cache lanes do not mutate Docker build args or the Dockerfile graph. Upstream Dockerfile cache mounts remain owned by BuildKit.

The main Docker workflow is [`.github/workflows/mastodon-docker-benchmark.yml`](.github/workflows/mastodon-docker-benchmark.yml), which runs GitHub Actions Cache, BoringCache managed BuildKit, and the explicit managed BuildKit + `sccache` composition side by side. The streaming workflow intentionally has no Docker tool-cache lane; its Dockerfile is Node/Yarn work rather than a stable C/C++ compiler-cache target.

## Output

Each workflow uploads machine-readable JSON and Markdown summaries. Those artifacts are intended to be ingested by the central `boringcache/benchmarks` publisher later.

## Token Model

This repo uses split BoringCache tokens as the standard CI shape:

- `BORINGCACHE_RESTORE_TOKEN` for read-only restore and proxy access
- `BORINGCACHE_SAVE_TOKEN` for trusted write paths
- `BORINGCACHE_API_TOKEN` only where a single bearer variable is still required for compatibility
