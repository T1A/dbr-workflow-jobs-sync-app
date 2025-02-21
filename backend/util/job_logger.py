# In log_capture.py
import logging
from typing import List
import sys
import os

# This custom logger is used to capture the log messages to standard log (backend) + store messages in-memory to be used by the frontend

class StringListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.log_messages: List[str] = []
        self.setFormatter(logging.Formatter('%(levelname)s: %(message)s\n'))

    def format_error_with_location(self, record):
        if record.levelno >= logging.ERROR:
            # Get the frame where the error occurred
            frame = sys._getframe(6)  # Adjust frame depth as needed
            filename = os.path.basename(frame.f_code.co_filename)
            lineno = frame.f_lineno
            return f"{self.format(record)} (in {filename}, line {lineno})"
        return self.format(record)

    def emit(self, record):
        msg = self.format_error_with_location(record) if record.levelno >= logging.ERROR else self.format(record)
        self.log_messages.append(msg)

    def get_logs(self) -> List[str]:
        return self.log_messages

    def clear(self):
        self.log_messages.clear()

def setup_job_logger(name: str = "job_logger") -> tuple[logging.Logger, StringListHandler]:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Console handler with detailed formatting
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s\n'))
    
    # String list handler with simplified formatting
    string_handler = StringListHandler()
    string_handler.setLevel(logging.INFO)
    
    logger.addHandler(console)
    logger.addHandler(string_handler)
    
    return logger, string_handler

def log_exception(logger: logging.Logger, message: str, e: Exception):
    """Helper function to log exceptions with file and line information"""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    filename = os.path.basename(exc_traceback.tb_frame.f_code.co_filename)
    lineno = exc_traceback.tb_lineno
    logger.error(f"{message}: {str(e)} (in {filename}, line {lineno})\n")