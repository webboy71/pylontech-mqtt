# Pylontech US2000 to Home Assistant MQTT Gateway (`pylontech-mqtt`)

A lightweight, robust Python service designed to run on a **Raspberry Pi 3 B+**, connect directly to the **Console port** of a stack of 4 (or more) **Pylontech US2000** batteries, and stream detailed battery telemetry to **Home Assistant OS (HAOS)** via **MQTT** using **Home Assistant MQTT Auto-Discovery**.

---

## 🌟 Features

- **Direct Console CLI Protocol**: Interacts natively with the Pylontech ASCII console (`pylon>`) over RS-232 at 115200 baud (the same port and speed you access with `picocom`).
- **Zero-Configuration Home Assistant Integration**:
  - Automatically creates **5 organized devices** in Home Assistant:
    1. **Master Stack Device**: Aggregates total battery power (W), combined current (A), bus voltage (V), stack SoC (%), cell imbalance/delta (mV), lowest/highest cell voltages, temperature spread, and charging/discharging states.
    2. **Units 1 to 4**: Individual devices tracking module voltage, current, power, SoC, SOH, cycle counts, BMS temperature, and all 15 individual cell voltages in millivolts.
  - Full MQTT Availability with Last Will and Testament (LWT) for clean online/offline presence.
- **Production Daemon**:
  - Auto-reconnection on serial cable unplug / plug.
  - Auto-reconnection on MQTT broker restart.
  - Native `systemd` service with automatic restarts.
  - Includes a quick `--test` mode to verify readings directly in your terminal.

---

## 🔌 Hardware Setup & Pinout

You can connect your Raspberry Pi 3 B+ to the **Master Battery's "Console" port** (RJ45) either via **Built-in GPIO UART** (Pins 8/10) or a **USB-to-RS232 Adapter**.

---

### Option A: Built-in Raspberry Pi GPIO UART (Recommended if using GPIO Pins)

On the Raspberry Pi 3 B+, the built-in hardware UART is on GPIO 14 (TXD) and GPIO 15 (RXD). Because the Pi's GPIOs operate at **3.3V TTL** and the Pylontech console port uses **RS-232 voltage levels**, an **RS-232 level shifter** (such as a MAX3232 transceiver board or HAT) is required between the Pi and the battery:

```
+---------------------------+       +-------------------+       +-------------------------------+
|  Raspberry Pi 3 B+        |       |  MAX3232 Module   |       |  Pylontech US2000 (Master)    |
|                           |       |  (Level Shifter)  |       |                               |
|  Pin 1 (3.3V Power)       |------>| VCC               |       |                               |
|  Pin 6 (GND Ground)       |------>| GND               |       |                               |
|  Pin 8 (GPIO 14 / TXD)    |------>| TTL RXD / DIN1    |       |                               |
|                           |       | RS232 DOUT1       |------>| RJ45 Pin 6 (Battery RX)       |
|  Pin 10 (GPIO 15 / RXD)   |<------| TTL TXD / DOUT2   |       |                               |
|                           |       | RS232 RIN2        |<------| RJ45 Pin 3 (Battery TX)       |
|                           |       | RS232 GND         |------>| RJ45 Pin 8 / Pin 1 (GND)      |
+---------------------------+       +-------------------+       +-------------------------------+
```

#### Pin Mapping Reference Table

| Raspberry Pi Pin | Signal | MAX3232 Side A (TTL) | MAX3232 Side B (RS-232) | Pylontech RJ45 Console Port |
| :--- | :--- | :--- | :--- | :--- |
| **Pin 1** | 3.3V DC Power | **VCC** | — | — |
| **Pin 6, 9, or 14** | Ground | **GND** | **GND** | **Pin 8** (or Pin 1) (GND) |
| **Pin 8** (GPIO 14) | TXD (Pi Out) | **TTL IN (TX)** | **RS232 OUT (TX)** | **Pin 6** (Battery RX) |
| **Pin 10** (GPIO 15) | RXD (Pi In) | **TTL OUT (RX)** | **RS232 IN (RX)** | **Pin 3** (Battery TX) |

#### Raspberry Pi OS UART Configuration (Crucial!)

On Raspberry Pi 3 B+, the primary PL011 UART is assigned to Bluetooth by default, and the Linux kernel provides a login console over serial by default. Follow these quick steps:

