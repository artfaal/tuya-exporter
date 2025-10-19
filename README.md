# Tuya Exporter for Prometheus

Экспортер данных с датчиков Tuya Smart Life в Prometheus Pushgateway для мониторинга в Grafana.

## Описание

Этот проект позволяет собирать данные с датчиков почвы (влажность, температура, заряд батареи) из облака Tuya IoT Platform и отправлять их в Prometheus Pushgateway для последующей визуализации в Grafana.

### Возможности

- ✅ Автоматическое обнаружение всех датчиков в аккаунте Tuya Smart Life
- ✅ Поддержка нескольких датчиков одновременно
- ✅ Использование имен устройств из Smart Life приложения
- ✅ Экспорт метрик: влажность почвы, температура, уровень заряда батареи
- ✅ Поддержка SOCKS5 прокси (опционально)
- ✅ Логирование в файл с ротацией
- ✅ Автозапуск на macOS через LaunchAgent

## Требования

- Python 3.7+
- Аккаунт в Tuya IoT Platform
- Prometheus Pushgateway
- Датчики, совместимые с Tuya Smart Life (например, датчики почвы)

## Установка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd tuya-exporter
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # На macOS/Linux
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка Tuya IoT Platform

Для работы с Tuya API необходимо зарегистрироваться в Tuya IoT Platform и создать проект:

1. Перейдите на https://iot.tuya.com/
2. Создайте аккаунт или войдите
3. Создайте Cloud Project:
   - **Development Method**: Smart Home
   - **Data Center**: выберите свой регион (EU, US, CN, IN)
4. Подпишитесь на необходимые API:
   - В разделе **API Products** найдите и подпишитесь на:
     - **IoT Core**
     - **Authorization**
5. Скопируйте учетные данные:
   - **Access ID** (Client ID)
   - **Access Secret** (Client Secret)
6. Свяжите ваш Smart Life аккаунт:
   - Перейдите в **Devices** → **Link Tuya App Account**
   - Отсканируйте QR-код в приложении Smart Life
   - Путь в приложении: **Me** → **Settings** (⚙️) → **QR Code Scanner**

### 5. Настройка переменных окружения

Скопируйте файл `.env.example` в `.env`:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл, добавив свои данные:

```bash
# Tuya IoT Platform Credentials
TUYA_ACCESS_ID=your_access_id_here
TUYA_ACCESS_KEY=your_access_key_here
TUYA_API_ENDPOINT=https://openapi.tuyaeu.com

# Prometheus Pushgateway
PUSHGATEWAY_URL=https://pushgateway.example.com

# Data collection interval (seconds)
INTERVAL=60

# SOCKS5 Proxy (опционально, можно оставить пустым)
PROXY_HOST=
PROXY_PORT=1080
PROXY_USER=
PROXY_PASSWORD=
```

## Использование

### Обнаружение датчиков (TinyTuya Wizard)

Перед запуском основного скрипта рекомендуется запустить TinyTuya wizard для обнаружения всех устройств и получения их локальных ключей:

```bash
python wizard.py
```

Визард попросит вас ввести:
- **API Region** (выберите ваш регион: `eu`, `us`, `cn`, `in`)
- **API Key** (TUYA_ACCESS_ID из .env)
- **API Secret** (TUYA_ACCESS_KEY из .env)

После этого wizard:
1. Подключится к Tuya Cloud API
2. Получит список всех ваших устройств
3. Просканирует локальную сеть для обнаружения устройств
4. Сохранит результаты в `devices.json` с именами из Smart Life

**Примечание:** Для работы wizard нужен доступ к локальной сети, где находятся устройства.

### Запуск экспортера

```bash
python tuya_exporter.py
```

Скрипт будет:
1. Загружать список датчиков из `devices.json`
2. Каждые 60 секунд (или другой интервал из `.env`) собирать данные через Tuya Cloud API
3. Отправлять метрики в Pushgateway с меткой `instance="home"`
4. Логировать все действия в консоль и файл `logs/tuya_exporter.log`

