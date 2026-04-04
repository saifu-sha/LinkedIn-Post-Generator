# LinkedIn Post Generator

This project scrapes LinkedIn posts, enriches them into a structured dataset, and uses a Groq-hosted LLM to generate new LinkedIn posts through a Streamlit UI.

## How The Project Is Organized

The codebase has two layers:

- `linkedin_post_generator/`
  The real implementation lives here.
- top-level files such as `main.py`, `preprocess.py`, and `data/new2.py`
  These are compatibility wrappers so you can keep using the old run commands.

### Main Package

- `linkedin_post_generator/config.py`
  Centralized paths, `.env` loading, and scraper settings.
- `linkedin_post_generator/models.py`
  Shared dataclasses and normalization helpers.
- `linkedin_post_generator/llm.py`
  Groq LLM creation and lazy compatibility wrapper.
- `linkedin_post_generator/repository.py`
  Loads and filters processed posts for few-shot prompting.
- `linkedin_post_generator/generator.py`
  Builds prompts and generates LinkedIn posts.
- `linkedin_post_generator/preprocess.py`
  Enriches raw scraped posts with metadata and unified tags.
- `linkedin_post_generator/ui.py`
  Streamlit interface.
- `linkedin_post_generator/scraper/`
  Scraper implementation split into cleaning, DOM extraction, session handling, Voyager fallback, and orchestration.

### Wrapper Files

- `main.py`
  Runs the Streamlit app.
- `preprocess.py`
  Runs the preprocessing pipeline.
- `post_generator.py`
  Re-exports generation helpers.
- `few_shots.py`
  Re-exports repository helpers.
- `llm_helper.py`
  Re-exports the lazy `llm` object for compatibility.
- `data/new2.py`
  Runs the scraper.

## Data Flow

1. Scrape posts from LinkedIn into `data/raw_posts.json`
2. Enrich those posts into `data/processed_posts.json`
3. Load processed posts as few-shot examples
4. Generate a new post in the Streamlit UI

## Requirements

- Python 3.12+
- Google Chrome installed
- A Groq API key
- LinkedIn credentials for scraping

## Installation

Create and activate a virtual environment, then install the project:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .[dev]
```

## Environment Variables

Create a `.env` file in the project root. You can copy `.env.example`.

Required values:

- `GROQ_API_KEY`
- `LINKEDIN_USERNAME`
- `LINKEDIN_PASSWORD`
- `LINKEDIN_PAGE`

Optional scraper tuning:

- `SCROLL_PAUSE_TIME`
- `MAX_SCROLLS`
- `POST_LOAD_TIMEOUT`

Example:

```env
GROQ_API_KEY=your_groq_api_key
SCROLL_PAUSE_TIME=0.8
MAX_SCROLLS=3
POST_LOAD_TIMEOUT=7
LINKEDIN_USERNAME=your_email
LINKEDIN_PASSWORD=your_password
LINKEDIN_PAGE=https://www.linkedin.com/in/example-profile/
```

## Running The Full Project

### 1. Scrape Raw Posts

```bash
python data/new2.py
```

What this does:

- opens a Chrome browser
- logs into LinkedIn
- navigates to the target page’s posts
- scrapes posts from the DOM
- falls back to Voyager API requests if needed
- saves output to `data/raw_posts.json`

Note:

- LinkedIn may require checkpoint or 2FA verification in the opened browser window.

### 2. Build Processed Posts

```bash
python preprocess.py
```

What this does:

- reads `data/raw_posts.json`
- asks the LLM to extract `line_count`, `language`, and `tags`
- asks the LLM to unify similar tags
- saves output to `data/processed_posts.json`

### 3. Start The App

```bash
streamlit run main.py
```

What this does:

- loads `data/processed_posts.json`
- shows tag, length, and language selectors
- builds a prompt using matching example posts
- calls the Groq model
- displays the generated post

## Development Commands

Run tests:

```bash
python -m pytest
```

Run lint checks:

```bash
python -m ruff check .
```

## Outputs

- `data/raw_posts.json`
  Raw scraped posts with `text` and `engagement`
- `data/processed_posts.json`
  Enriched posts with `text`, `engagement`, `line_count`, `language`, and `tags`

## Common Issues

### `GROQ_API_KEY is not set`

Your `.env` file is missing the API key, or the current shell is not using the project root.

### `Processed posts file was not found`

Run:

```bash
python preprocess.py
```

### LinkedIn login or checkpoint problems

The scraper supports manual verification in the opened browser window. Complete the challenge there and continue.

### JSON parsing errors during preprocessing

The preprocessing layer expects JSON-like model output and already handles fenced JSON. If the model returns invalid content, rerun or inspect the failing post.

## Recommended Run Order

```bash
python data/new2.py
python preprocess.py
streamlit run main.py
```
