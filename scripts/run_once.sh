#!/bin/zsh
set -eu

cd "$(dirname "$0")/.."
export PYTHONPYCACHEPREFIX="${TMPDIR:-/private/tmp}/trend_commerce_pycache"

python3 -m trend_commerce collect
python3 -m trend_commerce run
python3 -m trend_commerce social-dispatch
python3 -m trend_commerce report
