#!/usr/bin/env python3

import argparse
import os
import sys
import threading
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# pylint: disable=wrong-import-position
from cube_updater import CubeUpdater
from dronecan_monitor import DroneCaNMonitor
from progress_ui import ProgressUI


class BatchFirmwareUpdater:
    def __init__(self, auto_yes=False, skip_firmware=False):
        self.console = Console()
        self.progress_ui = ProgressUI(self.console)
        # Start unified progress display
        self.progress_ui.start_progress_display()
        self.cube_updater = CubeUpdater(self.progress_ui)
        self.dronecan_monitor = DroneCaNMonitor(self.progress_ui)
        self.auto_yes = auto_yes
        self.skip_cube_update = skip_firmware

        # Paths
        self.firmware_dir = Path(__file__).parent.parent / "firmware"

    def print_banner(self):
        banner = Text("DroneCAN Batch Firmware Updater", style="bold blue")
        self.console.print(Panel(banner, expand=False))
        self.console.print()

    def run(self):
        try:
            self.print_banner()

            if not self.skip_cube_update:
                # Phase A: Cube Detection and Update (One-time)
                self.console.print("[bold yellow]Phase A: Cube Firmware Update[/bold yellow]")
                self.console.print()

                # Check if firmware directory exists
                if not self.firmware_dir.exists():
                    self.progress_ui.add_console_output(
                        f"Error: Firmware directory not found: {self.firmware_dir}"
                    )
                    self.progress_ui.add_console_output(
                        "Please create the firmware directory and add APJ files for Cubes"
                    )
                    return 1

                # Detect connected Cube devices
                self.progress_ui.add_console_output("Scanning for connected Cube devices...")
                cube_devices = self.cube_updater.detect_devices()

                if not cube_devices:
                    self.progress_ui.add_console_output("No Cube devices detected.")
                else:
                    self.progress_ui.add_console_output(f"Found {len(cube_devices)} Cube device(s)")

                    # Check which devices need updates
                    devices_needing_update = self.cube_updater.check_firmware_versions(cube_devices)

                    if devices_needing_update:
                        self.progress_ui.add_console_output(
                            f"{len(devices_needing_update)} Cube(s) will be updated"
                        )

                        # Ask user for confirmation or auto-proceed
                        if self.auto_yes:
                            self.progress_ui.add_console_output(
                                "Auto-proceeding with updates (-y flag)"
                            )
                            proceed = True
                        else:
                            response = input(
                                f"Update {len(devices_needing_update)} Cube(s)? (y/N): "
                            )
                            proceed = response.lower() in ["y", "yes"]

                        if proceed:
                            self.progress_ui.add_console_output("Starting Cube firmware updates...")
                            success = self.cube_updater.update_devices(devices_needing_update)

                            if success:
                                self.progress_ui.add_console_output(
                                    "All Cube updates completed successfully!"
                                )
                            else:
                                self.progress_ui.add_console_output(
                                    "Some Cube updates failed. Check logs for details."
                                )
                                self.progress_ui.add_console_output(
                                    "Stopping here. Fix cube update issues before proceeding."
                                )
                                return 1
                        else:
                            self.progress_ui.add_console_output("Cube updates skipped by user.")
                    else:
                        self.progress_ui.add_console_output("All Cube devices are up to date.")

                self.console.print()
            else:
                self.progress_ui.add_console_output(
                    "Cube firmware update phase skipped (--skip-cube-update flag)"
                )

            self.progress_ui.add_console_output("Phase B: DroneCAN Continuous Monitoring")
            self.progress_ui.add_console_output("Starting DroneCAN monitoring mode...")
            time.sleep(6)

            # Phase B: DroneCAN Continuous Mode - Multi-interface support
            self.progress_ui.add_console_output("Starting DroneCAN monitoring mode...")
            self.progress_ui.add_console_output("Dynamic Node Allocation Server: Starting...")
            # DroneCAN monitor now handles its own threading and multi-interface support
            # It will discover all available interfaces and process them in parallel
            try:
                self.dronecan_monitor.start_monitoring()
                # start_monitoring() is now blocking and handles everything internally
                return 0
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Shutting down...[/yellow]")
                self.dronecan_monitor.stop_monitoring()
                return 0

        except Exception as e:
            self.console.print(f"[red]Error: {str(e)}[/red]")
            return 1


def main():
    parser = argparse.ArgumentParser(description="DroneCAN Batch Firmware Updater")
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Automatically answer yes to all prompts (non-interactive mode)",
    )
    parser.add_argument(
        "--skip-cube-update",
        action="store_true",
        help="Skip Cube firmware update phase and go directly to DroneCAN monitoring mode",
    )

    args = parser.parse_args()

    updater = BatchFirmwareUpdater(auto_yes=args.yes, skip_firmware=args.skip_cube_update)
    return updater.run()


if __name__ == "__main__":
    sys.exit(main())
