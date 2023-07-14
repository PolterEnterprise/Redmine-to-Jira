# ############################################################################## #
# Created by Polterx, on Saturday, 1st of July, 2023                             #
# Website https://poltersanctuary.com                                            #
# Github  https://github.com/PolterEnterprise                                    #
# ############################################################################## #

import coloredlogs
import logging
from logging.handlers import RotatingFileHandler

def configure_logging(debug_mode=False):
    level = logging.DEBUG if debug_mode else logging.INFO
    log_format = "[%(asctime)s] %(levelname)s %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(level=level, format=log_format, datefmt=datefmt)

    if not debug_mode:
        coloredlogs.install(level=level, fmt=log_format, datefmt=datefmt)
    else:
        coloredlogs.install(level=logging.INFO, fmt=log_format, datefmt=datefmt)

def setup_logger(log_file):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    log_format = "[%(asctime)s] %(levelname)s %(message)s"
    log_date_format = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(log_format, log_date_format)

    file_handler = RotatingFileHandler(log_file, maxBytes=1000000, backupCount=3)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger
