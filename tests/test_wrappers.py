import importlib.util
from pathlib import Path

import few_shots
import llm_helper
import post_generator
import preprocess


def load_module_from_path(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_root_wrappers_expose_expected_symbols():
    assert callable(few_shots.FewShotPosts)
    assert callable(post_generator.generate_post)
    assert callable(preprocess.process_posts)
    assert llm_helper.llm.__class__.__name__ == "LazyLLM"


def test_file_based_wrappers_define_main():
    project_root = Path(__file__).resolve().parent.parent

    main_module = load_module_from_path(project_root / "main.py", "legacy_main")
    scraper_module = load_module_from_path(project_root / "data" / "new2.py", "legacy_scraper")

    assert callable(main_module.main)
    assert callable(scraper_module.main)
