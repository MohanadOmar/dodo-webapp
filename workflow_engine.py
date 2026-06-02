"""Generates everything the agent needs from workflows.py — automatically.

Provides:
- WORKFLOW_TOOLS  : OpenAI tool schemas (just append to TOOLS in agent.py)
- WORKFLOW_FUNCS  : dict mapping name -> callable (just merge into TOOL_MAP)
"""
import json
import requests
from workflows import WORKFLOWS


def _interpolate(template, args: dict):
    """Recursively replace {arg_name} in strings inside the template."""
    if isinstance(template, str):
        try:
            return template.format(**args)
        except KeyError:
            return template
    if isinstance(template, dict):
        return {k: _interpolate(v, args) for k, v in template.items()}
    if isinstance(template, list):
        return [_interpolate(v, args) for v in template]
    return template


# ─── Transforms ─────────────────────────────────────────────────────────────
# Pre-compute summary stats from raw API output so Dodo doesn't have to.
# Add a new transform by writing a function and registering it below.

def _pick_first(d: dict, *keys):
    """Return the first non-empty value across keys/paths.
    Supports dotted paths like 'CustomerRef.name'.
    """
    for key in keys:
        cur = d
        ok = True
        for part in key.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                ok = False
                break
        if ok and cur not in (None, "", []):
            return cur
    return None


def _to_float(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (ValueError, TypeError):
        return 0.0


def transform_invoices(items: list) -> dict:
    """Aggregate a QuickBooks-style invoice array into a clean summary.

    Returns: count, unique_clients, total_owed, by_client (top 10),
             oldest_due, invoices (flat list with item_type for filtering)
    """
    if not isinstance(items, list):
        return {"error": "Expected a list of invoices"}

    by_client = {}  # name -> {invoices, total}
    total_owed = 0.0
    oldest = None  # (due_date, client, balance)
    invoice_list = []  # flat list of every invoice with key fields

    for inv in items:
        if not isinstance(inv, dict):
            continue

        client = _pick_first(inv,
            "CustomerRef.name",
            "Customer.DisplayName",
            "customerName",
            "CustomerName",
            "client",
        ) or "Unknown"

        balance = _to_float(_pick_first(inv,
            "Balance", "balance", "AmountDue", "amount_due",
        ))

        due = _pick_first(inv,
            "DueDate", "dueDate", "due_date",
        )

        doc_number = _pick_first(inv, "DocNumber", "docNumber", "invoice_number")

        # Extract ItemRef.name from the first Line item (skipping SubTotalLineDetail)
        item_type = None
        for line in inv.get("Line", []):
            detail = line.get("SalesItemLineDetail") or line.get("salesItemLineDetail")
            if detail:
                item_ref = detail.get("ItemRef") or detail.get("itemRef")
                if item_ref:
                    item_type = item_ref.get("name", None)
                break  # only need the first real line item

        # Aggregate
        if client not in by_client:
            by_client[client] = {"invoices": 0, "total": 0.0}
        by_client[client]["invoices"] += 1
        by_client[client]["total"] += balance
        total_owed += balance

        # Track oldest
        if due and (oldest is None or due < oldest[0]):
            oldest = (due, client, balance)

        # Add to flat list for detailed queries
        invoice_list.append({
            "client": client,
            "balance": balance,
            "due_date": due,
            "doc_number": doc_number,
            "item_type": item_type,
        })

    # Sort clients by total owed
    sorted_clients = sorted(
        [{"client": k, **v} for k, v in by_client.items()],
        key=lambda x: x["total"],
        reverse=True,
    )

    # Collect distinct item types
    item_types = sorted(set(i["item_type"] for i in invoice_list if i["item_type"]))

    summary = {
        "count": len(items),
        "unique_clients": len(by_client),
        "total_owed": round(total_owed, 2),
        "by_client": sorted_clients[:10],
        "item_types": item_types,
        "invoices": invoice_list,
    }

    if oldest:
        summary["oldest_due"] = {
            "due_date": oldest[0],
            "client": oldest[1],
            "balance": round(oldest[2], 2),
        }

    return summary


TRANSFORMS = {
    "invoices": transform_invoices,
}


def _make_function(workflow: dict):
    """Build a callable that POSTs to the workflow's webhook."""
    url = workflow["url"]
    template = workflow.get("payload_template")
    success_msg = workflow.get("success_message", "Workflow triggered.")
    timeout_seconds = workflow.get("timeout", 10)
    sync = workflow.get("sync", False)
    transform_name = workflow.get("transform")
    transform_fn = TRANSFORMS.get(transform_name) if transform_name else None

    def runner(**kwargs):
        payload = _interpolate(template, kwargs) if template else kwargs

        try:
            response = requests.post(url, json=payload, timeout=timeout_seconds)
            if response.status_code >= 400:
                return {"success": False, "error": f"n8n returned {response.status_code}: {response.text[:200]}"}

            try:
                body = response.json()

                # If a transform is configured, run it on the body
                if transform_fn:
                    items = body if isinstance(body, list) else body.get("data", body)
                    summary = transform_fn(items)
                    return {"success": True, **summary}

                # Default behavior — return raw body
                if isinstance(body, list):
                    return {"success": True, "data": body, "count": len(body)}
                if isinstance(body, dict) and body:
                    return {"success": True, **body}
            except Exception:
                pass

            return {"success": True, "message": success_msg.format(**kwargs)}

        except requests.Timeout:
            if sync:
                return {"success": False, "error": f"Workflow timed out after {timeout_seconds}s"}
            return {"success": True, "message": success_msg.format(**kwargs)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    runner.__name__ = workflow["name"]
    return runner


def _make_schema(workflow: dict) -> dict:
    """Build the OpenAI tool definition from the workflow config."""
    properties = {}
    required = []
    for inp in workflow.get("inputs", []):
        properties[inp["name"]] = {
            "type": inp.get("type", "string"),
            "description": inp.get("description", ""),
        }
        if inp.get("required", True):
            required.append(inp["name"])

    return {
        "type": "function",
        "function": {
            "name": workflow["name"],
            "description": workflow["description"],
            "parameters": {
                "type": "object",
                "required": required,
                "properties": properties,
            },
        },
    }


# Generated outputs — import these in agent.py
WORKFLOW_TOOLS = [_make_schema(wf) for wf in WORKFLOWS]
WORKFLOW_FUNCS = {wf["name"]: _make_function(wf) for wf in WORKFLOWS}
