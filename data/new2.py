# scrape_with_voyager_fallback_dedupe.py
# (Optimized for "Stealth Login" method)

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
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup as bs
from dotenv import load_dotenv

import requests
import threading

# Import stealth
from selenium_stealth import stealth

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


def get_missing_required_env_vars():
    missing = []
    if not username:
        missing.append("LINKEDIN_USERNAME")
    if not password:
        missing.append("LINKEDIN_PASSWORD")
    if not page:
        missing.append("LINKEDIN_PAGE")
    return missing


# ---------- CONFIG ----------
username = os.getenv("LINKEDIN_USERNAME")
password = os.getenv("LINKEDIN_PASSWORD")
page = os.getenv("LINKEDIN_PAGE")

# OUTPUT_JSON = "posts_likes_clean.json"
OUTPUT_JSON = r"C:\Users\saif\Desktop\Final Mini Project\data\raw_posts.json"
SCROLL_PAUSE_TIME = getenv_float("SCROLL_PAUSE_TIME", 0.8)
MAX_SCROLLS = getenv_int("MAX_SCROLLS", 3)
POST_LOAD_TIMEOUT = getenv_int("POST_LOAD_TIMEOUT", 7)
POST_CARD_XPATH = (
    "//article | "
    "//div[@data-urn] | "
    "//div[contains(@class,'feed-shared-update-v2')] | "
    "//div[contains(@class,'occludable-update')] | "
    "//div[contains(@class,'update-components-update-v2')] | "
    "//div[contains(@class,'fie-impression-container')]"
)
POST_TEXT_XPATH = (
    ".//*[contains(@class,'feed-shared-text') or "
    "contains(@class,'feed-shared-update-v2__description-wrapper') or "
    "contains(@class,'break-words') or "
    "contains(@class,'update-components-text') or "
    "@data-test-id='post-content']"
)
SEE_MORE_XPATH = (
    ".//button["
    "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'see more') or "
    "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'...more') or "
    "contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expand') or "
    "contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'see more') or "
    "contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'expand')"
    "]"
)

# ---------- Selenium options ----------
chrome_options = Options()

# ---
# !!! WE ARE NOT LOADING A PROFILE !!!
# The user-data-dir line has been REMOVED.
# ---

# We still want to look as human as possible
chrome_options.add_argument("--window-size=1280,900")
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)
# chrome_options.add_argument("--headless=new") # DO NOT USE HEADLESS, it will fail login

# (All helper functions like basic_clean, sentence_capitalize, etc. are unchanged)
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

def simple_normalize_hashtags(s):
    """Removes 'hashtag' and joins hashtags inline."""
    if not s:
        return s
    s = re.sub(r'(?i)hashtag', '', s)
    s = re.sub(r'[\n\s]+#\s*([A-Za-z0-9_]+)', r' #\1', s)
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip()

def clean_post_text(raw_text):
    """(Preserves lines) Apply cleaning pipeline to raw post text."""
    if raw_text is None:
        return ""
    
    # 1. Basic cleaning
    s = basic_clean(raw_text)
    
    # 2. Convert bullet/delimiters to newline
    s = re.sub(r'\s*[•·—–]\s*', '\n', s)
    
    # 3. Strip each line and drop empty lines
    #    This preserves all the \n from our new get_post_text
    lines = [ln.strip() for ln in s.split('\n')]
    s = '\n'.join([ln for ln in lines if ln]) # 'if ln' drops empty lines
    
    # 4. Sentence capitalization
    s = sentence_capitalize(s)
    
    # 5. Normalize hashtags
    s = simple_normalize_hashtags(s)
    
    # 6. Final tidy-up
    s = re.sub(r'[ \t]+$', '', s, flags=re.MULTILINE)
    s = re.sub(r'\n{3,}', '\n\n', s) # Collapse excess newlines
    
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


def normalize_inline_text(text):
    return re.sub(r'\s+', ' ', (text or '')).strip()


def extract_public_identifier(page_url):
    m = re.search(r'linkedin\.com\/(?:in|company|school)\/([A-Za-z0-9\-\_]+)', page_url)
    return m.group(1) if m else None


def wait_for_document_ready(driver, timeout=10):
    try:
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        return True
    except TimeoutException:
        return False


def wait_for_element(driver, by, value, timeout=10):
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.3).until(
            lambda d: d.find_element(by, value)
        )
    except Exception:
        return None


