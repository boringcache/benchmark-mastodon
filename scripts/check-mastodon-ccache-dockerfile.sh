#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
upstream_dockerfile="${repo_root}/upstream/Dockerfile"
fixture_dockerfile="${repo_root}/scenarios/mastodon-ccache/Dockerfile"
expected_dockerfile="$(mktemp)"
write_fixture=false
trap 'rm -f "$expected_dockerfile"' EXIT

if [[ "${1:-}" == "--write" ]]; then
  write_fixture=true
fi

awk '
  BEGIN {
    in_media_build = 0
    media_ccache_arg = 0
    media_ccache_deps = 0
    media_ccache_install = 0
    libvips_setup = 0
    libvips_compile = 0
    in_ffmpeg = 0
    ffmpeg_workdir = 0
    skipping_ffmpeg_run = 0
    ffmpeg_compile = 0
    in_ruby_build = 0
    ruby_build_apt_update = 0
    ruby_ccache_copy = 0
    bundler_compile = 0
  }

  skipping_ffmpeg_run {
    if ($0 == "  make install;") {
      print "RUN \\"
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
      print "  ccache --show-stats"
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
    print "# Use ccache for native extensions while keeping compiler selection in this Dockerfile."
    print "COPY --from=media-build /usr/local/bin/ccache /usr/local/bin/ccache"
    print "COPY --from=media-build /usr/local/bin/ccache-storage-http /usr/local/bin/ccache-storage-http"
    print "ENV CC=\"ccache cc\" CXX=\"ccache c++\" CCACHE_COMPILERCHECK=content"
    ruby_ccache_copy += 1
    next
  }

  /^FROM .* AS media-build$/ {
    in_media_build = 1
    print
    next
  }

  in_media_build && $0 == "ARG TARGETPLATFORM" {
    print
    print "ARG CCACHE_VERSION=4.13.6"
    print "ARG CCACHE_STORAGE_HTTP_VERSION=0.8"
    print "ENV CC=\"ccache cc\" CXX=\"ccache c++\" CCACHE_COMPILERCHECK=content"
    media_ccache_arg += 1
    next
  }

  in_media_build && $0 == "  build-essential \\" {
    print
    print "  ca-certificates \\"
    print "  curl \\"
    media_ccache_deps += 1
    next
  }

  in_media_build && $0 == "  ;" && media_ccache_install == 0 {
    print
    print ""
    print "RUN set -eux; \\"
    print "  arch=\"$(dpkg --print-architecture)\"; \\"
    print "  case \"$arch\" in \\"
    print "    amd64) ccache_arch=x86_64; helper_arch=amd64; ccache_sha=567b1b648411819590f918f045218c92da14418bdec3b30db94a3b4f5d77cf13; helper_sha=2c2cfafa39f5a4628201ccc11c81829197519159aa128fe00ea251f1f4f2461c ;; \\"
    print "    arm64) ccache_arch=aarch64; helper_arch=arm64; ccache_sha=fae67fb810e1f0d390409af6603355483572229e19183e68574cd0f851a6fb98; helper_sha=49587fb0534f5c6265fd1008267af795885f8297c6c51213708da74e4de9d475 ;; \\"
    print "    *) echo \"unsupported ccache architecture: ${arch}\" >&2; exit 1 ;; \\"
    print "  esac; \\"
    print "  ccache_archive=\"ccache-${CCACHE_VERSION}-linux-${ccache_arch}-glibc.tar.gz\"; \\"
    print "  helper_archive=\"ccache-storage-http-go-${CCACHE_STORAGE_HTTP_VERSION}-linux-${helper_arch}.tar.gz\"; \\"
    print "  curl -fsSL --retry 5 \"https://github.com/ccache/ccache/releases/download/v${CCACHE_VERSION}/${ccache_archive}\" -o \"/tmp/${ccache_archive}\"; \\"
    print "  echo \"${ccache_sha}  /tmp/${ccache_archive}\" | sha256sum --check; \\"
    print "  curl -fsSL --retry 5 \"https://github.com/ccache/ccache-storage-http-go/releases/download/v${CCACHE_STORAGE_HTTP_VERSION}/${helper_archive}\" -o \"/tmp/${helper_archive}\"; \\"
    print "  echo \"${helper_sha}  /tmp/${helper_archive}\" | sha256sum --check; \\"
    print "  tar xzf \"/tmp/${ccache_archive}\" -C /tmp; \\"
    print "  tar xzf \"/tmp/${helper_archive}\" -C /tmp; \\"
    print "  install -m 0755 \"/tmp/ccache-${CCACHE_VERSION}-linux-${ccache_arch}-glibc/ccache\" /usr/local/bin/ccache; \\"
    print "  install -m 0755 \"/tmp/ccache-storage-http-go-${CCACHE_STORAGE_HTTP_VERSION}-linux-${helper_arch}/ccache-storage-http\" /usr/local/bin/ccache-storage-http; \\"
    print "  ccache --version; \\"
    print "  helper_version=\"$(ccache-storage-http --version 2>&1 || true)\"; \\"
    print "  printf \"%s\\n\" \"$helper_version\"; \\"
    print "  printf \"%s\\n\" \"$helper_version\" | grep -F \"Version: ${CCACHE_STORAGE_HTTP_VERSION}\"; \\"
    print "  rm -rf /tmp/ccache-*"
    media_ccache_install += 1
    next
  }

  in_ruby_build && $0 == "  # Install build tools and bundler dependencies from APT" {
    print
    print "  apt-get update; \\"
    ruby_build_apt_update += 1
    next
  }

  $0 == "RUN meson setup build --prefix /usr/local/libvips --libdir=lib -Ddeprecated=false -Dintrospection=disabled -Dmodules=disabled -Dexamples=false" {
    print
    libvips_setup += 1
    next
  }

  $0 == "RUN ninja && ninja install" {
    print "RUN ninja && ninja install && ccache --show-stats"
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

  $0 == "  bundle install -j\"$(nproc)\";" {
    print "  bundle install -j\"$(nproc)\"; \\"
    print "  ccache --show-stats"
    bundler_compile += 1
    next
  }

  { print }

  END {
    if (media_ccache_arg != 1 ||
        media_ccache_deps != 1 ||
        media_ccache_install != 1 ||
        ruby_build_apt_update != 1 ||
        ruby_ccache_copy != 1 ||
        libvips_setup != 1 ||
        libvips_compile != 1 ||
        ffmpeg_compile != 1 ||
        bundler_compile != 1) {
      printf "unexpected Mastodon ccache Dockerfile hook count: arg=%d deps=%d install=%d ruby_build_apt_update=%d ruby_ccache_copy=%d libvips_setup=%d libvips_compile=%d ffmpeg_compile=%d bundler_compile=%d\\n",
        media_ccache_arg,
        media_ccache_deps,
        media_ccache_install,
        ruby_build_apt_update,
        ruby_ccache_copy,
        libvips_setup,
        libvips_compile,
        ffmpeg_compile,
        bundler_compile > "/dev/stderr"
      exit 1
    }
  }
' "$upstream_dockerfile" > "$expected_dockerfile"

if [[ "$write_fixture" == "true" ]]; then
  mkdir -p "$(dirname "$fixture_dockerfile")"
  cp "$expected_dockerfile" "$fixture_dockerfile"
fi

if ! diff -u "$expected_dockerfile" "$fixture_dockerfile"; then
  echo "scenarios/mastodon-ccache/Dockerfile is out of sync with upstream/Dockerfile plus the static ccache hook." >&2
  echo "Regenerate the fixture from the pinned upstream Dockerfile with scripts/check-mastodon-ccache-dockerfile.sh --write." >&2
  exit 1
fi
