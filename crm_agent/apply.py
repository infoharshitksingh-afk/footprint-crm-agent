"""
Step 5: apply only what a human approved.

Writes, to output/clean/:
  <your original files>      same columns as the export, cleaned, ready to re-import
  merge_plan.csv             survivor / merged-away pairs (run merges natively in the CRM so
                             activity history follows)
  removed_duplicates_*.csv   the rows merged away, untouched, in case you need them back
  change_log.csv             every change: old value, new value, why, who proposed, who approved
  owner_tasks.csv            approved flags the agent can't fix, routed to the record owner

Your original export is never modified.
"""
import csv
from datetime import datetime
from pathlib import Path

from .detect import norm_name
from .schema import ENRICHED_COLUMNS


def _header(raw_headers, obj, field):
    spec = raw_headers[obj]
    if field in spec["fields"]:
        return spec["fields"][field]
    col = ENRICHED_COLUMNS.get((obj, field), field)
    if col not in spec["headers"]:
        spec["headers"].append(col)
    return col


def apply(data, raw_headers, proposals, decisions, out_dir, approver="reviewer"):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")
    recs = {obj: {r["id"]: r for r in rows} for obj, rows in data.items()}
    log, tasks, merges = [], [], []
    removed = {obj: [] for obj in data}

    approved = [p for p in proposals if decisions.get(p["id"]) == "approved"]

    def set_field(obj, rec, field, new, p, note=""):
        col = _header(raw_headers, obj, field)
        old = rec["_raw"].get(col, "")
        if old == new:
            return
        rec["_raw"][col] = new
        rec[field] = new
        log.append({"time": now, "proposal": p["id"], "object": obj, "record_id": rec["id"],
                    "record": p["record_label"], "action": p["action"], "field": col, "old": old, "new": new,
                    "reason": note or p["reason"], "proposed_by": p["source"], "confidence": p["confidence"],
                    "approved_by": approver})

    # 1. field updates and links
    for p in approved:
        if p["action"] in ("update", "link"):
            rec = recs[p["object"]].get(p["record_id"])
            if rec:
                set_field(p["object"], rec, p["field"], p["new"], p)
        elif p["action"] == "flag":
            tasks.append({"owner": p["owner"] or "Unassigned", "object": p["object"][:-1],
                          "record": p["record_label"], "record_id": p["record_id"], "issue": p["issue_label"],
                          "why": p["reason"], "open_pipeline_touched": p["pipeline"], "proposal": p["id"]})

    # 2. merges: fill survivor gaps from losers, re-parent children, remove losers
    for p in approved:
        if p["action"] != "merge":
            continue
        obj = p["object"]
        survivor = recs[obj].get(p["record_id"])
        if not survivor:
            continue
        for lid in p["merge_ids"]:
            loser = recs[obj].pop(lid, None)
            if not loser:
                continue
            for field, col in raw_headers[obj]["fields"].items():
                if field in ("id",) or survivor["_raw"].get(col) or not loser["_raw"].get(col):
                    continue
                set_field(obj, survivor, field, loser["_raw"][col], p,
                          f"Filled from merged duplicate {lid}")
            if obj == "accounts":
                lname = norm_name(loser["name"])
                for child in ("contacts", "deals"):
                    if child not in raw_headers:
                        continue
                    for c in recs[child].values():
                        if norm_name(c["account_name"]) == lname:
                            set_field(child, c, "account_name", survivor["name"], p,
                                      f"Re-parented from duplicate account '{loser['name']}'")
            merges.append({"object": obj, "survivor_id": survivor["id"], "survivor": p["record_label"],
                           "merged_id": lid, "merged": loser.get("name") or loser.get("email"),
                           "proposal": p["id"]})
            removed[obj].append(loser)
            log.append({"time": now, "proposal": p["id"], "object": obj, "record_id": lid,
                        "record": loser.get("name") or loser.get("email"), "action": "merge", "field": "",
                        "old": lid, "new": f"merged into {survivor['id']}", "reason": p["reason"],
                        "proposed_by": p["source"], "confidence": p["confidence"], "approved_by": approver})

    # 3. write files
    written = []
    for obj, spec in raw_headers.items():
        path = out / spec["file"]
        _write(path, spec["headers"], [r["_raw"] for r in recs[obj].values()])
        written.append(path)
        if removed[obj]:
            p2 = out / f"removed_duplicates_{spec['file']}"
            _write(p2, spec["headers"], [r["_raw"] for r in removed[obj]])
            written.append(p2)
    for name, rows in (("merge_plan.csv", merges), ("change_log.csv", log)):
        if rows:
            _write(out / name, list(rows[0]), rows)
            written.append(out / name)
    if tasks:
        tasks.sort(key=lambda t: (t["owner"], -t["open_pipeline_touched"]))
        _write(out / "owner_tasks.csv", list(tasks[0]), tasks)
        written.append(out / "owner_tasks.csv")

    return {"approved": len(approved), "changes": len(log), "merges": len(merges), "tasks": len(tasks),
            "rejected": sum(v == "rejected" for v in decisions.values()), "files": [str(w) for w in written]}


def _write(path, headers, rows):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
