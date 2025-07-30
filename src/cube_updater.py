#!/usr/bin/env python3

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Import the existing uploader module
from uploader import firmware, ports_to_try, uploader


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
        self.firmware_dir = Path(__file__).parent.parent / "firmware"
        self.detected_devices: List[CubeDevice] = []

    def _log_output(self, message: str):
        """Log output to the progress UI console buffer"""
        if hasattr(self.progress_ui, "add_console_output"):
            self.progress_ui.add_console_output(message)
        else:
            # Fallback to regular print if progress UI is not ready
            print(message)

    def detect_devices(self) -> List[CubeDevice]:
        """Detect all connected Cube devices with retry for USB port changes"""
        devices = []

        # Create a mock args object for ports_to_try function
        class MockArgs:
            def __init__(self):
                self.port = None

        mock_args = MockArgs()

        # Try detection multiple times to handle USB port changes
        max_detection_rounds = 3

        for detection_round in range(max_detection_rounds):
            self._log_output(
                f"[DEBUG] Device detection round " f"{detection_round + 1}/{max_detection_rounds}"
            )

            possible_ports = ports_to_try(mock_args)
            round_devices = []

            for port in possible_ports:
                try:
                    # Skip ports we've already successfully detected
                    if any(d.port == port for d in devices):
                        continue

                    # Try to connect to each port and identify the device
                    device = self._identify_device(port)
                    if device:
                        round_devices.append(device)

                except Exception as e:
                    # DEBUG_PRINT: Device detection error
                    self._log_output(f"[DEBUG] Error detecting device on {port}: {e}")
                    continue

            devices.extend(round_devices)

            # If we found devices in this round, wait for potential port changes
            if round_devices:
                self._log_output(
                    f"[DEBUG] Found {len(round_devices)} devices in round "
                    f"{detection_round + 1}, waiting for port changes..."
                )
                time.sleep(2.0)

        self.detected_devices = devices
        self._log_output(f"[DEBUG] Total devices detected: {len(devices)}")
        return devices

    def _identify_device(self, port: str) -> Optional[CubeDevice]:
        """Try to identify a device on the given port"""
        try:
            # Create uploader instance with minimal configuration
            up = uploader(
                portname=port,
                baudrate_bootloader=115200,
                baudrate_flightstack=[57600],
                baudrate_bootloader_flash=None,
                target_system=None,
                target_component=None,
                source_system=255,
                source_component=1,
                no_extf=False,
                force_erase=False,
            )

            # Try to find and identify the bootloader
            if self._find_bootloader(up, port):
                board_name = up.board_name_for_board_id(up.board_type) or f"Unknown_{up.board_type}"

                device = CubeDevice(
                    port=port,
                    board_type=up.board_type,
                    board_rev=up.board_rev,
                    board_name=board_name,
                )

                up.close()
                return device

            up.close()

        except Exception as e:
            # DEBUG_PRINT: Device identification error
            self._log_output(f"[DEBUG] Failed to identify device on {port}: {e}")

        return None

    def _find_bootloader(self, up, port: str) -> bool:
        """Try to find bootloader on the given port with retries for USB port changes"""
        max_attempts = 10  # Increase attempts for USB port changes

        for attempt in range(max_attempts):
            try:
                up.open()
                # Try to identify the bootloader
                up.identify()
                return True

            except Exception as e:
                # DEBUG_PRINT: Attempt failed
                self._log_output(
                    f"[DEBUG] Bootloader attempt {attempt + 1}/{max_attempts} " f"on {port}: {e}"
                )

                # Try to send reboot command on first few attempts
                if attempt < 3:
                    try:
                        reboot_sent = up.send_reboot()
                        if reboot_sent:
                            self._log_output(
                                f"[DEBUG] Reboot sent to {port}, " f"waiting for USB port change..."
                            )
                    except Exception:
                        pass

                up.close()

                # Wait 2 seconds for USB port changes as requested
                time.sleep(2.0)

        return False

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

            # Create uploader instance
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
            )

            # Find bootloader
            self._log_output(f"[VERBOSE] {device.port}: Searching for bootloader...")
            if not self._find_bootloader(up, device.port):
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
        """Upload firmware with progress tracking using subprocess to
        isolate uploader output"""
        import os
        import re
        import subprocess
        import tempfile

        device_port = device_id.replace("cube_", "").replace("_", "/")

        self._log_output(f"[VERBOSE] {device_port}: Starting firmware upload process...")

        # Create a temporary script to run the uploader in isolation
        script_content = f"""#!/usr/bin/env python3
import sys
import os

# Add the src directory to the path
sys.path.insert(0, "{os.path.dirname(os.path.abspath(__file__))}")

from uploader import uploader, firmware

try:
    # Load firmware
    fw = firmware("{device.firmware_file}")

    # Create uploader
    up = uploader(
        portname="{device.port}",
        baudrate_bootloader=115200,
        baudrate_flightstack=[57600],
        baudrate_bootloader_flash=None,
        target_system=None,
        target_component=None,
        source_system=255,
        source_component=1,
        no_extf=False,
        force_erase=False
    )

    # Open and identify
    up.open()
    up.identify()

    # Upload firmware
    up.upload(fw, force=False, boot_delay=None)

    # Close connection
    up.close()

    print("UPLOAD_SUCCESS")
except Exception as e:
    print("UPLOAD_ERROR: " + str(e))
    sys.exit(1)
"""

        try:
            # Write the script to a temporary file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(script_content)
                script_path = f.name

            # Run the script and monitor output
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
            )

            upload_success = False

            # Monitor output line by line
            for line in iter(process.stdout.readline, ""):
                if not line:
                    break

                line = line.strip()
                if line:
                    self._log_output(f"[UPLOADER] {device_port}: {line}")

                    # Parse progress information
                    if "UPLOAD_SUCCESS" in line:
                        upload_success = True
                    elif "UPLOAD_ERROR:" in line:
                        error_msg = line.replace("UPLOAD_ERROR:", "").strip()
                        raise Exception(f"Upload failed: {error_msg}")
                    elif "Erase" in line and ":" in line:
                        # Extract progress from "Erase  : [====                ] 22.3%" format
                        progress_match = re.search(r"(\d+\.?\d*)", line)
                        if progress_match:
                            try:
                                progress_val = float(progress_match.group(1))
                                # Scale erase progress to 0-20% range
                                scaled_progress = min(progress_val * 0.2, 20)
                                self.progress_ui.update_cube_progress(
                                    device_id, "erasing", scaled_progress
                                )
                            except Exception:
                                self.progress_ui.update_cube_progress(device_id, "erasing", 15)
                        else:
                            self.progress_ui.update_cube_progress(device_id, "erasing", 15)
                    elif "Program:" in line:
                        # Extract progress from "Program: [=================== ] 96.1" format
                        progress_match = re.search(r"(\d+\.?\d*)", line)
                        if progress_match:
                            try:
                                progress_val = float(progress_match.group(1))
                                scaled_progress = min(20 + (progress_val * 0.7), 90)
                                self.progress_ui.update_cube_progress(
                                    device_id, "uploading", scaled_progress
                                )
                            except Exception:
                                pass
                    elif "Verify" in line and ":" in line:
                        self.progress_ui.update_cube_progress(device_id, "verifying", 95)

            # Wait for process to complete
            process.wait()

            if process.returncode != 0 and not upload_success:
                raise Exception(f"Upload process failed with return code {process.returncode}")

            if not upload_success:
                raise Exception("Upload completed but success confirmation not received")

            self._log_output(f"[VERBOSE] {device_port}: Upload completed successfully")
            self.progress_ui.update_cube_progress(device_id, "complete", 100)

        finally:
            # Clean up temporary script
            try:
                os.unlink(script_path)
            except Exception:
                pass
