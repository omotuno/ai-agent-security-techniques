#!/usr/bin/env bash
# Demo 5 — Production Guardrails: Apply the fix
#
# Enables NeMo Guardrails wrapping the LangChain agent:
#   - Input rail: ML-based jailbreak detection
#   - Input rail: PII scanning on user messages
#   - Output rail: PII redaction before responses reach the user

set -euo pipefail
source "$(dirname "$0")/../lib.sh"

echo ""
echo "============================================================"
echo "  DEMO 5 — PRODUCTION GUARDRAILS: Apply Fix"
echo "============================================================"
echo ""
echo "  What this enables:"
echo "    - NeMo Guardrails wraps the existing LangChain agent"
echo "    - Input rail: ML-based jailbreak detection"
echo "    - Input rail: PII scanning on user messages"
echo "    - Output rail: PII redaction (SSNs, emails, phone numbers)"
echo ""
echo "  Config files:"
echo "    - agent/guardrails/config/config.yml  (rails configuration)"
echo "    - agent/guardrails/config/rails.co    (Colang flow definitions)"
echo ""

restart_agent demo5_fixed

echo ""
echo "============================================================"
echo "  Fix applied. NeMo Guardrails are now active."
echo "  Refresh the Chat UI and re-run the attacks to confirm they're blocked."
echo "============================================================"
echo ""
