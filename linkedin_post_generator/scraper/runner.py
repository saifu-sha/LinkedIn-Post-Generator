"""Top-level scraper orchestration and raw JSON persistence."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Any

from selenium.common.exceptions import WebDriverException

from ..config import get_scraper_settings
from ..models import PostRecord
from .dom import ensure_posts_page, extract_posts_from_dom, scroll_feed_for_posts
from .session import create_driver, login_to_linkedin
from .voyager import fetch_posts_from_voyager


def _write_output(posts: list[PostRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump([post.to_dict() for post in posts], file, ensure_ascii=False, indent=2)


def main(output_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Run the scraper and save raw posts to JSON."""

    settings = get_scraper_settings(output_path)
    missing_env_vars = settings.missing_required_env_vars()
    if missing_env_vars:
        print("Missing required .env values:", ", ".join(missing_env_vars))
        print("Set them in the project root .env file before running the scraper.")
        return []

    driver = create_driver()
    try:
        if not login_to_linkedin(driver, settings):
            print("Login could not be completed. Exiting.")
            return []

        post_candidates, public_id = ensure_posts_page(
            driver,
            settings.page_url or "",
            timeout=settings.post_load_timeout,
        )
        print(
            f"DOM readiness check found {len(post_candidates)} candidate post containers before scrolling."
        )
        scroll_feed_for_posts(
            driver,
            pause_time=settings.scroll_pause_time,
            max_scrolls=settings.max_scrolls,
        )

        posts = extract_posts_from_dom(driver)
        source = "DOM"
        if not posts:
            print("DOM scraping yielded no results. Falling back to Voyager API using browser cookies...")
            posts = fetch_posts_from_voyager(driver, settings.page_url or "", public_id=public_id)
            source = "Voyager"

        _write_output(posts, settings.output_path)
        print(f"Saved {len(posts)} posts ({source}, deduped) to {settings.output_path}")
        return [post.to_dict() for post in posts]
    except WebDriverException as error:
        print(f"A WebDriver error occurred: {error}")
        traceback.print_exc()
    except Exception as error:
        print(f"An unexpected error occurred: {error}")
        traceback.print_exc()
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return []
