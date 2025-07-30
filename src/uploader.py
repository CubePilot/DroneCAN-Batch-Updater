#!/usr/bin/env python
############################################################################
#
#   Copyright (c) 2012-2017 PX4 Development Team. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in
#    the documentation and/or other materials provided with the
#    distribution.
# 3. Neither the name PX4 nor the names of its contributors may be
#    used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS
# OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED
# AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
############################################################################

#
# Serial firmware uploader for the PX4FMU bootloader
#
# The PX4 firmware file is a JSON-encoded Python object, containing
# metadata fields and a zlib-compressed base64-encoded firmware image.
#
# The uploader uses the following fields from the firmware file:
#
# image
#       The firmware that will be uploaded.
# image_size
#       The size of the firmware in bytes.
# board_id
#       The board for which the firmware is intended.
# board_revision
#       Currently only used for informational purposes.
#

# AP_FLAKE8_CLEAN

import argparse
import array
import base64
import binascii
import json
import os
import platform
import re
import struct
import sys
import time
import zlib
from sys import platform as _platform

import serial

is_WSL = bool("Microsoft" in platform.uname()[2])
is_WSL2 = bool("microsoft-standard-WSL2" in platform.release())

# default list of port names to look for autopilots
default_ports = [
    "/dev/serial/by-id/usb-Ardu*",
    "/dev/serial/by-id/usb-3D*",
    "/dev/serial/by-id/usb-APM*",
    "/dev/serial/by-id/usb-Radio*",
    "/dev/serial/by-id/usb-*_3DR_*",
    "/dev/serial/by-id/usb-Hex_Technology_Limited*",
    "/dev/serial/by-id/usb-Hex_ProfiCNC*",
    "/dev/serial/by-id/usb-Holybro*",
    "/dev/serial/by-id/usb-mRo*",
    "/dev/serial/by-id/usb-modalFC*",
    "/dev/serial/by-id/usb-Auterion*",
    "/dev/serial/by-id/usb-*-BL_*",
    "/dev/serial/by-id/usb-*_BL_*",
    "/dev/serial/by-id/usb-Swift-Flyer*",
    "/dev/serial/by-id/usb-CubePilot*",
    "/dev/serial/by-id/usb-Qiotek*",
    "/dev/tty.usbmodem*",
]

if "cygwin" in _platform or is_WSL:
    default_ports += ["/dev/ttyS*"]

if "win32" in _platform:
    for com_port in range(1, 255):
        default_ports += ["COM" + str(com_port)]

# Detect python version
if sys.version_info[0] < 3:
    runningPython3 = False
else:
    runningPython3 = True

# dictionary of bootloader {boardID: (firmware boardID, boardname), ...}
# designating firmware builds compatible with multiple boardIDs
compatible_IDs = {33: (9, "AUAVX2.1")}


