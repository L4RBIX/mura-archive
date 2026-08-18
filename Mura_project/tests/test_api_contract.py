from apps.api.main import app


def test_openapi_exposes_canonical_family_scoped_contract() -> None:
    paths = app.openapi()["paths"]

    assert "/v1/families/{family_id}/recordings" in paths
    assert "/v1/families/{family_id}/recordings/{recording_id}" in paths
    assert "/v1/families/{family_id}/recordings/{recording_id}/review-items" in paths
    assert "/v1/families/{family_id}/jobs/{job_id}" in paths
    assert "/v1/families/{family_id}/replays" in paths
    assert paths["/v1/families/{family_id}/recordings"]["post"]["responses"]["202"]


def test_openapi_retains_operator_and_infrastructure_routes() -> None:
    paths = app.openapi()["paths"]

    assert "/health" in paths
    assert "/ready" in paths
    assert "/v1/capabilities" in paths
    assert "/v1/process-transcript" in paths
    assert "/v1/jobs/{job_id}/trace" in paths
    assert "/v1/operations/release" in paths
    assert "/v1/operations/release/activate" in paths
    assert "/v1/operations/release/rollback" in paths
    assert "/v1/operations/retention" in paths
    assert "/v1/operations/retention/apply" in paths


def test_openapi_no_longer_exposes_unscoped_application_routes() -> None:
    paths = app.openapi()["paths"]

    assert "/v1/recordings" not in paths
    assert "/v1/recordings/{recording_id}" not in paths
    assert "/v1/recordings/{recording_id}/review-items" not in paths
    assert "/v1/jobs/{job_id}" not in paths
    assert not [path for path in paths if path.endswith("/retry")]
