"""Build the San Francisco (SoMa, around Salesforce Tower) map for the experimental robotaxi scene.

Input:  tools/sf_map/osm-soma.json  (OpenStreetMap via Overpass; © OpenStreetMap contributors, ODbL)
Output: site/assets/scenes/sanfrancisco/floor.jpg   2240x950 rendered street map (canvas is 1120x475)
        site/assets/scenes/sanfrancisco/roads.json  drivable road graph in canvas coordinates (one-way aware)
                                                     + scene anchors (hazard block, crosswalk, tower)
Usage:  <python with matplotlib> tools/sf_map/build_sf_map.py
"""
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Polygon

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "assets" / "scenes" / "sanfrancisco"
CW, CH = 1120, 475
TOWER = (37.78977, -122.39708)                       # Salesforce Tower
LON0, LON1 = -122.4030, -122.3912                    # ~1.04 km wide
KX = math.cos(math.radians(TOWER[0]))
HALF_LAT = (LON1 - LON0) * KX * CH / CW / 2          # keep the canvas aspect ratio
LAT0, LAT1 = TOWER[0] - HALF_LAT, TOWER[0] + HALF_LAT

DRIVE = {"primary", "secondary", "tertiary", "residential", "unclassified", "tertiary_link", "primary_link", "secondary_link"}
WIDTH = {"primary": 15, "secondary": 13, "tertiary": 11, "residential": 7, "unclassified": 7, "tertiary_link": 6, "primary_link": 7, "secondary_link": 7,
         "service": 3.2, "busway": 4.5, "pedestrian": 3.5}


def xy(lat, lon):
    return (lon - LON0) / (LON1 - LON0) * CW, (LAT1 - lat) / (LAT1 - LAT0) * CH


def key(p):
    return f"{p['lat']:.7f},{p['lon']:.7f}"


