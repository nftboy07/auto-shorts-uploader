import os
import re
import urllib.request
import urllib.parse
import json
import http.cookiejar
from pathlib import Path

def test_cookies():
    cookies_path = "/opt/instagram-youtube-shorts-agent/config/instagram_cookies.txt"
    if not os.path.exists(cookies_path):
        print("Cookies file not found at", cookies_path)
        return
        
    print("=== FILE CONTENT ===")
    with open(cookies_path, "r", encoding="utf-8") as f:
        print(f.read())
        
    # Test 1: Raw Dict Cookie Header
    cookies = {}
    with open(cookies_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                parts = re.split(r'\s+', line)
            if len(parts) >= 7 and ("instagram.com" in parts[0] or parts[0] == ""):
                cookies[parts[5]] = parts[6]
                
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    print("Parsed cookies dictionary keys:", list(cookies.keys()))
    
    # Test 2: MozillaCookieJar
    cookie_jar = http.cookiejar.MozillaCookieJar()
    try:
        # Fix formatting
        with open(cookies_path, 'r', encoding='utf-8') as f:
            content = f.read()
        lines = content.splitlines()
        fixed = []
        for line in lines:
            if not line.strip() or line.startswith("#"):
                fixed.append(line)
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                parts = re.split(r'\s+', line)
            if len(parts) >= 7:
                fixed.append("\t".join(parts[:7]))
        
        temp_path = str(Path(cookies_path).parent / "temp_test_cookies.txt")
        with open(temp_path, "w", encoding="utf-8") as f_temp:
            f_temp.write("\n".join(fixed))
            
        cookie_jar.load(temp_path, ignore_discard=True, ignore_expires=True)
        try: os.remove(temp_path)
        except Exception: pass
        
        print("Loaded MozillaCookieJar cookies:")
        for c in cookie_jar:
            print(f"  {c.name}: {c.value[:20]}... (expires={c.expires})")
    except Exception as e:
        print("MozillaCookieJar load failed:", e)

    # Test Request with HTTPCookieProcessor (MozillaCookieJar)
    cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
    proxy = "http://127.0.0.1:1081"
    proxy_handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(proxy_handler, cookie_handler)
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
        ("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"),
        ("Accept-Language", "en-US,en;q=0.9"),
    ]
    
    print("\n--- Testing request with MozillaCookieJar + HTTPCookieProcessor ---")
    try:
        url = "https://www.instagram.com/noryx.amv/"
        with opener.open(url, timeout=15) as resp:
            print("Response URL:", resp.geturl())
            print("Response Code:", resp.status)
            html = resp.read().decode("utf-8", errors="ignore")
            title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            if title:
                print("Title:", title.group(1))
            else:
                print("No title tag found")
            match = re.search(r'property="instapp:owner_id"\s+content="([0-9]+)"', html)
            if match:
                print("Resolved user ID:", match.group(1))
            else:
                print("Could not resolve user ID in HTML")
    except Exception as e:
        print("MozillaCookieJar Request failed:", e)

    # Test Request with raw Cookie header dict
    print("\n--- Testing request with raw Cookie header string ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Cookie": cookie_str,
    }
    req = urllib.request.Request("https://www.instagram.com/noryx.amv/", headers=headers)
    opener2 = urllib.request.build_opener(proxy_handler)
    try:
        with opener2.open(req, timeout=15) as resp:
            print("Response URL:", resp.geturl())
            print("Response Code:", resp.status)
            html = resp.read().decode("utf-8", errors="ignore")
            title = re.search(r"<title>(.*?)</title>", html, re.IGNORECASE)
            if title:
                print("Title:", title.group(1))
            match = re.search(r'property="instapp:owner_id"\s+content="([0-9]+)"', html)
            if match:
                print("Resolved user ID:", match.group(1))
            else:
                print("Could not resolve user ID in HTML")
    except Exception as e:
        print("Raw Cookie Request failed:", e)

if __name__ == "__main__":
    test_cookies()
