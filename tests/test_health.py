def test_health_check_endpoint(client):
    """
    Verify GET /api/health returns 200 OK and expected confirmation payload.
    """
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["message"] == "Document Verification API is running"
