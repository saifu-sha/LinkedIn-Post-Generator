# scrape_with_voyager_fallback_dedupe.py
# (Same as your last working script but adds robust duplicate filtering while preserving order)

import time
import re
import json
import os
import html
from pathlib import Path
from collections import deque
import traceback

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoSuchElementException
from bs4 import BeautifulSoup as bs
from dotenv import load_dotenv

import requests
import threading

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)


def getenv_int(name, default):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def getenv_float(name, default):
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return float(value)
    except ValueError:
        return default


# ---------- CONFIG ----------
username = os.getenv("LINKEDIN_USERNAME")
password = os.getenv("LINKEDIN_PASSWORD")
# set to a company/profile page to test
# page = os.getenv("LINKEDIN_PAGE")
page = os.getenv("LINKEDIN_PAGE")
# page = os.getenv("LINKEDIN_PAGE")

OUTPUT_JSON = "posts_likes_clean.json"
SCROLL_PAUSE_TIME = getenv_float("SCROLL_PAUSE_TIME", 1.5)
MAX_SCROLLS = getenv_int("MAX_SCROLLS", 1)

# Selenium options
chrome_options = Options()
# chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--window-size=1280,900")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# ---------- TEXT / NUMBER HELPERS ----------
def basic_clean(s):
    s = '' if s is None else str(s)
    s = html.unescape(s)
    s = re.sub(r'http\S+|www\.\S+', '', s)
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\r\n?', '\n', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    s = re.sub(r'[ \t]+\n', '\n', s)
    s = re.sub(r'\n[ \t]+', '\n', s)
    s = ''.join(ch for ch in s if ord(ch) >= 32 or ch == '\n')
    s = re.sub(r'([!?\.]){2,}', r'\1', s)
    s = re.sub(r'\s+([,.;:!?])', r'\1', s)
    s = re.sub(r'([,;:!?\.])([A-Za-z0-9])', r'\1 \2', s)
    s = re.sub(r'\s+\)', ')', s)
    s = re.sub(r'\(\s+', '(', s)
    return s.strip()

def sentence_capitalize(text):
    if not text:
        return text
    text = re.sub(r'[ \t]+', ' ', text.strip())
    def preserve_token(tok):
        if tok.isalpha() and sum(1 for c in tok if c.isupper()) > 1:
            return tok
        return tok.lower()
    tokens = re.findall(r'\S+|\n', text)
    rebuilt = []
    for t in tokens:
        if t == '\n':
            rebuilt.append(t)
        else:
            rebuilt.append(preserve_token(t))
    rebuilt = ' '.join([tok for tok in rebuilt if tok != ' ']).replace(' \n ', '\n')
    def cap(m):
        return m.group(1) + m.group(2).upper()
    rebuilt = re.sub(r'(^|[\.!\?\n]\s+)([a-z])', cap, rebuilt)
    rebuilt = re.sub(r'\bi\b', 'I', rebuilt)
    rebuilt = re.sub(r' *\n *', '\n', rebuilt)
    return rebuilt.strip()

def normalize_hashtags(s):
    """Normalize messy hashtag blocks into inline hashtags (e.g. '#NikeFootball #SwooshLife')."""
    if not s:
        return s
    # 1) Remove the literal word 'hashtag' (any case)
    s = re.sub(r'(?i)\bhashtag\b', '', s)
    # 2) Turn '#\nWord' or '# \n Word' into ' #Word'
    s = re.sub(r'#\s*\n\s*([A-Za-z0-9_]+)', r' #\1', s)
    # 3) Turn '\n#Word' into ' #Word' (join inline)
    s = re.sub(r'\n#\s*([A-Za-z0-9_]+)', r' #\1', s)
    # 4) Turn '# Word' into ' #Word'
    s = re.sub(r'#\s+([A-Za-z0-9_]+)', r' #\1', s)
    # 5) If there are lines that are just a single token (looks like tag), prefix with '#'
    #    (This catches lines like: "\nNikeFootball\nSwooshLife" where tags got split)
    def prefix_tag_lines(text):
        lines = text.split('\n')
        new_lines = []
        for ln in lines:
            ln_stripped = ln.strip()
            # single token with letters/digits/underscore -> probably a hashtag
            if re.fullmatch(r'[A-Za-z0-9_]+', ln_stripped):
                new_lines.append('#' + ln_stripped)
            else:
                new_lines.append(ln)
        return '\n'.join(new_lines)
    s = prefix_tag_lines(s)
    # 6) Join hashtag-lines to preceding content by replacing "...\n#Tag" -> "... #Tag"
    s = re.sub(r'([^\n])\n(#\w+)', r'\1 \2', s)
    # 7) Remove any leftover lines that are only a stray '#'
    s = re.sub(r'(?m)^\s*#\s*$', '', s)
    # 8) Collapse repeated spaces and clean newlines a bit
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()

