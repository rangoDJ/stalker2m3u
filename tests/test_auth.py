import sys
import os

# Add the parent directory to the path so we can import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import StalkerClient
import pytest

@pytest.mark.skipif(os.getenv("GITHUB_ACTIONS") == "true", reason="Live portal authentication typically blocked by datacenter IPs in CI")
def test_portal_authentication():
    """
    Integration test to check if the Stalker Portal accepts the current authentication parameters.
    """
    client = StalkerClient()
    success = client.authenticate()
    
    assert success is True, "Failed to authenticate against the Stalker Portal"
    assert client.token != "", "Session token is missing"
    
    print("Authentication test passed successfully!")

if __name__ == "__main__":
    test_portal_authentication()
