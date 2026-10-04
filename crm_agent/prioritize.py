"""
Step 3: rank every proposal by the open pipeline it touches.

A duplicate on an account with a $480K deal outranks fifty typos on dead
leads. The health score answers one question a Chief of Staff actually asks:
how much of the open pipeline can we trust right now?
"""
import statistics
from collections import Counter, defaultdict

from .detect import WEIGHT, canon_stage, norm_name, parse_amount
from .schema import STAGES_CLOSED


def score(data, proposals, survivor_map):
    deals = data["deals"]
    by_name = {}
    for a in data["accounts"]:
        by_name.setdefault(norm_name(a["name"]), a["id"])

    open_deals = [d for d in deals if canon_stage(d["stage"]) not in STAGES_CLOSED]
    amounts = [parse_amount(d["amount"]) for d in open_deals if parse_amount(d["amount"])]
    median = statistics.median(amounts) if amounts else 0

    deal_value, deal_est = {}, {}
    acct_pipe = Counter()
    for d in open_deals:
        amt = parse_amount(d["amount"])
        deal_value[d["id"]] = amt if amt else median
        deal_est[d["id"]] = amt is None
        aid = by_name.get(norm_name(d["account_name"]))
        if aid:
            acct_pipe[aid] += deal_value[d["id"]]

    contact_acct = {c["id"]: by_name.get(norm_name(c["account_name"])) for c in data["contacts"]}

    # which open deals are touched by a forecast-category proposal (directly or via their account)
    untrusted = set()
    acct_to_deals = defaultdict(list)
    for d in open_deals:
        aid = by_name.get(norm_name(d["account_name"]))
        if aid:
            acct_to_deals[aid].append(d["id"])

    for p in proposals:
        est = False
        if p["object"] == "deals":
            p["touched_deals"] = [p["record_id"]] if p["record_id"] in deal_value else []
            val = deal_value.get(p["record_id"], 0)
            est = deal_est.get(p["record_id"], False)
            if p["category"] == "forecast":
                untrusted.add(p["record_id"])
        elif p["object"] == "accounts":
            ids = [p["record_id"]] + p["merge_ids"]
            p["touched_deals"] = [d for i in ids for d in acct_to_deals[i]]
            val = sum(acct_pipe[i] for i in ids)
            if p["category"] == "forecast":
                for i in ids:
                    untrusted.update(acct_to_deals[i])
        else:
            aid = contact_acct.get(p["record_id"])
            p["touched_deals"] = list(acct_to_deals[aid]) if aid else []
            val = acct_pipe[aid] if aid else 0
        p["pipeline"] = round(val)
        p["pipeline_estimated"] = est
        p["priority"] = round(val * WEIGHT[p["category"]] * (0.5 + p["confidence"] / 2))

    proposals.sort(key=lambda p: (-p["priority"], p["id"]))

    total = sum(deal_value.values())
    at_risk = sum(deal_value[i] for i in untrusted if i in deal_value)
    reported = sum(a for a in amounts)
    cats = Counter(p["category"] for p in proposals)
    return {
        "deal_values": {k: round(v) for k, v in deal_value.items()},
        "open_deals": len(open_deals),
        "open_pipeline_reported": round(reported),
        "open_pipeline_incl_estimates": round(total),
        "median_open_deal": round(median),
        "deals_missing_amount": sum(deal_est.values()),
        "pipeline_untrusted": round(at_risk),
        "pipeline_trusted": round(total - at_risk),
        "trust_pct": round(100 * (total - at_risk) / total) if total else 100,
        "deals_untrusted": len(untrusted & set(deal_value)),
        "counts": {
            "accounts": len(data["accounts"]), "contacts": len(data["contacts"]), "deals": len(deals),
            "proposals": len(proposals),
            "fixes": sum(p["action"] != "flag" for p in proposals),
            "flags": sum(p["action"] == "flag" for p in proposals),
            "by_rule": sum(p["source"] == "rule" for p in proposals),
            "by_claude": sum(p["source"] == "claude" for p in proposals),
        },
        "by_category": dict(cats),
        "by_issue": dict(Counter(p["issue_label"] for p in proposals).most_common()),
    }