# CRC equivalent to crc_crc32() in AP_Math/crc.cpp
crctab = array.array(
    "I",
    [
        0x00000000,
        0x77073096,
        0xEE0E612C,
        0x990951BA,
        0x076DC419,
        0x706AF48F,
        0xE963A535,
        0x9E6495A3,
        0x0EDB8832,
        0x79DCB8A4,
        0xE0D5E91E,
        0x97D2D988,
        0x09B64C2B,
        0x7EB17CBD,
        0xE7B82D07,
        0x90BF1D91,
        0x1DB71064,
        0x6AB020F2,
        0xF3B97148,
        0x84BE41DE,
        0x1ADAD47D,
        0x6DDDE4EB,
        0xF4D4B551,
        0x83D385C7,
        0x136C9856,
        0x646BA8C0,
        0xFD62F97A,
        0x8A65C9EC,
        0x14015C4F,
        0x63066CD9,
        0xFA0F3D63,
        0x8D080DF5,
        0x3B6E20C8,
        0x4C69105E,
        0xD56041E4,
        0xA2677172,
        0x3C03E4D1,
        0x4B04D447,
        0xD20D85FD,
        0xA50AB56B,
        0x35B5A8FA,
        0x42B2986C,
        0xDBBBC9D6,
        0xACBCF940,
        0x32D86CE3,
        0x45DF5C75,
        0xDCD60DCF,
        0xABD13D59,
        0x26D930AC,
        0x51DE003A,
        0xC8D75180,
        0xBFD06116,
        0x21B4F4B5,
        0x56B3C423,
        0xCFBA9599,
        0xB8BDA50F,
        0x2802B89E,
        0x5F058808,
        0xC60CD9B2,
        0xB10BE924,
        0x2F6F7C87,
        0x58684C11,
        0xC1611DAB,
        0xB6662D3D,
        0x76DC4190,
        0x01DB7106,
        0x98D220BC,
        0xEFD5102A,
        0x71B18589,
        0x06B6B51F,
        0x9FBFE4A5,
        0xE8B8D433,
        0x7807C9A2,
        0x0F00F934,
        0x9609A88E,
        0xE10E9818,
        0x7F6A0DBB,
        0x086D3D2D,
        0x91646C97,
        0xE6635C01,
        0x6B6B51F4,
        0x1C6C6162,
        0x856530D8,
        0xF262004E,
        0x6C0695ED,
        0x1B01A57B,
        0x8208F4C1,
        0xF50FC457,
        0x65B0D9C6,
        0x12B7E950,
        0x8BBEB8EA,
        0xFCB9887C,
        0x62DD1DDF,
        0x15DA2D49,
        0x8CD37CF3,
        0xFBD44C65,
        0x4DB26158,
        0x3AB551CE,
        0xA3BC0074,
        0xD4BB30E2,
        0x4ADFA541,
        0x3DD895D7,
        0xA4D1C46D,
        0xD3D6F4FB,
        0x4369E96A,
        0x346ED9FC,
        0xAD678846,
        0xDA60B8D0,
        0x44042D73,
        0x33031DE5,
        0xAA0A4C5F,
        0xDD0D7CC9,
        0x5005713C,
        0x270241AA,
        0xBE0B1010,
        0xC90C2086,
        0x5768B525,
        0x206F85B3,
        0xB966D409,
        0xCE61E49F,
        0x5EDEF90E,
        0x29D9C998,
        0xB0D09822,
        0xC7D7A8B4,
        0x59B33D17,
        0x2EB40D81,
        0xB7BD5C3B,
        0xC0BA6CAD,
        0xEDB88320,
        0x9ABFB3B6,
        0x03B6E20C,
        0x74B1D29A,
        0xEAD54739,
        0x9DD277AF,
        0x04DB2615,
        0x73DC1683,
        0xE3630B12,
        0x94643B84,
        0x0D6D6A3E,
        0x7A6A5AA8,
        0xE40ECF0B,
        0x9309FF9D,
        0x0A00AE27,
        0x7D079EB1,
        0xF00F9344,
        0x8708A3D2,
        0x1E01F268,
        0x6906C2FE,
        0xF762575D,
        0x806567CB,
        0x196C3671,
        0x6E6B06E7,
        0xFED41B76,
        0x89D32BE0,
        0x10DA7A5A,
        0x67DD4ACC,
        0xF9B9DF6F,
        0x8EBEEFF9,
        0x17B7BE43,
        0x60B08ED5,
        0xD6D6A3E8,
        0xA1D1937E,
        0x38D8C2C4,
        0x4FDFF252,
        0xD1BB67F1,
        0xA6BC5767,
        0x3FB506DD,
        0x48B2364B,
        0xD80D2BDA,
        0xAF0A1B4C,
        0x36034AF6,
        0x41047A60,
        0xDF60EFC3,
        0xA867DF55,
        0x316E8EEF,
        0x4669BE79,
        0xCB61B38C,
        0xBC66831A,
        0x256FD2A0,
        0x5268E236,
        0xCC0C7795,
        0xBB0B4703,
        0x220216B9,
        0x5505262F,
        0xC5BA3BBE,
        0xB2BD0B28,
        0x2BB45A92,
        0x5CB36A04,
        0xC2D7FFA7,
        0xB5D0CF31,
        0x2CD99E8B,
        0x5BDEAE1D,
        0x9B64C2B0,
        0xEC63F226,
        0x756AA39C,
        0x026D930A,
        0x9C0906A9,
        0xEB0E363F,
        0x72076785,
        0x05005713,
        0x95BF4A82,
        0xE2B87A14,
        0x7BB12BAE,
        0x0CB61B38,
        0x92D28E9B,
        0xE5D5BE0D,
        0x7CDCEFB7,
        0x0BDBDF21,
        0x86D3D2D4,
        0xF1D4E242,
        0x68DDB3F8,
        0x1FDA836E,
        0x81BE16CD,
        0xF6B9265B,
        0x6FB077E1,
        0x18B74777,
        0x88085AE6,
        0xFF0F6A70,
        0x66063BCA,
        0x11010B5C,
        0x8F659EFF,
        0xF862AE69,
        0x616BFFD3,
        0x166CCF45,
        0xA00AE278,
        0xD70DD2EE,
        0x4E048354,
        0x3903B3C2,
        0xA7672661,
        0xD06016F7,
        0x4969474D,
        0x3E6E77DB,
        0xAED16A4A,
        0xD9D65ADC,
        0x40DF0B66,
        0x37D83BF0,
        0xA9BCAE53,
        0xDEBB9EC5,
        0x47B2CF7F,
        0x30B5FFE9,
        0xBDBDF21C,
        0xCABAC28A,
        0x53B39330,
        0x24B4A3A6,
        0xBAD03605,
        0xCDD70693,
        0x54DE5729,
        0x23D967BF,
        0xB3667A2E,
        0xC4614AB8,
        0x5D681B02,
        0x2A6F2B94,
        0xB40BBE37,
        0xC30C8EA1,
        0x5A05DF1B,
        0x2D02EF8D,
    ],
)


def crc32(bytes, state=0):
    """crc32 exposed for use by chibios.py"""
    for byte in bytes:
        index = (state ^ byte) & 0xFF
        state = crctab[index] ^ (state >> 8)
    return state


class firmware(object):
    """Loads a firmware file"""

    desc = {}
    image = bytes()
    crcpad = bytearray(b"\xff\xff\xff\xff")

    def __init__(self, path):

        # read the file
        f = open(path, "r")
        self.desc = json.load(f)
        f.close()

        self.image = bytearray(zlib.decompress(base64.b64decode(self.desc["image"])))
        if "extf_image" in self.desc:
            self.extf_image = bytearray(zlib.decompress(base64.b64decode(self.desc["extf_image"])))
        else:
            self.extf_image = None
        # pad image to 4-byte length
        while (len(self.image) % 4) != 0:
            self.image += bytes(0xFF)
        # pad image to 4-byte length
        if self.extf_image is not None:
            while (len(self.extf_image) % 4) != 0:
                self.extf_image += bytes(0xFF)

    def property(self, propname, default=None):
        if propname in self.desc:
            return self.desc[propname]
        return default

    def extf_crc(self, size):
        state = crc32(self.extf_image[:size], int(0))
        return state

    def crc(self, padlen):
        state = crc32(self.image, int(0))
        for i in range(len(self.image), (padlen - 1), 4):
            state = crc32(self.crcpad, state)
        return state


