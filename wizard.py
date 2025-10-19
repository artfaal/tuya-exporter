#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tuya Device Discovery Wizard using TinyTuya
Запускает wizard для локального обнаружения устройств и получения их имен
"""
import tinytuya
import sys

def main():
    print("=" * 70)
    print("🔍 Tuya Device Discovery Wizard (TinyTuya)")
    print("=" * 70)
    print()
    print("Этот мастер поможет найти все ваши Tuya устройства и получить их имена")
    print("из приложения Smart Life.")
    print()
    print("Вам понадобятся:")
    print("  1. API credentials из https://iot.tuya.com/")
    print("  2. Доступ к локальной сети с устройствами")
    print()
    print("Результат будет сохранен в devices.json")
    print("=" * 70)
    print()

    # Run TinyTuya wizard
    tinytuya.wizard()

if __name__ == "__main__":
    main()
