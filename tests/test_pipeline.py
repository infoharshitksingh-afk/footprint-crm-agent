"""
End-to-end test without network: swaps the Anthropic client for a fake that
answers the agent's structured tool calls the way Claude would, so the full
Claude code path (tool schemas, parsing, proposals, apply) is exercised.

  python tests/test_pipeline.py
"""
import csv
import json
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crm_agent import apply as applier, ingest, prioritize  # noqa: E402
from crm_agent.detect import Scanner  # noqa: E402
from crm_agent.judge import Judge  # noqa: E402


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kw):
        tool = kw["tools"][0]
        name = tool["name"]
        payload = json.loads(kw["messages"][0]["content"].split("\n\n", 1)[1])
        self.calls.append(name)
        # the tool schema must be valid enough to name required keys
        assert tool["input_schema"]["required"], name
        out = getattr(self, name)(payload)
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=out)])

    def duplicate_verdicts(self, p):
        v = []
        for pair in p["pairs"]:
            a, b = pair["a"]["name"], pair["b"]["name"]
            words = set((a + " " + b).split())
            same = a.split()[0].lower() == b.split()[0].lower() and "Logistics" not in words and not {"Community", "Credit"} <= words
            v.append({"pair_id": pair["pair_id"], "same_entity": same, "confidence": 0.88 if same else 0.9,
                      "reason": f"{'Same institution' if same else 'Different businesses'}: {a} / {b}."})
        return {"verdicts": v}

    def persona_labels(self, p):
        m = {"Head of Trust & Safety": "Fraud & Risk Leader", "Partner Risk Lead": "Fraud & Risk Leader"}
        return {"labels": [{"title": t, "persona": m.get(t, "Not a buyer"), "confidence": 0.8,
                            "reason": "Owns platform risk." if t in m else "No compliance stake."}
                           for t in p["titles"]]}

    def industry_labels(self, p):
        m = {"Juniper Wealth": "Not a target", "Kestrel Logistics": "Not a target", "Orbit Payroll": "Fintech - Payments"}
        return {"labels": [{"id": a["id"], "industry": m.get(a["name"], "Bank" if "Bank" in a["name"] else "Fintech - Other"),
                            "confidence": 0.75, "reason": "From name and domain."} for a in p["accounts"]]}

    def deal_reviews(self, p):
        out = []
        for d in p["deals"]:
            n = d["notes"].lower()
            out.append({
                "id": d["id"],
                "implied_stage": "Negotiation" if "redlines" in n else None,
                "stage_confidence": 0.85 if "redlines" in n else 0,
                "at_risk": "left the company" in n,
                "risk_reason": "Champion left and new VP is unresponsive." if "left the company" in n else None,
                "implied_source": "Event - Money20/20" if "money20/20" in n else
                                  ("Event - ACAMS" if "acams" in n else ("Inbound - Website" if "website" in n else None)),
                "source_confidence": 0.9, "reason": "Read from notes."})
        return {"reviews": out}

    def stage_map(self, p):
        return {"labels": [{"label": l, "stage": "Negotiation" if "verbal" in l.lower() else None,
                            "confidence": 0.8, "reason": "Verbal commit precedes paperwork."} for l in p["labels"]]}

    def map_headers(self, p):
        return {"mappings": []}


def fake_judge():
    j = Judge(enabled=False)
    j.client = SimpleNamespace(messages=FakeMessages())
    return j


def run():
    tmp = Path(tempfile.mkdtemp())
    inp = ROOT / "demo" / "data"
    judge = fake_judge()
    mapping = ingest.build_mapping(inp, judge)
    data, raw = ingest.load(inp, mapping)
    sc = Scanner(data, judge, date(2026, 10, 4))
    props, notes = sc.run()
    health = prioritize.score(data, props, sc.survivor)
    issues = {(p["issue"], p["record_label"]): p for p in props}
    labels = [p["record_label"] for p in props]

    def has(issue, label_part, action=None):
        for (i, l), p in issues.items():
            if i == issue and label_part in l and (action is None or p["action"] == action):
                return p
        raise AssertionError(f"missing {issue} on {label_part}")

    # duplicates: rule-caught and Claude-caught; look-alikes kept apart
    has("duplicate_account", "First Harbor", "merge")
    g = has("duplicate_account", "Granite Trust", "merge")
    assert g["source"] == "claude", g
    has("duplicate_account", "Silverline", "merge")
    assert any("Meridian" in n for n in notes), notes
    assert not any(p["issue"] == "duplicate_account" and "Kestrel" in p["record_label"] for p in props)
    # deals
    has("stage_mismatch", "Bayside", "update")
    has("deal_at_risk", "Driftwood", "flag")
    has("missing_source", "Silverline FCU - Sanctions", "update")
    has("orphan_deal", "Quanta - Percy pilot", "link")
    has("orphan_deal", "Northpoint - Sanctions", "link")
    has("nonstandard_stage", "Evergreen", "update")
    has("missing_amount", "Tidewater", "flag")
    has("past_close_date", "Keystone", "flag")
    has("stale_deal", "Ridgeway", "flag")
    # contacts
    has("orphan_contact", "Marcus Lee", "link")
    has("invalid_email", "Ivy Brandt", "update")
    has("duplicate_contact", "", "merge")
    # ranking: forecast issues on big accounts come first
    assert props[0]["category"] == "forecast", props[0]
    assert 0 < health["trust_pct"] < 100

    # approve everything, apply, check outputs
    decisions = {p["id"]: "approved" for p in props}
    res = applier.apply(data, raw, props, decisions, tmp / "clean")
    files = {Path(f).name for f in res["files"]}
    assert {"companies.csv", "contacts.csv", "deals.csv", "change_log.csv", "merge_plan.csv", "owner_tasks.csv"} <= files, files
    deals = list(csv.DictReader(open(tmp / "clean" / "deals.csv")))
    fh = next(d for d in deals if d["Deal Name"].startswith("First Harbor - Full"))
    companies = {r["Company name"] for r in csv.DictReader(open(tmp / "clean" / "companies.csv"))}
    assert fh["Associated Company"] in companies, fh
    assert "Granite Trust" not in companies and "Granite Trust Bancorp" in companies
    bay = next(d for d in deals if d["Deal Name"].startswith("Bayside"))
    assert bay["Deal Stage"] == "Negotiation"
    orphans = [d for d in deals if d["Associated Company"] not in companies]
    assert not orphans, orphans
    contacts = list(csv.DictReader(open(tmp / "clean" / "contacts.csv")))
    assert "Buyer Persona" in contacts[0]
    # originals untouched
    assert any(r["Company name"] == "Granite Trust" for r in csv.DictReader(open(inp / "companies.csv")))

    print(f"OK  {len(props)} proposals, {judge.client.messages.calls.__len__()} fake Claude calls "
          f"({sorted(set(judge.client.messages.calls))}), trust {health['trust_pct']}%")
    print(f"    apply: {res['changes']} changes, {res['merges']} merges, {res['tasks']} owner tasks")
    shutil.rmtree(tmp)


if __name__ == "__main__":
    run()
