#!/usr/bin/env bash
# Demo 2 — Tenant Isolation: Apply Fix
#
# Sets SECURITY_LEVEL=demo2_fixed so that the agent's tools enforce
# UserContext-based scoping (department filtering on queries).

set -euo pipefail
source "$(dirname "$0")/../lib.sh"

echo ""
echo "============================================================"
echo "  DEMO 2 — Tenant Isolation: APPLYING FIX"
echo "============================================================"
echo ""

restart_agent demo2_fixed

echo ""
echo "============================================================"
echo "  FIX APPLIED"
echo "============================================================"
echo ""
echo "  What changed:"
echo "    SECURITY_LEVEL = demo2_fixed"
echo ""
echo "    - Ticket search now filters by the caller's department"
echo "    - Wiki article retrieval checks department permissions"
echo "    - Tools receive UserContext and enforce row-level scoping"
echo ""
echo "  Refresh the Chat UI and re-run the attack to confirm it's blocked."
echo "============================================================"
echo ""
