#!/usr/bin/env python3

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class DroneCANLogger:
    """Centralized logging system for DroneCAN Batch Updater"""
    
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir) if log_dir else Path("logs")
        self.log_dir.mkdir(exist_ok=True)
        
        # Create timestamp for this session
        self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Set up loggers
        self._setup_loggers()
        
    def _setup_loggers(self):
        """Set up different loggers for different components"""
        
        # Main application logger
        self.main_logger = self._create_logger(
            "dronecan_main",
            f"dronecan_main_{self.session_timestamp}.log"
        )
        
        # Cube updater logger
        self.cube_logger = self._create_logger(
            "cube_updater", 
            f"cube_updater_{self.session_timestamp}.log"
        )
        
        # DroneCAN monitor logger
        self.dronecan_logger = self._create_logger(
            "dronecan_monitor",
            f"dronecan_monitor_{self.session_timestamp}.log"
        )
        
        # Uploader logger
        self.uploader_logger = self._create_logger(
            "uploader",
            f"uploader_{self.session_timestamp}.log"
        )
        
        # Combined session logger (all messages)
        self.session_logger = self._create_logger(
            "session_combined",
            f"session_combined_{self.session_timestamp}.log"
        )
        
    def _create_logger(self, name: str, filename: str) -> logging.Logger:
        """Create a logger with file and console output"""
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        
        # Prevent duplicate handlers
        if logger.handlers:
            return logger
            
        # File handler
        file_handler = logging.FileHandler(self.log_dir / filename, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
        
    def log_main(self, message: str, level: str = "INFO"):
        """Log main application messages"""
        self._log_to_logger(self.main_logger, message, level)
        self._log_to_logger(self.session_logger, f"[MAIN] {message}", level)
        
    def log_cube(self, message: str, level: str = "INFO"):
        """Log cube updater messages"""
        self._log_to_logger(self.cube_logger, message, level)
        self._log_to_logger(self.session_logger, f"[CUBE] {message}", level)
        
    def log_dronecan(self, message: str, level: str = "INFO"):
        """Log DroneCAN monitor messages"""
        self._log_to_logger(self.dronecan_logger, message, level)
        self._log_to_logger(self.session_logger, f"[DRONECAN] {message}", level)
        
    def log_uploader(self, message: str, level: str = "INFO"):
        """Log uploader messages"""
        self._log_to_logger(self.uploader_logger, message, level)
        self._log_to_logger(self.session_logger, f"[UPLOADER] {message}", level)
        
    def _log_to_logger(self, logger: logging.Logger, message: str, level: str):
        """Helper to log to a specific logger with the given level"""
        level = level.upper()
        if level == "DEBUG":
            logger.debug(message)
        elif level == "INFO":
            logger.info(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "CRITICAL":
            logger.critical(message)
        else:
            logger.info(message)
            
    def get_log_files(self) -> dict:
        """Get paths to all log files for this session"""
        return {
            "main": self.log_dir / f"dronecan_main_{self.session_timestamp}.log",
            "cube": self.log_dir / f"cube_updater_{self.session_timestamp}.log", 
            "dronecan": self.log_dir / f"dronecan_monitor_{self.session_timestamp}.log",
            "uploader": self.log_dir / f"uploader_{self.session_timestamp}.log",
            "session": self.log_dir / f"session_combined_{self.session_timestamp}.log"
        }
        
    def log_session_start(self):
        """Log session start information"""
        self.log_main("=" * 80)
        self.log_main("DroneCAN Batch Firmware Updater - Session Started")
        self.log_main(f"Session ID: {self.session_timestamp}")
        self.log_main(f"Log Directory: {self.log_dir.absolute()}")
        self.log_main("=" * 80)
        
    def log_session_end(self):
        """Log session end information"""
        self.log_main("=" * 80)
        self.log_main("DroneCAN Batch Firmware Updater - Session Ended")
        self.log_main(f"Session ID: {self.session_timestamp}")
        log_files = self.get_log_files()
        self.log_main("Log files created:")
        for component, path in log_files.items():
            if path.exists():
                size = path.stat().st_size
                self.log_main(f"  {component}: {path} ({size} bytes)")
        self.log_main("=" * 80)


# Global logger instance
_global_logger: Optional[DroneCANLogger] = None

def get_logger() -> DroneCANLogger:
    """Get the global logger instance, creating it if needed"""
    global _global_logger
    if _global_logger is None:
        _global_logger = DroneCANLogger()
        _global_logger.log_session_start()
    return _global_logger

def shutdown_logger():
    """Shutdown the global logger"""
    global _global_logger
    if _global_logger is not None:
        _global_logger.log_session_end()
        # Close all handlers
        for logger_name in ["dronecan_main", "cube_updater", "dronecan_monitor", "uploader", "session_combined"]:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers[:]:
                handler.close()
                logger.removeHandler(handler)
        _global_logger = None