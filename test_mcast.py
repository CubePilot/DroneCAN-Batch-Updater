#!/usr/bin/env python3
"""
Test script to verify DroneCAN functionality with mcast:0 interface.
This simulates the DroneCAN monitoring without requiring real hardware.
"""

import sys
import os
import time
import threading

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import dronecan
from rich.console import Console
from rich.panel import Panel

def test_mcast_connection():
    """Test DroneCAN connection using mcast:0"""
    console = Console()
    console.print(Panel("[bold blue]Testing DroneCAN with mcast:0[/bold blue]", expand=False))
    console.print()
    
    try:
        console.print("[yellow]Creating DroneCAN node with mcast:0...[/yellow]")
        
        # Create node using mcast:0 interface for testing
        node = dronecan.make_node('mcast:0', node_id=100, bitrate=1000000)
        
        console.print("[green]✓ DroneCAN node created successfully[/green]")
        console.print(f"Node ID: {node.node_id}")
        console.print(f"Interface: mcast:0")
        
        # Set up node monitor
        console.print("[yellow]Setting up node monitor...[/yellow]")
        node_monitor = dronecan.app.node_monitor.NodeMonitor(node)
        
        # Set up dynamic node allocation (as per the application)
        console.print("[yellow]Setting up dynamic node allocation server...[/yellow]")
        dynamic_node_allocator = dronecan.app.dynamic_node_id.CentralizedServer(node, node_monitor)
        
        console.print("[green]✓ Dynamic node allocation server started[/green]")
        
        # Test basic node operations
        console.print("[yellow]Testing basic node operations...[/yellow]")
        
        def test_loop():
            """Test loop to verify node spinning works"""
            for i in range(10):
                try:
                    node.spin(timeout=0.1)
                    time.sleep(0.1)
                except Exception as e:
                    console.print(f"[red]Error in node.spin(): {e}[/red]")
                    return False
            return True
        
        # Run test in separate thread
        test_result = [False]
        def run_test():
            test_result[0] = test_loop()
        
        test_thread = threading.Thread(target=run_test, daemon=True)
        test_thread.start()
        test_thread.join(timeout=5)
        
        if test_result[0]:
            console.print("[green]✓ Node operations working correctly[/green]")
        else:
            console.print("[red]✗ Node operations failed[/red]")
            return False
            
        # Test GetNodeInfo request mechanism
        console.print("[yellow]Testing GetNodeInfo request capability...[/yellow]")
        
        def on_node_info_response(response):
            console.print(f"[blue]GetNodeInfo response received from node {response.transfer.source_node_id}[/blue]")
        
        # Set up handler for GetNodeInfo responses
        node.add_handler(dronecan.uavcan.protocol.GetNodeInfo.Response, on_node_info_response)
        
        console.print("[green]✓ GetNodeInfo handler registered[/green]")
        
        # Test file server setup (needed for firmware updates)
        console.print("[yellow]Testing file server setup...[/yellow]")
        
        test_firmware_path = "/tmp/test_firmware.bin"
        with open(test_firmware_path, 'wb') as f:
            f.write(b'test firmware data')
        
        file_server = dronecan.app.file_server.FileServer(
            node, 
            path_map={'test': test_firmware_path}
        )
        
        console.print("[green]✓ File server configured[/green]")
        
        # Clean up test file
        os.remove(test_firmware_path)
        
        # Clean up
        console.print("[yellow]Cleaning up...[/yellow]")
        node.close()
        console.print("[green]✓ Node closed successfully[/green]")
        
        console.print()
        console.print("[bold green]mcast:0 testing completed successfully![/bold green]")
        console.print()
        console.print("[cyan]The system is ready for Here4 firmware updates using mcast:0 for testing.[/cyan]")
        
        return True
        
    except Exception as e:
        console.print(f"[red]Error during mcast:0 testing: {e}[/red]")
        return False

if __name__ == "__main__":
    success = test_mcast_connection()
    sys.exit(0 if success else 1)