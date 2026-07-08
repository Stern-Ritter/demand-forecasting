# M5 Demand Forecasting Service

ML-сервис для прогнозирования спроса на основе LightGBM модели.

## Архитектура

```
nginx (80) → FastAPI app (8000) → PostgreSQL
                              → RabbitMQ → ml_worker (× N)
```

- **FastAPI** — REST API + аутентификация JWT
- **PostgreSQL** — хранение пользователей, баланса, транзакций, задач прогноза
- **RabbitMQ** — очередь задач (масштабирование воркеров)
- **ml_worker** — загружает **обученную в ноутбуке** модель LightGBM из `./model` и делает рекурсивный прогноз на `horizon` дней вперед от последней даты истории, на каждый ряд.
- **nginx** — реверс-прокси + раздача статики (SPA)

### Модель

Модель обучается в `m5_models.ipynb` (раздел 8) и сохраняется в `./model`:

| Файл | Назначение |
|------|------------|
| `lgbm_recursive.pkl` | обученный LightGBM (`LGBMRegressor`) |
| `feature_names.pkl` | порядок 41 признака, которые ожидает модель |
| `cat_features.pkl` | 8 категориальных признаков `*_enc` |
| `id_encodings.pkl` | кодировки категорий `{колонка: {значение: код}}` |

Воркер монтирует `./model` read-only (одинаково для всех реплик) и восстанавливает
те же **41 признак**, что и при обучении: короткие лаги (1,2,7,8,14), скользящие
`rmean/rstd_{7,28}`, leak-safe `*_h28_*` (со сдвигом на 28), `zero_frac_h28_30`,
`dow_mean_4w_h28`, `days_since_sale_h28`, `days_since_release`, календарь
(`dayofweek`, `is_weekend`, `weekofyear`, `dayofmonth`, `month`, `is_christmas`),
цена (`sell_price`, `price_change`, `price_discount`), `snap`, кодировки
`item/dept/cat/store/state_id` и событий `event_name_1/event_type_1/event_type_2`.

`id` ряда раскладывается по схеме M5 (`FOODS_1_001_TX_2_evaluation` →
item=`FOODS_1_001`, dept=`FOODS_1`, cat=`FOODS`, store=`TX_2`, state=`TX`).

**Будущие экзогенные значения** (которых нет в загруженном CSV): `sell_price`
переносится с последнего известного значения, `snap` = 0, события считаются
отсутствующими (код −1, как для дней без событий при обучении).

## Запуск

```bash
# Скопировать .env файлы
cp app/.env.example app/.env
cp ml_worker/.env.example ml_worker/.env
cp .env.example .env

# Запустить
docker compose up -d --build

# Масштабировать воркеры (для параллельной обработки)
docker compose up -d --scale ml_worker=3
```

- UI: http://localhost
- Swagger (полный список endpoints): http://localhost/docs
- RabbitMQ-консоль: http://localhost:15672 (логин/пароль из `.env`)

При первом старте создается схема БД, роли (`USER`, `ADMIN`) и демо-пользователь
**`demo` / `demo1234`** (баланс 1000).

## Сценарий работы

1. **Регистрация** (`/auth/signup`) — создается пользователь с балансом 0.
2. **Вход** (`/auth/signin`) — возвращает JWT токен (`Authorization: Bearer <token>`).
3. **Пополнение** (`/balance/deposit`) — пополнение баланса кредитов.
4. **Загрузка CSV** (`/forecast/upload`) — создает задачу в статусе `pending`.
5. **Запуск** (`/forecast/job/{id}/process`) — списывает кредиты и ставит задачу в очередь; воркер обрабатывает ее асинхронно.
6. **Проверка статуса** (`/forecast/job/{id}`) — `pending → processing → completed`.
7. **Скачивание проноза** (`/forecast/job/{id}/download`) — скачивание CSV-файла с прогнозом.

> Баланс/транзакции по умолчанию в валюте `RUB` (можно явно передать `currency`).

## Входной формат CSV

```csv
id,date,sales,sell_price,snap,event_name_1,event_type_1,event_type_2
FOODS_1_001_TX_2_evaluation,2016-01-01,5,2.24,1,,,
FOODS_1_001_TX_2_evaluation,2016-01-02,3,2.24,0,,,
```

- Обязательные признаки: `id`, `date`, `sales`
- Опциональные признаки: `sell_price`, `snap`, `event_name_1`, `event_type_1`, `event_type_2` (если их нет, заполняются значениями по умолчанию)
- Пример файла для загрузки: `test_webservice_sample.csv` 10 рядов × 120 дней, сохраняется в `m5_models.ipynb` (раздел 8)

## Результат

Прогноз сохраняется в CSV-файле со столбцами:

```csv
id,date,forecast
FOODS_1_001_TX_2_evaluation,2016-04-25,0.4952
```

## Тестирование

```bash
# Поднять систему (нужна для интеграционных тестов)
docker compose up -d --build

# Установить зависимости
pip install -r tests/requirements-test.txt

# Весь набор (интеграционные + unit тесты)
pytest tests/ -v

# Только unit-тесты (работают без запущенного сервиса, нужна папка ./model)
pytest tests/test_forecast.py::test_load_model_bundle_matches_notebook \
       tests/test_forecast.py::test_decompose_and_encode_m5_id \
       tests/test_forecast.py::test_add_features_builds_notebook_columns \
       tests/test_forecast.py::test_run_forecast_uses_pretrained_model \
       tests/test_forecast.py::test_run_forecast_unknown_id_is_robust \
       tests/test_forecast.py::test_ml_service_invalid_csv -v
```

## API Endpoints

Полный список и схемы — в Swagger (`/docs`). Основные:

| Method | Path | Описание |
|--------|------|----------|
| POST | `/api/1.0/auth/signup` | Регистрация |
| POST | `/api/1.0/auth/signin` | Аутентификация |
| GET  | `/api/1.0/auth/me` | Текущий пользователь |
| GET  | `/api/1.0/users/{id}` | Профиль пользователя |
| GET  | `/api/1.0/balance/{id}` | Баланс |
| POST | `/api/1.0/balance/deposit` | Пополнение баланса |
| POST | `/api/1.0/balance/withdraw` | Снятие средств |
| POST | `/api/1.0/forecast/upload` | Загрузка CSV, создание задачи на прогноз (`?horizon=28`, 1–365) |
| POST | `/api/1.0/forecast/job/{id}/process` | Запуск прогноза |
| GET  | `/api/1.0/forecast/job/{id}` | Статус задачи прогноза|
| GET  | `/api/1.0/forecast/job/{id}/download` | Скачать результат прогноза (csv-файл) |
| GET  | `/api/1.0/forecast/jobs` | Список задач прогноза |
| GET  | `/api/1.0/history/transactions/{id}` | История транзакций |
| GET  | `/api/1.0/history/forecasts/{id}` | История прогнозов |
