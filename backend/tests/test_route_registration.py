from collections import Counter

from app.main import app


def test_openapi_operation_ids_are_unique_and_nested_routes_remain_available():
    schema = app.openapi()
    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and operation.get("operationId")
    ]
    duplicates = {
        operation_id: count
        for operation_id, count in Counter(operation_ids).items()
        if count > 1
    }
    assert duplicates == {}

    paths = schema["paths"]
    assert "/api/v1/legal/config" in paths
    assert "/api/v1/legal/status" in paths
    assert "/api/v1/legal/accept" in paths
    assert "/api/v1/privacy/export" in paths
    assert "/api/v1/privacy/requests" in paths
    assert "/api/v1/clips/{clip_id}/behavior" in paths
    assert "/api/v1/exports/{export_id}/download-event" in paths
    assert "/api/v1/admin/learning/summary" in paths
