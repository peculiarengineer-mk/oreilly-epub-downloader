#!/bin/sh
set -eu
python3 oreilly_login.py --cred "$2" "$1" 1>&2
cat "$1.epub"