class uploader(object):
    """Uploads a firmware file to the PX FMU bootloader"""

    # protocol bytes
    INSYNC = b"\x12"
    EOC = b"\x20"

    # reply bytes
    OK = b"\x10"
    FAILED = b"\x11"
    INVALID = b"\x13"  # rev3+
    BAD_SILICON_REV = b"\x14"  # rev5+

    # command bytes
    NOP = b"\x00"  # guaranteed to be discarded by the bootloader
    GET_SYNC = b"\x21"
    GET_DEVICE = b"\x22"
    CHIP_ERASE = b"\x23"
    CHIP_VERIFY = b"\x24"  # rev2 only
    PROG_MULTI = b"\x27"
    READ_MULTI = b"\x28"  # rev2 only
    GET_CRC = b"\x29"  # rev3+
    GET_OTP = b"\x2a"  # rev4+  , get a word from OTP area
    GET_SN = b"\x2b"  # rev4+  , get a word from SN area
    GET_CHIP = b"\x2c"  # rev5+  , get chip version
    SET_BOOT_DELAY = b"\x2d"  # rev5+  , set boot delay
    GET_CHIP_DES = b"\x2e"  # rev5+  , get chip description in ASCII
    MAX_DES_LENGTH = 20

    REBOOT = b"\x30"
    SET_BAUD = b"\x33"  # set baud

    EXTF_ERASE = b"\x34"  # erase sectors from external flash
    EXTF_PROG_MULTI = b"\x35"  # write bytes at external flash program address and increment
    EXTF_READ_MULTI = b"\x36"  # read bytes at address and increment
    EXTF_GET_CRC = b"\x37"  # compute & return a CRC of data in external flash

    CHIP_FULL_ERASE = b"\x40"  # full erase of flash

    INFO_BL_REV = b"\x01"  # bootloader protocol revision
    BL_REV_MIN = 2  # minimum supported bootloader protocol
    BL_REV_MAX = 5  # maximum supported bootloader protocol
    INFO_BOARD_ID = b"\x02"  # board type
    INFO_BOARD_REV = b"\x03"  # board revision
    INFO_FLASH_SIZE = b"\x04"  # max firmware size in bytes
    INFO_EXTF_SIZE = b"\x06"  # available external flash size

    PROG_MULTI_MAX = 252  # protocol max is 255, must be multiple of 4
    READ_MULTI_MAX = 252  # protocol max is 255

    NSH_INIT = bytearray(b"\x0d\x0d\x0d")
    NSH_REBOOT_BL = b"reboot -b\n"
    NSH_REBOOT = b"reboot\n"

    def __init__(
        self,
        portname,
        baudrate_bootloader,
        baudrate_flightstack,
        baudrate_bootloader_flash=None,
        target_system=None,
        target_component=None,
        source_system=None,
        source_component=None,
        no_extf=False,
        force_erase=False,
    ):
        self.MAVLINK_REBOOT_ID1 = bytearray(
            b"\xfe\x21\x72\xff\x00\x4c\x00\x00\x40\x40\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf6\x00\x01\x00\x00\x53\x6b"
        )  # NOQA
        self.MAVLINK_REBOOT_ID0 = bytearray(
            b"\xfe\x21\x45\xff\x00\x4c\x00\x00\x40\x40\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\xf6\x00\x00\x00\x00\xcc\x37"
        )  # NOQA
        if target_component is None:
            target_component = 1
        if source_system is None:
            source_system = 255
        if source_component is None:
            source_component = 1
        self.no_extf = no_extf
        self.force_erase = force_erase

        # open the port, keep the default timeout short so we can poll quickly
        self.port = serial.Serial(portname, baudrate_bootloader, timeout=2.0, write_timeout=2.0)
        self.baudrate_bootloader = baudrate_bootloader
        if baudrate_bootloader_flash is not None:
            self.baudrate_bootloader_flash = baudrate_bootloader_flash
        else:
            self.baudrate_bootloader_flash = self.baudrate_bootloader
        self.baudrate_flightstack = baudrate_flightstack
        self.baudrate_flightstack_idx = -1
        # generate mavlink reboot message:
        if target_system is not None:
            from pymavlink import mavutil

            m = mavutil.mavlink.MAVLink_command_long_message(
                target_system,
                target_component,
                mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
                1,  # confirmation
                3,  # remain in bootloader
                0,
                0,
                0,
                0,
                0,
                0,
            )
            mav = mavutil.mavlink.MAVLink(
                self, srcSystem=source_system, srcComponent=source_component
            )
            self.MAVLINK_REBOOT_ID1 = m.pack(mav)
            self.MAVLINK_REBOOT_ID0 = None

    def close(self):
        if self.port is not None:
            self.port.close()

    def open(self):
        timeout = time.time() + 0.2

        # Attempt to open the port while it exists and until timeout occurs
        while self.port is not None:
            portopen = True
            try:
                portopen = self.port.is_open
            except AttributeError:
                portopen = self.port.isOpen()

            if not portopen and time.time() < timeout:
                try:
                    self.port.open()
                except OSError:
                    # wait for the port to be ready
                    time.sleep(0.04)
                except serial.SerialException:
                    # if open fails, try again later
                    time.sleep(0.04)

            else:
                break

    def __send(self, c):
        self.port.write(c)

    def __recv(self, count=1):
        c = self.port.read(count)
        if len(c) < 1:
            raise RuntimeError("timeout waiting for data (%u bytes)" % count)
        # print("recv " + binascii.hexlify(c))
        return c

    def __recv_int(self):
        raw = self.__recv(4)
        val = struct.unpack("<I", raw)
        return val[0]

    def __recv_uint8(self):
        raw = self.__recv(1)
        val = struct.unpack("<B", raw)
        return val[0]

    def __getSync(self):
        self.port.flush()
        c = bytes(self.__recv())
        if c != self.INSYNC:
            raise RuntimeError("unexpected %s instead of INSYNC" % c)
        c = self.__recv()
        if c == self.INVALID:
            raise RuntimeError("bootloader reports INVALID OPERATION")
        if c == self.FAILED:
            raise RuntimeError("bootloader reports OPERATION FAILED")
        if c != self.OK:
            raise RuntimeError("unexpected response 0x%x instead of OK" % ord(c))

    # attempt to get back into sync with the bootloader
    def __sync(self):
        # send a stream of ignored bytes longer than the longest possible conversation
        # that we might still have in progress
        # self.__send(uploader.NOP * (uploader.PROG_MULTI_MAX + 2))
        self.port.flushInput()
        self.__send(uploader.GET_SYNC + uploader.EOC)
        self.__getSync()

    def __trySync(self):
        try:
            self.port.flush()
            if self.__recv() != self.INSYNC:
                # print("unexpected 0x%x instead of INSYNC" % ord(c))
                return False
            c = self.__recv()
            if c == self.BAD_SILICON_REV:
                raise NotImplementedError()
            if c != self.OK:
                # print("unexpected 0x%x instead of OK" % ord(c))
                return False
            return True

        except NotImplementedError:
            raise RuntimeError(
                "Programing not supported for this version of silicon!\n"
                "See https://pixhawk.org/help/errata"
            )
        except RuntimeError:
            # timeout, no response yet
            return False

    # send the GET_DEVICE command and wait for an info parameter
    def __getInfo(self, param):
        self.__send(uploader.GET_DEVICE + param + uploader.EOC)
        value = self.__recv_int()
        self.__getSync()
        return value

    # send the GET_OTP command and wait for an info parameter
    def __getOTP(self, param):
        t = struct.pack("I", param)  # int param as 32bit ( 4 byte ) char array.
        self.__send(uploader.GET_OTP + t + uploader.EOC)
        value = self.__recv(4)
        self.__getSync()
        return value

    # send the GET_SN command and wait for an info parameter
    def __getSN(self, param):
        t = struct.pack("I", param)  # int param as 32bit ( 4 byte ) char array.
        self.__send(uploader.GET_SN + t + uploader.EOC)
        value = self.__recv(4)
        self.__getSync()
        return value

    # send the GET_CHIP command
    def __getCHIP(self):
        self.__send(uploader.GET_CHIP + uploader.EOC)
        value = self.__recv_int()
        self.__getSync()
        return value

    # send the GET_CHIP command
    def __getCHIPDes(self):
        self.__send(uploader.GET_CHIP_DES + uploader.EOC)
        length = self.__recv_int()
        value = self.__recv(length)
        self.__getSync()
        if runningPython3:
            value = value.decode("ascii")
        peices = value.split(",")
        return peices

    def __drawProgressBar(self, label, progress, maxVal):
        if maxVal < progress:
            progress = maxVal

        percent = (float(progress) / float(maxVal)) * 100.0

        sys.stdout.write("\r%s: [%-20s] %.1f%%" % (label, "=" * int(percent / 5.0), percent))
        sys.stdout.flush()

    # send the CHIP_ERASE command and wait for the bootloader to become ready
    def __erase(self, label):
        print("\n", end="")
        if self.force_erase:
            print("Force erasing full chip\n")
            self.__send(uploader.CHIP_FULL_ERASE + uploader.EOC)
        else:
            self.__send(uploader.CHIP_ERASE + uploader.EOC)

        # erase is very slow, give it 20s
        timeout = 20.0
        deadline = time.time() + timeout
        while time.time() < deadline:

            # Draw progress bar (erase usually takes about 9 seconds to complete)
            estimatedTimeRemaining = deadline - time.time()
            if estimatedTimeRemaining >= 9.0:
                self.__drawProgressBar(label, timeout - estimatedTimeRemaining, 9.0)
            else:
                self.__drawProgressBar(label, 10.0, 10.0)
                sys.stdout.write(" (timeout: %d seconds) " % int(deadline - time.time()))
                sys.stdout.flush()

            if self.__trySync():
                self.__drawProgressBar(label, 10.0, 10.0)
                return

        raise RuntimeError("timed out waiting for erase")

    # send a PROG_MULTI command to write a collection of bytes
    def __program_multi(self, data):

        if runningPython3:
            length = len(data).to_bytes(1, byteorder="big")
        else:
            length = chr(len(data))

        self.__send(uploader.PROG_MULTI)
        self.__send(length)
        self.__send(data)
        self.__send(uploader.EOC)
        self.__getSync()

    # send a PROG_EXTF_MULTI command to write a collection of bytes to external flash
    def __program_multi_extf(self, data):

        if runningPython3:
            length = len(data).to_bytes(1, byteorder="big")
        else:
            length = chr(len(data))

        self.__send(uploader.EXTF_PROG_MULTI)
        self.__send(length)
        self.__send(data)
        self.__send(uploader.EOC)
        self.__getSync()

    # verify multiple bytes in flash
    def __verify_multi(self, data):

        if runningPython3:
            length = len(data).to_bytes(1, byteorder="big")
        else:
            length = chr(len(data))

        self.__send(uploader.READ_MULTI)
        self.__send(length)
        self.__send(uploader.EOC)
        self.port.flush()
        programmed = self.__recv(len(data))
        if programmed != data:
            print("got    " + binascii.hexlify(programmed))
            print("expect " + binascii.hexlify(data))
            return False
        self.__getSync()
        return True

    # read multiple bytes from flash
    def __read_multi(self, length):

        if runningPython3:
            clength = length.to_bytes(1, byteorder="big")
        else:
            clength = chr(length)

        self.__send(uploader.READ_MULTI)
        self.__send(clength)
        self.__send(uploader.EOC)
        self.port.flush()
        ret = self.__recv(length)
        self.__getSync()
        return ret

    # send the reboot command
    def __reboot(self):
        self.__send(uploader.REBOOT + uploader.EOC)
        self.port.flush()

        # v3+ can report failure if the first word flash fails
        if self.bl_rev >= 3:
            self.__getSync()

    # split a sequence into a list of size-constrained pieces
    def __split_len(self, seq, length):
        return [seq[i : i + length] for i in range(0, len(seq), length)]

    # upload code
    def __program(self, label, fw):
        print("\n", end="")
        code = fw.image
        groups = self.__split_len(code, uploader.PROG_MULTI_MAX)

        uploadProgress = 0
        for bytes in groups:
            self.__program_multi(bytes)

            # Print upload progress (throttled, so it does not delay upload progress)
            uploadProgress += 1
            if uploadProgress % 256 == 0:
                self.__drawProgressBar(label, uploadProgress, len(groups))
        self.__drawProgressBar(label, 100, 100)

    # download code
    def __download(self, label, fw):
        print("\n", end="")
        f = open(fw, "wb")

        downloadProgress = 0
        readsize = uploader.READ_MULTI_MAX
        total = 0
        while True:
            n = min(self.fw_maxsize - total, readsize)
            bb = self.__read_multi(n)
            f.write(bb)

            total += len(bb)
            # Print download progress (throttled, so it does not delay download progress)
            downloadProgress += 1
            if downloadProgress % 256 == 0:
                self.__drawProgressBar(label, total, self.fw_maxsize)
            if len(bb) < readsize:
                break
        f.close()
        self.__drawProgressBar(label, total, self.fw_maxsize)
        print("\nReceived %u bytes to %s" % (total, fw))

    # verify code
    def __verify_v2(self, label, fw):
        print("\n", end="")
        self.__send(uploader.CHIP_VERIFY + uploader.EOC)
        self.__getSync()
        code = fw.image
        groups = self.__split_len(code, uploader.READ_MULTI_MAX)
        verifyProgress = 0
        for bytes in groups:
            verifyProgress += 1
            if verifyProgress % 256 == 0:
                self.__drawProgressBar(label, verifyProgress, len(groups))
            if not self.__verify_multi(bytes):
                raise RuntimeError("Verification failed")
        self.__drawProgressBar(label, 100, 100)

    def __verify_v3(self, label, fw):
        print("\n", end="")
        self.__drawProgressBar(label, 1, 100)
        expect_crc = fw.crc(self.fw_maxsize)
        self.__send(uploader.GET_CRC + uploader.EOC)
        report_crc = self.__recv_int()
        self.__getSync()
        if report_crc != expect_crc:
            print("Expected 0x%x" % expect_crc)
            print("Got      0x%x" % report_crc)
            raise RuntimeError("Program CRC failed")
        self.__drawProgressBar(label, 100, 100)

    def __set_boot_delay(self, boot_delay):
        self.__send(uploader.SET_BOOT_DELAY + struct.pack("b", boot_delay) + uploader.EOC)
        self.__getSync()

    def __setbaud(self, baud):
        self.__send(uploader.SET_BAUD + struct.pack("I", baud) + uploader.EOC)
        self.__getSync()

    def erase_extflash(self, label, size):
        if runningPython3:
            size_bytes = size.to_bytes(4, byteorder="little")
        else:
            size_bytes = chr(size)
        self.__send(uploader.EXTF_ERASE + size_bytes + uploader.EOC)
        self.__getSync()
        last_pct = 0
        while True:
            if last_pct < 90:
                pct = self.__recv_uint8()
                if last_pct != pct:
                    self.__drawProgressBar(label, pct, 100)
                    last_pct = pct
            elif self.__trySync():
                self.__drawProgressBar(label, 10.0, 10.0)
                return

    def __program_extf(self, label, fw):
        print("\n", end="")
        code = fw.extf_image
        groups = self.__split_len(code, uploader.PROG_MULTI_MAX)

        uploadProgress = 0
        for bytes in groups:
            self.__program_multi_extf(bytes)

            # Print upload progress (throttled, so it does not delay upload progress)
            uploadProgress += 1
            if uploadProgress % 32 == 0:
                self.__drawProgressBar(label, uploadProgress, len(groups))
        self.__drawProgressBar(label, 100, 100)

    def __verify_extf(self, label, fw, size):
        if runningPython3:
            size_bytes = size.to_bytes(4, byteorder="little")
        else:
            size_bytes = chr(size)
        print("\n", end="")
        self.__drawProgressBar(label, 1, 100)

        expect_crc = fw.extf_crc(size)
        self.__send(uploader.EXTF_GET_CRC + size_bytes + uploader.EOC)

        # crc can be slow, give it 10s
        deadline = time.time() + 10.0
        while time.time() < deadline:

            # Draw progress bar
            estimatedTimeRemaining = deadline - time.time()
            if estimatedTimeRemaining >= 4.0:
                self.__drawProgressBar(label, 10.0 - estimatedTimeRemaining, 4.0)
            else:
                self.__drawProgressBar(label, 5.0, 5.0)
                sys.stdout.write(" (timeout: %d seconds) " % int(deadline - time.time()))
                sys.stdout.flush()

            try:
                report_crc = self.__recv_int()
                break
            except Exception:
                continue

        if time.time() >= deadline:
            raise RuntimeError("Program CRC timed out")

        self.__getSync()
        if report_crc != expect_crc:
            print("\nExpected 0x%x" % expect_crc)
            print("Got      0x%x" % report_crc)
            raise RuntimeError("Program CRC failed")
        self.__drawProgressBar(label, 100, 100)

    # get basic data about the board
    def identify(self):
        # make sure we are in sync before starting
        self.__sync()

        # get the bootloader protocol ID first
        self.bl_rev = self.__getInfo(uploader.INFO_BL_REV)
        if (self.bl_rev < uploader.BL_REV_MIN) or (self.bl_rev > uploader.BL_REV_MAX):
            print("Unsupported bootloader protocol %d" % self.bl_rev)
            raise RuntimeError("Bootloader protocol mismatch")

        if self.no_extf:
            self.extf_maxsize = 0
        else:
            try:
                self.extf_maxsize = self.__getInfo(uploader.INFO_EXTF_SIZE)
            except Exception:
                print("Could not get external flash size, assuming 0")
                self.extf_maxsize = 0
                self.__sync()

        self.board_type = self.__getInfo(uploader.INFO_BOARD_ID)
        self.board_rev = self.__getInfo(uploader.INFO_BOARD_REV)
        self.fw_maxsize = self.__getInfo(uploader.INFO_FLASH_SIZE)

    def dump_board_info(self):
        # OTP added in v4:
        print("Bootloader Protocol: %u" % self.bl_rev)
        if self.bl_rev > 3:
            otp = b""
            for byte in range(0, 32 * 6, 4):
                x = self.__getOTP(byte)
                otp = otp + x
            #                print(binascii.hexlify(x).decode('Latin-1') + ' ', end='')
            # see src/modules/systemlib/otp.h in px4 code:
            otp_id = otp[0:4]
            otp_idtype = otp[4:5]
            otp_vid = otp[8:4:-1]
            otp_pid = otp[12:8:-1]
            otp_coa = otp[32:160]
            # show user:
            try:
                print("OTP:")
                print("  type: " + otp_id.decode("Latin-1"))
                print("  idtype: " + binascii.b2a_qp(otp_idtype).decode("Latin-1"))
                print("  vid: " + binascii.hexlify(otp_vid).decode("Latin-1"))
                print("  pid: " + binascii.hexlify(otp_pid).decode("Latin-1"))
                print("  coa: " + binascii.b2a_base64(otp_coa).decode("Latin-1"), end="")
                print("  sn: ", end="")
                for byte in range(0, 12, 4):
                    x = self.__getSN(byte)
                    x = x[::-1]  # reverse the bytes
                    print(binascii.hexlify(x).decode("Latin-1"), end="")  # show user
                print("")
            except Exception:
                # ignore bad character encodings
                pass

        if self.bl_rev >= 5:
            des = self.__getCHIPDes()
            if len(des) == 2:
                print("ChipDes:")
                print("  family: %s" % des[0])
                print("  revision: %s" % des[1])
        print("Chip:")
        if self.bl_rev > 4:
            chip = self.__getCHIP()
            mcu_id = chip & 0xFFF
            revs = {}

            F4_IDS = {
                0x413: "STM32F40x_41x",
                0x419: "STM32F42x_43x",
                0x421: "STM32F42x_446xx",
            }
            F7_IDS = {
                0x449: "STM32F74x_75x",
                0x451: "STM32F76x_77x",
            }
            H7_IDS = {
                0x450: "STM32H74x_75x",
            }

            family = mcu_id & 0xFFF

            if family in F4_IDS:
                mcu = F4_IDS[family]
                MCU_REV_STM32F4_REV_A = 0x1000
                MCU_REV_STM32F4_REV_Z = 0x1001
                MCU_REV_STM32F4_REV_Y = 0x1003
                MCU_REV_STM32F4_REV_1 = 0x1007
                MCU_REV_STM32F4_REV_3 = 0x2001
                revs = {
                    MCU_REV_STM32F4_REV_A: ("A", True),
                    MCU_REV_STM32F4_REV_Z: ("Z", True),
                    MCU_REV_STM32F4_REV_Y: ("Y", True),
                    MCU_REV_STM32F4_REV_1: ("1", True),
                    MCU_REV_STM32F4_REV_3: ("3", False),
                }
                rev = (chip & 0xFFFF0000) >> 16

                if rev in revs:
                    (label, flawed) = revs[rev]
                    if flawed and family == 0x419:
                        print(
                            "  %x %s rev%s (flawed; 1M limit, see STM32F42XX Errata sheet sec. 2.1.10)"
                            % (
                                chip,
                                mcu,
                                label,
                            )
                        )
                    elif family == 0x419:
                        print(
                            "  %x %s rev%s (no 1M flaw)"
                            % (
                                chip,
                                mcu,
                                label,
                            )
                        )
                    else:
                        print(
                            "  %x %s rev%s"
                            % (
                                chip,
                                mcu,
                                label,
                            )
                        )
            elif family in F7_IDS:
                print("  %s %08x" % (F7_IDS[family], chip))
            elif family in H7_IDS:
                print("  %s %08x" % (H7_IDS[family], chip))
        else:
            print("  [unavailable; bootloader too old]")

        print("Info:")
        print("  flash size: %u" % self.fw_maxsize)
        print("  ext flash size: %u" % self.extf_maxsize)
        name = self.board_name_for_board_id(self.board_type)
        if name is not None:
            print("  board_type: %u (%s)" % (self.board_type, name))
        else:
            print("  board_type: %u" % self.board_type)
        print("  board_rev: %u" % self.board_rev)

        print("Identification complete")

    def board_name_for_board_id(self, board_id):
        """return name for board_id, None if it can't be found"""
        shared_ids = {
            9: "fmuv3",
            50: "fmuv5",
            140: "CubeOrange",
            1063: "CubeOrangePlus",
        }
        if board_id in shared_ids:
            return shared_ids[board_id]

        try:
            ret = []

            hwdef_dir = os.path.join(
                os.path.dirname(os.path.realpath(__file__)),
                "..",
                "..",
                "libraries",
                "AP_HAL_ChibiOS",
                "hwdef",
            )
            # uploader.py is swiped into other places, so if the dir
            # doesn't exist then fail silently
            if os.path.exists(hwdef_dir):
                dirs = [
                    (
                        x
                        if (
                            x not in ["scripts", "common", "STM32CubeConf"]
                            and os.path.isdir(os.path.join(hwdef_dir, x))
                        )
                        else None
                    )
                    for x in os.listdir(hwdef_dir)
                ]  # NOQA
                for adir in dirs:
                    if adir is None:
                        continue
                    filepath = os.path.join(hwdef_dir, adir, "hwdef.dat")
                    if not os.path.exists(filepath):
                        continue
                    fh = open(filepath)
                    if fh is None:
                        continue
                    text = fh.readlines()
                    for line in text:
                        m = re.match(r"^\s*APJ_BOARD_ID\s+(\d+)\s*$", line)
                        if m is None:
                            continue
                        if int(m.group(1)) == board_id:
                            ret.append(adir)
            if len(ret) == 0:
                return None
            return " or ".join(ret)
        except Exception as e:
            print("Failed to get name: %s" % str(e))
        return None

    # Verify firmware version on board matches provided version
    def verify_firmware_is(self, fw, boot_delay=None):
        if self.bl_rev == 2:
            self.__verify_v2("Verify ", fw)
        else:
            self.__verify_v3("Verify ", fw)

        if boot_delay is not None:
            self.__set_boot_delay(boot_delay)

        print("\nRebooting.\n")
        self.__reboot()
        self.port.close()

    # upload the firmware
    def upload(self, fw, force=False, boot_delay=None):
        # Make sure we are doing the right thing
        if self.board_type != fw.property("board_id"):
            # ID mismatch: check compatibility
            incomp = True
            if self.board_type in compatible_IDs:
                comp_fw_id = compatible_IDs[self.board_type][0]
                board_name = compatible_IDs[self.board_type][1]
                if comp_fw_id == fw.property("board_id"):
                    msg = (
                        "Target %s (board_id: %d) is compatible with firmware for board_id=%u)"
                        % (board_name, self.board_type, fw.property("board_id"))
                    )
                    print("INFO: %s" % msg)
                    incomp = False
            if incomp:
                msg = (
                    "Firmware not suitable for this board (board_type=%u (%s) board_id=%u (%s))"
                    % (
                        self.board_type,
                        self.board_name_for_board_id(self.board_type),
                        fw.property("board_id"),
                        self.board_name_for_board_id(fw.property("board_id")),
                    )
                )
                print("WARNING: %s" % msg)

                if force:
                    print("FORCED WRITE, FLASHING ANYWAY!")
                else:
                    raise IOError(msg)

        self.dump_board_info()

        if self.fw_maxsize < fw.property("image_size") or self.extf_maxsize < fw.property(
            "extf_image_size", 0
        ):
            raise RuntimeError("Firmware image is too large for this board")

        if self.baudrate_bootloader_flash != self.baudrate_bootloader:
            print("Setting baudrate to %u" % self.baudrate_bootloader_flash)
            self.__setbaud(self.baudrate_bootloader_flash)
            self.port.baudrate = self.baudrate_bootloader_flash
            self.__sync()

        if fw.property("extf_image_size", 0) > 0:
            self.erase_extflash("Erase ExtF  ", fw.property("extf_image_size", 0))
            self.__program_extf("Program ExtF", fw)
            self.__verify_extf("Verify ExtF ", fw, fw.property("extf_image_size", 0))

        if fw.property("image_size") > 0:
            self.__erase("Erase  ")
            self.__program("Program", fw)

            if self.bl_rev == 2:
                self.__verify_v2("Verify ", fw)
            else:
                self.__verify_v3("Verify ", fw)

        if boot_delay is not None:
            self.__set_boot_delay(boot_delay)

        print("\nRebooting.\n")
        self.__reboot()
        self.port.close()

    def __next_baud_flightstack(self):
        self.baudrate_flightstack_idx = self.baudrate_flightstack_idx + 1
        if self.baudrate_flightstack_idx >= len(self.baudrate_flightstack):
            return False

        try:
            self.port.baudrate = self.baudrate_flightstack[self.baudrate_flightstack_idx]
        except Exception:
            return False

        return True

    def send_reboot(self):
        if not self.__next_baud_flightstack():
            return False

        print(
            "Attempting reboot on %s with baudrate=%d..." % (self.port.port, self.port.baudrate),
            file=sys.stderr,
        )
        print(
            "If the board does not respond, unplug and re-plug the USB connector.",
            file=sys.stderr,
        )

        try:
            # try MAVLINK command first
            self.port.flush()
            if self.MAVLINK_REBOOT_ID1 is not None:
                self.__send(self.MAVLINK_REBOOT_ID1)
            if self.MAVLINK_REBOOT_ID0 is not None:
                self.__send(self.MAVLINK_REBOOT_ID0)
            # then try reboot via NSH
            self.__send(uploader.NSH_INIT)
            self.__send(uploader.NSH_REBOOT_BL)
            self.__send(uploader.NSH_INIT)
            self.__send(uploader.NSH_REBOOT)
            self.port.flush()
            self.port.baudrate = self.baudrate_bootloader
        except Exception:
            try:
                self.port.flush()
                self.port.baudrate = self.baudrate_bootloader
            except Exception:
                pass

        return True

    # upload the firmware
    def download(self, fw):
        if self.baudrate_bootloader_flash != self.baudrate_bootloader:
            print("Setting baudrate to %u" % self.baudrate_bootloader_flash)
            self.__setbaud(self.baudrate_bootloader_flash)
            self.port.baudrate = self.baudrate_bootloader_flash
            self.__sync()

        self.__download("Download", fw)
        self.port.close()


