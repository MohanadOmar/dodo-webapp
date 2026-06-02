"""All n8n workflows in one place.

To add a new workflow:
1. Append a dict to WORKFLOWS below
2. Push & redeploy
That's it. The tool, schema, and routing all generate automatically.

Field reference:
    name              — internal id, must be valid Python identifier (no spaces/dashes)
    url               — n8n webhook URL
    description       — what Dodo sees. Tell it WHEN to use this and what happens.
    inputs            — list of parameter dicts the LLM will fill in
        name            — argument name
        description     — what the arg means
        required        — bool (default True)
    payload_template  — how to shape the JSON sent to n8n.
                        Use {arg_name} to interpolate. Defaults to flat dict of args.
    success_message   — what Dodo says back. Use {arg_name} to interpolate.
                        Defaults to "Workflow triggered."
"""

WORKFLOWS = [
    {
        "name": "search_grants",
        "url": "https://sansona.app.n8n.cloud/webhook/garett",
        "description": (
            "Search for grants matching specific cities and keywords. "
            "Triggers Garett, an external workflow that searches grants.gov + Google "
            "and texts the results back. Use when the user asks to find/search/look up grants. "
            "Always confirm cities and keywords with the user before triggering."
        ),
        "inputs": [
            {
                "name": "cities_and_keywords",
                "description": "Comma-separated cities and keywords. Example: 'Austin, Houston, small business, technology'",
            },
        ],
        "payload_template": {
            "original_message": {"content": "{cities_and_keywords}"},
        },
        "success_message": "Searching grants for: {cities_and_keywords}. I'll text you when results are ready.",
    },
    # ── Add new workflows here. Just copy the block above. ──

    {
        "name": "get_overdue_invoices",
        "url": "https://sansona.app.n8n.cloud/webhook/ad284edc-ef15-4379-8ff2-d849ad980e50",
        "description": (
            "Fetch all overdue/unpaid QuickBooks invoices via the Zylo workflow. "
            "Use this when the user asks about overdue invoices, unpaid invoices, "
            "outstanding balances, what clients owe, who hasn't paid, or anything "
            "about money owed. Returns a list of invoices with client names, "
            "amounts, balances, and due dates. Read the data and answer the user's "
            "question naturally — count clients, sum totals, identify oldest, etc."
        ),
        "inputs": [],  # No params — Zylo just dumps overdue invoices
        "sync": True,  # Wait for the response
        "timeout": 30,  # QuickBooks queries can be slow
        "transform": "invoices",  # Pre-aggregate so Dodo gets clean stats
    },
]
