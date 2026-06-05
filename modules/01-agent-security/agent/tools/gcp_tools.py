"""GCP operations tools for the TechCorp IT agent.

These tools use Python GCP client libraries that automatically inherit
the Cloud Run service account's credentials. When running with the
default compute SA (roles/editor), they can access almost anything.
When running with the custom least-privilege SA, they get 403 errors.

These tools exist for Demo 1 (Blast Radius) and Demo 6 (Least Privilege).
They are removed from the agent's tool list by ToolFilterMiddleware after
Demo 1's fix.
"""

from google.api_core.exceptions import Forbidden, NotFound
from google.cloud import secretmanager, storage
from langchain_core.tools import tool

from agent.config import GCP_PROJECT

_storage_client = None
_secret_client = None


def _get_storage_client():
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client(project=GCP_PROJECT)
    return _storage_client


def _get_secret_client():
    global _secret_client
    if _secret_client is None:
        _secret_client = secretmanager.SecretManagerServiceClient()
    return _secret_client


@tool
def list_storage_buckets() -> dict:
    """List all Google Cloud Storage buckets in the project."""
    try:
        client = _get_storage_client()
        buckets = list(client.list_buckets())
        return {
            "status": "success",
            "bucket_count": len(buckets),
            "buckets": [{"name": b.name} for b in buckets],
        }
    except Forbidden as e:
        return {"status": "permission_denied", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@tool
def check_storage_bucket(bucket_name: str) -> dict:
    """List contents of a Google Cloud Storage bucket."""
    try:
        bucket = _get_storage_client().get_bucket(bucket_name)
        blobs = list(bucket.list_blobs(max_results=20))
        return {
            "status": "success",
            "bucket": bucket_name,
            "object_count": len(blobs),
            "objects": [{"name": b.name, "size": b.size} for b in blobs],
        }
    except Forbidden as e:
        return {"status": "permission_denied", "error": str(e)}
    except NotFound:
        return {"status": "not_found", "error": f"Bucket {bucket_name} not found."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@tool
def get_service_secret(secret_name: str) -> dict:
    """Retrieve a secret value from Google Cloud Secret Manager."""
    try:
        name = f"projects/{GCP_PROJECT}/secrets/{secret_name}/versions/latest"
        response = _get_secret_client().access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        return {
            "status": "success",
            "secret_name": secret_name,
            "value": payload,
        }
    except Forbidden as e:
        return {"status": "permission_denied", "error": str(e)}
    except NotFound:
        return {"status": "not_found", "error": f"Secret {secret_name} not found."}
    except Exception as e:
        return {"status": "error", "error": str(e)}