def ports_to_try(args):
    portlist = []
    if args.port is None:
        patterns = default_ports
    else:
        patterns = args.port.split(",")
    # use glob to support wildcard ports. This allows the use of
    # /dev/serial/by-id/usb-ArduPilot on Linux, which prevents the
    # upload from causing modem hangups etc
    if "linux" in _platform or "darwin" in _platform or "cygwin" in _platform:
        import glob

        for pattern in patterns:
            portlist += sorted(glob.glob(pattern))
    else:
        portlist = patterns

    # filter ports based on platform:
    if "cygwin" in _platform:
        # Cygwin, don't open MAC OS and Win ports, we are more like
        # Linux. Cygwin needs to be before Windows test
        pass
    elif "darwin" in _platform:
        # OS X, don't open Windows and Linux ports
        portlist = [port for port in portlist if "COM" not in port and "ACM" not in port]
    elif "win" in _platform:
        # Windows, don't open POSIX ports
        portlist = [port for port in portlist if "/" not in port]

    return portlist


def modemmanager_check():
    if os.path.exists("/usr/sbin/ModemManager"):
        print(
            """
===========================================================================================
WARNING: You should uninstall ModemManager as it conflicts with any non-modem serial device
===========================================================================================
"""
        )
    if os.path.exists("/usr/bin/brltty"):
        print(
            """
=====================================================================================
WARNING: You should uninstall brltty as it conflicts with any non-modem serial device
=====================================================================================
"""
        )


