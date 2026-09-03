#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dockerfile="${repo_root}/upstream/Dockerfile"
fixture_dockerfile="${repo_root}/scenarios/mastodon-sccache/Dockerfile"
expected_dockerfile="$(mktemp)"
write_fixture=false
trap 'rm -f "$expected_dockerfile"' EXIT

if [[ "${1:-}" == "--write" ]]; then
  write_fixture=true
fi

awk '
  BEGIN {
    in_media_build = 0
    media_sccache_arg = 0
    media_sccache_deps = 0
    media_sccache_install = 0
    libvips_setup = 0
    libvips_compile = 0
    in_ffmpeg = 0
    ffmpeg_workdir = 0
    skipping_ffmpeg_run = 0
    ffmpeg_compile = 0
    in_ruby_build = 0
    ruby_build_apt_update = 0
    ruby_sccache_copy = 0
  }

  skipping_ffmpeg_run {
    if ($0 == "  make install;") {
      print "RUN --mount=type=secret,id=boringcache-tool-cache-env,required=false \\"
      print "  if [ -f /run/secrets/boringcache-tool-cache-env ]; then \\"
      print "    . /run/secrets/boringcache-tool-cache-env; \\"
      print "    export SCCACHE_SERVER_PORT=42262; \\"
      print "    export SCCACHE_ERROR_LOG=/tmp/boringcache-sccache-ffmpeg.log; \\"
      print "    sccache --start-server || true; \\"
      print "  fi; \\"
      print "  configure_compiler_args=(); \\"
      print "  if [ -n \"${CC:-}\" ]; then \\"
      print "    configure_compiler_args+=(--cc=\"$CC\"); \\"
      print "  fi; \\"
      print "  if [ -n \"${CXX:-}\" ]; then \\"
      print "    configure_compiler_args+=(--cxx=\"$CXX\"); \\"
      print "  fi; \\"
      print "  ./configure \\"
      print "  \"${configure_compiler_args[@]}\" \\"
      print "  --prefix=/usr/local/ffmpeg \\"
      print "  --toolchain=hardened \\"
      print "  --disable-debug \\"
      print "  --disable-devices \\"
      print "  --disable-doc \\"
      print "  --disable-ffplay \\"
      print "  --disable-network \\"
      print "  --disable-static \\"
      print "  --enable-ffmpeg \\"
      print "  --enable-ffprobe \\"
      print "  --enable-gpl \\"
      print "  --enable-libdav1d \\"
      print "  --enable-libmp3lame \\"
      print "  --enable-libopus \\"
      print "  --enable-libsnappy \\"
      print "  --enable-libvorbis \\"
      print "  --enable-libvpx \\"
      print "  --enable-libwebp \\"
      print "  --enable-libx264 \\"
      print "  --enable-libx265 \\"
      print "  --enable-shared \\"
      print "  --enable-version3 \\"
      print "  ; \\"
      print "  make -j\"$(nproc)\"; \\"
      print "  make install; \\"
      print "  if [ -f /run/secrets/boringcache-tool-cache-env ]; then \\"
      print "    echo BEGIN_BORINGCACHE_SCCACHE_STATS; \\"
      print "    sccache --show-stats; \\"
      print "    echo END_BORINGCACHE_SCCACHE_STATS; \\"
      print "  fi"
      skipping_ffmpeg_run = 0
      ffmpeg_compile += 1
    }
    next
  }

  /^FROM / {
    in_media_build = 0
    in_ruby_build = 0
  }

  /^FROM ruby AS ruby-build$/ {
    in_ruby_build = 1
    print
    print ""
    print "# Keep Ruby native extension builds compatible with Ruby images whose compiler config invokes sccache."
    print "COPY --from=media-build /usr/local/bin/sccache /usr/local/bin/sccache"
    ruby_sccache_copy += 1
    next
  }

  /^FROM .* AS media-build$/ {
    in_media_build = 1
    print
    next
  }

  in_media_build && $0 == "ARG TARGETPLATFORM" {
    print
    print "ARG SCCACHE_VERSION=v0.14.0"
    media_sccache_arg += 1
    next
  }

  in_media_build && $0 == "  build-essential \\" {
    print
    print "  ca-certificates \\"
    print "  curl \\"
    media_sccache_deps += 1
    next
  }

  in_media_build && $0 == "  ;" && media_sccache_install == 0 {
    print
    print ""
    print "RUN set -eux; \\"
    print "  arch=\"$(dpkg --print-architecture)\"; \\"
    print "  case \"$arch\" in \\"
    print "    amd64) sccache_arch=\"x86_64\" ;; \\"
    print "    arm64) sccache_arch=\"aarch64\" ;; \\"
    print "    *) echo \"unsupported sccache architecture: ${arch}\" >&2; exit 1 ;; \\"
    print "  esac; \\"
    print "  curl -fsSL \"https://github.com/mozilla/sccache/releases/download/${SCCACHE_VERSION}/sccache-${SCCACHE_VERSION}-${sccache_arch}-unknown-linux-musl.tar.gz\" | tar xz -C /tmp; \\"
    print "  mv \"/tmp/sccache-${SCCACHE_VERSION}-${sccache_arch}-unknown-linux-musl/sccache\" /usr/local/bin/sccache; \\"
    print "  chmod +x /usr/local/bin/sccache; \\"
    print "  sccache --version"
    media_sccache_install += 1
    next
  }

  in_ruby_build && $0 == "  # Install build tools and bundler dependencies from APT" {
    print
    print "  apt-get update; \\"
    ruby_build_apt_update += 1
    next
  }

  $0 == "RUN meson setup build --prefix /usr/local/libvips --libdir=lib -Ddeprecated=false -Dintrospection=disabled -Dmodules=disabled -Dexamples=false" {
    print "RUN --mount=type=secret,id=boringcache-tool-cache-env,required=false \\"
    print "  if [ -f /run/secrets/boringcache-tool-cache-env ]; then \\"
    print "    . /run/secrets/boringcache-tool-cache-env; \\"
    print "    export SCCACHE_SERVER_PORT=42261; \\"
    print "  fi; \\"
    print "  meson setup build --prefix /usr/local/libvips --libdir=lib -Ddeprecated=false -Dintrospection=disabled -Dmodules=disabled -Dexamples=false"
    libvips_setup += 1
    next
  }

  $0 == "RUN ninja && ninja install" {
    print "RUN --mount=type=secret,id=boringcache-tool-cache-env,required=false \\"
    print "  if [ -f /run/secrets/boringcache-tool-cache-env ]; then \\"
    print "    . /run/secrets/boringcache-tool-cache-env; \\"
    print "    export SCCACHE_SERVER_PORT=42261; \\"
    print "    export SCCACHE_ERROR_LOG=/tmp/boringcache-sccache-libvips.log; \\"
    print "    sccache --start-server || true; \\"
    print "  fi; \\"
    print "  ninja && ninja install; \\"
    print "  if [ -f /run/secrets/boringcache-tool-cache-env ]; then \\"
    print "    echo BEGIN_BORINGCACHE_SCCACHE_STATS; \\"
    print "    sccache --show-stats; \\"
    print "    echo END_BORINGCACHE_SCCACHE_STATS; \\"
    print "  fi"
    libvips_compile += 1
    next
  }

  /^FROM .* AS ffmpeg$/ {
    in_ffmpeg = 1
    print
    next
  }

  in_ffmpeg && $0 == "WORKDIR /usr/local/ffmpeg/src/ffmpeg-${FFMPEG_VERSION}" {
    ffmpeg_workdir = 1
    print
    next
  }

  ffmpeg_workdir && $0 == "RUN \\" {
    skipping_ffmpeg_run = 1
    ffmpeg_workdir = 0
    next
  }

  { print }

  END {
    if (media_sccache_arg != 1 ||
        media_sccache_deps != 1 ||
        media_sccache_install != 1 ||
        ruby_build_apt_update != 1 ||
        ruby_sccache_copy != 1 ||
        libvips_setup != 1 ||
        libvips_compile != 1 ||
        ffmpeg_compile != 1) {
      printf "unexpected Mastodon sccache Dockerfile hook count: arg=%d deps=%d install=%d ruby_build_apt_update=%d ruby_sccache_copy=%d libvips_setup=%d libvips_compile=%d ffmpeg_compile=%d\n",
        media_sccache_arg,
        media_sccache_deps,
        media_sccache_install,
        ruby_build_apt_update,
        ruby_sccache_copy,
        libvips_setup,
        libvips_compile,
        ffmpeg_compile > "/dev/stderr"
      exit 1
    }
  }
' "$upstream_dockerfile" > "$expected_dockerfile"

if [[ "$write_fixture" == "true" ]]; then
  mkdir -p "$(dirname "$fixture_dockerfile")"
  cp "$expected_dockerfile" "$fixture_dockerfile"
fi

if ! diff -u "$expected_dockerfile" "$fixture_dockerfile"; then
  echo "scenarios/mastodon-sccache/Dockerfile is out of sync with upstream/Dockerfile plus the static sccache hook." >&2
  echo "Regenerate the fixture from the pinned upstream Dockerfile with scripts/check-mastodon-sccache-dockerfile.sh --write." >&2
  exit 1
fi
