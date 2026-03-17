# benchmark-mastodon

Isolated Mastodon benchmark runner for BoringCache vs GitHub Actions cache.

This repo exists separately from the central benchmarks publisher so Mastodon can have:

- a pinned upstream source commit
- isolated GitHub Actions cache usage
- isolated BoringCache workspace usage
- independent nightly benchmark runs

## Source Model

- upstream app source lives in the pinned `upstream/` submodule
- `Dockerfile.benchmark` is benchmark-owned and committed here
- stale scenarios are committed patches in `scenarios/`

Pinned upstream source:

- `mastodon/mastodon@919b1e69b84f1f11376f8ff370f5c5fc7dd7ec9c`

## Scenarios

- `cold`
- `warm1`
- `warm2`
- `stale-low`: one Ruby source file change
- `stale-mid`: one `Gemfile` metadata change
- `layer-miss`: `--no-cache` Docker rebuild on the same pinned tree

## Output

Each workflow uploads machine-readable JSON and Markdown summaries. Those artifacts are intended to be ingested by the central `boringcache/benchmarks` publisher later.
