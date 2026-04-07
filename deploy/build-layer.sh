#!/bin/bash
# Build Lambda layer for a gateway target and upload to S3
# Usage: ./build-layer.sh <target-name> <s3-bucket> [region]
# Example: ./build-layer.sh global-knowledge my-techbot-bucket us-west-2

set -euo pipefail

TARGET_NAME="${1:?Usage: $0 <target-name> <s3-bucket> [region]}"
S3_BUCKET="${2:?Usage: $0 <target-name> <s3-bucket> [region]}"
REGION="${3:-us-west-2}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET_DIR="${SCRIPT_DIR}/targets/${TARGET_NAME}"
REQUIREMENTS="${TARGET_DIR}/requirements.txt"

if [ ! -f "$REQUIREMENTS" ]; then
    echo "❌ requirements.txt not found: $REQUIREMENTS"
    exit 1
fi

WORK_DIR=$(mktemp -d)
trap "rm -rf $WORK_DIR" EXIT

echo "📦 Building layer for target: ${TARGET_NAME}"

# Install dependencies into layer structure
pip install -r "$REQUIREMENTS" \
    --target "$WORK_DIR/python" \
    --platform manylinux2014_aarch64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --no-deps 2>/dev/null || \
pip install -r "$REQUIREMENTS" \
    --target "$WORK_DIR/python" \
    --platform manylinux2014_aarch64 \
    --implementation cp \
    --python-version 3.12

# Create zip
ZIP_FILE="${SCRIPT_DIR}/${TARGET_NAME}-layer.zip"
cd "$WORK_DIR"
zip -r "$ZIP_FILE" python/ -q

echo "📤 Uploading to s3://${S3_BUCKET}/${TARGET_NAME}-layer.zip"
aws s3 cp "$ZIP_FILE" "s3://${S3_BUCKET}/${TARGET_NAME}-layer.zip" --region "$REGION"

echo "✅ Layer uploaded: s3://${S3_BUCKET}/${TARGET_NAME}-layer.zip"
echo "   Size: $(du -h "$ZIP_FILE" | cut -f1)"

rm -f "$ZIP_FILE"