def wait_for_login_transition(driver, timeout=8):
    start = time.time()
    while time.time() - start < timeout:
        try:
            if any(c.get('name') == 'li_at' for c in driver.get_cookies()):
                return True
        except Exception:
            pass
        try:
            if "/login" not in driver.current_url.lower():
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def count_raw_post_candidates(driver):
    try:
        return len(driver.find_elements(By.XPATH, POST_CARD_XPATH))
    except Exception:
        return 0


def get_text_block_elements(container):
    try:
        blocks = container.find_elements(By.XPATH, POST_TEXT_XPATH)
    except StaleElementReferenceException:
        return []

    valid_blocks = []
    for block in blocks:
        try:
            text = normalize_inline_text(block.get_attribute("innerText") or block.text)
        except StaleElementReferenceException:
            continue
        if text:
            valid_blocks.append(block)
    return valid_blocks


def is_likely_post_candidate(container):
    try:
        tag_name = (container.tag_name or "").lower()
        classes = container.get_attribute("class") or ""
        data_urn = container.get_attribute("data-urn") or ""
        text_blocks = get_text_block_elements(container)
        if text_blocks:
            return True

        text = normalize_inline_text(container.get_attribute("innerText") or container.text)
        marker_found = any(
            marker in classes
            for marker in (
                "feed-shared",
                "occludable-update",
                "update-components",
                "main-feed-activity-card",
                "fie-impression-container",
            )
        )
        return bool(text) and len(text) >= 20 and (tag_name == "article" or bool(data_urn) or marker_found)
    except StaleElementReferenceException:
        return False


def find_post_candidate_elements(driver):
    raw_candidates = driver.find_elements(By.XPATH, POST_CARD_XPATH)
    filtered_candidates = []
    seen_ids = set()
    for candidate in raw_candidates:
        try:
            if candidate.id in seen_ids:
                continue
            if not is_likely_post_candidate(candidate):
                continue
            seen_ids.add(candidate.id)
            filtered_candidates.append(candidate)
        except StaleElementReferenceException:
            continue
    return filtered_candidates


def wait_for_post_candidates(driver, timeout=POST_LOAD_TIMEOUT):
    try:
        WebDriverWait(driver, timeout, poll_frequency=1.0).until(
            lambda d: count_raw_post_candidates(d) > 0
        )
    except TimeoutException:
        return []
    end_time = time.time() + 2.0
    candidates = find_post_candidate_elements(driver)
    while not candidates and time.time() < end_time:
        time.sleep(0.25)
        candidates = find_post_candidate_elements(driver)
    return candidates


def expand_see_more_buttons(driver, container):
    try:
        buttons = container.find_elements(By.XPATH, SEE_MORE_XPATH)
    except StaleElementReferenceException:
        return

    for button in buttons:
        try:
            if not button.is_displayed():
                continue
            try:
                driver.execute_script("arguments[0].click();", button)
            except Exception:
                button.click()
            time.sleep(0.1)
        except Exception:
            continue


def scroll_feed_for_posts(driver):
    print("Starting scroll to load posts...")
    try:
        last_height = driver.execute_script("return document.body.scrollHeight")
    except Exception:
        last_height = 0
    last_candidate_count = len(find_post_candidate_elements(driver))
    scrolls = 0
    no_change_count = 0

    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(SCROLL_PAUSE_TIME)
        try:
            new_height = driver.execute_script("return document.body.scrollHeight")
        except Exception:
            new_height = last_height
        current_candidate_count = len(find_post_candidate_elements(driver))
        if new_height == last_height and current_candidate_count == last_candidate_count:
            no_change_count += 1
        else:
            no_change_count = 0
        last_height = new_height
        last_candidate_count = current_candidate_count
        scrolls += 1
        print(f"Scrolled {scrolls}/{MAX_SCROLLS} (candidates: {current_candidate_count}, no-change: {no_change_count})")
        if no_change_count >= 2 or (MAX_SCROLLS and scrolls >= MAX_SCROLLS):
            break

    time.sleep(1.0)


def response_preview(response, limit=240):
    if response is None:
        return "no response received"
    try:
        snippet = normalize_inline_text(response.text)
    except Exception:
        snippet = ""
    if not snippet:
        return "empty response body"
    if len(snippet) > limit:
        return snippet[:limit] + "..."
    return snippet


