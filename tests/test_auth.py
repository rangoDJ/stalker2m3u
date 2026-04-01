import sys
import os

# Add the parent directory to the path so we can import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import authenticate

def test_portal_authentication():
    """
    Integration test to check if the Stalker Portal accepts the current authentication parameters.
    This will actually call the remote portal configured via Environment Variables.
    """
    success, headers = authenticate()
    
    assert success is True, "Failed to authenticate against the Stalker Portal (Check Credentials/URL)"
    assert "Authorization" in headers, "Authorization token is missing from the headers"
    
    print("Authentication test passed successfully!")

if __name__ == "__main__":
    test_portal_authentication()
