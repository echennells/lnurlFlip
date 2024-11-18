import pytest
from fastapi.testclient import TestClient

from lnbits.app import create_app
from lnbits.settings import settings

from tests.helpers import get_random_invoice_hash

# Create test client
app = create_app()
client = TestClient(app)

# Test data
test_data = {
    "name": "Test Universal",
    "wallet": "test_wallet_123",
    "lnurlwithdrawamount": 1000,
    "selectedLnurlp": "test_lnurlp_123",
    "selectedLnurlw": "test_lnurlw_123"
}

@pytest.mark.asyncio
async def test_create_lnurluniversal():
    """Test creating a new LnurlUniversal record"""
    response = client.post(
        "/lnurluniversal/api/v1/myex",
        json=test_data,
        headers={"X-Api-Key": "test_key"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == test_data["name"]
    assert data["wallet"] == test_data["wallet"]
    assert data["state"] == "payment"
    assert data["total"] == 0
    assert data["uses"] == 0

@pytest.mark.asyncio
async def test_get_lnurluniversal():
    """Test retrieving LnurlUniversal records"""
    # First create a record
    create_response = client.post(
        "/lnurluniversal/api/v1/myex",
        json=test_data,
        headers={"X-Api-Key": "test_key"}
    )
    universal_id = create_response.json()["id"]
    
    # Then retrieve it
    response = client.get(
        f"/lnurluniversal/api/v1/myex",
        headers={"X-Api-Key": "test_key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    assert any(record["id"] == universal_id for record in data)

@pytest.mark.asyncio
async def test_delete_lnurluniversal():
    """Test deleting a LnurlUniversal record"""
    # First create a record
    create_response = client.post(
        "/lnurluniversal/api/v1/myex",
        json=test_data,
        headers={"X-Api-Key": "test_key"}
    )
    universal_id = create_response.json()["id"]
    
    # Then delete it
    response = client.delete(
        f"/lnurluniversal/api/v1/myex/{universal_id}",
        headers={"X-Api-Key": "test_key"}
    )
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(
        f"/lnurluniversal/api/v1/myex",
        headers={"X-Api-Key": "test_key"}
    )
    data = get_response.json()
    assert not any(record["id"] == universal_id for record in data)

@pytest.mark.asyncio
async def test_update_lnurluniversal():
    """Test updating a LnurlUniversal record"""
    # First create a record
    create_response = client.post(
        "/lnurluniversal/api/v1/myex",
        json=test_data,
        headers={"X-Api-Key": "test_key"}
    )
    universal_id = create_response.json()["id"]
    
    # Update data
    updated_data = test_data.copy()
    updated_data["name"] = "Updated Name"
    
    # Perform update
    response = client.put(
        f"/lnurluniversal/api/v1/myex/{universal_id}",
        json=updated_data,
        headers={"X-Api-Key": "test_key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
