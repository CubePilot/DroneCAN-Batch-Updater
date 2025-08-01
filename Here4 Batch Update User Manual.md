# Here4 Batch Update User Manual
## Using DroneCAN Batch Updater with Multiple Cube Autopilots

### Overview

This manual guides you through updating multiple Here4 GNSS/RTK units using the DroneCAN Batch Firmware Updater tool with multiple CubeOrange/CubeOrangePlus autopilots. The tool provides an automated, two-phase approach that first updates the Cube autopilots, then continuously monitors and updates Here4 units as they connect to the DroneCAN network.

### What You'll Need

#### Hardware Requirements
- **Multiple CubeOrange or CubeOrangePlus autopilots** (one per Here4 unit or group)
- **Here4 GNSS/RTK units** to be updated
- **USB cables** for connecting Cubes to computer
- **CAN cables and splitter board** for DroneCAN network
- **Power supply** for Here4 units (5V recommended)
- **Computer** running Windows, macOS, or Linux

#### Software Requirements
- **dronecan-batch-updater** executable (standalone application)

---

## Phase 1: Initial Setup

### Step 1: Install Software

1. **Download and extract the application**
   - Download the `dronecan-batch-updater` zip file for your platform
   - Extract the zip file to get the executable

2. **Make executable** (Linux/macOS only):
   ```bash
   chmod +x dronecan-batch-updater
   ```

3. **Linux System Setup** (Linux only):
   ```bash
   sudo usermod -a -G dialout $USER
   sudo apt remove modemmanager
   ```

### Step 2: Hardware Connections

1. **Connect Multiple Cubes**
   - Connect each Cube to your computer via USB
   - Use separate USB ports for each Cube OR use a powered USB hub (not unpowered hub)
   - Ensure reliable USB cables
   - Cubes will appear as different serial ports

2. **Set Up DroneCAN Network**
   - Power Here4 units with 5V supply
   - Connect one Cube to CAN network using **CAN2 port** on the Cube (not CAN1)
   - This Cube will serve as the DroneCAN gateway

---

## Phase 2: Running the Update Process

### Step 1: Launch the Updater

```bash
# Run the standalone executable
./dronecan-batch-updater
```

**Note:** The application is completely self-contained. Ignore any slcan errors that may appear in the terminal.

### Step 2: Phase A - Cube Detection and Updates

The tool will automatically scan for and update any connected Cube autopilots first. This phase typically completes quickly if the Cubes already have current firmware.

**Note:** Only Cubes with Here4 units already connected will be added to the monitoring phase.

### Step 3: Phase B - Here4 Detection and Updates

Once the Cubes are ready, the tool automatically enters continuous monitoring mode for Here4 units. Here4 needs to be connected using white/blue cable plug.

<div align="center">
<img src="Here4%20CAN.jpeg" alt="Here4 CAN Connection" width="200">
</div>

**Important:** Always use the white/blue cable connection (shown in green circle) for DroneCAN communication during firmware updates.

Make sure Power connection is not connected to the Here4 from Cube. Here4 needs to be separately powered using a 5V power supply, NOT from Cube.

#### Upper Panel: Update Console
```
╭─ Update Console ──────────────────────────────────────────────────────────────╮
│ usb-Hex_ProfiCNC_CubeOrange_1B002A000E51393239383638-if02-CAN2-124 flashing   │
│ progress: 294.0/35...                                                         │
│ usb-Hex_ProfiCNC_CubeOrange_1B002A000E51393239383638-if02-CAN2-125 flashing   │
│ progress: 334.0/35...                                                         │
╰───────────────────────────────────────────────────────────────────────────────╯
```
This shows real-time detailed update information and flash progress for each device.

