# Firmware Directory

This directory contains firmware files for both Cube autopilots and DroneCAN devices.

## Structure

```
firmware/
├── *.apj                           # Cube firmware files (place directly here)
│   ├── CubeOrange.apj
│   └── CubePilot-CubeOrangePlus.apj
│
└── com.cubepilot.{device_name}/    # DroneCAN device firmware
    ├── com.cubepilot.gps/
    │   └── firmware.bin
    ├── com.cubepilot.esc/
    │   └── firmware.bin
    └── com.cubepilot.compass/
        └── firmware.bin
```

## Cube Firmware (APJ Files)

- Place APJ firmware files directly in this directory
- Files can have any descriptive name
- Tool matches firmware based on board ID inside the APJ file
- Supported formats: ArduPilot APJ (JSON with embedded firmware)

## DroneCAN Device Firmware (BIN Files)

- Create subdirectories named after the device identifier
- Device identifier comes from GetNodeInfo response in DroneCAN
- Format: `com.cubepilot.{device_name}`
- Place `firmware.bin` file inside each device directory

### Device Name Detection

The tool extracts device names from DroneCAN GetNodeInfo responses:
- Checks `software_version` field first
- Falls back to `name` field
- Finally checks `hardware_version` field
- Looks for pattern: `com.cubepilot.{device_name}`

### Example Device Names

Common CubePilot device names:
- `com.cubepilot.gps` - GPS modules
- `com.cubepilot.esc` - Electronic Speed Controllers  
- `com.cubepilot.compass` - Compass/magnetometer modules
- `com.cubepilot.airspeed` - Airspeed sensors
- `com.cubepilot.power` - Power modules

## Adding New Firmware

1. **For Cube devices**: Copy APJ file to this directory
2. **For DroneCAN devices**: 
   - Create directory: `com.cubepilot.{device_name}`
   - Copy firmware.bin to that directory
3. Restart the updater tool to detect new firmware