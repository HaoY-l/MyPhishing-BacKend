import logging
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FILE = os.getenv("LOG_FILE", "app.log")

def get_logger(name="mail_gateway"):
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

    if not getattr(logger, "_has_handlers", False):
        # 控制台 handler
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(ch)

        # 文件 handler
        fh = logging.FileHandler(LOG_FILE)
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)

        logger._has_handlers = True
        logger.propagate = False  # 防止重复打印

    return logger

logger = get_logger()
