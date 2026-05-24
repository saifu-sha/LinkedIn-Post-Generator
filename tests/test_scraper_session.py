import pytest

from linkedin_post_generator.scraper import session


def test_build_chrome_service_skips_chromedriver_from_path(monkeypatch, tmp_path):
    driver_path = tmp_path / "chromedriver.exe"
    driver_path.write_text("", encoding="utf-8")
    captured_args = {}

    class FakeSeleniumManager:
        def binary_paths(self, args):
            captured_args["value"] = args
            return {"driver_path": str(driver_path)}

    monkeypatch.setattr(session, "SeleniumManager", FakeSeleniumManager)

    service = session.build_chrome_service()

    assert captured_args["value"] == ["--browser", "chrome", "--skip-driver-in-path"]
    assert service.path == str(driver_path)
    assert service.DRIVER_PATH_ENV_KEY == "LINKEDIN_POST_GENERATOR_CHROMEDRIVER"


def test_build_chrome_service_rejects_invalid_manager_result(monkeypatch):
    class FakeSeleniumManager:
        def binary_paths(self, args):
            return {"driver_path": ""}

    monkeypatch.setattr(session, "SeleniumManager", FakeSeleniumManager)

    with pytest.raises(session.NoSuchDriverException, match="valid ChromeDriver"):
        session.build_chrome_service()
