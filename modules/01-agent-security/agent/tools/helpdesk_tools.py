"""Helpdesk tools for the TechCorp IT agent.

When AuthorizationMiddleware is active, it injects UserContext via
InjectedToolArg before each tool call. When it's not active (vulnerable
state), user_context is None and tools return everything unfiltered.
"""

from typing import Annotated

from firebase_admin import auth
from google.cloud import firestore
from langchain_core.tools import InjectedToolArg, tool
from langchain_openai import OpenAIEmbeddings

from agent.auth import UserContext
from agent.config import COMPANY_ID, EMBEDDING_MODEL, ensure_firebase_initialized, get_firestore_client

ensure_firebase_initialized()

db = get_firestore_client()

# Lazy-initialized embedding model
_embeddings_model: OpenAIEmbeddings | None = None


def _get_embeddings_model() -> OpenAIEmbeddings:
    global _embeddings_model
    if _embeddings_model is None:
        _embeddings_model = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    return _embeddings_model


# ---------------------------------------------------------------------------
# Ticket tools
# ---------------------------------------------------------------------------


@tool
def lookup_ticket(
    ticket_id: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> dict:
    """Look up a specific IT support ticket by its ID."""
    doc = db.collection(f"companies/{COMPANY_ID}/tickets").document(ticket_id).get()

    if not doc.exists:
        return {"error": f"Ticket {ticket_id} not found."}

    ticket = doc.to_dict()
    ticket["ticket_id"] = ticket_id

    # When user_context is None (no AuthorizationMiddleware), return everything.
    # When user_context is injected by middleware, enforce RBAC.
    if user_context is None:
        return ticket
    if user_context.role == "admin":
        return ticket
    if user_context.role == "manager" and ticket.get("department") == user_context.department:
        return ticket
    if ticket.get("created_by") == user_context.employee_id:
        return ticket

    return {"error": "Access denied. You can only view your own tickets."}


@tool
def update_ticket(
    ticket_id: str,
    internal_notes: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> dict:
    """Add or update internal notes on a support ticket. Useful for recording
    diagnostic results, status updates, or follow-up information."""
    doc_ref = db.collection(f"companies/{COMPANY_ID}/tickets").document(ticket_id)
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Ticket {ticket_id} not found."}

    ticket = doc.to_dict()

    if user_context is None:
        doc_ref.update({"internal_notes": internal_notes})
        return {"status": "updated", "ticket_id": ticket_id}
    if user_context.role == "admin":
        pass
    elif user_context.role == "manager" and ticket.get("department") == user_context.department:
        pass
    elif ticket.get("created_by") == user_context.employee_id:
        pass
    else:
        return {"error": "Access denied. You can only update your own tickets."}

    doc_ref.update({"internal_notes": internal_notes})
    return {"status": "updated", "ticket_id": ticket_id}


@tool
def search_tickets(
    query: str | None = None,
    status: str | None = None,
    email: str | None = None,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> list[dict]:
    """Search IT support tickets. Use 'status' to filter by ticket status (e.g. 'open', 'in_progress', 'closed'). Use 'query' only for keyword search in ticket title/description. Only use 'email' when the user explicitly asks for tickets by a specific person; do NOT add email when the user just says 'my tickets' or 'all tickets' since access control already handles scoping."""
    base = db.collection(f"companies/{COMPANY_ID}/tickets")

    # RBAC scoping at the Firestore level (security boundary)
    if user_context is not None:
        if user_context.role == "admin":
            results = base.stream()
        elif user_context.role == "manager":
            results = base.where("department", "==", user_context.department).stream()
        else:
            results = base.where("created_by", "==", user_context.employee_id).stream()
    else:
        # No scoping (vulnerable)
        results = base.stream()

    # Resolve email to employee_id for creator filtering
    filter_by_creator = None
    if email:
        matches = (
            db.collection(f"companies/{COMPANY_ID}/employees")
            .where("email", "==", email)
            .limit(1)
            .stream()
        )
        match = next(matches, None)
        if match:
            filter_by_creator = match.id

    # Client-side filtering (can only narrow within RBAC boundary)
    tickets = []
    query_lower = query.lower() if query else ""
    for doc in results:
        ticket = doc.to_dict()
        ticket["ticket_id"] = doc.id
        if query_lower:
            searchable = (
                ticket.get("title", "").lower() + " " +
                ticket.get("description", "").lower() + " " +
                ticket.get("status", "").lower()
            )
            if not any(word in searchable for word in query_lower.split()):
                continue
        if status and ticket.get("status") != status.lower():
            continue
        if filter_by_creator and ticket.get("created_by") != filter_by_creator:
            continue
        tickets.append(ticket)

    return tickets


@tool
def get_wiki_article(
    article_id: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> dict:
    """Retrieve a knowledge base article by its ID."""
    doc = db.collection(f"companies/{COMPANY_ID}/wiki").document(article_id).get()

    if not doc.exists:
        return {"error": f"Article {article_id} not found."}

    article = doc.to_dict()
    article["article_id"] = article_id

    if user_context is None:
        return article

    # Department-restricted articles
    article_dept = article.get("department")
    if article_dept is None:
        return article  # Public article
    if user_context.role == "admin":
        return article
    if article_dept == user_context.department:
        return article

    return {
        "error": f"Access denied. This article is restricted to the {article_dept} department."
    }


def _apply_access_control(articles: list[dict], user_context) -> list[dict]:
    """Filter articles by department access control."""
    if user_context is None:
        return articles
    return [
        a for a in articles
        if a.get("department") is None
        or user_context.role == "admin"
        or a.get("department") == user_context.department
    ]


def _search_wiki_firestore(query: str) -> list[dict]:
    """Similarity search using Firestore's native vector search."""
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from google.cloud.firestore_v1.vector import Vector

    query_embedding = _get_embeddings_model().embed_query(query)

    results = (
        db.collection(f"companies/{COMPANY_ID}/wiki")
        .find_nearest(
            vector_field="embedding",
            query_vector=Vector(query_embedding),
            distance_measure=DistanceMeasure.COSINE,
            limit=5,
        )
        .get()
    )

    articles = []
    for doc in results:
        article = doc.to_dict()
        article.pop("embedding", None)
        article["article_id"] = doc.id
        articles.append(article)
    return articles


@tool
def search_wiki_articles(
    query: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> list[dict]:
    """Search knowledge base articles by semantic similarity."""
    articles = _search_wiki_firestore(query)
    return _apply_access_control(articles, user_context)


# ---------------------------------------------------------------------------
# Dangerous tools (Demo 1 — removed by ToolFilterMiddleware after fix)
# ---------------------------------------------------------------------------


@tool
def reset_password(employee_id: str, new_password: str) -> dict:
    """Reset any employee's password immediately. No confirmation required."""
    # Look up the employee's email, then update their Firebase Auth password
    emp_doc = db.collection(f"companies/{COMPANY_ID}/employees").document(employee_id).get()
    if not emp_doc.exists:
        return {"error": f"Employee {employee_id} not found."}

    email = emp_doc.to_dict()["email"]
    firebase_user = auth.get_user_by_email(email)
    auth.update_user(firebase_user.uid, password=new_password)

    db.collection(f"companies/{COMPANY_ID}/audit_log").add({
        "action": "password_reset",
        "target_employee": employee_id,
        "new_password": new_password,
        "source": "helpdesk_agent",
        "timestamp": firestore.SERVER_TIMESTAMP,
    })
    return {
        "status": "success",
        "employee_id": employee_id,
        "message": f"Password for {employee_id} has been reset.",
    }


@tool
def request_password_reset(
    employee_id: str,
    reason: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> dict:
    """Submit a password reset request for admin approval. Does NOT reset the password directly."""
    requested_by = user_context.employee_id if user_context else "unknown"
    db.collection(f"companies/{COMPANY_ID}/password_reset_requests").add({
        "target_employee": employee_id,
        "reason": reason,
        "requested_by": requested_by,
        "requested_via": "helpdesk_agent",
        "status": "pending_approval",
        "timestamp": firestore.SERVER_TIMESTAMP,
    })
    return {
        "status": "pending",
        "message": "Password reset request submitted. An admin must approve it in the admin portal.",
    }


@tool
def list_software_licenses(
    employee_id: str,
    user_context: Annotated[UserContext | None, InjectedToolArg] = None,
) -> list[dict]:
    """List software licenses assigned to an employee."""
    # Resolve email to internal employee ID if needed
    lookup_id = employee_id
    if "@" in employee_id:
        matches = (
            db.collection(f"companies/{COMPANY_ID}/employees")
            .where("email", "==", employee_id)
            .limit(1)
            .stream()
        )
        match = next(matches, None)
        if match:
            lookup_id = match.id

    # When user_context is injected, enforce RBAC
    if user_context is not None:
        if user_context.role == "admin":
            pass  # Admins can view any employee's licenses
        elif user_context.role == "manager":
            # Managers can view licenses for employees in their department
            emp_doc = db.collection(f"companies/{COMPANY_ID}/employees").document(lookup_id).get()
            if emp_doc.exists and emp_doc.to_dict().get("department") != user_context.department:
                return [{"error": "Access denied. You can only view licenses for employees in your department."}]
        else:
            # Employees can only view their own licenses
            if lookup_id != user_context.employee_id:
                return [{"error": "Access denied. You can only view your own licenses."}]

    results = (
        db.collection(f"companies/{COMPANY_ID}/software_licenses")
        .where("assigned_to", "==", lookup_id)
        .stream()
    )
    return [doc.to_dict() for doc in results]
