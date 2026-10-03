#!/usr/bin/env bash
# Local dependency overlay only; never apt install or modify the system prefix.
set -euo pipefail
task_root="$(cd "$(dirname "$0")/../.." && pwd)"
task_private="$task_root/dev/private"
mkdir -p "$task_private/native_debs" "$task_private/native_prefix"
cd "$task_private/native_debs"
apt-get download libicu-dev libicu74 libcapstone-dev libcapstone4 ninja-build pkgconf pkgconf-bin libpkgconf3 python3-pyelftools
for task_deb in ./*.deb; do
    dpkg-deb -x "$task_deb" "$task_private/native_prefix"
done
sha256sum ./*.deb
