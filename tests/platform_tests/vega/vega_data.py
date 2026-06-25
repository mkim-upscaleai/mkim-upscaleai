"""
Physical platform constants for Vega 6540 (x86_64-upscaleai_6540-r0).

Derived from caspian-sonic-buildimage device/upscaleai/.../platform.json and
6540/specs/DUT-VALIDATION.md. Update here when platform.json topology changes.
"""

VEGA_PLATFORMS = ["x86_64-upscaleai_6540-r0"]

# Chassis layout (platform.json)
FAN_DRAWER_COUNT = 4
FANS_PER_DRAWER = 2
FAN_COUNT = FAN_DRAWER_COUNT * FANS_PER_DRAWER
PSU_COUNT = 2

# TMP1075 board sensors on FPGA I2C bus 30 @ 0x48-0x4F (platform.json names)
BOARD_THERMAL_NAMES = [
    "ASIC_Rear",
    "ASIC_Front_Mid",
    "ASIC_Front_Mid_2",
    "ASIC_Rear_Left_VRM",
    "Exhaust",
    "OSFP60_Rear",
    "ASIC_Rear_Right_VRM",
    "OSFP0_Rear",
]

# Host COMX coretemp sensors exposed via sonic_platform (names from platform.json)
CPU_THERMAL_PREFIXES = ("CPU Package", "CPU Core")

# I2C bring-up anchors from DUT-VALIDATION.md (kernel bus numbers)
FPGA_THERMAL_BUS = 30
FPGA_THERMAL_ADDRS = ["0048", "0049", "004a", "004b", "004c", "004d", "004e", "004f"]
FAN_TRAY_BUSES = [32, 33, 34, 35]
PSU_PMBUS_BUSES = [36, 37]

# Sensible lab idle ranges (°C)
MIN_BOARD_TEMP_C = 5.0
MAX_BOARD_TEMP_C = 105.0
MIN_CPU_TEMP_C = 5.0
MAX_CPU_TEMP_C = 105.0

MIN_FAN_RPM = 100
MAX_FAN_RPM = 60000

# On-board service SFPP (always populated on Vega carrier)
SERVICE_SFPP_PORTS = ["Ethernet512", "Ethernet520"]

# CMIS / OSFP EEPROM keys (any subset may appear depending on module type)
CMIS_EEPROM_KEYS = [
    "Identifier",
    "Vendor Name",
    "Vendor PN",
    "Vendor SN",
    "CMIS Revision",
    "Application Advertisement",
]

# PMON daemons expected when platform bring-up is complete
VEGA_PMON_DAEMONS = ["thermalctld", "psud", "xcvrd"]

# Host reboot cause (software path; hardware latch not enabled on current Vega)
REBOOT_CAUSE_HOST_FILE = "/host/reboot-cause/reboot-cause.txt"


def is_vega_platform(dut):
    return dut.facts.get("platform") in VEGA_PLATFORMS