def find_bootloader(up, port):
    while True:
        up.open()

        # port is open, try talking to it
        try:
            # identify the bootloader
            up.identify()
            print(
                "Found board %x,%x bootloader rev %x on %s"
                % (up.board_type, up.board_rev, up.bl_rev, port)
            )
            return True

        except Exception:
            pass

        reboot_sent = up.send_reboot()

        # wait for the reboot, without we might run into Serial I/O Error 5
        time.sleep(0.25)

        # always close the port
        up.close()

        # wait for the close, without we might run into Serial I/O Error 6
        time.sleep(0.3)

        if not reboot_sent:
            return False


def main():

    # Parse commandline arguments
    parser = argparse.ArgumentParser(description="Firmware uploader for the PX autopilot system.")
    parser.add_argument(
        "--port",
        action="store",
        help="Comma-separated list of serial port(s) to which the FMU may be attached",
        default=None,
    )
    parser.add_argument(
        "--baud-bootloader",
        action="store",
        type=int,
        default=115200,
        help="Baud rate of the serial port (default is 115200) when communicating with bootloader, only required for true serial ports.",  # NOQA
    )
    parser.add_argument(
        "--baud-bootloader-flash",
        action="store",
        type=int,
        default=None,
        help="Attempt to negotiate this baudrate with bootloader for flashing.",
    )
    parser.add_argument(
        "--baud-flightstack",
        action="store",
        default="57600",
        help="Comma-separated list of baud rate of the serial port (default is 57600) when communicating with flight stack (Mavlink or NSH), only required for true serial ports.",  # NOQA
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Override board type check and continue loading",
    )
    parser.add_argument(
        "--boot-delay",
        type=int,
        default=None,
        help="minimum boot delay to store in flash",
    )
    parser.add_argument("--target-system", type=int, action="store", help="System ID to update")
    parser.add_argument(
        "--target-component", type=int, action="store", help="Component ID to update"
    )
    parser.add_argument(
        "--source-system",
        type=int,
        action="store",
        help="Source system to send reboot mavlink packets from",
        default=255,
    )
    parser.add_argument(
        "--source-component",
        type=int,
        action="store",
        help="Source component to send reboot mavlink packets from",
        default=0,
    )
    parser.add_argument(
        "--download",
        action="store_true",
        default=False,
        help="download firmware from board",
    )
    parser.add_argument(
        "--identify",
        action="store_true",
        help="Do not flash firmware; simply dump information about board",
    )
    parser.add_argument(
        "--verify-firmware-is",
        action="store_true",
        help="Do not flash firmware; verify that the firmware on the board matches the supplied firmware",
    )
    parser.add_argument(
        "--no-extf",
        action="store_true",
        help="Do not attempt external flash operations",
    )
    parser.add_argument(
        "--erase-extflash",
        type=lambda x: int(x, 0),
        default=None,
        help="Erase sectors containing specified amount of bytes from ext flash",
    )
    parser.add_argument(
        "--force-erase",
        action="store_true",
        help="Do not check for pre cleared flash, always erase the chip",
    )
    parser.add_argument(
        "firmware",
        nargs="?",
        action="store",
        default=None,
        help="Firmware file to be uploaded",
    )
    args = parser.parse_args()

    # warn people about ModemManager which interferes badly with Pixhawk
    modemmanager_check()

    if args.firmware is None and not args.identify and not args.erase_extflash:
        parser.error("Firmware filename required for upload or download")
        sys.exit(1)

    # Load the firmware file
    if not args.download and not args.identify and not args.erase_extflash:
        fw = firmware(args.firmware)
        print(
            "Loaded firmware for %x,%x, size: %d bytes, waiting for the bootloader..."
            % (
                fw.property("board_id"),
                fw.property("board_revision"),
                fw.property("image_size"),
            )
        )
    print("If the board does not respond within 1-2 seconds, unplug and re-plug the USB connector.")

    baud_flightstack = [int(x) for x in args.baud_flightstack.split(",")]

    # Spin waiting for a device to show up
    try:
        while True:

            for port in ports_to_try(args):

                # print("Trying %s" % port)

                # create an uploader attached to the port
                try:
                    up = uploader(
                        port,
                        args.baud_bootloader,
                        baud_flightstack,
                        args.baud_bootloader_flash,
                        args.target_system,
                        args.target_component,
                        args.source_system,
                        args.source_component,
                        args.no_extf,
                        args.force_erase,
                    )

                except Exception as e:
                    if not is_WSL and not is_WSL2 and "win32" not in _platform:
                        # open failed, WSL must cycle through all ttyS* ports quickly but rate limit everything else
                        print("Exception creating uploader: %s" % str(e))
                        time.sleep(0.05)

                    # and loop to the next port
                    continue

                if not find_bootloader(up, port):
                    # Go to the next port
                    continue

                try:
                    # ok, we have a bootloader, try flashing it
                    if args.identify:
                        up.dump_board_info()
                    elif args.download:
                        up.download(args.firmware)
                    elif args.verify_firmware_is:
                        up.verify_firmware_is(fw, boot_delay=args.boot_delay)
                    elif args.erase_extflash:
                        up.erase_extflash("Erase ExtF", args.erase_extflash)
                        print("\nExtF Erase Finished")
                    else:
                        up.upload(fw, force=args.force, boot_delay=args.boot_delay)

                except RuntimeError as ex:
                    # print the error and exit as a failure
                    sys.exit("\nERROR: %s" % ex.args)

                except IOError:
                    up.close()
                    continue

                finally:
                    # always close the port
                    up.close()

                # we could loop here if we wanted to wait for more boards...
                sys.exit(0)

            # Delay retries to < 20 Hz to prevent spin-lock from hogging the CPU
            time.sleep(0.05)

    # CTRL+C aborts the upload/spin-lock by interrupt mechanics
    except KeyboardInterrupt:
        print("\n Upload aborted by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
