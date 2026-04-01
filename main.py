import os
import urllib.parse
import urllib.request
import json
import hashlib
import base64
import time
import random
import logging
import http.cookiejar
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse, HTMLResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("stalker2m3u")

# Global variables
_TOKEN = None
_CATEGORIES = {}
_CHANNELS_CACHE = []
_CACHE_EXPIRY = 600 # 10 minutes
_LAST_FETCH_TIME = 0

def load_config():
    config = {
        "PORTAL_URL": os.getenv("PORTAL_URL", "http://glotv.me/stalker_portal/server/load.php"),
        "MAC": os.getenv("MAC", "00:1A:79:05:B2:16"),
        "SERIAL": os.getenv("SERIAL", "062014N014137"),
        "MODEL": os.getenv("MODEL", "MAG520"),
        "DEVICE_ID": os.getenv("DEVICE_ID", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92"),
        "DEVICE_ID2": os.getenv("DEVICE_ID2", "51C0AA6D99A09AA28EB3ED32D9D2BEE557EE791F5F8BB7555B77218E220BBD92"),
    }
    cp = os.path.join(os.path.dirname(__file__), "config.json")
    if os.path.exists(cp):
        try:
            with open(cp, "r") as f: config.update(json.load(f))
        except: pass
    return config

CONFIG = load_config()
PORTAL_URL = CONFIG["PORTAL_URL"]
MAC = CONFIG["MAC"]
SERIAL = CONFIG["SERIAL"]
MODEL = CONFIG["MODEL"]
DEVICE_ID = CONFIG["DEVICE_ID"]
DEVICE_ID2 = CONFIG["DEVICE_ID2"]

class StalkerClient:
    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.token = ""
        self.server_random = ""
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'X-User-Agent': f'Model: {MODEL}; Link: WiFi',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cookie': f'mac={urllib.parse.quote(MAC)}; sn={urllib.parse.quote(SERIAL)}; stb_lang=en; timezone=UTC;'
        }
    
    def _call(self, url, use_token=True):
        if use_token and self.token:
             if "token=" not in url:
                  url += f"&token={self.token}"
        
        headers = dict(self.headers)
        if use_token and self.token:
             headers['Authorization'] = f'Bearer {self.token}'
        
        # Inject standard cookies if JAR is empty
        domain = urllib.parse.urlparse(PORTAL_URL).netloc
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(0, 'mac', urllib.parse.quote(MAC), None, False, domain, True, False, '/', True, False, None, False, None, None, {}))
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(0, 'sn', urllib.parse.quote(SERIAL), None, False, domain, True, False, '/', True, False, None, False, None, None, {}))
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(0, 'stb_lang', 'en', None, False, domain, True, False, '/', True, False, None, False, None, None, {}))
        self.cookie_jar.set_cookie(http.cookiejar.Cookie(0, 'timezone', 'UTC', None, False, domain, True, False, '/', True, False, None, False, None, None, {}))
             
        try:
            req = urllib.request.Request(url, headers=headers)
            with self.opener.open(req, timeout=15) as resp:
                body = resp.read().decode('utf-8', errors='replace')
                return json.loads(body) if body else {}
        except Exception as e:
            logger.error(f"API Error: {url} -> {e}")
            return {}

    def authenticate(self):
        if self.token: return True
        hs_url = f'{PORTAL_URL}?type=stb&action=handshake&JsHttpRequest=1-xml'
        res = self._call(hs_url, use_token=False)
        if isinstance(res, dict):
            js_data = res.get('js', {})
            self.token = js_data.get('token', '')
            if self.token:
                logger.info(f"Handshake OK. Token: {self.token[:8]}...")
        
        sig = base64.b64encode(hashlib.sha256((DEVICE_ID + SERIAL).encode()).digest()).decode()
        ver = urllib.parse.quote("ImageDescription: 2.20.02-pub-520; ImageDate: Thu Apr 29 15:17:55 EEST 2021")
        params = (f"&ver={ver}&sn={SERIAL}&stb_type={MODEL}&device_id={DEVICE_ID}&device_id2={DEVICE_ID2}"
                  f"&signature={urllib.parse.quote(sig)}")
        
        auth_url = f'{PORTAL_URL}?type=stb&action=get_profile&JsHttpRequest=1-xml&hd=1{params}'
        res = self._call(auth_url)
        
        if isinstance(res, dict) and res.get('js', {}).get('status') == 2:
             logger.info("Status 2: Retrying with do_auth...")
             do_auth_url = f'{PORTAL_URL}?type=stb&action=do_auth&JsHttpRequest=1-xml{params}'
             res = self._call(do_auth_url)
             
        if isinstance(res, dict):
            js_data = res.get('js')
            if isinstance(js_data, dict) and (js_data.get('id') or js_data.get('status') == 1):
                logger.info(f"Stalker Auth SUCCESS. ID: {js_data.get('id')}")
                return True
        logger.error(f"Stalker Auth FAILED: {res}")
        return False

    def get_genres(self):
        url = f"{PORTAL_URL}?type=itv&action=get_genres&JsHttpRequest=1-xml"
        res = self._call(url)
        return res.get("js", []) if isinstance(res, dict) else []

    def fetch_all_channels(self, genre_id=None):
        cat_param = f"&category={genre_id}" if genre_id else ""
        url = f"{PORTAL_URL}?type=itv&action=get_all_channels&JsHttpRequest=1-xml{cat_param}"
        res = self._call(url)
        if isinstance(res, dict) and isinstance(res.get("js"), list):
             return res.get("js")
        
        logger.warning(f"get_all_channels failed (genre={genre_id}), falling back to paginated list.")
        items = []
        for page in range(1, 50):
             p_url = f"{PORTAL_URL}?type=itv&action=get_ordered_list&JsHttpRequest=1-xml&p={page}{cat_param}"
             p_res = self._call(p_url)
             p_items = p_res.get("js", {}).get("data", []) if isinstance(p_res, dict) else []
             if not p_items: break
             items.extend(p_items)
             if len(p_items) < p_res.get("js", {}).get("max_page_items", 14): break
        return items

