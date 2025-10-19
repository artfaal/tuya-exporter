#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tuya Device Discovery Wizard
Поиск и отображение всех устройств в аккаунте Tuya Smart Life
"""
from tuya_connector import TuyaOpenAPI
import json
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === CONFIGURATION ===
ACCESS_ID = os.getenv("TUYA_ACCESS_ID")
ACCESS_KEY = os.getenv("TUYA_ACCESS_KEY")
API_ENDPOINT = os.getenv("TUYA_API_ENDPOINT", "https://openapi.tuyaeu.com")

# SOCKS5 Proxy configuration (optional)
PROXY_HOST = os.getenv("PROXY_HOST")
PROXY_PORT = int(os.getenv("PROXY_PORT", "1080"))
PROXY_USER = os.getenv("PROXY_USER")
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD")

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

def setup_proxy():
    """Setup SOCKS5 proxy if credentials are provided"""
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

def get_user_info(openapi):
    """Получаем информацию о пользователе для получения UID"""
    try:
        response = openapi.get("/v1.0/token", {"grant_type": 1})

        if response.get("success") and "result" in response:
            uid = response["result"].get("uid")
            logger.info(f"✅ User UID: {uid}")
            return uid
        return None
    except Exception as e:
        logger.error(f"❌ Error getting user info: {e}")
        return None

def get_all_devices(openapi):
    """Получаем список всех устройств"""
    try:
        uid = get_user_info(openapi)

        if not uid:
            logger.error("Could not get user UID, trying alternative method...")

        # Пробуем получить устройства
        response = openapi.get(f"/v1.0/users/{uid}/devices") if uid else openapi.get("/v2.0/cloud/thing/device")

        if not response.get("success"):
            logger.error(f"Failed to get devices: {response}")
            return []

        devices = response.get("result", {})

        # Обрабатываем разные форматы ответа
        if isinstance(devices, dict):
            devices = devices.get("devices", []) or devices.get("list", [])
        elif not isinstance(devices, list):
            devices = []

        return devices

    except Exception as e:
        logger.error(f"Error getting devices: {e}", exc_info=True)
        return []

def save_devices_to_json(devices):
    """Сохраняем список устройств в файл devices.json"""
    try:
        with open("devices.json", "w", encoding="utf-8") as f:
            json.dump(devices, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Devices saved to devices.json")
    except Exception as e:
        logger.error(f"Error saving devices: {e}")

def main():
    logger.info("=" * 70)
    logger.info("🔍 Tuya Device Discovery Wizard")
    logger.info("=" * 70)

    # Check credentials
    if not ACCESS_ID or not ACCESS_KEY:
        logger.error("❌ Missing credentials! Please set TUYA_ACCESS_ID and TUYA_ACCESS_KEY in .env file")
        return

    # Setup proxy if configured
    setup_proxy()

    # Initialize Tuya API
    logger.info(f"🔌 Connecting to Tuya API: {API_ENDPOINT}")
    openapi = TuyaOpenAPI(API_ENDPOINT, ACCESS_ID, ACCESS_KEY)
    openapi.connect()
    logger.info("✅ Connected to Tuya API\n")

    # Get all devices
    logger.info("🔍 Discovering devices...")
    devices = get_all_devices(openapi)

    if not devices:
        logger.error("❌ No devices found!")
        return

    logger.info(f"\n✅ Found {len(devices)} device(s):\n")

    # Display devices grouped by category
    categories = {}
    for dev in devices:
        category = dev.get("category", "unknown")
        if category not in categories:
            categories[category] = []
        categories[category].append(dev)

    for category, devs in sorted(categories.items()):
        logger.info(f"📂 Category: {category}")
        for dev in devs:
            status = "🟢 online" if dev.get("online", False) else "🔴 offline"
            logger.info(f"   • {dev.get('name', 'Unknown')} ({dev.get('id')})")
            logger.info(f"     Product: {dev.get('product_name', 'Unknown')}")
            logger.info(f"     Status: {status}")
            logger.info("")

    # Save to file
    save_devices_to_json(devices)

    # Show soil sensors specifically
    soil_sensors = [d for d in devices if d.get("category") == "zwjcy" or
                    "Soil" in d.get("product_name", "") or
                    "Plant" in d.get("product_name", "")]

    if soil_sensors:
        logger.info("\n" + "=" * 70)
        logger.info(f"🌱 Found {len(soil_sensors)} Soil Sensor(s):")
        logger.info("=" * 70)
        for sensor in soil_sensors:
            status = "🟢 online" if sensor.get("online", False) else "🔴 offline"
            logger.info(f"\nDevice Name: {sensor.get('name')}")
            logger.info(f"Device ID:   {sensor.get('id')}")
            logger.info(f"Status:      {status}")
            logger.info(f"Product:     {sensor.get('product_name')}")

    logger.info("\n" + "=" * 70)
    logger.info("✅ Discovery complete! Check devices.json for full details.")
    logger.info("=" * 70)

if __name__ == "__main__":
    main()
