def test_list_resources_returns_items_envelope(client):
    response = client.get("/api/v1/resources")
    assert response.status_code == 200
    assert response.json() == {"items": []}