"""Storage Tools — Firebase Storage upload for step agents.

Uploads files to gs://skillmatic-ea1ab.firebasestorage.app/runs/{orgId}/{runId}/{stepId}/
and records metadata in the Firestore files/ subcollection.
"""

from __future__ import annotations

import os
import mimetypes

from google.cloud import storage as gcs
from firebase_admin import firestore as fs

from step_agent.firestore_client import _get_db, write_event
from step_agent.file_tools import write_shared_file

BUCKET_NAME = "skillmatic-ea1ab.firebasestorage.app"

_bucket = None


def _get_bucket():
    global _bucket
    if _bucket is None:
        client = gcs.Client()
        _bucket = client.bucket(BUCKET_NAME)
    return _bucket


def upload_to_storage(
    org_id: str,
    run_id: str,
    step_id: str,
    local_path: str,
    *,
    name: str | None = None,
    description: str | None = None,
    mime_type: str | None = None,
) -> dict:
    """Upload a local file to Firebase Storage and record metadata in Firestore.

    Args:
        org_id: Organization ID.
        run_id: Playbook run ID.
        step_id: Step ID.
        local_path: Absolute path to the file on the local filesystem.
        name: Filename for storage (defaults to basename of local_path).
        description: Optional description for the file.
        mime_type: MIME type (auto-detected if not provided).

    Returns:
        Dict with storagePath and fileId.
    """
    if name is None:
        name = os.path.basename(local_path)
    if mime_type is None:
        mime_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

    storage_path = f"runs/{org_id}/{run_id}/{step_id}/{name}"
    file_size = os.path.getsize(local_path)

    # Upload to GCS
    bucket = _get_bucket()
    blob = bucket.blob(storage_path)
    blob.upload_from_filename(local_path, content_type=mime_type)
    print(f"[storage] Uploaded {local_path} -> gs://{BUCKET_NAME}/{storage_path} ({file_size} bytes)")

    # Write file doc to Firestore
    db = _get_db()
    file_data = {
        "name": name,
        "stepId": step_id,
        "storagePath": storage_path,
        "mimeType": mime_type,
        "sizeBytes": file_size,
        "uploadedAt": fs.SERVER_TIMESTAMP,
        "description": description,
    }
    _, doc_ref = (
        db.collection("orgs").document(org_id)
        .collection("playbook_runs").document(run_id)
        .collection("files").add(file_data)
    )
    print(f"[storage] Wrote file doc: {doc_ref.id}")

    # Emit file_ready event
    write_event(
        org_id, run_id, "file_ready",
        step_id=step_id,
        payload={
            "fileId": doc_ref.id,
            "name": name,
            "storagePath": storage_path,
            "mimeType": mime_type,
            "sizeBytes": file_size,
        },
    )

    return {"storagePath": storage_path, "fileId": doc_ref.id}


def write_report(
    org_id: str,
    run_id: str,
    step_id: str,
    content: str,
    *,
    title: str = "report.md",
    description: str | None = None,
) -> dict:
    """Write a report to /shared AND upload to Firebase Storage.

    Args:
        org_id: Organization ID.
        run_id: Playbook run ID.
        step_id: Step ID.
        content: Report content (markdown).
        title: Filename for the report.
        description: Optional description.

    Returns:
        Dict with storagePath and fileId.
    """
    # Write locally (ephemeral, for orchestrator to read before pod terminates)
    local_path = write_shared_file(f"results/{step_id}/{title}", content)

    # Upload to persistent storage
    return upload_to_storage(
        org_id, run_id, step_id,
        local_path,
        name=title,
        description=description or f"Step report: {title}",
        mime_type="text/markdown",
    )
