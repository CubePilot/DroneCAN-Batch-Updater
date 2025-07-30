#!/usr/bin/env python3

import re
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

import dronecan


class RemoteDroneCANNode:
    """Represents a remote DroneCAN device discovered on the network"""
    def __init__(self, node_id: int, device_name: str, interface: str, bus_number: int):
        self.node_id = node_id
        self.device_name = device_name
        self.interface = interface
        self.bus_number = bus_number
        self.software_version: Optional[str] = None
        self.hardware_version: Optional[str] = None
        self.unique_id: Optional[bytes] = None  # Hardware unique ID for tracking across node_id changes
        self.firmware_path: Optional[str] = None
        self.needs_update: bool = False
        self.last_seen: float = 0.0

    def __str__(self) -> str:
        if self.interface and self.bus_number is not None:
            # Extract just the interface name (e.g., "tty.usbmodem11101" from "/dev/tty.usbmodem11101")
            interface_name = self.interface.split('/')[-1] if '/' in self.interface else self.interface
            return f"{interface_name}-CAN{self.bus_number}-{self.node_id}"
        else:
            return f"-CAN?-{self.node_id}"

    def __repr__(self) -> str:
        return self.__str__()


class DroneCANNode:

    def __init__(
        self,
        port: str,
        bus_number: int,
        node_id: int = 127,
        bitrate: int = 1000000,
        progress_ui=None,
        firmware_dir: Optional[Path] = None,
    ):
        """
        Create a DroneCAN node with threading support

        Args:
            port: Serial port path (e.g., '/dev/tty.usbmodem11301')
            bus_number: CAN bus number (1 or 2)
            node_id: Node ID (default 127)
            bitrate: CAN bitrate (default 1000000)
        """
        self.port = port
        self.bus_number = bus_number
        self.node_id = node_id
        self.bitrate = bitrate

        # Node and threading
        self.node: Optional[dronecan.node.Node] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

        # Dynamic node allocator
        self.dynamic_node_allocator = None

        # Connection string
        self.mavlink_connection = f"mavcan:{self.port}"

        # NodeManager functionality
        self.progress_ui = progress_ui
        self.firmware_dir = firmware_dir or Path("firmware")
        self.discovered_nodes: Dict[int, RemoteDroneCANNode] = {}
        self.lock = threading.Lock()
        self.new_node_callback: Optional[Callable] = None
        self.node_removed_callback: Optional[Callable] = None
        self.processed_nodes = set()  # Track nodes processed on this specific interface

    def start(self) -> bool:
        """
        Start the DroneCAN node and its threading

        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            # Create the DroneCAN node
            self.node = dronecan.make_node(
                self.mavlink_connection,
                node_id=self.node_id,
                bitrate=self.bitrate,
                bus_number=self.bus_number,
            )

            # Set up dynamic node allocator (skip NodeMonitor to avoid library bugs)
            try:
                self.dynamic_node_allocator = dronecan.app.dynamic_node_id.CentralizedServer(
                    self.node, None
                )
            except Exception as e:
                print(
                    f"DEBUG: Dynamic node allocator failed for {self.port} "
                    f"bus {self.bus_number}: {e}"
                )
                self.dynamic_node_allocator = None

            # Set up node status handler for device discovery
            self.node.add_handler(
                dronecan.uavcan.protocol.NodeStatus, self._handle_node_status
            )

            # Start the spinning thread
            self.running = True
            self.thread = threading.Thread(target=self._spin_loop, daemon=True)
            self.thread.start()

            return True

        except Exception as e:
            print(f"DEBUG: Failed to start node on {self.port} bus {self.bus_number}: {e}")
            return False

    def stop(self):
        """Stop the node and clean up resources"""
        self.running = False

        # Wait for thread to finish
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

        # Close the node
        if self.node:
            try:
                self.node.close()
            except Exception as e:
                print(f"DEBUG: Error closing node on {self.port}: {e}")

        self.node = None
        self.thread = None
        self.dynamic_node_allocator = None

    def _spin_loop(self):
        """Main spinning loop running in separate thread"""
        while self.running and self.node:
            try:
                self.node.spin(timeout=0.1)
            except Exception as e:
                # Handle queue.Full and other exceptions gracefully
                if "queue.Full" in str(e) or "Full" in str(e):
                    time.sleep(0.1)  # Slow down if queue is full
                else:
                    # For other exceptions, continue but add small delay
                    time.sleep(0.01)

    def _handle_node_status(self, event):
        """Handle NodeStatus messages to discover devices and manage nodes"""
        try:
            node_id = event.transfer.source_node_id
            # Skip known Cube/autopilot nodes (typically node 1-20) and our own node
            if node_id <= 20 or node_id == self.node_id:
                return

            # Always request node info for proper device tracking
            request = dronecan.uavcan.protocol.GetNodeInfo.Request()
            self.node.request(request, node_id, self._handle_node_info_response)
        except Exception as e:
            print(f"DEBUG: Exception in _handle_node_status: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")

    def discover_devices(self, timeout: float = 2.0) -> List[int]:
        """
        Discover devices on this interface for a specified time

        Args:
            timeout: Discovery timeout in seconds

        Returns:
            List of discovered device node IDs
        """
        if not self.running or not self.node:
            return []

        # Wait for the specified timeout
        time.sleep(timeout)

        # Return list of discovered node IDs
        with self.lock:
            return list(self.discovered_nodes.keys())

    def get_info(self) -> dict:
        """Get information about this node"""
        with self.lock:
            discovered_devices = list(self.discovered_nodes.keys())
        return {
            "port": self.port,
            "bus_number": self.bus_number,
            "node_id": self.node_id,
            "mavlink_connection": self.mavlink_connection,
            "running": self.running,
            "discovered_devices": discovered_devices,
            "device_count": len(discovered_devices),
        }

    def __str__(self) -> str:
        with self.lock:
            device_count = len(self.discovered_nodes)
        return (
            f"DroneCANNode({self.port}, bus={self.bus_number}, "
            f"devices={device_count})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    # NodeManager functionality methods
    
    def _log_to_console(self, message: str):
        """Log message to console section"""
        if self.progress_ui:
            self.progress_ui.add_console_output(message)

    def start_monitoring(
        self,
        new_node_callback: Optional[Callable] = None,
        node_removed_callback: Optional[Callable] = None,
    ):
        """Start monitoring for new nodes"""
        self.new_node_callback = new_node_callback
        self.node_removed_callback = node_removed_callback

        # Set up periodic scanning
        self._start_periodic_scanning()

    def stop_monitoring(self):
        """Stop node monitoring"""
        # Handlers are automatically cleaned up when node closes
        pass

    def _start_periodic_scanning(self):
        """Start periodic scanning and cleanup for nodes"""

        def scan_loop():
            while True:
                try:
                    # Clean up stale nodes every 5 seconds
                    self._cleanup_stale_nodes()
                    time.sleep(5)

                except Exception:
                    time.sleep(5)

        thread = threading.Thread(target=scan_loop, daemon=True)
        thread.start()

    def _cleanup_stale_nodes(self):
        """Remove nodes that haven't been seen for 20+ seconds"""
        current_time = time.time()
        stale_threshold = 20.0  # 20 seconds

        with self.lock:
            stale_nodes = []
            for node_id, node in self.discovered_nodes.items():
                if current_time - node.last_seen > stale_threshold:
                    stale_nodes.append(node_id)

            # Remove stale nodes
            for node_id in stale_nodes:
                remote_node = self.discovered_nodes[node_id]
                self._log_to_console(
                    f"{str(remote_node)} timed out, removing from monitoring"
                )

                # Remove from progress UI
                self.progress_ui.remove_dronecan_device(str(remote_node))

                # Notify callback about node removal
                if self.node_removed_callback:
                    self.node_removed_callback(self, remote_node)

                # Remove from discovered nodes
                del self.discovered_nodes[node_id]


                # Keep the node in processed_nodes to prevent immediate re-processing
                # It will be cleared when the program restarts

    def _handle_node_info_response(self, event):
        """Handle GetNodeInfo response from node.request() callback"""
        try:
            if event is None:
                # Request timed out
                return

            node_id = event.transfer.source_node_id
            node_info = event.response

            # Extract device information
            device_name = self._extract_device_name(node_info)
            if not device_name:
                # Use temporary format since RemoteDroneCANNode not created yet
                interface_name = self.port.split('/')[-1] if '/' in self.port else self.port
                interface_clean = ''.join(c for c in interface_name if c.isprintable() and ord(c) < 128)
                temp_node_id = f"{interface_clean}-CAN{self.bus_number}-{node_id}"
                self._log_to_console(f"{temp_node_id} is not a com.cubepilot device")
                return

            # Create or update node record
            with self.lock:
                # Extract unique_id to check for existing device with different node_id
                unique_id = bytes(node_info.hardware_version.unique_id)
                
                # Check if we already know this device by unique_id (node_id might have changed)
                existing_node = None
                old_node_id = None
                
                # Search for existing node by unique_id
                for existing_id, remote_node in self.discovered_nodes.items():
                    if remote_node.unique_id == unique_id:
                        existing_node = remote_node
                        old_node_id = existing_id
                        break
                
                if existing_node:
                    if old_node_id != node_id:
                        self._log_to_console(f"{str(existing_node)} node_id changed from {old_node_id} to {node_id}")
                        
                        # Update the node_id and move it in discovered_nodes dict
                        existing_node.node_id = node_id
                        existing_node.last_seen = time.time()
                        
                        # Remove old entry and add new one
                        del self.discovered_nodes[old_node_id]
                        self.discovered_nodes[node_id] = existing_node
                        
                        # Update device_id in progress UI
                        old_device_id = f"{existing_node.interface.split('/')[-1]}-CAN{existing_node.bus_number}-{old_node_id}"
                        new_device_id = f"{str(existing_node)}"
                        
                        # Remove old progress entry and add new one
                        self.progress_ui.remove_dronecan_device(old_device_id)
                        interface_name = f"{self.port} CAN{self.bus_number}"
                        if existing_node.needs_update:
                            self._log_to_console(f"{str(existing_node)} requires update")
                        else:
                            self._log_to_console(f"{str(existing_node)} is up to date")
                        self.progress_ui.add_dronecan_device(
                            device_id=new_device_id,
                            name=existing_node.device_name,
                            node_id=f"Node {node_id}",
                            device_type=(
                                existing_node.device_name.split(".")[-1] if "." in existing_node.device_name else existing_node.device_name
                            ),
                            interface=interface_name,
                            status="queued" if existing_node.needs_update else "complete",
                        )
                    else:
                        # Same node_id, just update timestamp
                        existing_node.last_seen = time.time()
                    return
                
                if node_id not in self.discovered_nodes:
                    # Check if this node has already been processed for updates on this interface
                    if node_id in self.processed_nodes:
                        return
                    # Create a new RemoteDroneCANNode instance for the discovered device
                    remote_node = RemoteDroneCANNode(
                        node_id=node_id, 
                        device_name=device_name,
                        interface=self.port,
                        bus_number=self.bus_number
                    )

                    # Log identification now that we have the RemoteDroneCANNode object
                    self._log_to_console(f"{str(remote_node)} identified as {device_name}")

                    # Set device information
                    version_str = f"{node_info.software_version.major}.{node_info.software_version.minor}"
                    
                    # Include VCS commit hash if available
                    vcs_commit = node_info.software_version.vcs_commit
                    if vcs_commit != 0:  # 0 means unknown/unavailable
                        version_str += f".{vcs_commit:x}"  # Convert to hex format
                    
                    remote_node.software_version = version_str
                    remote_node.hardware_version = f"{node_info.hardware_version.major}.{node_info.hardware_version.minor}"
                    remote_node.unique_id = bytes(node_info.hardware_version.unique_id)
                    remote_node.last_seen = time.time()

                    # Find firmware file for this device
                    firmware_path = self._find_firmware_path(device_name)
                    remote_node.firmware_path = firmware_path
                    remote_node.needs_update = firmware_path is not None

                    if firmware_path:
                        self._log_to_console(f"{str(remote_node)} found firmware")
                    else:
                        self._log_to_console(f"{str(remote_node)} no firmware available")
                    self.discovered_nodes[node_id] = remote_node

                    # Add to progress UI with interface information
                    interface_name = f"{self.port} CAN{self.bus_number}"
                    if self.progress_ui:
                        # Set status based on whether firmware update is needed
                        device_status = "queued" if remote_node.needs_update else "complete"
                        self.progress_ui.add_dronecan_device(
                            device_id=str(remote_node),
                            name=device_name,
                            node_id=f"Node {node_id}",
                            device_type=(
                                device_name.split(".")[-1] if "." in device_name else device_name
                            ),
                            interface=interface_name,
                            status=device_status,
                        )

                    # Notify callback about new node (only once)
                    if self.new_node_callback and remote_node.needs_update:
                        self._log_to_console(f"Starting firmware update process for {str(remote_node)}")
                        self.processed_nodes.add(node_id)  # Mark as processed before starting update
                        self.new_node_callback(self, remote_node)
                    elif self.new_node_callback:
                        self._log_to_console(f"Device {str(remote_node)} does not need update")
                        self.processed_nodes.add(node_id)  # Mark as processed even if no update needed

                else:
                    # Update existing node
                    self.discovered_nodes[node_id].last_seen = time.time()

        except Exception as e:
            print(f"DEBUG: Exception in _handle_node_info_response: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")

    def _extract_device_name(self, node_info) -> Optional[str]:
        """Extract device name from GetNodeInfo response"""
        try:
            # The device name should be in the software version or name field
            # Format: com.cubepilot.device_name

            # Try name field first (most common location for Here4)
            if node_info.name:
                name_info = str(node_info.name)
                if "com.cubepilot." in name_info:
                    result = self._parse_device_name(name_info)
                    if result:
                        return result

            # Try software version
            if node_info.software_version:
                version_info = str(node_info.software_version)
                if "com.cubepilot." in version_info:
                    result = self._parse_device_name(version_info)
                    if result:
                        return result

            # Try hardware version
            if node_info.hardware_version:
                hw_info = str(node_info.hardware_version)
                if "com.cubepilot." in hw_info:
                    result = self._parse_device_name(hw_info)
                    if result:
                        return result

        except Exception:
            pass

        return None

    def _parse_device_name(self, text: str) -> Optional[str]:
        """Parse device name from text containing com.cubepilot.device_name"""
        try:
            match = re.search(r"com\.cubepilot\.(\w+)", text)
            if match:
                device_name = f"com.cubepilot.{match.group(1)}"
                return device_name
        except Exception:
            pass
        return None


    def _find_firmware_path(self, device_name: str) -> Optional[str]:
        """Find firmware file path for the given device name"""
        try:
            device_dir = self.firmware_dir / device_name
            
            # First try versioned firmware files (firmware_<version>.bin)
            if device_dir.exists():
                for firmware_file in device_dir.glob("firmware_*.bin"):
                    if firmware_file.is_file():
                        return str(firmware_file)
            
            # Fallback to legacy firmware.bin format
            firmware_file = device_dir / "firmware.bin"
            if firmware_file.exists():
                return str(firmware_file)

        except Exception:
            pass

        return None

    def get_nodes_needing_update(self) -> Dict[int, RemoteDroneCANNode]:
        """Get all nodes that need firmware updates"""
        with self.lock:
            return {
                node_id: node
                for node_id, node in self.discovered_nodes.items()
                if node.needs_update
            }

    def get_all_nodes(self) -> Dict[int, RemoteDroneCANNode]:
        """Get all discovered nodes"""
        with self.lock:
            return self.discovered_nodes.copy()
