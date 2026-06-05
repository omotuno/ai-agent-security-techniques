#!/usr/bin/env bash
#
# Demo 1 - Blast Radius: Apply the least-privilege fix.
#
# Sets SECURITY_LEVEL=demo1_fixed so the agent strips dangerous tools
# (reset_password, list_storage_buckets, check_storage_bucket, get_service_secret) before
# the LLM ever sees them.

set -euo pipefail
source "$(dirname "$0")/../lib.sh"

echo ""
echo "============================================================"
echo "  DEMO 1 — BLAST RADIUS: Applying Fix"
echo "============================================================"
echo ""

restart_agent demo1_fixed

echo ""
echo "  --------------------------------------------------------"
echo "  Fix applied. The agent now enforces:"
echo "    - Role-based tool access (Alice cannot reset passwords)"
echo "    - Dangerous tools removed before the LLM sees them"
echo "  --------------------------------------------------------"
echo ""
echo "  Refresh the Chat UI and re-run the attack to confirm it's blocked."
echo ""
