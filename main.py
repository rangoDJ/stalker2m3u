import os
import urllib.parse
import json
import hashlib
import base64
import time
import random
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

app = FastAPI()

PORTAL_URL = os.getenv("PORTAL_URL", "http://glotv.me/stalker_portal/server/load.php")
MAC = os.getenv("MAC", "00:1A:79:05:B2:16")
SERIAL = os.getenv("SERIAL", "062014N014137")
MODEL = os.getenv("MODEL", "MAG520")
DEVICE_ID = os.getenv("DEVICE_ID", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92")
DEVICE_ID2 = os.getenv("DEVICE_ID2", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92")

# Global variables for session and token caching
_TOKEN = "AABBCCDD1234567890AABBCCDD123456"
_SESSION = None
_AUTH_HEADERS = None

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

def authenticate(force=False):
    global _TOKEN, _SESSION, _AUTH_HEADERS
    if _AUTH_HEADERS and not force:
        return True, _AUTH_HEADERS

    if not _SESSION:
        _SESSION = requests.Session()
    
    headers = get_common_headers()
    
    # Step 1: Handshake
    hs_url = f'{PORTAL_URL}?type=stb&action=handshake&token={_TOKEN}&JsHttpRequest=1-xml'
    hs_headers = dict(headers)
    hs_headers['Cookie'] = f'sn={SERIAL}; mac={MAC}; stb_lang=en; timezone=UTC'
    
    try:
        resp = _SESSION.get(hs_url, headers=hs_headers, timeout=10)
        data = resp.json()
        new_token = data.get('js', {}).get('token')
        if new_token:
            _TOKEN = new_token
    except Exception as e:
        print(f"Handshake error: {e}")
        
    # Step 2: Get Profile (Auth)
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
        resp = _SESSION.get(auth_url, headers=auth_headers, timeout=10)
        data = resp.json()
        if data.get('js', {}).get('id'):
            print(f"Auth success! Portal ID: {data.get('js').get('id')}")
            _AUTH_HEADERS = auth_headers
            return True, _AUTH_HEADERS
        else:
            print("Auth failed - no ID returned.")
    except Exception as e:
        print(f"Profile error: {e}")
        
    return False, auth_headers

@app.get("/playlist.m3u", response_class=PlainTextResponse)
def get_playlist(request: Request):
    success, headers = authenticate()
    if not success:
         return "#EXTM3U\n#EXTINF:-1,Auth Failed\nhttp://error"
    
    channels = []
    page = 1
    
    # Loop over paginated channels
    while True:
        page_url = f"{PORTAL_URL}?type=itv&action=get_ordered_list&JsHttpRequest=1-xml&p={page}"
        print(f"Fetching channels page {page}")
        try:
            r = _SESSION.get(page_url, headers=headers, timeout=10)
            data = r.json()
            items = data.get("js", {}).get("data", [])
            
            if not items:
                 break
                 
            for item in items:
                 cmd = item.get('cmd')
                 name = item.get('name', 'Unknown Channel')
                 if cmd and name:
                      # Base64 encode the stream command
                      cmd_b64 = base64.urlsafe_b64encode(cmd.encode()).decode()
                      logo_url = item.get('logo', '')
                      
                      # Build our own proxy URL
                      # e.g., http://localhost:8080/stream/...
                      base_url = str(request.base_url)
                      proxy_url = f"{base_url}stream/{cmd_b64}"
                      
                      extinf = f'#EXTINF:-1 tvg-logo="{logo_url}" tvg-id="{item.get("id", "")}","{name}"\n{proxy_url}'
                      channels.append(extinf)
                      
            # Pagination logic
            max_p = data.get("js", {}).get("max_page_items", 14)
            if len(items) < int(max_p):
                break
                
            page += 1
            if page > 100: # Safety break just in case
                break
        except Exception as e:
            print(f"Error fetching channels at page {page}: {e}")
            break

    # Construct the final M3U
    m3u = "#EXTM3U\n" + "\n".join(channels)
    return m3u

@app.get("/stream/{cmd_b64}")
def stream_proxy(cmd_b64: str):
    success, headers = authenticate()
    if not success:
         return PlainTextResponse("Auth failed", status_code=401)
         
    try:
        # Decode base64 padding issues can be solved by adding missing =
        padding = 4 - (len(cmd_b64) % 4)
        if padding and padding != 4:
            cmd_b64 += "=" * padding
        cmd = base64.urlsafe_b64decode(cmd_b64.encode()).decode()
    except Exception as e:
        return PlainTextResponse(f"Invalid cmd format: {e}", status_code=400)
    
    # Request the stream link
    link_url = f"{PORTAL_URL}?type=itv&action=create_link&cmd={urllib.parse.quote(cmd)}&JsHttpRequest=1-xml"
    try:
        r = _SESSION.get(link_url, headers=headers, timeout=10)
        data = r.json()
        cmd_result = data.get('js', {}).get('cmd', '')
        
        # If the token expired and we get an error, re-auth and try once more.
        if not cmd_result:
            authenticate(force=True)
            r = _SESSION.get(link_url, headers=_AUTH_HEADERS, timeout=10)
            data = r.json()
            cmd_result = data.get('js', {}).get('cmd', '')

        if cmd_result:
             # cmd often looks like: ffmpeg http://url
             parts = cmd_result.split()
             actual_url = parts[-1] if len(parts) > 1 else cmd_result
             return RedirectResponse(url=actual_url)
             
    except Exception as e:
        print(f"Stream generation error: {e}")
        
    return PlainTextResponse("Stream link not found or portal error.", status_code=404)
