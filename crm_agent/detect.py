"""
Step 2: find what's wrong and propose a fix for each problem.

Rules handle everything deterministic (formatting, exact duplicates, missing
fields, stale deals). Claude is called only for judgment calls. Every proposal
records who made it ("rule" or "claude"), how confident it is, and why.

Nothing here changes data. It only produces proposals for a human to review.
"""
import re
import statistics
from collections import Counter, defaultdict
from datetime import date
from difflib import SequenceMatcher

from .schema import (COUNTRY_SYNONYMS, INDUSTRY_SYNONYMS, PERSONA_RULES, PERSONAL_EMAIL_TYPOS,
                     RULES, SOURCE_KEYWORDS, STAGE_SYNONYMS, STAGES, STAGES_CLOSED)

# how much an issue matters to the forecast; drives sort order in the review queue
WEIGHT = {"forecast": 1.0, "attribution": 0.6, "hygiene": 0.3, "enrichment": 0.1}

ISSUES = {
    # issue key: (label, category)
    "duplicate_account": ("Duplicate account", "forecast"),
    "possible_duplicate_account": ("Possible duplicate account", "forecast"),
    "orphan_deal": ("Deal not linked to an account", "forecast"),
    "missing_amount": ("Open deal has no amount", "forecast"),
    "missing_close_date": ("Open deal has no close date", "forecast"),
    "past_close_date": ("Close date already passed", "forecast"),
    "stage_mismatch": ("Stage contradicts deal notes", "forecast"),
    "deal_at_risk": ("Notes say deal is at risk", "forecast"),
    "nonstandard_stage": ("Non-standard stage label", "forecast"),
    "stale_deal": ("No activity in 30+ days", "forecast"),
    "missing_source": ("Deal has no source", "attribution"),
    "no_next_step": ("Open deal has no next step", "hygiene"),
    "duplicate_contact": ("Duplicate contact", "hygiene"),
    "orphan_contact": ("Contact not linked to an account", "hygiene"),
    "invalid_email": ("Invalid email", "hygiene"),
    "email_format": ("Email formatting", "hygiene"),
    "domain_format": ("Domain formatting", "hygiene"),
    "missing_domain": ("Account has no domain", "hygiene"),
    "industry": ("Non-standard industry", "hygiene"),
    "country": ("Non-standard country", "hygiene"),
    "persona": ("Buyer persona untagged", "enrichment"),
}

LEGAL = {"inc", "llc", "ltd", "corp", "corporation", "co", "company", "the", "plc", "na", "n a"}
ABBREV = {"fcu": "federal credit union", "cu": "credit union", "natl": "national", "nat'l": "national",
          "intl": "international", "fin": "financial", "svcs": "services", "&": "and", "bk": "bank"}