#### Lower Panel: Firmware Update Progress
```
╭────────────────────── Firmware Update Progress ───────────────────────── ─╮
│ ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓   │
│ ┃ Device                         ┃ Progress                           ┃   │
│ ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇   │
│ │ com.cubepilot.here4 [Node 125] │ █████████████████░░░ 89% Updating  │   │
│ │ (/dev/serial/by-id/usb-Hex_Pr… │                                    │   │
│ │ CAN2)                          │                                    │   │
│ │ com.cubepilot.here4 [Node 124] │ █████████████████░░░ 87% Updating  │   │
│ │ (/dev/serial/by-id/usb-Hex_Pr… │                                    │   │
│ │ CAN2)                          │                                    │   │
│ └────────────────────────────────┴────────────────────────────────────┘   │
╰───────────────────────────────────────────────────────────────────────────╯
```
This shows a clean progress table with:
- **Device identification**: Here4 units with their CAN node IDs
- **Connection path**: Which Cube/CAN port they're connected through  
- **Progress bars**: Visual percentage and status for each unit
- **Status indicators**: "Updating", "Complete", "Detected", etc.

---

## Phase 3: Managing the Update Process

### Understanding the Interface

**Real-time Updates:**
- **Dual-panel display** provides both detailed logs and summary view
- **Multiple devices update simultaneously** for efficiency  
- **Progress bars update in real-time** showing exact percentages

**Status Indicators:**
- `89% Updating` - Firmware transfer in progress with exact percentage
- `100% Complete` - Update completed successfully
- `Detected` - Device found, update starting
- `Failed` - Update failed
- `Rebooting` - Device restarting after successful update

**Device Information:**
- **Node ID**: CAN network identifier (e.g., Node 124, Node 125)
- **Device Type**: Shows `com.cubepilot.here4` for Here4 units
- **Connection Path**: Shows which Cube and CAN port is used (e.g., CAN2)
- **Serial Identifier**: Abbreviated USB path for troubleshooting (e.g., `/dev/serial/by-id/usb-Hex_Pr…`)

### Adding More Here4 Units

The tool runs continuously in monitoring mode, so you can:

1. **Connect additional Here4 units** to the CAN network at any time
2. **Power them on** - they'll appear automatically in the progress table
3. **Updates start immediately** without user intervention
4. **Watch real-time progress** in both console panels

### Monitoring Multiple Updates

The interface handles multiple simultaneous updates:
- **Each Here4 gets its own progress row** in the table
- **Updates run in parallel** for faster batch processing
- **Automatic node ID assignment** via built-in DNA server

### Completing Updates

When a Here4 update completes:
1. Progress bar reaches **100%**
2. Status changes to **"Complete"** 
3. Device shows **"mode changed to 1 (rebooting)"** in upper console
4. Here4 automatically restarts with new firmware
5. Unit disappears from active update list

### Stopping the Process

- **Ctrl+C** to stop monitoring
- **Wait for current updates to complete** before stopping

---

## Troubleshooting

### Cube Detection Issues

**Problem:** No Cube devices detected
```
No CubeOrange devices found. Please check connections.
```

**Solutions:**
1. **Check USB connections**
   - Try different USB ports
   - Use high-quality USB cables
   - Ensure Cubes are powered

2. **Linux permissions** (if applicable)
   - Check that user permissions were set correctly in Phase 1
   - Try rebooting or logging out and back in
   - Restart terminal session if needed

3. **Manual Cube firmware update**
   - Manually update firmware using CubeOrange.apj or CubeOrangePlus.apj from downloaded zip file
   - Run the software with `--skip-cube-update` flag

### Here4 Detection Issues

**Problem:** Here4 units not appearing in the update interface

**Solutions:**
1. **Check CAN connections**
   - Verify CAN-H and CAN-L wiring is correct
   - Ensure 120Ω terminators at both ends of CAN bus
   - Check for loose connections at CAN connectors

2. **Power supply verification**
   - Here4 requires stable **5V power** (4.5-5.5V range)
   - Check power LED on Here4 units (should be solid)
   - Verify adequate power supply capacity for all units
   - Ensure good ground connections

3. **CAN bus health**
   - Check CAN bus isn't overloaded (too many devices)
   - Verify no conflicting node IDs
   - Test with single Here4 first
   - Use shorter CAN cable runs if possible

4. **Cube CAN port configuration**
   - Tool automatically detects CAN2 port as shown in interface
   - Ensure CAN port is enabled and configured correctly
   - Try different CAN port if available (CAN1 vs CAN2)

