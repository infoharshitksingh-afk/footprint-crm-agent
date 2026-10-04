"""
Canonical CRM schema. Every CRM export is mapped onto this, so nothing
downstream cares whether the data came from HubSpot, Salesforce, Attio,
Pipedrive or a spreadsheet.

Edit the picklists below to match how your team actually sells.
"""

# canonical field -> header synonyms seen in common CRM exports (lowercased)
FIELDS = {
    "accounts": {
        "id": ["record id", "company id", "account id", "id", "organization id", "org id"],
        "name": ["company name", "account name", "name", "organization", "organization name", "company"],
        "domain": ["company domain name", "domain", "website", "website url", "company website"],
        "industry": ["industry", "vertical", "segment", "industry type"],
        "country": ["country/region", "country", "billing country", "hq country", "region"],
        "owner": ["company owner", "account owner", "owner", "owner name"],
        "created": ["create date", "created date", "created at", "created"],
    },
    "contacts": {
        "id": ["record id", "contact id", "id", "person id", "lead id"],
        "first_name": ["first name", "firstname", "given name"],
        "last_name": ["last name", "lastname", "surname", "family name"],
        "email": ["email", "email address", "work email", "primary email"],
        "title": ["job title", "title", "position", "role"],
        "account_name": ["associated company", "company name", "account name", "company", "organization"],
        "owner": ["contact owner", "owner", "owner name", "lead owner"],
        "source": ["original source", "lead source", "source"],
        "last_activity": ["last activity date", "last activity", "last contacted", "last engagement date"],
    },
    "deals": {
        "id": ["record id", "deal id", "opportunity id", "id"],
        "name": ["deal name", "opportunity name", "name", "title"],
        "stage": ["deal stage", "stage", "opportunity stage", "pipeline stage"],
        "amount": ["amount", "deal amount", "acv", "arr", "value", "opportunity amount"],
        "close_date": ["close date", "expected close date", "closedate"],
        "owner": ["deal owner", "opportunity owner", "owner", "owner name"],
        "account_name": ["associated company", "account name", "company name", "company", "organization"],
        "source": ["lead source", "original source", "source", "deal source", "campaign"],
        "last_activity": ["last activity date", "last activity", "last contacted", "last engagement date"],
        "next_step": ["next step", "next steps", "next action"],
        "notes": ["deal description", "description", "notes", "deal notes", "comments"],
        "created": ["create date", "created date", "created at", "created"],
    },
}

# fields the agent adds when it enriches a record (become new columns on export)
ENRICHED_COLUMNS = {
    ("contacts", "persona"): "Buyer Persona",
}

STAGES_OPEN = ["Discovery", "Demo", "Technical Evaluation", "Proposal", "Negotiation"]
STAGES_CLOSED = ["Closed Won", "Closed Lost"]
STAGES = STAGES_OPEN + STAGES_CLOSED

STAGE_SYNONYMS = {
    "discovery": "Discovery", "discovery call": "Discovery", "qualification": "Discovery",
    "qualified": "Discovery", "appointment scheduled": "Discovery",
    "demo": "Demo", "demo scheduled": "Demo", "demo completed": "Demo",
    "technical evaluation": "Technical Evaluation", "tech eval": "Technical Evaluation",
    "pilot": "Technical Evaluation", "poc": "Technical Evaluation", "back-test": "Technical Evaluation",
    "proposal": "Proposal", "proposal sent": "Proposal", "presentation scheduled": "Proposal",
    "negotiation": "Negotiation", "negotiating": "Negotiation", "contract sent": "Negotiation",
    "decision maker bought-in": "Negotiation",
    "closed won": "Closed Won", "closedwon": "Closed Won", "won": "Closed Won",
    "closed lost": "Closed Lost", "closedlost": "Closed Lost", "lost": "Closed Lost",
}

INDUSTRIES = ["Bank", "Credit Union", "Fintech - Payments", "Fintech - Crypto",
              "Fintech - Lending", "Fintech - BaaS / Neobank", "Fintech - Other", "Not a target"]

INDUSTRY_SYNONYMS = {
    "bank": "Bank", "banking": "Bank", "banks": "Bank", "community bank": "Bank",
    "credit union": "Credit Union", "cu": "Credit Union",
    "payments": "Fintech - Payments", "payment processing": "Fintech - Payments",
    "crypto": "Fintech - Crypto", "cryptocurrency": "Fintech - Crypto", "digital assets": "Fintech - Crypto",
    "lending": "Fintech - Lending", "consumer lending": "Fintech - Lending",
    "baas": "Fintech - BaaS / Neobank", "neobank": "Fintech - BaaS / Neobank",
    "fintech": "Fintech - Other", "fin tech": "Fintech - Other",
}
# deliberately NOT mapped by rule: "financial services" (bank? lender? wealth?) -> Claude decides

COUNTRY_SYNONYMS = {
    "us": "United States", "usa": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "united states": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "united kingdom": "United Kingdom",
    "great britain": "United Kingdom", "gb": "United Kingdom", "england": "United Kingdom",
    "ca": "Canada", "canada": "Canada",
}

# Footprint's buyers, roughly. Order matters: first match wins.
PERSONAS = ["Compliance Executive", "BSA/AML Leader", "Fraud & Risk Leader", "Compliance Operations",
            "Executive Sponsor", "Technical Evaluator", "Procurement / Finance", "Not a buyer"]

PERSONA_RULES = [
    ("Compliance Executive", ["chief compliance", "cco", "head of compliance", "vp compliance", "vp, compliance"]),
    ("BSA/AML Leader", ["bsa", "aml", "mlro", "financial crime", "fincrime", "sanctions"]),
    ("Fraud & Risk Leader", ["fraud", "chief risk", "head of risk", "cro", "risk officer"]),
    ("Compliance Operations", ["kyc", "edd", "compliance analyst", "investigation", "risk & compliance",
                               "compliance manager"]),
    ("Executive Sponsor", ["ceo", "coo", "founder", "president", "general manager"]),
    ("Technical Evaluator", ["engineer", "engineering", "cto", "product", "developer", "architect"]),
    ("Procurement / Finance", ["procurement", "controller", "cfo", "finance", "purchasing", "vendor management"]),
]

# words that mark an event/source in free-text notes (rule fallback when no API key)
SOURCE_KEYWORDS = [
    ("money20/20", "Event - Money20/20"), ("money 20/20", "Event - Money20/20"),
    ("acams", "Event - ACAMS"), ("sibos", "Event - Sibos"), ("fintech meetup", "Event - Fintech Meetup"),
    ("demo form", "Inbound - Demo Request"), ("demo request", "Inbound - Demo Request"),
    ("website", "Inbound - Website"), ("referr", "Referral"), ("intro from", "Referral"),
    ("partner", "Partner"),
]

PERSONAL_EMAIL_TYPOS = {"gmial.com": "gmail.com", "gamil.com": "gmail.com", "gmai.com": "gmail.com",
                        "hotmial.com": "hotmail.com", "yaho.com": "yahoo.com", "outlok.com": "outlook.com"}

# How the agent judges hygiene. Tune to taste.
RULES = {
    "stale_days": 30,          # open deal with no activity for this long = stale
    "fuzzy_name_threshold": 0.72,
}
