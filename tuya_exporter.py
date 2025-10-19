#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tuya Multi-Sensor → Prometheus Pushgateway Exporter
Поддержка нескольких датчиков с именами из Smart Life
Работа через SOCKS5 прокси
"""
from tuya_connector import TuyaOpenAPI
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import time
import logging
import json
import os
import re
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

# === TRANSLITERATION MAP ===
TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
    'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
    'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
}

def sanitize_label(text):
    """
    Sanitize device name for Prometheus label
    - Transliterate cyrillic to latin
    - Replace spaces and special chars with underscore
    - Keep only alphanumeric and underscore
    """
    # Transliterate cyrillic
    result = ''.join(TRANSLIT_MAP.get(c, c) for c in text)
    # Replace spaces and non-alphanumeric with underscore
    result = re.sub(r'[^a-zA-Z0-9_]+', '_', result)
    # Remove leading/trailing underscores
    result = result.strip('_')
    # Convert to lowercase for consistency
    result = result.lower()
    return result if result else 'unknown'

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

def get_user_info():
    """Получаем информацию о пользователе для получения UID"""
    try:
        # Получаем информацию о токене
        response = openapi.get("/v1.0/token", {"grant_type": 1})
        logger.debug(f"Token info: {json.dumps(response, indent=2)}")

        if response.get("success") and "result" in response:
            uid = response["result"].get("uid")
            logger.info(f"User UID: {uid}")
            return uid
        return None
    except Exception as e:
        logger.error(f"Error getting user info: {e}")
        return None

def get_all_devices():
    """Получаем список всех устройств через пользовательский API"""
    try:
        # Сначала получаем UID пользователя
        uid = get_user_info()

        if not uid:
            logger.error("Could not get user UID")
            # Пробуем альтернативный метод - получение устройств напрямую
            logger.info("Trying alternative method to get devices...")

        # Используем endpoint для получения устройств пользователя
        response = openapi.get(f"/v1.0/users/{uid}/devices") if uid else openapi.get("/v2.0/cloud/thing/device")

        logger.debug(f"Devices response: {json.dumps(response, indent=2, ensure_ascii=False)}")

        if not response.get("success"):
            logger.error(f"Failed to get devices: {response}")
            return []

        devices = response.get("result", {})

        # Обрабатываем разные форматы ответа
        if isinstance(devices, dict):
            devices = devices.get("devices", []) or devices.get("list", [])
        elif not isinstance(devices, list):
            devices = []

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
                    "online": dev.get("online", False),
                    "product_name": product_name
                })

        logger.info(f"Found {len(soil_sensors)} soil sensor(s):")
        for sensor in soil_sensors:
            status = "🟢 online" if sensor["online"] else "🔴 offline"
            logger.info(f"  - {sensor['name']} ({sensor['id']}) {status}")

        return soil_sensors

    except Exception as e:
        logger.error(f"Error getting devices: {e}", exc_info=True)
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

        # Sanitize device name for Prometheus label
        safe_name = sanitize_label(device_name)

        # Влажность почвы
        if "humidity" in data:
            humidity = float(data["humidity"])
            humidity_gauge.labels(device_id=device_id, device_name=safe_name).set(humidity)
            logger.info(f"  💧 {device_name}: Humidity {humidity}%")
            metrics_pushed = True

        # Температура
        if "temp_current" in data:
            temp = float(data["temp_current"]) / 10
            temperature_gauge.labels(device_id=device_id, device_name=safe_name).set(temp)
            logger.info(f"  🌡️  {device_name}: Temperature {temp}°C")
            metrics_pushed = True

        # Батарея
        if "battery_percentage" in data:
            battery = float(data["battery_percentage"])
            battery_gauge.labels(device_id=device_id, device_name=safe_name).set(battery)
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
        logger.error("❌ No soil sensors found!")
        logger.info("\n💡 Tip: Check if devices are visible in devices.json from tinytuya wizard")
        logger.info("You can manually add device IDs to the script if needed.\n")

        # Fallback: используем известный датчик
        logger.info("Using known device as fallback...")
        devices = [{
            "id": "bf95b7947d0d48b6d11yrz",
            "name": "Smart Soil Tester",
            "category": "zwjcy",
            "online": True,
            "product_name": "Smart Soil Tester"
        }]

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
                push_to_gateway(PUSHGATEWAY, job='tuya_sensors', registry=registry)
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
