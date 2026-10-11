#!/usr/bin/env bash
#
# download_sample.sh - Download a sample of Waymo Motion Dataset TFRecord files
#
set -euo pipefail

BUCKET_BASE="gs://waymo_open_dataset_motion_v_1_3_1/uncompressed/tf_example"
DEFAULT_OUTPUT_DIR="./data"
DEFAULT_SHARDS=1
DEFAULT_SPLIT="validation"

usage() {
  cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Download a small sample of Waymo Open Dataset (Motion) TFRecord files.

Options:
  -s, --split SPLIT        Dataset split to download:
                           'validation' (default), 'training', 'testing',
                           'validation_interactive', 'testing_interactive', or 'all'
  -n, --num-shards NUM     Number of TFRecord shard files to download per split (default: ${DEFAULT_SHARDS})
  -o, --output-dir DIR     Destination directory (default: ${DEFAULT_OUTPUT_DIR})
  -d, --dry-run            Show files that would be downloaded without downloading
  -h, --help               Show this help message and exit

Examples:
  # Download 1 validation shard (~770 MB) to ./data/validation/
  ./download_sample.sh

  # Download 2 shards from training and 1 from validation into ./data
  ./download_sample.sh --split validation --num-shards 1
  ./download_sample.sh --split training --num-shards 2

  # Dry run to preview what will be downloaded
  ./download_sample.sh --split all --num-shards 1 --dry-run
EOF
}

# Parse command-line arguments
SPLIT="${DEFAULT_SPLIT}"
NUM_SHARDS="${DEFAULT_SHARDS}"
OUTPUT_DIR="${DEFAULT_OUTPUT_DIR}"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--split)
      SPLIT="$2"
      shift 2
      ;;
    -n|--num-shards)
      NUM_SHARDS="$2"
      shift 2
      ;;
    -o|--output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    -d|--dry-run)
      DRY_RUN=true
      shift 1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! [[ "$NUM_SHARDS" =~ ^[0-9]+$ ]] || [ "$NUM_SHARDS" -le 0 ]; then
  echo "Error: --num-shards must be a positive integer." >&2
  exit 1
fi

# Determine target splits
if [ "$SPLIT" = "all" ]; then
  SPLITS=("validation" "training" "testing" "validation_interactive" "testing_interactive")
else
  SPLITS=("$SPLIT")
fi

echo "=================================================="
echo " Waymo Motion Dataset Sample Downloader"
echo "=================================================="
echo "Splits:         ${SPLITS[*]}"
echo "Shards/split:   ${NUM_SHARDS}"
echo "Destination:    ${OUTPUT_DIR}"
echo "Dry run:        ${DRY_RUN}"
echo "=================================================="

for s in "${SPLITS[@]}"; do
  split_gcs_dir="${BUCKET_BASE}/${s}"
  split_out_dir="${OUTPUT_DIR}/${s}"

  echo ""
  echo "Fetching file list for split: ${s}..."

  # Get list of files up to NUM_SHARDS
  files=$(gcloud storage ls "${split_gcs_dir}/*" 2>/dev/null | head -n "${NUM_SHARDS}" || true)

  if [ -z "$files" ]; then
    echo "Warning: No files found in ${split_gcs_dir}"
    continue
  fi

  if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would create directory: ${split_out_dir}"
    echo "[DRY RUN] Files to download for '${s}':"
    while IFS= read -r file_uri; do
      echo "  - ${file_uri}"
    done <<< "$files"
  else
    mkdir -p "${split_out_dir}"
    while IFS= read -r file_uri; do
      filename=$(basename "$file_uri")
      target_file="${split_out_dir}/${filename}"

      if [ -f "$target_file" ]; then
        echo "File already exists, skipping: ${target_file}"
      else
        echo "Downloading: ${file_uri} -> ${split_out_dir}/"
        gcloud storage cp "${file_uri}" "${split_out_dir}/"
      fi
    done <<< "$files"
  fi
done

echo ""
echo "Done!"
