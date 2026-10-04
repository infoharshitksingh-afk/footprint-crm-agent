"""
The judgment layer. Claude only sees the cases rules can't settle:
  - are these two accounts the same company?
  - what kind of buyer is this job title?
  - what do the deal notes say about stage, risk and where the deal came from?
  - which industry bucket does this account belong in?
  - which canonical field does an unfamiliar CSV header mean?

Runs on the user's own Anthropic API key (ANTHROPIC_API_KEY). With no key, or
with --no-llm, every method returns nothing and the rules engine falls back to
flagging these cases for a human instead of proposing a fix.

Only the fields needed for each judgment are sent: names, domains, titles and
deal notes. Never emails, phone numbers or amounts.
"""
import json
import os

from .schema import INDUSTRIES, PERSONAS, STAGES

DEFAULT_MODEL = os.environ.get("CRM_AGENT_MODEL", "claude-sonnet-5-5")
BATCH = 25

SYSTEM = (
    "You are a revenue-operations analyst cleaning the CRM of a company that sells "
    "financial-crime compliance software (KYC, AML transaction monitoring, sanctions, fraud "
    "investigations) to banks, credit unions and fintechs. Be conservative: when the evidence is "
    "thin, say so with a low confidence instead of guessing. Every answer needs a one-sentence "
    "reason a sales manager would accept."
)


