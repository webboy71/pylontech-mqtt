"""Serial client for Pylontech US2000 interactive console CLI."""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional
try:
    import serial
except ImportError:
    serial = None

from .config import AppConfig
from .parser import (
    BatteryTelemetry,
    StackTelemetry,
    UnitInfo,
    aggregate_stack_telemetry,
    parse_bat_output,
    parse_info_output,
    parse_pwr_output,
    parse_soh_details,
    parse_stat_details,
)

logger = logging.getLogger(__name__)


class PylontechSerialClient:
    """Manages serial communication with the Pylontech Console port."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.serial_cfg = config.serial
        self.polling_cfg = config.polling
        self._serial: Optional[Any] = None
        self._is_connected = False
        self._unit_infos: Dict[int, UnitInfo] = {}
        self._last_info_poll_time = 0.0

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self._serial is not None and getattr(self._serial, "is_open", False)

    def connect(self) -> bool:
        """Attempt to open the serial port and synchronize with the console."""
        if self.is_connected:
            return True

        if serial is None:
            logger.error("pyserial package is not installed. Please install pyserial.")
            return False

        logger.info(
            "Connecting to Pylontech serial port %s at %d baud...",
            self.serial_cfg.port,
            self.serial_cfg.baudrate,
        )
        try:
            self._serial = serial.Serial(
                port=self.serial_cfg.port,
                baudrate=self.serial_cfg.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.serial_cfg.timeout,
                write_timeout=self.serial_cfg.timeout,
            )
            self._is_connected = True
            time.sleep(0.2)
            self._sync_prompt()
            logger.info("Successfully connected to Pylontech console.")
            return True
        except Exception as e:
            logger.error("Failed to open serial port %s: %s", self.serial_cfg.port, e)
            self._close()
            return False

    def _close(self) -> None:
        self._is_connected = False
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def disconnect(self) -> None:
        """Explicitly disconnect from serial port."""
        logger.info("Disconnecting serial port...")
        self._close()

    def fetch_bms_logs(self) -> Dict[str, str]:
        """Fetch raw BMS event/fault logs ('log' and 'datalist event 0')."""
        if not self.is_connected:
            if not self.connect():
                return {}

        logs: Dict[str, str] = {}
        for cmd in ("log", "datalist event 0"):
            try:
                logs[cmd] = self.send_command(cmd, timeout=max(self.serial_cfg.timeout, 5.0))
            except Exception as e:
                logs[cmd] = f"Error running '{cmd}': {e}"
        return logs

    def _sync_prompt(self) -> None:
        """Send newline to wake/synchronize the console prompt."""
        if not self._serial:
            return
        try:
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
            self._serial.write(b"\r\n")
            time.sleep(0.3)
            # Read whatever comes back
            _ = self._serial.read(self._serial.in_waiting or 1)
        except Exception as e:
            logger.debug("Prompt sync notice: %s", e)

    def send_command(self, cmd: str, timeout: Optional[float] = None) -> str:
        """
        Send a console command and read until response terminator ($$, pylon>, or timeout).
        """
        if not self.is_connected or not self._serial:
            raise ConnectionError("Serial port is not connected")

        t_out = timeout or self.serial_cfg.timeout
        cmd_str = cmd.strip() + "\r\n"
        cmd_bytes = cmd_str.encode("ascii", errors="ignore")

        try:
            # Clear stale bytes from buffer before sending
            self._serial.reset_input_buffer()
            self._serial.write(cmd_bytes)
            self._serial.flush()

            start_time = time.time()
            response_chunks: List[bytes] = []

            while (time.time() - start_time) < t_out:
                if self._serial.in_waiting > 0:
                    chunk = self._serial.read(self._serial.in_waiting)
                    response_chunks.append(chunk)
                    full_text = b"".join(response_chunks).decode("ascii", errors="ignore")

                    # Check if command has completed
                    if "$$" in full_text or "pylon>" in full_text or "Command completed" in full_text:
                        # Give a tiny pause to catch trailing prompt if any
                        time.sleep(0.05)
                        if self._serial.in_waiting > 0:
                            response_chunks.append(self._serial.read(self._serial.in_waiting))
                        break
                else:
                    time.sleep(0.05)

            full_response = b"".join(response_chunks).decode("ascii", errors="ignore")
            logger.debug("Command '%s' response:\n%s", cmd.strip(), full_response)
            return full_response

        except (getattr(serial, "SerialException", OSError), OSError) as e:
            logger.error("Serial error while executing command '%s': %s", cmd, e)
            self._close()
            raise

    def fetch_unit_info(self, unit_id: int) -> UnitInfo:
        """Fetch static device info (serial number, model, firmware) for a unit."""
        try:
            raw = self.send_command(f"info {unit_id}")
            info = parse_info_output(raw, unit_id)
            # If serial number is still Unknown, try sending plain 'info' or 'barcode'
            if info.serial_number == "Unknown":
                raw_info = self.send_command("info")
                info = parse_info_output(raw_info, unit_id)
            return info
        except Exception as e:
            logger.warning("Failed to fetch info for unit %d: %s", unit_id, e)
            return UnitInfo(unit_id=unit_id)

    def refresh_all_unit_infos(self, count: int) -> Dict[int, UnitInfo]:
        """Fetch info for all units and cache them."""
        new_infos: Dict[int, UnitInfo] = {}
        for u in range(1, count + 1):
            info = self.fetch_unit_info(u)
            new_infos[u] = info
        self._unit_infos = new_infos
        self._last_info_poll_time = time.time()
        return self._unit_infos

    def poll_telemetry(self) -> Optional[StackTelemetry]:
        """
        Poll real-time telemetry from all connected batteries:
        1. Send 'pwr' for stack & pack overview
        2. Send 'bat <id>' for each battery to get individual cell voltages
        3. Send 'soh <id>' if available
        4. Aggregate into StackTelemetry
        """
        if not self.is_connected:
            if not self.connect():
                return None

        try:
            # 1. Fetch 'pwr' table
            raw_pwr = self.send_command("pwr")
            pwr_data = parse_pwr_output(raw_pwr)

            # Determine number of batteries
            if self.polling_cfg.battery_count > 0:
                target_count = self.polling_cfg.battery_count
            else:
                # Auto-detection mode (battery_count <= 0)
                present_units = [
                    u_id
                    for u_id, d in pwr_data.items()
                    if d.get("voltage_v", 0.0) > 10.0
                    or str(d.get("base_state", "")).lower() not in ("absent", "not connect", "offline", "-", "", "none")
                ]
                target_count = max(present_units) if present_units else max(len(pwr_data), 1)

            # Refresh static info if not cached or expired
            now = time.time()
            if not self._unit_infos or (now - self._last_info_poll_time) > self.polling_cfg.info_interval_seconds:
                logger.info("Refreshing static unit info for %d battery units...", target_count)
                self.refresh_all_unit_infos(target_count)

            telemetries: Dict[int, BatteryTelemetry] = {}

            # Process each unit
            for u_id in range(1, target_count + 1):
                # Start with pwr row or default
                row_dict = pwr_data.get(u_id, {"unit_id": u_id})
                u_telem = BatteryTelemetry(
                    unit_id=u_id,
                    voltage_v=row_dict.get("voltage_v", 0.0),
                    current_a=row_dict.get("current_a", 0.0),
                    power_w=row_dict.get("power_w", 0.0),
                    temperature_c=row_dict.get("temperature_c", 0.0),
                    temp_low_c=row_dict.get("temp_low_c", 0.0),
                    temp_high_c=row_dict.get("temp_high_c", 0.0),
                    volt_low_mv=row_dict.get("volt_low_mv", 0.0),
                    volt_high_mv=row_dict.get("volt_high_mv", 0.0),
                    cell_delta_mv=row_dict.get("cell_delta_mv", 0.0),
                    soc_percent=row_dict.get("soc_percent", 0.0),
                    base_state=row_dict.get("base_state", "Normal"),
                    voltage_state=row_dict.get("voltage_state", "Normal"),
                    current_state=row_dict.get("current_state", "Normal"),
                    temp_state=row_dict.get("temp_state", "Normal"),
                    coulomb_state=row_dict.get("coulomb_state", "Normal"),
                    bv_state=row_dict.get("bv_state"),
                    bt_state=row_dict.get("bt_state"),
                    lc_state=row_dict.get("lc_state"),
                    battery_time=row_dict.get("battery_time"),
                    last_update=now,
                )

                # 2. Detailed cell voltages & temps via 'bat <id>'
                if self.polling_cfg.read_cell_details:
                    try:
                        raw_bat = self.send_command(f"bat {u_id}")
                        bat_dict = parse_bat_output(raw_bat, u_id)
                        if bat_dict.get("cell_voltages_mv"):
                            u_telem.cell_voltages_mv = bat_dict["cell_voltages_mv"]
                            max_v = max(u_telem.cell_voltages_mv)
                            min_v = min(u_telem.cell_voltages_mv)
                            max_idx = u_telem.cell_voltages_mv.index(max_v) + 1
                            min_idx = u_telem.cell_voltages_mv.index(min_v) + 1
                            u_telem.highest_cell = f"Cell {max_idx:02d} ({max_v:.0f}mV)"
                            u_telem.lowest_cell = f"Cell {min_idx:02d} ({min_v:.0f}mV)"
                        if bat_dict.get("cell_temperatures_c"):
                            u_telem.cell_temperatures_c = bat_dict["cell_temperatures_c"]
                        if bat_dict.get("bms_temperature_c") is not None:
                            u_telem.bms_temperature_c = bat_dict["bms_temperature_c"]
                        if bat_dict.get("cycle_count") is not None:
                            u_telem.cycle_count = bat_dict["cycle_count"]
                        if bat_dict.get("total_capacity_ah") is not None:
                            u_telem.total_capacity_ah = bat_dict["total_capacity_ah"]
                        if bat_dict.get("remaining_capacity_ah") is not None:
                            u_telem.remaining_capacity_ah = bat_dict["remaining_capacity_ah"]
                        if bat_dict.get("soh_percent") is not None:
                            u_telem.soh_percent = bat_dict["soh_percent"]
                        if bat_dict.get("soc_percent") is not None and u_telem.soc_percent == 0.0:
                            u_telem.soc_percent = bat_dict["soc_percent"]
                    except Exception as e:
                        logger.warning("Error reading 'bat %d': %s", u_id, e)

                # 3. Fetch SOH details if not already populated
                if u_telem.soh_percent is None or u_telem.soh_status is None:
                    try:
                        raw_soh = self.send_command(f"soh {u_id}")
                        soh_details = parse_soh_details(raw_soh, u_id)
                        if u_telem.soh_percent is None and soh_details.get("soh_percent") is not None:
                            u_telem.soh_percent = soh_details["soh_percent"]
                        if soh_details.get("soh_status") is not None:
                            u_telem.soh_status = soh_details["soh_status"]
                        if soh_details.get("soh_abnormal_cells") is not None:
                            u_telem.soh_abnormal_cells = soh_details["soh_abnormal_cells"]
                    except Exception:
                        pass

                # 4. Fetch Cycle Count & Statistics via 'stat <id>'
                try:
                    raw_stat = self.send_command(f"stat {u_id}")
                    stat_details = parse_stat_details(raw_stat, u_id)
                    if u_telem.cycle_count is None and stat_details.get("cycle_count") is not None:
                        u_telem.cycle_count = stat_details["cycle_count"]
                    for stat_key in (
                        "charge_count",
                        "discharge_count",
                        "discharged_capacity_ah",
                        "coc_times",
                        "doc_times",
                        "sc_times",
                        "ht_count",
                        "lt_count",
                        "lv_count",
                        "hv_count",
                        "bat_ov_times",
                        "pwr_ov_times",
                    ):
                        if stat_details.get(stat_key) is not None:
                            setattr(u_telem, stat_key, stat_details[stat_key])
                except Exception:
                    pass

                # 5. Populate Total Capacity & Current Limits from cached UnitInfo
                unit_info = self._unit_infos.get(u_id)
                if unit_info:
                    if unit_info.max_charge_current_a is not None:
                        u_telem.max_charge_current_a = unit_info.max_charge_current_a
                    if unit_info.max_discharge_current_a is not None:
                        u_telem.max_discharge_current_a = unit_info.max_discharge_current_a
                if u_telem.total_capacity_ah is None:
                    if unit_info and unit_info.capacity_ah is not None:
                        u_telem.total_capacity_ah = unit_info.capacity_ah
                    elif u_telem.remaining_capacity_ah is not None and u_telem.soc_percent > 0:
                        u_telem.total_capacity_ah = round(
                            u_telem.remaining_capacity_ah / (u_telem.soc_percent / 100.0), 2
                        )

                telemetries[u_id] = u_telem

            # Aggregate into master stack
            stack_telemetry = aggregate_stack_telemetry(telemetries, self._unit_infos)
            return stack_telemetry

        except Exception as e:
            logger.error("Failed to poll telemetry from Pylontech: %s", e)
            self._close()
            return None
