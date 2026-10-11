#!/usr/bin/env python3
"""
download_sample.py - Download a small sample of Waymo Motion Dataset TFRecord files.
"""

import argparse
import subprocess
import sys
from pathlib import Path

BUCKET_BASE = "gs://waymo_open_dataset_motion_v_1_3_1/uncompressed/tf_example"
ALL_SPLITS = [
    "validation",
    "training",
    "testing",
    "validation_interactive",
    "testing_interactive",
]


def run_cmd(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def main():
    parser = argparse.ArgumentParser(
        description="Download a sample of Waymo Motion Dataset TFRecord files."
    )
    parser.add_argument(
        "-s",
        "--split",
        choices=ALL_SPLITS + ["all"],
        default="validation",
        help="Split to download (default: validation)",
    )
    parser.add_argument(
        "-n",
        "--num-shards",
        type=int,
        default=1,
        help="Number of shards to download per split (default: 1)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("./data"),
        help="Target output directory (default: ./data)",
    )
    parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Preview files to download without actually downloading",
    )

    args = parser.parse_args()

    splits = ALL_SPLITS if args.split == "all" else [args.split]

    print("=" * 50)
    print(" Waymo Motion Dataset Sample Downloader")
    print("=" * 50)
    print(f"Splits:         {', '.join(splits)}")
    print(f"Shards/split:   {args.num_shards}")
    print(f"Destination:    {args.output_dir.resolve()}")
    print(f"Dry run:        {args.dry_run}")
    print("=" * 50)

    for split in splits:
        split_gcs_uri = f"{BUCKET_BASE}/{split}"
        split_out_dir = args.output_dir / split

        print(f"\nFetching file list for split: {split}...")
        try:
            res = run_cmd(["gcloud", "storage", "ls", f"{split_gcs_uri}/*"])
            files = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
        except subprocess.CalledProcessError as e:
            print(f"Error querying GCS bucket: {e.stderr}", file=sys.stderr)
            continue

        selected_files = files[: args.num_shards]
        if not selected_files:
            print(f"No files found for {split}")
            continue

        if args.dry_run:
            print(f"[DRY RUN] Target directory: {split_out_dir}")
            for f in selected_files:
                print(f"  - {f}")
            continue

        split_out_dir.mkdir(parents=True, exist_ok=True)

        for gcs_file in selected_files:
            filename = Path(gcs_file).name
            target_path = split_out_dir / filename
            if target_path.exists():
                print(f"File already exists, skipping: {target_path}")
                continue

            print(f"Downloading: {gcs_file} -> {split_out_dir}/")
            try:
                subprocess.run(
                    ["gcloud", "storage", "cp", gcs_file, str(split_out_dir)],
                    check=True,
                )
            except subprocess.CalledProcessError as e:
                print(f"Failed to download {gcs_file}: {e}", file=sys.stderr)

    print("\nDone!")


if __name__ == "__main__":
    main()