def clean_post_text(raw_text):
    """Apply cleaning pipeline to raw post text, *then* normalize hashtags nicely."""
    if raw_text is None:
        return ""
    s = basic_clean(raw_text)
    # convert bullet/delimiters to newline
    s = re.sub(r'\s*[•·—–]\s*', '\n', s)
    # strip each line and drop empty lines
    lines = [ln.strip() for ln in s.split('\n')]
    s = '\n'.join([ln for ln in lines if ln != ''])
    # sentence capitalization (your existing helper)
    s = sentence_capitalize(s)
    # now normalize hashtags (this ensures '#Nike' stays inline and removes 'hashtag' tokens)
    s = normalize_hashtags(s)
    # final tidy-up: remove trailing spaces on lines and collapse accidental multiple newlines
    s = re.sub(r'[ \t]+$', '', s, flags=re.MULTILINE)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()

def convert_abbreviated_to_number(s):
    if not s:
        return 0
    s = str(s).strip().replace(',', '').upper()
    s = re.sub(r'[^\dKM\.]', '', s)
    if s == '':
        return 0
    try:
        if 'K' in s:
            return int(float(s.replace('K', '')) * 1000)
        if 'M' in s:
            return int(float(s.replace('M', '')) * 1000000)
        if '.' in s:
            return int(float(s))
        return int(s)
    except Exception:
        return 0

def extract_number_from_text(s):
    if not s:
        return 0
    m = re.search(r'(\d{1,3}(?:[.,]\d{3})*|\d+(?:\.\d+)?\s*[KMkm]?)', s)
    if m:
        return convert_abbreviated_to_number(m.group(1))
    return 0

# ---------- DOM helpers ----------
def get_post_text_from_container(container_soup):
    selectors = [
        ("div", {"class": re.compile(r"feed-shared-update-v2__description-wrapper")}),
        ("div", {"class": re.compile(r"feed-shared-text")}),
        ("span", {"class": re.compile(r"break-words")}),
        ("div", {"data-test-id": "post-content"}),
        ("p", {}),
    ]
    for tag, attrs in selectors:
        if attrs:
            el = container_soup.find(tag, attrs=attrs)
        else:
            el = container_soup.find(tag)
        if el and el.get_text(strip=True):
            return el.get_text("\n", strip=True)
    text = container_soup.get_text("\n", strip=True)
    return text if text and len(text) > 3 else ""

def extract_likes_from_container_soup(container_soup):
    max_candidate = 0
    for btn in container_soup.find_all("button"):
        aria = (btn.get("aria-label") or "").lower()
        txt = btn.get_text(" ", strip=True)
        combined = f"{aria} {txt}".strip()
        if 'reaction' in aria or 'like' in aria or 'react' in aria:
            v = extract_number_from_text(combined)
            if v:
                return v
        v = extract_number_from_text(combined)
        if v > max_candidate:
            max_candidate = v
    text_blob = container_soup.get_text(" ", strip=True)
    m = re.search(r'(\d+(?:[.,]\d+)?\s*[KMkm]?)\s*(?:reactions|reaction|likes|like|react|•|·|\u00B7)', text_blob)
    if m:
        return convert_abbreviated_to_number(m.group(1))
    all_nums = re.findall(r'(\d+(?:[.,]\d+)?\s*[KMkm]?)', text_blob)
    candidates = [convert_abbreviated_to_number(x) for x in all_nums]
    return max(candidates) if candidates else 0

