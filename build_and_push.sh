#!/usr/bin/env bash
set -e

if [ $# -ne 1 ]; then
    echo "Usage: build_and_push.sh <version_tag>" >&2
    exit 1
fi

REPO="kasbench/kasbench-load-generator"
TAG=$1

docker buildx build \
 --platform linux/amd64,linux/arm64 \
 --tag "${REPO}:${TAG}" \
 --tag "${REPO}:latest" \
 --push \
 . 
 
