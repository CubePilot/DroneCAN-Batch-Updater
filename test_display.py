#!/usr/bin/env python3

import sys
import os
import time
import threading

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from rich.console import Console
from progress_ui import ProgressUI

def test_progress_display():
    console = Console()
    progress_ui = ProgressUI(console)
    
    # Add some test devices
    progress_ui.add_cube_device("test1", "CubeOrange", "/dev/tty.test1", "CubeOrange")
    progress_ui.add_cube_device("test2", "CubeBlack", "/dev/tty.test2", "CubeBlack") 
    
    # Start the live display
    progress_ui.start_progress_display()
    
    # Simulate some console output and progress updates
    for i in range(10):
        progress_ui.add_console_output(f"[VERBOSE] test1: Progress step {i}")
        progress_ui.update_cube_progress("test1", "uploading", i * 10)
        
        if i > 5:
            progress_ui.add_console_output(f"[VERBOSE] test2: Progress step {i-5}")
            progress_ui.update_cube_progress("test2", "uploading", (i-5) * 10)
        
        time.sleep(0.3)
    
    progress_ui.update_cube_progress("test1", "complete", 100)
    progress_ui.update_cube_progress("test2", "complete", 100)
    
    # Add some final console output
    progress_ui.add_console_output("[VERBOSE] test1: Upload completed successfully!")
    progress_ui.add_console_output("[VERBOSE] test2: Upload completed successfully!")
    
    time.sleep(1)
    progress_ui.stop_live_display()
    
    console.print("\n[green]Test completed![/green]")

if __name__ == "__main__":
    test_progress_display()