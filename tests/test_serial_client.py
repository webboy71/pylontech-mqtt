"""Unit tests for PylontechSerialClient respecting configured battery count."""

import unittest
from unittest.mock import MagicMock, patch

from pylontech_mqtt.config import AppConfig
from pylontech_mqtt.serial_client import PylontechSerialClient

SAMPLE_PWR_8_UNITS = """
@
Power Volt   Curr   Tempr Tlow  Thigh Vlow  Vhigh Base.St Volt.St Curr.St Temp.St Coulmb.St Coulomb Base.Pr
1     49950  -1250  23000 22000 24000 3328  3332  Dischg  Normal  Normal  Normal  Normal    98%     Normal
2     49960  -1240  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
3     49950  -1230  23000 22000 24000 3328  3330  Dischg  Normal  Normal  Normal  Normal    98%     Normal
4     49960  -1250  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
5     49950  -1250  23000 22000 24000 3328  3332  Dischg  Normal  Normal  Normal  Normal    98%     Normal
6     49960  -1240  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
7     49950  -1230  23000 22000 24000 3328  3330  Dischg  Normal  Normal  Normal  Normal    98%     Normal
8     49960  -1250  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
Command completed successfully
$$
pylon>
"""

SAMPLE_PWR_4_PRESENT_4_ABSENT = """
@
Power Volt   Curr   Tempr Tlow  Thigh Vlow  Vhigh Base.St Volt.St Curr.St Temp.St Coulmb.St Coulomb Base.Pr
1     49950  -1250  23000 22000 24000 3328  3332  Dischg  Normal  Normal  Normal  Normal    98%     Normal
2     49960  -1240  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
3     49950  -1230  23000 22000 24000 3328  3330  Dischg  Normal  Normal  Normal  Normal    98%     Normal
4     49960  -1250  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
5     -      -      -     -     -     -     -     Absent  -       -       -       -         -       -
6     -      -      -     -     -     -     -     Absent  -       -       -       -         -       -
7     -      -      -     -     -     -     -     Absent  -       -       -       -         -       -
8     -      -      -     -     -     -     -     Absent  -       -       -       -         -       -
Command completed successfully
$$
pylon>
"""

SAMPLE_BAT_OUTPUT = """
@
Battery 1:
Cell Volt: 3328 3329 3330 3329 3331 3329 3330 3331 3328 3329 3330 3329 3331 3329 3330
Cell Temp: 23000 23000 23000 23000 23000
BMS Temp: 24000
B.V.St: Normal
B.T.St: Normal
Coulomb: 98%
Total Coulomb: 50000 mAH
Real Coulomb: 49000 mAH
Cycle: 142
Command completed successfully
$$
pylon>
"""

SAMPLE_INFO_OUTPUT = """
@
Device address      : 1
Manufacturer        : Pylontech
Device name         : US2000
Serial Number       : PPTA012345678901
Main Soft version   : B65.12
Command completed successfully
$$
pylon>
"""


class TestSerialClientBatteryCount(unittest.TestCase):

    def setUp(self):
        self.config = AppConfig()
        self.config.polling.battery_count = 4
        self.config.polling.read_cell_details = True
        self.client = PylontechSerialClient(self.config)
        self.client._is_connected = True
        self.client._serial = MagicMock()
        self.client._serial.is_open = True

    def test_respects_configured_battery_count_when_pwr_returns_8_rows(self):
        """When 8 rows exist in pwr, but config specifies 4, only 4 units must be polled."""
        commands_sent = []

        def mock_send_command(cmd: str, timeout=None):
            commands_sent.append(cmd)
            if cmd == "pwr":
                return SAMPLE_PWR_8_UNITS
            elif cmd.startswith("bat "):
                return SAMPLE_BAT_OUTPUT
            elif cmd.startswith("info"):
                return SAMPLE_INFO_OUTPUT
            elif cmd.startswith("soh "):
                return "SOH: 99%\n$$"
            return "$$"

        self.client.send_command = mock_send_command

        telemetry = self.client.poll_telemetry()
        self.assertIsNotNone(telemetry)
        # Verify stack has exactly 4 active units
        self.assertEqual(telemetry.active_units_count, 4)
        self.assertEqual(len(telemetry.unit_telemetries), 4)
        self.assertIn(1, telemetry.unit_telemetries)
        self.assertIn(4, telemetry.unit_telemetries)
        self.assertNotIn(5, telemetry.unit_telemetries)
        self.assertNotIn(8, telemetry.unit_telemetries)

        # Verify only bat 1..4 and info 1..4 were sent, not bat 5..8
        self.assertIn("bat 1", commands_sent)
        self.assertIn("bat 4", commands_sent)
        self.assertNotIn("bat 5", commands_sent)
        self.assertNotIn("bat 8", commands_sent)

    def test_auto_detection_with_zero_battery_count(self):
        """When battery_count is 0, absent units (5..8) are excluded."""
        self.config.polling.battery_count = 0
        commands_sent = []

        def mock_send_command(cmd: str, timeout=None):
            commands_sent.append(cmd)
            if cmd == "pwr":
                return SAMPLE_PWR_4_PRESENT_4_ABSENT
            elif cmd.startswith("bat "):
                return SAMPLE_BAT_OUTPUT
            elif cmd.startswith("info"):
                return SAMPLE_INFO_OUTPUT
            return "$$"

        self.client.send_command = mock_send_command

        telemetry = self.client.poll_telemetry()
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.active_units_count, 4)
        self.assertEqual(len(telemetry.unit_telemetries), 4)
        self.assertNotIn(5, telemetry.unit_telemetries)

    def test_fetches_cycle_count_from_stat_when_bat_returns_table(self):
        """When bat <id> returns a cell table without Cycle, poll_telemetry queries stat <id>."""
        bat_table = """
@
Battery  Volt   Curr   Tempr  Base State  Volt. State  Curr. State  Temp. State  Coulomb
0        3328   -1250  23000  Dischg      Normal       Normal       Normal       98%
1        3329   -1250  23000  Dischg      Normal       Normal       Normal       98%
Command completed successfully
$$
"""
        stat_output = """
@
Device address 1.
CYCLE Times : 87
Command completed successfully.
$$
"""

        def mock_send_command(cmd: str, timeout=None):
            if cmd == "pwr":
                return SAMPLE_PWR_8_UNITS
            elif cmd.startswith("bat "):
                return bat_table
            elif cmd.startswith("info"):
                return SAMPLE_INFO_OUTPUT
            elif cmd.startswith("soh "):
                return "SOH: 99%\n$$"
            elif cmd.startswith("stat "):
                return stat_output
            return "$$"

        self.client.send_command = mock_send_command

        telemetry = self.client.poll_telemetry()
        self.assertIsNotNone(telemetry)
        self.assertEqual(telemetry.unit_telemetries[1].cycle_count, 87)
        self.assertEqual(telemetry.unit_telemetries[1].cell_voltages_mv, [3328.0, 3329.0])


if __name__ == "__main__":
    unittest.main()
