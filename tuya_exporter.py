#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tuya Multi-Sensor → Prometheus Pushgateway Exporter

Экспортер данных с датчиков почвы Tuya в Prometheus Pushgateway.
- Загружает список датчиков из devices.json (TinyTuya wizard)
- Получает данные через Tuya Cloud API
- Отправляет метрики в Pushgateway с поддержкой русских имён
- Опциональная работа через SOCKS5 прокси
"""
import os
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# SOCKS5 Proxy configuration (optional)
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = int(os.getenv("PROXY_PORT", "1080"))
PROXY_USER = os.getenv("PROXY_USER")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# === SETUP SOCKS5 PROXY BEFORE ANY NETWORK IMPORTS ===
if PROXY_HOST and PROXY_USER and PROXY_PASSWORD:
    import socks
    import socket

    socks.set_default_proxy(
        socks.SOCKS5,
        PROXY_HOST,
        PROXY_PORT,
        rdns=True,  # Enable remote DNS resolution through SOCKS5
        username=PROXY_USER,
        password=PROXY_PASSWORD
    )
    socket.socket = socks.socksocket
    print(f"SOCKS5 proxy configured: {PROXY_HOST}:{PROXY_PORT} (remote DNS)")

# NOW import network libraries
from tuya_connector import TuyaOpenAPI
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import time
import logging
import json
import yaml
import socket
from logging.handlers import RotatingFileHandler

# Устанавливаем глобальный таймаут для всех socket операций (30 секунд)
socket.setdefaulttimeout(30.0)

# === CONFIGURATION ===
ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_KEY = os.getenv("TUYA_ACCESS_KEY")
API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")
PUSHGATEWAY = os.getenv("PUSHGATEWAY_URL")
INTERVAL = int(os.getenv("INTERVAL", "60"))

# === LOGGING ===
os.makedirs("logs", exist_ok=True)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console_handler.setFormatter(console_formatter)

# File handler (rotating, max 10MB, keep 5 backups)
file_handler = RotatingFileHandler(
    "logs/tuya_exporter.log",
    maxBytes=10*1024*1024,
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(file_formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Log proxy status
if PROXY_HOST and PROXY_USER and PROXY_PASSWORD:
    logger.info(f"🔒 SOCKS5 proxy enabled: {PROXY_HOST}:{PROXY_PORT} (remote DNS)")
else:
    logger.info("📡 Using direct connection (no proxy)")

# === INIT TUYA API ===
openapi = TuyaOpenAPI(API_ENDPOINT, ACCESS_ID, ACCESS_KEY)
openapi.connect()

# === METRICS (with labels) ===
registry = CollectorRegistry()
humidity_gauge = Gauge(
    'tuya_plant_humidity',
    'Soil humidity (%)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
temperature_gauge = Gauge(
    'tuya_plant_temperature',
    'Soil temperature (°C)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
battery_gauge = Gauge(
    'tuya_plant_battery',
    'Battery level (%)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
humidity_threshold_min_gauge = Gauge(
    'tuya_plant_humidity_threshold_min',
    'Minimum optimal soil humidity (%)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
humidity_threshold_max_gauge = Gauge(
    'tuya_plant_humidity_threshold_max',
    'Maximum optimal soil humidity (%)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)

# === SMART PLUG METRICS ===
plug_switch_gauge = Gauge(
    'tuya_plug_switch',
    'Smart plug switch state (0=off, 1=on)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
plug_power_gauge = Gauge(
    'tuya_plug_power',
    'Current power consumption (W)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
plug_current_gauge = Gauge(
    'tuya_plug_current',
    'Current draw (mA)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)
plug_voltage_gauge = Gauge(
    'tuya_plug_voltage',
    'Voltage (V)',
    ['device_id', 'device_name', 'group'],
    registry=registry
)

heartbeat_gauge = Gauge(
    'tuya_exporter_last_success_timestamp',
    'Unix timestamp of last successful data collection',
    registry=registry
)

def get_all_devices():
    """Загружаем устройства из devices.json (TinyTuya wizard output)"""
    try:
        if not os.path.exists("devices.json"):
            logger.error("❌ devices.json not found!")
            logger.info("💡 Run 'python wizard.py' first to discover devices")
            return []

        with open("devices.json", "r", encoding="utf-8") as f:
            devices = json.load(f)

        if not isinstance(devices, list):
            logger.error("❌ Invalid devices.json format")
            return []

        logger.info(f"📄 Loaded {len(devices)} devices from devices.json")

        # Фильтруем датчики почвы (zwjcy) и розетки (cz)
        filtered_devices = []

        for dev in devices:
            category = dev.get("category", "")
            product_name = dev.get("product_name", "")
            name = dev.get("name", "Unknown")

            # Определяем датчики почвы по категории или названию продукта
            is_soil_sensor = category == "zwjcy" or "Soil" in product_name or "Plant" in product_name
            # Определяем розетки по категории
            is_smart_plug = category == "cz"

            if is_soil_sensor or is_smart_plug:
                filtered_devices.append({
                    "id": dev["id"],
                    "name": name,
                    "category": category,
                    "online": True,  # Считаем все устройства из devices.json активными
                    "product_name": product_name
                })

        # Подсчитываем устройства по типам
        soil_count = sum(1 for d in filtered_devices if d['category'] == 'zwjcy')
        plug_count = sum(1 for d in filtered_devices if d['category'] == 'cz')

        logger.info(f"Found {soil_count} soil sensor(s) and {plug_count} smart plug(s):")
        for device in filtered_devices:
            device_type = "sensor" if device['category'] == 'zwjcy' else "plug"
            logger.info(f"  - [{device_type}] {device['name']} ({device['id']})")

        return filtered_devices

    except Exception as e:
        logger.error(f"Error loading devices.json: {e}", exc_info=True)
        return []

def load_plant_config():
    """Загружаем конфигурацию пороговых значений для растений из YAML"""
    config_path = "plant_config.yaml"

    # Дефолтные значения если конфиг не найден
    default_config = {
        'defaults': {
            'humidity_min': 40,
            'humidity_max': 60
        },
        'plants': {}
    }

    try:
        if not os.path.exists(config_path):
            logger.debug(f"📝 {config_path} not found, using defaults")
            return default_config

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning(f"⚠️  {config_path} is empty, using defaults")
            return default_config

        # Проверяем структуру конфига
        if 'defaults' not in config:
            config['defaults'] = default_config['defaults']
        if 'plants' not in config:
            config['plants'] = {}

        logger.debug(f"✅ Loaded plant config: {len(config['plants'])} custom settings")
        return config

    except yaml.YAMLError as e:
        logger.error(f"❌ Error parsing {config_path}: {e}")
        return default_config
    except Exception as e:
        logger.error(f"❌ Error loading {config_path}: {e}")
        return default_config

def get_device_data(device_id):
    """Получаем данные конкретного устройства"""
    try:
        response = openapi.get(f"/v1.0/devices/{device_id}")

        if not response.get("success"):
            logger.debug(f"Device info failed, trying status endpoint...")
            response = openapi.get(f"/v1.0/iot-03/devices/{device_id}/status")

        if not response.get("success"):
            logger.error(f"API error for {device_id}: {response.get('code')} - {response.get('msg')}")
            return None

        result = response.get("result", {})

        # Обрабатываем разные форматы ответа
        if isinstance(result, list):
            status = result
        else:
            status = result.get("status", [])

        if not status:
            return None

        data_dict = {item["code"]: item["value"] for item in status}
        return data_dict

    except socket.timeout:
        logger.error(f"Timeout при получении данных для {device_id}")
        return None
    except ConnectionError as e:
        logger.error(f"Ошибка соединения при получении данных для {device_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Ошибка при получении данных для {device_id}: {e}")
        return None

def push_metrics(device_id, device_name, group, data):
    """Отправляем метрики с labels"""
    try:
        metrics_pushed = False

        # Влажность почвы
        if "humidity" in data:
            humidity = float(data["humidity"])
            humidity_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(humidity)
            logger.info(f"  💧 {device_name}: Humidity {humidity}%")
            metrics_pushed = True

        # Температура
        if "temp_current" in data:
            temp = float(data["temp_current"]) / 10
            temperature_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(temp)
            logger.info(f"  🌡️  {device_name}: Temperature {temp}°C")
            metrics_pushed = True

        # Батарея
        if "battery_percentage" in data:
            battery = float(data["battery_percentage"])
            battery_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(battery)
            logger.info(f"  🔋 {device_name}: Battery {battery}%")
            metrics_pushed = True

        return metrics_pushed

    except Exception as e:
        logger.error(f"Error processing metrics for {device_name}: {e}")
        return False

def push_thresholds(device_id, device_name, group, plant_config):
    """Устанавливаем пороговые значения влажности для растения"""
    try:
        # Ищем настройки для конкретного растения по имени
        plant_settings = plant_config['plants'].get(device_name)

        if plant_settings:
            humidity_min = plant_settings.get('humidity_min', plant_config['defaults']['humidity_min'])
            humidity_max = plant_settings.get('humidity_max', plant_config['defaults']['humidity_max'])
        else:
            # Используем дефолтные значения
            humidity_min = plant_config['defaults']['humidity_min']
            humidity_max = plant_config['defaults']['humidity_max']

        # Устанавливаем метрики
        humidity_threshold_min_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(humidity_min)
        humidity_threshold_max_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(humidity_max)

        logger.debug(f"  📊 {device_name}: Thresholds {humidity_min}-{humidity_max}%")
        return True

    except Exception as e:
        logger.error(f"Error setting thresholds for {device_name}: {e}")
        return False

def push_plug_metrics(device_id, device_name, group, data):
    """Отправляем метрики для розетки"""
    try:
        metrics_pushed = False

        # Состояние вкл/выкл
        if "switch_1" in data:
            switch_state = 1 if data["switch_1"] else 0
            plug_switch_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(switch_state)
            state_text = "ON" if switch_state else "OFF"
            logger.info(f"  🔌 {device_name}: Switch {state_text}")
            metrics_pushed = True

        # Мощность
        if "cur_power" in data:
            power = float(data["cur_power"]) / 10  # Конвертируем в ватты
            plug_power_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(power)
            logger.info(f"  ⚡ {device_name}: Power {power}W")
            metrics_pushed = True

        # Ток
        if "cur_current" in data:
            current = float(data["cur_current"])
            plug_current_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(current)
            logger.info(f"  🔋 {device_name}: Current {current}mA")
            metrics_pushed = True

        # Напряжение
        if "cur_voltage" in data:
            voltage = float(data["cur_voltage"]) / 10  # Конвертируем в вольты
            plug_voltage_gauge.labels(device_id=device_id, device_name=device_name, group=group).set(voltage)
            logger.info(f"  ⚡ {device_name}: Voltage {voltage}V")
            metrics_pushed = True

        return metrics_pushed

    except Exception as e:
        logger.error(f"Error processing plug metrics for {device_name}: {e}")
        return False

def main():
    logger.info("=" * 60)
    logger.info("🌱 Tuya Multi-Sensor Exporter Started")
    logger.info("=" * 60)

    # Получаем список всех датчиков
    devices = get_all_devices()

    if not devices:
        logger.error("❌ No devices found in devices.json!")
        logger.info("\n💡 Run 'python wizard.py' to discover your devices\n")
        return

    logger.info(f"\n📊 Starting monitoring of {len(devices)} device(s)...\n")

    while True:
        try:
            # Загружаем конфиг пороговых значений (перечитывается каждый цикл для автообновления)
            plant_config = load_plant_config()

            any_data = False

            for device in devices:
                device_id = device["id"]
                device_name = device["name"]
                device_category = device.get("category", "")

                if not device["online"]:
                    logger.warning(f"⚠️  {device_name} is offline, skipping...")
                    continue

                data = get_device_data(device_id)

                if not data:
                    continue

                # Обрабатываем датчики почвы
                if device_category == "zwjcy":
                    # Извлекаем group из конфигурации растения
                    plant_settings = plant_config['plants'].get(device_name, {})
                    group = plant_settings.get('group', plant_config['defaults'].get('group', 'unknown'))

                    # Устанавливаем пороговые значения для растения
                    push_thresholds(device_id, device_name, group, plant_config)

                    if push_metrics(device_id, device_name, group, data):
                        any_data = True

                # Обрабатываем розетки
                elif device_category == "cz":
                    # Извлекаем group из конфигурации розетки
                    plug_settings = plant_config.get('plugs', {}).get(device_name, {})
                    group = plug_settings.get('group', 'unknown')

                    if push_plug_metrics(device_id, device_name, group, data):
                        any_data = True

            if any_data:
                # Update heartbeat timestamp on successful data collection
                try:
                    heartbeat_gauge.set(time.time())
                    push_to_gateway(PUSHGATEWAY, job='tuya_sensors', registry=registry, grouping_key={'instance': 'home'}, timeout=10)
                    logger.info(f"✅ All metrics pushed to Pushgateway (heartbeat updated)\n")
                except socket.timeout:
                    logger.error("❌ Timeout при отправке метрик в Pushgateway\n")
                except ConnectionError as e:
                    logger.error(f"❌ Ошибка соединения с Pushgateway: {e}\n")
                except Exception as e:
                    logger.error(f"❌ Ошибка при отправке метрик в Pushgateway: {e}\n")
            else:
                logger.warning("⚠️  No data collected in this cycle\n")

        except KeyboardInterrupt:
            logger.info("\n👋 Stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error in main loop: {e}\n", exc_info=True)
            logger.info("Продолжаем работу через 60 секунд...\n")
            time.sleep(60)

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
