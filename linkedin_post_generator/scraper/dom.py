"""DOM navigation and Selenium-based post extraction helpers."""

from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..models import PostRecord
from .cleaning import (
    clean_post_text,
    extract_likes_from_text_blob,
    extract_number_from_text,
    fingerprint_text,
    normalize_inline_text,
)

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


def extract_public_identifier(page_url: str | None) -> str | None:
    """Extract the public LinkedIn identifier from a profile or company URL."""

    if not page_url:
        return None
    match = re.search(r"linkedin\.com\/(?:in|company|school)\/([A-Za-z0-9\-_]+)", page_url)
    return match.group(1) if match else None


def wait_for_document_ready(driver: object, timeout: int = 10) -> bool:
    """Wait until the browser reports a fully loaded document."""

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.5).until(
            lambda browser: browser.execute_script("return document.readyState") == "complete"
        )
        return True
    except TimeoutException:
        return False


def wait_for_element(driver: object, by: str, value: str, timeout: int = 10) -> object | None:
    """Wait for a single element to become available."""

    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.3).until(
            lambda browser: browser.find_element(by, value)
        )
    except Exception:
        return None


def count_raw_post_candidates(driver: object) -> int:
    """Return the number of potential post containers on the page."""

    try:
        return len(driver.find_elements(By.XPATH, POST_CARD_XPATH))
    except Exception:
        return 0


def get_text_block_elements(container: object) -> list[object]:
    """Return non-empty text-bearing elements inside a post container."""

    try:
        blocks = container.find_elements(By.XPATH, POST_TEXT_XPATH)
    except StaleElementReferenceException:
        return []

    valid_blocks: list[object] = []
    for block in blocks:
        try:
            text = normalize_inline_text(block.get_attribute("innerText") or block.text)
        except StaleElementReferenceException:
            continue
        if text:
            valid_blocks.append(block)
    return valid_blocks


def is_likely_post_candidate(container: object) -> bool:
    """Heuristically decide whether an element looks like a post card."""

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


def find_post_candidate_elements(driver: object) -> list[object]:
    """Find post containers in document order and remove duplicates."""

    raw_candidates = driver.find_elements(By.XPATH, POST_CARD_XPATH)
    filtered_candidates: list[object] = []
    seen_ids: set[str] = set()
    for candidate in raw_candidates:
        try:
            if candidate.id in seen_ids or not is_likely_post_candidate(candidate):
                continue
            seen_ids.add(candidate.id)
            filtered_candidates.append(candidate)
        except StaleElementReferenceException:
            continue
    return filtered_candidates


def wait_for_post_candidates(driver: object, timeout: int) -> list[object]:
    """Wait until post candidates appear on the current page."""

    try:
        WebDriverWait(driver, timeout, poll_frequency=1.0).until(
            lambda browser: count_raw_post_candidates(browser) > 0
        )
    except TimeoutException:
        return []

    end_time = time.time() + 2.0
    candidates = find_post_candidate_elements(driver)
    while not candidates and time.time() < end_time:
        time.sleep(0.25)
        candidates = find_post_candidate_elements(driver)
    return candidates


def expand_see_more_buttons(driver: object, container: object) -> None:
    """Expand collapsed post content within a container."""

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


def scroll_feed_for_posts(driver: object, *, pause_time: float, max_scrolls: int) -> None:
    """Scroll the feed to load additional posts."""

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
        time.sleep(pause_time)
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
        print(
            f"Scrolled {scrolls}/{max_scrolls} "
            f"(candidates: {current_candidate_count}, no-change: {no_change_count})"
        )

        if no_change_count >= 2 or (max_scrolls and scrolls >= max_scrolls):
            break

    time.sleep(1.0)


def get_post_text_from_container(container_soup: BeautifulSoup) -> str:
    """Extract post text from parsed container HTML."""

    for anchor in container_soup.find_all("a"):
        try:
            if anchor.text:
                anchor.replace_with(anchor.text + " ")
            else:
                anchor.decompose()
        except Exception:
            continue

    for line_break in container_soup.find_all("br"):
        line_break.replace_with("\n")

    selectors = [
        ("div", {"class": re.compile(r"feed-shared-update-v2__description-wrapper")}),
        ("div", {"class": re.compile(r"feed-shared-text")}),
        ("span", {"class": re.compile(r"break-words")}),
        ("div", {"data-test-id": "post-content"}),
        ("p", {}),
    ]

    for tag, attrs in selectors:
        element = container_soup.find(tag, attrs=attrs) if attrs else container_soup.find(tag)
        if element:
            text = element.get_text("\n", strip=True)
            if text:
                return text

    text = container_soup.get_text("\n", strip=True)
    return text if text and len(text) > 3 else ""