### SLCAN Errors flooding the console
**Problem:** Errors dumping into console from SLCAN backend

**Solution:**
* There is no solution to this problem yet. Functionally the units will continue updating, ignore this error, it should go away, or wait for exisiting units to finish flashing and restart the program.

* Reducing the Number of Here4 units connected to Cube might heplp

### Update Failures

**Problem:** Updates fail or get stuck at certain percentages

**Solutions:**
1. **USB/CAN connection issues**
   - Check USB cable quality to Cube
   - Verify stable CAN bus connections
   - Try different USB port on computer
   - Avoid USB hubs if possible

2. **Power stability**
   - Ensure stable **5V supply** to Here4 units
   - Check for voltage drops during update
   - Use adequate power supply capacity
   - Verify clean power (no switching noise)

3. **Firmware compatibility**
   - Firmware is automatically matched to device hardware
   - Latest firmware versions are used automatically

4. **Manual retry for failures**
   - Tool does not automatically retry failed updates
   - If update fails, restart the tool and try again
   - Check hardware connections before retrying

---

## Best Practices for Batch Updates

### Pre-Update Checklist

Before starting a batch update session:

1. **Hardware Verification**
   - ✅ All Here4 units powered with stable **5V**
   - ✅ All Cube autopilots connected via quality USB cables
   - ✅ CAN connections secure and properly wired

2. **Software Preparation**
   - ✅ Downloaded `dronecan-batch-updater` executable
   - ✅ Made executable on Linux/macOS systems

3. **Environment Setup**
   - ✅ Stable power supply for all devices
   - ✅ Clean work area with good cable management
   - ✅ Computer has adequate USB ports available

### Post-Update Verification

After all updates complete:

1. **Verify successful completion**
   - All devices should show "Complete" status
   - Check upper console for any error messages
   - Note final node IDs assigned to each Here4

2. **Functional testing**
   - Use a different Cube updated to stable ArduPilot release for testing
   - Power cycle all Here4 units
   - Verify LED patterns indicate normal operation
   - Test GNSS signal acquisition if possible
   - Confirm devices appear in ground station software

---

## Advanced Tips

### Handling Large Batches

For production-scale updating of many Here4 units, use this efficient 4-station workflow:

#### Station 1: Unpacking
- **Unpack Here4 units**
- **Prepare units** for update station

#### Station 2: Firmware Updates
- **Recommended setup**: Use 3 Cubes with 4 Here4 units connected per Cube per laptop
<div align="center">
<div align="center">
<img src="Here4%20Setup.jpeg" alt="Here4 Setup" width="300">
</div>
</div>

- **Connect Here4 units** to CAN network via Cube autopilots
- **Power with 5V supply** and run `dronecan-batch-updater`
- **Monitor update progress** using the dual-panel interface
- **Verify completion** - units should **breathe blue LED** when update finished
- **Move completed units** to testing station

#### Station 3: Functional Testing
- **Connect to CubeOrangePlus** running latest ArduPilot stable firmware
- **Power via proper 5V supply** 
- **Verify LED pattern** - should display **rainbow pattern** indicating proper operation after initialization. constant **Red breathing** might indicate either a fault with CAN Bus (ensure you are connecting White CAN cable from Here4 not Red).
- **Check Here4 LED pattern** - should show proper rainbow initialization sequence

<div align="center">
<img src="Here4%20CAN.jpeg" alt="Here4 CAN Connection" width="300">
</div>

**Note:** Use the white/blue CAN cable connection (circled in green) for all testing operations, just as during the update process.
- **Move tested units** to packaging station

#### Station 4: Repacking
- **Final visual inspection** of updated units
- **Repack units** into shipping boxes
- **Label with firmware version** and update date
- **Quality control documentation**

**Production Flow Benefits:**
- **Parallel processing** - multiple stations operating simultaneously
- **Quality assurance** at each stage
- **Clear pass/fail indicators** (blue breathing → rainbow pattern)
- **Efficient throughput** for large quantities

**Cable Management:**
- Use quality CAN cables with proper shielding
- Keep CAN bus runs as short as practical
- Avoid parallel runs with power cables
- Use proper strain relief at connectors
