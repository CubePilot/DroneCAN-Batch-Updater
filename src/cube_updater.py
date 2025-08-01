#!/usr/bin/env python3

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Import the existing uploader module
from uploader import firmware, ports_to_try, uploader, find_bootloader
from logger import get_logger


def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and Nuitka builds"""
    import os
    
    # Check if running under Nuitka by checking if __compiled__ exists in globals
    if "__compiled__" in globals():
        # Running under Nuitka - use same directory as script file
        base_path = Path(__file__).parent
        print(f"Getting resource path for: {relative_path} at base path: {base_path} for Nuitka")
    else:
        # Running from source - go up one level to project root
        base_path = Path(__file__).parent.parent
        print(f"Getting resource path for: {relative_path} at base path: {base_path} for dev")

    return Path(base_path) / relative_path


@dataclass
class CubeDevice:
    port: str
    board_type: int
    board_rev: int
    board_name: str
    current_firmware_version: Optional[str] = None
    needs_update: bool = False
    firmware_file: Optional[str] = None


class CubeUpdater:
    def __init__(self, progress_ui):
        self.progress_ui = progress_ui
        self.logger = get_logger()
        self.firmware_dir = get_resource_path("firmware")
        self.detected_devices: List[CubeDevice] = []

    def _log_output(self, message: str):
        """Log output to the progress UI console buffer and log files"""
        # Log to file
        self.logger.log_cube(message)
        
        # Also send to UI
        if hasattr(self.progress_ui, "add_console_output"):
            self.progress_ui.add_console_output(message)
        else:
            # Fallback to regular print if progress UI is not ready
            print(message)

    def detect_devices(self) -> List[CubeDevice]:
        """Detect all connected Cube devices using uploader.py's main detection pattern with retries"""
        devices = []

        # Create a mock args object for ports_to_try function  
        class MockArgs:
            def __init__(self):
                self.port = None

        mock_args = MockArgs()

        # Use uploader.py's exact detection pattern with continuous retry like main()
        max_attempts = 3
        for attempt in range(max_attempts):
            self._log_output(f"[DEBUG] Device detection attempt {attempt + 1}/{max_attempts}")
            
            for port in ports_to_try(mock_args):
                # Skip ports we've already found devices on
                if any(d.port == port for d in devices):
                    self._log_output(f"[DEBUG] Skipping already detected port: {port}")
                    continue
                    
                try:
                    # Create log callback for device identification
                    def log_callback(message):
                        self._log_output(f"[UPLOADER] {port}: {message}")

                    # Create uploader instance exactly like uploader.py main() does
                    up = uploader(
                        port,
                        115200,  # baud_bootloader
                        [57600], # baud_flightstack  
                        None,    # baud_bootloader_flash
                        None,    # target_system
                        None,    # target_component  
                        255,     # source_system
                        1,       # source_component
                        False,   # no_extf
                        False,   # force_erase
                        log_callback=log_callback,
                    )

                    # Use uploader.py's find_bootloader exactly
                    if find_bootloader(up, port):
                        self._log_output(f"[DEBUG] Found Cube device on {port}")
                        board_name = up.board_name_for_board_id(up.board_type) or f"Unknown_{up.board_type}"

                        device = CubeDevice(
                            port=port,
                            board_type=up.board_type,
                            board_rev=up.board_rev,
                            board_name=board_name,
                        )

                        devices.append(device)
                        up.close()
                    else:
                        up.close()

                except Exception as e:
                    self._log_output(f"[DEBUG] Error on {port}: {e}")
                    continue
            
            # Continue scanning all attempts to find all possible devices
            # Don't break early - we want to find ALL cubes
                
            # Small delay between attempts to allow USB re-enumeration
            if attempt < max_attempts - 1:
                self._log_output(f"[DEBUG] Completed attempt {attempt + 1}, waiting before next attempt...")
                time.sleep(0.5)

        self.detected_devices = devices
        self._log_output(f"[DEBUG] Total devices detected: {len(devices)}")
        return devices


    def check_firmware_versions(self, devices: List[CubeDevice]) -> List[CubeDevice]:
        """Check which devices need firmware updates"""
        devices_needing_update = []

        # DEBUG_PRINT: Check firmware versions
        self._log_output(f"[DEBUG] Checking firmware for {len(devices)} devices")

        for device in devices:
            # DEBUG_PRINT: Device info
            self._log_output(
                f"[DEBUG] Device: {device.port}, board_type: {device.board_type}, "
                f"board_name: {device.board_name}"
            )

            # Find matching firmware file for this device
            firmware_file = self._find_firmware_file(device)

            if firmware_file:
                # DEBUG_PRINT: Firmware found
                self._log_output(f"[DEBUG] Found firmware for {device.port}: {firmware_file}")
                device.firmware_file = firmware_file
                device.needs_update = True  # For now, assume all devices need update
                devices_needing_update.append(device)

                # Add to progress UI
                device_id = f"cube_{device.port.replace('/', '_')}"
                self.progress_ui.add_cube_device(
                    device_id=device_id,
                    name=device.board_name,
                    port=device.port,
                    device_type=device.board_name,
                )
            else:
                # DEBUG_PRINT: No firmware found
                self._log_output(
                    f"[DEBUG] No firmware found for {device.port} "
                    f"(board_type: {device.board_type})"
                )

        # DEBUG_PRINT: Result
        self._log_output(f"[DEBUG] {len(devices_needing_update)} devices need updates")
        return devices_needing_update

    def _find_firmware_file(self, device: CubeDevice) -> Optional[str]:
        """Find appropriate firmware file for the device"""
        # DEBUG_PRINT: Firmware search
        self._log_output(f"[DEBUG] Looking for firmware in: {self.firmware_dir}")

        # Look for APJ files in firmware directory
        apj_files = list(self.firmware_dir.glob("*.apj"))
        self._log_output(f"[DEBUG] Found APJ files: {[str(f) for f in apj_files]}")

        for apj_file in apj_files:
            try:
                # DEBUG_PRINT: Testing firmware file
                self._log_output(f"[DEBUG] Testing firmware file: {apj_file}")

                # Load firmware and check board compatibility
                fw = firmware(str(apj_file))
                fw_board_id = fw.property("board_id")

                # DEBUG_PRINT: Board ID comparison
                self._log_output(
                    f"[DEBUG] Firmware board_id: {fw_board_id}, "
                    f"Device board_type: {device.board_type}"
                )

                if fw_board_id == device.board_type:
                    self._log_output(f"[DEBUG] Match found! Using {apj_file}")
                    return str(apj_file)

            except Exception as e:
                # DEBUG_PRINT: Firmware file error
                self._log_output(f"[DEBUG] Error loading firmware {apj_file}: {e}")
                continue

        # If no exact match, look for compatible firmware
        # Check if this board has compatible firmware
        from uploader import compatible_IDs

        if device.board_type in compatible_IDs:
            compatible_board_id = compatible_IDs[device.board_type][0]

            for apj_file in apj_files:
                try:
                    fw = firmware(str(apj_file))
                    if fw.property("board_id") == compatible_board_id:
                        return str(apj_file)
                except Exception:
                    continue

        return None

    def update_devices(self, devices: List[CubeDevice]) -> bool:
        """Update firmware on all specified devices in parallel"""
        if not devices:
            return True

        # Progress display already started in main

        success_count = 0

        try:
            # Use ThreadPoolExecutor for parallel updates
            with ThreadPoolExecutor(max_workers=len(devices)) as executor:
                # Submit all update tasks
                future_to_device = {}
                for device in devices:
                    device_id = f"cube_{device.port.replace('/', '_')}"
                    future = executor.submit(self._update_single_device, device, device_id)
                    future_to_device[future] = device

                # Wait for all updates to complete and track progress
                for future in as_completed(future_to_device):
                    device = future_to_device[future]
                    try:
                        if future.result():
                            success_count += 1
                        else:
                            pass  # Error already logged in _update_single_device
                    except Exception:
                        pass  # Error already logged in _update_single_device

        finally:
            # Show final progress display
            print("\n" + "=" * 80)
            print("FIRMWARE UPDATE COMPLETE")
            print("=" * 80)
            self.progress_ui.display_cube_progress()

            # Give a moment for all threads to clean up
            time.sleep(0.5)

        return success_count == len(devices)

    def _update_single_device(self, device: CubeDevice, device_id: str) -> bool:
        """Update firmware on a single device"""
        try:
            self._log_output(
                f"[VERBOSE] {device.port}: Starting firmware update " f"({device.board_name})"
            )
            self._log_output(
                f"[VERBOSE] {device.port}: Using firmware file: {device.firmware_file}"
            )

            self.progress_ui.update_cube_progress(device_id, "connecting", 0)

            # Load firmware file
            self._log_output(f"[VERBOSE] {device.port}: Loading firmware file...")
            fw = firmware(device.firmware_file)
            self._log_output(f"[VERBOSE] {device.port}: Firmware loaded successfully")

            # Create progress callback function
            def progress_callback(phase, progress_percent):
                if phase == "erase":
                    # Scale erase progress to 0-20% range  
                    scaled_progress = min(progress_percent * 0.2, 20)
                    self.progress_ui.update_cube_progress(device_id, "erasing", scaled_progress)
                    self._log_output(f"[UPLOADER] {device.port}: Erasing: {progress_percent:.1f}%")
                elif phase == "program":
                    # Scale program progress to 20-90% range
                    scaled_progress = min(20 + (progress_percent * 0.7), 90)
                    self.progress_ui.update_cube_progress(device_id, "uploading", scaled_progress)
                    self._log_output(f"[UPLOADER] {device.port}: Programming: {progress_percent:.1f}%")
                elif phase == "verify":
                    self.progress_ui.update_cube_progress(device_id, "verifying", 95)
                    self._log_output(f"[UPLOADER] {device.port}: Verifying: {progress_percent:.1f}%")

            # Create log callback function
            def log_callback(message):
                self._log_output(f"[UPLOADER] {device.port}: {message}")

            # Create uploader instance with progress and log callbacks
            self._log_output(f"[VERBOSE] {device.port}: Creating uploader connection...")
            up = uploader(
                portname=device.port,
                baudrate_bootloader=115200,
                baudrate_flightstack=[57600],
                baudrate_bootloader_flash=None,
                target_system=None,
                target_component=None,
                source_system=255,
                source_component=1,
                no_extf=False,
                force_erase=False,
                progress_callback=progress_callback,
                log_callback=log_callback,
            )

            # Find bootloader
            self._log_output(f"[VERBOSE] {device.port}: Searching for bootloader...")
            if not find_bootloader(up, device.port):
                self._log_output(f"[VERBOSE] {device.port}: Bootloader not found")
                self.progress_ui.update_cube_progress(
                    device_id, "failed", 0, "Bootloader not found"
                )
                up.close()
                return False

            self._log_output(
                f"[VERBOSE] {device.port}: Bootloader found, " f"board type: {up.board_type}"
            )

            # Perform the upload with progress tracking
            self._upload_with_progress(up, fw, device_id, device)

            up.close()
            self._log_output(f"[VERBOSE] {device.port}: Firmware update completed successfully!")
            self.progress_ui.update_cube_progress(device_id, "complete", 100)
            return True

        except Exception as e:
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            self.progress_ui.update_cube_progress(device_id, "failed", 0, error_msg)
            self._log_output(f"[VERBOSE] {device.port}: Update failed - {e}")
            return False

    def _upload_with_progress(self, up, fw, device_id: str, device: "CubeDevice"):
        """Upload firmware with real-time progress tracking via callback"""
        
        device_port = device_id.replace("cube_", "").replace("_", "/")
        self._log_output(f"[VERBOSE] {device_port}: Starting firmware upload process...")

        try:
            # The uploader now has a progress_callback that will handle UI updates automatically
            self._log_output(f"[UPLOADER] {device_port}: Starting firmware upload...")
            
            # Perform the upload - progress updates will be handled by the callback
            up.upload(fw, force=False, boot_delay=None)
            
            # Final completion update
            self.progress_ui.update_cube_progress(device_id, "complete", 100)
            self._log_output(f"[UPLOADER] {device_port}: Upload completed successfully")

        except Exception as e:
            self._log_output(f"[UPLOADER] {device_port}: Upload failed: {str(e)}")
            raise
