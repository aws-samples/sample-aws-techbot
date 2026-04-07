#!/bin/bash
# Build and upload all gateway target Lambda layers + code to both S3 buckets
# Usage: ./build-and-upload.sh

set -euo pipefail

BUCKETS=(
    "haomiaoj-yuzeli-aws-techbot-us-west-2:us-west-2"
    "haomiaoj-yuzeli-aws-techbot-us-east-1:us-east-1"
)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGETS_DIR="${SCRIPT_DIR}/targets"
TARGETS=(global-knowledge china-knowledge customer-stories pricing)

for TARGET_NAME in "${TARGETS[@]}"; do
    TARGET_DIR="${TARGETS_DIR}/${TARGET_NAME}"
    REQUIREMENTS="${TARGET_DIR}/requirements.txt"

    if [ ! -d "$TARGET_DIR" ]; then
        echo "⚠️  Skipping ${TARGET_NAME}: directory not found"
        continue
    fi

    echo ""
    echo "=========================================="
    echo "📦 Building: ${TARGET_NAME}"
    echo "=========================================="

    # --- Build layer ---
    LAYER_ZIP="/tmp/${TARGET_NAME}-layer.zip"
    if [ -f "$REQUIREMENTS" ]; then
        WORK_DIR=$(mktemp -d)

        echo "📥 Installing dependencies..."
        pip3 install -r "$REQUIREMENTS" \
            --target "$WORK_DIR/python" \
            --python-version 3.12 \
            --only-binary=:all: 2>/dev/null || \
        pip3 install -r "$REQUIREMENTS" \
            --target "$WORK_DIR/python"

        cd "$WORK_DIR"
        zip -r "$LAYER_ZIP" python/ -q
        cd "$SCRIPT_DIR"
        echo "   Layer size: $(du -h "$LAYER_ZIP" | cut -f1)"

        rm -rf "$WORK_DIR"
    fi

    # --- Package code ---
    CODE_ZIP="/tmp/${TARGET_NAME}-code.zip"
    cd "$TARGET_DIR"
    zip -j "$CODE_ZIP" index.py -q
    cd "$SCRIPT_DIR"

    # --- Upload to all buckets ---
    for BUCKET_ENTRY in "${BUCKETS[@]}"; do
        S3_BUCKET="${BUCKET_ENTRY%%:*}"
        REGION="${BUCKET_ENTRY##*:}"

        if [ -f "$LAYER_ZIP" ]; then
            echo "📤 Uploading layer → s3://${S3_BUCKET}/${TARGET_NAME}-layer.zip (${REGION})"
            aws s3 cp "$LAYER_ZIP" "s3://${S3_BUCKET}/${TARGET_NAME}-layer.zip" --region "$REGION"
        fi

        echo "📤 Uploading code  → s3://${S3_BUCKET}/${TARGET_NAME}-code.zip (${REGION})"
        aws s3 cp "$CODE_ZIP" "s3://${S3_BUCKET}/${TARGET_NAME}-code.zip" --region "$REGION"
    done

    rm -f "$LAYER_ZIP" "$CODE_ZIP"
    echo "✅ ${TARGET_NAME} done"
done

# ===========================================
# Upload worker.zip and template.yaml
# ===========================================
echo ""
echo "=========================================="
echo "📦 Packaging: worker + template"
echo "=========================================="

# --- Worker Lambda ---
WORKER_ZIP="/tmp/worker.zip"
cd "${SCRIPT_DIR}/worker"
zip -j "$WORKER_ZIP" index.py -q
cd "$SCRIPT_DIR"

# --- Upload worker.zip + template.yaml to all buckets ---
for BUCKET_ENTRY in "${BUCKETS[@]}"; do
    S3_BUCKET="${BUCKET_ENTRY%%:*}"
    REGION="${BUCKET_ENTRY##*:}"

    echo "📤 Uploading worker.zip  → s3://${S3_BUCKET}/worker.zip (${REGION})"
    aws s3 cp "$WORKER_ZIP" "s3://${S3_BUCKET}/worker.zip" --region "$REGION"

    echo "📤 Uploading template.yaml → s3://${S3_BUCKET}/template.yaml (${REGION})"
    aws s3 cp "${SCRIPT_DIR}/template.yaml" "s3://${S3_BUCKET}/template.yaml" --region "$REGION"
done

rm -f "$WORKER_ZIP"
echo "✅ worker + template done"

echo ""
echo "=========================================="
echo "✅ All artifacts uploaded to both buckets"
echo "=========================================="
