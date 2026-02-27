"""K8s Client — helpers for creating step agent Jobs and PVCs.

Uses in-cluster config when running inside GKE (ServiceAccount token auto-mounted).
The playbook agent creates step agent Jobs in the same namespace.

No project-specific values are hardcoded — the image registry comes from the
AGENT_IMAGE_REGISTRY env var, set by the Firebase Function that launched us.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass

from kubernetes import client, config

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

_api_batch: client.BatchV1Api | None = None
_api_core: client.CoreV1Api | None = None


def _init_clients() -> None:
    global _api_batch, _api_core
    if _api_batch is not None:
        return
    config.load_incluster_config()
    _api_batch = client.BatchV1Api()
    _api_core = client.CoreV1Api()


def _namespace() -> str:
    return os.environ.get("NAMESPACE", "skillmatic")


# ---------------------------------------------------------------------------
# Image resolution
# ---------------------------------------------------------------------------


def resolve_image(agent_image: str) -> str:
    """Resolve a step's agentImage to a full container image reference.

    If the image already contains '/' (e.g. a full registry path), use as-is.
    Otherwise prepend the AGENT_IMAGE_REGISTRY env var.
    """
    if "/" in agent_image:
        return agent_image
    registry = os.environ.get("AGENT_IMAGE_REGISTRY", "")
    if not registry:
        raise ValueError(
            f"Cannot resolve short image name '{agent_image}': "
            "AGENT_IMAGE_REGISTRY env var is not set"
        )
    return f"{registry}/{agent_image}"


# ---------------------------------------------------------------------------
# Job result
# ---------------------------------------------------------------------------


@dataclass
class JobResult:
    succeeded: bool
    job_name: str
    message: str


# ---------------------------------------------------------------------------
# PVC helpers
# ---------------------------------------------------------------------------


def create_run_pvc(run_id: str, size_gi: str = "1Gi") -> str:
    """Create a PersistentVolumeClaim for a playbook run's shared storage.

    Returns the PVC name.
    """
    _init_clients()
    pvc_name = f"run-{run_id}"

    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            namespace=_namespace(),
            labels={"app": "skillmatic", "run-id": run_id},
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(
                requests={"storage": size_gi},
            ),
        ),
    )

    _api_core.create_namespaced_persistent_volume_claim(
        namespace=_namespace(), body=pvc,
    )
    return pvc_name


# ---------------------------------------------------------------------------
# Job helpers
# ---------------------------------------------------------------------------


def create_step_job(
    run_id: str,
    step_id: str,
    image: str,
    org_id: str,
    pvc_name: str,
    *,
    timeout_minutes: int = 30,
    env_extras: dict[str, str] | None = None,
    service_account: str = "agent-sa",
) -> str:
    """Create a K8s Job for a step agent.

    Returns the Job name.
    """
    _init_clients()
    job_name = f"step-{run_id}-{step_id}"[:63]  # K8s name limit

    env_vars = [
        client.V1EnvVar(name="RUN_ID", value=run_id),
        client.V1EnvVar(name="ORG_ID", value=org_id),
        client.V1EnvVar(name="STEP_ID", value=step_id),
        client.V1EnvVar(name="NAMESPACE", value=_namespace()),
    ]
    for k, v in (env_extras or {}).items():
        env_vars.append(client.V1EnvVar(name=k, value=v))

    labels = {
        "app": "skillmatic",
        "run-id": run_id,
        "step-id": step_id,
        "component": "step-agent",
    }

    container = client.V1Container(
        name="step-agent",
        image=image,
        env=env_vars,
        volume_mounts=[
            client.V1VolumeMount(name="shared", mount_path="/shared"),
        ],
    )

    pod_spec = client.V1PodSpec(
        service_account_name=service_account,
        restart_policy="Never",
        containers=[container],
        volumes=[
            client.V1Volume(
                name="shared",
                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                    claim_name=pvc_name,
                ),
            ),
        ],
    )

    job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name,
            namespace=_namespace(),
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=timeout_minutes * 60,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels=labels),
                spec=pod_spec,
            ),
        ),
    )

    _api_batch.create_namespaced_job(namespace=_namespace(), body=job)
    return job_name


# ---------------------------------------------------------------------------
# Job monitoring
# ---------------------------------------------------------------------------


def wait_for_job(
    job_name: str,
    timeout_seconds: int = 1800,
    poll_interval: int = 10,
    on_poll: Callable[[], None] | None = None,
) -> JobResult:
    """Poll a K8s Job until it succeeds, fails, or times out.

    Args:
        on_poll: Optional callback invoked on each poll iteration (e.g. to
                 check Firestore step status for paused detection).
    """
    _init_clients()
    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        job = _api_batch.read_namespaced_job(
            name=job_name, namespace=_namespace(),
        )
        status = job.status

        if status.succeeded and status.succeeded >= 1:
            return JobResult(
                succeeded=True,
                job_name=job_name,
                message="Job completed successfully",
            )

        if status.failed and status.failed >= 1:
            reason = "Job failed"
            if status.conditions:
                for cond in status.conditions:
                    if cond.type == "Failed":
                        reason = cond.message or cond.reason or reason
                        break
            return JobResult(
                succeeded=False,
                job_name=job_name,
                message=reason,
            )

        if on_poll is not None:
            on_poll()

        time.sleep(poll_interval)

    return JobResult(
        succeeded=False,
        job_name=job_name,
        message=f"Job timed out after {timeout_seconds}s",
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def delete_job(job_name: str) -> None:
    """Delete a Job and its pods (best-effort)."""
    _init_clients()
    try:
        _api_batch.delete_namespaced_job(
            name=job_name,
            namespace=_namespace(),
            propagation_policy="Foreground",
        )
    except client.ApiException as exc:
        if exc.status != 404:
            raise


def delete_pvc(pvc_name: str) -> None:
    """Delete a PVC."""
    _init_clients()
    _api_core.delete_namespaced_persistent_volume_claim(
        name=pvc_name, namespace=_namespace(),
    )