def main():
    els = json.load(open(Path(__file__).with_name("osm-soma.json")))["elements"]
    OUT.mkdir(parents=True, exist_ok=True)

    # ---------------- road graph (directed, one-way aware) ----------------
    nodes, edges, names = {}, [], {}
    for e in els:
        hw = e["tags"].get("highway")
        if hw not in DRIVE or e["tags"].get("access") in ("no", "private"):
            continue
        g, ow = e["geometry"], e["tags"].get("oneway", "no")
        ids = []
        for p in g:
            k = key(p)
            if k not in nodes:
                nodes[k] = {"i": len(nodes), "xy": [round(v, 1) for v in xy(p["lat"], p["lon"])], "ll": [p["lat"], p["lon"]]}
            ids.append(nodes[k]["i"])
        name = e["tags"].get("name", "")
        for a, b in zip(ids, ids[1:]):
            if ow in ("yes", "true", "1"):
                edges.append([a, b])
            elif ow == "-1":
                edges.append([b, a])
            else:
                edges.append([a, b]); edges.append([b, a])
            names.setdefault(a, set()).add(name); names.setdefault(b, set()).add(name)
    pts = [None] * len(nodes)
    for n in nodes.values():
        pts[n["i"]] = n["xy"]

    def junction(n1, n2):
        cand = [i for i, s in names.items() if any(n1 in x for x in s) and any(n2 in x for x in s)]
        if not cand:
            raise SystemExit(f"no junction {n1} × {n2}")
        return [round(sum(pts[i][0] for i in cand) / len(cand), 1), round(sum(pts[i][1] for i in cand) / len(cand), 1)]

    fm, fh = junction("Fremont", "Mission"), junction("Fremont", "Howard")
    hazard = [round((fm[0] + fh[0]) / 2, 1), round((fm[1] + fh[1]) / 2, 1)]
    # the closed block follows Fremont St between the two junctions (SoMa streets run diagonally)
    dx, dy = fh[0] - fm[0], fh[1] - fm[1]; L2 = dx * dx + dy * dy
    seg = []
    for i, s in names.items():
        if any("Fremont" in x for x in s):
            t = ((pts[i][0] - fm[0]) * dx + (pts[i][1] - fm[1]) * dy) / L2
            off = abs((pts[i][0] - fm[0]) * dy - (pts[i][1] - fm[1]) * dx) / math.sqrt(L2)
            if 0 <= t <= 1 and off < 8:
                seg.append((t, pts[i]))
    zone = [fm] + [p for _, p in sorted(seg)] + [fh]
    crosswalk = junction("1st Street", "Mission")
    tower = [round(v, 1) for v in xy(*TOWER)]
    meta = {"hazard": hazard, "hazard_label": "Fremont St · Mission–Howard", "zone": zone, "zone_label": "FREMONT ST (MISSION–HOWARD) · CLOSED",
            "person": crosswalk, "person_label": "1st & Mission crosswalk", "tower": tower,
            "bbox": [LAT0, LON0, LAT1, LON1], "attribution": "© OpenStreetMap contributors (ODbL)"}
    json.dump({"nodes": pts, "edges": edges, "meta": meta}, open(OUT / "roads.json", "w"), separators=(",", ":"))

    # ---------------- rendered street map ----------------
    fig = plt.figure(figsize=(CW / 100 * 2, CH / 100 * 2), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, CW); ax.set_ylim(CH, 0); ax.axis("off")
    fig.patch.set_facecolor("#e9ece6")

    def poly(e, fc, ec="none", lw=0, z=1):
        g = e["geometry"]
        if len(g) < 3:
            return
        ax.add_patch(Polygon([xy(p["lat"], p["lon"]) for p in g], closed=True, fc=fc, ec=ec, lw=lw, zorder=z))

    for e in els:
        t = e["tags"]
        if t.get("leisure") == "park" or t.get("landuse") == "grass":
            poly(e, "#cfe3c2", z=1)
        elif t.get("landuse") in ("construction",):
            poly(e, "#e3ddd2", z=1)
    for e in els:
        if "building" in e["tags"]:
            tower_b = "Salesforce Tower" in e["tags"].get("name", "")
            poly(e, "#9fb4c8" if tower_b else "#d6d9d3", "#c3c8c1" if not tower_b else "#6f8aa3", 0.6, z=2)

    def line(e, color, w, z):
        g = e["geometry"]
        xs, ys = zip(*[xy(p["lat"], p["lon"]) for p in g])
        ax.plot(xs, ys, color=color, lw=w, solid_capstyle="round", solid_joinstyle="round", zorder=z)

    for e in els:
        hw = e["tags"].get("highway")
        if hw in ("footway", "pedestrian", "steps", "cycleway") and e["tags"].get("footway") != "crossing":
            line(e, "#f6f6f2", 1.6 if hw != "pedestrian" else 3.5, 3)
        elif hw in ("service", "busway"):
            line(e, "#fbfbf8", WIDTH[hw], 3)
    for e in els:                                   # casing then fill for drivable streets
        hw = e["tags"].get("highway")
        if hw in DRIVE:
            line(e, "#b9bdb4", WIDTH[hw] + 2.4, 4)
    for e in els:
        hw = e["tags"].get("highway")
        if hw in DRIVE:
            line(e, "#ffffff", WIDTH[hw], 5)
    for e in els:                                   # centre lines on the big streets
        hw = e["tags"].get("highway")
        if hw in ("primary", "secondary") and e["tags"].get("oneway") != "yes":
            line(e, "#e8c96a", 0.9, 6)

    # street names: one label per street, on its longest drivable piece
    best = {}
    for e in els:
        t = e["tags"]
        if t.get("highway") in DRIVE and t.get("name"):
            g = [xy(p["lat"], p["lon"]) for p in e["geometry"]]
            L = sum(math.dist(a, b) for a, b in zip(g, g[1:]))
            if L > best.get(t["name"], (0, None))[0]:
                best[t["name"]] = (L, g)
    for nm, (L, g) in best.items():
        if L < 70:
            continue
        mid = L / 2; acc = 0
        for a, b in zip(g, g[1:]):
            d = math.dist(a, b)
            if acc + d >= mid and d > 0:
                f = (mid - acc) / d; x, y = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
                if ang > 90: ang -= 180
                if ang < -90: ang += 180
                ax.text(x, y, nm.replace(" Street", " St").upper(), fontsize=8.6, color="#5b6168", ha="center", va="center", rotation=ang,
                        rotation_mode="anchor", fontweight="bold", zorder=8, path_effects=[pe.withStroke(linewidth=2.6, foreground="#ffffff")])
                break
            acc += d

    tx, ty = tower
    ax.text(tx, ty - 2, "SALESFORCE\nTOWER", fontsize=8.5, color="#2d4a66", ha="center", va="center", fontweight="bold", zorder=9, linespacing=1.0,
            path_effects=[pe.withStroke(linewidth=2.5, foreground="#ffffff")])
    for e in els:
        if e["tags"].get("name") == "Salesforce Transit Center" and len(e["geometry"]) > 3:
            xs, ys = zip(*[xy(p["lat"], p["lon"]) for p in e["geometry"]])
            ax.text(sum(xs) / len(xs), sum(ys) / len(ys), "SALESFORCE TRANSIT CENTER · PARK", fontsize=7.6, color="#3f6b2f", ha="center", va="center",
                    fontweight="bold", zorder=9, path_effects=[pe.withStroke(linewidth=2.4, foreground="#ffffff")])
            break
    ax.text(CW - 6, CH - 5, "© OpenStreetMap contributors", fontsize=8, color="#555b60", ha="right", va="bottom", zorder=10,
            bbox=dict(boxstyle="round,pad=0.2", fc="#ffffffcc", ec="none"))
    fig.savefig(OUT / "floor.jpg", dpi=100, pil_kwargs={"quality": 88})
    print(f"wrote {OUT/'floor.jpg'} and roads.json: {len(pts)} nodes, {len(edges)} directed edges; hazard {hazard} person {crosswalk} tower {tower}")


if __name__ == "__main__":
    main()
