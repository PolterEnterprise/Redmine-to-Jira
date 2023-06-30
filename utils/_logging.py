import logging
from logging.handlers import RotatingFileHandler
import coloredlogs

def setup_logger(log_file):
    # Create a logger instance
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    # Define log formatting
    log_format = "[%(asctime)s] %(levelname)s %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, log_date_format)

    # Create a rotating file handler
    file_handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Create a console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Add handlers to the logger
    logger.addHandler(file_handler)
    # logger.addHandler(console_handler)

    # Apply colored output to the console
    coloredlogs.install(level=logging.INFO, fmt=log_format, datefmt=log_date_format)

    return logger
