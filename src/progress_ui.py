#!/usr/bin/env python3

import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table


@dataclass
class DeviceStatus:
    name: str
    port: str
    device_type: str
    status: str  # 'queued', 'connecting', 'erasing', 'uploading', 'verifying', 'complete', 'failed'
    progress: float = 0.0
    error_msg: Optional[str] = None
    interface: Optional[str] = None  # For DroneCAN devices, track which interface they're on


class ProgressUI:
    def __init__(self, console: Console):
        self.console = console
        self.cube_devices: Dict[str, DeviceStatus] = {}
        self.dronecan_devices: Dict[str, DeviceStatus] = {}
        self.active_interfaces: Dict[str, str] = {}  # interface_name -> status
        self.lock = threading.Lock()
        self.console_buffer: List[str] = []
        self.max_buffer_lines = 100
        self._last_refresh_time = 0.0
        self._refresh_throttle = 0.1  # Minimum 100ms between refreshes
        self._display_active = False  # Always track display state

    def add_cube_device(self, device_id: str, name: str, port: str, device_type: str):
        with self.lock:
            self.cube_devices[device_id] = DeviceStatus(
                name=name, port=port, device_type=device_type, status="queued"
            )

    def add_dronecan_device(self, device_id: str, name: str, node_id: str, device_type: str, interface: str = None, status: str = "queued"):
        with self.lock:
            # Only add if device doesn't already exist to avoid resetting status
            if device_id not in self.dronecan_devices:
                self.dronecan_devices[device_id] = DeviceStatus(
                    name=name, port=node_id, device_type=device_type, status=status, interface=interface
                )

    def remove_dronecan_device(self, device_id: str):
        """Remove a DroneCAN device from tracking"""
        with self.lock:
            if device_id in self.dronecan_devices:
                del self.dronecan_devices[device_id]

        # Always refresh display when removing a device
        if self._display_active:
            self._refresh_display()

    def register_interface(self, interface_name: str, status: str = "Monitoring"):
        """Register an active interface for monitoring"""
        with self.lock:
            self.active_interfaces[interface_name] = status

    def update_interface_status(self, interface_name: str, status: str):
        """Update the status of an active interface"""
        with self.lock:
            if interface_name in self.active_interfaces:
                self.active_interfaces[interface_name] = status

        # Refresh display when interface status changes
        if self._display_active:
            self._refresh_display()

    def add_console_output(self, line: str):
        """Add a line to the console buffer"""
        if line.strip():  # Only add non-empty lines
            with self.lock:
                self.console_buffer.append(line.strip())
                # Keep buffer size manageable
                if len(self.console_buffer) > self.max_buffer_lines:
                    self.console_buffer = self.console_buffer[-self.max_buffer_lines :]

            # Refresh outside of the lock to avoid deadlock
            self._refresh_display()

    def update_cube_progress(
        self,
        device_id: str,
        status: str,
        progress: float = 0.0,
        error_msg: Optional[str] = None,
    ):
        with self.lock:
            if device_id in self.cube_devices:
                self.cube_devices[device_id].status = status
                self.cube_devices[device_id].progress = progress
                self.cube_devices[device_id].error_msg = error_msg

        # Refresh outside of the lock to avoid deadlock  
        self._refresh_display()


    def start_progress_display(self):
        """Initialize the unified progress display for both Cube and DroneCAN devices"""
        # Start the unified display system
        self._display_active = True
        self._render_unified_display()

    def update_dronecan_progress(
        self,
        device_id: str,
        status: str,
        progress: float = 0.0,
        error_msg: Optional[str] = None,
    ):
        with self.lock:
            if device_id in self.dronecan_devices:
                self.dronecan_devices[device_id].status = status
                self.dronecan_devices[device_id].progress = progress
                self.dronecan_devices[device_id].error_msg = error_msg

        # Refresh the unified display
        self._refresh_display()

    def _refresh_display(self):
        """Manually refresh the unified display with throttling"""
        if not self._display_active:
            return

        current_time = time.time()
        if current_time - self._last_refresh_time < self._refresh_throttle:
            return  # Skip refresh if too recent

        self._last_refresh_time = current_time
        self._render_unified_display()

    def _render_unified_display(self):
        """Render unified display for both Cube and DroneCAN devices"""
        if not self._display_active:
            return

        try:
            # Get terminal dimensions
            terminal_height = self.console.size.height
            terminal_width = self.console.size.width

            # Calculate total device count for layout
            total_devices = len(self.cube_devices) + len(self.dronecan_devices)
            device_tree_lines = max(1, total_devices + 4) if total_devices > 0 else 1
            progress_panel_height = device_tree_lines + 4

            # Reserve space for progress panel and margins
            available_console_lines = max(3, terminal_height - progress_panel_height - 4)

            # Get snapshot of current state
            with self.lock:
                console_lines = (
                    self.console_buffer[-available_console_lines:] if self.console_buffer else []
                )
                cube_devices_copy = dict(self.cube_devices)
                dronecan_devices_copy = dict(self.dronecan_devices)

            # Clear screen and move to top
            self.console.clear()

            # Display console output section
            if console_lines:
                max_content_width = max(40, terminal_width - 8)
                truncated_lines = []
                for line in console_lines:
                    if len(line) > max_content_width:
                        truncated_lines.append(line[:max_content_width - 3] + "...")
                    else:
                        truncated_lines.append(line)

                console_content = "\n".join(truncated_lines)
                console_panel = Panel(
                    console_content,
                    title="[bold green]Update Console[/bold green]",
                    title_align="left",
                    width=min(terminal_width, 120),
                )
                self.console.print(console_panel)
                self.console.print()

            # Create unified progress section
            if not cube_devices_copy and not dronecan_devices_copy:
                progress_panel = Panel(
                    "[dim]No devices[/dim]",
                    title="[bold cyan]Firmware Update Progress[/bold cyan]",
                    width=min(terminal_width, 120),
                )
            else:
                # Create simplified device table - only Device and Progress
                table = Table(show_header=True, header_style="bold magenta")
                table.add_column("Device", style="cyan", width=30)
                table.add_column("Progress", style="white", width=40)

                # Add Cube devices
                for device_id, device in cube_devices_copy.items():
                    progress_bar = self._create_progress_bar(device.progress, device.status)
                    device_name = f"{device.name} ({device.port})" if device.name else device.port
                    table.add_row(device_name, progress_bar)

                # Add DroneCAN devices
                for device_id, device in dronecan_devices_copy.items():
                    progress_bar = self._create_progress_bar(device.progress, device.status)
                    device_name = f"{device.name} [Node {device.port}]" if device.name else f"Node {device.port}"
                    if device.interface:
                        device_name += f" ({device.interface})"
                    table.add_row(device_name, progress_bar)

                progress_panel = Panel(
                    table,
                    title="[bold cyan]Firmware Update Progress[/bold cyan]",
                    width=min(terminal_width, 120),
                )

            self.console.print(progress_panel)

        except Exception:
            # Fallback if rendering fails
            pass

    def _create_progress_bar(self, progress: float, status: str) -> str:
        """Create a visual progress bar"""
        if status == "failed":
            return "[red]████████████████████[/red] Failed"
        elif status == "complete":
            return "[green]████████████████████[/green] 100% Complete ✓"
        elif progress > 0:
            filled = int(progress / 5)  # 20 chars total, so each char = 5%
            empty = 20 - filled
            bar = "[cyan]" + "█" * filled + "[/cyan]" + "░" * empty
            return f"{bar} {progress:.0f}% {status.title()}"
        else:
            return "[dim]░░░░░░░░░░░░░░░░░░░░[/dim] 0% Queued"

    def _create_device_tree(self, devices: Dict[str, DeviceStatus], title: str) -> Table:
        """Create a table showing device status"""
        table = Table(show_header=False, box=None, pad_edge=False)
        table.add_column("Device", style="dim")
        table.add_column("Progress", min_width=40)

        # For DroneCAN devices, show ALL active interfaces
        if title == "DroneCAN Devices":
            # Show all active interfaces first
            with self.lock:
                active_interfaces = dict(self.active_interfaces)
            
            if not active_interfaces and not devices:
                table.add_row("  No interfaces", "[dim]None monitoring[/dim]")
                return table

            # Group devices by interface
            device_by_interface = {}
            for device in devices.values():
                interface = device.interface or "Unknown Interface"
                if interface not in device_by_interface:
                    device_by_interface[interface] = []
                device_by_interface[interface].append(device)

            # Show each active interface
            for interface_name, status in active_interfaces.items():
                interface_devices = device_by_interface.get(interface_name, [])
                device_count = len(interface_devices)
                
                # Interface header with status
                if device_count > 0:
                    status_text = f"{status} ({device_count} device{'s' if device_count != 1 else ''})"
                else:
                    status_text = f"{status} (0 devices)"
                
                table.add_row(f"[bold cyan]📡 {interface_name}[/bold cyan]", f"[dim]{status_text}[/dim]")
                
                # Show devices under this interface
                for device in interface_devices:
                    device_name = f"  └─ {device.port} ({device.name})" if device.name else f"  └─ {device.port}"
                    progress_bar = self._create_progress_bar(device.progress, device.status)

                    if device.error_msg:
                        device_name += f" [red]({device.error_msg})[/red]"

                    table.add_row(device_name, progress_bar)
        else:
            # Group by device type for Cube devices or fallback
            if not devices:
                table.add_row("  No devices", "[dim]None detected[/dim]")
                return table
                
            device_types = {}
            for device in devices.values():
                if device.device_type not in device_types:
                    device_types[device.device_type] = []
                device_types[device.device_type].append(device)

            for device_type, type_devices in device_types.items():
                for i, device in enumerate(type_devices):
                    device_name = f"{device.port} ({device.name})" if device.name else device.port
                    progress_bar = self._create_progress_bar(device.progress, device.status)

                    if device.error_msg:
                        device_name += f" [red]({device.error_msg})[/red]"

                    table.add_row(device_name, progress_bar)

        return table

    def display_cube_progress(self):
        """Display current cube update progress"""
        with self.lock:
            if not self.cube_devices:
                return

            table = self._create_device_tree(self.cube_devices, "Cube Devices")
            self.console.print()
            self.console.print(
                Panel(
                    table,
                    title="[bold yellow]Cube Firmware Update Progress[/bold yellow]",
                )
            )

    def display_dronecan_progress(self):
        """Display current DroneCAN update progress"""
        with self.lock:
            table = self._create_device_tree(self.dronecan_devices, "DroneCAN Devices")
            return Panel(table, title="[bold cyan]DroneCAN Devices[/bold cyan]")


    def start_cube_live_display(self):
        """Start live updating display for Cube firmware updates with console output above"""
        # Instead of using Rich Live, use a simple approach with manual updates
        self._display_active = True
        self._render_display()


    def _render_dronecan_display(self):
        """Render the DroneCAN display state with console output above progress"""
        if not self._display_active:
            return

        try:
            # Get terminal dimensions
            terminal_height = self.console.size.height
            terminal_width = self.console.size.width

            # Calculate device tree height for progress panel
            device_count = len(self.dronecan_devices)
            device_tree_lines = (
                max(1, device_count + 2) if device_count > 0 else 1
            )  # +2 for headers and spacing
            progress_panel_height = device_tree_lines + 4  # +4 for panel borders and title

            # Reserve space for progress panel and some margin
            available_console_lines = max(
                3, terminal_height - progress_panel_height - 4
            )  # -4 for spacing and margins

            # Get a snapshot of the current state
            with self.lock:
                console_lines = (
                    self.console_buffer[-available_console_lines:] if self.console_buffer else []
                )
                dronecan_devices_copy = dict(self.dronecan_devices)

            # Clear screen and move to top
            self.console.clear()

            # Display console output section (limit content width)
            if console_lines:
                # Truncate long lines to fit terminal width
                max_content_width = max(40, terminal_width - 8)  # Leave 8 chars for panel borders
                truncated_lines = []
                for line in console_lines:
                    if len(line) > max_content_width:
                        truncated_lines.append(line[: max_content_width - 3] + "...")
                    else:
                        truncated_lines.append(line)

                console_content = "\n".join(truncated_lines)
                console_panel = Panel(
                    console_content,
                    title="[bold green]DroneCAN Update Console[/bold green]",
                    title_align="left",
                    width=min(terminal_width, 120),  # Cap width to prevent overflow
                )
                self.console.print(console_panel)
                self.console.print()

            # Create progress section
            if not dronecan_devices_copy:
                progress_panel = Panel(
                    "[dim]No DroneCAN devices[/dim]",
                    title="[bold cyan]DroneCAN Firmware Update Progress[/bold cyan]",
                    width=min(terminal_width, 120),
                )
            else:
                # Use the interface-aware device tree creation
                table = self._create_device_tree(dronecan_devices_copy, "DroneCAN Devices")

                progress_panel = Panel(
                    table,
                    title="[bold cyan]DroneCAN Firmware Update Progress[/bold cyan]",
                    width=min(terminal_width, 120),
                )

            self.console.print(progress_panel)

        except Exception:
            # Fallback if rendering fails
            pass

    def _render_display(self):
        """Render the current display state"""
        if not self._display_active:
            return

        try:
            # Calculate console buffer size based on terminal height
            terminal_height = self.console.size.height
            # Reserve space for progress panel (estimated 6-8 lines) and some margin
            progress_panel_lines = max(
                6, len(self.cube_devices) * 2 + 4
            )  # Estimate progress panel height
            available_console_lines = max(
                5, terminal_height - progress_panel_lines - 2
            )  # Leave 2 lines margin

            # Get a snapshot of the current state
            with self.lock:
                console_lines = (
                    self.console_buffer[-available_console_lines:] if self.console_buffer else []
                )
                cube_devices_copy = dict(self.cube_devices)

            # Create progress section
            if not cube_devices_copy:
                progress_panel = Panel(
                    "[dim]No cube devices[/dim]",
                    title="[bold yellow]Cube Firmware Update Progress[/bold yellow]",
                )
            else:
                # Create device tree from the snapshot
                table = Table(show_header=False, box=None, pad_edge=False)
                table.add_column("Device", style="dim")
                table.add_column("Progress", min_width=40)

                # Group by device type
                device_types = {}
                for device in cube_devices_copy.values():
                    if device.device_type not in device_types:
                        device_types[device.device_type] = []
                    device_types[device.device_type].append(device)

                for device_type, type_devices in device_types.items():
                    for i, device in enumerate(type_devices):
                        device_name = (
                            f"{device.port} ({device.name})" if device.name else device.port
                        )
                        progress_bar = self._create_progress_bar(device.progress, device.status)

                        if device.error_msg:
                            device_name += f" [red]({device.error_msg})[/red]"

                        table.add_row(device_name, progress_bar)

                progress_panel = Panel(
                    table,
                    title="[bold yellow]Cube Firmware Update Progress[/bold yellow]",
                )

            # Clear screen and move cursor to top
            self.console.clear()

            # Print console output section if we have any
            if console_lines:
                console_text = "\n".join(console_lines)
                console_panel = Panel(console_text, title="[bold blue]Console Output[/bold blue]")
                self.console.print(console_panel)
                self.console.print()

            # Print progress section
            self.console.print(progress_panel)

        except Exception:
            # If rendering fails, just skip this update
            pass


    def update_dronecan_status(self):
        """Refresh the unified status display"""
        # Manual refresh for unified progress display
        self._refresh_display()

    def print_final_summary(self):
        """Print final summary of all operations"""
        with self.lock:
            total_cubes = len(self.cube_devices)
            successful_cubes = sum(1 for d in self.cube_devices.values() if d.status == "complete")
            failed_cubes = total_cubes - successful_cubes

            total_dronecan = len(self.dronecan_devices)
            successful_dronecan = sum(
                1 for d in self.dronecan_devices.values() if d.status == "complete"
            )
            failed_dronecan = total_dronecan - successful_dronecan

            summary = Table(show_header=True, box=None)
            summary.add_column("Device Type", style="bold")
            summary.add_column("Total", justify="center")
            summary.add_column("Successful", justify="center", style="green")
            summary.add_column("Failed", justify="center", style="red")

            summary.add_row("Cubes", str(total_cubes), str(successful_cubes), str(failed_cubes))
            summary.add_row(
                "DroneCAN",
                str(total_dronecan),
                str(successful_dronecan),
                str(failed_dronecan),
            )

            self.console.print()
            self.console.print(Panel(summary, title="[bold]Update Summary[/bold]"))