client = StalkerClient()
app = FastAPI()

@app.get("/")
def api_home():
    if not client.authenticate(): return {"status": "auth_failed"}
    genres = client.get_genres()
    return {"status": "ok", "genres": genres}

@app.get("/playlist.m3u", response_class=PlainTextResponse)
def get_m3u(request: Request, genre_id: str = None):
    if not client.authenticate(): return "#EXTM3U\n#EXTINF:-1,Authentication failed\nhttp://error"
    
    items = client.fetch_all_channels(genre_id)
    genres_raw = client.get_genres()
    genres_map = {str(g.get("id")): g.get("title") for g in genres_raw if isinstance(g, dict)}
    
    m3u = ["#EXTM3U"]
    for item in items:
        if not isinstance(item, dict): continue
        gid = str(item.get("tv_genre_id", ""))
        # No manual filter needed now as API handles it
        name = item.get("name", "Unknown")
        cmd = item.get("cmd", "")
        if not cmd: continue
        
        cmd_b = base64.urlsafe_b64encode(cmd.encode()).decode()
        proxy_url = f"{request.base_url}stream/{cmd_b}"
        cat_name = genres_map.get(gid, "General")
        m3u.append(f'#EXTINF:-1 tvg-id="{item.get("id", "")}" tvg-logo="{item.get("logo", "")}" group-title="{cat_name}",{name}\n{proxy_url}')
        
    return "\n".join(m3u)

@app.get("/stream/{cmd_b64}")
def stream_proxy(cmd_b64: str):
    if not client.authenticate(): return PlainTextResponse("Auth failed", status_code=401)
    try:
        cmd = base64.urlsafe_b64decode(cmd_b64 + "=" * (-len(cmd_b64) % 4)).decode()
        url = f"{PORTAL_URL}?type=itv&action=create_link&cmd={urllib.parse.quote(cmd)}&JsHttpRequest=1-xml"
        res = client._call(url)
        link = res.get("js", {}).get("cmd", "")
        if link:
            return RedirectResponse(url=link.split()[-1] if " " in link else link)
    except: pass
    return PlainTextResponse("Stream link failed", status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
