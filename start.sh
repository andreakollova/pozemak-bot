#!/bin/bash
cd "$(dirname "$0")"
export SSL_CERT_FILE="$(pwd)/.venv/lib/python3.13/site-packages/certifi/cacert.pem"
.venv/bin/python3 main.py
