#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/code-ref/data-samples"
DST_DIR="${ROOT_DIR}/tests/fixtures/data-samples"

rm -rf "${DST_DIR}"
mkdir -p "${DST_DIR}"

if [[ -d "${SRC_DIR}" ]]; then
  (
    cd "${SRC_DIR}"
    find . -type f -name "*.json" | while read -r file; do
      mkdir -p "${DST_DIR}/$(dirname "${file}")"
      cp "${file}" "${DST_DIR}/${file}"
    done
  )
fi