# ---------- Voyager JSON helpers ----------
def find_first_key(d, key):
    q = deque([d])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            if key in cur:
                return cur[key]
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for item in cur:
                if isinstance(item, (dict, list)):
                    q.append(item)
    return None

def extract_texts_from_json(obj):
    texts = []
    q = deque([obj])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            if 'commentary' in cur and isinstance(cur['commentary'], dict):
                t = cur['commentary'].get('text')
                if isinstance(t, str) and t.strip():
                    texts.append(t)
            if 'text' in cur and isinstance(cur['text'], str):
                if cur['text'].strip():
                    texts.append(cur['text'])
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for v in cur:
                if isinstance(v, (dict, list)):
                    q.append(v)
    return texts

def extract_likes_from_json(obj):
    candidates = []
    q = deque([obj])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            if 'totalSocialActivityCount' in cur:
                try:
                    candidates.append(int(cur['totalSocialActivityCount']))
                except:
                    pass
            if 'totalSocialActivityCounts' in cur:
                sub = cur['totalSocialActivityCounts']
                if isinstance(sub, dict) and 'count' in sub:
                    try:
                        candidates.append(int(sub['count']))
                    except:
                        pass
            if 'socialDetail' in cur and isinstance(cur['socialDetail'], dict):
                s = cur['socialDetail']
                if 'totalSocialActivityCounts' in s and isinstance(s['totalSocialActivityCounts'], dict):
                    c = s['totalSocialActivityCounts'].get('count')
                    if isinstance(c, int):
                        candidates.append(c)
            for v in cur.values():
                if isinstance(v, (dict, list)):
                    q.append(v)
        elif isinstance(cur, list):
            for v in cur:
                if isinstance(v, (dict, list)):
                    q.append(v)
    if candidates:
        return max(candidates)
    try:
        s = json.dumps(obj)
        m = re.search(r'"count"\s*:\s*(\d+)', s)
        if m:
            return int(m.group(1))
    except:
        pass
    return 0

# ---------- Helper to create requests session from selenium ----------
def build_requests_session_from_selenium(driver, proxy=None):
    sess = requests.Session()
    if proxy:
        sess.proxies.update({"http": proxy, "https": proxy})
    for c in driver.get_cookies():
        cookie_dict = {k: c.get(k) for k in ("name", "value", "domain", "path", "expiry", "secure", "httpOnly")}
        try:
            sess.cookies.set(cookie_dict["name"], cookie_dict["value"], domain=cookie_dict["domain"])
        except Exception:
            sess.cookies.set(cookie_dict["name"], cookie_dict["value"])
    return sess

# ---------- Manual verification wait ----------
def wait_for_manual_verification(driver, timeout=300):
    start = time.time()
    done_event = threading.Event()
    input_result = {"pressed": False}
    def wait_for_enter():
        try:
            input("Press Enter here once you've completed the verification in the browser (or wait for cookie detection)...\n")
            input_result["pressed"] = True
            done_event.set()
        except Exception:
            pass
    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()
    print("\nLinkedIn appears to require additional verification (checkpoint / 2FA).")
    print("Please complete the verification manually in the opened browser window.")
    print("Either press Enter in this terminal after verification or the script will detect the session cookie and continue automatically.")
    print(f"Waiting up to {timeout} seconds for manual verification...\n")
    while True:
        try:
            cookies = driver.get_cookies()
        except Exception:
            cookies = []
        if any(c.get('name') == 'li_at' for c in cookies):
            print("Login cookie (li_at) detected — continuing.")
            done_event.set()
            return True
        if done_event.is_set() and input_result.get("pressed"):
            try:
                cookies = driver.get_cookies()
            except Exception:
                cookies = []
            if any(c.get('name') == 'li_at' for c in cookies):
                print("li_at cookie detected after manual confirmation — continuing.")
                return True
            else:
                print("Enter pressed but li_at cookie not found yet. If verification is incomplete, finish it in the browser then press Enter again.")
                done_event.clear()
                t = threading.Thread(target=wait_for_enter, daemon=True)
                t.start()
        if time.time() - start > timeout:
            print("\nTimeout waiting for manual verification.")
            return False
        time.sleep(2)

