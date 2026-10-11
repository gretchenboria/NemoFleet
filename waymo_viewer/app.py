import glob
import os
from pathlib import Path
import time
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
import tensorflow as tf

# Matplotlib dark mode configuration
plt.style.use("dark_background")
plt.rcParams["figure.facecolor"] = "#0e1117"
plt.rcParams["axes.facecolor"] = "#0e1117"
plt.rcParams["savefig.facecolor"] = "#0e1117"

# Optional Pillow import
try:
    from PIL import Image
except ImportError:
    Image = None

# Optional Waymo Open Dataset perception protobufs
try:
    from waymo_open_dataset import dataset_pb2 as open_dataset
    HAS_WAYMO_PROTO = True
except ImportError:
    HAS_WAYMO_PROTO = False

# Page Configuration
st.set_page_config(
    page_title="Waymo Motion Scenario Studio",
    layout="wide",
    page_icon="🚗",
    initial_sidebar_state="collapsed",
)

# Custom CSS
st.markdown(
    """
<style>
    /* Hide default Streamlit header overlay so it doesn't block top widget clicks */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .block-container {
        padding-top: 1.0rem !important;
        padding-bottom: 0.5rem !important;
        padding-left: 1.2rem !important;
        padding-right: 1.2rem !important;
        max-width: 100%;
    }
    /* Compact metric cards */
    div[data-testid="stMetric"] {
        background-color: #12151e;
        border-radius: 8px;
        padding: 6px 12px;
        border: 1px solid #232838;
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        color: #8fa0c0 !important;
        font-weight: 500;
        margin-bottom: 0px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.15rem !important;
        color: #f0f4fc !important;
        font-weight: 700;
        line-height: 1.2 !important;
    }
    /* Custom buttons */
    .stButton button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        min-height: 2.3rem !important;
    }
    /* Dataframe styling */
    div[data-testid="stDataFrame"] {
        border: 1px solid #232838;
        border-radius: 8px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Constants & Color Maps
AGENT_TYPES = {
    -1: "INVALID",
    0: "UNSET",
    1: "VEHICLE",
    2: "PEDESTRIAN",
    3: "CYCLIST",
    4: "OTHER",
}

AGENT_COLORS = {
    1: "#1f77b4",  # Blue (Vehicle)
    2: "#ff7f0e",  # Orange (Pedestrian)
    3: "#2ca02c",  # Green (Cyclist)
    4: "#9467bd",  # Purple (Other)
    0: "#8c564b",
    -1: "#555555",
}

ROADGRAPH_TYPES = {
    1: ("Lane Center (Freeway)", "#555555", "--"),
    2: ("Lane Center (Surface)", "#555555", "--"),
    3: ("Lane Center (Bike)", "#2ca02c", ":"),
    6: ("Road Edge", "#888888", "-"),
    15: ("Road Line (Broken White)", "#dddddd", "--"),
    16: ("Road Line (Solid White)", "#dddddd", "-"),
    17: ("Road Line (Double Solid White)", "#ffffff", "-"),
    18: ("Road Line (Broken Yellow)", "#ffcc00", "--"),
    19: ("Road Line (Solid Yellow)", "#ffcc00", "-"),
    20: ("Road Line (Double Solid Yellow)", "#ffcc00", "-"),
    21: ("Road Edge (Curb)", "#777777", "-"),
    22: ("Crosswalk", "#ff7f7f", ":"),
    23: ("Speed Bump", "#d62728", ":"),
    24: ("Stop Sign", "#e377c2", "s"),
}

# Session State Initialization
if "current_step" not in st.session_state:
    st.session_state["current_step"] = 0
if "is_playing" not in st.session_state:
    st.session_state["is_playing"] = False


def find_local_tfrecords():
    found = glob.glob("./data/**/*.tfrecord*", recursive=True) + glob.glob("./*.tfrecord*")
    return sorted(list(set(found)))


# Sidebar: Data Source & Map Settings
with st.sidebar:
    st.header("⚙️ Settings & Data")
    local_files = find_local_tfrecords()
    default_path = local_files[0] if local_files else "./data/validation/validation_tfexample.tfrecord-00000-of-00150"

    file_selection_mode = st.radio(
        "Source Mode:",
        options=["Local Data Folder", "Custom Path"] if local_files else ["Custom Path"],
    )

    if file_selection_mode == "Local Data Folder" and local_files:
        file_path = st.selectbox("Choose TFRecord:", options=local_files)
    else:
        file_path = st.text_input("Path to file:", value=default_path)

    st.divider()
    st.subheader("Map Visuals")
    show_roadgraph = st.checkbox("HD Road Network", value=True)
    show_trajectories = st.checkbox("Trajectory Trails", value=True)
    highlight_predicted = st.checkbox("Highlight Target Tracks", value=True)
    center_on_sdc = st.checkbox("Center on SDC Vehicle", value=True)
    view_radius = st.slider("Map Zoom Radius (m)", min_value=25, max_value=120, value=55, step=5)
    playback_delay = st.select_slider(
        "Playback Delay",
        options=[0.02, 0.04, 0.08, 0.12],
        value=0.04,
        format_func=lambda x: f"{int(x*1000)}ms",
    )


def extract_feat(f, key, dtype=float):
    if key not in f:
        return np.array([], dtype=dtype)
    kind = f[key].WhichOneof("kind")
    if kind == "float_list":
        return np.array(f[key].float_list.value, dtype=dtype)
    elif kind == "int64_list":
        return np.array(f[key].int64_list.value, dtype=dtype)
    elif kind == "bytes_list":
        return [b.decode("utf-8", errors="ignore") for b in f[key].bytes_list.value]
    return np.array([], dtype=dtype)


@st.cache_data(show_spinner="Reading TFRecords...")
def inspect_and_load_tfrecord(path, max_records=100):
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    dataset = tf.data.TFRecordDataset(path)
    records = []
    dataset_type = "unknown"

    for i, raw_bytes in enumerate(dataset):
        raw_val = raw_bytes.numpy()
        if i == 0:
            try:
                example = tf.train.Example()
                example.ParseFromString(raw_val)
                if "scenario/id" in example.features.feature or "state/current/x" in example.features.feature:
                    dataset_type = "motion_tf_example"
            except Exception:
                pass

            if dataset_type == "unknown" and HAS_WAYMO_PROTO:
                try:
                    frame = open_dataset.Frame()
                    frame.ParseFromString(raw_val)
                    if len(frame.images) > 0 or len(frame.laser_labels) > 0:
                        dataset_type = "perception_frame"
                except Exception:
                    pass

        records.append(raw_val)
        if len(records) >= max_records:
            break

    return dataset_type, records


def parse_motion_scenario(raw_bytes):
    ex = tf.train.Example()
    ex.ParseFromString(raw_bytes)
    f = ex.features.feature

    sc_id_list = extract_feat(f, "scenario/id")
    scenario_id = sc_id_list[0] if sc_id_list else "unknown"

    agent_ids = extract_feat(f, "state/id", dtype=int)
    agent_types = extract_feat(f, "state/type", dtype=int)
    is_sdc = extract_feat(f, "state/is_sdc", dtype=int)
    tracks_to_predict = extract_feat(f, "state/tracks_to_predict", dtype=int)
    objects_of_interest = extract_feat(f, "state/objects_of_interest", dtype=int)

    num_agents = len(agent_ids) if len(agent_ids) > 0 else 128

    def assemble_traj(key):
        past = extract_feat(f, f"state/past/{key}").reshape(num_agents, 10) if f"state/past/{key}" in f else np.zeros((num_agents, 10))
        current = extract_feat(f, f"state/current/{key}").reshape(num_agents, 1) if f"state/current/{key}" in f else np.zeros((num_agents, 1))
        future = extract_feat(f, f"state/future/{key}").reshape(num_agents, 80) if f"state/future/{key}" in f else np.zeros((num_agents, 80))
        return np.concatenate([past, current, future], axis=1)

    x = assemble_traj("x")
    y = assemble_traj("y")
    z = assemble_traj("z")
    bbox_yaw = assemble_traj("bbox_yaw")
    length = assemble_traj("length")
    width = assemble_traj("width")
    height = assemble_traj("height")
    speed = assemble_traj("speed")

    # Valid mask
    past_valid = extract_feat(f, "state/past/valid", dtype=int).reshape(num_agents, 10) if "state/past/valid" in f else np.zeros((num_agents, 10), dtype=int)
    curr_valid = extract_feat(f, "state/current/valid", dtype=int).reshape(num_agents, 1) if "state/current/valid" in f else np.zeros((num_agents, 1), dtype=int)
    fut_valid = extract_feat(f, "state/future/valid", dtype=int).reshape(num_agents, 80) if "state/future/valid" in f else np.zeros((num_agents, 80), dtype=int)
    valid = np.concatenate([past_valid, curr_valid, fut_valid], axis=1) == 1

    # Roadgraph
    rg_xyz = extract_feat(f, "roadgraph_samples/xyz").reshape(-1, 3) if "roadgraph_samples/xyz" in f else np.zeros((0, 3))
    rg_type = extract_feat(f, "roadgraph_samples/type", dtype=int)
    rg_id = extract_feat(f, "roadgraph_samples/id", dtype=int)
    rg_valid = extract_feat(f, "roadgraph_samples/valid", dtype=int) == 1 if "roadgraph_samples/valid" in f else np.ones(len(rg_type), dtype=bool)

    if len(rg_valid) == len(rg_xyz):
        rg_xyz = rg_xyz[rg_valid]
        rg_type = rg_type[rg_valid]
        rg_id = rg_id[rg_valid]

    return {
        "scenario_id": scenario_id,
        "num_agents": num_agents,
        "agent_ids": agent_ids,
        "agent_types": agent_types,
        "is_sdc": is_sdc,
        "tracks_to_predict": tracks_to_predict,
        "objects_of_interest": objects_of_interest,
        "x": x,
        "y": y,
        "z": z,
        "bbox_yaw": bbox_yaw,
        "length": length,
        "width": width,
        "height": height,
        "speed": speed,
        "valid": valid,
        "rg_xyz": rg_xyz,
        "rg_type": rg_type,
        "rg_id": rg_id,
    }


# Auto-load or reload dataset
if "records" not in st.session_state or st.session_state.get("file_path") != file_path:
    try:
        dataset_type, records = inspect_and_load_tfrecord(file_path)
        st.session_state["dataset_type"] = dataset_type
        st.session_state["records"] = records
        st.session_state["file_path"] = file_path
    except Exception as e:
        st.error(f"Error loading {file_path}: {e}")
        records = []
        dataset_type = "unknown"
else:
    records = st.session_state["records"]
    dataset_type = st.session_state["dataset_type"]

if records:
    # -------------------------------------------------------------------------
    # TOP HEADER BAR
    # -------------------------------------------------------------------------
    num_scenarios = len(records)
    if "last_record_idx" not in st.session_state:
        st.session_state["last_record_idx"] = 0

    scenario_options = [f"Scenario #{i + 1}" for i in range(num_scenarios)]

    h_col1, h_prev, h_scen, h_next, h_col3 = st.columns([1.8, 0.45, 2.0, 0.45, 2.8])
    with h_col1:
        st.markdown("<h3 style='margin:0; padding:0; color:#f0f4fc;'>🚗 Waymo Motion Studio</h3>", unsafe_allow_html=True)

    with h_prev:
        if st.button("◀", use_container_width=True, help="Previous Scenario", key="btn_prev_scen"):
            curr = st.session_state.get("last_record_idx", 0)
            st.session_state["last_record_idx"] = (curr - 1) % num_scenarios
            st.session_state["is_playing"] = False
            st.session_state["current_step"] = 0
            st.rerun()

    with h_scen:
        selected_scenario_str = st.selectbox(
            "Select Scenario",
            options=scenario_options,
            index=st.session_state["last_record_idx"],
            label_visibility="collapsed",
        )
    record_idx = scenario_options.index(selected_scenario_str)

    with h_next:
        if st.button("▶", use_container_width=True, help="Next Scenario", key="btn_next_scen"):
            curr = st.session_state.get("last_record_idx", 0)
            st.session_state["last_record_idx"] = (curr + 1) % num_scenarios
            st.session_state["is_playing"] = False
            st.session_state["current_step"] = 0
            st.rerun()

    if record_idx != st.session_state["last_record_idx"]:
        st.session_state["last_record_idx"] = record_idx
        st.session_state["is_playing"] = False
        st.session_state["current_step"] = 0

    # -------------------------------------------------------------------------
    # INTERACTIVE PLAYBACK TOOLBAR
    # -------------------------------------------------------------------------
    c_play, c_reset, c_time, c_slider = st.columns([1.0, 1.0, 1.4, 6.6])

    with c_play:
        play_label = "⏸️ Pause" if st.session_state["is_playing"] else "▶️ Play"
        if st.button(play_label, use_container_width=True, type="primary" if st.session_state["is_playing"] else "secondary", key="btn_play_toggle"):
            st.session_state["is_playing"] = not st.session_state["is_playing"]
            if st.session_state["is_playing"] and st.session_state["current_step"] >= 90:
                st.session_state["current_step"] = 0
            st.rerun()

    with c_reset:
        if st.button("⏮️ Reset", use_container_width=True, key="btn_reset_step"):
            st.session_state["is_playing"] = False
            st.session_state["current_step"] = 0
            st.rerun()

    time_offset = (st.session_state["current_step"] - 10) * 0.1

    with c_time:
        st.markdown(
            f"<div style='font-size: 0.88rem; font-weight: 700; color: #00e5ff; background: #12151e; border: 1px solid #232838; border-radius: 8px; text-align: center; padding: 6px 0px;'>"
            f"Step {st.session_state['current_step']}/90 ({time_offset:+.1f}s)</div>",
            unsafe_allow_html=True,
        )

    with c_slider:
        slider_val = st.slider(
            "Timeline Slider",
            min_value=0,
            max_value=90,
            value=st.session_state["current_step"],
            help="Step 0-9: Past 1.0s | Step 10: Current Observation | Step 11-90: Future 8.0s",
            label_visibility="collapsed",
        )
        if slider_val != st.session_state["current_step"] and not st.session_state["is_playing"]:
            st.session_state["current_step"] = slider_val
            st.rerun()

    timestep = st.session_state["current_step"]
    time_offset = (timestep - 10) * 0.1

    # -------------------------------------------------------------------------
    # MAIN DASHBOARD (Balanced 50/50 Map & Live Telemetry)
    # -------------------------------------------------------------------------
    if dataset_type in ("motion_tf_example", "unknown"):
        scenario = parse_motion_scenario(records[record_idx])

        with h_col3:
            st.markdown(
                f"<div style='font-size: 0.82rem; color: #8fa0c0; text-align: right; padding-top: 6px;'>"
                f"Scenario ID: <code>{scenario['scenario_id'][:20]}...</code> | Total Objects: <b>{scenario['num_agents']}</b></div>",
                unsafe_allow_html=True,
            )

        valid_agents_mask = np.any(scenario["valid"], axis=1)
        active_at_t = scenario["valid"][:, timestep]
        num_active_now = int(np.sum(active_at_t))
        num_predicted = int(np.sum(scenario["tracks_to_predict"] == 1))
        sdc_indices = np.where(scenario["is_sdc"] == 1)[0]
        has_sdc = len(sdc_indices) > 0
        sdc_id = sdc_indices[0] if has_sdc else None

        # SDC metrics
        if has_sdc and scenario["valid"][sdc_id, timestep]:
            sdc_speed_ms = scenario["speed"][sdc_id, timestep]
            sdc_speed_mph = sdc_speed_ms * 2.23694
            sdc_yaw_deg = np.degrees(scenario["bbox_yaw"][sdc_id, timestep]) % 360
        else:
            sdc_speed_ms = 0.0
            sdc_speed_mph = 0.0
            sdc_yaw_deg = 0.0

        # Balanced 2-Column Split
        map_col, data_col = st.columns([1.0, 1.0], gap="medium")

        # ----------------------------------------------------
        # LEFT COLUMN: CRISP BEV MAP
        # ----------------------------------------------------
        with map_col:
            fig, ax = plt.subplots(figsize=(5.6, 5.0), dpi=100)
            fig.patch.set_facecolor("#0e1117")
            ax.set_facecolor("#0e1117")

            # 1. Roadgraph
            if show_roadgraph and len(scenario["rg_xyz"]) > 0:
                rg_xyz = scenario["rg_xyz"]
                rg_id = scenario["rg_id"]
                rg_type = scenario["rg_type"]

                for elem_id in np.unique(rg_id):
                    mask = rg_id == elem_id
                    pts = rg_xyz[mask]
                    e_type = rg_type[mask][0] if len(rg_type[mask]) > 0 else 1
                    _, color, lstyle = ROADGRAPH_TYPES.get(e_type, ("Road", "#444444", "-"))

                    if lstyle == "s":
                        ax.scatter(pts[:, 0], pts[:, 1], color=color, s=14, marker="s", alpha=0.8)
                    else:
                        ax.plot(pts[:, 0], pts[:, 1], color=color, linestyle=lstyle, linewidth=0.9, alpha=0.5)

            # 2. View Center
            if center_on_sdc and has_sdc and scenario["valid"][sdc_id, timestep]:
                center_x = scenario["x"][sdc_id, timestep]
                center_y = scenario["y"][sdc_id, timestep]
            elif np.any(active_at_t):
                center_x = float(np.mean(scenario["x"][active_at_t, timestep]))
                center_y = float(np.mean(scenario["y"][active_at_t, timestep]))
            else:
                center_x, center_y = 0.0, 0.0

            # 3. Agents
            num_agents = scenario["num_agents"]
            for i in range(num_agents):
                if not valid_agents_mask[i]:
                    continue

                a_type = scenario["agent_types"][i]
                is_sdc_agent = scenario["is_sdc"][i] == 1
                is_predicted = scenario["tracks_to_predict"][i] == 1

                if is_sdc_agent:
                    color = "#00e5ff"  # Cyan SDC
                elif is_predicted and highlight_predicted:
                    color = "#ff1744"  # Neon Red Targets
                else:
                    color = AGENT_COLORS.get(a_type, "#2979ff")

                # Trajectories
                if show_trajectories:
                    past_steps = np.where(scenario["valid"][i, : timestep + 1])[0]
                    if len(past_steps) > 1:
                        ax.plot(
                            scenario["x"][i, past_steps],
                            scenario["y"][i, past_steps],
                            color=color,
                            linewidth=1.6 if (is_predicted or is_sdc_agent) else 1.0,
                            alpha=0.8,
                        )

                    fut_steps = np.where(scenario["valid"][i, timestep:])[0] + timestep
                    if len(fut_steps) > 1:
                        ax.plot(
                            scenario["x"][i, fut_steps],
                            scenario["y"][i, fut_steps],
                            color=color,
                            linestyle="--",
                            linewidth=1.2 if (is_predicted or is_sdc_agent) else 0.7,
                            alpha=0.35,
                        )

                # Bounding Box at current timestep
                if scenario["valid"][i, timestep]:
                    pos_x = scenario["x"][i, timestep]
                    pos_y = scenario["y"][i, timestep]
                    yaw = scenario["bbox_yaw"][i, timestep]
                    agent_len = max(float(scenario["length"][i, timestep]), 1.8)
                    agent_wid = max(float(scenario["width"][i, timestep]), 0.8)

                    cos_h = np.cos(yaw)
                    sin_h = np.sin(yaw)
                    R = np.array([[cos_h, -sin_h], [sin_h, cos_h]])
                    dx = agent_len / 2.0
                    dy = agent_wid / 2.0
                    corners = np.array([[-dx, -dy], [dx, -dy], [dx, dy], [-dx, dy]])
                    rot_corners = corners @ R.T + np.array([pos_x, pos_y])

                    poly = patches.Polygon(
                        rot_corners,
                        closed=True,
                        facecolor=color,
                        edgecolor="#ffffff" if (is_predicted or is_sdc_agent) else "#000000",
                        alpha=0.9 if (is_predicted or is_sdc_agent) else 0.7,
                        linewidth=1.6 if (is_predicted or is_sdc_agent) else 0.8,
                        zorder=12 if is_sdc_agent else (10 if is_predicted else 5),
                    )
                    ax.add_patch(poly)

                    # Heading Line
                    front_pt = np.array([dx, 0.0]) @ R.T + np.array([pos_x, pos_y])
                    ax.plot([pos_x, front_pt[0]], [pos_y, front_pt[1]], color="#ffffff", linewidth=1.3, zorder=13)

            ax.set_aspect("equal", "datalim")
            ax.set_xlim(center_x - view_radius, center_x + view_radius)
            ax.set_ylim(center_y - view_radius, center_y + view_radius)
            ax.set_title(
                f"BEV Map • Step {timestep}/90 (t = {time_offset:+.1f}s)",
                color="#f0f4fc",
                fontsize=11,
                fontweight="bold",
                pad=8,
            )
            ax.tick_params(colors="#4a5568", labelsize=8)
            for spine in ax.spines.values():
                spine.set_color("#232838")
            ax.grid(True, color="#1c212d", linestyle=":")
            plt.subplots_adjust(top=0.93, bottom=0.07, left=0.08, right=0.95)

            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

            # Compact Legend
            st.markdown(
                "<div style='font-size: 0.82rem; color: #8fa0c0; text-align: center; margin-top: -4px;'>"
                "<span style='color:#00e5ff;'>■</span> SDC &nbsp;|&nbsp; "
                "<span style='color:#ff1744;'>■</span> Target Track &nbsp;|&nbsp; "
                "<span style='color:#1f77b4;'>■</span> Vehicle &nbsp;|&nbsp; "
                "<span style='color:#ff7f0e;'>■</span> Pedestrian &nbsp;|&nbsp; "
                "<span style='color:#2ca02c;'>■</span> Cyclist"
                "</div>",
                unsafe_allow_html=True,
            )

        # ----------------------------------------------------
        # RIGHT COLUMN: TELEMETRY & LIVE DATA
        # ----------------------------------------------------
        with data_col:
            # Metric badges
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("SDC Speed", f"{sdc_speed_ms:.1f} m/s", delta=f"{sdc_speed_mph:.1f} mph")
            m2.metric("Active Now", f"{num_active_now} objs", delta=f"of {np.sum(valid_agents_mask)} total")
            m3.metric("Targets", f"{num_predicted}", delta="to predict")
            m4.metric("Heading", f"{int(sdc_yaw_deg)}°", delta="SDC Yaw")

            # Real-Time Telemetry Curve (SDC Speed over time)
            if has_sdc:
                sdc_speeds = scenario["speed"][sdc_id, :]
                time_steps = np.arange(91)

                fig_chart, ax_c = plt.subplots(figsize=(5.8, 1.2), dpi=100)
                fig_chart.patch.set_facecolor("#12151e")
                ax_c.set_facecolor("#12151e")
                ax_c.plot(time_steps, sdc_speeds, color="#00e5ff", linewidth=1.8, label="SDC Speed")
                ax_c.axvline(x=timestep, color="#ff1744", linestyle="--", linewidth=1.5, label="Current t")
                ax_c.scatter([timestep], [sdc_speed_ms], color="#ff1744", s=30, zorder=5)
                ax_c.set_xlim(0, 90)
                ax_c.set_ylim(0, max(float(np.max(sdc_speeds)) * 1.15, 5.0))
                ax_c.set_ylabel("Speed (m/s)", color="#8fa0c0", fontsize=7.5)
                ax_c.tick_params(colors="#4a5568", labelsize=7)
                for spine in ax_c.spines.values():
                    spine.set_color("#232838")
                ax_c.grid(True, color="#232838", linestyle=":", alpha=0.5)
                plt.subplots_adjust(top=0.90, bottom=0.22, left=0.10, right=0.96)
                st.pyplot(fig_chart, use_container_width=True)
                plt.close(fig_chart)

            # Live Dynamic Agents Table
            st.markdown("<p style='font-size: 0.8rem; font-weight: 700; margin: 4px 0px 2px 0px; color: #8fa0c0;'>LIVE AGENTS TELEMETRY</p>", unsafe_allow_html=True)
            active_indices = np.where(scenario["valid"][:, timestep])[0]

            if len(active_indices) > 0:
                table_rows = []
                for idx in active_indices:
                    is_sdc_a = scenario["is_sdc"][idx] == 1
                    is_pred_a = scenario["tracks_to_predict"][idx] == 1

                    if is_sdc_a:
                        role_str = "🚙 SDC"
                        sort_prio = 0
                    elif is_pred_a:
                        role_str = "🎯 Target"
                        sort_prio = 1
                    else:
                        role_str = "🚗 Agent"
                        sort_prio = 2

                    table_rows.append({
                        "_prio": sort_prio,
                        "Role": role_str,
                        "ID": int(scenario["agent_ids"][idx]) if idx < len(scenario["agent_ids"]) else idx,
                        "Type": AGENT_TYPES.get(scenario["agent_types"][idx], "OTHER"),
                        "Speed (m/s)": round(float(scenario["speed"][idx, timestep]), 2),
                        "Speed (mph)": round(float(scenario["speed"][idx, timestep]) * 2.23694, 1),
                        "X (m)": round(float(scenario["x"][idx, timestep]), 1),
                        "Y (m)": round(float(scenario["y"][idx, timestep]), 1),
                        "Heading": f"{int(np.degrees(scenario['bbox_yaw'][idx, timestep]) % 360)}°",
                    })

                df = pd.DataFrame(table_rows).sort_values(by=["_prio", "Speed (m/s)"], ascending=[True, False]).drop(columns=["_prio"])

                table_height = min(max(len(df) * 35 + 40, 360), 650)
                st.dataframe(
                    df,
                    use_container_width=True,
                    height=table_height,
                    hide_index=True,
                )
            else:
                st.info("No active agents tracked at this exact timestep.")

        # Playback auto-stepping loop
        if st.session_state.get("is_playing", False):
            if st.session_state["current_step"] < 90:
                time.sleep(playback_delay)
                st.session_state["current_step"] += 1
                st.rerun()
            else:
                st.session_state["is_playing"] = False
                st.rerun()

    # Perception Dataset View
    elif dataset_type == "perception_frame" and HAS_WAYMO_PROTO:
        frame = open_dataset.Frame()
        frame.ParseFromString(records[record_idx])

        col1, col2, col3 = st.columns(3)
        col1.metric("Frame Index", f"{record_idx + 1} / {len(records)}")
        col2.metric("Timestamp (μs)", frame.timestamp_micros)
        col3.metric("3D Objects Detected", len(frame.laser_labels))

        st.divider()
        st.subheader("📷 Synchronized Camera Streams")

        camera_names = {
            open_dataset.CameraName.FRONT: "Front",
            open_dataset.CameraName.FRONT_LEFT: "Front Left",
            open_dataset.CameraName.FRONT_RIGHT: "Front Right",
            open_dataset.CameraName.SIDE_LEFT: "Side Left",
            open_dataset.CameraName.SIDE_RIGHT: "Side Right",
        }

        if len(frame.images) > 0:
            cols = st.columns(min(len(frame.images), 5))
            for idx, camera_img in enumerate(frame.images):
                cam_title = camera_names.get(camera_img.name, f"Camera {camera_img.name}")
                rgb_array = tf.io.decode_jpeg(camera_img.image).numpy()
                with cols[idx % len(cols)]:
                    st.image(rgb_array, caption=cam_title, use_container_width=True)
        else:
            st.info("No camera images found in this frame.")
else:
    st.info("👋 Welcome! Select a valid TFRecord in the sidebar to begin.")