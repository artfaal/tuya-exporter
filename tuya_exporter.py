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
from tuya_connector import TuyaOpenAPI
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import time
import logging
import json
import os
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# Load environment variables
load_dotenv()

# === CONFIGURATION ===
ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_KEY = os.getenv("TUYA_ACCESS_KEY")
API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")
PUSHGATEWAY = os.getenv("PUSHGATEWAY_URL")
INTERVAL = int(os.getenv("INTERVAL", "60"))

# SOCKS5 Proxy configuration (optional)
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = int(os.getenv("PROXY_PORT", "1080"))
PROXY_USER = os.getenv("PROXY_USER")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

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

# === SETUP SOCKS5 PROXY ===
if PROXY_HOST and PROXY_USER and PROXY_PASSWORD:
    import socks
    import socket

    socks.set_default_proxy(
        socks.SOCKS5,
        PROXY_HOST,
        PROXY_PORT,
        username=PROXY_USER,
        password=PROXY_PASSWORD
    )
    socket.socket = socks.socksocket
    logger.info(f"🔒 SOCKS5 proxy enabled: {PROXY_HOST}:{PROXY_PORT}")
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
    ['device_id', 'device_name'],
    registry=registry
)
temperature_gauge = Gauge(
    'tuya_plant_temperature',
    'Soil temperature (°C)',
    ['device_id', 'device_name'],
    registry=registry
)
battery_gauge = Gauge(
    'tuya_plant_battery',
    'Battery level (%)',
    ['device_id', 'device_name'],
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

        # Фильтруем только датчики почвы (категория zwjcy)
        soil_sensors = []

        for dev in devices:
            category = dev.get("category", "")
            product_name = dev.get("product_name", "")
            name = dev.get("name", "Unknown")

            # Определяем датчики почвы по категории или названию продукта
            if category == "zwjcy" or "Soil" in product_name or "Plant" in product_name:
                soil_sensors.append({
                    "id": dev["id"],
                    "name": name,
                    "category": category,
                    "online": True,  # Считаем все устройства из devices.json активными
                    "product_name": product_name
                })

        logger.info(f"Found {len(soil_sensors)} soil sensor(s):")
        for sensor in soil_sensors:
            logger.info(f"  - {sensor['name']} ({sensor['id']})")

        return soil_sensors

    except Exception as e:
        logger.error(f"Error loading devices.json: {e}", exc_info=True)
        return []

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

    except Exception as e:
        logger.error(f"Error getting data for {device_id}: {e}")
        return None

def push_metrics(device_id, device_name, data):
    """Отправляем метрики с labels"""
    try:
        metrics_pushed = False

        # Влажность почвы
        if "humidity" in data:
            humidity = float(data["humidity"])
            humidity_gauge.labels(device_id=device_id, device_name=device_name).set(humidity)
            logger.info(f"  💧 {device_name}: Humidity {humidity}%")
            metrics_pushed = True

        # Температура
        if "temp_current" in data:
            temp = float(data["temp_current"]) / 10
            temperature_gauge.labels(device_id=device_id, device_name=device_name).set(temp)
            logger.info(f"  🌡️  {device_name}: Temperature {temp}°C")
            metrics_pushed = True

        # Батарея
        if "battery_percentage" in data:
            battery = float(data["battery_percentage"])
            battery_gauge.labels(device_id=device_id, device_name=device_name).set(battery)
            logger.info(f"  🔋 {device_name}: Battery {battery}%")
            metrics_pushed = True

        return metrics_pushed

    except Exception as e:
        logger.error(f"Error processing metrics for {device_name}: {e}")
        return False

def main():
    logger.info("=" * 60)
    logger.info("🌱 Tuya Multi-Sensor Exporter Started")
    logger.info("=" * 60)

    # Получаем список всех датчиков
    devices = get_all_devices()

    if not devices:
        logger.error("❌ No soil sensors found in devices.json!")
        logger.info("\n💡 Run 'python wizard.py' to discover your devices\n")
        return

    logger.info(f"\n📊 Starting monitoring of {len(devices)} device(s)...\n")

    while True:
        try:
            any_data = False

            for device in devices:
                device_id = device["id"]
                device_name = device["name"]

                if not device["online"]:
                    logger.warning(f"⚠️  {device_name} is offline, skipping...")
                    continue

                data = get_device_data(device_id)

                if data:
                    if push_metrics(device_id, device_name, data):
                        any_data = True

            if any_data:
                push_to_gateway(PUSHGATEWAY, job='tuya_sensors', registry=registry, grouping_key={'instance': 'home'})
                logger.info(f"✅ All metrics pushed to Pushgateway\n")
            else:
                logger.warning("⚠️  No data collected in this cycle\n")

        except KeyboardInterrupt:
            logger.info("\n👋 Stopped by user")
            break
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}\n", exc_info=True)

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
