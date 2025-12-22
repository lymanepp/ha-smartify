#!/usr/bin/env bash

set -e

cd "$(dirname "$0")/.."

#sudo python -m pip install -e .
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-test.txt

sudo -n apt-get update
sudo -n apt-get install -y --no-install-recommends ffmpeg libturbojpeg0 libpcap0.8

#git config --global --add safe.directory "$PWD"

#python -m pip install pre-commit
#pre-commit install --install-hooks
