import os
from dataclasses import dataclass, field

import firebase_admin
from google.cloud import firestore


# ── Feature matrix: what each SECURITY_LEVEL enables ──
# Each demo progressively adds defenses. A student can read this table
# to understand the full progression at a glance.
_DEMO_FEATURES = {
    #                            dangerous  tenant   sanitize  memory   guard-   memory
    #                            tools?     isolate? inputs?   guard?   rails?   load?
    "demo1_vulnerable":         (True,      False,   False,    False,   False,   False),
    "demo1_fixed":              (False,     False,   False,    False,   False,   False),
    "demo2_vulnerable":         (False,     False,   False,    False,   False,   False),
    "demo2_fixed":              (False,     True,    False,    False,   False,   False),
    "demo3_vulnerable":         (False,     True,    False,    False,   False,   False),
    "demo3_fixed":              (False,     True,    True,     False,   False,   False),
    "demo4_vulnerable":         (False,     True,    True,     False,   False,   True),
    "demo4_fixed":              (False,     True,    True,     True,    False,   True),
    "demo5_vulnerable":         (False,     True,    True,     True,    False,   True),
    "demo5_fixed":              (False,     True,    True,     True,    True,    True),
    # Demo 6 fix is at the infrastructure layer (service account), not application.
    # Both entries have identical app-layer features — the difference is the GCP SA.
    "demo6_vulnerable":         (True,      True,    True,     True,    True,    True),
    "demo6_fixed":              (True,      True,    True,     True,    True,    True),
}

VALID_LEVELS = set(_DEMO_FEATURES.keys())


@dataclass
class SecurityConfig:
    """Security configuration driven by SECURITY_LEVEL environment variable.

    Each demo has a 'vulnerable' and 'fixed' state. The SECURITY_LEVEL env var
    controls which security features are enabled, allowing the same agent code
    to run in both states without code changes.

    See _DEMO_FEATURES above for the full feature matrix.
    """

    level: str = field(default_factory=lambda: os.getenv("SECURITY_LEVEL", "demo1_vulnerable"))

    def __post_init__(self):
        if self.level not in VALID_LEVELS:
            raise ValueError(
                f"Invalid SECURITY_LEVEL={self.level!r}. "
                f"Valid values: {sorted(VALID_LEVELS)}"
            )

    def _feature(self, index: int) -> bool:
        return _DEMO_FEATURES[self.level][index]

    @property
    def allow_dangerous_tools(self) -> bool:
        return self._feature(0)

    @property
    def enforce_tenant_isolation(self) -> bool:
        return self._feature(1)

    @property
    def enable_tool_call_validation(self) -> bool:
        return self._feature(2)

    @property
    def enable_safe_memory(self) -> bool:
        return self._feature(3)

    @property
    def enable_guardrails(self) -> bool:
        return self._feature(4)

    @property
    def enable_memory_loading(self) -> bool:
        return self._feature(5)


# LLM configuration
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.4")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# GCP configuration
GCP_PROJECT = os.getenv("GCP_PROJECT")
if not GCP_PROJECT:
    raise RuntimeError("GCP_PROJECT environment variable is required")

# Firestore
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE", "(default)")
COMPANY_ID = os.getenv("COMPANY_ID", "techcorp")

# LangSmith (optional)
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "ai-security-course")

# Cached singletons
_security_config: SecurityConfig | None = None
_firestore_client: firestore.Client | None = None


def get_security_config() -> SecurityConfig:
    global _security_config
    if _security_config is None:
        _security_config = SecurityConfig()
    return _security_config


def get_firestore_client() -> firestore.Client:
    """Shared Firestore client — used by tools, memory, and seed scripts."""
    global _firestore_client
    if _firestore_client is None:
        _firestore_client = firestore.Client(project=GCP_PROJECT, database=FIRESTORE_DATABASE)
    return _firestore_client


def ensure_firebase_initialized():
    """Initialize Firebase Admin SDK once."""
    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            options={"projectId": GCP_PROJECT}
        )