**Важно:** Имена датчиков берутся из `devices.json` и отправляются в Prometheus как есть (поддерживаются русские имена).

### Просмотр логов

Логи автоматически записываются в директорию `logs/`:

```bash
tail -f logs/tuya_exporter.log
```

Логи автоматически ротируются при достижении 10 МБ, сохраняется 5 последних файлов.

## Метрики Prometheus

Экспортер отправляет следующие метрики:

- `tuya_plant_humidity{device_id="...", device_name="...", instance="home"}` - Влажность почвы (%)
- `tuya_plant_temperature{device_id="...", device_name="...", instance="home"}` - Температура почвы (°C)
- `tuya_plant_battery{device_id="...", device_name="...", instance="home"}` - Уровень заряда батареи (%)

Каждая метрика помечена labels:
- `device_id` - ID устройства в Tuya
- `device_name` - Имя устройства из `devices.json` (поддерживаются русские имена)
- `instance` - Метка экземпляра (всегда `"home"`)

## Автозапуск на macOS

Для автоматического запуска экспортера при загрузке системы создайте LaunchAgent:

```bash
# Создайте файл
nano ~/Library/LaunchAgents/com.tuya.exporter.plist
```

Содержимое файла:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.tuya.exporter</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/southnet-mac-server/PROJECTS/tuya-exporter/venv/bin/python</string>
        <string>/Users/southnet-mac-server/PROJECTS/tuya-exporter/tuya_exporter.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/southnet-mac-server/PROJECTS/tuya-exporter</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/southnet-mac-server/PROJECTS/tuya-exporter/logs/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/Users/southnet-mac-server/PROJECTS/tuya-exporter/logs/stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
```

Загрузка и запуск сервиса:

```bash
# Загрузить и запустить
launchctl load ~/Library/LaunchAgents/com.tuya.exporter.plist

# Проверить статус
launchctl list | grep tuya

# Остановить
launchctl unload ~/Library/LaunchAgents/com.tuya.exporter.plist

# Просмотр логов
tail -f /Users/southnet-mac-server/PROJECTS/tuya-exporter/logs/tuya_exporter.log
tail -f /Users/southnet-mac-server/PROJECTS/tuya-exporter/logs/stderr.log
```

## Обновление имен датчиков

Если вы переименовали датчики в приложении Smart Life:

1. Остановите экспортер:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.tuya.exporter.plist
   ```

2. Запустите wizard для обновления `devices.json`:
   ```bash
   cd /Users/southnet-mac-server/PROJECTS/tuya-exporter
   source venv/bin/activate
   python wizard.py
   ```

3. Перезапустите экспортер:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.tuya.exporter.plist
   ```

## Структура проекта

```
tuya-exporter/
├── tuya_exporter.py        # Основной скрипт экспортера
├── wizard.py               # Скрипт обнаружения датчиков (TinyTuya)
├── requirements.txt        # Зависимости Python
├── .env                    # Конфигурация (не в git)
├── .env.example            # Пример конфигурации
├── devices.json.example    # Пример структуры devices.json
├── .gitignore              # Исключения для git
├── README.md               # Документация
└── logs/                   # Директория логов
    ├── tuya_exporter.log   # Основные логи
    ├── stdout.log          # stdout LaunchAgent
    └── stderr.log          # stderr LaunchAgent
```

## Troubleshooting

### Датчики не обнаруживаются

1. Убедитесь, что вы связали Smart Life аккаунт с проектом в Tuya IoT Platform
2. Проверьте правильность региона API (EU/US/CN/IN)
3. Запустите `python wizard.py` для диагностики

### Ошибки подключения к API

1. Проверьте правильность Access ID и Access Key
2. Убедитесь, что подписаны на необходимые API (IoT Core, Authorization)
3. Проверьте настройки прокси, если используете

### LaunchAgent не запускается

1. Проверьте пути в plist файле
2. Убедитесь, что виртуальное окружение активировано и зависимости установлены
3. Проверьте логи в `logs/stderr.log`

## Лицензия

MIT

## Автор

Created for monitoring Tuya Smart Life soil sensors with Prometheus and Grafana.
