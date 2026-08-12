#!/usr/bin/env python3
"""
Skill-Capability-Router · data generator
========================================
Reads the CC Switch skill registry (SQLite) and regenerates the routing
artifacts under ``data/``:

  skills.json       full normalized capability catalog (canonical entries + aliases)
  thin-table.md     compact discovery table, grouped by category (route here first)
  semantic-table.md full per-skill detail (read only after a thin-table match)
  manifest.json     generation metadata + validation report (gitignored)

Dependency-free, deterministic, rebuildable. Works on any machine that has a
CC Switch DB (or a ``skills.json`` export) and Python 3.

Usage
-----
  python scripts/generate_router.py                    # default DB ~/.cc-switch/cc-switch.db
  python scripts/generate_router.py --db C:\\path\\cc-switch.db
  python scripts/generate_router.py --json data/skills.json --root .
  python scripts/generate_router.py --validate-only

Canonicalisation rules
----------------------
* Base name = name with `[ _]?-?Automation` stripped, lowercased, dashes for
  separators. Two rows sharing a base are the same capability.
* Canonical entry = the hyphen (kebab) form if present, else the title-case
  form. Prefers the row with a non-boilerplate description for ``description``.
* ``aliases`` lists every other name spelling that maps to the same base.
* Category comes from the keyword map below; unmatched bases fall back to
  ``general``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import datetime

# --------------------------------------------------------------------------
# Curated category map.  ``base`` substrings are matched in order of
# appearance of the categories in ``CATEGORY_ORDER``; first match wins.
# Edit freely — regeneration is deterministic.
# --------------------------------------------------------------------------

CATEGORY_ORDER = [
    "finance-payments",
    "crm-sales",
    "marketing-email",
    "seo-analytics",
    "social-media",
    "communication-collab",
    "project-management",
    "hr-recruiting",
    "support-helpdesk",
    "dev-tools",
    "data-databases",
    "ai-ml-media",
    "documents-files",
    "ecommerce-retail",
    "travel-events",
    "sports-gaming",
    "health-fitness",
    "logistics-field",
    "education",
    "general",
]

CATEGORY_KEYWORDS = {
    # --- finance, accounting, payments, crypto, financial data -------------
    "finance-payments": [
        "xero", "wave-accounting", "quickbooks", "freshbooks", "sage",
        "zoho-books", "zoho-invoice", "zoho-inventory", "moneybird",
        "lexoffice", "sevdesk", "odoo", "netsuite", "bench", "brex", "ramp",
        "coupa", "taxjar", "ynab", "splitwise", "quaderno", "moonclerk",
        "plaid", "finmei", "btcpay", "coinbase", "coinmarketcap",
        "coinranking", "coinmarketcal", "bitquery", "alchemy", "open-sea",
        "polygon", "venly", "token-metrics", "blocknative", "beaconchain",
        "alpha-vantage", "benzinga", "nasdaq", "twelve-data", "eodhd",
        "finage", "fixer", "float", "chargebee", "recurly", "invoice",
        "accounting", "payroll", "ledger", "reimburse", "expense", "banking",
        "crypto", "blockchain", "stripe-billing", "gravity", "tide",
        "elorus", "flutterwave", "helcim", "plisio", "spondyr", "fraudlabs",
        "minerstat", "altoviz", "cryptocurrency", "wallet", "payments",
        "mboum", "trading",
    ],
    # --- CRM, sales automation, sales intelligence ------------------------
    "crm-sales": [
        "salesforce", "hubspot", "highlevel", "zoho-bigin", "zoho", "attio",
        "pipeline-crm", "capsule-crm", "kommo", "apptivo", "salesmate",
        "folk", "centralstationcrm", "nocrm-io", "espocrm", "dynamics-365",
        "copper", "crm", "sales", "deal", "lead", "zoominfo",
        "peopledatalabs", "apollo", "contact", "prospect", "pipeline",
        "salescrush", "gong", "seismic", "moxie", "forcemanager",
        "jobnimbus", "simla", "keap", "sidetracker", "autobound", "axonaut",
        "breeze", "fireberry", "godial", "firmbase", "quote", "accelo",
        "affinity", "deals", "opportunity",
    ],
    # --- email + marketing campaigns + outreach ---------------------------
    "marketing-email": [
        "active-campaign", "klaviyo", "mailchimp", "mailerlite", "mailersend",
        "mailbluster", "mailboxlayer", "mailcheck", "mailcoach", "mails-so",
        "mailsoftly", "emailable", "emaillistverify", "neverbounce",
        "zerobounce", "verifiedemail", "realphonevalidation", "listclean",
        "sendlane", "sendloop", "sendfox", "sendspark", "benchmark-email",
        "moosend", "omnisend", "emailoctopus", "enginemailer", "segmetrics",
        "beamer", "esputnik", "campayn", "chaser", "spoki", "email",
        "newsletter", "campaign", "marketing", "outreach", "cold-email",
        "drip", "landing-page", "popup", "customerio", "findymail",
        "fullenrich", "hunter", "instantly", "emelia", "reply", "lemlist",
        "woodpecker", "tomba", "persistiq", "proofly", "userlist", "unione",
        "vero", "remarkety", "kit", "tapfiliate", "goody", "gagelist",
        "typefully", "stannp", "hyperise", "bouncer", "clearout",
        "feathery", "tally", "fomo", "leadgen", "affiliate", "forms",
        "endorsal", "goodbits", "hotspot", "basin", "poptin", "pop-up",
        "lead-form", "signup-form",
    ],
    # --- SEO, SEM, ad platforms, search ------------------------------------
    "seo-analytics": [
        "ahrefs", "semrush", "moz", "neuronwriter", "googleads", "metaads",
        "google-search-console", "similarweb", "serpapi", "serpdog",
        "zenserp", "ravenseotools", "seo", "keyword", "backlink",
        "rank-tracker", "advertising", "ad-campaign", "google-adwords",
        "facebook-ads", "gsc", "search-analytics", "site-analyzer",
        "builtwith", "serply", "competitive-ads", "microsoft-clarity",
        "adrapid", "analytics-meta", "keyword-research", "page-speed",
    ],
    # --- social media --------------------------------------------------------
    "social-media": [
        "twitter", "facebook", "instagram", "linkedin", "tiktok", "pinterest",
        "reddit", "youtube", "threads", "bluesky", "mastodon", "twitch",
        "slack-gif", "giphy", "social", "posting", "hashtag", "repost",
        "stories", "reel", "twitter-algorithm", "buffer", "hootsuite",
        "ayrshare", "hypeauditor", "phantombuster", "brandwatch",
    ],
    # --- communication, messaging, calls, meetings --------------------------
    "communication-collab": [
        "slack", "discord", "webex", "zoom", "googlemeet", "google-chat",
        "chatwork", "telnyx", "twilio", "sendbird", "ring-central",
        "ringcentral", "msg91", "waboxapp", "whatsapp", "telegram", "viber",
        "sms", "call", "voip", "phone", "meeting", "videoconf", "dialpad",
        "sendgrid", "resend", "postmark", "mailgun", "notify", "notification",
        "smtp", "elevio", "googlemail", "zoho-mail", "gmail", "ably",
        "hookdeck", "svix", "pushbullet", "pushover", "revolt", "missive",
        "vestaboard", "internal-comms", "mocean", "textit", "livesession",
        "dailybot", "demio", "webinar", "group-chat", "real-time",
        "agent-mail", "email-sending", "many-chat", "instant-messaging",
    ],
    # --- project & task management, time tracking ----------------------------
    "project-management": [
        "jira", "linear", "trello", "monday", "asana", "clickup", "shortcut",
        "wrike", "basecamp", "teamwork", "pinboard", "leiga", "moco",
        "streamtime", "everhour", "harvest", "toggl", "clockify", "teamcamp",
        "workiom", "notion", "task", "kanban", "sprint", "scrum", "timesheet",
        "timeslice", "project", "deadline", "milestone", "agile", "cal-",
        "calendarhero", "timekit", "oncehub", "timecamp", "timely",
        "timelink", "ticktick", "desktime", "fireflies", "mural", "loomio",
        "process-street", "fibery", "productboard", "productlane",
        "habitica", "gist", "maintainx", "bigpicture", "beeminder",
        "schedule", "booking-calendar", "meeting-notes", "sprint-planning",
        "googlecalendar", "appointo", "appointment", "booking-link",
    ],
    # --- HR, recruiting, onboarding -----------------------------------------
    "hr-recruiting": [
        "ashby", "lever", "workday", "breezy-hr", "smartrecruiters",
        "recruitee", "workable", "greenhouse", "jazzhr", "icims", "talenthr",
        "applyboard", "fountain", "hiringplan", "sap-successfactors", "deel",
        "recruit", "ats", "candidate", "applicant", "onboarding", "hiring",
        "interview", "resume", "employee", "staff", "payroll-hr", "factorial",
        "rippling", "connecteam", "worksnaps", "people", "hris",
    ],
    # --- support, helpdesk, live chat, customer service -----------------------
    "support-helpdesk": [
        "zendesk", "intercom", "gorgias", "freshdesk", "helpscout",
        "supportbee", "livechat", "crisp", "front", "plain", "superchat",
        "respond-io", "wati", "botpress", "chatbotkit", "chatfai",
        "docsbot-ai", "customgpt", "botsonic", "landbot", "zoho-desk",
        "support", "helpdesk", "ticket", "customer-service", "chatbot",
        "knowledge-base", "csat", "reply-io", "re-amaze", "supportivekoala",
        "gleap", "helpwise", "thanks-io", "mopinion", "qualaroo", "refiner",
        "retently", "satismeter", "simplesat", "feedback", "canny",
        "nps", "onboarding-email", "user-feedback", "botbaba", "botstar",
        "gatherup",
    ],
    # --- developer tools, CI/CD, infra, security, low-code --------------------
    "dev-tools": [
        "github", "gitlab", "bitbucket", "circleci", "buildkite", "codeship",
        "cloudflare", "vercel", "netlify", "render", "heroku", "digital-ocean",
        "ngrok", "docker", "kubernetes", "k8s", "terraform", "ansible",
        "sentry", "honeybadger", "bugsnag", "codacy", "sourcegraph", "npm",
        "browserless", "browserbase", "browser-tool", "apify", "firecrawl",
        "scrapingbee", "scrapingant", "scrapfly", "zenrows", "diffbot",
        "tavily", "openperplex", "prisma", "neon", "turso", "supabase",
        "supadata", "auth0", "algolia", "mcp-builder", "codeinterpreter",
        "triggercmd", "test-app", "webapp-testing", "browserhub",
        "smartproxy", "brightdata", "cutt-ly", "tinyurl", "shorten",
        "webhook", "api-key", "rest-api", "graphql", "cloud", "infra",
        "deploy", "container", "registry", "gitops", "statuscake",
        "updown-io", "uptimerobot", "pingdom", "new-relic", "datadog",
        "influxdb", "better-stack", "mezmo", "virustotal", "securitytrails",
        "mx-toolbox", "digicert", "sslmate", "lastpass", "bitwarden",
        "ip2location", "ipdata", "ipinfo", "dnsfilter", "nextdns",
        "twocaptcha", "bubble", "webflow", "plasmic", "weweb", "budibase",
        "appsmith", "n8n", "zapier", "backendless", "nango", "appdrag",
        "bannerbear", "html-to-image", "screenshot-fyi", "screenshotone",
        "browser", "cloudlayer", "localize", "translation", "codereadr",
        "rocketlane", "rootly", "incident", "oncall", "pagerduty", "git",
        "code", "sdk", "cli", "devops", "cicd", "sonarqube", "javascript",
        "python-package", "caddy", "gcp", "aws", "azure", "fly-io",
        "appcircle", "appveyor", "bugbug", "bugherd", "developer-growth",
        "doppler-secretops", "crowdin", "hashnode", "launch-darkly",
        "launchdarkly", "memberstack", "remote-retrieval", "short-io",
        "stack-exchange", "wakatime", "wiz", "yandex", "webvizio",
        "theme-factory", "skill-creator", "skill-share", "template-skill",
        "opengraph-io", "parma", "parsehub", "scrape-do", "scrapegraph-ai",
        "bolt-iot", "sensibo", "seqera", "microsoft-tenant", "google-admin",
        "hackernews", "control-d", "ip2proxy", "ip2whois", "browseai",
        "linkhut", "linkup", "heyreach", "wachete", "yousearch", "globalping",
        "nano-nets", "geoapify", "geocodio", "geokeo", "opencage",
        "placekey", "graphhopper", "tomtom", "mapulus", "radar",
        "here-", "google-maps", "mapbox", "address-validation",
        "contentful", "kontent-ai", "prismic", "conversion-tools",
        "conveyor", "fluxguard", "honeyhive", "identitycheck",
        "piloterr", "passcreator", "opengraph", "geo-location", "gps",
        "code-review", "packages", "releases", "feature-flag", "screenshots",
        "atlassian", "abstract", "domain-name-brainstormer",
        "changelog-generator", "customjs", "metaphor", "neutrino", "agility",
        "here", "zeplin", "grafbase", "agentql", "agenty", "apex27",
        "browser-agent", "scraper", "web-scraping", "proxiedmail",
        "passslot", "wallet-pass", "email-proxy",
    ],
    # --- data, databases, analytics, BI --------------------------------------
    "data-databases": [
        "bigquery", "snowflake", "redshift", "clickhouse", "mysql",
        "postgres", "mongodb", "duckdb", "metabase", "tableau", "powerbi",
        "looker", "posthog", "mixpanel", "amplitude", "segment", "klipfolio",
        "gigasheet", "dbt", "fivetran", "airbyte", "bigml", "datarobot",
        "datagma", "census", "gosquared", "woopra", "aryn", "crustdata",
        "kaggle", "googlebigquery", "grin", "sql", "database", "warehouse",
        "analytics", "dashboard", "bi-", "etl", "elt", "csv", "sheets-data",
        "db-", "query", "metric", "kpi", "reports", "pipeline", "appsflyer",
        "keen", "perigon", "interzoid", "textrazor", "taggun", "typless",
        "semanticscholar", "nasa", "baserow", "grist", "ninox", "kadoa",
        "magnetic", "simple-analytics", "big-data-cloud", "platerecognizer",
        "tisane", "dromo", "enigma", "weather", "airvisual", "ambee",
        "ambient", "stormglass", "sensors", "insights", "spreadsheet-data",
        "data-extraction", "data-cleaning", "data-import", "parsera",
        "genderize", "turbot", "stock-data", "sentiment-analysis", "corrently",
        "energy", "utilities",
    ],
    # --- AI / ML / LLM / media generation -------------------------------------
    "ai-ml-media": [
        "openai", "anthropic", "gemini", "groq", "mistral", "perplexity",
        "replicate", "cohere", "ollama", "llama", "v0-", "flowiseai",
        "langbase", "langsmith", "griptape", "elevenlabs", "heygen",
        "deepgram", "speechify", "rev-ai", "happy-scribe", "veo", "luma",
        "runway", "dreamstudio", "dall-e", "stable-diffusion", "midjourney",
        "canvas-design", "image-enhancer", "remove-bg", "all-images-ai",
        "pexels", "shotstack", "aivoov", "textcortex", "writer", "winston-ai",
        "gamma", "ai-ml", "ai-ml-api", "langchain", "gpt", "llm", "rag",
        "embedding", "vector", "model", "inference", "machine-learning",
        "ml-", "whisper", "transcri", "tts", "text-to-speech", "text-to-video",
        "text-to-image", "video", "audio", "music", "image-", "photo",
        "design", "avatar", "voice", "speech", "podcast", "nlp",
        "openrouter", "astica", "humanloop", "retellai", "synthflow",
        "wit-ai", "gan-ai", "melo", "lmnt", "listennotes", "claid",
        "timelinesai", "sitespeakai", "mem", "mem0", "logo-dev", "imgbb",
        "imgix", "uploadcare", "shortpixel", "bunnycdn", "smugmug",
        "spotify", "toneden", "ritekit", "castingwords", "gladia",
        "cincopa", "cardly", "flexisign", "convolo", "entelligence",
        "generation", "ai-agents", "ai-search", "neural", "deep-learning",
        "bolna", "alttext", "spotlightr", "video-hosting", "abyssale",
        "insighto", "placid", "image-generation", "visual-generation",
    ],
    # --- documents, files, storage --------------------------------------------
    "documents-files": [
        "pdf", "docx", "xlsx", "pptx", "pdf4me", "pdfless", "pdfmonkey",
        "pdf-co", "pdf-api", "docmosis", "carbone", "craftmypdf",
        "docugenerate", "documenso", "documint", "docupilot", "docupost",
        "docuseal", "text-to-pdf", "adobe", "esignatures", "signwell",
        "signaturely", "eversign", "dropbox-sign", "pandadoc", "box",
        "dropbox", "googledrive", "googlephotos", "share-point",
        "sharepoint", "files-com", "boxhero", "printautopilot", "ocrspace",
        "ocr-web-service", "extracta-ai", "parseur", "docsumo", "klippa",
        "doc", "document", "spreadsheet", "slide", "file", "storage",
        "cloud-storage", "folder", "signature", "contract", "invoice-doc",
        "image-to-text", "scan", "convert", "forms-docs", "excel",
        "brand-guidelines", "draftable", "signpath", "boldsign",
        "intelliprint", "templated", "encodian", "heyzine", "kaleido",
        "visme", "ignisign", "firmao", "affinda", "amara", "bidsketch",
        "certifier", "etermin", "documents", "templates", "report",
        "file-conversion", "word-docs", "spreadsheets", "slides",
        "brandfetch", "accredible", "certificate", "badge",
    ],
    # --- ecommerce, retail, payments checkout, shipping -----------------------
    "ecommerce-retail": [
        "shopify", "woocommerce", "stripe", "lemon-squeezy", "gumroad",
        "paddle", "payhip", "square", "braintree", "storeganise",
        "storerocket", "sendowl", "printful", "printify", "hotmart",
        "bigcommerce", "medusa", "saleor", "commercetools", "prestashop",
        "opencart", "magento", "shipengine", "shipstation", "easypost",
        "afterpay", "klarna", "affirm", "paypal", "moonpay", "loyverse",
        "pos", "checkout", "cart", "store", "retail", "ecommerce",
        "merchant", "product-listing", "inventory", "fulfillment", "shipping",
        "ups", "fedex", "dhl", "ship", "delivery", "returns", "coupon",
        "discount", "subscription", "membership", "baselinker",
        "brightpearl", "junglescout", "kraken-io", "ko-fi", "membervault",
        "amazon", "bestbuy", "givebutter", "raisely", "gift-up",
        "memberspot", "dpd2", "beaconstac", "blackbaud", "cults",
        "affiliate-commerce", "marketplace", "product-feed", "dropshipping",
        "zylvie", "digital-product", "amcards", "daffy", "gift-card",
        "donation", "fundraising",
    ],
    # --- travel, events, booking, tickets --------------------------------------
    "travel-events": [
        "amadeus", "sabre", "travelperk", "getyourguide", "getbybus",
        "gettransfer", "kayak", "skyscanner", "tripadvisor", "eventbrite",
        "eventee", "eventzilla", "sympla", "ticketmaster", "seat-geek",
        "universe", "booking", "hotel", "flight", "travel", "trip", "tour",
        "event", "ticket", "conference", "webinar", "checkin", "qr-ticket",
        "qantas", "singaporeair", "hotel-booking", "viator", "humanitix",
        "evenium", "expofp", "rafflys", "lodgify", "booqable", "cabinpanda",
        "apaleo", "hospitality", "guest", "tours", "itinerary",
    ],
    # --- gaming, sports, esports -----------------------------------------------
    "sports-gaming": [
        "battlenet", "epic-games", "dungeon-fighter", "college-football",
        "steam-", "sports", "esports", "game", "gaming", "score", "odds",
        "league", "tournament",
    ],
    # --- health, fitness, wellness ---------------------------------------------
    "health-fitness": [
        "fitbit", "strava", "health", "fitness", "wellness", "workout",
        "heart-rate", "sleep", "nutrition", "medical", "telehealth", "vitals",
    ],
    # --- logistics, field service, routing ---------------------------------------
    "logistics-field": [
        "detrack", "optimoroute", "route4me", "servicem8", "logistics",
        "dispatch", "field-service", "route-optimization", "fleet", "courier",
        "last-mile", "fleet-management",
    ],
    # --- education, learning, assessment --------------------------------------
    "education": [
        "blackboard", "classmarker", "coassemble", "d2lbrightspace",
        "google-classroom", "lessonspace", "linguapop", "campus", "lms",
        "elearning", "quiz", "course", "assessment", "training",
    ],
    "general": [],
}

# Fallback: if no keyword matches, substrings like these hint at a category.
DOMAIN_WORD_FALLBACK = [
    ("invoice", "finance-payments"), ("accounting", "finance-payments"),
    ("payment", "finance-payments"), ("pay-", "finance-payments"),
    ("crm", "crm-sales"), ("sales", "crm-sales"), ("lead", "crm-sales"),
    ("email", "marketing-email"), ("marketing", "marketing-email"),
    ("newsletter", "marketing-email"), ("sms", "communication-collab"),
    ("seo", "seo-analytics"), ("analytics", "data-databases"),
    ("social", "social-media"), ("support", "support-helpdesk"),
    ("helpdesk", "support-helpdesk"), ("ticket", "support-helpdesk"),
    ("recruit", "hr-recruiting"), ("hire", "hr-recruiting"),
    ("hr-", "hr-recruiting"), ("project", "project-management"),
    ("task", "project-management"), ("database", "data-databases"),
    ("data-", "data-databases"), ("video", "ai-ml-media"),
    ("image", "ai-ml-media"), ("photo", "ai-ml-media"), ("audio", "ai-ml-media"),
    ("pdf", "documents-files"), ("doc", "documents-files"),
    ("file", "documents-files"), ("storage", "documents-files"),
    ("shop", "ecommerce-retail"), ("store", "ecommerce-retail"),
    ("booking", "travel-events"), ("event", "travel-events"),
    ("travel", "travel-events"), ("form", "marketing-email"),
    ("survey", "project-management"), ("meeting", "communication-collab"),
    ("api", "dev-tools"), ("cloud", "dev-tools"), ("auth", "dev-tools"),
    ("security", "dev-tools"), ("test", "dev-tools"), ("browser", "dev-tools"),
    ("feedback", "support-helpdesk"), ("reviews", "support-helpdesk"),
    ("games", "sports-gaming"), ("gaming", "sports-gaming"),
    ("sports", "sports-gaming"), ("odds", "sports-gaming"),
    ("health", "health-fitness"), ("fitness", "health-fitness"),
    ("medical", "health-fitness"), ("wellness", "health-fitness"),
    ("logistics", "logistics-field"), ("courier", "logistics-field"),
    ("dispatch", "logistics-field"),
    ("education", "education"), ("course", "education"), ("lms", "education"),
    ("class", "education"), ("quiz", "education"),
]

# Explicit single-entry overrides, always take precedence.
BASE_OVERRIDES = {
    "api2pdf": "documents-files",
    "apiflash": "documents-files",
    "composio": "dev-tools",
    "composio-search": "dev-tools",
    "connect": "general",
    "connect-apps": "general",
    "v0": "ai-ml-media",
    "exa": "dev-tools",
    "writer": "ai-ml-media",
    "microsoft-clarity": "seo-analytics",
    "salesforce-marketing-cloud": "marketing-email",
    "salesforce-service-cloud": "support-helpdesk",
    "github-vault-router": "general",
    "optimize-agent-capabilities": "general",
    "file-organizer": "documents-files",
    "invoice-organizer": "documents-files",
    "pdf": "documents-files",
    "docx": "documents-files",
    "xlsx": "documents-files",
    "pptx": "documents-files",
    "mocean": "communication-collab",
    "exa": "dev-tools",
    "bart": "travel-events",
    "starton": "finance-payments",
    "artifacts-builder": "ai-ml-media",
    "modelry": "general",
    "zenrows": "dev-tools",
    "cal": "project-management",
    "canvas": "ai-ml-media",
    "customer.io": "marketing-email",
    "grafbase": "dev-tools",
    "frontend-design": "ai-ml-media",
    "web-artifacts-builder": "dev-tools",
    "algorithmic-art": "ai-ml-media",
}


def base_name(name: str) -> str:
    """Normalize a skill name to its base tool id (dash-separated, lowercase)."""
    n = re.sub(r"[ _]?-?[Aa]utomation$", "", name.strip())
    n = n.strip().replace(" ", "-").replace("_", "-")
    return n.lower()


def categorize(base: str) -> str:
    if base in BASE_OVERRIDES:
        return BASE_OVERRIDES[base]
    for cat in CATEGORY_ORDER:
        if cat == "general":
            continue
        for kw in CATEGORY_KEYWORDS[cat]:
            if kw in base:
                return cat
    for word, cat in DOMAIN_WORD_FALLBACK:
        if word in base:
            return cat
    return "general"


def kind_of(name: str) -> str:
    if name.lower().endswith("automation"):
        return "automation"
    return "utility"


def source_of(base: str, name: str) -> str:
    n = name.lower()
    if n.endswith("automation") or base in BASE_OVERRIDES:
        if "github-vault-router" in base:
            return "workflow"
        if name in ("pdf", "docx", "xlsx", "pptx", "artifacts-builder",
                    "brand-guidelines", "canvas-design", "deep-research",
                    "dataviz", "claude-api"):
            return "anthropic"
        if n.endswith("automation"):
            return "composio"
    if base in ("connect", "connect-apps"):
        return "anthropic"
    return "community"


def is_boilerplate(desc: str) -> bool:
    if not desc:
        return True
    d = desc.strip().lower()
    if "rube mcp" in d or "composio" in d or "automate" in d and len(desc) < 140:
        return True
    return len(desc.strip()) < 20


ACRONYMS = {"crm", "api", "ai", "io", "ml", "cms", "seo", "sdk", "db", "id",
            "saas", "pos", "erp", "bi", "cli", "smtp", "pdf", "html", "sql",
            "url", "asn", "http", "dns", "ips", "ui", "ux", "it", "hr"}


def humanize(base: str) -> str:
    """Turn a base id into a readable title, keeping common acronyms uppercase."""
    words = base.replace("_", "-").split("-")
    parts = []
    for w in words:
        w = w.strip()
        if not w:
            continue
        parts.append(w.upper() if w in ACRONYMS else w.title())
    return " ".join(parts)


def verb_object_output(entry: dict) -> tuple[str, str, str]:
    """Structured capability summary in verb + object + output form."""
    base = entry["base"]
    display = humanize(base)
    if entry["kind"] == "automation":
        return "automate", display, "actions via Rube MCP (Composio)"
    desc = entry.get("description", "")
    if desc and not is_boilerplate(desc):
        m = re.match(r"^([^.]{2,60})\.", desc.strip())
        return "use", display, (m.group(1) if m else desc[:80])
    return "use", display, "installed skill"


def load_from_db(db_path: str) -> list[dict]:
    con = sqlite3.connect(db_path)
    rows = con.execute(
        "SELECT name, description, directory, repo_owner, repo_name, "
        "enabled_claude, enabled_codex, enabled_gemini, enabled_opencode, "
        "enabled_hermes, enabled_grokbuild FROM skills"
    ).fetchall()
    con.close()
    out = []
    for (name, desc, directory, owner, repo, ec, ecx, eg, eo, eh, egk) in rows:
        out.append({
            "name": name,
            "dir": directory,
            "description": (desc or "").strip(),
            "enabled": {
                "claude": int(ec or 0), "codex": int(ecx or 0),
                "gemini": int(eg or 0), "opencode": int(eo or 0),
                "hermes": int(eh or 0), "grokbuild": int(egk or 0),
            },
        })
    return out


def load_from_json(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("skills", [])


def build_catalog(rows: list[dict]) -> list[dict]:
    # group rows by base name
    groups: dict[str, list[dict]] = {}
    for r in rows:
        b = base_name(r["name"])
        groups.setdefault(b, []).append(r)

    catalog = []
    for base in sorted(groups):
        group = groups[base]
        # canonical row: prefer kebab name, then hyphen form, then first
        def rank(r):
            n = r["name"]
            score = 0
            if n == base:           # exact kebab match
                score = 0
            elif n.replace("_", "-") == base:
                score = 1
            elif " " in n:
                score = 2
            else:
                score = 3
            return (score, n.lower())
        group_sorted = sorted(group, key=rank)
        canonical = group_sorted[0]
        # best description: the least boilerplate among rows
        best_desc = ""
        for r in group:
            if not is_boilerplate(r["description"]):
                best_desc = r["description"]
                break
        if not best_desc:
            best_desc = next((r["description"] for r in group if r["description"]), "")
        display = next((r["name"] for r in group if " " in r["name"]), canonical["dir"])
        entry = {
            "name": canonical["dir"],        # on-disk skill dir = the registered skill name
            "dir": canonical["dir"],
            "display": display,
            "base": base,
            "kind": kind_of(canonical["name"]),
            "source": source_of(base, canonical["name"]),
            "category": categorize(base),
            "aliases": sorted({r["name"] for r in group if r["name"] != canonical["name"]}),
            "description": best_desc,
            "enabled": canonical["enabled"],
        }
        entry["verb"], entry["object"], entry["output"] = verb_object_output(entry)
        catalog.append(entry)

    return catalog


def render_thin_table(catalog: list[dict]) -> str:
    lines = []
    lines.append("# Skill Capability Router — Thin Discovery Table")
    lines.append("")
    lines.append("> Generated by `scripts/generate_router.py`. Do not edit by hand.")
    lines.append("> Read per category on a meaning match; then open the matching row in `semantic-table.md`.")
    lines.append("")
    for cat in CATEGORY_ORDER:
        items = [e for e in catalog if e["category"] == cat]
        if not items:
            continue
        lines.append(f"## {cat} ({len(items)})")
        lines.append("")
        for e in items:
            desc = e["description"]
            if e["kind"] == "automation" and (not desc or is_boilerplate(desc)):
                cap = f"Automate {e['object']}"
            else:
                cap = desc.split("\n")[0].strip()
                if len(cap) > 110:
                    cap = cap[:110].rstrip() + "…"
            flags = e["enabled"]
            state = "on" if flags["claude"] else "-"
            alias = f" (alias: {e['aliases'][0]})" if e["aliases"] else ""
            lines.append(f"- `{e['name']}` — {cap}{alias} [{state}]")
        lines.append("")
    return "\n".join(lines)


def render_semantic_table(catalog: list[dict]) -> str:
    lines = []
    lines.append("# Skill Capability Router — Semantic Routing Table")
    lines.append("")
    lines.append("> Generated by `scripts/generate_router.py`. Read a row only after a thin-table match.")
    lines.append("")
    for e in sorted(catalog, key=lambda x: (x["category"], x["name"])):
        lines.append(f"## {e['name']}")
        lines.append("")
        lines.append(f"- **base / capability**: {e['verb']} {e['object']} — {e['output']}")
        lines.append(f"- **category**: {e['category']}  ·  **kind**: {e['kind']}  ·  **source**: {e['source']}")
        lines.append(f"- **directory**: `{e['dir']}`")
        if e["aliases"]:
            lines.append(f"- **aliases**: {', '.join(e['aliases'])}")
        if e["description"]:
            lines.append(f"- **description**: {e['description'].strip()}")
        flags = e["enabled"]
        enabled = [k for k, v in flags.items() if v]
        lines.append(f"- **enabled**: {', '.join(enabled) if enabled else 'none'}  "
                     f"(claude={flags['claude']}, codex={flags['codex']}, gemini={flags['gemini']}, "
                     f"opencode={flags['opencode']}, hermes={flags['hermes']}, grokbuild={flags['grokbuild']})")
        lines.append("")
    return "\n".join(lines)


ZH_CATEGORY = {
    "finance-payments": "财务与支付",
    "crm-sales": "客户关系与销售",
    "marketing-email": "营销与邮件",
    "seo-analytics": "SEO 与分析",
    "social-media": "社交媒体",
    "communication-collab": "沟通与协作",
    "project-management": "项目管理与工时",
    "hr-recruiting": "人力资源与招聘",
    "support-helpdesk": "客服与工单",
    "dev-tools": "开发与工具",
    "data-databases": "数据与数据库",
    "ai-ml-media": "AI / 机器学习与媒体",
    "documents-files": "文档与文件",
    "ecommerce-retail": "电商与零售",
    "travel-events": "旅行与活动",
    "sports-gaming": "体育与游戏",
    "health-fitness": "健康与健身",
    "logistics-field": "物流与现场",
    "education": "教育",
    "general": "通用 / 其他",
}

ZH_VERB = {
    "automate": "自动化",
    "use": "处理",
}

# 常见工具的中文释义;未收录的用「自动化/处理 + 英文名」兜底
TOOL_ZH = {
    "xero": "在线记账",
    "quickbooks": "会计记账",
    "freshbooks": "会计开票",
    "wave-accounting": "免费记账",
    "zoho-books": "Zoho 记账",
    "zoho-invoice": "Zoho 开票",
    "zoho-inventory": "Zoho 库存",
    "sage": "企业管理软件",
    "netsuite": "ERP/财务套件",
    "salesforce": "CRM 客户管理",
    "hubspot": "CRM/营销套件",
    "highlevel": "营销 CRM",
    "zoho-bigin": "Zoho 轻 CRM",
    "attio": "现代 CRM",
    "pipeline-crm": "销售管道 CRM",
    "capsule-crm": "轻量 CRM",
    "kommo": "销售消息 CRM",
    "salesmate": "销售 CRM",
    "slack": "团队沟通",
    "discord": "社群聊天",
    "teams": "微软团队协作",
    "webex": "视频会议",
    "zoom": "视频会议",
    "twilio": "短信/通话 API",
    "sendgrid": "邮件发送",
    "resend": "开发邮件发送",
    "mailchimp": "邮件营销",
    "mailerlite": "邮件营销",
    "active-campaign": "邮件自动化营销",
    "klaviyo": "电商邮件营销",
    "github": "代码托管",
    "gitlab": "代码托管/CI",
    "bitbucket": "代码托管",
    "jira": "项目管理/缺陷跟踪",
    "linear": "极简项目管理",
    "notion": "笔记/知识库",
    "trello": "看板任务",
    "asana": "任务协作",
    "monday": "团队工作平台",
    "clickup": "一体化项目管理",
    "snowflake": "云数仓",
    "bigquery": "谷歌云数仓",
    "postgres": "PostgreSQL 数据库",
    "mysql": "MySQL 数据库",
    "mongodb": "MongoDB 文档库",
    "supabase": "开源后端/BaaS",
    "openai": "OpenAI 大模型",
    "anthropic": "Anthropic/Claude",
    "gemini": "谷歌 Gemini",
    "groq": "Groq 高速推理",
    "mistral": "Mistral 模型",
    "deepgram": "语音转录",
    "elevenlabs": "AI 语音合成",
    "heygen": "AI 数字人视频",
    "canvas-design": "视觉设计",
    "pdf": "PDF 文档",
    "docx": "Word 文档",
    "xlsx": "Excel 表格",
    "pptx": "PPT 演示",
    "shopify": "电商建站",
    "stripe": "支付收单",
    "paypal": "支付",
    "square": "线下支付/POS",
    "amazon": "亚马逊电商",
    "zendesk": "客服工单",
    "intercom": "在线客服",
    "gorgias": "电商客服",
    "freshdesk": "客服工单",
    "ashby": "招聘 ATS",
    "lever": "招聘 ATS",
    "workday": "HR/财务套件",
    "breezy-hr": "招聘 ATS",
    "eventbrite": "活动票务",
    "ticketmaster": "票务平台",
    "airbnb": "民宿预订",
    "github-vault-router": "GitHub 能力路由工作流",
}


def render_zh_catalog(catalog: list[dict]) -> str:
    from collections import Counter
    counts = Counter(e["category"] for e in catalog)
    lines = []
    lines.append("# 技能能力路由 — 中文技能目录")
    lines.append("")
    lines.append(f"> 由 `scripts/generate_router.py` 生成。共 **{len(catalog)}** 个技能、**{len(counts)}** 个分类。")
    lines.append("> 技能名保持英文(调用时用),释义为中文;未收录释义的自动化技能用「自动化 + 英文名」。")
    lines.append("")
    idx = 1
    for cat in CATEGORY_ORDER:
        items = [e for e in catalog if e["category"] == cat]
        if not items:
            continue
        zh = ZH_CATEGORY.get(cat, cat)
        lines.append(f"## {idx}. {zh} · `{cat}`({len(items)})")
        lines.append("")
        for e in sorted(items, key=lambda x: x["name"]):
            verb = ZH_VERB.get(e["verb"], e["verb"])
            gloss = TOOL_ZH.get(e["base"], "")
            gloss = f"({gloss})" if gloss else ""
            lines.append(f"- `{e['name']}` — {verb} {e['object']}{gloss}")
        lines.append("")
        idx += 1
    return "\n".join(lines)


def render_index(catalog: list[dict]) -> str:
    from collections import Counter
    counts = Counter(e["category"] for e in catalog)
    kinds = Counter(e["kind"] for e in catalog)
    lines = []
    lines.append("# Skill Capability Router — Data Index")
    lines.append("")
    n_cats = sum(1 for c in CATEGORY_ORDER if counts.get(c))
    lines.append(f"> Generated by `scripts/generate_router.py` from the CC Switch skill registry. "
                 f"{len(catalog)} canonical skills, {n_cats} categories. Do not edit by hand.")
    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("| File | What it is | When to read |")
    lines.append("| --- | --- | --- |")
    lines.append("| `thin-table.md` | Compact discovery table, grouped by category, one line per skill | First — route here on a tool/domain mention |")
    lines.append("| `semantic-table.md` | Full per-skill rows (capability, aliases, description, enablement) | After a thin-table match |")
    lines.append("| `skills.json` | Machine-readable full catalog | Programmatic use |")
    lines.append("")
    lines.append("## Categories")
    lines.append("")
    lines.append("Skills route to exactly one category. The category map is the curated keyword table in the generator (`CATEGORY_KEYWORDS` + `BASE_OVERRIDES`); unmatched skills fall back to `general`.")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("| --- | --- |")
    for cat in CATEGORY_ORDER:
        if counts.get(cat):
            lines.append(f"| `{cat}` | {counts[cat]} |")
    lines.append("")
    lines.append(f"Kinds: **{kinds.get('automation', 0)}** automation (`*-automation`, executed via Rube MCP / Composio) · "
                 f"**{kinds.get('utility', 0)}** utility.")
    lines.append("")
    lines.append("## How to use")
    lines.append("")
    lines.append("1. Read `thin-table.md` category matching the task's tool/domain.")
    lines.append("2. On a match, open the same skill's row in `semantic-table.md`, then invoke the skill by its **name/directory** (e.g. `xero-automation`).")
    lines.append("3. For `*-automation` skills, search Rube MCP (Composio) tools for current schemas before executing.")
    lines.append("4. Underscore/hyphen duplicates are collapsed; route to the canonical hyphen name.")
    lines.append("")
    lines.append("## Regenerate")
    lines.append("")
    lines.append("```bash")
    lines.append("python scripts/generate_router.py")
    lines.append("```")
    lines.append("")
    lines.append("Re-runs against `~/.cc-switch/cc-switch.db` (or `--db`/`--json`) and rewrites all four files deterministically.")
    lines.append("")
    return "\n".join(lines)


def validate(catalog: list[dict]) -> list[str]:
    errors = []
    names = [e["name"] for e in catalog]
    dup = [n for n in set(names) if names.count(n) > 1]
    if dup:
        errors.append(f"duplicate canonical names: {dup}")
    for e in catalog:
        if not e["base"] or not e["category"]:
            errors.append(f"{e['name']}: missing base/category")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Regenerate Skill-Capability-Router data artifacts")
    ap.add_argument("--root", default=None, help="repo root (default: parent of scripts/)")
    ap.add_argument("--db", default=None, help="path to CC Switch SQLite DB")
    ap.add_argument("--json", default=None, help="read skills from a JSON export instead of the DB")
    ap.add_argument("--validate-only", action="store_true", help="validate without writing")
    args = ap.parse_args()

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(root, "data")
    os.makedirs(data_dir, exist_ok=True)

    if args.json:
        rows = load_from_json(args.json)
        src_label = args.json
    else:
        db = args.db or os.path.expanduser("~/.cc-switch/cc-switch.db")
        if not os.path.exists(db):
            print(f"[error] DB not found: {db}", file=sys.stderr)
            return 2
        rows = load_from_db(db)
        src_label = db

    catalog = build_catalog(rows)
    errors = validate(catalog)

    from collections import Counter
    cats = Counter(e["category"] for e in catalog)
    kinds = Counter(e["kind"] for e in catalog)
    sources = Counter(e["source"] for e in catalog)
    alias_pairs = sum(1 for e in catalog if e["aliases"])

    if args.validate_only:
        print(f"[validate] rows={len(rows)} canonical={len(catalog)} errors={len(errors)}")
        for err in errors:
            print(f"  - {err}")
        return 0 if not errors else 1

    if errors:
        print("[warn] validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)

    # skills.json
    with open(os.path.join(data_dir, "skills.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    # index + zh catalog + thin + semantic tables
    with open(os.path.join(data_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(render_index(catalog))
    with open(os.path.join(data_dir, "skills.zh-CN.md"), "w", encoding="utf-8") as f:
        f.write(render_zh_catalog(catalog))
    with open(os.path.join(data_dir, "thin-table.md"), "w", encoding="utf-8") as f:
        f.write(render_thin_table(catalog))
    with open(os.path.join(data_dir, "semantic-table.md"), "w", encoding="utf-8") as f:
        f.write(render_semantic_table(catalog))

    # manifest (local metadata; gitignored)
    manifest = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "input": src_label,
        "row_count": len(rows),
        "canonical_count": len(catalog),
        "alias_groups": alias_pairs,
        "categories": dict(cats),
        "kinds": dict(kinds),
        "sources": dict(sources),
        "validation_errors": errors,
    }
    with open(os.path.join(data_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"[ok] rows={len(rows)} → canonical={len(catalog)} aliases={alias_pairs}")
    print(f"[ok] categories: {dict(cats)}")
    print(f"[ok] kinds: {dict(kinds)}  sources: {dict(sources)}")
    print(f"[ok] validation errors: {len(errors)}")
    print(f"[ok] wrote data/README.md, data/skills.zh-CN.md, data/skills.json, data/thin-table.md, data/semantic-table.md, data/manifest.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
