import os
import urllib.parse
import urllib.request
import json
import hashlib
import base64
import time
import random
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("verify_portal")

# Global variables
_TOKEN = "AABBCCDD1234567890AABBCCDD123456"
_AUTH_HEADERS = None

def load_config():
    config = {
        "PORTAL_URL": "http://glotv.me/stalker_portal/server/load.php",
        "MAC": "00:1A:79:05:B2:16",
        "SERIAL": "062014N014137",
        "MODEL": "MAG520",
        "DEVICE_ID": "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92",
        "DEVICE_ID2": "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92",
    }
    
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                file_config = json.load(f)
                config.update(file_config)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
            
    return config

CONFIG = load_config()
PORTAL_URL = CONFIG["PORTAL_URL"]
MAC = CONFIG["MAC"]
SERIAL = CONFIG["SERIAL"]
MODEL = CONFIG["MODEL"]
DEVICE_ID = CONFIG["DEVICE_ID"]
DEVICE_ID2 = CONFIG["DEVICE_ID2"]

def get_hw_version_2(mac, sn):
    return hashlib.sha1((mac.upper() + sn).encode()).hexdigest()

def get_device_signature(dev_id, sn):
    hash_bytes = hashlib.sha256((dev_id + sn).encode()).digest()
    return base64.b64encode(hash_bytes).decode()

def get_api_sig_params(mac, sn, model, dev_id):
    hw_ver = get_hw_version_2(mac, sn)
    ts = int(time.time())
    rand_hex = hashlib.sha1(str(random.random()).encode()).hexdigest()
    
    metrics = {
        "mac": mac,
        "sn": sn,
        "model": model,
        "type": "STB",
        "uid": dev_id,
        "random": rand_hex
    }
    metrics_json = json.dumps(metrics, separators=(',', ':'))
    metrics_encoded = urllib.parse.quote(metrics_json)
    
    return f"metrics={metrics_encoded}&hw_version_2={hw_ver}&timestamp={ts}&api_signature=262&prehash=a46fc18d33875f3f79cb7c8afb5ae16b7fbf2443"

def get_common_headers():
    return {
        'User-Agent': f'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
        'X-User-Agent': f'Model: {MODEL}; Link: WiFi',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }

def call_portal_api(url, headers):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            if not body:
                return {}
            return json.loads(body)
    except Exception as e:
        logger.error(f"API Request Failed: {url} -> {e}")
        return {}

def authenticate():
    global _TOKEN, _AUTH_HEADERS
    headers = get_common_headers()
    
    # Handshake
    hs_url = f'{PORTAL_URL}?type=stb&action=handshake&token={_TOKEN}&JsHttpRequest=1-xml'
    hs_headers = dict(headers)
    hs_headers['Cookie'] = f'sn={SERIAL}; mac={MAC}; stb_lang=en; timezone=UTC'
    
    try:
        req = urllib.request.Request(hs_url, headers=hs_headers)
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        data = json.loads(body)
        new_token = data.get('js', {}).get('token')
        if new_token:
            _TOKEN = new_token
    except Exception as e:
        logger.error(f"Handshake error: {e}")
        
    # Get Profile
    api_sig = get_api_sig_params(MAC, SERIAL, MODEL, DEVICE_ID)
    sig = get_device_signature(DEVICE_ID, SERIAL)
    ver_str = urllib.parse.quote("ImageDescription: 2.20.02-pub-520; ImageDate: Thu Apr 29 15:17:55 EEST 2021")
    
    auth_url = (f'{PORTAL_URL}?type=stb&action=get_profile&JsHttpRequest=1-xml&hd=1'
                f'&ver={ver_str}&sn={SERIAL}&stb_type={MODEL}'
                f'&device_id={DEVICE_ID}&device_id2={DEVICE_ID2}'
                f'&signature={urllib.parse.quote(sig)}&auth_second_step=1&{api_sig}')
                
    auth_headers = dict(headers)
    auth_headers['Authorization'] = f'Bearer {_TOKEN}'
    auth_headers['Cookie'] = f'PHPSESSID=null; sn={urllib.parse.quote(SERIAL)}; mac={urllib.parse.quote(MAC)}; stb_lang=en; timezone=UTC;'
    
    try:
        req = urllib.request.Request(auth_url, headers=auth_headers)
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode('utf-8', errors='replace')
        data = json.loads(body)
        if data.get('js') and data.get('js').get('id'):
            logger.info(f"Auth success! Portal ID: {data.get('js').get('id')}")
            _AUTH_HEADERS = auth_headers
            return True, _AUTH_HEADERS
        else:
            logger.error("Auth failed - no ID returned.")
    except Exception as e:
        logger.error(f"Profile error: {e}")
        
    return False, auth_headers

def main():
    print("=" * 60)
    print("STALKER PORTAL VERIFICATION")
    print(f"Portal: {PORTAL_URL}")
    print(f"MAC   : {MAC}")
    print("=" * 60)
    
    success, headers = authenticate()
    if not success:
        print("Failed to authenticate with the portal.")
        return

    # Fetch genres
    url = f"{PORTAL_URL}?type=itv&action=get_genres&JsHttpRequest=1-xml"
    data = call_portal_api(url, headers)
    genres = data.get("js", [])
    
    if not genres:
        print("No genres found.")
        return

    base_url = os.getenv("BASE_URL_PORT", "http://localhost:8080/")
    if not base_url.endswith("/"):
        base_url += "/"

    print(f"\nAvailable Genres ({len(genres)}):")
    print("-" * 60)
    
    for g in genres:
        title = g.get("title")
        g_id = g.get("id")
        playlist_link = f"{base_url}playlist.m3u?genre={urllib.parse.quote(title)}"
        print(f"ID: {g_id:<5} | Genre: {title:<25} | Link: {playlist_link}")

    print("-" * 60)
    print(f"\nGeneral Playlist: {base_url}playlist.m3u")
    print("=" * 60)

if __name__ == "__main__":
    main()
