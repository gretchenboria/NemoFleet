# 🚗 Waymo Dataset Interactive Viewer

An interactive Streamlit application for previewing and analyzing **Waymo Open Dataset (Motion & Perception)** TFRecords.

## Features

- **Motion Dataset Viewer**:
  - Interactive Bird's-Eye-View (BEV) rendering of HD road graph (lanes, crosswalks, road edges, stop signs).
  - 91-step timeline slider (past 1s, current observation, future 8s @ 10 Hz).
  - Oriented bounding boxes, heading directions, and past/future trajectory trails.
  - Highlights Autonomous Vehicle (SDC) and target prediction tracks.
  - Live active agents telemetry table (speed, position, heading, type).
- **Perception Dataset Viewer**:
  - Synchronized multi-camera streams preview (Front, Front-Left, Front-Right, Side-Left, Side-Right).
  - 3D laser label object class breakdown.
- **Sample Downloader**:
  - `download_sample.sh` / `download_sample.py` to download small shards instead of entire multi-gigabyte buckets.

---

## Getting Started with `uv`

### 1. Lock and Sync Environment

```bash
uv sync --python 3.11
```

### 2. Run the Viewer

```bash
uv run streamlit run app.py
```

---

## Downloading Sample Data

```bash
# Download 1 validation shard (~770 MB)
./download_sample.sh

# Download 1 training shard
./download_sample.sh --split training --num-shards 1
```
