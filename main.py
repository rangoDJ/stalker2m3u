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
    Advanced status dashboard showing proxy configuration, filters and available genres.
    """
    from fastapi.responses import HTMLResponse
    import urllib.parse
    
    # Try to get current genres
    success, headers = authenticate()
    available_genres = []
    status_class = "offline"
    status_text = "ERROR"
    
    if success:
        cats = get_categories(headers)
        if cats:
            # Sort genres by title
            available_genres = sorted(
                [{"id": k, "title": v} for k, v in cats.items()],
                key=lambda x: x["title"]
            )
            status_class = "online"
            status_text = "ACTIVE"

    exclude_genres = FILTERS.get("exclude_genres", [])
    exclude_channels = FILTERS.get("exclude_channels", [])
    
    # Filter out excluded genres from the quick links
    filtered_genres = [g for g in available_genres if g["title"] not in exclude_genres]
    
    base_url = os.getenv("BASE_URL_PORT", "http://localhost:8080/")
    if not base_url.endswith("/"):
        base_url += "/"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Stalker2M3U | Proxy Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg-color: #0f172a;
                --card-bg: #1e293b;
                --text-primary: #f8fafc;
                --text-secondary: #94a3b8;
                --accent-color: #38bdf8;
                --success-color: #22c55e;
                --danger-color: #ef4444;
                --border-color: #334155;
            }}
            
            * {{ box-sizing: border-box; }}
            body {{ 
                font-family: 'Inter', sans-serif; 
                line-height: 1.6; 
                max-width: 1000px; 
                margin: 0 auto; 
                padding: 40px 20px; 
                background-color: var(--bg-color); 
                color: var(--text-primary);
            }}
            
            h1 {{ font-weight: 700; font-size: 2.5rem; margin-bottom: 0.5rem; color: var(--text-primary); letter-spacing: -0.025em; }}
            h2 {{ font-weight: 600; font-size: 1.25rem; margin-top: 0; margin-bottom: 1.5rem; color: var(--accent-color); border-bottom: 1px solid var(--border-color); padding-bottom: 10px; }}
            
            .subtitle {{ color: var(--text-secondary); margin-bottom: 3rem; font-weight: 400; }}
            
            .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 24px; margin-bottom: 32px; }}
            
            .card {{ 
                background: var(--card-bg); 
                padding: 24px; 
                border-radius: 16px; 
                border: 1px solid var(--border-color);
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
                transition: transform 0.2s ease, border-color 0.2s ease;
            }}
            
            .card:hover {{ border-color: var(--accent-color); }}
            
            .status {{ 
                display: inline-flex; 
                align-items: center;
                padding: 4px 12px; 
                border-radius: 9999px; 
                font-weight: 600; 
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }}
            
            .online {{ background: rgba(34, 197, 94, 0.1); color: var(--success-color); border: 1px solid rgba(34, 197, 94, 0.2); }}
            .offline {{ background: rgba(239, 68, 68, 0.1); color: var(--danger-color); border: 1px solid rgba(239, 68, 68, 0.2); }}
            
            .info-row {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid rgba(51, 65, 85, 0.5); }}
            .label {{ font-weight: 500; color: var(--text-secondary); font-size: 0.875rem; }}
            .value {{ font-family: 'ui-monospace', monospace; color: var(--text-primary); font-size: 0.875rem; word-break: break-all; text-align: right; margin-left: 10px; }}
            
            .genre-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }}
            .genre-tag {{ 
                background: rgba(56, 189, 248, 0.05); 
                border: 1px solid var(--border-color);
                padding: 10px 16px; 
                border-radius: 12px;
                color: var(--text-primary);
                text-decoration: none;
                font-size: 0.875rem;
                display: flex;
                align-items: center;
                transition: all 0.2s ease;
            }}
            
            .genre-tag:hover {{ 
                background: rgba(56, 189, 248, 0.1);
                border-color: var(--accent-color);
                transform: translateY(-2px);
            }}
            
            .genre-tag::before {{ content: '●'; color: var(--accent-color); margin-right: 8px; font-size: 0.6rem; }}
            
            .exclusion-list {{ list-style: none; padding: 0; margin: 0; }}
            .exclusion-item {{ 
                padding: 8px 12px; 
                background: rgba(239, 68, 68, 0.05); 
                border-radius: 8px; 
                margin-bottom: 8px; 
                font-size: 0.8125rem; 
                color: var(--text-secondary);
                border: 1px solid rgba(239, 68, 68, 0.1);
                display: flex;
                align-items: center;
            }}
            .exclusion-item::before {{ content: '✕'; color: var(--danger-color); margin-right: 8px; font-weight: bold; }}
            
            .main-playlist-btn {{
                background: var(--accent-color);
                color: var(--bg-color);
                padding: 12px 24px;
                border-radius: 12px;
                text-decoration: none;
                font-weight: 600;
                display: inline-flex;
                align-items: center;
                margin-top: 10px;
                transition: opacity 0.2s ease;
            }}
            .main-playlist-btn:hover {{ opacity: 0.9; }}
            
            @media (max-width: 640px) {{
                h1 {{ font-size: 2rem; }}
                .grid {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <h1>Stalker2M3U Proxy Dashboard</h1>
        <p class="subtitle">High-performance M3U proxy for Stalker Portals</p>
        
        <div class="grid">
            <div class="card">
                <h2>Portal Connection</h2>
                <div class="info-row">
                    <span class="label">Status</span>
                    <span class="status {status_class}">{status_text}</span>
                </div>
                <div class="info-row">
                    <span class="label">Portal URL</span>
                    <span class="value">{PORTAL_URL}</span>
                </div>
                <div class="info-row">
                    <span class="label">STB MAC</span>
                    <span class="value">{MAC}</span>
                </div>
                <div class="info-row">
                    <span class="label">Base URL</span>
                    <span class="value">{base_url}</span>
                </div>
                <div style="margin-top: 20px;">
                    <a href="/playlist.m3u" class="main-playlist-btn">
                        <span style="margin-right: 8px;">📄</span> Download Full Playlist
                    </a>
                </div>
            </div>

            <div class="card" style="grid-row: span 2;">
                <h2>Active Filters</h2>
                <div class="info-row">
                    <span class="label">Excluded Genres</span>
                    <span class="value">{len(exclude_genres)}</span>
                </div>
                <div class="exclusion-list">
                    {"".join(f'<div class="exclusion-item">{g}</div>' for g in exclude_genres) if exclude_genres else '<div class="info-row"><span class="value" style="text-align:left; color:var(--text-secondary)">None</span></div>'}
                </div>
                
                <div class="info-row" style="margin-top: 24px;">
                    <span class="label">Excluded Channels</span>
                    <span class="value">{len(exclude_channels)}</span>
                </div>
                <div class="exclusion-list">
                    {"".join(f'<div class="exclusion-item">{c}</div>' for c in exclude_channels) if exclude_channels else '<div class="info-row"><span class="value" style="text-align:left; color:var(--text-secondary)">None</span></div>'}
                </div>
            </div>

            <div class="card" style="grid-column: 1 / -1;">
                <h2>Available Genre Playlists</h2>
                <div class="genre-grid">
                    {"".join(f'<a href="/playlist.m3u?genre={urllib.parse.quote(g["title"], safe="")}" class="genre-tag">{g["title"]}</a>' for g in filtered_genres) if filtered_genres else '<p style="color:var(--text-secondary)">No genres available or all filtered out.</p>'}
                </div>
            </div>
        </div>
        
        <p style="text-align: center; color: var(--text-secondary); font-size: 0.75rem; margin-top: 40px;">
            Stalker2M3U v2.0 &bull; Running on FastAPI
        </p>
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
    
    # Fetch categories
    categories = get_categories(headers)
    
    # Map genre name to genre ID if filtering is requested
    target_category_id = None
    if genre:
        import urllib.parse
        decoded_genre = urllib.parse.unquote(genre).strip().lower()
        for cat_id, cat_title in categories.items():
            if decoded_genre == cat_title.strip().lower():
                target_category_id = cat_id
                logger.info(f"Filtering by category ID: {target_category_id} ('{cat_title}')")
                break
    
    # Loop over paginated channels
    while True:
        page_url = f"{PORTAL_URL}?type=itv&action=get_ordered_list&JsHttpRequest=1-xml&p={page}"
        if target_category_id:
            page_url += f"&category={target_category_id}"
            
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
                  if genre:
                       req_genre = genre.strip().lower()
                       chn_genre = cat_name.strip().lower()
                       if req_genre not in chn_genre:
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