1. **Disable Serial Login Console & Enable Hardware Serial**:
   ```bash
   sudo raspi-config
   ```
   Navigate to: **Interface Options** -> **Serial Port**:
   - *"Would you like a login shell to be accessible over serial?"* -> Select **No**
   - *"Would you like the serial port hardware to be enabled?"* -> Select **Yes**
   - Finish and reboot if prompted.

2. **(Recommended for Pi 3 B+) Dedicate PL011 UART to GPIO 14/15**:
   On Raspberry Pi 3 B+, disable the onboard Bluetooth or swap it to mini-UART to ensure stable 115200 baud communication:
   ```bash
   sudo nano /boot/firmware/config.txt
   # (Or /boot/config.txt on older Raspberry Pi OS versions)
   ```
   Add to the bottom of the file:
   ```ini
   enable_uart=1
   dtoverlay=disable-bt
   ```
   Disable the systemd service for bluetooth modem:
   ```bash
   sudo systemctl disable hciuart
   ```
   Then reboot:
   ```bash
   sudo reboot
   ```

3. **Serial Device to Use in `config.yaml`**:
   Use **`/dev/serial0`** (or `/dev/ttyAMA0`).

---

### Option B: USB-to-RS232 Adapter

If using an external USB-to-RS232 adapter (e.g. FTDI, CH340, PL2303):
- Plug the USB end into the Pi.
- Connect RJ45 Pin 3 to DB9 Pin 2 (RX), RJ45 Pin 6 to DB9 Pin 3 (TX), and RJ45 Pin 8 to DB9 Pin 5 (GND).
- Device in `config.yaml`: **`/dev/ttyUSB0`**.

---

> [!NOTE]
> Ensure you plug into the port labeled **Console** (RS-232), NOT the CAN or RS-485 inverter communication ports. In a stack of 4 batteries connected with link cables, querying the Master battery aggregates telemetry from all 4 units.

---

## 🚀 Quick Start on Raspberry Pi 3 B+

### 1. Copy Files to your Pi 3 B+
Clone or transfer the `pylontech-mqtt` repository to your Pi 3 B+:
```bash
cd /home/pi
# If copied locally or cloned:
cd pylontech-mqtt
```

### 2. Run Automated Installer
The installer creates a dedicated Python virtualenv in `/opt/pylontech-mqtt`, sets up permissions, creates the default configuration file, and enables the systemd service:
```bash
sudo chmod +x install.sh
sudo ./install.sh
```

### 3. Configure MQTT & Serial
Edit `/etc/pylontech-mqtt/config.yaml`:
```bash
sudo nano /etc/pylontech-mqtt/config.yaml
```

Update your Home Assistant IP and MQTT credentials:
```yaml
serial:
  port: "/dev/ttyUSB0"      # Or /dev/serial/by-id/...
  baudrate: 115200

polling:
  interval_seconds: 15.0   # Polling frequency
  battery_count: 4          # 4 units in stack
  read_cell_details: true   # Fetch individual cell voltages

mqtt:
  host: "192.168.1.50"      # IP address of your HAOS Pi
  port: 1883
  username: "homeassistant" # Your MQTT user
  password: "your_password"
  ha_discovery_enabled: true
```

### 4. Test Communication
Run the service once in test mode to verify that it reads your batteries and outputs telemetry:
```bash
/opt/pylontech-mqtt/venv/bin/python3 -m pylontech_mqtt.main --config /etc/pylontech-mqtt/config.yaml --test
```

You should see output similar to:
```
============================================================
  PYLONTECH BATTERY STACK TELEMETRY
============================================================
Active Units       : 4
Stack State        : Discharging
Stack Voltage      : 49.95 V
Stack Current      : -5.00 A
Stack Power        : -249.8 W
Stack SoC          : 98.0 % (Min: 98.0%, Max: 98.0%)
Remaining Capacity : 196.0 Ah / 200.0 Ah
Min Cell Voltage   : 3328.0 mV
Max Cell Voltage   : 3332.0 mV
Cell Delta         : 4.0 mV
Temp Range         : 22.0 °C to 24.0 °C
------------------------------------------------------------
Unit 1 [PPTA0123... | FW: B65.12]:
  Voltage: 49.95V | Current: -1.25A | Power: -62.4W | SoC: 98%
  Cycles: 142 | SOH: 99.0% | Temp: 23.0°C
  Cells (15): 3328mV, 3329mV, 3330mV, 3329mV, 3331mV...
  Status: Base=Dischg, Volt=Normal, Curr=Normal, Temp=Normal
...
============================================================
```

