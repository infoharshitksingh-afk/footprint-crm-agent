"""
Generates a deliberately messy, synthetic CRM export that looks like a
compliance-software startup selling to banks and fintechs.

Every company and person here is fictional. The mess is planted on purpose:
duplicate accounts (some obvious, some only a human or an LLM would catch),
look-alike companies that are NOT duplicates, orphaned contacts and deals,
stale pipeline, missing amounts, and event attribution buried in deal notes.

Headers mimic a HubSpot export so the field-mapping step has real work to do.

Usage:  python demo/generate_demo.py            (writes demo/data/*.csv)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

AS_OF = date(2026, 10, 4)
random.seed(7)
OUT = Path(__file__).parent / "data"
OWNERS = ["Maya Chen", "Derek Okafor", "Priya Raman", "Tom Becker", "Lena Ortiz"]


def d(days_ago):
    return (AS_OF - timedelta(days=days_ago)).isoformat()


# ---------------------------------------------------------------- accounts
# (name, domain, industry, country)
ACCOUNTS = [
    ("First Harbor Bank", "firstharborbank.com", "Banking", "USA"),
    ("Granite Trust Bancorp", "granitetrust.com", "bank", "United States"),
    ("Meridian Community Bank", "meridiancb.com", "Banking", "US"),
    ("Meridian Credit Union", "meridiancu.org", "Credit Union", "US"),
    ("Silverline Federal Credit Union", "silverlinefcu.org", "Credit Union", "USA"),
    ("Northpoint National Bank", "northpointbank.com", "Financial Services", "United States"),
    ("Cedar Valley Bank & Trust", "cedarvalleybank.com", "banking", "U.S."),
    ("Bayside Savings Bank", "baysidesavings.com", "Banking", "USA"),
    ("Keystone Commerce Bank", "keystonecommerce.com", "", "US"),
    ("Prairie State Bank", "prairiestatebank.com", "Banking", "United States of America"),
    ("Lakeshore Capital Bank", "lakeshorecapital.com", "Financial Services", "USA"),
    ("Harborline Bank UK", "harborline.co.uk", "Banking", "UK"),
    ("Lumen Pay", "lumenpay.com", "Fintech", "USA"),
    ("Arcpoint Wallet", "arcpoint.com", "FinTech", "US"),
    ("Tallyhaus", "tallyhaus.com", "fin tech", "United States"),
    ("Coinvault Exchange", "coinvault.io", "Crypto", "USA"),
    ("NovaRemit", "novaremit.com", "Payments", "US"),
    ("Brightledger", "brightledger.com", "Fintech", "USA"),
    ("Kestrel Card", "kestrelcard.io", "Payments", "USA"),
    ("Kestrel Logistics", "kestrel-logistics.com", "Logistics", "USA"),
    ("Orbit Payroll", "orbitpayroll.com", "", "US"),
    ("Cadence Credit", "cadencecredit.com", "Lending", "USA"),
    ("Stackbridge", "stackbridge.io", "Fintech", "Canada"),
    ("Paywise", "paywise.com", "Payments", "United Kingdom"),
    ("Fernhill Lending", "fernhill.com", "lending", "USA"),
    ("Quanta Neobank", "quantabank.app", "Fintech", "USA"),
    ("Ridgeway Money", "ridgewaymoney.com", "", "USA"),
    ("Solace Remittance", "solaceremit.com", "Payments", "US"),
    ("Driftwood Card Co", "driftwoodcard.com", "Fintech", "USA"),
    ("Helix Digital Assets", "helixassets.io", "crypto", "USA"),
    ("Tidewater Bank", "tidewaterbank.com", "Banking", "USA"),
    ("Summit Rock Credit Union", "summitrockcu.org", "Credit Union", "US"),
    ("Copperline Payments", "copperline.com", "Payments", "USA"),
    ("Evergreen BaaS", "evergreenbaas.com", "Fintech", "USA"),
    ("Juniper Wealth", "juniperwealth.com", "Wealth Management", "USA"),
]

# planted duplicates: (name, domain, industry, country, duplicate_of)
DUPES = [
    ("First Harbor Bancorp", "firstharborbank.com", "Bank", "US"),        # same domain
    ("LumenPay Inc.", "lumenpay.com", "Payments", "USA"),                  # same domain
    ("ArcPoint", "www.arcpoint.com", "Fintech", "USA"),                    # domain w/ www
    ("Northpoint Bank", "https://northpointbank.com/", "Banking", "US"),   # domain w/ scheme
    ("Granite Trust", "", "Banking", "USA"),                               # fuzzy, no domain
    ("Silverline FCU", "", "Credit Union", "USA"),                         # abbreviation
    ("Tallyhaus Inc", "", "", "US"),                                       # fuzzy, no domain
    ("Coinvault", "coinvault.io", "crypto", "USA"),                        # same domain
]

accounts = []
rid = 1000
for n, dom, ind, ctry in ACCOUNTS + DUPES:
    rid += 1
    accounts.append({
        "Record ID": str(rid),
        "Company name": n,
        "Company Domain Name": dom,
        "Industry": ind,
        "Country/Region": ctry,
        "Company owner": random.choice(OWNERS),
        "Create Date": d(random.randint(60, 700)),
    })

# ---------------------------------------------------------------- contacts
FIRST = ["Alicia", "Ben", "Carmen", "David", "Elena", "Farid", "Grace", "Hector", "Ines", "James",
         "Kira", "Luis", "Mona", "Nate", "Olu", "Paula", "Quinn", "Rosa", "Sam", "Tara", "Uma",
         "Victor", "Wen", "Ximena", "Yusuf", "Zoe"]
LAST = ["Abbott", "Banerjee", "Castillo", "Doyle", "Eze", "Fischer", "Gupta", "Hale", "Ito",
        "Jensen", "Kowalski", "Lindqvist", "Moreau", "Nakamura", "Osei", "Park", "Quintero",
        "Reyes", "Silva", "Tanaka", "Ueda", "Vance", "Walsh", "Xu", "Young", "Zimmer"]
TITLES = ["Chief Compliance Officer", "BSA Officer", "VP, BSA/AML", "BSA/AML Manager",
          "Head of Fraud Operations", "Director, Financial Crimes", "KYC Operations Lead",
          "Sr Mgr - Risk & Compliance", "MLRO", "Head of Trust & Safety", "CEO", "COO",
          "VP Engineering", "Staff Software Engineer", "Head of Product", "Procurement Manager",
          "Compliance Analyst", "EDD Team Lead", "Chief Risk Officer", "Sanctions Screening Manager",
          "Dir. of Customer Ops", "Founder", "Controller", "Fraud Strategy Analyst"]
SOURCES = ["Outbound", "Inbound - Website", "Referral", "Event - Money20/20", "Event - ACAMS",
           "Partner", "Inbound - Demo Request"]


def slug_email(first, last, domain):
    return f"{first.lower()}.{last.lower()}@{domain}"


contacts = []
crid = 5000
base_accounts = accounts[: len(ACCOUNTS)]
for acct in base_accounts:
    for _ in range(random.randint(2, 5)):
        crid += 1
        f, l = random.choice(FIRST), random.choice(LAST)
        contacts.append({
            "Record ID": str(crid),
            "First Name": f,
            "Last Name": l,
            "Email": slug_email(f, l, acct["Company Domain Name"]),
            "Job Title": random.choice(TITLES),
            "Associated Company": acct["Company name"],
            "Contact owner": acct["Company owner"],
            "Original Source": random.choice(SOURCES) if random.random() > 0.25 else "",
            "Last Activity Date": d(random.randint(1, 200)),
        })

# planted contact problems
def add_contact(**kw):
    global crid
    crid += 1
    row = {"Record ID": str(crid), "First Name": "", "Last Name": "", "Email": "", "Job Title": "",
           "Associated Company": "", "Contact owner": random.choice(OWNERS), "Original Source": "",
           "Last Activity Date": d(random.randint(5, 120))}
    row.update(kw)
    contacts.append(row)

# duplicate contacts (same email, different case / slightly different name)
c0 = contacts[3]
add_contact(**{"First Name": c0["First Name"], "Last Name": c0["Last Name"],
               "Email": c0["Email"].upper(), "Job Title": c0["Job Title"],
               "Associated Company": c0["Associated Company"]})
c1 = contacts[20]
add_contact(**{"First Name": c1["First Name"][0] + ".", "Last Name": c1["Last Name"],
               "Email": " " + c1["Email"] + " ", "Job Title": "",
               "Associated Company": c1["Associated Company"]})
# invalid emails
add_contact(**{"First Name": "Rachel", "Last Name": "Ng", "Email": "rachel.ng@", "Job Title": "BSA Officer",
               "Associated Company": "Tidewater Bank"})
add_contact(**{"First Name": "Omar", "Last Name": "Haddad", "Email": "n/a", "Job Title": "Head of Compliance",
               "Associated Company": "Fernhill Lending"})
add_contact(**{"First Name": "Ivy", "Last Name": "Brandt", "Email": "ivy.brandt@gmial.com",
               "Job Title": "AML Investigations Manager", "Associated Company": "Copperline Payments"})
# orphans whose email domain gives the account away
add_contact(**{"First Name": "Marcus", "Last Name": "Lee", "Email": "marcus.lee@quantabank.app",
               "Job Title": "Head of Financial Crime", "Associated Company": ""})
add_contact(**{"First Name": "Sofia", "Last Name": "Marin", "Email": "smarin@prairiestatebank.com",
               "Job Title": "Deputy BSA Officer", "Associated Company": ""})
add_contact(**{"First Name": "Jonah", "Last Name": "Weiss", "Email": "jonah@evergreenbaas.com",
               "Job Title": "Partner Risk Lead", "Associated Company": ""})
# contacts parked on duplicate accounts
add_contact(**{"First Name": "Hannah", "Last Name": "Cole", "Email": "hcole@firstharborbank.com",
               "Job Title": "Chief Compliance Officer", "Associated Company": "First Harbor Bancorp"})
add_contact(**{"First Name": "Raj", "Last Name": "Mehta", "Email": "raj@lumenpay.com",
               "Job Title": "Head of Risk", "Associated Company": "LumenPay Inc."})

# ---------------------------------------------------------------- deals
STAGES_CLEAN = ["Discovery", "Demo", "Technical Evaluation", "Proposal", "Negotiation"]
STAGE_MESS = {"Demo": ["demo", "Demo Scheduled"], "Proposal": ["Proposal Sent", "proposal"],
              "Negotiation": ["Negotiating"], "Discovery": ["discovery call"]}
PRODUCTS = ["KYC + Percy", "Transaction Monitoring", "EDD Automation", "Sanctions Screening",
            "Full Platform", "Fraud Investigations"]

deals = []
drid = 9000


def add_deal(**kw):
    global drid
    drid += 1
    row = {"Record ID": str(drid), "Deal Name": "", "Deal Stage": "", "Amount": "", "Close Date": "",
           "Deal owner": random.choice(OWNERS), "Associated Company": "", "Lead Source": "",
           "Last Activity Date": "", "Next Step": "", "Deal Description": "", "Create Date": ""}
    row.update(kw)
    deals.append(row)


# healthy-ish baseline pipeline
for acct in base_accounts:
    if acct["Industry"].lower() in ("logistics", "wealth management"):
        continue
    if random.random() < 0.35:
        continue
    stage = random.choice(STAGES_CLEAN + ["Closed Won", "Closed Lost"])
    amt = random.choice([45000, 60000, 85000, 120000, 150000, 180000, 240000, 300000, 420000])
    created = random.randint(40, 300)
    close_in = random.randint(10, 150) if not stage.startswith("Closed") else -random.randint(5, 60)
    add_deal(**{
        "Deal Name": f"{acct['Company name']} - {random.choice(PRODUCTS)}",
        "Deal Stage": random.choice(STAGE_MESS.get(stage, [stage])) if random.random() < 0.3 else stage,
        "Amount": str(amt),
        "Close Date": (AS_OF + timedelta(days=close_in)).isoformat(),
        "Deal owner": acct["Company owner"],
        "Associated Company": acct["Company name"],
        "Lead Source": random.choice(SOURCES),
        "Last Activity Date": d(random.randint(1, 25)),
        "Next Step": random.choice(["Security review call", "Send order form", "Pilot kickoff",
                                    "Exec alignment w/ CCO", "Back-test results readout"]),
        "Deal Description": "",
        "Create Date": d(created),
    })

# planted deal problems -----------------------------------------------------
P = [
    # missing amount on a late-stage deal
    dict(**{"Deal Name": "Tidewater Bank - Transaction Monitoring", "Deal Stage": "Negotiation", "Amount": "",
            "Close Date": (AS_OF + timedelta(days=20)).isoformat(), "Associated Company": "Tidewater Bank",
            "Lead Source": "Referral", "Last Activity Date": d(3), "Next Step": "MSA redlines",
            "Create Date": d(120)}),
    # close date in the past, still open
    dict(**{"Deal Name": "Keystone Commerce - EDD Automation", "Deal Stage": "Proposal", "Amount": "180000",
            "Close Date": d(41), "Associated Company": "Keystone Commerce Bank", "Lead Source": "Outbound",
            "Last Activity Date": d(9), "Next Step": "Follow up on pricing", "Create Date": d(160)}),
    # stale + no next step
    dict(**{"Deal Name": "Ridgeway Money - KYC", "Deal Stage": "Technical Evaluation", "Amount": "95000",
            "Close Date": (AS_OF + timedelta(days=30)).isoformat(), "Associated Company": "Ridgeway Money",
            "Lead Source": "Inbound - Website", "Last Activity Date": d(83), "Next Step": "",
            "Create Date": d(190)}),
    # notes say late stage, stage says early
    dict(**{"Deal Name": "Bayside Savings - Full Platform", "Deal Stage": "Discovery", "Amount": "310000",
            "Close Date": (AS_OF + timedelta(days=25)).isoformat(), "Associated Company": "Bayside Savings Bank",
            "Lead Source": "Event - ACAMS", "Last Activity Date": d(2), "Next Step": "Legal",
            "Deal Description": "Their legal sent back MSA redlines Friday. Procurement asked for final pricing "
                                "and a signature date before quarter end.",
            "Create Date": d(140)}),
    # notes say deal is dying, stage says proposal
    dict(**{"Deal Name": "Driftwood Card - Fraud Investigations", "Deal Stage": "Proposal", "Amount": "220000",
            "Close Date": (AS_OF + timedelta(days=15)).isoformat(), "Associated Company": "Driftwood Card Co",
            "Lead Source": "Partner", "Last Activity Date": d(38), "Next Step": "Check in",
            "Deal Description": "Champion (Head of Fraud) left the company in August. No reply from new "
                                "VP since. Budget may have moved to an in-house build.",
            "Create Date": d(210)}),
    # attribution only in notes
    dict(**{"Deal Name": "Silverline FCU - Sanctions Screening", "Deal Stage": "Demo", "Amount": "75000",
            "Close Date": (AS_OF + timedelta(days=60)).isoformat(), "Associated Company": "Silverline FCU",
            "Lead Source": "", "Last Activity Date": d(6), "Next Step": "Demo w/ BSA team",
            "Deal Description": "Met their BSA Officer at our booth at Money20/20 Vegas. Warm intro to CRO after.",
            "Create Date": d(30)}),
    dict(**{"Deal Name": "Solace Remittance - KYC + Percy", "Deal Stage": "Discovery", "Amount": "140000",
            "Close Date": (AS_OF + timedelta(days=90)).isoformat(), "Associated Company": "Solace Remittance",
            "Lead Source": "", "Last Activity Date": d(4), "Next Step": "Scoping call",
            "Deal Description": "Came out of the ACAMS Hollywood dinner we hosted. Their CCO asked for a "
                                "back-test on their alert backlog.",
            "Create Date": d(21)}),
    dict(**{"Deal Name": "Copperline - Transaction Monitoring", "Deal Stage": "Technical Evaluation",
            "Amount": "260000", "Close Date": (AS_OF + timedelta(days=45)).isoformat(),
            "Associated Company": "Copperline Payments", "Lead Source": "", "Last Activity Date": d(5),
            "Next Step": "Back-test readout", "Deal Description": "Inbound from website demo form. Switching "
            "off legacy TM vendor at renewal in Q1.", "Create Date": d(70)}),
    # deals parked on duplicate accounts
    dict(**{"Deal Name": "First Harbor - Full Platform", "Deal Stage": "Negotiation", "Amount": "480000",
            "Close Date": (AS_OF + timedelta(days=18)).isoformat(), "Associated Company": "First Harbor Bancorp",
            "Lead Source": "Outbound", "Last Activity Date": d(2), "Next Step": "Exec sign-off",
            "Create Date": d(200)}),
    dict(**{"Deal Name": "Granite Trust - KYC expansion", "Deal Stage": "Proposal", "Amount": "155000",
            "Close Date": (AS_OF + timedelta(days=40)).isoformat(), "Associated Company": "Granite Trust",
            "Lead Source": "Referral", "Last Activity Date": d(11), "Next Step": "Pricing review",
            "Create Date": d(95)}),
    dict(**{"Deal Name": "Tallyhaus - EDD", "Deal Stage": "demo", "Amount": "65000",
            "Close Date": (AS_OF + timedelta(days=50)).isoformat(), "Associated Company": "Tallyhaus Inc",
            "Lead Source": "Inbound - Demo Request", "Last Activity Date": d(8), "Next Step": "Demo",
            "Create Date": d(25)}),
    # orphan deal: company name doesn't match any account exactly
    dict(**{"Deal Name": "Northpoint - Sanctions + TM", "Deal Stage": "Technical Evaluation", "Amount": "290000",
            "Close Date": (AS_OF + timedelta(days=35)).isoformat(), "Associated Company": "Northpoint Natl Bank",
            "Lead Source": "Event - Money20/20", "Last Activity Date": d(7), "Next Step": "Security questionnaire",
            "Create Date": d(110)}),
    dict(**{"Deal Name": "Quanta - Percy pilot", "Deal Stage": "Proposal", "Amount": "",
            "Close Date": "", "Associated Company": "", "Lead Source": "Inbound - Website",
            "Last Activity Date": d(14), "Next Step": "", "Deal Description": "Pilot on 3 months of alerts. "
            "Marcus Lee (Head of FinCrime) is the champion.", "Create Date": d(45)}),
    # unknown stage label
    dict(**{"Deal Name": "Evergreen BaaS - Partner bank program", "Deal Stage": "Verbal Yes", "Amount": "390000",
            "Close Date": (AS_OF + timedelta(days=12)).isoformat(), "Associated Company": "Evergreen BaaS",
            "Lead Source": "Partner", "Last Activity Date": d(1), "Next Step": "Order form",
            "Create Date": d(150)}),
]
for p in P:
    add_deal(**p)

# ---------------------------------------------------------------- write
OUT.mkdir(parents=True, exist_ok=True)
for name, rows in (("companies.csv", accounts), ("contacts.csv", contacts), ("deals.csv", deals)):
    random.shuffle(rows)
    with open(OUT / name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows):>4} rows -> {OUT / name}")
