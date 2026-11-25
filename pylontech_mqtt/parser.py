"""Parsers for Pylontech US2000 ASCII console CLI outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class UnitInfo:
    unit_id: int
    manufacturer: str = "Pylontech"
    model: str = "US2000"
    serial_number: str = "Unknown"
    firmware_version: str = "Unknown"
    board_version: str = "Unknown"
    barcode: str = "Unknown"
    capacity_ah: Optional[float] = None


@dataclass
class BatteryTelemetry:
    unit_id: int
    voltage_v: float = 0.0
    current_a: float = 0.0
    power_w: float = 0.0
    temperature_c: float = 0.0
    temp_low_c: float = 0.0
    temp_high_c: float = 0.0
    volt_low_mv: float = 0.0
    volt_high_mv: float = 0.0
    cell_delta_mv: float = 0.0
    soc_percent: float = 0.0
    soh_percent: Optional[float] = None
    base_state: str = "Idle"
    voltage_state: str = "Normal"
    current_state: str = "Normal"
    temp_state: str = "Normal"
    coulomb_state: str = "Normal"
    cycle_count: Optional[int] = None
    remaining_capacity_ah: Optional[float] = None
    total_capacity_ah: Optional[float] = None
    cell_voltages_mv: List[float] = field(default_factory=list)
    cell_temperatures_c: List[float] = field(default_factory=list)
    bms_temperature_c: Optional[float] = None
    last_update: Optional[float] = None


@dataclass
class StackTelemetry:
    total_voltage_v: float = 0.0
    total_current_a: float = 0.0
    total_power_w: float = 0.0
    soc_percent: float = 0.0
    min_soc_percent: float = 0.0
    max_soc_percent: float = 0.0
    min_cell_voltage_mv: float = 0.0
    max_cell_voltage_mv: float = 0.0
    cell_delta_mv: float = 0.0
    highest_temp_c: float = 0.0
    lowest_temp_c: float = 0.0
    total_remaining_capacity_ah: float = 0.0
    total_capacity_ah: float = 0.0
    total_cycles_avg: float = 0.0
    active_units_count: int = 0
    stack_state: str = "Idle"  # "Charging", "Discharging", "Idle", "Warning", "Alarm"
    is_charging: bool = False
    is_discharging: bool = False
    has_warning: bool = False
    has_alarm: bool = False
    unit_telemetries: Dict[int, BatteryTelemetry] = field(default_factory=dict)
    unit_infos: Dict[int, UnitInfo] = field(default_factory=dict)


def clean_console_text(raw_text: str) -> str:
    """Strip ANSI codes, echoes, and command prompts from console output."""
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    text = ansi_escape.sub("", raw_text)
    # Normalize carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def parse_pwr_output(output: str) -> Dict[int, Dict[str, Any]]:
    """
    Parse the multiline table returned by the 'pwr' command.
    Handles space-aligned or pipe-delimited variations across firmware versions.
    """
    cleaned = clean_console_text(output)
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]

    parsed_units: Dict[int, Dict[str, Any]] = {}
    header_found = False
    headers: List[str] = []

    for line in lines:
        if line.startswith("@") or line.startswith("$$") or "pylon>" in line or "Command completed" in line:
            continue

        # Split line by whitespace or pipe
        if "|" in line:
            tokens = [t.strip() for t in line.split("|") if t.strip()]
        else:
            tokens = [t.strip() for t in line.split() if t.strip()]

        if not tokens:
            continue

        # Detect header line
        lower_tokens = [t.lower() for t in tokens]
        if any(h in lower_tokens for h in ["power", "pack", "volt", "curr", "tempr", "coulomb", "base.st"]):
            headers = [t.lower() for t in tokens]
            header_found = True
            continue

        # If header was found and first token is an integer, this is a row
        if header_found and tokens[0].isdigit():
            unit_id = int(tokens[0])
            row_data: Dict[str, Any] = {"unit_id": unit_id}

            # Map based on headers if count matches or is close
            if len(tokens) == len(headers):
                for h, val in zip(headers, tokens):
                    row_data[h] = val
            else:
                # Fallback standard positional mapping for standard US2000 'pwr' format:
                # [0:Power/Index, 1:Volt, 2:Curr, 3:Tempr, 4:Tlow, 5:Thigh, 6:Vlow, 7:Vhigh,
                #  8:Base.St, 9:Volt.St, 10:Curr.St, 11:Temp.St, 12:Coulmb.St/SoC, 13:Coulomb...]
                positional_keys = [
                    "power", "volt", "curr", "tempr", "tlow", "thigh", "vlow", "vhigh",
                    "base.st", "volt.st", "curr.st", "temp.st", "coulmb.st", "coulomb"
                ]
                for idx, key in enumerate(positional_keys):
                    if idx < len(tokens):
                        row_data[key] = tokens[idx]

            # Convert and normalize values
            data = _normalize_pwr_row(row_data, unit_id)
            parsed_units[unit_id] = data

    return parsed_units


def _normalize_pwr_row(row: Dict[str, Any], unit_id: int) -> Dict[str, Any]:
    """Helper to convert raw strings from pwr table to physical floats/strings."""
    result: Dict[str, Any] = {"unit_id": unit_id}

    # Voltage (mV -> V)
    raw_volt = row.get("volt")
    if raw_volt:
        try:
            v_val = float(re.sub(r"[^\d.-]", "", str(raw_volt)))
            # If > 1000, it is in mV (e.g. 49950 -> 49.95V)
            result["voltage_v"] = round(v_val / 1000.0 if v_val > 1000 else v_val, 3)
        except ValueError:
            result["voltage_v"] = 0.0

    # Current (mA -> A)
    raw_curr = row.get("curr")
    if raw_curr is not None:
        try:
            c_val = float(re.sub(r"[^\d.-]", "", str(raw_curr)))
            result["current_a"] = round(c_val / 1000.0 if abs(c_val) > 100 else c_val, 3)
        except ValueError:
            result["current_a"] = 0.0

    # Power (W = V * A)
    v = result.get("voltage_v", 0.0)
    c = result.get("current_a", 0.0)
    result["power_w"] = round(v * c, 2)

    # Temperature (mC -> °C)
    for k_src, k_dst in [("tempr", "temperature_c"), ("tlow", "temp_low_c"), ("thigh", "temp_high_c")]:
        raw_t = row.get(k_src)
        if raw_t:
            try:
                t_val = float(re.sub(r"[^\d.-]", "", str(raw_t)))
                result[k_dst] = round(t_val / 1000.0 if abs(t_val) > 1000 else t_val, 1)
            except ValueError:
                result[k_dst] = 0.0

    # Cell min/max voltages (mV)
    for k_src, k_dst in [("vlow", "volt_low_mv"), ("vhigh", "volt_high_mv")]:
        raw_v = row.get(k_src)
        if raw_v:
            try:
                result[k_dst] = float(re.sub(r"[^\d.-]", "", str(raw_v)))
            except ValueError:
                result[k_dst] = 0.0

    if "volt_high_mv" in result and "volt_low_mv" in result:
        result["cell_delta_mv"] = round(result["volt_high_mv"] - result["volt_low_mv"], 1)

    # SoC (Coulomb)
    # Search for column with % or numeric SoC
    soc_val = None
    for k in ["coulomb", "coulmb.st", "soc"]:
        raw_soc = row.get(k)
        if raw_soc and ("%" in str(raw_soc) or (str(raw_soc).isdigit() and 0 <= int(str(raw_soc)) <= 100)):
            try:
                soc_val = float(re.sub(r"[^\d.-]", "", str(raw_soc)))
                break
            except ValueError:
                pass
    result["soc_percent"] = soc_val if soc_val is not None else 0.0

    # Status strings
    result["base_state"] = str(row.get("base.st", "Normal")).capitalize()
    result["voltage_state"] = str(row.get("volt.st", "Normal")).capitalize()
    result["current_state"] = str(row.get("curr.st", "Normal")).capitalize()
    result["temp_state"] = str(row.get("temp.st", "Normal")).capitalize()
    result["coulomb_state"] = str(row.get("coulmb.st", "Normal")).capitalize()

    return result


def parse_bat_output(output: str, unit_id: int) -> Dict[str, Any]:
    """
    Parse the output of the 'bat <unit_id>' command.
    Supports both the standard Pylontech table format (one row per cell 0..14)
    and key-value summary formats.
    Extracts individual cell voltages (mV), cell temperatures (°C),
    BMS temp, coulomb counts, cycle counts, SOH.
    """
    cleaned = clean_console_text(output)
    result: Dict[str, Any] = {
        "unit_id": unit_id,
        "cell_voltages_mv": [],
        "cell_temperatures_c": [],
    }

    table_header_found = False
    volt_col_idx = 1
    tempr_col_idx = 3

    for line in cleaned.splitlines():
        line = line.strip()
        if not line or line.startswith("@") or line.startswith("$$") or "pylon>" in line or "Command completed" in line:
            continue

        # Detect table header for standard Pylontech 'bat <id>' output:
        # e.g. "Battery  Volt   Curr   Tempr  Base State  Volt. State  Curr. State  Temp. State  Coulomb"
        # or   "Battery | Volt | Curr | Tempr | Base.St | ..."
        if "|" in line:
            tokens = [t.strip() for t in line.split("|") if t.strip()]
        else:
            tokens = [t.strip() for t in line.split() if t.strip()]

        lower_tokens = [t.lower() for t in tokens]
        if (
            not table_header_found
            and ":" not in line
            and any(h in lower_tokens for h in ["battery", "cell"])
            and "volt" in lower_tokens
        ):
            table_header_found = True
            volt_col_idx = lower_tokens.index("volt")
            if "tempr" in lower_tokens:
                tempr_col_idx = lower_tokens.index("tempr")
            elif "temp" in lower_tokens:
                tempr_col_idx = lower_tokens.index("temp")
            continue

        # Parse table data rows (first token is cell index 0..14)
        if table_header_found and tokens and tokens[0].isdigit():
            if len(tokens) > volt_col_idx:
                try:
                    v_mv = float(re.sub(r"[^\d.-]", "", tokens[volt_col_idx]))
                    result["cell_voltages_mv"].append(v_mv)
                except ValueError:
                    pass

            if len(tokens) > tempr_col_idx:
                try:
                    t_raw = float(re.sub(r"[^\d.-]", "", tokens[tempr_col_idx]))
                    result["cell_temperatures_c"].append(
                        round(t_raw / 1000.0 if abs(t_raw) > 1000 else t_raw, 1)
                    )
                except ValueError:
                    pass

            # Extract SoC (%) and remaining capacity (mAH) if present in row
            if "soc_percent" not in result:
                for tok in tokens[4:]:
                    if "%" in tok:
                        try:
                            result["soc_percent"] = float(re.sub(r"[^\d.-]", "", tok))
                            break
                        except ValueError:
                            pass

            if "remaining_capacity_ah" not in result:
                m_cap = re.search(r"(\d+)\s*mAH\b", line, re.IGNORECASE)
                if m_cap:
                    result["remaining_capacity_ah"] = round(float(m_cap.group(1)) / 1000.0, 2)
            continue

        # Key-value format fallbacks:
        # Cell Voltages: e.g. "Cell Volt: 3328 3329 3330 3329 ..." or "Cell Volt(mV): ..."
        if re.search(r"Cell\s+Volt", line, re.IGNORECASE):
            parts = re.split(r"[:=]", line, maxsplit=1)
            if len(parts) == 2:
                nums = re.findall(r"[-+]?\d+", parts[1])
                result["cell_voltages_mv"] = [float(n) for n in nums]

        # Cell Temperatures: e.g. "Cell Temp: 23000 23000 23000 23000" or "Cell Temp(mC): ..."
        elif re.search(r"Cell\s+Temp", line, re.IGNORECASE):
            parts = re.split(r"[:=]", line, maxsplit=1)
            if len(parts) == 2:
                nums = re.findall(r"[-+]?\d+", parts[1])
                result["cell_temperatures_c"] = [
                    round(float(n) / 1000.0 if abs(float(n)) > 1000 else float(n), 1)
                    for n in nums
                ]

        # BMS Temperature: e.g. "BMS Temp: 24000"
        elif re.search(r"BMS\s+Temp", line, re.IGNORECASE):
            nums = re.findall(r"[-+]?\d+", line)
            if nums:
                t = float(nums[0])
                result["bms_temperature_c"] = round(t / 1000.0 if abs(t) > 1000 else t, 1)

        # Cycle count: e.g. "Cycle: 142" or "Cycle count: 142"
        elif re.search(r"Cycle", line, re.IGNORECASE):
            nums = re.findall(r"\d+", line)
            if nums:
                result["cycle_count"] = int(nums[0])

        # Total Coulomb / Capacity: e.g. "Total Coulomb: 50000 mAH" or "Total Coulomb: 50AH"
        elif re.search(r"Total\s+Coulomb", line, re.IGNORECASE):
            nums = re.findall(r"[-+]?\d+", line)
            if nums:
                c_val = float(nums[0])
                # Convert mAh to Ah if > 500
                result["total_capacity_ah"] = round(c_val / 1000.0 if c_val > 500 else c_val, 2)

        # Real Coulomb / Remaining Capacity: e.g. "Real Coulomb: 49000 mAH"
        elif re.search(r"Real\s+Coulomb", line, re.IGNORECASE):
            nums = re.findall(r"[-+]?\d+", line)
            if nums:
                c_val = float(nums[0])
                result["remaining_capacity_ah"] = round(c_val / 1000.0 if c_val > 500 else c_val, 2)

        # SOH: e.g. "SOH: 99%"
        elif re.search(r"\bSOH\b", line, re.IGNORECASE):
            nums = re.findall(r"\d+", line)
            if nums:
                result["soh_percent"] = float(nums[0])

        # Coulomb percentage: e.g. "Coulomb: 98%"
        elif re.search(r"^Coulomb\s*:", line, re.IGNORECASE):
            nums = re.findall(r"\d+", line)
            if nums:
                result["soc_percent"] = float(nums[0])

    # If cell voltages exist, compute min, max and delta
    if result["cell_voltages_mv"]:
        v_min = min(result["cell_voltages_mv"])
        v_max = max(result["cell_voltages_mv"])
        result["volt_low_mv"] = v_min
        result["volt_high_mv"] = v_max
        result["cell_delta_mv"] = round(v_max - v_min, 1)

    return result


def parse_info_output(output: str, unit_id: int) -> UnitInfo:
    """
    Parse the output of the 'info <unit_id>' or 'info' command.
    Extracts manufacturer, model, serial number, firmware versions.
    """
    cleaned = clean_console_text(output)
    info = UnitInfo(unit_id=unit_id)

    for line in cleaned.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue

        parts = line.split(":", 1)
        key = parts[0].strip().lower()
        val = parts[1].strip()

        if "manufacturer" in key:
            info.manufacturer = val or "Pylontech"
        elif "device name" in key or "module name" in key or "model" in key:
            info.model = val or "US2000"
        elif "serial number" in key or "sn" == key:
            info.serial_number = val
        elif "barcode" in key:
            info.barcode = val
            if info.serial_number == "Unknown":
                info.serial_number = val
        elif "main soft version" in key or "firmware" in key:
            info.firmware_version = val
        elif "board version" in key or "hardware" in key:
            info.board_version = val
        elif "specification" in key:
            m_cap = re.search(r"(\d+(?:\.\d+)?)\s*AH\b", val, re.IGNORECASE)
            if m_cap:
                info.capacity_ah = float(m_cap.group(1))

    return info


def parse_soh_output(output: str, unit_id: int) -> Optional[float]:
    """
    Parse output of 'soh <unit_id>' command, returning SOH float (0..100) or None.
    Supports both key-value ('SOH: 99%') and Pylontech cell-table format
    ('Battery  Voltage  SOHCount  SOHStatus').
    """
    cleaned = clean_console_text(output)
    table_header_found = False
    status_col_idx = 3
    total_cells = 0
    normal_cells = 0

    for line in cleaned.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("@") or line_stripped.startswith("$$") or "pylon>" in line_stripped or "Command completed" in line_stripped:
            continue

        # Match 'SOH: 99%' or 'SOH = 99%' or 'SOH: 99'
        m = re.search(r"\bsoh\b\s*[:=]\s*(\d+)", line_stripped, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if 0 <= val <= 100:
                return val
        # Also check for 'SOH 99%' pattern
        m2 = re.search(r"\bsoh\b.*?(\d+)%", line_stripped, re.IGNORECASE)
        if m2 and not line_stripped.lower().startswith("soh "):
            val = float(m2.group(1))
            if 0 <= val <= 100:
                return val

        # Detect Pylontech 'soh <id>' table header:
        # e.g. "Power 1. Battery  Voltage  SOHCount  SOHStatus"
        # or   "Battery | Voltage | SOHCount | SOHStatus"
        if "|" in line_stripped:
            tokens = [t.strip() for t in line_stripped.split("|") if t.strip()]
        else:
            tokens = [t.strip() for t in re.split(r"\s+", line_stripped) if t.strip() and t.strip() != "-"]

        lower_tokens = [t.lower() for t in tokens]
        if not table_header_found and "sohstatus" in lower_tokens:
            table_header_found = True
            # On data rows, columns are [cell_idx, voltage, soh_count, soh_status]
            # Header may have leading "Power 1." prefix, so find offset from "battery"
            if "battery" in lower_tokens:
                bat_idx = lower_tokens.index("battery")
                status_col_idx = lower_tokens.index("sohstatus") - bat_idx
            else:
                status_col_idx = 3
            continue

        if table_header_found and tokens and tokens[0].isdigit():
            if len(tokens) > status_col_idx:
                total_cells += 1
                if tokens[status_col_idx].lower() == "normal":
                    normal_cells += 1

    if total_cells > 0:
        return round(100.0 * normal_cells / total_cells, 1)
    return None


def parse_stat_output(output: str, unit_id: int) -> Optional[int]:
    """Parse output of 'stat <unit_id>' command, returning cycle count int or None."""
    cleaned = clean_console_text(output)
    for line in cleaned.splitlines():
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("@") or line_stripped.startswith("$$") or "pylon>" in line_stripped:
            continue
        # Match 'CYCLE Times : 11', 'Cycle count: 142', 'Cycles: 142', or 'Cycle: 142'
        m = re.search(r"\bcycle(?:\s*times|\s*count|s)?\s*[:=]\s*(\d+)", line_stripped, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None



def aggregate_stack_telemetry(
    unit_telemetries: Dict[int, BatteryTelemetry],
    unit_infos: Dict[int, UnitInfo],
) -> StackTelemetry:
    """
    Combine individual unit telemetries into master stack totals.
    - Stack Voltage: Average bus voltage across parallel packs (or master unit voltage)
    - Stack Current: Sum of all unit currents (A)
    - Stack Power: Total stack instantaneous power (W)
    - Stack SoC: Mean and Min SoC (%)
    - Min/Max Cell Voltage: Across all 60 cells (15 cells * 4 units)
    - Cell Delta: Peak-to-peak difference in mV across entire stack
    - Temperature: Min and Max cell temperatures
    - Alarms/Warnings: Aggregated boolean status
    """
    stack = StackTelemetry()
    stack.unit_telemetries = unit_telemetries
    stack.unit_infos = unit_infos

    active_units = [u for u in unit_telemetries.values() if u.voltage_v > 10.0]
    stack.active_units_count = len(active_units)

    if not active_units:
        return stack

    # Voltages & Currents
    voltages = [u.voltage_v for u in active_units]
    currents = [u.current_a for u in active_units]
    powers = [u.power_w for u in active_units]
    socs = [u.soc_percent for u in active_units]

    stack.total_voltage_v = round(sum(voltages) / len(voltages), 2)
    stack.total_current_a = round(sum(currents), 2)
    stack.total_power_w = round(sum(powers), 2)

    stack.soc_percent = round(sum(socs) / len(socs), 1)
    stack.min_soc_percent = min(socs)
    stack.max_soc_percent = max(socs)

    # Capacities
    rem_caps = [u.remaining_capacity_ah for u in active_units if u.remaining_capacity_ah is not None]
    tot_caps = [u.total_capacity_ah for u in active_units if u.total_capacity_ah is not None]
    if rem_caps:
        stack.total_remaining_capacity_ah = round(sum(rem_caps), 2)
    if tot_caps:
        stack.total_capacity_ah = round(sum(tot_caps), 2)

    # Cycles
    cycles = [u.cycle_count for u in active_units if u.cycle_count is not None]
    if cycles:
        stack.total_cycles_avg = round(sum(cycles) / len(cycles), 1)

    # All cell voltages across all units
    all_cells_mv: List[float] = []
    for u in active_units:
        if u.cell_voltages_mv:
            all_cells_mv.extend(u.cell_voltages_mv)
        elif u.volt_low_mv > 0 and u.volt_high_mv > 0:
            all_cells_mv.append(u.volt_low_mv)
            all_cells_mv.append(u.volt_high_mv)

    if all_cells_mv:
        stack.min_cell_voltage_mv = min(all_cells_mv)
        stack.max_cell_voltage_mv = max(all_cells_mv)
        stack.cell_delta_mv = round(stack.max_cell_voltage_mv - stack.min_cell_voltage_mv, 1)

    # All temperatures
    all_temps: List[float] = []
    for u in active_units:
        if u.cell_temperatures_c:
            all_temps.extend(u.cell_temperatures_c)
        if u.temperature_c:
            all_temps.append(u.temperature_c)
        if u.temp_low_c:
            all_temps.append(u.temp_low_c)
        if u.temp_high_c:
            all_temps.append(u.temp_high_c)

    if all_temps:
        stack.highest_temp_c = max(all_temps)
        stack.lowest_temp_c = min(all_temps)

    # State
    if stack.total_current_a > 0.5:
        stack.stack_state = "Charging"
        stack.is_charging = True
    elif stack.total_current_a < -0.5:
        stack.stack_state = "Discharging"
        stack.is_discharging = True
    else:
        stack.stack_state = "Idle"

    # Warnings & Alarms
    has_alarm = False
    has_warn = False
    for u in active_units:
        for st in [u.voltage_state, u.current_state, u.temp_state, u.coulomb_state]:
            if "alarm" in st.lower():
                has_alarm = True
            elif "warn" in st.lower() or "high" in st.lower() or "low" in st.lower():
                has_warn = True

    stack.has_alarm = has_alarm
    stack.has_warning = has_warn
    if has_alarm:
        stack.stack_state = "Alarm"
    elif has_warn and stack.stack_state == "Idle":
        stack.stack_state = "Warning"

    return stack