# ---------- Utility: wait until profile/posts content appears ----------
def wait_until_posts_visible(driver, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            html_src = driver.page_source
            soup = bs(html_src, "html.parser")
            if soup.find("article"):
                return True
            if soup.find("div", {"role": "feed"}) or soup.find("div", {"class": re.compile(r"^scaffold-layout.*")}):
                if soup.find("div", {"class": re.compile(r"feed-shared-update-v2|occludable-update|update-card")}):
                    return True
            nav_active = soup.find(lambda tag: tag.name in ("a","button","div") and tag.get_text(strip=True).lower().startswith("posts"))
            if nav_active:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False

# ---------- Robust requests helper ----------
def requests_get_with_retry(sess, url, headers=None, params=None, timeout=20, retries=3):
    attempt = 0
    while attempt < retries:
        try:
            r = sess.get(url, headers=headers, params=params, timeout=timeout)
            return r
        except requests.exceptions.RequestException as e:
            attempt += 1
            backoff = 1.5 ** attempt
            print(f"Requests error on attempt {attempt}/{retries}: {e}. Retrying in {backoff:.1f}s...")
            time.sleep(backoff)
    return None

# ---------- Fingerprint helper (dedupe) ----------
def fingerprint_text(s):
    """
    Compute a stable fingerprint for deduping:
    - clean whitespace, lowercase, remove punctuation except hashtags and newline,
    - collapse repeated spaces and convert newlines to single newline markers.
    """
    if not s:
        return ""
    # preserve hashtags but remove punctuation that changes duplicates (commas, quotes etc)
    s2 = s.strip().lower()
    # keep newline boundaries but normalize them
    s2 = re.sub(r'\r\n?', '\n', s2)
    s2 = re.sub(r'\n\s+', '\n', s2)
    # remove punctuation except # and newline and alphanumerics and spaces
    s2 = re.sub(r'[^\w\s#\n]', '', s2)
    # collapse spaces
    s2 = re.sub(r'[ \t]+', ' ', s2)
    # collapse multiple newlines
    s2 = re.sub(r'\n+', '\n', s2)
    return s2.strip()

# ---------- MAIN ----------
def main():
    driver = webdriver.Chrome(options=chrome_options)
    try:
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass

        # Login
        driver.get("https://www.linkedin.com/login")
        time.sleep(1.0)
        driver.find_element(By.ID, "username").send_keys(username)
        driver.find_element(By.ID, "password").send_keys(password)
        driver.find_element(By.ID, "password").submit()
        time.sleep(3.0)

        # manual verification handling
        cur_url = driver.current_url.lower()
        cookies = driver.get_cookies()
        has_li_at = any(c.get('name') == 'li_at' for c in cookies)
        if ("/checkpoint" in cur_url) or ("/challenge" in cur_url) or (not has_li_at and "/login" in cur_url):
            ok = wait_for_manual_verification(driver, timeout=300)
            if not ok:
                print("Manual verification did not complete. Exiting.")
                return
        else:
            if not has_li_at:
                start = time.time()
                while time.time() - start < 10:
                    if any(c.get('name') == 'li_at' for c in driver.get_cookies()):
                        has_li_at = True
                        break
                    time.sleep(0.5)
                if not has_li_at:
                    print("li_at cookie not detected yet. If LinkedIn requires verification you can complete it now.")
                    if not wait_for_manual_verification(driver, timeout=120):
                        print("Manual verification did not happen. Proceeding but likely not logged-in; Voyager likely to fail.")

        # navigation & posts tab handling
        public_id = None
        m = re.search(r'linkedin\.com\/in\/([A-Za-z0-9\-\_]+)', page)
        if m:
            public_id = m.group(1)

        post_page = page.rstrip('/') + "/posts"
        print("Opening posts page:", post_page)
        driver.get(post_page)
        time.sleep(2.5)

        if "/feed/" in driver.current_url or not wait_until_posts_visible(driver, timeout=2):
            try:
                clicked = False
                candidates = driver.find_elements(By.XPATH,
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'all posts') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts & activity') ]")
                for c in candidates:
                    try:
                        href = c.get_attribute("href")
                        if href and ("/posts" in href or "recent-activity" in href):
                            try:
                                c.click()
                            except Exception:
                                driver.get(href)
                            time.sleep(2.0)
                            clicked = True
                            break
                        else:
                            try:
                                c.click()
                                time.sleep(2.0)
                                clicked = True
                                break
                            except Exception:
                                pass
                    except Exception:
                        continue
                if clicked:
                    print("Clicked Posts tab / link; waiting for posts to show...")
                    if not wait_until_posts_visible(driver, timeout=8):
                        print("Posts tab clicked but no posts visible yet.")
                else:
                    if public_id:
                        try_urls = [
                            f"https://www.linkedin.com/in/{public_id}/detail/recent-activity/",
                            f"https://www.linkedin.com/in/{public_id}/recent-activity/all/",
                            f"https://www.linkedin.com/company/{public_id}/posts"
                        ]
                        for u in try_urls:
                            try:
                                driver.get(u)
                                time.sleep(2.0)
                                if wait_until_posts_visible(driver, timeout=3):
                                    print("Reached posts via variant:", u)
                                    break
                            except Exception:
                                pass
                    if not wait_until_posts_visible(driver, timeout=1):
                        print("Could not automatically reach Posts. Please open the profile/company's Posts page in the Chrome window now.")
                        try:
                            input("When the Posts tab is visible in the browser, press Enter here to continue (or Ctrl+C to abort):\n")
                        except Exception:
                            pass
                        if not wait_until_posts_visible(driver, timeout=12):
                            print("Posts still not visible after manual attempt. Continuing — results may be empty.")
            except Exception as e:
                print("Error attempting to click Posts tab:", e)
                traceback.print_exc()

        # scrolling
        print("Starting scroll to load posts...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        scrolls = 0
        no_change_count = 0
        while True:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                no_change_count += 1
            else:
                no_change_count = 0
            last_height = new_height
            scrolls += 1
            print(f"Scrolled {scrolls}/{MAX_SCROLLS} (no-change: {no_change_count})")
            if no_change_count >= 3 or (MAX_SCROLLS and scrolls >= MAX_SCROLLS):
                break
        time.sleep(1.5)

        # ---------- Selenium-ordered extraction with dedupe ----------
        results = []
        seen_fingerprints = set()
        print("Collecting post elements (Selenium) in document order...")
        xpath_expr = ("//article | "
                      "//div[contains(@class,'feed-shared-update-v2') and @data-urn] | "
                      "//div[contains(@class,'occludable-update')] | "
                      "//div[contains(@class,'update-card')] | "
                      "//div[contains(@class,'ember-view') and @data-urn]")
        elements = driver.find_elements(By.XPATH, xpath_expr)
        print(f"Found {len(elements)} candidate elements. Inspecting each in order...")

        for idx, el in enumerate(elements, start=1):
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", el)
                time.sleep(0.4)

                # expand "see more"
                try:
                    see_more_buttons = el.find_elements(By.XPATH,
                        ".//button[contains(., 'See more') or contains(., 'see more') or contains(., '…more') or contains(., '… see more') or contains(., '...see more') or contains(., 'See More') or contains(., '…more')]")
                    for b in see_more_buttons:
                        try:
                            if b.is_displayed():
                                b.click()
                                time.sleep(0.25)
                        except Exception:
                            pass
                except Exception:
                    pass

                inner_html = el.get_attribute("innerHTML") or ""
                inner_text = el.get_attribute("innerText") or ""
                cont_soup = bs(inner_html, "html.parser")
                raw_text = get_post_text_from_container(cont_soup)
                if not raw_text or len(raw_text.strip()) < 3:
                    raw_text = inner_text.strip()
                if not raw_text or len(raw_text.strip()) < 3:
                    continue
                cleaned = clean_post_text(raw_text)

                # fingerprint for dedupe
                fp = fingerprint_text(cleaned)
                if not fp:
                    continue
                if fp in seen_fingerprints:
                    # duplicate — skip, preserve first occurrence order
                    # print(f"Skipping duplicate post at element #{idx}")
                    continue
                seen_fingerprints.add(fp)

                likes = extract_likes_from_container_soup(cont_soup)
                results.append({"text": cleaned, "engagement": int(likes)})
                print(f"Collected post #{len(results)} from element #{idx}")
            except Exception as e:
                print(f"Warning processing element #{idx}: {e}")
                continue

        if results:
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"Saved {len(results)} posts (DOM, selenium-ordered, deduped) to {out_path}")
            return

        # --- Voyager fallback with same dedupe logic ---
        print("DOM scraping yielded no results. Falling back to Voyager API using browser cookies...")

        sess = build_requests_session_from_selenium(driver)
        liat = sess.cookies.get("li_at") or sess.cookies.get("li_at", domain=".www.linkedin.com")
        jsess = sess.cookies.get("JSESSIONID") or sess.cookies.get("JSESSIONID", domain=".www.linkedin.com")
        if not liat:
            print("Warning: li_at cookie not found in Selenium cookies. Voyager may fail.")
        if not jsess:
            print("Warning: JSESSIONID cookie not found. Voyager needs CSRF (JSESSIONID) header.")
        csrf_token = jsess.strip('"') if jsess else ""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json, text/plain, */*",
            "X-Restli-Protocol-Version": "2.0.0",
            "csrf-token": csrf_token,
            "Referer": page.rstrip('/') + "/",
        }
        sess.headers.update(headers)

        if not public_id:
            og = bs(driver.page_source, "html.parser").find("meta", {"property": "og:url"})
            if og and og.get("content"):
                m2 = re.search(r'linkedin\.com\/in\/([A-Za-z0-9\-\_]+)', og.get("content"))
                if m2:
                    public_id = m2.group(1)

        if not public_id:
            print("No public id detected. Voyager requires profile public id (e.g. amardeep247). Cannot use Voyager fallback.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return

        profile_url = f"https://www.linkedin.com/voyager/api/identity/profiles/(publicIdentifier:{public_id})"
        print("Fetching profile metadata (Voyager):", profile_url)
        r = requests_get_with_retry(sess, profile_url, headers=headers, timeout=20, retries=3)
        if not r or r.status_code != 200:
            print("Voyager profile metadata failed or timed out.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        profile_json = r.json()
        profile_urn = find_first_key(profile_json, "entityUrn") or find_first_key(profile_json, "profileUrn") or profile_json.get("entityUrn")
        print("Resolved profile URN:", profile_urn)
        if not profile_urn:
            print("Could not find profile URN - aborting Voyager fallback.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return

        updates_url = "https://www.linkedin.com/voyager/api/identity/profileUpdatesV2"
        params = {"profileUrn": profile_urn, "count": 50, "q": "member"}
        print("Fetching updates via Voyager:", updates_url)
        r2 = requests_get_with_retry(sess, updates_url, headers=headers, params=params, timeout=30, retries=3)
        if not r2 or r2.status_code != 200:
            print("Voyager updates request failed or timed out.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return

        data = r2.json()
        containers = []
        if isinstance(data, dict):
            if "included" in data and isinstance(data["included"], list):
                containers.extend(data["included"])
            if "elements" in data and isinstance(data["elements"], list):
                containers.extend(data["elements"])
            containers.append(data)

        results = []
        seen_fingerprints = set()
        for c in containers:
            texts = extract_texts_from_json(c)
            if not texts:
                continue
            likes = extract_likes_from_json(c)
            for t in texts:
                txt = re.sub(r'\s+', ' ', t).strip()
                if not txt:
                    continue
                cleaned = clean_post_text(txt)
                fp = fingerprint_text(cleaned)
                if not fp:
                    continue
                if fp in seen_fingerprints:
                    continue
                seen_fingerprints.add(fp)
                results.append({"text": cleaned, "engagement": int(likes or 0)})

        out_path = Path(OUTPUT_JSON)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(results)} posts (Voyager, deduped) to {out_path}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