GENERIC = {"bank", "bancorp", "bancshares", "national", "trust", "federal", "credit", "union", "savings",
           "financial", "and", "community", "capital", "group", "holdings", "uk", "us"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
FREE_MAIL = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com"}


# ---------------------------------------------------------------- helpers
def norm_name(s):
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9' ]+", " ", s)
    words = []
    for w in s.split():
        words.extend(ABBREV.get(w, w).split())
    return " ".join(w for w in words if w not in LEGAL)


def core_name(s):
    words = [w for w in norm_name(s).split() if w not in GENERIC]
    return " ".join(words) or norm_name(s)


def norm_domain(s):
    s = (s or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    s = re.sub(r"^www\.", "", s)
    return s.split("/")[0]


def email_domain(e):
    e = (e or "").strip().lower()
    return e.split("@", 1)[1] if "@" in e else ""


def parse_amount(s):
    s = re.sub(r"[^0-9.]", "", s or "")
    try:
        return float(s) if s else None
    except ValueError:
        return None


def parse_date(s):
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        for fmt in ("%m/%d/%Y", "%d/%m/%Y", "%m/%d/%y"):
            try:
                from datetime import datetime
                return datetime.strptime(s.strip(), fmt).date()
            except ValueError:
                pass
    return None


def canon_stage(s):
    if s in STAGES:
        return s
    return STAGE_SYNONYMS.get((s or "").strip().lower())


class UnionFind:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


# ---------------------------------------------------------------- scanner
class Scanner:
    def __init__(self, data, judge, as_of=None):
        self.d = data
        self.judge = judge
        self.as_of = as_of or date.today()
        self.proposals = []
        self.notes = []          # human-readable log of what the agent decided not to do
        self.acc = {a["id"]: a for a in data["accounts"]}
        self.by_name = {}
        for a in data["accounts"]:
            self.by_name.setdefault(norm_name(a["name"]), a["id"])
        self.by_domain = defaultdict(list)
        for a in data["accounts"]:
            if norm_domain(a["domain"]):
                self.by_domain[norm_domain(a["domain"])].append(a["id"])
        self.survivor = {}       # account id -> survivor id after proposed merges

    # -- proposal factory
    def propose(self, obj, rec, issue, action, reason, confidence, source, field=None, old="", new="",
                merge_ids=None, extra=None):
        label, category = ISSUES[issue]
        p = {
            "id": f"P{len(self.proposals) + 1:04d}",
            "object": obj, "record_id": rec["id"], "record_label": self.label(obj, rec),
            "owner": rec.get("owner", ""),
            "issue": issue, "issue_label": label, "category": category,
            "action": action, "field": field, "old": old, "new": new,
            "merge_ids": merge_ids or [], "reason": reason,
            "confidence": round(float(confidence), 2), "source": source,
        }
        if extra:
            p.update(extra)
        self.proposals.append(p)
        return p

    def label(self, obj, r):
        if obj == "contacts":
            n = f"{r['first_name']} {r['last_name']}".strip()
            return f"{n} <{r['email']}>" if r["email"] else n
        return r["name"] or r["id"]

    def src(self, used_claude):
        return "claude" if used_claude else "rule"

    def link_account(self, name, email=""):
        """Resolve a free-text company name (or email domain) to an account id."""
        n = norm_name(name)
        if n and n in self.by_name:
            return self.by_name[n], 1.0, "exact name match"
        dom = email_domain(email)
        if dom and dom in self.by_domain:
            return self.by_domain[dom][0], 0.95, f"email domain {dom} matches the account's domain"
        if n:
            best, score = None, 0.0
            for key, aid in self.by_name.items():
                s = SequenceMatcher(None, n, key).ratio()
                if core_name(name) and core_name(name) == core_name(self.acc[aid]["name"]):
                    s = max(s, 0.9)
                if s > score:
                    best, score = aid, s
            if best and score >= 0.85:
                return best, round(score, 2), f"name is a close match ({score:.0%})"
            # short form: every word of the guess starts the account's name ("Quanta" -> "Quanta Neobank")
            words = n.split()
            hits = [aid for key, aid in self.by_name.items() if key.split()[:len(words)] == words]
            if len(set(hits)) == 1:
                return hits[0], 0.8, f"'{name}' is the start of the account name '{self.acc[hits[0]]['name']}'"
        return None, 0, ""

    def check_exact_link(self, obj, rec):
        """Company name normalizes to an account but isn't spelled the same way. Most CRMs associate
        on the exact string, so 'Northpoint Natl Bank' silently doesn't roll up to the account."""
        aid = self.by_name.get(norm_name(rec["account_name"]))
        if aid and self.survivor.get(aid, aid) == aid and rec["account_name"] != self.acc[aid]["name"]:
            issue = "orphan_deal" if obj == "deals" else "orphan_contact"
            self.propose(obj, rec, issue, "link", f"'{rec['account_name']}' is written differently from the "
                         f"account record '{self.acc[aid]['name']}', so it doesn't roll up.", 0.93, "rule",
                         "account_name", rec["account_name"], self.acc[aid]["name"])
        return aid

    # ================================================================ run
    def run(self):
        self.scan_accounts()
        self.scan_contacts()
        self.scan_deals()
        return self.proposals, self.notes

    # ---------------------------------------------------------- accounts
    def scan_accounts(self):
        accts = self.d["accounts"]
        uf = UnionFind()
        why = defaultdict(list)
        conf = defaultdict(lambda: 1.0)
        source = defaultdict(set)

        # 1. exact duplicates by normalized domain
        for dom, ids in self.by_domain.items():
            for other in ids[1:]:
                uf.union(other, ids[0])
            if len(ids) > 1:
                key = ids[0]
                why[key].append(f"share the domain {dom}")
                conf[key] = min(conf[key], 0.97)
                source[key].add("rule")

        # 1b. exact duplicates by name once legal suffixes and punctuation are stripped
        by_norm = defaultdict(list)
        for a in accts:
            by_norm[norm_name(a["name"])].append(a)
        for n, group in by_norm.items():
            doms = {norm_domain(a["domain"]) for a in group if a["domain"]}
            if len(group) > 1 and len(doms) <= 1:
                for other in group[1:]:
                    uf.union(other["id"], group[0]["id"])
                key = uf.find(group[0]["id"])
                why[key].append("have the same name once abbreviations (FCU, Natl), suffixes (Inc, LLC) and punctuation are normalized")
                conf[key] = min(conf[key], 0.95)
                source[key].add("rule")

        # 2. fuzzy candidates, blocked on first 3 letters of the core name
        blocks = defaultdict(list)
        for a in accts:
            c = core_name(a["name"])
            blocks[c[:3]].append(a)
        pairs = []
        for block in blocks.values():
            for i, a in enumerate(block):
                for b in block[i + 1:]:
                    if uf.find(a["id"]) == uf.find(b["id"]):
                        continue
                    ca, cb = core_name(a["name"]), core_name(b["name"])
                    if ca == cb or SequenceMatcher(None, ca, cb).ratio() >= RULES["fuzzy_name_threshold"]:
                        pairs.append((a, b))

        if pairs:
            contact_domains = defaultdict(Counter)
            for c in self.d["contacts"]:
                aid = self.by_name.get(norm_name(c["account_name"]))
                if aid and email_domain(c["email"]):
                    contact_domains[aid][email_domain(c["email"])] += 1
            payload = [{
                "pair_id": f"{a['id']}|{b['id']}",
                "a": {"name": a["name"], "domain": norm_domain(a["domain"]), "industry": a["industry"],
                      "country": a["country"], "contact_email_domains": list(contact_domains[a["id"]])[:3]},
                "b": {"name": b["name"], "domain": norm_domain(b["domain"]), "industry": b["industry"],
                      "country": b["country"], "contact_email_domains": list(contact_domains[b["id"]])[:3]},
            } for a, b in pairs]
            verdicts = {v["pair_id"]: v for v in self.judge.resolve_duplicates(payload)}
            for a, b in pairs:
                v = verdicts.get(f"{a['id']}|{b['id']}")
                if v is None:
                    # no Claude: flag only when core names are identical, never auto-merge
                    if core_name(a["name"]) == core_name(b["name"]):
                        self.propose("accounts", a, "possible_duplicate_account", "flag",
                                     f"'{a['name']}' and '{b['name']}' have the same core name. Needs a human "
                                     "check (set ANTHROPIC_API_KEY to have Claude judge this).",
                                     0.5, "rule", merge_ids=[b["id"]], extra={"merge_names": [b["name"]]})
                    continue
                if v["same_entity"] and v["confidence"] >= 0.6:
                    uf.union(b["id"], a["id"])
                    key = uf.find(a["id"])
                    why[key].append(v["reason"])
                    conf[key] = min(conf[key], v["confidence"])
                    source[key].add("claude")
                else:
                    self.notes.append(f"Kept separate: '{a['name']}' vs '{b['name']}'. {v['reason']}")

        # 3. turn groups into one merge proposal each
        groups = defaultdict(list)
        for a in accts:
            groups[uf.find(a["id"])].append(a)
        pipe = self.open_pipeline_by_account()
        n_contacts = Counter(self.by_name.get(norm_name(c["account_name"])) for c in self.d["contacts"])
        for root, members in groups.items():
            if len(members) < 2:
                continue
            survivor = max(members, key=lambda a: (bool(a["domain"]), n_contacts[a["id"]],
                                                   pipe.get(a["id"], 0), len(a["name"])))
            losers = [m for m in members if m is not survivor]
            for m in members:
                self.survivor[m["id"]] = survivor["id"]
            # gather reasons from every union root that ended up in this group
            reasons = []
            srcs = set()
            c = 1.0
            for k in list(why):
                if uf.find(k) == root:
                    reasons += why[k]
                    srcs |= source[k]
                    c = min(c, conf[k])
            names = ", ".join(f"'{m['name']}'" for m in losers)
            self.propose(
                "accounts", survivor, "duplicate_account", "merge",
                f"{names} {'is' if len(losers) == 1 else 'are'} the same company as '{survivor['name']}': "
                + "; ".join(dict.fromkeys(reasons)) + ". Keep the most complete record (domain, contacts); "
                "its deals and contacts move over.",
                c, "claude" if "claude" in srcs else "rule", merge_ids=[m["id"] for m in losers],
                extra={"merge_names": [m["name"] for m in losers]})

        # 4. field hygiene on surviving accounts
        unknown_industry = []
        for a in accts:
            if self.survivor.get(a["id"], a["id"]) != a["id"]:
                continue  # merging away; don't clean a record that's about to disappear
            nd = norm_domain(a["domain"])
            if a["domain"] and nd != a["domain"].strip():
                self.propose("accounts", a, "domain_format", "update", "Strip protocol, www and paths so "
                             "domains match across records and enrichment tools.", 0.99, "rule",
                             "domain", a["domain"], nd)
            if not nd:
                doms = Counter(email_domain(c["email"]) for c in self.d["contacts"]
                               if self.by_name.get(norm_name(c["account_name"])) == a["id"]
                               and email_domain(c["email"]) and email_domain(c["email"]) not in FREE_MAIL)
                if doms:
                    top, n = doms.most_common(1)[0]
                    if top not in self.by_domain:
                        self.propose("accounts", a, "missing_domain", "update",
                                     f"{n} contact(s) at this account use @{top}.", 0.85 if n > 1 else 0.7,
                                     "rule", "domain", "", top)
                else:
                    self.propose("accounts", a, "missing_domain", "flag", "No domain and no contacts to "
                                 "infer it from. Domain is the key that stops duplicates coming back.",
                                 1.0, "rule", "domain")
            ind = INDUSTRY_SYNONYMS.get(a["industry"].strip().lower())
            if ind and ind != a["industry"]:
                self.propose("accounts", a, "industry", "update", f"'{a['industry']}' maps to the standard "
                             f"picklist value '{ind}'.", 0.95, "rule", "industry", a["industry"], ind)
            elif not ind and a["industry"] not in INDUSTRY_SYNONYMS.values():
                unknown_industry.append(a)
            ctry = COUNTRY_SYNONYMS.get(a["country"].strip().lower())
            if ctry and ctry != a["country"]:
                self.propose("accounts", a, "country", "update", f"Standardize '{a['country']}' so territory "
                             "and regional reports group correctly.", 0.99, "rule", "country", a["country"], ctry)

        if unknown_industry:
            labels = {l["id"]: l for l in self.judge.classify_industries(
                [{"id": a["id"], "name": a["name"], "domain": norm_domain(a["domain"]),
                  "current_label": a["industry"]} for a in unknown_industry])}
            for a in unknown_industry:
                l = labels.get(a["id"])
                if l:
                    self.propose("accounts", a, "industry", "update", l["reason"], l["confidence"], "claude",
                                 "industry", a["industry"], l["industry"])
                else:
                    self.propose("accounts", a, "industry", "flag",
                                 f"'{a['industry'] or 'blank'}' isn't on the picklist and can't be mapped by "
                                 "rule.", 1.0, "rule", "industry", a["industry"])

    # ---------------------------------------------------------- contacts
    def scan_contacts(self):
        cs = self.d["contacts"]
        # email formatting + validity
        for c in cs:
            raw, e = c["email"], c["email"].strip().lower()
            dom = email_domain(e)
            if dom in PERSONAL_EMAIL_TYPOS:
                fixed = e.replace(dom, PERSONAL_EMAIL_TYPOS[dom])
                self.propose("contacts", c, "invalid_email", "update", f"'{dom}' is a common typo of "
                             f"{PERSONAL_EMAIL_TYPOS[dom]}. Also a personal address; worth finding a work email.",
                             0.75, "rule", "email", raw, fixed)
            elif e and not EMAIL_RE.match(e):
                self.propose("contacts", c, "invalid_email", "flag", f"'{raw}' isn't a deliverable address. "
                             "Sequences to this contact will bounce.", 1.0, "rule", "email", raw)
            elif not e:
                self.propose("contacts", c, "invalid_email", "flag", "No email on file.", 1.0, "rule", "email")
            elif e != raw:
                self.propose("contacts", c, "email_format", "update", "Trim spaces and lowercase so dedupe "
                             "and email sync match it.", 0.99, "rule", "email", raw, e)

        # duplicates by normalized email
        by_email = defaultdict(list)
        for c in cs:
            e = c["email"].strip().lower()
            if EMAIL_RE.match(e):
                by_email[e].append(c)
        merged_away = set()
        for e, group in by_email.items():
            if len(group) < 2:
                continue
            keep = max(group, key=lambda c: (sum(bool(c[k]) for k in ("first_name", "last_name", "title",
                                                                        "account_name", "source")),
                                             c["last_activity"]))
            losers = [c for c in group if c is not keep]
            merged_away |= {c["id"] for c in losers}
            self.propose("contacts", keep, "duplicate_contact", "merge",
                         f"{len(group)} records share {e}. Keep the most complete one; activity history "
                         "follows the merge in your CRM.", 0.98, "rule", merge_ids=[c["id"] for c in losers],
                         extra={"merge_names": [f"{c['first_name']} {c['last_name']} ({c['id']})" for c in losers]})

        # account links + personas
        untagged = defaultdict(list)
        for c in cs:
            if c["id"] in merged_away:
                continue
            exact = self.check_exact_link("contacts", c)
            if not exact:
                aid, score, how = self.link_account(c["account_name"], c["email"])
                if aid:
                    target = self.acc[self.survivor.get(aid, aid)]
                    self.propose("contacts", c, "orphan_contact", "link",
                                 f"Not linked to a known account; {how}.", score, "rule", "account_name",
                                 c["account_name"], target["name"])
                else:
                    self.propose("contacts", c, "orphan_contact", "flag",
                                 "No account and nothing in the email or company field to match on.",
                                 1.0, "rule", "account_name", c["account_name"])
            if c["title"]:
                persona = rule_persona(c["title"])
                if persona:
                    self.propose("contacts", c, "persona", "update", f"Title '{c['title']}' matches the "
                                 f"{persona} rule.", 0.9, "rule", "persona", "", persona)
                else:
                    untagged[c["title"]].append(c)

        if untagged:
            labels = {l["title"]: l for l in self.judge.classify_titles(list(untagged))}
            for title, group in untagged.items():
                l = labels.get(title)
                for c in group:
                    if l:
                        self.propose("contacts", c, "persona", "update", l["reason"], l["confidence"],
                                     "claude", "persona", "", l["persona"])
                    else:
                        self.propose("contacts", c, "persona", "flag", f"No rule covers the title '{title}'.",
                                     1.0, "rule", "persona")

    # ---------------------------------------------------------- deals
    def open_pipeline_by_account(self):
        out = Counter()
        for dl in self.d["deals"]:
            st = canon_stage(dl["stage"])
            if st in STAGES_CLOSED:
                continue
            aid = self.by_name.get(norm_name(dl["account_name"]))
            amt = parse_amount(dl["amount"])
            if aid and amt:
                out[aid] += amt
        return out

    def scan_deals(self):
        ds = self.d["deals"]
        sources_seen = sorted({d["source"] for d in ds if d["source"]})
        unknown_stages = defaultdict(list)
        open_with_notes = []

        for dl in ds:
            st = canon_stage(dl["stage"])
            if st is None and dl["stage"]:
                unknown_stages[dl["stage"]].append(dl)
            elif st and st != dl["stage"]:
                self.propose("deals", dl, "nonstandard_stage", "update", f"'{dl['stage']}' is a variant of "
                             f"'{st}'. Mixed labels split the pipeline report.", 0.97, "rule", "stage",
                             dl["stage"], st)
            if st in STAGES_CLOSED:
                continue
            dl["_open"] = True

            # account link
            self.check_exact_link("deals", dl)
            if not self.by_name.get(norm_name(dl["account_name"])):
                guess = dl["account_name"] or dl["name"].split(" - ")[0]
                aid, score, how = self.link_account(guess)
                if aid:
                    target = self.acc[self.survivor.get(aid, aid)]
                    basis = how if dl["account_name"] else f"deal name starts with '{guess}'; {how}"
                    self.propose("deals", dl, "orphan_deal", "link", f"Pipeline not rolling up to any "
                                 f"account; {basis}.", min(score, 0.9), "rule", "account_name",
                                 dl["account_name"], target["name"])
                else:
                    self.propose("deals", dl, "orphan_deal", "flag", "Deal isn't linked to an account and "
                                 "nothing matches.", 1.0, "rule", "account_name", dl["account_name"])

            if parse_amount(dl["amount"]) is None:
                self.propose("deals", dl, "missing_amount", "flag", "Open deal with no amount is invisible "
                             "to the forecast. Owner needs to enter one.", 1.0, "rule", "amount")
            cd = parse_date(dl["close_date"])
            if not cd:
                self.propose("deals", dl, "missing_close_date", "flag", "No close date, so this deal can't "
                             "land in any forecast period.", 1.0, "rule", "close_date")
            elif cd < self.as_of:
                self.propose("deals", dl, "past_close_date", "flag", f"Close date {cd} passed "
                             f"{(self.as_of - cd).days} days ago and the deal is still open. Either it slipped "
                             "or it closed and nobody updated it.", 1.0, "rule", "close_date", dl["close_date"])
            la = parse_date(dl["last_activity"])
            if la and (self.as_of - la).days > RULES["stale_days"]:
                self.propose("deals", dl, "stale_deal", "flag", f"No logged activity for "
                             f"{(self.as_of - la).days} days.", 1.0, "rule", "last_activity", dl["last_activity"])
            if not dl["next_step"]:
                self.propose("deals", dl, "no_next_step", "flag", "Open deal with no next step.", 1.0, "rule",
                             "next_step")
            if dl["notes"]:
                open_with_notes.append(dl)
            elif not dl["source"]:
                self.propose("deals", dl, "missing_source", "flag", "No source and no notes to infer one. "
                             "Event and marketing ROI can't count this deal.", 1.0, "rule", "source")

        # non-standard stage labels -> Claude
        if unknown_stages:
            mapped = {m["label"]: m for m in self.judge.map_stages(list(unknown_stages))}
            for label, group in unknown_stages.items():
                m = mapped.get(label)
                for dl in group:
                    if m and m["stage"]:
                        self.propose("deals", dl, "nonstandard_stage", "update", m["reason"], m["confidence"],
                                     "claude", "stage", label, m["stage"])
                    else:
                        self.propose("deals", dl, "nonstandard_stage", "flag", f"'{label}' isn't a stage in "
                                     "the pipeline.", 1.0, "rule", "stage", label)

        # deal notes -> Claude (stage reality, risk, attribution); keyword fallback for source
        reviews = {}
        if open_with_notes:
            reviews = {r["id"]: r for r in self.judge.review_deal_notes(
                [{"id": d["id"], "name": d["name"], "current_stage": canon_stage(d["stage"]) or d["stage"],
                  "current_source": d["source"], "notes": d["notes"]} for d in open_with_notes],
                sources_seen)}
        for dl in open_with_notes:
            r = reviews.get(dl["id"])
            cur = canon_stage(dl["stage"]) or dl["stage"]
            if r:
                if r.get("implied_stage") and r["implied_stage"] != cur and r["stage_confidence"] >= 0.6:
                    self.propose("deals", dl, "stage_mismatch", "update", r["reason"], r["stage_confidence"],
                                 "claude", "stage", dl["stage"], r["implied_stage"])
                if r.get("at_risk"):
                    self.propose("deals", dl, "deal_at_risk", "flag", r.get("risk_reason") or r["reason"], 0.8,
                                 "claude", "stage", dl["stage"])
            if not dl["source"]:
                if r and r.get("implied_source") and r["source_confidence"] >= 0.6:
                    self.propose("deals", dl, "missing_source", "update", f"Notes: \"{dl['notes'][:90]}\"",
                                 r["source_confidence"], "claude", "source", "", r["implied_source"])
                else:
                    kw = keyword_source(dl["notes"])
                    if kw:
                        self.propose("deals", dl, "missing_source", "update", f"Notes mention it: "
                                     f"\"{dl['notes'][:90]}\"", 0.7, "rule", "source", "", kw)
                    else:
                        self.propose("deals", dl, "missing_source", "flag", "No source recorded.", 1.0,
                                     "rule", "source")


def rule_persona(title):
    t = f" {title.lower()} "
    for persona, keys in PERSONA_RULES:
        for k in keys:
            # short keys (cco, cro, ceo...) must match as whole words
            if len(k) <= 4 and re.search(rf"\b{re.escape(k)}\b", t):
                return persona
            if len(k) > 4 and k in t:
                return persona
    return None


def keyword_source(text):
    t = (text or "").lower()
    for k, v in SOURCE_KEYWORDS:
        if k in t:
            return v
    return None
