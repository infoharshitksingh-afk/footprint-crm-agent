#!/usr/bin/env python3
"""
CRM cleanup agent.

  python run.py scan                 read input/*.csv, propose fixes, open the review page
  python run.py apply                apply the decisions you exported from the review page
  python run.py demo                 run on the synthetic demo CRM in demo/data

Options for scan/demo:
  --input DIR        folder of CRM CSV exports (default: input)
  --output DIR       where proposals, review page and cleaned files go (default: output)
  --no-llm           rules only; never call Claude even if ANTHROPIC_API_KEY is set
  --model NAME       Claude model (default: $CRM_AGENT_MODEL or claude-sonnet-5-5)
  --as-of DATE       treat this date as "today" (YYYY-MM-DD)
  --remap            ignore the saved mapping.json and map headers again
  --no-open          don't open the review page in a browser
"""
import argparse
import hashlib
import json
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path

from crm_agent import apply as applier
from crm_agent import ingest, prioritize, report
from crm_agent.detect import Scanner
from crm_agent.judge import DEFAULT_MODEL, Judge

ROOT = Path(__file__).parent


def scan(args):
    inp, out = Path(args.input), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    judge = Judge(enabled=not args.no_llm, model=args.model)
    print(f"Mode: {'Claude (' + judge.model + ') + rules' if judge.enabled else 'rules only'}")
    if not judge.enabled and not args.no_llm:
        print("  No ANTHROPIC_API_KEY found. Judgment calls will be flagged for a human instead of fixed.")

    map_path = out / "mapping.json"
    saved = None if args.remap else ingest.read_mapping(map_path)
    mapping = ingest.build_mapping(inp, judge, existing=saved)
    ingest.save_mapping(mapping, map_path)
    print("\nField mapping (edit output/mapping.json and re-run to change):")
    for fname, spec in mapping.items():
        print(f"  {fname} -> {spec['object']}  [{spec.get('mapped_by', 'saved')}]")
        for canon, header in spec["fields"].items():
            print(f"      {canon:<14} <- {header}")
        if spec["ignored"]:
            print(f"      ignored: {', '.join(spec['ignored'])}")

    data, raw_headers = ingest.load(inp, mapping)
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    scanner = Scanner(data, judge, as_of)
    proposals, notes = scanner.run()
    health = prioritize.score(data, proposals, scanner.survivor)

    run_id = hashlib.sha1(json.dumps([str(inp.resolve()), sorted(mapping), as_of.isoformat(),
                                      datetime.now().isoformat()]).encode()).hexdigest()[:10]
    run = {
        "run_id": run_id, "as_of": as_of.isoformat(), "input": str(inp.resolve()),
        "files": list(mapping), "llm": judge.enabled, "model": judge.model if judge.enabled else None,
        "claude_calls": judge.calls, "errors": judge.errors, "company": args.company,
        "health": health, "notes": notes, "proposals": proposals,
    }
    (out / "proposals.json").write_text(json.dumps(run, indent=1, default=str))
    page = report.render(run, out / "review.html")

    h, c = health, health["counts"]
    print(f"\nOpen pipeline you can trust: {h['trust_pct']}%  "
          f"(${h['pipeline_trusted']:,} of ${h['open_pipeline_incl_estimates']:,} across {h['open_deals']} deals)")
    print(f"{c['proposals']} proposals: {c['fixes']} fixes, {c['flags']} flags  |  "
          f"{c['by_rule']} by rules, {c['by_claude']} by Claude ({judge.calls} API calls)")
    for e in judge.errors:
        print(f"  ! Claude call failed, fell back to rules: {e}")
    print("\nTop 5 by pipeline at stake:")
    for p in proposals[:5]:
        print(f"  ${p['pipeline']:>9,}  {p['issue_label']:<32} {p['record_label'][:48]}")
    print(f"\nReview page: {page.resolve()}")
    print("Approve or reject there, save decisions.json into the output folder, then: python run.py apply")
    if not args.no_open:
        webbrowser.open(page.resolve().as_uri())


def apply_cmd(args):
    out = Path(args.output)
    run_path = out / "proposals.json"
    if not run_path.exists():
        sys.exit("No proposals.json found. Run `python run.py scan` first.")
    run = json.loads(run_path.read_text())
    dec_path = Path(args.decisions or out / "decisions.json")
    if not dec_path.exists():
        sys.exit(f"No decisions file at {dec_path}. Export it from the review page first.")
    dec = json.loads(dec_path.read_text())
    if dec.get("run_id") != run["run_id"]:
        sys.exit("These decisions came from a different scan. Re-export them from the current review page.")
    mapping = ingest.read_mapping(out / "mapping.json")
    data, raw_headers = ingest.load(run["input"], mapping)
    res = applier.apply(data, raw_headers, run["proposals"], dec["decisions"], out / "clean",
                        approver=args.approver)
    print(f"Applied {res['approved']} approved proposals ({res['rejected']} rejected, rest left pending).")
    print(f"  {res['changes']} field changes, {res['merges']} records merged, {res['tasks']} owner tasks")
    for f in res["files"]:
        print(f"  wrote {f}")


def main():
    ap = argparse.ArgumentParser(description="CRM cleanup agent", formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "demo"):
        s = sub.add_parser(name)
        s.add_argument("--input", default=str(ROOT / ("demo/data" if name == "demo" else "input")))
        s.add_argument("--output", default=str(ROOT / ("output/demo" if name == "demo" else "output")))
        s.add_argument("--no-llm", action="store_true")
        s.add_argument("--model", default=DEFAULT_MODEL)
        s.add_argument("--as-of", default="2026-10-04" if name == "demo" else None)
        s.add_argument("--company", default="Footprint" if name == "demo" else "")
        s.add_argument("--remap", action="store_true")
        s.add_argument("--no-open", action="store_true")
    a = sub.add_parser("apply")
    a.add_argument("--output", default=str(ROOT / "output"))
    a.add_argument("--decisions")
    a.add_argument("--approver", default="reviewer")
    args = ap.parse_args()
    if args.cmd == "apply":
        apply_cmd(args)
    else:
        scan(args)


if __name__ == "__main__":
    main()
