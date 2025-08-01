# DroneCAN Batch Firmware Updater

A streamlined, interactive batch firmware update tool for CubeOrange/CubeOrangePlus autopilots and DroneCAN peripheral devices.

## Features

- **Two-Phase Operation**: 
  - Phase A: One-time Cube device detection & update
  - Phase B: Continuous DroneCAN device monitoring & auto-update
- **Robust Device Detection**: Multi-attempt retry logic handles USB re-enumeration and bootloader transitions
- **Multiple Device Support**: Parallel detection and updating of multiple Cube devices
- **Minimal User Interaction**: Single confirmation prompt then fully automated
- **Real-time Progress Display**: Grouped progress bars by device type
- **Cross-platform**: Single binary for Windows, macOS, and Linux with platform-specific optimizations
- **Dynamic Node Allocation**: Built-in DNA server for DroneCAN devices

## Quick Start

### 1. Setup Environment

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Prepare Firmware

Create the firmware directory structure:

```
firmware/
├── CubeOrange.apj                    # Cube firmware files
├── CubePilot-CubeOrangePlus.apj
├── com.cubepilot.gps/
│   └── firmware.bin
├── com.cubepilot.esc/
│   └── firmware.bin
└── com.cubepilot.compass/
    └── firmware.bin
```

### 3. Run the Tool

```bash
# Development mode
python src/main.py

# Or build and run executable
python build.py
./dist/dronecan-batch-updater
```

## Firmware Structure

### Cube Devices
- Place APJ firmware files directly in `firmware/` directory
- Files should be named descriptively (e.g., `CubeOrange.apj`)
- Tool auto-matches firmware based on board ID

### DroneCAN Devices  
- Create subdirectories named after device identifier from GetNodeInfo
- Format: `firmware/com.cubepilot.{device_name}/firmware.bin`
- Device name extracted from GetNodeInfo response
- Tool auto-detects and updates when devices appear

## Workflow

1. **Startup**: Tool scans for connected Cube devices
2. **Version Check**: Compares current firmware vs available firmware  
3. **User Confirmation**: Single prompt for batch Cube updates
4. **Cube Updates**: Sequential update of all Cube devices with progress display
5. **DroneCAN Mode**: Starts DNA server and continuous monitoring
6. **Auto-Updates**: Automatically updates DroneCAN devices as they connect

## Building Executables

```bash
# Build single executable for current platform
python build.py

# Clean build artifacts
python build.py clean
```

Executables are created in `dist/` directory.

## Configuration

Default settings in `src/dronecan_monitor.py`:
- CAN Port: `/dev/ttyACM0`
- Node ID: 100
- Bitrate: 1000000

Modify these values as needed for your setup.

## Progress Display

### Phase A - Cube Updates
```
CubeOrange Devices:
├── /dev/ttyACM0 [████████████████████] 100% Complete ✓
├── /dev/ttyACM1 [████████████░░░░░░░░] 65% Uploading
└── /dev/ttyACM2 [░░░░░░░░░░░░░░░░░░░░] 0% Queued
```

### Phase B - DroneCAN Monitoring
```
DroneCAN Devices:
├── Node 42 (com.cubepilot.gps) [████████████████████] 100% Complete ✓
├── Node 43 (com.cubepilot.esc) [████████░░░░░░░░░░░░] 40% Uploading...
└── Node 44 (com.cubepilot.compass) [░░░░░░░░░░░░░░░░░░░░] 0% Detected, updating...
```

## Platform-Specific Notes

### Linux
- **USB Device Detection**: The tool uses robust retry logic to handle USB re-enumeration during bootloader transitions
- **Multiple Devices**: Supports detection and parallel updating of multiple Cube devices
- **Permissions**: Ensure user is in `dialout` group for serial port access:
  ```bash
  sudo usermod -a -G dialout $USER
  newgrp dialout
  ```

### Windows
- **COM Port Scanning**: Automatically scans COM1-COM255 for devices
- **USB Drivers**: Ensure proper USB drivers are installed for Cube devices

### macOS
- **USB Interface**: Uses `/dev/tty.usbmodem*` pattern for device detection
- **Security**: May require approval for USB device access

## Troubleshooting

### Common Issues

1. **No Cube devices detected**
   - Check USB connections and try different ports
   - Verify device is in bootloader mode (rapid LED blinking)
   - On Linux: Check user permissions with `groups` command
   - Try unplugging and reconnecting USB cable

2. **Linux-specific detection issues**
   - Tool automatically retries detection with proper USB re-enumeration handling
   - Multiple USB interfaces (`-if00`, `-if02`) are handled automatically
   - Bootloader transitions are managed with appropriate delays

3. **DroneCAN devices not appearing**
   - Verify CAN bus connections and termination
   - Check CAN port configuration in source code
   - Ensure devices are powered and operational
   - Use `mcast:0` for testing with single devices

4. **Firmware not found**
   - Check firmware directory structure matches expected format
   - Verify APJ file board IDs match detected devices
   - Ensure GetNodeInfo returns correct device identifier

### Debug Mode

Uncomment DEBUG_PRINT statements in source files for detailed logging:
```python
print(f"[DEBUG] Message here")
```

## Dependencies

- `dronecan>=1.0.0` - DroneCAN protocol support
- `pymavlink>=2.4.0` - MAVLink communication
- `pyserial>=3.5` - Serial port communication  
- `rich>=13.0.0` - Enhanced terminal UI
- `pyinstaller>=5.0.0` - Binary building
- `colorama>=0.4.0` - Cross-platform colors
- `click>=8.0.0` - CLI framework

## License

This project integrates existing PX4/ArduPilot uploader code which is licensed under BSD-3-Clause.