class Judge:
    def __init__(self, enabled=True, model=DEFAULT_MODEL):
        self.model = model
        self.client = None
        self.calls = 0
        self.errors = []
        key = os.environ.get("ANTHROPIC_API_KEY")
        if enabled and key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=key)
            except ImportError:
                self.errors.append("anthropic package not installed; run: pip install anthropic")

    @property
    def enabled(self):
        return self.client is not None

    # ------------------------------------------------------------------ core
    def _ask(self, instruction, payload, schema, tool_name):
        """Force a single structured tool call and return its input."""
        if not self.enabled:
            return None
        try:
            self.calls += 1
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM,
                tools=[{"name": tool_name, "description": instruction, "input_schema": schema}],
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": f"{instruction}\n\n{json.dumps(payload, indent=1)}"}],
            )
            for block in msg.content:
                if getattr(block, "type", "") == "tool_use":
                    return block.input
        except Exception as e:  # network, auth, rate limit: degrade to rules, never crash
            self.errors.append(f"{tool_name}: {type(e).__name__}: {e}")
        return None

    def _batched(self, items, fn):
        out = []
        for i in range(0, len(items), BATCH):
            res = fn(items[i:i + BATCH])
            if res:
                out.extend(res)
        return out

    # -------------------------------------------------------------- judgments
    def map_headers(self, obj, unmapped, missing):
        schema = {"type": "object", "properties": {"mappings": {"type": "array", "items": {
            "type": "object", "properties": {
                "canonical": {"type": "string", "enum": missing},
                "header": {"type": "string", "enum": unmapped}},
            "required": ["canonical", "header"]}}}, "required": ["mappings"]}
        res = self._ask(
            f"These CSV headers came from a CRM export of {obj}. Map any header that clearly means one "
            "of the canonical fields. Leave out headers that don't clearly match.",
            {"unmapped_headers": unmapped, "canonical_fields_still_missing": missing},
            schema, "map_headers")
        return {m["canonical"]: m["header"] for m in (res or {}).get("mappings", [])}

    def resolve_duplicates(self, pairs):
        """pairs: [{"pair_id", "a": {...}, "b": {...}}] -> [{"pair_id","same_entity","confidence","reason"}]"""
        schema = {"type": "object", "properties": {"verdicts": {"type": "array", "items": {
            "type": "object", "properties": {
                "pair_id": {"type": "string"},
                "same_entity": {"type": "boolean"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"}},
            "required": ["pair_id", "same_entity", "confidence", "reason"]}}}, "required": ["verdicts"]}

        def run(chunk):
            res = self._ask(
                "Decide whether each pair of CRM accounts is the same legal entity (a duplicate record "
                "that should be merged). Abbreviations (FCU, Natl, Inc) and missing domains are common in "
                "duplicates. Different companies that merely share a word (e.g. a card issuer and a "
                "logistics firm) are NOT duplicates. A parent and a separately-sold subsidiary are NOT "
                "duplicates. Use the email domains of each account's contacts as evidence.",
                {"pairs": chunk}, schema, "duplicate_verdicts")
            return (res or {}).get("verdicts")
        return self._batched(pairs, run)

    def classify_titles(self, titles):
        schema = {"type": "object", "properties": {"labels": {"type": "array", "items": {
            "type": "object", "properties": {
                "title": {"type": "string"},
                "persona": {"type": "string", "enum": PERSONAS},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"}},
            "required": ["title", "persona", "confidence", "reason"]}}}, "required": ["labels"]}

        def run(chunk):
            res = self._ask(
                "Assign each job title to the buyer persona it represents for financial-crime compliance "
                "software. 'Not a buyer' is for roles with no stake in compliance, fraud or the purchase.",
                {"titles": chunk}, schema, "persona_labels")
            return (res or {}).get("labels")
        return self._batched(titles, run)

    def classify_industries(self, accounts):
        schema = {"type": "object", "properties": {"labels": {"type": "array", "items": {
            "type": "object", "properties": {
                "id": {"type": "string"},
                "industry": {"type": "string", "enum": INDUSTRIES},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"}},
            "required": ["id", "industry", "confidence", "reason"]}}}, "required": ["labels"]}

        def run(chunk):
            res = self._ask(
                "Assign each account to one industry bucket using its name, domain and current label. "
                "'Not a target' is for companies with no financial-crime compliance need. Use low "
                "confidence when the name alone is ambiguous.",
                {"accounts": chunk}, schema, "industry_labels")
            return (res or {}).get("labels")
        return self._batched(accounts, run)

    def review_deal_notes(self, deals, sources):
        schema = {"type": "object", "properties": {"reviews": {"type": "array", "items": {
            "type": "object", "properties": {
                "id": {"type": "string"},
                "implied_stage": {"type": ["string", "null"], "enum": STAGES + [None],
                                  "description": "Stage the notes imply, or null if notes don't say"},
                "stage_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "at_risk": {"type": "boolean"},
                "risk_reason": {"type": ["string", "null"]},
                "implied_source": {"type": ["string", "null"],
                                   "description": "Where the deal came from, using the team's existing "
                                                  "source values when one fits; null if unknown"},
                "source_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"}},
            "required": ["id", "implied_stage", "stage_confidence", "at_risk", "implied_source",
                         "source_confidence", "reason"]}}}, "required": ["reviews"]}

        def run(chunk):
            res = self._ask(
                "Read each open deal's notes. Say which stage the notes actually imply (only if they "
                "clearly do), whether the deal is at risk (champion left, gone dark, budget moved, lost to "
                "competitor or in-house build), and where the deal originated if the notes say. Only use "
                f"these stages: {', '.join(STAGES)}.",
                {"existing_source_values": sources, "deals": chunk}, schema, "deal_reviews")
            return (res or {}).get("reviews")
        return self._batched(deals, run)

    def map_stages(self, labels):
        schema = {"type": "object", "properties": {"labels": {"type": "array", "items": {
            "type": "object", "properties": {
                "label": {"type": "string"},
                "stage": {"type": ["string", "null"], "enum": STAGES + [None]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reason": {"type": "string"}},
            "required": ["label", "stage", "confidence", "reason"]}}}, "required": ["labels"]}
        res = self._ask(
            f"Map each non-standard deal stage label to the closest standard stage: {', '.join(STAGES)}. "
            "Return null if it can't be mapped with confidence.",
            {"labels": labels}, schema, "stage_map")
        return (res or {}).get("labels") or []
