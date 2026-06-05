#!/usr/bin/env bash
# Demo 3 — Indirect Prompt Injection: Apply the fix
#
# Sets SECURITY_LEVEL=demo3_fixed so the agent enables its injection defenses:
#   1. ToolCallValidator — validates tool calls against user intent
#   2. Data boundaries — tool results wrapped so LLM treats them as data
#   3. Content scanning — flags known injection patterns

set -euo pipefail
source "$(dirname "$0")/../lib.sh"

echo ""
echo "============================================================"
echo "  DEMO 3 — INDIRECT PROMPT INJECTION: Applying Fix"
echo "============================================================"
echo ""

restart_agent demo3_fixed

echo ""
echo "  What changes at this security level:"
echo "  ------------------------------------------------------------"
echo ""
echo "  1. ToolCallValidator — validates every tool call against the"
echo "     user's ORIGINAL request. If the user asked to look up a"
echo "     ticket, the agent will NOT allow a search_tickets() call"
echo "     that was never requested."
echo ""
echo "  2. Data / Instruction Boundaries — tool results are wrapped"
echo "     so the LLM treats them as data, not directives."
echo ""
echo "  3. Content Scanning — tool outputs are scanned for known"
echo "     injection patterns (fake system headers, urgency phrases)."
echo ""
echo "  ------------------------------------------------------------"
echo ""
echo "  Fix applied. Refresh the Chat UI and re-run the attack"
echo "  to confirm the injection is now blocked."
echo ""
