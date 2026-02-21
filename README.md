# Tuya Exporter for Prometheus

Экспортер данных с датчиков Tuya Smart Life в Prometheus Pushgateway для мониторинга в Grafana.

## Описание

Собирает данные с датчиков почвы (влажность, температура, заряд батареи) и умных розеток (состояние, мощность, ток, напряжение) из облака Tuya IoT Platform и отправляет их в Prometheus Pushgateway.

### Возможности

- Автоматическое обнаружение всех датчиков и розеток в аккаунте Tuya Smart Life
- Экспорт метрик датчиков: влажность почвы, температура, уровень заряда батареи
- Экспорт метрик розеток: состояние вкл/выкл, мощность, ток, напряжение
- Группировка растений и розеток по зонам освещения
- Настраиваемые пороговые значения влажности для каждого растения
- Автообновление конфига без перезапуска приложения
- Поддержка SOCKS5 прокси (опционально)
- Логирование в файл с ротацией

## Требования

- Docker + Docker Compose
- Аккаунт в Tuya IoT Platform
- Prometheus Pushgateway

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/artfaal/tuya-exporter.git
cd tuya-exporter
```

### 2. Настройка переменных окружения

```bash
cp .env.example .env
```

Заполнить `.env`:

```env
TUYA_ACCESS_ID=your_access_id_here
TUYA_ACCESS_KEY=your_access_key_here
TUYA_API_ENDPOINT=https://openapi.tuyaeu.com
PUSHGATEWAY_URL=https://pushgateway.example.com
INTERVAL=60

# SOCKS5 прокси (опционально)
PROXY_HOST=
PROXY_PORT=1080
PROXY_USER=
PROXY_PASSWORD=
```

> Получить `Access ID` и `Access Key` можно на [iot.tuya.com](https://iot.tuya.com/) в настройках вашего Cloud Project.

### 3. Обнаружение устройств (wizard)

Перед первым запуском нужно запустить wizard — он подключится к Tuya Cloud, найдёт все устройства и сохранит их в `devices.json`:

```bash
docker compose --profile wizard run --rm tuya-wizard
```

Wizard прочитает `Access ID` и `Access Key` из `.env` и предложит использовать существующие настройки (`Use existing credentials Y/n`).

> Wizard запускается с `network_mode: host` — это нужно для сканирования локальной сети.

### 4. Настройка пороговых значений растений

```bash
cp plant_config.yaml.example plant_config.yaml
```

Отредактировать `plant_config.yaml` под свои растения (имена берутся из `devices.json`).

### 5. Запуск

```bash
docker compose up -d
```

## Управление

```bash
# Статус
docker compose ps

# Логи (live)
docker compose logs -f

# Остановить
docker compose down

# Обновить код и перезапустить
git pull && docker compose up -d --build

# Обновить список устройств (после добавления новых датчиков)
docker compose --profile wizard run --rm tuya-wizard
docker compose restart tuya-exporter
```

## Настройка Tuya IoT Platform

1. Перейти на [iot.tuya.com](https://iot.tuya.com/) → создать Cloud Project
   - **Development Method**: Smart Home
   - **Data Center**: выбрать свой регион (EU, US, CN, IN)
2. В разделе **API Products** подписаться на **IoT Core** и **Authorization**
3. Скопировать **Access ID** (Client ID) и **Access Secret** (Client Secret)
4. Связать Smart Life аккаунт: **Devices** → **Link Tuya App Account** → отсканировать QR в приложении Smart Life (**Me** → **Settings** → **QR Code Scanner**)

## Конфигурация растений и розеток (`plant_config.yaml`)

```yaml
defaults:
  humidity_min: 40
  humidity_max: 60
  group: unknown

plants:
  Варлам:
    humidity_min: 35
    humidity_max: 55
    group: alpha

  Филипп:
    humidity_min: 40
    humidity_max: 60
    group: bravo

plugs:
  Альфа:
    group: alpha
  Браво:
    group: bravo
```

Изменения в `plant_config.yaml` применяются автоматически при следующем цикле (~60 сек), без перезапуска.

## Метрики Prometheus

### Датчики почвы

| Метрика | Описание |
|---|---|
| `tuya_plant_humidity` | Влажность почвы (%) |
| `tuya_plant_temperature` | Температура почвы (°C) |
| `tuya_plant_battery` | Заряд батареи (%) |
| `tuya_plant_humidity_threshold_min` | Минимальная оптимальная влажность (%) |
| `tuya_plant_humidity_threshold_max` | Максимальная оптимальная влажность (%) |

### Умные розетки

| Метрика | Описание |
|---|---|
| `tuya_plug_switch` | Состояние (0=выкл, 1=вкл) |
| `tuya_plug_power` | Мощность (W) |
| `tuya_plug_current` | Ток (mA) |
| `tuya_plug_voltage` | Напряжение (V) |

### Heartbeat

| Метрика | Описание |
|---|---|
| `tuya_exporter_last_success_timestamp` | Unix timestamp последнего успешного сбора |

```promql
# Алерт если данные не обновлялись > 5 минут
(time() - tuya_exporter_last_success_timestamp) > 300
```

Все метрики имеют labels: `device_id`, `device_name`, `group`, `instance="home"`.

## Структура проекта

```
tuya-exporter/
├── tuya_exporter.py           # Основной скрипт
├── wizard.py                  # Обнаружение устройств (TinyTuya)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env                       # Секреты (не в git)
├── .env.example
├── devices.json               # Список устройств, генерируется wizard (не в git)
├── devices.json.example
├── plant_config.yaml          # Пороговые значения растений (не в git)
├── plant_config.yaml.example
└── logs/                      # Логи (volume)
    └── tuya_exporter.log
```

## Troubleshooting

**Датчики не обнаруживаются**
- Убедитесь, что связали Smart Life аккаунт с проектом в Tuya IoT Platform
- Проверьте правильность региона API (EU/US/CN/IN)
- Запустите wizard: `docker compose --profile wizard run --rm tuya-wizard`

**Ошибки подключения к API**
- Проверьте правильность `TUYA_ACCESS_ID` и `TUYA_ACCESS_KEY` в `.env`
- Убедитесь, что подписаны на **IoT Core** и **Authorization**

**Данные не попадают в Pushgateway**
- Проверьте `PUSHGATEWAY_URL` в `.env`
- Проверьте логи: `docker compose logs -f`

## Лицензия

MIT
