#!/usr/bin/env python3

import glob
import os
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

import dronecan

from dronecan_node import DroneCANNode, RemoteDroneCANNode



def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and Nuitka onefile"""
    import os
    base_path = Path(__file__).parent
    print(f"Getting resource path for: {relative_path} at base path: {base_path}")
    return Path(base_path) / relative_path

class DroneCaNMonitor:
    def __init__(self, progress_ui):
        self.progress_ui = progress_ui
        self.firmware_dir = get_resource_path("firmware")
        self.node: Optional[dronecan.node.Node] = None
        self.node_manager: Optional[DroneCANNode] = None
        self.node_managers = []  # List of DroneCANNode instances for parallel processing
        self.dynamic_node_allocator = None
        self.running = False
        self.allocated_node_ids = set()  # Track allocated node IDs for cleanup

        # Default CAN settings
        self.port = None  # Will be auto-detected
        self.node_id = 100
        self.bitrate = 1000000

    def _detect_available_ports(self) -> List[str]:
        """Detect available serial ports for DroneCAN"""
        possible_ports = []

        # Common DroneCAN/CAN interface ports
        if sys.platform.startswith("linux"):
            possible_ports.extend(glob.glob("/dev/serial/by-id/usb-*if02"))
        elif sys.platform.startswith("darwin"):  # macOS
            possible_ports.extend(glob.glob("/dev/tty.usbmodem*03"))
            # Only use tty. devices, not cu. devices
        elif sys.platform.startswith("win"):
            for i in range(1, 256):
                possible_ports.append(f"COM{i}")

        # Filter to only existing ports
        available_ports = []
        for port in possible_ports:
            try:
                if os.path.exists(port) or sys.platform.startswith("win"):
                    available_ports.append(port)
            except Exception:
                continue

        return available_ports

    def start_monitoring(self, port: str = None, node_id: int = None, bitrate: int = None):
        """Start DroneCAN monitoring with dynamic node allocation"""
        try:
            # Progress display already started in main - ready to show device identification messages
            
            # Use provided parameters or defaults
            self.node_id = node_id or self.node_id
            self.bitrate = bitrate or self.bitrate

            # If no port specified, try to detect one
            if port:
                self.port = port
            else:
                # Detect available serial ports
                available_ports = self._detect_available_ports()

                if not available_ports:
                    self._log_output("No serial ports available for DroneCAN monitoring")
                    self._log_output("Connect a CAN interface and restart")
                    return

                # Discovery Phase: Test each port with both CAN bus 1 and 2
                # to find ALL interfaces with nodes
                discovered_interfaces = []  # List of DroneCANNode objects with discovered devices
                self._log_output("Discovery phase: Testing all interfaces for DroneCAN devices...")

                for test_port in available_ports:
                    port_found_devices = False  # Track if we found devices on this port
                    for bus_number in [2]:  # Test only bus number 2
                        if port_found_devices:  # Skip remaining buses if we already found devices
                            break
                        
                        try:
                            self._log_output(f"Testing {test_port} CAN bus {bus_number}...")

                            # Create DroneCANNode instance
                            node = DroneCANNode(
                                port=test_port,
                                bus_number=bus_number,
                                node_id=self.node_id,
                                bitrate=self.bitrate,
                                progress_ui=self.progress_ui,
                                firmware_dir=self.firmware_dir,
                            )

                            # Try to start the node
                            if node.start():
                                # Discover devices for 5 seconds
                                # Need enough time for nodes to get ID and start publishing
                                devices_found = node.discover_devices(timeout=10.0)

                                if devices_found:
                                    # Keep this node for further use
                                    discovered_interfaces.append(node)
                                    self._log_output(
                                        f"✓ Found {len(devices_found)} devices on "
                                        f"{test_port} CAN bus {bus_number}: {devices_found}"
                                    )
                                    port_found_devices = True  # Mark that we found devices on this port
                                else:
                                    self._log_output("  No devices found")
                                    # Stop unused node
                                    node.stop()
                            else:
                                self._log_output("  Failed to start node")

                        except Exception as e:
                            import traceback
                            self._log_output(f"  Error during discovery: {str(e)}")
                            self._log_output(f"  DEBUG: Traceback: {traceback.format_exc()}")
                            continue

                # Summary of discovery results
                if not discovered_interfaces:
                    self._log_output("No DroneCAN devices found on available interfaces")
                    self._log_output("Connect Here4 devices and restart")
                    return

                # Display discovery summary
                total_devices = sum(len(node.discovered_nodes) for node in discovered_interfaces)
                self._log_output("\n=== DISCOVERY COMPLETE ===")
                self._log_output(
                    f"Found {len(discovered_interfaces)} working interface(s) "
                    f"with {total_devices} total devices:"
                )

                for i, node in enumerate(discovered_interfaces):
                    device_list = ", ".join(map(str, node.discovered_nodes.keys()))
                    self._log_output(
                        f"  {i+1}. {node.port} CAN bus {node.bus_number}: "
                        f"{len(node.discovered_nodes)} devices [{device_list}]"
                    )

                # Process ALL discovered interfaces in parallel
                self._log_output(
                    f"\nProcessing ALL {len(discovered_interfaces)} interface(s) in parallel"
                )
                self._log_output("=========================\n")

                # Brief pause to let user see the discovery results
                self._log_output("Starting monitoring and update process in 3 seconds...")
                
                time.sleep(3)

                # Process all discovered interfaces for monitoring and updates
                self._process_all_interfaces(discovered_interfaces)

        except Exception as e:
            self._log_output(f"DEBUG: Exception caught: {e}")
            self._log_output(f"DEBUG: Exception type: {type(e)}")
            import traceback

            self._log_output(f"DEBUG: Traceback: {traceback.format_exc()}")
            self._log_output("Failed to start DroneCAN monitoring")
            self._log_output(f"Error: {str(e)}")
            self._log_output("DroneCAN monitoring disabled.")
            self.running = False
            return

    def _process_all_interfaces(self, discovered_interfaces):
        """Process all discovered interfaces in parallel for monitoring and updates"""
        try:
            self._log_output(f"Setting up monitoring for {len(discovered_interfaces)} interface(s)...")

            # Set up node managers for each interface
            self.node_managers = []
            for node in discovered_interfaces:
                try:
                    # progress_ui and firmware_dir already set during discovery
                    self._log_output(f"Setting up monitoring for {node.port} CAN bus {node.bus_number}...")
                    # Register this interface as active in the progress UI
                    interface_name = f"{node.port} CAN{node.bus_number}"
                    self.progress_ui.register_interface(interface_name, "Monitoring")
                    
                    node.start_monitoring(self._on_new_node_detected, self._on_node_removed)
                    self.node_managers.append(node)

                    self._log_output(f"✓ Monitoring started for {node.port} CAN bus {node.bus_number}")
                    
                    # Start firmware updates for any nodes that need updates immediately
                    self._start_immediate_updates(node)

                except Exception as e:
                    self._log_output(f"✗ Failed to start monitoring for {node.port}: {e}")
                    continue

            if not self.node_managers:
                self._log_output("No interfaces could be set up for monitoring")
                return

            # DroneCAN progress display already started - don't start live display

            # Set running flag and start monitoring
            self.running = True
            self._log_output(f"Monitoring active on {len(self.node_managers)} interface(s)")

            # Keep the main thread alive - the DroneCANNode threads handle spinning
            try:
                while self.running:
                    time.sleep(1)
                    # Update progress display
                    self.progress_ui.update_dronecan_status()
            except KeyboardInterrupt:
                self._log_output("\nShutting down...")
                self.running = False

        except Exception as e:
            import traceback
            self._log_output(f"Error in parallel processing: {e}")
            self._log_output(f"DEBUG: Traceback: {traceback.format_exc()}")
            self.running = False

    def stop_monitoring(self):
        """Stop DroneCAN monitoring"""
        self.running = False

        # Progress display will be stopped when the program exits

        # Stop all node managers
        for node_manager in self.node_managers:
            try:
                node_manager.stop_monitoring()
            except Exception as e:
                self._log_output(f"DEBUG: Error stopping node manager: {e}")

    def _on_new_node_detected(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode):
        """Callback when a new node is detected that needs update"""
        self._log_output(f"{str(remote_node)} detected and identified as {remote_node.device_name}")

        # Track this node for potential cleanup
        self.allocated_node_ids.add(remote_node.node_id)

        if remote_node.firmware_path:
            # Start firmware update in a separate thread
            # The firmware update process will handle waiting for operational mode
            update_thread = threading.Thread(
                target=self._update_node_firmware, args=(manager_node, remote_node), daemon=True
            )
            update_thread.start()
        else:
            self._log_output(f"{str(remote_node)} no firmware available")

    def _on_node_removed(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode):
        """Callback when a node is removed due to timeout"""
        self._log_output(f"{str(remote_node)} removed from allocation due to timeout")

        # Remove from our tracking
        self.allocated_node_ids.discard(remote_node.node_id)

        # Try to clean up from dynamic node allocators in all node managers
        for node_manager in self.node_managers:
            if node_manager.dynamic_node_allocator:
                try:
                    # Remove from dynamic node allocator's internal tracking
                    allocator = node_manager.dynamic_node_allocator
                    allocator._node_tracker._nodes.pop(remote_node.node_id, None)
                except Exception:
                    pass  # Ignore errors in cleanup

    
    def _log_output(self, message: str):
        """Log output to the progress UI console buffer"""
        self.progress_ui.add_console_output(message)
    
    def _start_immediate_updates(self, node):
        """Start firmware updates immediately for discovered nodes that need updates"""
        try:
            # Get all nodes that need updates from this interface
            nodes_needing_update = node.get_nodes_needing_update()
            
            for node_id, remote_node in nodes_needing_update.items():
                self._log_output(f"{str(remote_node)} starting immediate firmware update")
                
                # Track this node for cleanup
                self.allocated_node_ids.add(remote_node.node_id)
                
                # Start firmware update in a separate thread
                update_thread = threading.Thread(
                    target=self._update_node_firmware, args=(node, remote_node), daemon=True
                )
                update_thread.start()
                
        except Exception as e:
            self._log_output(f"Error starting immediate updates for {node.port}: {e}")

    def _wait_for_operational_and_get_version(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode, timeout: float = 10.0) -> str:
        """Wait for device to be operational and get its firmware version"""
        try:
            self._log_output(f"{str(remote_node)} waiting for operational mode to check firmware version...")
            start_time = time.time()
            current_version = None
            
            def on_node_status(e):
                nonlocal current_version
                if e.transfer.source_node_id == remote_node.node_id:
                    if e.message.mode == e.message.MODE_OPERATIONAL:
                        # Extract version from vendor_specific_status_code or other fields if available
                        # For now, use the software_version that was captured during discovery
                        current_version = remote_node.software_version
            
            # Set up handler to listen for node status
            manager_node.node.add_handler(dronecan.uavcan.protocol.NodeStatus, on_node_status)
            
            # Wait for operational mode and version extraction
            last_log_time = 0
            while time.time() - start_time < timeout:
                elapsed = time.time() - start_time
                
                # Log every 2 seconds
                if elapsed - last_log_time >= 2.0:
                    self._log_output(f"{str(remote_node)} still waiting for operational mode... ({elapsed:.1f}s/{timeout}s)")
                    last_log_time = elapsed
                
                try:
                    manager_node.node.spin(0.1)
                    if current_version:
                        break
                except Exception:
                    time.sleep(0.01)  # Small delay on exception
                    
            # Remove handler
            try:
                manager_node.node.remove_handler(dronecan.uavcan.protocol.NodeStatus, on_node_status)
            except:
                pass
                
            if current_version:
                self._log_output(f"{str(remote_node)} current firmware version: {current_version}")
                return current_version
            else:
                elapsed = time.time() - start_time
                self._log_output(f"{str(remote_node)} timeout after {elapsed:.1f}s waiting for operational mode, continuing anyway")
                return ""
                
        except Exception as e:
            self._log_output(f"{str(remote_node)} error checking firmware version: {e}")
            return ""

    def _update_node_firmware(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode):
        """Update firmware for a specific node"""

        try:
            self._log_output(
                f"{str(remote_node)} starting firmware update"
            )
            self.progress_ui.update_dronecan_progress(str(remote_node), "connecting", 5)

            # Wait for node to enter operational mode before starting firmware update
            self._log_output(f"{str(remote_node)} waiting for operational mode before starting update...")
            operational_version = self._wait_for_operational_and_get_version(manager_node, remote_node)
            
            if operational_version:
                self._log_output(f"{str(remote_node)} operational with firmware version: {operational_version}")
            else:
                self._log_output(f"{str(remote_node)} timeout waiting for operational mode, proceeding with update anyway")

            self._log_output(f"{str(remote_node)} update thread started, preparing firmware update...")
            time.sleep(0.5)  # Give UI time to refresh

            # Use existing firmware_update.py logic
            # This is adapted from the existing firmware_update.py script
            success = self._perform_dronecan_update(manager_node, remote_node)

            if success:
                self.progress_ui.update_dronecan_progress(str(remote_node), "complete", 100)
                self._log_output(
                    f"{str(remote_node)} firmware update completed successfully"
                )
            else:
                self.progress_ui.update_dronecan_progress(str(remote_node), "failed", 0, "Update failed")
                self._log_output(f"{str(remote_node)} firmware update failed")

        except Exception as e:
            error_msg = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
            self.progress_ui.update_dronecan_progress(
                str(remote_node), "failed", 0, error_msg
            )
            self._log_output(
                f"{str(remote_node)} exception during firmware update: {error_msg}"
            )

    def _perform_dronecan_update(
        self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode
    ) -> bool:
        """Perform the actual DroneCAN firmware update"""
        try:
            import base64
            import struct
            import zlib
            import os

            if not manager_node.node:
                self._log_output("Error: Manager node is not running")
                return False

            # Extract target firmware version from filename
            firmware_filename = os.path.basename(remote_node.firmware_path)
            target_version = None
            if firmware_filename.startswith("firmware_") and firmware_filename.endswith(".bin"):
                target_version = firmware_filename[9:-4]  # Remove "firmware_" and ".bin"
                self._log_output(f"Target firmware version: {target_version}")

            # Check current firmware version by waiting for device to be operational
            if target_version:
                current_version = self._wait_for_operational_and_get_version(manager_node, remote_node)
                if current_version == target_version:
                    self._log_output(f"{str(remote_node)} already has target firmware version {target_version}, skipping firmware update")
                    # Skip firmware update but still do bootloader update and restart
                    # Mark as not needing update since it already has correct firmware
                    remote_node.needs_update = False
                    self.progress_ui.update_dronecan_progress(str(remote_node), "bootloader", 90, "Bootloader update")
                    self._start_bootloader_update(manager_node, remote_node)
                    self.progress_ui.update_dronecan_progress(str(remote_node), "restarting", 95, "Restarting node")
                    self._restart_node(manager_node, remote_node)
                    self.progress_ui.update_dronecan_progress(str(remote_node), "complete", 100, "Update complete")
                    return True
                else:
                    self._log_output(f"{str(remote_node)} current version: {current_version}, target: {target_version}, proceeding with update")

            # Read firmware file
            with open(remote_node.firmware_path, "rb") as f:
                firmware_data = f.read()

            firmware_size_bytes = len(firmware_data)
            firmware_size_kb = firmware_size_bytes / 1024
            self._log_output(
                f"Firmware file loaded: {firmware_size_kb:.1f} KB ({firmware_size_bytes} bytes)"
            )

            # Create file hash (similar to existing firmware_update.py)
            file_hash = base64.b64encode(
                struct.pack("<I", zlib.crc32(bytearray(remote_node.firmware_path, "utf-8")))
            )[:7].decode("utf-8")

            self.progress_ui.update_dronecan_progress(str(remote_node), "preparing", 10)

            # Set up file server
            dronecan.app.file_server.FileServer(
                manager_node.node, path_map={file_hash: remote_node.firmware_path}
            )
            self._log_output(f"File server configured with hash: {file_hash}")

            self.progress_ui.update_dronecan_progress(str(remote_node), "preparing", 15, "Restarting to maintenance mode")

            # Send restart requests every 5s for 30s until MAINTENANCE mode
            maintenance_reached = False
            maintenance_wait_start = time.time()
            maintenance_timeout = 30.0  # 30 second timeout
            last_restart_time = 0
            restart_interval = 5.0  # Send restart every 5 seconds
            
            def on_maintenance_status(e):
                nonlocal maintenance_reached
                if e.transfer.source_node_id == remote_node.node_id:
                    if e.message.mode == e.message.MODE_MAINTENANCE:
                        maintenance_reached = True
                        self._log_output(f"{str(remote_node)} entered maintenance mode")
            
            def on_restart_response(e):
                if e is not None and e.response:
                    if e.response.ok:
                        self._log_output(f"{str(remote_node)} restart request acknowledged")
                    else:
                        self._log_output(f"{str(remote_node)} restart request failed")
                else:
                    self._log_output(f"{str(remote_node)} no response to restart request")
            
            # Set up handler for maintenance mode detection
            maintenance_handler = manager_node.node.add_handler(dronecan.uavcan.protocol.NodeStatus, on_maintenance_status)
            
            self._log_output(f"{str(remote_node)} sending restart requests every {restart_interval}s until maintenance mode (timeout: {maintenance_timeout}s)...")
            
            while not maintenance_reached and (time.time() - maintenance_wait_start) < maintenance_timeout:
                current_time = time.time()
                
                # Send restart request every 5 seconds
                if current_time - last_restart_time >= restart_interval:
                    elapsed = current_time - maintenance_wait_start
                    self._log_output(f"{str(remote_node)} sending restart request (elapsed: {elapsed:.1f}s)")
                    
                    # Send restart request
                    restart_request = dronecan.uavcan.protocol.RestartNode.Request()
                    restart_request.magic_number = restart_request.MAGIC_NUMBER
                    manager_node.node.request(restart_request, remote_node.node_id, on_restart_response, priority=30)
                    
                    last_restart_time = current_time
                
                try:
                    manager_node.node.spin(0.1)
                except:
                    pass
            
            # Remove maintenance handler
            try:
                maintenance_handler.remove()
            except:
                pass
            
            if not maintenance_reached:
                self._log_output(f"{str(remote_node)} timeout waiting for maintenance mode after {maintenance_timeout}s, proceeding anyway...")
            else:
                self._log_output(f"{str(remote_node)} ready for firmware update in maintenance mode")
            
            self.progress_ui.update_dronecan_progress(str(remote_node), "uploading", 20)

            # Track update state
            update_started = False
            update_complete = False
            start_time = None
            last_progress = 0
            last_kb_flashed = 0

            self._log_output("Setting up update handlers and starting request...")

            def on_node_status(e):
                nonlocal update_started, update_complete, start_time, last_progress, last_kb_flashed

                if e.transfer.source_node_id == remote_node.node_id:
                    current_mode = e.message.mode

                    if current_mode == e.message.MODE_SOFTWARE_UPDATE:
                        if not update_started:
                            self._log_output(f"{str(remote_node)} entered firmware update mode")
                            update_started = True
                            start_time = time.time()
                            last_progress = 50
                            self.progress_ui.update_dronecan_progress(str(remote_node), "updating", 50)
                        else:
                            # Extract progress from vendor_specific_status_code (kilobytes flashed)
                            kb_flashed = e.message.vendor_specific_status_code

                            if (
                                firmware_size_kb > 0
                                and kb_flashed >= 0
                                and kb_flashed >= last_kb_flashed
                            ):
                                # Only update if progress is moving forward
                                flash_progress = min(kb_flashed / firmware_size_kb, 1.0)
                                progress_percent = 50 + (flash_progress * 39)  # 50% to 89%

                                # Only update progress if it's actually increasing
                                if progress_percent > last_progress:
                                    last_progress = progress_percent
                                    last_kb_flashed = kb_flashed
                                    self._log_output(
                                        f"{str(remote_node)} flashing progress: {kb_flashed:.1f}/"
                                        f"{firmware_size_kb:.1f} KB ({flash_progress*100:.1f}%)"
                                    )
                                    self.progress_ui.update_dronecan_progress(
                                        str(remote_node), "updating", progress_percent
                                    )
                    elif current_mode == e.message.MODE_OPERATIONAL:
                        if update_started and not update_complete:
                            elapsed = time.time() - start_time
                            self._log_output(
                                f"{str(remote_node)} returned to operational mode - firmware update "
                                f"completed in {elapsed:.1f} seconds"
                            )
                            update_complete = True
                            last_progress = 90
                            # Update to bootloader phase instead of complete
                            try:
                                self.progress_ui.update_dronecan_progress(
                                    str(remote_node), "bootloader", 90, "Bootloader update"
                                )
                                remote_node.needs_update = False
                                self._log_output(
                                    f"Firmware update completed for {remote_node}, starting bootloader update"
                                )
                                # Force a display refresh to ensure the progress shows
                                self.progress_ui._refresh_display()
                                
                                # Start bootloader update after firmware is complete
                                self._start_bootloader_update(manager_node, remote_node)
                                
                                # Update to restarting phase
                                self.progress_ui.update_dronecan_progress(
                                    str(remote_node), "restarting", 95, "Restarting node"
                                )
                                
                                # Restart node after bootloader update is complete (regardless of success)
                                self._restart_node(manager_node, remote_node)
                                
                                # Finally update to complete
                                self.progress_ui.update_dronecan_progress(
                                    str(remote_node), "complete", 100, "Update complete"
                                )
                                
                            except Exception as e:
                                self._log_output(f"Error during bootloader/restart phase: {e}")
                    elif update_started and not update_complete:
                        # Device exited SOFTWARE_UPDATE mode but not to OPERATIONAL
                        # Might be rebooting
                        self._log_output(f"{str(remote_node)} mode changed to {current_mode} (rebooting...)")
                        if last_progress < 90:  # Only update if we haven't already shown verifying
                            last_progress = 90
                            self.progress_ui.update_dronecan_progress(str(remote_node), "verifying", 90)

            def on_response(e):
                if e is not None:
                    if e.response.error == e.response.ERROR_OK:
                        self._log_output(f"{str(remote_node)} firmware update request accepted")
                    elif e.response.error == e.response.ERROR_IN_PROGRESS:
                        self._log_output(f"{str(remote_node)} update already in progress")
                    else:
                        self._log_output(f"{str(remote_node)} firmware update response: error {e.response.error}")
                        # Schedule another update request (as per original logic)
                        manager_node.node.defer(4, request_update)
                else:
                    self._log_output(f"{str(remote_node)} no response to firmware update request")

            def request_update():
                if not update_started:
                    self._log_output(f"{str(remote_node)} sending firmware update request...")
                    request = (
                        dronecan.uavcan.protocol.file.BeginFirmwareUpdate.Request(
                            source_node_id=manager_node.node.node_id,
                            image_file_remote_path=dronecan.uavcan.protocol.file.Path(
                                path=file_hash
                            ),
                        )
                    )
                    manager_node.node.request(request, remote_node.node_id, on_response, priority=30)

            # Set up handlers
            manager_node.node.add_handler(dronecan.uavcan.protocol.NodeStatus, on_node_status)

            # Start the update process with periodic requests
            self._log_output(f"{str(remote_node)} starting firmware update request loop...")
            request_update()

            # Schedule periodic requests every 1 second until update starts
            def schedule_periodic_requests():
                if not update_started:
                    request_update()
                    manager_node.node.defer(1.0, schedule_periodic_requests)

            # Start periodic requests
            manager_node.node.defer(1.0, schedule_periodic_requests)

            # Wait for update to complete (with timeout)
            timeout = 1200  # 20 minutes timeout
            start_wait = time.time()

            self._log_output(
                f"Waiting for update to start and complete (timeout: {timeout}s)..."
            )

            while not update_started or not update_complete:
                if time.time() - start_wait > timeout:
                    self._log_output(f"Firmware update timeout after {timeout} seconds")
                    return False

                try:
                    manager_node.node.spin(0.1)
                except dronecan.transport.TransferError:
                    pass

            return True

        except Exception as e:
            self._log_output(f"{str(remote_node)} error during firmware update: {str(e)}")
            return False

    def _start_bootloader_update(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode):
        """Start bootloader update by setting FLASH_BOOTLOADER parameter with retry logic"""
        try:
            self._log_output(f"{str(remote_node)} starting bootloader update...")
            
            # Initialize bootloader state
            remote_node.bootloader_state = "pending"
            
            def on_log_message(e):
                if e.transfer.source_node_id == remote_node.node_id:
                    try:
                        # Handle the log message text (it's a uint8 array, not a string)
                        if hasattr(e.message.text, 'to_bytes'):
                            # If it has to_bytes method, use it
                            log_bytes = e.message.text.to_bytes()
                            log_text = log_bytes.decode('utf-8', errors='ignore')
                        else:
                            # If it's already bytes or a list/array of integers
                            if isinstance(e.message.text, (bytes, bytearray)):
                                log_text = e.message.text.decode('utf-8', errors='ignore')
                            else:
                                # Assume it's an array of integers (uint8 values)
                                log_bytes = bytes(e.message.text)
                                log_text = log_bytes.decode('utf-8', errors='ignore')
                        
                        self._log_output(f"{str(remote_node)} log: {log_text}")
                        
                        # Check for bootloader completion messages
                        if "Bootloader unchanged" in log_text:
                            remote_node.bootloader_state = "unchanged"
                            self._log_output(f"{str(remote_node)} bootloader update completed - bootloader was unchanged")
                        elif "Bootloader Flash ok" in log_text:
                            remote_node.bootloader_state = "updated"
                            self._log_output(f"{str(remote_node)} bootloader update completed - bootloader was successfully updated")
                            
                    except Exception as decode_error:
                        self._log_output(f"{str(remote_node)} error decoding log message: {decode_error}")
            
            # Add handler for log messages from this specific node BEFORE setting parameter
            self._log_output(f"{str(remote_node)} listening for bootloader completion messages...")
            log_handler = manager_node.node.add_handler(dronecan.uavcan.protocol.debug.LogMessage, on_log_message)
            
            def on_param_response(e):
                # Only for logging purposes
                if e is not None and e.response:
                    if e.response.name.decode('utf-8') == "FLASH_BOOTLOADER":
                        if e.response.value.integer_value == 1:
                            self._log_output(f"{str(remote_node)} FLASH_BOOTLOADER parameter set successfully")
                        else:
                            self._log_output(f"{str(remote_node)} FLASH_BOOTLOADER parameter set to {e.response.value.integer_value}")
                    else:
                        self._log_output(f"{str(remote_node)} unexpected parameter response: {e.response.name.decode('utf-8')}")
                else:
                    self._log_output(f"{str(remote_node)} no response to FLASH_BOOTLOADER parameter set request")
            
            def request_bootloader_update():
                if remote_node.bootloader_state == "pending":
                    self._log_output(f"{str(remote_node)} sending FLASH_BOOTLOADER parameter request...")
                    # Create parameter set request
                    param_request = dronecan.uavcan.protocol.param.GetSet.Request()
                    param_request.name = "FLASH_BOOTLOADER".encode('utf-8')
                    param_request.value.integer_value = 1
                    
                    # Send parameter set request
                    manager_node.node.request(param_request, remote_node.node_id, on_param_response, priority=30)
            
            # Start the bootloader update process with periodic requests
            self._log_output(f"{str(remote_node)} starting FLASH_BOOTLOADER parameter request loop...")
            request_bootloader_update()
            
            # Schedule periodic requests every 5 seconds until bootloader completes
            def schedule_periodic_requests():
                if remote_node.bootloader_state == "pending":
                    request_bootloader_update()
                    manager_node.node.defer(5.0, schedule_periodic_requests)
            
            # Start periodic requests
            manager_node.node.defer(5.0, schedule_periodic_requests)

            # Wait for bootloader completion with 30 second timeout
            timeout_start = time.time()
            timeout_duration = 30.0  # 30 second total timeout
            
            self._log_output(f"{str(remote_node)} waiting for bootloader completion (timeout: {timeout_duration}s)...")
            
            while remote_node.bootloader_state == "pending" and (time.time() - timeout_start) < timeout_duration:
                try:
                    manager_node.node.spin(0.1)
                except:
                    pass

            # Remove the handler
            try:
                log_handler.remove()
            except:
                pass
            
            if remote_node.bootloader_state != "pending":
                if remote_node.bootloader_state == "updated":
                    self._log_output(f"{str(remote_node)} bootloader successfully updated")
                elif remote_node.bootloader_state == "unchanged":
                    self._log_output(f"{str(remote_node)} bootloader was already up to date")
                return True  # Bootloader update successful
            else:
                self._log_output(f"{str(remote_node)} timeout waiting for bootloader completion after {timeout_duration}s")
                remote_node.bootloader_state = "timeout"
                return False  # Bootloader update failed/timeout
                
        except Exception as e:
            self._log_output(f"{str(remote_node)} error during bootloader update: {str(e)}")

    def _restart_node(self, manager_node: DroneCANNode, remote_node: RemoteDroneCANNode):
        """Restart the node using RestartNode service"""
        try:
            self._log_output(f"{str(remote_node)} sending restart node request...")
            
            def on_restart_response(e):
                if e is not None and e.response:
                    if e.response.ok:
                        self._log_output(f"{str(remote_node)} restart request acknowledged")
                    else:
                        self._log_output(f"{str(remote_node)} restart request failed")
                else:
                    self._log_output(f"{str(remote_node)} no response to restart request")
            
            # Create restart node request
            restart_request = dronecan.uavcan.protocol.RestartNode.Request()
            restart_request.magic_number = restart_request.MAGIC_NUMBER
            
            # Send restart request
            manager_node.node.request(restart_request, remote_node.node_id, on_restart_response, priority=30)
            
            self._log_output(f"{str(remote_node)} restart request sent")
            
        except Exception as e:
            self._log_output(f"{str(remote_node)} error during node restart: {str(e)}")

