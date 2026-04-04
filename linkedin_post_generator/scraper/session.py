"""Browser/session helpers for LinkedIn authentication and cookie reuse."""

from __future__ import annotations

import threading
import time

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium_stealth import stealth

from ..config import ScraperSettings
from .dom import wait_for_document_ready, wait_for_element


def build_chrome_options() -> Options:
    """Create Selenium Chrome options for the scraper."""

    options = Options()
    options.add_argument("--window-size=1280,900")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return options


def create_driver() -> webdriver.Chrome:
    """Create and configure a Selenium Chrome driver."""

    driver = webdriver.Chrome(options=build_chrome_options())
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def wait_for_login_transition(driver: object, timeout: int = 8) -> bool:
    """Wait for either a successful login cookie or a URL transition."""

    start = time.time()
    while time.time() - start < timeout:
        try:
            if any(cookie.get("name") == "li_at" for cookie in driver.get_cookies()):
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


def wait_for_manual_verification(driver: object, timeout: int = 300) -> bool:
    """Wait for manual checkpoint completion in the opened browser."""

    start = time.time()
    done_event = threading.Event()
    input_result = {"pressed": False}

    def wait_for_enter() -> None:
        try:
            input(
                "Press Enter here once you've completed the verification in the browser "
                "(or wait for cookie detection)...\n"
            )
            input_result["pressed"] = True
            done_event.set()
        except Exception:
            return

    threading.Thread(target=wait_for_enter, daemon=True).start()
    print("\nLinkedIn appears to require additional verification (checkpoint / 2FA).")
    print("Please complete the verification manually in the opened browser window.")
    print(
        "Either press Enter in this terminal after verification or the script will "
        "detect the session cookie and continue automatically."
    )
    print(f"Waiting up to {timeout} seconds for manual verification...\n")

    while True:
        try:
            cookies = driver.get_cookies()
        except Exception:
            cookies = []

        if any(cookie.get("name") == "li_at" for cookie in cookies):
            print("Login cookie (li_at) detected; continuing.")
            return True

        if done_event.is_set() and input_result.get("pressed"):
            print("Enter pressed but li_at cookie is not available yet. Waiting for the authenticated session.")
            done_event.clear()
            input_result["pressed"] = False
            threading.Thread(target=wait_for_enter, daemon=True).start()

        if time.time() - start > timeout:
            print("\nTimeout waiting for manual verification.")
            return False
        time.sleep(2)


def login_to_linkedin(driver: object, settings: ScraperSettings) -> bool:
    """Authenticate to LinkedIn using environment-backed credentials."""

    print("Attempting login...")
    driver.get("https://www.linkedin.com/login")
    wait_for_document_ready(driver, timeout=10)

    try:
        username_input = wait_for_element(driver, By.ID, "username", timeout=8)
        password_input = wait_for_element(driver, By.ID, "password", timeout=8)
        if not username_input or not password_input:
            raise NoSuchElementException("LinkedIn login form fields were not found.")
        username_input.send_keys(settings.username)
        password_input.send_keys(settings.password)
        password_input.submit()
        wait_for_login_transition(driver, timeout=8)
    except Exception as error:
        print(f"Error filling login form: {error}. Page might require manual intervention.")

    current_url = driver.current_url.lower()
    try:
        cookies = driver.get_cookies()
    except Exception:
        cookies = []

    has_li_at = any(cookie.get("name") == "li_at" for cookie in cookies)
    if "/checkpoint" in current_url or "/challenge" in current_url or (not has_li_at and "/login" in current_url):
        return wait_for_manual_verification(driver, timeout=300)

    if not has_li_at:
        print("Login submitted, waiting for 'li_at' cookie...")
        start = time.time()
        while time.time() - start < 10:
            if any(cookie.get("name") == "li_at" for cookie in driver.get_cookies()):
                print("'li_at' cookie found.")
                return True
            time.sleep(0.5)

        print("li_at cookie not detected. Assuming manual verification is needed.")
        return wait_for_manual_verification(driver, timeout=120)

    print("Login successful (li_at cookie detected immediately).")
    return True


def build_requests_session_from_selenium(driver: object, proxy: str | None = None) -> requests.Session:
    """Create a requests session that reuses Selenium cookies."""

    session = requests.Session()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})

    for cookie in driver.get_cookies():
        try:
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"))
        except Exception:
            session.cookies.set(cookie["name"], cookie["value"])
    return session