def extract_likes_from_text_blob(text_blob):
    text_blob = normalize_inline_text(text_blob)
    if not text_blob:
        return 0
    m = re.search(r'(\d+(?:[.,]\d+)?\s*[KMkm]?)\s*(?:reactions|reaction|likes|like|react)\b', text_blob, flags=re.IGNORECASE)
    if m:
        return convert_abbreviated_to_number(m.group(1))
    all_nums = re.findall(r'(\d+(?:[.,]\d+)?\s*[KMkm]?)', text_blob)
    candidates = [convert_abbreviated_to_number(x) for x in all_nums]
    return max(candidates) if candidates else 0

# ---------- DOM helpers ----------
def get_post_text_from_container(container_soup):
    
    # --- NEW PRE-PROCESSING ---
    # 1. Neutralize mentions (<a> tags) by replacing them with their text.
    #    This stops get_text() from adding newlines for them.
    for a in container_soup.find_all("a"):
        try:
            if a.text:
                a.replace_with(a.text + " ") # Add a space for safety
            else:
                a.decompose()
        except Exception:
            pass # Handle any errors during replacement

    # 2. Explicitly replace <br> tags with a newline character
    for br in container_soup.find_all("br"):
        br.replace_with("\n")
    # --- END PRE-PROCESSING ---

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
        
        if el:
            # Now get_text() will respect our newlines and not add mention-newlines
            text = el.get_text("\n", strip=True)
            if text:
                return text

    # Fallback
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
        # Check for the login cookie 'li_at'
        if any(c.get('name') == 'li_at' for c in cookies):
            print("Login cookie (li_at) detected — continuing.")
            done_event.set()
            return True
        
        # Check if user pressed Enter
        if done_event.is_set() and input_result.get("pressed"):
            try:
                cookies = driver.get_cookies()
            except Exception:
                cookies = []
            if any(c.get('name') == 'li_at' for c in cookies):
                print("li_at cookie detected after manual confirmation — continuing.")
                return True
            else:
                # User pressed Enter but cookie is still not found
                print("Enter pressed but li_at cookie not found yet. If verification is incomplete, finish it in the browser then press Enter again.")
                done_event.clear() # Reset event
                input_result["pressed"] = False
                t = threading.Thread(target=wait_for_enter, daemon=True) # Start a new thread
                t.start()
                
        if time.time() - start > timeout:
            print("\nTimeout waiting for manual verification.")
            return False
        time.sleep(2)

# ---------- Utility: wait until profile/posts content appears ----------
def wait_until_posts_visible(driver, timeout=20):
    wait_for_document_ready(driver, timeout=min(timeout, 10))
    candidates = wait_for_post_candidates(driver, timeout=timeout)
    return bool(candidates)

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
    s2 = s.strip().lower()
    s2 = re.sub(r'\r\n?', '\n', s2)
    s2 = re.sub(r'\n\s+', '\n', s2)
    s2 = re.sub(r'[^\w\s#\n]', '', s2)
    s2 = re.sub(r'[ \t]+', ' ', s2)
    s2 = re.sub(r'\n+', '\n', s2)
    return s2.strip()

