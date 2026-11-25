"""Home Assistant MQTT Discovery payload builder."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .config import AppConfig
from .parser import UnitInfo


class HomeAssistantDiscovery:
    """Builds Home Assistant MQTT Auto-Discovery configuration payloads."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.prefix = config.mqtt.ha_discovery_prefix
        self.topic_prefix = config.mqtt.topic_prefix
        self.avail_topic = f"{self.topic_prefix}/status"

    def get_stack_state_topic(self) -> str:
        return f"{self.topic_prefix}/stack/state"

    def get_unit_state_topic(self, unit_id: int) -> str:
        return f"{self.topic_prefix}/unit/{unit_id}/state"

    def build_all_discovery_messages(
        self,
        battery_count: Optional[int] = None,
        unit_infos: Optional[Dict[int, UnitInfo]] = None,
        cell_count: int = 15,
    ) -> List[tuple[str, str]]:
        """
        Generate (topic, payload) pairs for all stack and unit entities.
        """
        count = (
            battery_count
            if battery_count is not None and battery_count > 0
            else (self.config.polling.battery_count if self.config.polling.battery_count > 0 else 4)
        )
        messages: List[tuple[str, str]] = []
        infos = unit_infos or {}

        # 1. Master Stack Entities
        stack_entities = self._build_stack_discovery(count)
        for topic, payload_dict in stack_entities:
            messages.append((topic, json.dumps(payload_dict, ensure_ascii=False)))

        # 2. Individual Unit Entities (1 to count)
        for unit_id in range(1, count + 1):
            info = infos.get(unit_id, UnitInfo(unit_id=unit_id))
            unit_cell_count = info.cell_count if info.cell_count and info.cell_count > 0 else cell_count
            unit_entities = self._build_unit_discovery(unit_id, info, unit_cell_count)
            for topic, payload_dict in unit_entities:
                messages.append((topic, json.dumps(payload_dict, ensure_ascii=False)))

        return messages

    def build_cleanup_discovery_messages(
        self,
        configured_count: int,
        max_count: int = 16,
        cell_count: int = 15,
    ) -> List[tuple[str, str]]:
        """
        Generate empty payload MQTT discovery messages (topic, "") to instruct Home Assistant
        to remove any previously registered excess unit entities (e.g. units 5..16 when configured for 4).
        """
        cleanup_messages: List[tuple[str, str]] = []
        if configured_count >= max_count:
            return cleanup_messages

        for unit_id in range(configured_count + 1, max_count + 1):
            unit_entities = self._build_unit_discovery(unit_id, UnitInfo(unit_id=unit_id), cell_count)
            for topic, _ in unit_entities:
                cleanup_messages.append((topic, ""))

        return cleanup_messages

    def _build_stack_discovery(self, battery_count: int) -> List[tuple[str, Dict[str, Any]]]:
        """Build discovery entries for the aggregated Master Stack device."""
        device_id = "pylontech_battery_stack"
        state_topic = self.get_stack_state_topic()
        device_dict = {
            "identifiers": [device_id],
            "name": "Pylontech Battery Stack",
            "model": f"US2000 ({battery_count}-Pack Stack)",
            "manufacturer": "Pylontech",
            "sw_version": "1.0.0",
        }

        entities: List[tuple[str, Dict[str, Any]]] = []

        # Stack Sensors
        sensor_definitions = [
            {
                "id": "stack_state",
                "name": "State",
                "val_tpl": "{{ value_json.stack_state }}",
                "icon": "mdi:battery-heart-variant",
            },
            {
                "id": "total_voltage",
                "name": "Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "V",
                "val_tpl": "{{ value_json.total_voltage_v }}",
            },
            {
                "id": "total_current",
                "name": "Current",
                "dev_cla": "current",
                "stat_cla": "measurement",
                "unit": "A",
                "val_tpl": "{{ value_json.total_current_a }}",
            },
            {
                "id": "total_power",
                "name": "Power",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "unit": "W",
                "val_tpl": "{{ value_json.total_power_w }}",
            },
            {
                "id": "soc",
                "name": "State of Charge (SoC)",
                "dev_cla": "battery",
                "stat_cla": "measurement",
                "unit": "%",
                "val_tpl": "{{ value_json.soc_percent }}",
            },
            {
                "id": "min_soc",
                "name": "Minimum SoC",
                "dev_cla": "battery",
                "stat_cla": "measurement",
                "unit": "%",
                "val_tpl": "{{ value_json.min_soc_percent }}",
            },
            {
                "id": "max_soc",
                "name": "Maximum SoC",
                "dev_cla": "battery",
                "stat_cla": "measurement",
                "unit": "%",
                "val_tpl": "{{ value_json.max_soc_percent }}",
            },
            {
                "id": "min_cell_voltage",
                "name": "Lowest Cell Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.min_cell_voltage_mv }}",
                "icon": "mdi:battery-arrow-down-outline",
            },
            {
                "id": "max_cell_voltage",
                "name": "Highest Cell Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.max_cell_voltage_mv }}",
                "icon": "mdi:battery-arrow-up-outline",
            },
            {
                "id": "cell_delta",
                "name": "Cell Delta (Balance)",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.cell_delta_mv }}",
                "icon": "mdi:scale-balance",
            },
            {
                "id": "highest_temp",
                "name": "Highest Temperature",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.highest_temp_c }}",
            },
            {
                "id": "lowest_temp",
                "name": "Lowest Temperature",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.lowest_temp_c }}",
            },
            {
                "id": "total_remaining_capacity",
                "name": "Remaining Capacity",
                "stat_cla": "measurement",
                "unit": "Ah",
                "val_tpl": "{{ value_json.total_remaining_capacity_ah }}",
                "icon": "mdi:battery-high",
            },
            {
                "id": "total_capacity",
                "name": "Total Capacity",
                "unit": "Ah",
                "val_tpl": "{{ value_json.total_capacity_ah }}",
                "icon": "mdi:battery",
            },
            {
                "id": "active_units_count",
                "name": "Active Units Count",
                "stat_cla": "measurement",
                "val_tpl": "{{ value_json.active_units_count }}",
                "icon": "mdi:counter",
            },
        ]

        for s in sensor_definitions:
            topic = f"{self.prefix}/sensor/{device_id}/{s['id']}/config"
            payload: Dict[str, Any] = {
                "name": f"Pylontech Stack {s['name']}",
                "unique_id": f"{device_id}_{s['id']}",
                "state_topic": state_topic,
                "value_template": s["val_tpl"],
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            if "dev_cla" in s:
                payload["device_class"] = s["dev_cla"]
            if "stat_cla" in s:
                payload["state_class"] = s["stat_cla"]
            if "unit" in s:
                payload["unit_of_measurement"] = s["unit"]
            if "icon" in s:
                payload["icon"] = s["icon"]

            entities.append((topic, payload))

        # Stack Binary Sensors
        binary_sensor_definitions = [
            {
                "id": "is_charging",
                "name": "Charging",
                "dev_cla": "battery_charging",
                "val_tpl": "{{ 'ON' if value_json.is_charging else 'OFF' }}",
            },
            {
                "id": "is_discharging",
                "name": "Discharging",
                "dev_cla": "power",
                "val_tpl": "{{ 'ON' if value_json.is_discharging else 'OFF' }}",
                "icon": "mdi:battery-minus-variant",
            },
            {
                "id": "has_warning",
                "name": "Warning",
                "dev_cla": "problem",
                "val_tpl": "{{ 'ON' if value_json.has_warning else 'OFF' }}",
            },
            {
                "id": "has_alarm",
                "name": "Alarm",
                "dev_cla": "problem",
                "val_tpl": "{{ 'ON' if value_json.has_alarm else 'OFF' }}",
            },
        ]

        for bs in binary_sensor_definitions:
            topic = f"{self.prefix}/binary_sensor/{device_id}/{bs['id']}/config"
            payload = {
                "name": f"Pylontech Stack {bs['name']}",
                "unique_id": f"{device_id}_{bs['id']}",
                "state_topic": state_topic,
                "value_template": bs["val_tpl"],
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            if "dev_cla" in bs:
                payload["device_class"] = bs["dev_cla"]
            if "icon" in bs:
                payload["icon"] = bs["icon"]
            entities.append((topic, payload))

        return entities

    def _build_unit_discovery(
        self,
        unit_id: int,
        info: UnitInfo,
        cell_count: int = 15,
    ) -> List[tuple[str, Dict[str, Any]]]:
        """Build discovery entries for an individual battery module."""
        device_id = f"pylontech_unit_{unit_id}"
        state_topic = self.get_unit_state_topic(unit_id)

        device_dict: Dict[str, Any] = {
            "identifiers": [device_id],
            "name": f"Pylontech Battery Unit {unit_id}",
            "model": info.model or "US2000",
            "manufacturer": info.manufacturer or "Pylontech",
            "via_device": "pylontech_battery_stack",
        }
        if info.serial_number and info.serial_number != "Unknown":
            device_dict["serial_number"] = info.serial_number
        if info.firmware_version and info.firmware_version != "Unknown":
            device_dict["sw_version"] = info.firmware_version
        if info.board_version and info.board_version != "Unknown":
            device_dict["hw_version"] = info.board_version

        entities: List[tuple[str, Dict[str, Any]]] = []

        # Standard unit sensors
        unit_sensors = [
            {
                "id": "voltage",
                "name": "Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "V",
                "val_tpl": "{{ value_json.voltage_v }}",
            },
            {
                "id": "current",
                "name": "Current",
                "dev_cla": "current",
                "stat_cla": "measurement",
                "unit": "A",
                "val_tpl": "{{ value_json.current_a }}",
            },
            {
                "id": "power",
                "name": "Power",
                "dev_cla": "power",
                "stat_cla": "measurement",
                "unit": "W",
                "val_tpl": "{{ value_json.power_w }}",
            },
            {
                "id": "soc",
                "name": "SoC",
                "dev_cla": "battery",
                "stat_cla": "measurement",
                "unit": "%",
                "val_tpl": "{{ value_json.soc_percent }}",
            },
            {
                "id": "soh",
                "name": "SOH",
                "stat_cla": "measurement",
                "unit": "%",
                "val_tpl": "{{ value_json.soh_percent if value_json.soh_percent is not none else '' }}",
                "icon": "mdi:heart-pulse",
            },
            {
                "id": "cycles",
                "name": "Cycle Count",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.cycle_count if value_json.cycle_count is not none else '' }}",
                "icon": "mdi:sync",
            },
            {
                "id": "remaining_capacity",
                "name": "Remaining Capacity",
                "stat_cla": "measurement",
                "unit": "Ah",
                "val_tpl": "{{ value_json.remaining_capacity_ah if value_json.remaining_capacity_ah is not none else '' }}",
                "icon": "mdi:battery-high",
            },
            {
                "id": "total_capacity",
                "name": "Total Capacity",
                "unit": "Ah",
                "val_tpl": "{{ value_json.total_capacity_ah if value_json.total_capacity_ah is not none else '' }}",
                "icon": "mdi:battery",
            },
            {
                "id": "temperature",
                "name": "Temperature",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.temperature_c }}",
            },
            {
                "id": "bms_temperature",
                "name": "BMS Temperature",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.bms_temperature_c if value_json.bms_temperature_c is not none else value_json.temperature_c }}",
            },
            {
                "id": "temp_low",
                "name": "Temperature Lowest",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.temp_low_c }}",
            },
            {
                "id": "temp_high",
                "name": "Temperature Highest",
                "dev_cla": "temperature",
                "stat_cla": "measurement",
                "unit": "°C",
                "val_tpl": "{{ value_json.temp_high_c }}",
            },
            {
                "id": "cell_low_volt",
                "name": "Lowest Cell Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.volt_low_mv }}",
                "icon": "mdi:battery-arrow-down-outline",
            },
            {
                "id": "cell_high_volt",
                "name": "Highest Cell Voltage",
                "dev_cla": "voltage",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.volt_high_mv }}",
                "icon": "mdi:battery-arrow-up-outline",
            },
            {
                "id": "cell_delta",
                "name": "Cell Delta",
                "stat_cla": "measurement",
                "unit": "mV",
                "val_tpl": "{{ value_json.cell_delta_mv }}",
                "icon": "mdi:scale-balance",
            },
            {
                "id": "base_state",
                "name": "Base State",
                "val_tpl": "{{ value_json.base_state }}",
                "icon": "mdi:information-outline",
            },
            {
                "id": "coulomb_state",
                "name": "Coulomb State",
                "val_tpl": "{{ value_json.coulomb_state }}",
                "icon": "mdi:information-outline",
            },
            {
                "id": "soh_status",
                "name": "SOH Status",
                "val_tpl": "{{ value_json.soh_status if value_json.soh_status is not none else '' }}",
                "icon": "mdi:heart-pulse",
            },
            {
                "id": "max_charge_current",
                "name": "Max Charge Current",
                "dev_cla": "current",
                "stat_cla": "measurement",
                "unit": "A",
                "val_tpl": "{{ value_json.max_charge_current_a if value_json.max_charge_current_a is not none else '' }}",
            },
            {
                "id": "max_discharge_current",
                "name": "Max Discharge Current",
                "dev_cla": "current",
                "stat_cla": "measurement",
                "unit": "A",
                "val_tpl": "{{ value_json.max_discharge_current_a if value_json.max_discharge_current_a is not none else '' }}",
            },
            {
                "id": "discharged_capacity",
                "name": "Lifetime Discharged Capacity",
                "stat_cla": "total_increasing",
                "unit": "Ah",
                "val_tpl": "{{ value_json.discharged_capacity_ah if value_json.discharged_capacity_ah is not none else '' }}",
                "icon": "mdi:battery-arrow-down",
            },
            {
                "id": "charge_count",
                "name": "Charge Count",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.charge_count if value_json.charge_count is not none else '' }}",
                "icon": "mdi:counter",
            },
            {
                "id": "discharge_count",
                "name": "Discharge Count",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.discharge_count if value_json.discharge_count is not none else '' }}",
                "icon": "mdi:counter",
            },
            {
                "id": "coc_times",
                "name": "Charge Over-Current Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.coc_times if value_json.coc_times is not none else '' }}",
                "icon": "mdi:alert-circle-outline",
            },
            {
                "id": "doc_times",
                "name": "Discharge Over-Current Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.doc_times if value_json.doc_times is not none else '' }}",
                "icon": "mdi:alert-circle-outline",
            },
            {
                "id": "sc_times",
                "name": "Short Circuit Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.sc_times if value_json.sc_times is not none else '' }}",
                "icon": "mdi:alert-octagon-outline",
            },
            {
                "id": "ht_count",
                "name": "High Temp Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.ht_count if value_json.ht_count is not none else '' }}",
                "icon": "mdi:thermometer-alert",
            },
            {
                "id": "lt_count",
                "name": "Low Temp Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.lt_count if value_json.lt_count is not none else '' }}",
                "icon": "mdi:thermometer-alert",
            },
            {
                "id": "lv_count",
                "name": "Low Voltage Events",
                "stat_cla": "total_increasing",
                "val_tpl": "{{ value_json.lv_count if value_json.lv_count is not none else '' }}",
                "icon": "mdi:battery-alert",
            },
            {
                "id": "bv_state",
                "name": "Balance Voltage State",
                "val_tpl": "{{ value_json.bv_state if value_json.bv_state is not none else '' }}",
                "icon": "mdi:information-outline",
            },
            {
                "id": "bt_state",
                "name": "Balance Temp State",
                "val_tpl": "{{ value_json.bt_state if value_json.bt_state is not none else '' }}",
                "icon": "mdi:information-outline",
            },
        ]

        for s in unit_sensors:
            topic = f"{self.prefix}/sensor/{device_id}/{s['id']}/config"
            payload: Dict[str, Any] = {
                "name": f"Unit {unit_id} {s['name']}",
                "unique_id": f"{device_id}_{s['id']}",
                "state_topic": state_topic,
                "value_template": s["val_tpl"],
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            if "dev_cla" in s:
                payload["device_class"] = s["dev_cla"]
            if "stat_cla" in s:
                payload["state_class"] = s["stat_cla"]
            if "unit" in s:
                payload["unit_of_measurement"] = s["unit"]
            if "icon" in s:
                payload["icon"] = s["icon"]
            entities.append((topic, payload))

        # Individual Cell Voltage & Temperature Sensors (1 to cell_count, typically 15 for US2000)
        for cell_idx in range(1, cell_count + 1):
            c_id = f"cell_{cell_idx}_voltage"
            topic = f"{self.prefix}/sensor/{device_id}/{c_id}/config"
            payload = {
                "name": f"Unit {unit_id} Cell {cell_idx} Voltage",
                "unique_id": f"{device_id}_{c_id}",
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.cell_voltages_mv[{cell_idx - 1}] if value_json.cell_voltages_mv | length >= {cell_idx} else '' }}}}",
                "device_class": "voltage",
                "state_class": "measurement",
                "unit_of_measurement": "mV",
                "icon": "mdi:battery-outline",
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            entities.append((topic, payload))

            t_id = f"cell_{cell_idx}_temperature"
            t_topic = f"{self.prefix}/sensor/{device_id}/{t_id}/config"
            t_payload = {
                "name": f"Unit {unit_id} Cell {cell_idx} Temperature",
                "unique_id": f"{device_id}_{t_id}",
                "state_topic": state_topic,
                "value_template": f"{{{{ value_json.cell_temperatures_c[{cell_idx - 1}] if value_json.cell_temperatures_c | length >= {cell_idx} else '' }}}}",
                "device_class": "temperature",
                "state_class": "measurement",
                "unit_of_measurement": "°C",
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            entities.append((t_topic, t_payload))

        # Unit Binary Sensors (Warnings / Faults)
        unit_binary_sensors = [
            {
                "id": "voltage_warning",
                "name": "Voltage Warning",
                "dev_cla": "problem",
                "val_tpl": "{{ 'OFF' if value_json.voltage_state in ['Normal', 'Idle', ''] else 'ON' }}",
            },
            {
                "id": "current_warning",
                "name": "Current Warning",
                "dev_cla": "problem",
                "val_tpl": "{{ 'OFF' if value_json.current_state in ['Normal', 'Idle', ''] else 'ON' }}",
            },
            {
                "id": "temp_warning",
                "name": "Temperature Warning",
                "dev_cla": "problem",
                "val_tpl": "{{ 'OFF' if value_json.temp_state in ['Normal', 'Idle', ''] else 'ON' }}",
            },
        ]

        for bs in unit_binary_sensors:
            topic = f"{self.prefix}/binary_sensor/{device_id}/{bs['id']}/config"
            payload = {
                "name": f"Unit {unit_id} {bs['name']}",
                "unique_id": f"{device_id}_{bs['id']}",
                "state_topic": state_topic,
                "value_template": bs["val_tpl"],
                "availability_topic": self.avail_topic,
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": device_dict,
            }
            if "dev_cla" in bs:
                payload["device_class"] = bs["dev_cla"]
            entities.append((topic, payload))

        return entities
