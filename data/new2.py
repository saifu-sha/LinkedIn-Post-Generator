"""Compatibility wrapper for the LinkedIn scraper entrypoint."""


def main() -> None:
    """Run the package-based scraper."""

    from linkedin_post_generator.scraper.runner import main as run_scraper

    run_scraper()


if __name__ == "__main__":
    main()
