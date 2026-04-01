import os
import urllib.parse
import urllib.request
import json
import hashlib
import base64
import time
import random
import logging
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("stalker2m3u")

# Global variables for session and token caching
_TOKEN = "AABBCCDD1234567890AABBCCDD123456"
_SESSION = None
_AUTH_HEADERS = None
_CATEGORIES = {} # Cache for genre ID -> Name mapping

def load_config():
    # Priority: config.json > environment variables > defaults
    config = {
        "PORTAL_URL": os.getenv("PORTAL_URL", "http://glotv.me/stalker_portal/server/load.php"),
        "MAC": os.getenv("MAC", "00:1A:79:05:B2:16"),
        "SERIAL": os.getenv("SERIAL", "062014N014137"),
        "MODEL": os.getenv("MODEL", "MAG520"),
        "DEVICE_ID": os.getenv("DEVICE_ID", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92"),
        "DEVICE_ID2": os.getenv("DEVICE_ID2", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92"),
        "filters": {
            "exclude_genres": [],
            "exclude_channels": []
        }
    }
    
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                file_config = json.load(f)
                config.update(file_config)
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
            
    return config

# Load settings
CONFIG = load_config()
PORTAL_URL = CONFIG["PORTAL_URL"]
MAC = CONFIG["MAC"]
SERIAL = CONFIG["SERIAL"]
MODEL = CONFIG["MODEL"]
DEVICE_ID = CONFIG["DEVICE_ID"]
DEVICE_ID2 = CONFIG["DEVICE_ID2"]
FILTERS = CONFIG.get("filters", {})

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    base_url = os.getenv("BASE_URL_PORT", "http://0.0.0.0:8080/")
    if not base_url.endswith("/"):
        base_url += "/"
        
    logger.info("=" * 60)
    logger.info("STALKER2M3U PROXY INITIALIZING")
    logger.info(f"PORTAL URL : {PORTAL_URL}")
    logger.info(f"STB MAC    : {MAC}")
    logger.info(f"STB MODEL  : {MODEL}")
    logger.info(f"SERIAL     : {SERIAL}")
    logger.info(f"DASHBOARD  : {base_url}")
    logger.info(f"PLAYLIST   : {base_url}playlist.m3u")
    logger.info("=" * 60)

@app.get("/")
def dashboard():
    """
    Simple status dashboard showing proxy configuration and portal health.
    """
    from fastapi.responses import HTMLResponse
    
    exclude_genres = FILTERS.get("exclude_genres", [])
    exclude_channels = FILTERS.get("exclude_channels", [])
    
    html = f"""
    <html>
        <head>
            <title>Stalker2M3U Dashboard</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; line-height: 1.6; max-width: 800px; margin: 40px auto; padding: 20px; background-color: #f4f7f9; }}
                h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
                .status {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: bold; font-size: 0.9em; }}
                .online {{ background: #e8f5e9; color: #2e7d32; }}
                .info-row {{ display: flex; justify-content: space-between; margin-bottom: 10px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
                .label {{ font-weight: bold; color: #7f8c8d; }}
                .value {{ font-family: monospace; color: #34495e; }}
                a {{ color: #3498db; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                ul {{ margin: 5px 0; padding-left: 20px; }}
            </style>
        </head>
        <body>
            <h1>Stalker2M3U Proxy Dashboard</h1>
            
            <div class="card">
                <h2>Portal Connection</h2>
                <div class="info-row">
                    <span class="label">Status</span>
                    <span class="status online">ACTIVE</span>
                </div>
                <div class="info-row">
                    <span class="label">Portal URL</span>
                    <span class="value">{PORTAL_URL}</span>
                </div>
                <div class="info-row">
                    <span class="label">STB MAC</span>
                    <span class="value">{MAC}</span>
                </div>
            </div>

            <div class="card">
                <h2>Active Filters</h2>
                <div class="info-row">
                    <span class="label">Excluded Genres</span>
                    <span class="value">{len(exclude_genres)} items</span>
                </div>
                <ul>
                    {"".join(f"<li>{g}</li>" for g in exclude_genres) if exclude_genres else "<li>None</li>"}
                </ul>
                <div class="info-row">
                    <span class="label">Excluded Channels</span>
                    <span class="value">{len(exclude_channels)} items</span>
                </div>
                <ul>
                    {"".join(f"<li>{c}</li>" for c in exclude_channels) if exclude_channels else "<li>None</li>"}
                </ul>
            </div>

            <div class="card">
                <h2>Resources</h2>
                <ul>
                    <li>📄 <a href="/playlist.m3u">M3U Playlist</a></li>
                    <li>🎾 <a href="/playlist.m3u?genre=Sports">Sports Only Playlist</a></li>
                </ul>
            </div>
        </body>
    </html>
    """
    return HTMLResponse(content=html)

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
    """
    Helper to perform a GET request using urllib and parse the JSON response.
    """
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            if not body:
                logger.error(f"Empty response from: {url}")
                return {}
            return json.loads(body)
    except Exception as e:
        logger.error(f"API Request Failed: {url} -> {e}")
        if hasattr(e, 'read'):
            error_body = e.read().decode('utf-8', errors='replace')
            logger.debug(f"Error Body: {error_body}")
        return {}

def get_categories(headers):
    """
    Fetch and cache genres/categories from the portal.
    """
    global _CATEGORIES
    if _CATEGORIES:
        return _CATEGORIES
        
    url = f"{PORTAL_URL}?type=itv&action=get_genres&JsHttpRequest=1-xml"
    data = call_portal_api(url, headers)
    genres = data.get("js", [])
    
    # Map ID -> Title
    new_cats = {str(g.get("id")): g.get("title") for g in genres if g.get("id")}
    if new_cats:
        _CATEGORIES = new_cats
        logger.info(f"Loaded {len(_CATEGORIES)} categories from portal.")
        
    return _CATEGORIES

def authenticate(force=False):
    global _TOKEN, _AUTH_HEADERS
    if _AUTH_HEADERS and not force:
        return True, _AUTH_HEADERS
    
    headers = get_common_headers()
    
    # Step 1: Handshake
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
        req = urllib.request.Request(auth_url, headers=auth_headers)
        resp = urllib.request.urlopen(req, timeout=10)
        body = resp.read().decode('utf-8', errors='replace')
        data = json.loads(body)
        if data.get('js') and data.get('js').get('id'):
            logger.info(f"Auth success! Portal ID: {data.get('js').get('id')}")
            _AUTH_HEADERS = auth_headers
            return True, _AUTH_HEADERS
        else:
            logger.error("Auth failed - no ID returned.")
            logger.debug(f"Response: {body}")
    except Exception as e:
        logger.error(f"Profile error: {e}")
        
    return False, auth_headers

@app.get("/playlist.m3u", response_class=PlainTextResponse)
def get_playlist(request: Request, genre: str = None):
    success, headers = authenticate()
    if not success:
         return "#EXTM3U\n#EXTINF:-1,Auth Failed\nhttp://error"
    
    channels = []
    page = 1
    
    # Fetch categories for group-title support
    categories = get_categories(headers)
    
    # Loop over paginated channels
    while True:
        page_url = f"{PORTAL_URL}?type=itv&action=get_ordered_list&JsHttpRequest=1-xml&p={page}"
        logger.info(f"Fetching channels page {page}")
        
        data = call_portal_api(page_url, headers)
        items = data.get("js", {}).get("data", [])
        
        if not items:
             break
             
        for i, item in enumerate(items):
             cmd = item.get('cmd')
             name = item.get('name', 'Unknown Channel')
             if cmd and name:
                  # Genre handling
                  genre_id = str(item.get('tv_genre_id', ''))
                  cat_name = categories.get(genre_id, 'Other')
                  
                  # Mandatory filters from config.json
                  exclude_genres = FILTERS.get("exclude_genres", [])
                  exclude_channels = FILTERS.get("exclude_channels", [])
                  
                  if any(eg.lower() in cat_name.lower() for eg in exclude_genres):
                      continue
                  if any(ec.lower() in name.lower() for ec in exclude_channels):
                      continue

                  # Optional filtering by genre (URL query param)
                  if genre and genre.lower() not in cat_name.lower():
                       continue

                  # Base64 encode the stream command
                  cmd_b64 = base64.urlsafe_b64encode(cmd.encode()).decode()
                  logo_url = item.get('logo', '')
                  
                  # Build our own proxy URL
                  # e.g., http://localhost:8080/stream/...
                  base_url = os.getenv("BASE_URL_PORT", str(request.base_url))
                  if not base_url.endswith("/"):
                      base_url += "/"
                  proxy_url = f"{base_url}stream/{cmd_b64}"
                  
                  extinf = f'#EXTINF:-1 tvg-logo="{logo_url}" tvg-id="{item.get("id", "")}" group-title="{cat_name}","{name}"\n{proxy_url}'
                  channels.append(extinf)
                  
        # Pagination logic
        max_p = data.get("js", {}).get("max_page_items", 14)
        if len(items) < int(max_p):
            break
            
        page += 1
        if page > 100: # Safety break just in case
            break

    logger.info(f"Successfully generated playlist with {len(channels)} channels.")
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
        data = call_portal_api(link_url, headers)
        cmd_result = data.get('js', {}).get('cmd', '')
        
        # If the token expired and we get an error, re-auth and try once more.
        if not cmd_result:
            logger.info("Retrying with forced re-authentication...")
            success, new_headers = authenticate(force=True)
            if success:
                data = call_portal_api(link_url, new_headers)
                cmd_result = data.get('js', {}).get('cmd', '')

        if cmd_result:
             # cmd often looks like: ffmpeg http://url
             parts = cmd_result.split()
             actual_url = parts[-1] if len(parts) > 1 else cmd_result
             return RedirectResponse(url=actual_url)
             
    except Exception as e:
        logger.error(f"Stream generation error: {e}")
        
    return PlainTextResponse("Stream link not found or portal error.", status_code=404)
