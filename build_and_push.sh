#!/usr/bin/env bash
set -e

if [ $# -ne 2 ]; then
    echo "Usage: build_and_push.sh <repository> <version_tag>" >&2
    exit 1
fi

REPO=$1
TAG=$2

docker buildx build \
 --platform linux/amd64,linux/arm64 \
 --tag "${REPO}:${TAG}" \
 --tag "${REPO}:latest \
 --push \
 . || { echo "Error: Docker build failed" >&2; exit 1; }

# docker push "${REPO}:${TAG}" || { echo "Error: Docker push failed" >&2; exit 1; }
