# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import os
import coloredlogs
import logging

from logging.handlers import RotatingFileHandler

DEFAULT_LOG_FORMAT = "[%(asctime)s] %(levelname)s %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_FILE_SIZE = 1000000  # 1MB
BACKUP_COUNT = 3

def configure_logging(debug_mode=False, log_format=DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT):
    level = logging.DEBUG if debug_mode else logging.INFO

    logging.basicConfig(level=level, format=log_format, datefmt=datefmt)

    if debug_mode:
        coloredlogs.install(level=logging.INFO, fmt=log_format, datefmt=datefmt)
    else:
        coloredlogs.install(level=level, fmt=log_format, datefmt=datefmt)

def setup_logger(prefix, log_dir, log_file_name, log_format=DEFAULT_LOG_FORMAT, datefmt=DEFAULT_DATE_FORMAT):
    # Create full log directory path with prefix
    full_log_dir = os.path.join(log_dir, prefix)
    
    # Create log directory if it doesn't exist
    os.makedirs(full_log_dir, exist_ok=True)

    # Full path to the log file
    log_file = os.path.join(full_log_dir, log_file_name)

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(log_format, datefmt)

    file_handler = RotatingFileHandler(log_file, maxBytes=MAX_LOG_FILE_SIZE, backupCount=BACKUP_COUNT)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


