TICKETS = [
    # ── Billing (8 tickets — 40%) ──
    {"id": "TKT-001", "text": "My bill is way too high this month, I was charged $200 extra",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-002", "text": "I see a charge for a service I never signed up for",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-003", "text": "My payment didn't go through but the money left my bank",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-004", "text": "Can I get an invoice for my business account for tax purposes?",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-005", "text": "I was double-billed for my monthly subscription",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-006", "text": "The promotional rate on my bill expired without notice",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-007", "text": "I need to update my payment method to a new credit card",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    {"id": "TKT-008", "text": "There's a roaming charge on my bill but I didn't leave the country",
     "expected_agent": "BillingAgent", "expected_method": "rule"},
    # ── Technical (6 tickets — 30%) ──
    {"id": "TKT-009", "text": "There's a complete outage in my area, no one has service",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    {"id": "TKT-010", "text": "I have no signal at all since yesterday morning",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    {"id": "TKT-011", "text": "My internet is extremely slow, barely loading any pages",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    {"id": "TKT-012", "text": "Calls keep getting dropped after 30 seconds of talking",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    {"id": "TKT-013", "text": "The WiFi router you sent keeps disconnecting every hour",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    {"id": "TKT-014", "text": "I'm getting no signal in my basement office since the tower update",
     "expected_agent": "TechnicalAgent", "expected_method": "rule"},
    # ── Cancellation (2 tickets — 10%) ──
    {"id": "TKT-015", "text": "I want to cancel my service and switch to another provider",
     "expected_agent": "RetentionAgent", "expected_method": "priority"},
    {"id": "TKT-016", "text": "I'm done with this company, please cancel everything immediately",
     "expected_agent": "RetentionAgent", "expected_method": "priority"},
    # ── Ambiguous (4 tickets — 20%) ──
    {"id": "TKT-017", "text": "My phone isn't working right, something is definitely wrong",
     "expected_agent": "LLM-classified", "expected_method": "llm"},
    {"id": "TKT-018", "text": "I've been having problems ever since I upgraded my plan last week",
     "expected_agent": "LLM-classified", "expected_method": "llm"},
    {"id": "TKT-019", "text": "Nothing works and I'm very frustrated with everything",
     "expected_agent": "LLM-classified", "expected_method": "llm"},
    {"id": "TKT-020", "text": "purple elephant moonbeam random gibberish xkcd 42",
     "expected_agent": "GeneralSupportAgent", "expected_method": "fallback"},
]

ROUTING_RULES =[

    # (pattern , target_name)
    
    (r"\b(bill|charge | payment |invoice | billed | subscription | rate | roaming )\b", "BillingAgent"),
    (r"\b(outage | no signal | slow | dropped | disconnect | no srevice | tower)\b", "TechnicalAgent"),
]

INTENT_TO_AGENT = {
   "technical" : "TechnicalAgent",
   "billing"  :"BillingAgent",
   "cancellation":"RetentionAgent",
   "general" : "GeneralSupportAgent",
}


PRIORITY_PATTERNS = [
    r"\b(cancel\w*|switch provider|terminate|discontinue|done with this company)\b",
    r"\bleave\b.*\b(provider|service|company|carrier|plan)\b",
]