"""Entry point: setup/status web app with the poller running in the background."""

import logging

import uvicorn

from .config import Config


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run("deye_monitor.web:app", host="0.0.0.0", port=Config().web_port,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
