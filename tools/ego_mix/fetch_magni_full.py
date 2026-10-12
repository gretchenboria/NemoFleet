"""Full THÖR-MAGNI release (52 runs, CC BY 4.0, doi 10.5281/zenodo.13865754) -> planned-path training samples.

  uv run --no-project --python 3.12 --with remotezip python tools/ego_mix/fetch_magni_full.py OUT.samples.jsonl HELD_OUT_DIR

Reads each motion CSV straight out of the 22 GB zip with range requests (about 2.5 GB of CSV, one file on
disk at a time). Runs that appear in HELD_OUT_DIR's val or test set are skipped, and every other run is hinted
"train", so the existing val and test rows stay exactly as they were and remain unseen.
"""
import json
import os
import sys
import tempfile

from remotezip import RemoteZip

import adapt_magni
from common import HZ, tracks_doc
from featurize import samples

URL = "https://zenodo.org/api/records/13865754/files/THOR_MAGNI.zip/content"
out, held_dir = sys.argv[1:3]
held = {json.loads(l)["meta"]["group"].split(":")[1] for s in ("val", "test") for l in open(os.path.join(held_dir, f"{s}.jsonl")) if '"magni:' in l}
print("held-out runs:", sorted(held), flush=True)
n = collections_n = 0
with RemoteZip(URL) as z, open(out, "w") as f, tempfile.TemporaryDirectory() as tmp:
    for info in z.infolist():
        if "/CSVs_Scenarios/" not in info.filename or not info.filename.endswith(".csv"):
            continue
        run = os.path.basename(info.filename)[:-4].split("Magni_")[-1]
        if run in held:
            continue
        path = z.extract(info, tmp)
        try:
            bodies = adapt_magni.load(path)
            k = 0
            for ego in bodies:
                emb = "robot" if "Robot" in ego else "human" if ego.startswith("Helmet") else None
                if not emb:
                    continue
                for j, frames in enumerate(adapt_magni.ego_view(bodies, ego)):
                    doc = tracks_doc(f"magni-{run}-{ego}-{j}", "magni", frames, embodiment=emb, site="indoor-workspace", group=run, split_hint="train")
                    for s in samples(doc, plan=True):
                        f.write(json.dumps(s) + "\n"); k += 1
            n += k
            print(run, k, "samples", flush=True)
        except Exception as e:  # noqa: BLE001
            print(run, "SKIPPED", repr(e)[:120], flush=True)
        os.remove(path)
print(n, "samples ->", out)
