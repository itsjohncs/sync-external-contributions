#!/usr/bin/env bash

set -eu

if [[ ! ${VIRTUAL_ENV:-} =~ sync-external-contributions ]]; then
    echo "Make sure you have the virtual environment active"
    exit 1
fi

ROOT_DIR="$(realpath --relative-to="$PWD" "$(dirname "${BASH_SOURCE[0]}")")"

PYTHON_FILES=("$ROOT_DIR/main.py")
BASH_FILES=("$ROOT_DIR/lint.sh")

set -x
shfmt -i=4 -sr "${BASH_FILES[@]}"
black "${PYTHON_FILES[@]}"
