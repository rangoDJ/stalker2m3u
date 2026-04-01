import os
import json
import urllib.parse
import urllib.request
import time
import hashlib
import base64
import http.cookiejar

# Configuration
with open("config.json", 'r') as f: config = json.load(f)
PORTAL_URL = config.get("PORTAL_URL")
MAC = config.get("MAC")
SERIAL = config.get("SERIAL")
DEVICE_ID = config.get("DEVICE_ID")
DEVICE_ID2 = config.get("DEVICE_ID2", DEVICE_ID)
MODEL = config.get("MODEL", "MAG520")

class StalkerTester:
    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.token = ""
    
    def call(self, type_param, action, params=""):
        url = f"{PORTAL_URL}?type={type_param}&action={action}&JsHttpRequest=1-xml{params}"
        if self.token: url += f"&token={self.token}"
             
        headers = {
            'User-Agent': 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3',
            'X-User-Agent': f'Model: {MODEL}; Link: WiFi',
            'Cookie': f'mac={urllib.parse.quote(MAC)}; sn={urllib.parse.quote(SERIAL)}; stb_lang=en; timezone=UTC;'
        }
        if self.token: headers['Authorization'] = f'Bearer {self.token}'
        
        req = urllib.request.Request(url, headers=headers)
        try:
            with self.opener.open(req, timeout=10) as resp:
                content = resp.read().decode('utf-8')
                return json.loads(content)
        except: return {}

    def run_test(self):
        print("1. Handshake...")
        res = self.call("stb", "handshake")
        if not isinstance(res, dict): return
        self.token = res.get("js", {}).get("token", "")
        print(f"   Token: {self.token[:8]}...")

        print("2. Authenticate...")
        sig = base64.b64encode(hashlib.sha256((DEVICE_ID + SERIAL).encode()).digest()).decode()
        ver = urllib.parse.quote("ImageDescription: 2.20.02-pub-520; ImageDate: Thu Apr 29 15:17:55 EEST 2021")
        params = (f"&ver={ver}&sn={SERIAL}&stb_type={MODEL}&device_id={DEVICE_ID}&device_id2={DEVICE_ID2}"
                  f"&signature={urllib.parse.quote(sig)}")
        
        res = self.call("stb", "get_profile", params)
        if isinstance(res, dict) and res.get("js", {}).get("status") == 2:
             print("   Status 2: Retrying with do_auth...")
             res = self.call("stb", "do_auth", params)

        if isinstance(res, dict) and (res.get("js", {}).get("id") or res.get("js", {}).get("status") == 1):
             print(f"   Auth Success! ID: {res.get('js', {}).get('id')}")
        else:
             print(f"   Auth Failed: {res}")

        print("3. Checking Category 32 (Cricket)...")
        res_32 = self.call("itv", "get_ordered_list", "&category=32&p=1")
        if isinstance(res_32, dict) and isinstance(res_32.get("js"), dict):
            items = res_32.get("js", {}).get("data", [])
            print(f"   RESULT: Found {len(items)} channels.")
            for i in items[:10]:
                print(f"    - {i.get('name')} (ID: {i.get('id')})")
        else:
            print(f"   Category 32 failed: {res_32}")

if __name__ == "__main__":
    StalkerTester().run_test()
