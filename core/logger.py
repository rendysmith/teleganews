from loguru import logger
import sys

def setup_logger():
    logger.remove()
    logger.add(
        sys.stdout,
        format="<level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add("logs/app.log", rotation="10 MB", level="DEBUG")
    return logger

logger = setup_logger()