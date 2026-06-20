import os
import logging
from logging.handlers import RotatingFileHandler


_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG_DIR = os.path.join(_ROOT_DIR, "logs")

if not os.path.exists(_LOG_DIR):
    os.makedirs(_LOG_DIR, exist_ok=True)

_LOG_FILE = os.path.join(_LOG_DIR, "iris.log")

def get_logger(name: str = "Iris", level=logging.INFO) -> logging.Logger:
    
    logger = logging.getLogger(name)
    
    
    if not logger.hasHandlers():
        logger.setLevel(level)
        
        
        file_handler = RotatingFileHandler(_LOG_FILE, maxBytes=5*1024*1024, backupCount=2, encoding="utf-8")
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        
        
        console_handler = logging.StreamHandler()
        
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        
        logger.propagate = False
        
    return logger
