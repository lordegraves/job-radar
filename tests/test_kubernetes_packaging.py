"""Verify Kubernetes resources preserve Junior's single-writer data model."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUBERNETES = ROOT / "packaging/kubernetes"


def _load(name: str) -> dict:
    return yaml.safe_load((KUBERNETES / name).read_text(encoding="utf-8"))


def test_deployment_uses_one_non_root_writer_and_health_probes() -> None:
    deployment = _load("deployment.yaml")
    spec = deployment["spec"]
    pod = spec["template"]["spec"]
    container = pod["containers"][0]

    assert spec["replicas"] == 1
    assert spec["strategy"]["type"] == "Recreate"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert container["readinessProbe"]["httpGet"]["path"] == "/health"
    assert container["livenessProbe"]["httpGet"]["path"] == "/health"
    assert container["volumeMounts"][0]["mountPath"] == "/var/lib/junior"
    assert {"name": "JUNIOR_PORT", "value": "8000"} in container["env"]


def test_service_is_private_cluster_ip() -> None:
    service = _load("service.yaml")
    assert service["spec"]["type"] == "ClusterIP"


def test_secret_manifest_contains_no_secret_value() -> None:
    secret = _load("secret.yaml")
    assert secret["data"] == {}
    assert "stringData" not in secret


def test_cronjobs_are_guarded_and_share_persistent_data() -> None:
    scan = _load("scan-cronjob.yaml")
    backup = _load("backup-cronjob.yaml")

    for resource in (scan, backup):
        assert resource["spec"]["suspend"] is True
        assert resource["spec"]["concurrencyPolicy"] == "Forbid"
        assert resource["spec"]["successfulJobsHistoryLimit"] == 3
        assert resource["spec"]["failedJobsHistoryLimit"] == 3
    assert (
        scan["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        ["containers"][0]["command"][0]
        == "junior-scheduled"
    )
    assert (
        backup["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        ["containers"][0]["command"][0]
        == "junior-backup"
    )
    assert "--keep" in (
        backup["spec"]["jobTemplate"]["spec"]["template"]["spec"]
        ["containers"][0]["command"]
    )
