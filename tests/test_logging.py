from loguru import logger

from app.core.logger import configure_logging


def test_configure_logging_creates_file_and_writes(tmp_path, monkeypatch):
    """Ensure configure_logging creates logs/bot.log and records messages."""
    monkeypatch.chdir(tmp_path)

    configure_logging()

    log_file = tmp_path / "logs" / "bot.log"
    assert log_file.exists()

    test_message = "Log file integration smoke-test"
    logger.info(test_message)

    contents = log_file.read_text()
    assert test_message in contents
    assert "INFO" in contents

