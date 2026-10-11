# Waymo TFRecord Interactive Viewer Installation & Run Guide

This Streamlit application allows you to interactively preview Waymo Open Dataset TFRecords (both **Motion Dataset** scenarios with Bird's-Eye-View map rendering, agent bounding boxes, trajectory trails, and **Perception Dataset** multi-camera streams).

---

## 1. Quick Run with `uv` (Recommended)

You can launch the app directly without manually managing virtualenvs:

```bash
uv run --python 3.11 \
  --with streamlit \
  --with tensorflow \
  --with matplotlib \
  --with pillow \
  streamlit run app.py
```

---

## 2. Standard Virtual Environment Installation

If you prefer using a persistent environment:

### Using `uv`
```bash
# Create Python 3.11 virtual environment
uv venv --python 3.11

# Activate environment
source .venv/bin/activate

# Install required dependencies
uv pip install streamlit tensorflow matplotlib pillow
```

### Using standard `pip`
```bash
pip install streamlit tensorflow matplotlib pillow
```

*(Note: `waymo-open-dataset-tf-2-12-0` is optional and only needed if viewing raw perception camera frames that require dataset proto classes. Motion Dataset TFExamples are parsed natively using TensorFlow).*

---

## 3. Running the Streamlit App

```bash
streamlit run app.py
```

Open your browser at `http://localhost:8501`.

---

## 4. Downloading Dataset Samples

To download additional sample TFRecords:

```bash
# Download 1 validation shard (~770 MB)
./download_sample.sh

# Download 1 training shard
./download_sample.sh --split training --num-shards 1

# Preview without downloading
./download_sample.sh --split all --dry-run
```
