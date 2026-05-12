# config/config_logging.py
import logging
import sys
from datetime import datetime


def setup_logging(level=logging.INFO, log_file=None):
    """配置日志"""
    handlers = [logging.StreamHandler(sys.stdout)]

    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

    return logging.getLogger(__name__)


def get_logger(name):
    return logging.getLogger(name)