def extract_likes_from_container_soup(container_soup: BeautifulSoup) -> int:
    """Extract reaction counts from parsed container HTML."""

    max_candidate = 0
    for button in container_soup.find_all("button"):
        aria_label = (button.get("aria-label") or "").lower()
        text = button.get_text(" ", strip=True)
        combined = f"{aria_label} {text}".strip()
        if any(keyword in aria_label for keyword in ("reaction", "like", "react")):
            value = extract_number_from_text(combined)
            if value:
                return value
        value = extract_number_from_text(combined)
        if value > max_candidate:
            max_candidate = value

    text_blob = container_soup.get_text(" ", strip=True)
    if max_candidate:
        return max_candidate
    return extract_likes_from_text_blob(text_blob)


def ensure_posts_page(driver: object, page_url: str, *, timeout: int) -> tuple[list[object], str | None]:
    """Navigate to a profile's posts page and return the loaded candidates."""

    public_id = extract_public_identifier(page_url)
    post_page = page_url.rstrip("/") + "/posts"
    print(f"Opening posts page: {post_page}")
    driver.get(post_page)
    wait_for_document_ready(driver, timeout=10)
    post_candidates = wait_for_post_candidates(driver, timeout=timeout)

    if "/feed/" in driver.current_url or post_candidates:
        return post_candidates, public_id

    print("No real post cards detected on the direct posts URL. Attempting alternate navigation...")
    try:
        clicked = False
        nav_candidates = driver.find_elements(
            By.XPATH,
            "//a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'all posts') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts & activity') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'activity')] | "
            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'posts') or "
            "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'activity')]",
        )

        for candidate in nav_candidates:
            try:
                href = candidate.get_attribute("href")
                if href and ("/posts" in href or "recent-activity" in href):
                    print(f"Found explicit posts link: {href}")
                    try:
                        candidate.click()
                    except Exception:
                        driver.get(href)
                    wait_for_document_ready(driver, timeout=10)
                    clicked = True
                    break
                if "post" in candidate.text.lower() or "activity" in candidate.text.lower():
                    print(f"Found generic posts/activity button or link: {candidate.text}")
                    try:
                        candidate.click()
                        wait_for_document_ready(driver, timeout=10)
                        clicked = True
                        break
                    except Exception:
                        continue
            except Exception:
                continue

        if clicked:
            print("Clicked a posts/activity entry. Waiting for real post cards...")
            post_candidates = wait_for_post_candidates(driver, timeout=timeout)
            if post_candidates:
                return post_candidates, public_id

        if public_id:
            try_urls = [
                f"https://www.linkedin.com/in/{public_id}/detail/recent-activity/",
                f"https://www.linkedin.com/in/{public_id}/recent-activity/all/",
                f"https://www.linkedin.com/company/{public_id}/posts",
            ]
            for url in try_urls:
                try:
                    print(f"Trying direct URL: {url}")
                    driver.get(url)
                    wait_for_document_ready(driver, timeout=10)
                    post_candidates = wait_for_post_candidates(driver, timeout=timeout)
                    if post_candidates:
                        print(f"Reached posts via variant: {url}")
                        return post_candidates, public_id
                except Exception:
                    continue

        print("Could not automatically reach Posts. Please open the profile's 'Posts' page in the browser.")
        try:
            input("When the Posts tab is visible in the browser, press Enter here to continue:\n")
        except Exception:
            pass
        post_candidates = wait_for_post_candidates(driver, timeout=12)
        if not post_candidates:
            print("Posts still not visible after manual attempt. Continuing; results may be empty.")
    except Exception as error:
        print(f"Error attempting to click Posts tab: {error}")

    return post_candidates, public_id


def extract_posts_from_dom(driver: object) -> list[PostRecord]:
    """Extract and deduplicate posts from the current DOM."""

    results: list[PostRecord] = []
    seen_fingerprints: set[str] = set()
    print("Collecting post elements (Selenium) in document order...")
    elements = find_post_candidate_elements(driver)
    print(f"Found {len(elements)} candidate elements. Inspecting each in order...")

    for index, element in enumerate(elements, start=1):
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior:'auto', block:'center'});", element)
            time.sleep(0.2)
            expand_see_more_buttons(driver, element)

            inner_text = element.get_attribute("innerText") or ""
            if not inner_text:
                continue

            raw_text = ""
            likes = extract_likes_from_text_blob(inner_text)
            for block in get_text_block_elements(element):
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
                inner_html = element.get_attribute("innerHTML") or ""
                if inner_html:
                    container_soup = BeautifulSoup(inner_html, "html.parser")
                    if raw_text == inner_text.strip():
                        soup_text = get_post_text_from_container(container_soup)
                        if soup_text:
                            raw_text = soup_text
                    if likes == 0:
                        likes = extract_likes_from_container_soup(container_soup)

            cleaned = clean_post_text(raw_text)
            fingerprint = fingerprint_text(cleaned)
            if not fingerprint or fingerprint in seen_fingerprints:
                continue

            seen_fingerprints.add(fingerprint)
            results.append(PostRecord(text=cleaned, engagement=int(likes)))
            print(f"Collected post #{len(results)} from element #{index}")
        except Exception as error:
            print(f"Warning processing element #{index}: {error}")
            continue

    return results
