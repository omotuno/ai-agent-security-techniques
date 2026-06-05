"""NeMo Guardrails integration for the TechCorp IT Helpdesk agent.

Demo 5 wraps the LangChain agent with NeMo Guardrails to add
production-grade input/output rails:
  - Input rail: ML-based jailbreak detection
  - Input rail: PII scanning on user messages
  - Output rail: PII redaction before responses reach the user
"""

import os

from nemoguardrails import RailsConfig
from nemoguardrails.integrations.langchain.runnable_rails import RunnableRails

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "config")


def create_guardrails(config_path: str | None = None) -> RunnableRails:
    """Create a RunnableRails instance that can wrap any LangChain agent.

    Usage:
        guardrails = create_guardrails()
        guarded_agent = guardrails | agent
    """
    path = config_path or _CONFIG_DIR
    config = RailsConfig.from_path(path)
    return RunnableRails(config)