### 5. Start Background Service
```bash
sudo systemctl start pylontech-mqtt
sudo systemctl status pylontech-mqtt
```

View live logs at any time:
```bash
sudo journalctl -u pylontech-mqtt -f
```

---

## 🏠 Home Assistant Setup

Because this service publishes standard **Home Assistant MQTT Discovery** payloads:
1. In Home Assistant, open **Settings -> Devices & Services**.
2. If you already have the **MQTT** integration configured, 5 new devices will automatically appear:
   - **`Pylontech Battery Stack`** (Master device)
   - **`Pylontech Battery Unit 1`**
   - **`Pylontech Battery Unit 2`**
   - **`Pylontech Battery Unit 3`**
   - **`Pylontech Battery Unit 4`**

### Available Sensors

| Device | Entity | Unit / Type | Description |
| :--- | :--- | :--- | :--- |
| **Stack** | `sensor.pylontech_stack_power` | `W` | Instantaneous total charge/discharge power |
| **Stack** | `sensor.pylontech_stack_current` | `A` | Combined charge/discharge current |
| **Stack** | `sensor.pylontech_stack_voltage` | `V` | Average bus voltage |
| **Stack** | `sensor.pylontech_stack_state_of_charge_soc` | `%` | Average SoC across all 4 units |
| **Stack** | `sensor.pylontech_stack_cell_delta_balance` | `mV` | Max cell voltage minus min cell voltage (balance metric) |
| **Stack** | `sensor.pylontech_stack_lowest_cell_voltage` | `mV` | Lowest cell across all 60 cells |
| **Stack** | `sensor.pylontech_stack_highest_cell_voltage` | `mV` | Highest cell across all 60 cells |
| **Stack** | `binary_sensor.pylontech_stack_charging` | `Binary` | ON when stack is charging |
| **Stack** | `binary_sensor.pylontech_stack_discharging` | `Binary` | ON when stack is discharging |
| **Unit 1-4** | `sensor.unit_X_voltage` | `V` | Pack voltage |
| **Unit 1-4** | `sensor.unit_X_current` | `A` | Pack current |
| **Unit 1-4** | `sensor.unit_X_soc` | `%` | Unit State of Charge |
| **Unit 1-4** | `sensor.unit_X_soh` | `%` | Unit State of Health |
| **Unit 1-4** | `sensor.unit_X_cycle_count` | `Cycles` | Total lifetime cycles |
| **Unit 1-4** | `sensor.unit_X_cell_1_voltage` .. `cell_15_voltage` | `mV` | Individual cell voltages |
| **Unit 1-4** | `binary_sensor.unit_X_voltage_warning` | `Problem` | Over/Under-voltage alert |

---

## 📊 Example Home Assistant Dashboard Card

Add this Lovelace card YAML to display your battery bank status:

```yaml
type: vertical-stack
cards:
  - type: custom:mushroom-title-card
    title: Pylontech Battery Bank
    subtitle: 4x US2000 (9.6 kWh Total)
  - type: glance
    entities:
      - entity: sensor.pylontech_stack_state_of_charge_soc
        name: Stack SoC
      - entity: sensor.pylontech_stack_power
        name: Power
      - entity: sensor.pylontech_stack_voltage
        name: Voltage
      - entity: sensor.pylontech_stack_current
        name: Current
      - entity: sensor.pylontech_stack_cell_delta_balance
        name: Cell Delta
  - type: entities
    title: Individual Battery Modules
    entities:
      - entity: sensor.pylontech_battery_unit_1_soc
        name: Unit 1 SoC
      - entity: sensor.pylontech_battery_unit_2_soc
        name: Unit 2 SoC
      - entity: sensor.pylontech_battery_unit_3_soc
        name: Unit 3 SoC
      - entity: sensor.pylontech_battery_unit_4_soc
        name: Unit 4 SoC
```

---

## 🛠️ Management & Service Commands

| Action | Command |
| :--- | :--- |
| **Check service status** | `sudo systemctl status pylontech-mqtt` |
| **Start service** | `sudo systemctl start pylontech-mqtt` |
| **Stop service** | `sudo systemctl stop pylontech-mqtt` |
| **Restart service** | `sudo systemctl restart pylontech-mqtt` |
| **View live logs** | `sudo journalctl -u pylontech-mqtt -f` |
| **Run unit tests** | `python3 -m unittest discover tests` |

---

## 📜 License

MIT License. Designed for renewable energy enthusiasts and Home Assistant users.
