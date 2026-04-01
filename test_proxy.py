import urllib.request
import sys
import time

def test_local_proxy():
    print("Testing Stalker2M3U Proxy...")
    print("Base URL: http://localhost:8080")
    
    # Wait a bit for server to start if needed
    time.sleep(2)
    
    try:
        # 1. Test Dashboard (Home)
        print("\n1. Testing Home/Categories...")
        with urllib.request.urlopen("http://localhost:8080/") as resp:
            content = resp.read().decode()
            if "genres" in content:
                print("   [OK] Home loaded (JSON).")
                # print(content)
            else:
                print("   [FAIL] Home content mismatch.")
        
        # 2. Test Cricket Playlist (Genre ID 32)
        print("\n2. Testing Cricket Playlist (genre_id=32)...")
        url = "http://localhost:8080/playlist.m3u?genre_id=32"
        with urllib.request.urlopen(url) as resp:
            content = resp.read().decode()
            lines = content.splitlines()
            channels = [l for l in lines if l.startswith("#EXTINF")]
            print(f"   [RESULT] Found {len(channels)} channels in Category 32.")
            if channels:
                print("   Channels found:")
                for c in channels[:5]:
                    print(f"    - {c.split(',')[-1]}")
            else:
                print("   [EMPTY] No channels returned for Category 32.")
                # Show raw output if empty to debug
                print("   Raw output start:", content[:100])

    except Exception as e:
        print(f"   [ERROR] Connection failed: {e}")

if __name__ == "__main__":
    test_local_proxy()
