#!/usr/bin/env bash
# Demo 4 - Memory Poisoning: Apply the fix.
#
# This script:
#   1. Sets SECURITY_LEVEL=demo4_fixed (structured memory schemas)
#   2. Clears poisoned session memory from Firestore

set -euo pipefail
source "$(dirname "$0")/../lib.sh"

COMPANY_ID="${COMPANY_ID:-techcorp}"

echo ""
echo "============================================================"
echo "  DEMO 4 — MEMORY POISONING: Apply Fix"
echo "============================================================"
echo ""

# ---------------------------------------------------------------
# Step 1: Restart agent with fixed security level
# ---------------------------------------------------------------
echo "  [1/2] Restarting agent..."
echo ""

restart_agent demo4_fixed

# ---------------------------------------------------------------
# Step 2: Clear poisoned memory from Firestore
# ---------------------------------------------------------------
echo ""
echo "  [2/2] Clearing poisoned session memory from Firestore..."
echo ""

cd "$MODULE_DIR"
PYTHONPATH=. uv run --project agent python3 - <<'PYTHON_SCRIPT'
import os
import firebase_admin
from firebase_admin import firestore as fb_firestore
from google.cloud import firestore

COMPANY_ID = os.getenv("COMPANY_ID", "techcorp")
EMPLOYEE_ID = "emp_101"
GCP_PROJECT = os.environ["GCP_PROJECT"]

if not firebase_admin._apps:
    firebase_admin.initialize_app(options={"projectId": GCP_PROJECT})

db = firestore.Client(project=GCP_PROJECT)
deleted = 0

# Clear flat collection
flat_ref = db.collection(f"agent_memory/{COMPANY_ID}/{EMPLOYEE_ID}/sessions")
for doc in flat_ref.stream():
    doc.reference.delete()
    deleted += 1

# Clear nested collections under the employee document
emp_doc_ref = db.collection("agent_memory").document(COMPANY_ID)
try:
    for sub_col in emp_doc_ref.collections():
        if EMPLOYEE_ID in sub_col.id or "session" in sub_col.id.lower():
            for doc in sub_col.stream():
                doc.reference.delete()
                deleted += 1
except Exception as e:
    print(f"        Warning: could not list subcollections: {e}")

# Clear top-level agent_memory docs for this user
query = db.collection("agent_memory").where("employee_id", "==", EMPLOYEE_ID)
for doc in query.stream():
    doc.reference.delete()
    deleted += 1

print(f"        Deleted {deleted} memory document(s).")
PYTHON_SCRIPT

echo ""
echo "  --------------------------------------------------------"
echo "  FIX APPLIED. What changed:"
echo "  --------------------------------------------------------"
echo ""
echo "  1. Structured SessionSummary schema (Pydantic):"
echo "     Only ticket_ids, topics, issues_raised survive."
echo "     Free-text instructions cannot pass validation."
echo ""
echo "  2. Memory loaded as reference data, not instructions:"
echo "     Past summaries are informational context, not orders."
echo ""
echo "  3. Integrity validation:"
echo "     Summaries are scanned for instruction-like patterns"
echo "     and flagged/stripped before storage."
echo ""
echo "  Refresh the Chat UI and re-run the attack to confirm the fix."
echo "============================================================"
echo ""
