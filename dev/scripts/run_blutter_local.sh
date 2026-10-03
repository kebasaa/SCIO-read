#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "$0")/../.." && pwd)"
task_private="$task_root/dev/private"
task_prefix="$task_private/native_prefix/usr"
export PATH="$task_prefix/bin:$PATH"
export LD_LIBRARY_PATH="$task_prefix/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export PYTHONPATH="$task_prefix/lib/python3/dist-packages:${PYTHONPATH:-}"
export PYTHONDONTWRITEBYTECODE=1
export PKG_CONFIG_SYSROOT_DIR="$task_private/native_prefix"
export PKG_CONFIG_LIBDIR="$task_prefix/lib/x86_64-linux-gnu/pkgconfig:$task_prefix/share/pkgconfig"
export CMAKE_PREFIX_PATH="$task_prefix"
export ICU_ROOT="$task_prefix"
export TMPDIR="$task_private/tmp"
mkdir -p "$TMPDIR"
cd "$task_private/blutter"
python3 blutter.py "$task_private/flutter_1_5_6_arm64" "$task_private/flutter_1_5_6_analysis_native_v3" --rebuild
