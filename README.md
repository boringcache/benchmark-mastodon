# benchmark-mastodon

Isolated Mastodon benchmark runner for BoringCache vs GitHub Actions cache.

This repo exists separately from the central benchmarks publisher so Mastodon can have:

- a pinned upstream source commit
- isolated GitHub Actions cache usage
- one shared BoringCache workspace name: `boringcache/benchmarks`
- independent benchmark runs triggered by upstream sync commits and manual dispatches

## Source Model

- upstream app source lives in the pinned `upstream/` submodule
- workflows build the upstream Dockerfile with `upstream/` as the Docker context

Pinned upstream source:

- see committed `upstream/` submodule on `main`

## Scenarios

- `cold`
- `warm1`
- `layer_miss`

BoringCache uses the outer BuildKit registry/OCI cache path only. It does not call BoringCache inside Dockerfile `RUN` steps, and upstream Dockerfile cache mounts stay native to BuildKit.

## Output

Each workflow uploads machine-readable JSON and Markdown summaries. Those artifacts are intended to be ingested by the central `boringcache/benchmarks` publisher later.

## Token Model

This repo uses split BoringCache tokens as the standard CI shape:

- `BORINGCACHE_RESTORE_TOKEN` for read-only restore and proxy access
- `BORINGCACHE_SAVE_TOKEN` for trusted write paths
- `BORINGCACHE_API_TOKEN` only where a single bearer variable is still required for compatibility
