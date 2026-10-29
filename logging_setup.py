import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_dir: Path | None = None) -> Path:
    if log_dir is None:
        if os.name == "nt":
            root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:
            root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
        log_dir = root / "JARVIS" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "jarvis.log"
    handler = RotatingFileHandler(
        log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
        force=True,
    )

    logger = logging.getLogger("jarvis")

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught application exception",
                        exc_info=(exc_type, exc_value, exc_traceback))

    def handle_thread_exception(args):
        logger.critical("Uncaught exception in thread %s", args.thread.name,
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
    logger.info("JARVIS logging started")
    return log_path