# ---------- MAIN ----------
def main():
    missing_env_vars = get_missing_required_env_vars()
    if missing_env_vars:
        print("Missing required .env values:", ", ".join(missing_env_vars))
        print("Set them in the project root .env file before running the scraper.")
        return

    # This will create a NEW browser instance
    driver = webdriver.Chrome(options=chrome_options) 
    
    # --- ADDING STEALTH ---
    # This patches the driver to look more human
    stealth(driver,
          languages=["en-US", "en"],
          vendor="Google Inc.",
          platform="Win32",
          webgl_vendor="Intel Inc.",
          renderer="Intel Iris OpenGL Engine",
          fix_hairline=True,
          )
    
    try:
        # ---
        # !!! LOGIN BLOCK IS NOW ACTIVE !!!
        # We will attempt to log in automatically.
        # ---
        print("Attempting login...")
        driver.get("https://www.linkedin.com/login")
        wait_for_document_ready(driver, timeout=10)
        
        try:
            username_input = wait_for_element(driver, By.ID, "username", timeout=8)
            password_input = wait_for_element(driver, By.ID, "password", timeout=8)
            if not username_input or not password_input:
                raise NoSuchElementException("LinkedIn login form fields were not found.")
            username_input.send_keys(username)
            password_input.send_keys(password)
            password_input.submit()
            wait_for_login_transition(driver, timeout=8)
        except Exception as e:
            print(f"Error filling login form: {e}. Page might be different.")
            # This can happen if already on a checkpoint page
            
        # manual verification handling
        cur_url = driver.current_url.lower()
        try:
            cookies = driver.get_cookies()
        except Exception:
            cookies = []
            
        has_li_at = any(c.get('name') == 'li_at' for c in cookies)
        
        # Check if we are on a checkpoint page OR if we failed login and are still on /login
        if ("/checkpoint" in cur_url) or ("/challenge" in cur_url) or (not has_li_at and "/login" in cur_url):
            # This is where you will do the manual step
            ok = wait_for_manual_verification(driver, timeout=300)
            if not ok:
                print("Manual verification did not complete. Exiting.")
                return
        elif not has_li_at:
            # We're not on a checkpoint, but we also don't have the cookie.
            # Wait a few seconds to see if it appears (e.g., during a redirect)
            print("Login submitted, waiting for 'li_at' cookie...")
            start = time.time()
            while time.time() - start < 10:
                if any(c.get('name') == 'li_at' for c in driver.get_cookies()):
                    has_li_at = True
                    print("'li_at' cookie found.")
                    break
                time.sleep(0.5)
            
            if not has_li_at:
                print("li_at cookie not detected. Assuming manual verification is needed.")
                if not wait_for_manual_verification(driver, timeout=120):
                    print("Manual verification did not happen. Proceeding but likely to fail.")
        else:
            print("Login successful (li_at cookie detected immediately).")

        # ---
        # !!! END OF LOGIN BLOCK !!!
        # ---

        # navigation & posts tab handling
        public_id = extract_public_identifier(page)

        post_page = page.rstrip('/') + "/posts"
        print(f"Opening posts page: {post_page}")
        driver.get(post_page)
        wait_for_document_ready(driver, timeout=10)
        post_candidates = wait_for_post_candidates(driver, timeout=POST_LOAD_TIMEOUT)
        
        # (The rest of the script is identical to the last version)
        # Check if we landed on the feed or if posts aren't visible
        if "/feed/" in driver.current_url or not post_candidates:
            print("No real post cards detected on the direct posts URL. Attempting alternate navigation...")
            try:
                clicked = False
                nav_candidates = driver.find_elements(By.XPATH,
                    "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'all posts') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts & activity') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'activity')] | "
                    "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts') or "
                    "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'activity')]")
                
                for c in nav_candidates:
                    try:
                        href = c.get_attribute("href")
                        if href and ("/posts" in href or "recent-activity" in href):
                            print(f"Found explicit posts link: {href}")
                            try:
                                c.click()
                            except Exception:
                                driver.get(href)
                            wait_for_document_ready(driver, timeout=10)
                            clicked = True
                            break
                        elif "post" in c.text.lower() or "activity" in c.text.lower():
                             print(f"Found generic posts/activity button or link: {c.text}")
                             try:
                                 c.click()
                                 wait_for_document_ready(driver, timeout=10)
                                 clicked = True
                                 break
                             except Exception:
                                 continue
                    except Exception:
                        continue
                        
                if clicked:
                    print("Clicked a posts/activity entry. Waiting for real post cards...")
                    post_candidates = wait_for_post_candidates(driver, timeout=POST_LOAD_TIMEOUT)
                    if not post_candidates:
                        print("Posts/activity navigation succeeded, but no post cards were detected yet.")
                if not post_candidates:
                    print("Could not find or click a posts/activity control. Trying direct activity URLs...")
                    if public_id:
                        try_urls = [
                            f"https://www.linkedin.com/in/{public_id}/detail/recent-activity/",
                            f"https://www.linkedin.com/in/{public_id}/recent-activity/all/",
                            f"https://www.linkedin.com/company/{public_id}/posts"
                        ]
                        post_candidates = []
                        for u in try_urls:
                            try:
                                print(f"Trying direct URL: {u}")
                                driver.get(u)
                                wait_for_document_ready(driver, timeout=10)
                                post_candidates = wait_for_post_candidates(driver, timeout=POST_LOAD_TIMEOUT)
                                if post_candidates:
                                    print("Reached posts via variant:", u)
                                    break
                            except Exception:
                                pass
                        if not post_candidates:
                            print("Direct URL navigation failed to load posts.")
                    
                    if not post_candidates:
                        print("Could not automatically reach Posts. Please open the profile's 'Posts' page in the Chrome window now.")
                        try:
                            input("When the Posts tab is visible in the browser, press Enter here to continue (or Ctrl+C to abort):\n")
                        except Exception:
                            pass
                        post_candidates = wait_for_post_candidates(driver, timeout=12)
                        if not post_candidates:
                            print("Posts still not visible after manual attempt. Continuing — results may be empty.")
            except Exception as e:
                print(f"Error attempting to click Posts tab: {e}")
                traceback.print_exc()

        print(f"DOM readiness check found {len(post_candidates)} candidate post containers before scrolling.")
        scroll_feed_for_posts(driver)

        # ---------- Selenium-ordered extraction with dedupe ----------
        results = []
        seen_fingerprints = set()
        print("Collecting post elements (Selenium) in document order...")
        elements = find_post_candidate_elements(driver)
        print(f"Found {len(elements)} candidate elements. Inspecting each in order...")

        for idx, el in enumerate(elements, start=1):
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", el)
                time.sleep(0.2)
                expand_see_more_buttons(driver, el)
                if False:
                    see_more_buttons = el.find_elements(By.XPATH,
                        ".//button[contains(., 'See more') or contains(., 'see more') or contains(., '…more') or contains(., '… see more') or contains(., '...see more') or contains(., 'See More') or contains(., '…more')]")
                    for b in see_more_buttons:
                        try:
                            if b.is_displayed():
                                b.click()
                                time.sleep(0.25)
                        except Exception:
                            pass
                inner_text = el.get_attribute("innerText") or ""
                if not inner_text:
                    continue
                raw_text = ""
                likes = extract_likes_from_text_blob(inner_text)
                for block in get_text_block_elements(el):
                    try:
                        block_text = block.get_attribute("innerText") or block.text
                    except StaleElementReferenceException:
                        continue
                    if normalize_inline_text(block_text):
                        raw_text = block_text
                        break
                if not raw_text or len(raw_text.strip()) < 3:
                    raw_text = inner_text.strip()
                if not raw_text or len(raw_text.strip()) < 3:
                    continue
                if likes == 0 or raw_text == inner_text.strip():
                    inner_html = el.get_attribute("innerHTML") or ""
                    if inner_html:
                        cont_soup = bs(inner_html, "html.parser")
                        if raw_text == inner_text.strip():
                            soup_text = get_post_text_from_container(cont_soup)
                            if soup_text:
                                raw_text = soup_text
                        if likes == 0:
                            likes = extract_likes_from_container_soup(cont_soup)
                cleaned = clean_post_text(raw_text)
                fp = fingerprint_text(cleaned)
                if not fp:
                    continue
                if fp in seen_fingerprints:
                    continue
                seen_fingerprints.add(fp)
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
            print("CRITICAL: li_at cookie not found. Voyager will fail. Login was unsuccessful.")
            return
        if not jsess:
            print("Warning: JSESSIONID cookie not found. Voyager needs CSRF (JSESSIONID) header.")
        
        csrf_token = jsess.strip('"') if jsess else ""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "X-Restli-Protocol-Version": "2.0.0",
            "csrf-token": csrf_token,
            "Referer": page.rstrip('/') + "/",
        }
        sess.headers.update(headers)
        if not public_id:
            og = bs(driver.page_source, "html.parser").find("meta", {"property": "og:url"})
            if og and og.get("content"):
                public_id = extract_public_identifier(og.get("content"))
        if not public_id:
            print("No public id detected. Voyager requires profile public id. Cannot use Voyager fallback.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        profile_url = f"https://www.linkedin.com/voyager/api/identity/profiles/(publicIdentifier:{public_id})"
        print("Fetching profile metadata (Voyager):", profile_url)
        r = requests_get_with_retry(sess, profile_url, headers=headers, timeout=20, retries=3)
        if not r:
            print("Voyager profile metadata request timed out after retries.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        if r.status_code != 200:
            print(f"Voyager profile metadata failed with HTTP {r.status_code} at {r.url}. Body preview: {response_preview(r)}")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        try:
            profile_json = r.json()
        except json.JSONDecodeError:
            print("Voyager profile response was not valid JSON.")
            return
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
        if not r2:
            print("Voyager updates request timed out after retries.")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        if r2.status_code != 200:
            print(f"Voyager updates request failed with HTTP {r2.status_code} at {r2.url}. Body preview: {response_preview(r2)}")
            out_path = Path(OUTPUT_JSON)
            with out_path.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            return
        try:
            data = r2.json()
        except json.JSONDecodeError:
            print("Voyager updates response was not valid JSON.")
            return
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

    except WebDriverException as e:
        print(f"A WebDriver error occurred: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        traceback.print_exc()
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    main()
