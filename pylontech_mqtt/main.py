"""Main entry point for pylontech-mqtt service."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from typing import Optional

from .config import AppConfig, load_config
from .mqtt_publisher import MQTTPublisher
from .serial_client import PylontechSerialClient

logger = logging.getLogger("pylontech_mqtt")


class PylontechDaemon:
    """Coordinates serial polling and MQTT publishing."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.serial_client = PylontechSerialClient(config)
        self.mqtt_publisher = MQTTPublisher(config)
        self._running = False

    def setup_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        def handle_signal(sig: int, frame: Optional[object]) -> None:
            signame = signal.Signals(sig).name
            logger.info("Received termination signal %s. Shutting down...", signame)
            self.stop()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def start(self) -> None:
        """Start the daemon."""
        self._running = True
        self.setup_signal_handlers()

        logger.info("Starting pylontech-mqtt service...")
        logger.info("Serial port: %s (Baud: %d)", self.config.serial.port, self.config.serial.baudrate)
        logger.info("MQTT Broker: %s:%d (Topic: %s)", self.config.mqtt.host, self.config.mqtt.port, self.config.mqtt.topic_prefix)
        logger.info("Polling Interval: %.1f seconds", self.config.polling.interval_seconds)

        # Start MQTT client
        try:
            self.mqtt_publisher.start()
        except Exception as e:
            logger.error("Failed to start MQTT publisher: %s", e)

        # Initial connection to serial
        self.serial_client.connect()

        # Polling loop
        last_poll_time = 0.0
        while self._running:
            now = time.time()
            if (now - last_poll_time) >= self.config.polling.interval_seconds:
                try:
                    telemetry = self.serial_client.poll_telemetry()
                    if telemetry:
                        logger.info(
                            "Polled %d units | Stack: %.2fV | %.2fA | %.1fW | SoC: %.1f%% | State: %s",
                            telemetry.active_units_count,
                            telemetry.total_voltage_v,
                            telemetry.total_current_a,
                            telemetry.total_power_w,
                            telemetry.soc_percent,
                            telemetry.stack_state,
                        )
                        self.mqtt_publisher.publish_telemetry(telemetry)
                    else:
                        logger.warning("No telemetry received. Retrying in %ds...", int(self.config.serial.reconnect_delay))
                        time.sleep(self.config.serial.reconnect_delay)
                except Exception as e:
                    logger.error("Unexpected error during poll cycle: %s", e, exc_info=True)
                    time.sleep(self.config.serial.reconnect_delay)

                last_poll_time = time.time()

            # Small sleep to keep CPU usage negligible
            time.sleep(0.5)

        self._cleanup()

    def stop(self) -> None:
        """Signal the daemon to stop."""
        self._running = False

    def _cleanup(self) -> None:
        """Clean up connections."""
        logger.info("Performing clean shutdown...")
        self.serial_client.disconnect()
        self.mqtt_publisher.stop()
        logger.info("Service stopped cleanly.")

    def run_once(self) -> bool:
        """Run a single test poll and print results without starting daemon."""
        logger.info("Running single test poll from %s...", self.config.serial.port)
        if not self.serial_client.connect():
            logger.error("Could not connect to serial port %s", self.config.serial.port)
            return False

        telemetry = self.serial_client.poll_telemetry()
        if not telemetry:
            logger.error("Failed to read telemetry from batteries.")
            self.serial_client.disconnect()
            return False

        print("\n" + "=" * 60)
        print("  PYLONTECH BATTERY STACK TELEMETRY")
        print("=" * 60)
        print(f"Active Units       : {telemetry.active_units_count}")
        print(f"Stack State        : {telemetry.stack_state}")
        print(f"Stack Voltage      : {telemetry.total_voltage_v:.2f} V")
        print(f"Stack Current      : {telemetry.total_current_a:.2f} A")
        print(f"Stack Power        : {telemetry.total_power_w:.1f} W")
        print(f"Stack SoC          : {telemetry.soc_percent:.1f} % (Min: {telemetry.min_soc_percent:.1f}%, Max: {telemetry.max_soc_percent:.1f}%)")
        print(f"Remaining Capacity : {telemetry.total_remaining_capacity_ah:.1f} Ah / {telemetry.total_capacity_ah:.1f} Ah")
        print(f"Min Cell Voltage   : {telemetry.min_cell_voltage_mv:.1f} mV")
        print(f"Max Cell Voltage   : {telemetry.max_cell_voltage_mv:.1f} mV")
        print(f"Cell Delta         : {telemetry.cell_delta_mv:.1f} mV")
        print(f"Temp Range         : {telemetry.lowest_temp_c:.1f} °C to {telemetry.highest_temp_c:.1f} °C")
        print("-" * 60)

        for u_id, u in telemetry.unit_telemetries.items():
            info = telemetry.unit_infos.get(u_id)
            sn = info.serial_number if info else "Unknown"
            fw = info.firmware_version if info else "Unknown"
            print(f"Unit {u_id} [{sn} | FW: {fw}]:")
            print(f"  Voltage: {u.voltage_v:.2f}V | Current: {u.current_a:.2f}A | Power: {u.power_w:.1f}W | SoC: {u.soc_percent:.0f}%")
            if u.cycle_count is not None:
                print(f"  Cycles: {u.cycle_count} | SOH: {u.soh_percent}% | Temp: {u.temperature_c:.1f}°C")
            if u.cell_voltages_mv:
                cells_str = ", ".join(f"{int(c)}mV" for c in u.cell_voltages_mv)
                print(f"  Cells ({len(u.cell_voltages_mv)}): {cells_str}")
            print(f"  Status: Base={u.base_state}, Volt={u.voltage_state}, Curr={u.current_state}, Temp={u.temp_state}")
            print()

        print("=" * 60)
        self.serial_client.disconnect()
        return True


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Pylontech US2000 to Home Assistant MQTT Gateway")
    parser.add_argument("-c", "--config", help="Path to config.yaml file", default=None)
    parser.add_argument("-p", "--port", help="Serial port (e.g. /dev/ttyUSB0)", default=None)
    parser.add_argument("-m", "--mqtt-host", help="MQTT broker IP address or hostname", default=None)
    parser.add_argument("--test", action="store_true", help="Run once in test mode and print output without loop")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    config = load_config(args.config)
    if args.port:
        config.serial.port = args.port
    if args.mqtt_host:
        config.mqtt.host = args.mqtt_host
    if args.debug:
        config.logging.level = "DEBUG"

    # Configure root logger
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    daemon = PylontechDaemon(config)
    if args.test:
        success = daemon.run_once()
        sys.exit(0 if success else 1)
    else:
        daemon.start()


if __name__ == "__main__":
    main()
