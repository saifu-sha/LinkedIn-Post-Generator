"""Compatibility wrapper for the Streamlit application entrypoint."""


def main() -> None:
    """Run the Streamlit UI."""

    from linkedin_post_generator.ui import main as run_app

    run_app()


if __name__ == "__main__":
    main()
