"""Voyager API fallback used when DOM scraping yields no results."""

from __future__ import annotations

import json
import time
from collections import deque

import requests
from bs4 import BeautifulSoup

from ..models import PostRecord
from .cleaning import clean_post_text, extract_number_from_text, fingerprint_text, response_preview
from .dom import extract_public_identifier
from .session import build_requests_session_from_selenium


def requests_get_with_retry(
    session: requests.Session,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, object] | None = None,
    timeout: int = 20,
    retries: int = 3,
) -> requests.Response | None:
    """Perform a GET request with retry/backoff for transient failures."""

    attempt = 0
    while attempt < retries:
        try:
            return session.get(url, headers=headers, params=params, timeout=timeout)
        except requests.exceptions.RequestException as error:
            attempt += 1
            backoff = 1.5**attempt
            print(
                f"Requests error on attempt {attempt}/{retries}: {error}. "
                f"Retrying in {backoff:.1f}s..."
            )
            time.sleep(backoff)
    return None


def find_first_key(payload: object, key: str) -> object | None:
    """Traverse nested JSON until a matching key is found."""

    queue = deque([payload])
    while queue:
        current = queue.popleft()
        if isinstance(current, dict):
            if key in current:
                return current[key]
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for item in current:
                if isinstance(item, (dict, list)):
                    queue.append(item)
    return None


def extract_texts_from_json(payload: object) -> list[str]:
    """Collect text fields that may contain post bodies."""

    texts: list[str] = []
    queue = deque([payload])
    while queue:
        current = queue.popleft()
        if isinstance(current, dict):
            commentary = current.get("commentary")
            if isinstance(commentary, dict):
                text = commentary.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text)
            text = current.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for value in current:
                if isinstance(value, (dict, list)):
                    queue.append(value)
    return texts


def extract_likes_from_json(payload: object) -> int:
    """Find the most likely reaction count in a Voyager payload."""

    candidates: list[int] = []
    queue = deque([payload])
    while queue:
        current = queue.popleft()
        if isinstance(current, dict):
            if "totalSocialActivityCount" in current:
                candidates.append(extract_number_from_text(str(current["totalSocialActivityCount"])))
            if "totalSocialActivityCounts" in current and isinstance(current["totalSocialActivityCounts"], dict):
                count = current["totalSocialActivityCounts"].get("count")
                candidates.append(extract_number_from_text(str(count)))
            if "socialDetail" in current and isinstance(current["socialDetail"], dict):
                detail = current["socialDetail"].get("totalSocialActivityCounts", {})
                if isinstance(detail, dict):
                    candidates.append(extract_number_from_text(str(detail.get("count"))))
            for value in current.values():
                if isinstance(value, (dict, list)):
                    queue.append(value)
        elif isinstance(current, list):
            for value in current:
                if isinstance(value, (dict, list)):
                    queue.append(value)

    return max(candidates, default=0)


def fetch_posts_from_voyager(
    driver: object,
    page_url: str,
    *,
    public_id: str | None = None,
) -> list[PostRecord]:
    """Fetch posts using Voyager APIs with Selenium cookies."""

    session = build_requests_session_from_selenium(driver)
    li_at = session.cookies.get("li_at") or session.cookies.get("li_at", domain=".www.linkedin.com")
    jsession_id = session.cookies.get("JSESSIONID") or session.cookies.get(
        "JSESSIONID",
        domain=".www.linkedin.com",
    )
    if not li_at:
        print("CRITICAL: li_at cookie not found. Voyager will fail. Login was unsuccessful.")
        return []
    if not jsession_id:
        print("Warning: JSESSIONID cookie not found. Voyager needs CSRF (JSESSIONID) header.")

    csrf_token = jsession_id.strip('"') if jsession_id else ""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "X-Restli-Protocol-Version": "2.0.0",
        "csrf-token": csrf_token,
        "Referer": page_url.rstrip("/") + "/",
    }
    session.headers.update(headers)

    resolved_public_id = public_id or extract_public_identifier(page_url)
    if not resolved_public_id:
        og_tag = BeautifulSoup(driver.page_source, "html.parser").find("meta", {"property": "og:url"})
        if og_tag and og_tag.get("content"):
            resolved_public_id = extract_public_identifier(str(og_tag.get("content")))
    if not resolved_public_id:
        print("No public id detected. Voyager fallback cannot proceed.")
        return []

    profile_url = (
        "https://www.linkedin.com/voyager/api/identity/profiles/"
        f"(publicIdentifier:{resolved_public_id})"
    )
    print(f"Fetching profile metadata (Voyager): {profile_url}")
    profile_response = requests_get_with_retry(session, profile_url, headers=headers, timeout=20, retries=3)
    if not profile_response:
        print("Voyager profile metadata request timed out after retries.")
        return []
    if profile_response.status_code != 200:
        print(
            f"Voyager profile metadata failed with HTTP {profile_response.status_code} "
            f"at {profile_response.url}. Body preview: {response_preview(profile_response)}"
        )
        return []

    try:
        profile_json = profile_response.json()
    except json.JSONDecodeError:
        print("Voyager profile response was not valid JSON.")
        return []

    profile_urn = (
        find_first_key(profile_json, "entityUrn")
        or find_first_key(profile_json, "profileUrn")
        or profile_json.get("entityUrn")
    )
    if not profile_urn:
        print("Could not find profile URN; aborting Voyager fallback.")
        return []

    updates_url = "https://www.linkedin.com/voyager/api/identity/profileUpdatesV2"
    params = {"profileUrn": profile_urn, "count": 50, "q": "member"}
    print(f"Fetching updates via Voyager: {updates_url}")
    updates_response = requests_get_with_retry(
        session,
        updates_url,
        headers=headers,
        params=params,
        timeout=30,
        retries=3,
    )
    if not updates_response:
        print("Voyager updates request timed out after retries.")
        return []
    if updates_response.status_code != 200:
        print(
            f"Voyager updates request failed with HTTP {updates_response.status_code} "
            f"at {updates_response.url}. Body preview: {response_preview(updates_response)}"
        )
        return []

    try:
        data = updates_response.json()
    except json.JSONDecodeError:
        print("Voyager updates response was not valid JSON.")
        return []

    containers: list[object] = []
    if isinstance(data, dict):
        if isinstance(data.get("included"), list):
            containers.extend(data["included"])
        if isinstance(data.get("elements"), list):
            containers.extend(data["elements"])
        containers.append(data)

    results: list[PostRecord] = []
    seen_fingerprints: set[str] = set()
    for container in containers:
        texts = extract_texts_from_json(container)
        if not texts:
            continue
        likes = extract_likes_from_json(container)
        for text in texts:
            cleaned = clean_post_text(text)
            fingerprint = fingerprint_text(cleaned)
            if not fingerprint or fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            results.append(PostRecord(text=cleaned, engagement=int(likes or 0)))
    return results
