from loguru import logger
import os

log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(log_path, exist_ok=True)
log_file = os.path.join(log_path, 'irrigation_system.log')

logger.add(log_file, 
          rotation="500 MB",
          encoding="utf-8",
          enqueue=True,
          compression="zip",
          retention="10 days")