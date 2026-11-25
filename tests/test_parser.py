"""Unit tests for Pylontech console ASCII CLI parsers."""

import unittest
from pylontech_mqtt.parser import (
    BatteryTelemetry,
    UnitInfo,
    aggregate_stack_telemetry,
    parse_bat_output,
    parse_info_output,
    parse_pwr_output,
    parse_soh_details,
    parse_soh_output,
    parse_stat_details,
    parse_stat_output,
)

SAMPLE_PWR_OUTPUT = """
@
Power Volt   Curr   Tempr Tlow  Thigh Vlow  Vhigh Base.St Volt.St Curr.St Temp.St Coulmb.St Coulomb Base.Pr
1     49950  -1250  23000 22000 24000 3328  3332  Dischg  Normal  Normal  Normal  Normal    98%     Normal
2     49960  -1240  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
3     49950  -1230  23000 22000 24000 3328  3330  Dischg  Normal  Normal  Normal  Normal    98%     Normal
4     49960  -1250  23000 22000 24000 3329  3331  Dischg  Normal  Normal  Normal  Normal    98%     Normal
Command completed successfully
$$
pylon>
"""

SAMPLE_PWR_PIPE_OUTPUT = """
@
Power | Volt | Curr | Tempr | Tlow | Thigh | Vlow | Vhigh | Base.St | Volt.St | Curr.St | Temp.St | Coulomb | Time | B.V.St | B.T.St
1     | 50120| 2500 | 25000 | 24000| 26000 | 3340 | 3345  | Charge  | Normal  | Normal  | Normal  | 75%     | 0    | Normal | Normal
2     | 50110| 2490 | 25000 | 24000| 26000 | 3339 | 3344  | Charge  | Normal  | Normal  | Normal  | 75%     | 0    | Normal | Normal
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

SAMPLE_BAT_TABLE_OUTPUT = """
@
Battery  Volt   Curr   Tempr  Base State  Volt. State  Curr. State  Temp. State  Coulomb
0        3328   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
1        3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
2        3330   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
3        3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
4        3331   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
5        3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
6        3330   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
7        3331   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
8        3328   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
9        3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
10       3330   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
11       3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
12       3331   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
13       3329   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
14       3330   -1250  23000  Dischg      Normal       Normal       Normal       98%     49000 mAH
Command completed successfully
$$
pylon>
"""

SAMPLE_BAT_PIPE_TABLE_OUTPUT = """
@
Battery | Volt | Curr | Tempr | Base.St | Volt.St | Curr.St | Temp.St | Coulomb
0       | 3340 | 2500 | 25000 | Charge  | Normal  | Normal  | Normal  | 75%
1       | 3345 | 2500 | 25000 | Charge  | Normal  | Normal  | Normal  | 75%
Command completed successfully
$$
pylon>
"""

SAMPLE_INFO_OUTPUT = """
@
Device address      : 1
Manufacturer        : Pylontech
Device name         : US2000
Board version       : PHOB01_V2.8
Main Soft version   : B65.12
Soft  version       : V1.3
Boot  version       : V1.2
Comm version        : V2.0
Serial Number       : PPTA012345678901
Barcode             : PPTA012345678901
Specification       : 48V/50AH
Cell Number         : 15
Max Charge Curr     : 25000mA
Max Dischg Curr     : -50000mA
Command completed successfully
$$
pylon>
"""

SAMPLE_SOH_OUTPUT = """
@
soh 1
Battery 1:
SOH: 99%
Command completed successfully
$$
pylon>
"""

SAMPLE_SOH_TABLE_OUTPUT = """
@
Power 1. Battery  Voltage  SOHCount  SOHStatus
0                 3302     0         Normal
1                 3303     0         Normal
2                 3303     0         Normal
3                 3302     0         Normal
4                 3303     0         Normal
5                 3302     0         Normal
6                 3303     0         Normal
7                 3303     0         Normal
8                 3303     0         Normal
9                 3303     0         Normal
10                3304     0         Normal
11                3304     0         Normal
12                3305     0         Normal
13                3304     0         Normal
14                3304     0         Normal
Command completed successfully.
$$
pylon>
"""

SAMPLE_STAT_OUTPUT = """
@
Device address 1.
Data Items : 628
HisData Items : 2044
Charge Cnt. : 0
Discharge Cnt. : 761
Charge Times : 35859
Status Cnt. : 760
Idle Times : 38704
COC Times : 0
DOC Times : 0
COCA Times : 0
DOCA Times : 0
SC Times : 0
CYCLE Times : 142
Pwr Percent : 67
Pwr Coulomb : 120297600
Dsg Cap : 4542819
HT Cnt : 0
LT Cnt : 0
LV Cnt : 17416
HV Cnt : 5
Bat OV Times : 3
Pwr OV Times : 1
Command completed successfully.
$$
pylon>
"""


class TestParser(unittest.TestCase):

    def test_parse_pwr_output_space(self):
        result = parse_pwr_output(SAMPLE_PWR_OUTPUT)
        self.assertEqual(len(result), 4)
        self.assertIn(1, result)
        self.assertIn(4, result)

        u1 = result[1]
        self.assertEqual(u1["unit_id"], 1)
        self.assertEqual(u1["voltage_v"], 49.95)
        self.assertEqual(u1["current_a"], -1.25)
        self.assertEqual(u1["power_w"], round(49.95 * -1.25, 2))
        self.assertEqual(u1["temperature_c"], 23.0)
        self.assertEqual(u1["temp_low_c"], 22.0)
        self.assertEqual(u1["temp_high_c"], 24.0)
        self.assertEqual(u1["volt_low_mv"], 3328.0)
        self.assertEqual(u1["volt_high_mv"], 3332.0)
        self.assertEqual(u1["cell_delta_mv"], 4.0)
        self.assertEqual(u1["soc_percent"], 98.0)
        self.assertEqual(u1["base_state"], "Dischg")
        self.assertEqual(u1["voltage_state"], "Normal")

    def test_parse_pwr_output_pipe(self):
        result = parse_pwr_output(SAMPLE_PWR_PIPE_OUTPUT)
        self.assertEqual(len(result), 2)
        u1 = result[1]
        self.assertEqual(u1["voltage_v"], 50.12)
        self.assertEqual(u1["current_a"], 2.5)
        self.assertEqual(u1["power_w"], round(50.12 * 2.5, 2))
        self.assertEqual(u1["base_state"], "Charge")
        self.assertEqual(u1["soc_percent"], 75.0)

    def test_parse_bat_output(self):
        result = parse_bat_output(SAMPLE_BAT_OUTPUT, unit_id=1)
        self.assertEqual(result["unit_id"], 1)
        self.assertEqual(len(result["cell_voltages_mv"]), 15)
        self.assertEqual(result["cell_voltages_mv"][0], 3328.0)
        self.assertEqual(result["cell_voltages_mv"][4], 3331.0)
        self.assertEqual(len(result["cell_temperatures_c"]), 5)
        self.assertEqual(result["cell_temperatures_c"][0], 23.0)
        self.assertEqual(result["bms_temperature_c"], 24.0)
        self.assertEqual(result["cycle_count"], 142)
        self.assertEqual(result["total_capacity_ah"], 50.0)
        self.assertEqual(result["remaining_capacity_ah"], 49.0)
        self.assertEqual(result["soc_percent"], 98.0)
        self.assertEqual(result["volt_low_mv"], 3328.0)
        self.assertEqual(result["volt_high_mv"], 3331.0)
        self.assertEqual(result["cell_delta_mv"], 3.0)

    def test_parse_bat_table_output(self):
        result = parse_bat_output(SAMPLE_BAT_TABLE_OUTPUT, unit_id=1)
        self.assertEqual(result["unit_id"], 1)
        self.assertEqual(len(result["cell_voltages_mv"]), 15)
        self.assertEqual(result["cell_voltages_mv"][0], 3328.0)
        self.assertEqual(result["cell_voltages_mv"][4], 3331.0)
        self.assertEqual(result["cell_voltages_mv"][14], 3330.0)
        self.assertEqual(len(result["cell_temperatures_c"]), 15)
        self.assertEqual(result["cell_temperatures_c"][0], 23.0)
        self.assertEqual(result["soc_percent"], 98.0)
        self.assertEqual(result["remaining_capacity_ah"], 49.0)
        self.assertEqual(result["volt_low_mv"], 3328.0)
        self.assertEqual(result["volt_high_mv"], 3331.0)
        self.assertEqual(result["cell_delta_mv"], 3.0)

    def test_parse_bat_pipe_table_output(self):
        result = parse_bat_output(SAMPLE_BAT_PIPE_TABLE_OUTPUT, unit_id=2)
        self.assertEqual(result["unit_id"], 2)
        self.assertEqual(result["cell_voltages_mv"], [3340.0, 3345.0])
        self.assertEqual(result["cell_temperatures_c"], [25.0, 25.0])
        self.assertEqual(result["soc_percent"], 75.0)
        self.assertEqual(result["volt_low_mv"], 3340.0)
        self.assertEqual(result["volt_high_mv"], 3345.0)
        self.assertEqual(result["cell_delta_mv"], 5.0)

    def test_parse_info_output(self):
        info = parse_info_output(SAMPLE_INFO_OUTPUT, unit_id=1)
        self.assertEqual(info.unit_id, 1)
        self.assertEqual(info.manufacturer, "Pylontech")
        self.assertEqual(info.model, "US2000")
        self.assertEqual(info.serial_number, "PPTA012345678901")
        self.assertEqual(info.firmware_version, "B65.12")
        self.assertEqual(info.board_version, "PHOB01_V2.8")
        self.assertEqual(info.boot_version, "V1.2")
        self.assertEqual(info.comm_version, "V2.0")
        self.assertEqual(info.cell_count, 15)
        self.assertEqual(info.max_charge_current_a, 25.0)
        self.assertEqual(info.max_discharge_current_a, -50.0)
        self.assertEqual(info.capacity_ah, 50.0)

    def test_parse_soh_output(self):
        soh = parse_soh_output(SAMPLE_SOH_OUTPUT, unit_id=1)
        self.assertEqual(soh, 99.0)

    def test_parse_soh_table_output(self):
        soh = parse_soh_output(SAMPLE_SOH_TABLE_OUTPUT, unit_id=1)
        self.assertEqual(soh, 100.0)

    def test_parse_soh_table_output_with_abnormal_cell(self):
        abnormal = SAMPLE_SOH_TABLE_OUTPUT.replace("6                 3303     0         Normal", "6                 3303     13        Abnormal")
        soh = parse_soh_output(abnormal, unit_id=1)
        self.assertEqual(soh, 93.3)

    def test_parse_stat_output(self):
        cycles = parse_stat_output(SAMPLE_STAT_OUTPUT, unit_id=1)
        self.assertEqual(cycles, 142)

    def test_parse_stat_details(self):
        details = parse_stat_details(SAMPLE_STAT_OUTPUT, unit_id=1)
        self.assertEqual(details["cycle_count"], 142)
        self.assertEqual(details["charge_count"], 0)
        self.assertEqual(details["discharge_count"], 761)
        self.assertEqual(details["discharged_capacity_ah"], 4542.82)
        self.assertEqual(details["coc_times"], 0)
        self.assertEqual(details["doc_times"], 0)
        self.assertEqual(details["sc_times"], 0)
        self.assertEqual(details["ht_count"], 0)
        self.assertEqual(details["lt_count"], 0)
        self.assertEqual(details["lv_count"], 17416)
        self.assertEqual(details["hv_count"], 5)
        self.assertEqual(details["bat_ov_times"], 3)
        self.assertEqual(details["pwr_ov_times"], 1)

    def test_parse_soh_details(self):
        details = parse_soh_details(SAMPLE_SOH_TABLE_OUTPUT, unit_id=1)
        self.assertEqual(details["soh_percent"], 100.0)
        self.assertEqual(details["soh_status"], "Normal")
        self.assertEqual(details["soh_abnormal_cells"], 0)

    def test_aggregate_stack_telemetry(self):
        pwr_data = parse_pwr_output(SAMPLE_PWR_OUTPUT)
        bat_data = parse_bat_output(SAMPLE_BAT_OUTPUT, unit_id=1)

        unit_telemetries = {}
        for u_id in range(1, 5):
            row = pwr_data[u_id]
            unit_telemetries[u_id] = BatteryTelemetry(
                unit_id=u_id,
                voltage_v=row["voltage_v"],
                current_a=row["current_a"],
                power_w=row["power_w"],
                temperature_c=row["temperature_c"],
                temp_low_c=row["temp_low_c"],
                temp_high_c=row["temp_high_c"],
                volt_low_mv=row["volt_low_mv"],
                volt_high_mv=row["volt_high_mv"],
                cell_delta_mv=row["cell_delta_mv"],
                soc_percent=row["soc_percent"],
                base_state=row["base_state"],
                cycle_count=140 + u_id,
                total_capacity_ah=50.0,
                remaining_capacity_ah=49.0,
                cell_voltages_mv=bat_data["cell_voltages_mv"],
                cell_temperatures_c=bat_data["cell_temperatures_c"],
            )

        unit_infos = {
            1: UnitInfo(unit_id=1, serial_number="PPTA01", firmware_version="B65.12"),
            2: UnitInfo(unit_id=2, serial_number="PPTA02", firmware_version="B65.12"),
            3: UnitInfo(unit_id=3, serial_number="PPTA03", firmware_version="B65.12"),
            4: UnitInfo(unit_id=4, serial_number="PPTA04", firmware_version="B65.12"),
        }

        stack = aggregate_stack_telemetry(unit_telemetries, unit_infos)

        self.assertEqual(stack.active_units_count, 4)
        self.assertTrue(stack.total_voltage_v in (49.95, 49.96))
        # Total current is -1.25 - 1.24 - 1.23 - 1.25 = -4.97 A
        self.assertEqual(stack.total_current_a, -4.97)
        self.assertEqual(stack.soc_percent, 98.0)
        self.assertEqual(stack.total_capacity_ah, 200.0)
        self.assertEqual(stack.total_remaining_capacity_ah, 196.0)
        self.assertEqual(stack.min_cell_voltage_mv, 3328.0)
        self.assertEqual(stack.max_cell_voltage_mv, 3331.0)
        self.assertEqual(stack.cell_delta_mv, 3.0)
        self.assertEqual(stack.stack_state, "Discharging")
        self.assertTrue(stack.is_discharging)
        self.assertFalse(stack.is_charging)
        self.assertFalse(stack.has_alarm)

    def test_aggregate_stack_charging_state(self):
        unit_telemetries = {
            1: BatteryTelemetry(unit_id=1, voltage_v=51.2, current_a=10.0, power_w=512.0, soc_percent=60.0),
            2: BatteryTelemetry(unit_id=2, voltage_v=51.2, current_a=10.0, power_w=512.0, soc_percent=60.0),
        }
        stack = aggregate_stack_telemetry(unit_telemetries, {})
        self.assertEqual(stack.total_current_a, 20.0)
        self.assertEqual(stack.total_power_w, 1024.0)
        self.assertEqual(stack.stack_state, "Charging")
        self.assertTrue(stack.is_charging)
        self.assertFalse(stack.is_discharging)


if __name__ == "__main__":
    unittest.main()
