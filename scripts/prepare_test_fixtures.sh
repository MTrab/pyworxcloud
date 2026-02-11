#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/code-ref/data-samples"
DST_DIR="${ROOT_DIR}/tests/fixtures/data-samples"

mkdir -p "${DST_DIR}"

if [[ -d "${SRC_DIR}" ]]; then
  find "${SRC_DIR}" -type f -name "*.json" -exec cp "{}" "${DST_DIR}/" \;
fi
