# 3x-ui Telegram Bot

Telegram-бот для управления [3x-ui панелью](https://github.com/MHSanaei/3x-ui) — просмотр инбаундов и создание клиентских подключений прямо из Telegram.

## Возможности

- 🔌 Подключение к 3x-ui через официальный REST API
- 📋 Просмотр всех инбаундов с деталями (протокол, порт, количество клиентов)
- ➕ Создание нового клиента по выбранному инбаунду с привязкой к Telegram ID
- 🔐 Поддержка протоколов: **VMess, VLESS, Trojan, Shadowsocks**
- 📎 Автоматическое получение ссылки подключения после создания клиента
- 🛡️ Ограничение доступа по Telegram ID (whitelist администраторов)
- ♻️ Автоматический re-login при истечении сессии

## Структура файлов

```
3xui-telegram-bot/
├── bot.py          # Основной файл бота (aiogram 3.x)
├── panel_api.py    # Async клиент для 3x-ui REST API
├── .env.example    # Пример конфигурации
├── requirements.txt
└── README.md
```

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/GraveGoose/3xui-telegram-bot.git
cd 3xui-telegram-bot
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

### 3. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 4. Настройка конфигурации

```bash
cp .env.example .env
nano .env
```

Заполните `.env`:

```env
BOT_TOKEN=1234567890:AABBccDDeeFFggHH...        # Токен от @BotFather
ADMIN_IDS=123456789,987654321                    # Ваши Telegram ID
PANEL_URL=http://1.2.3.4:54321                   # URL вашей 3x-ui панели
PANEL_USERNAME=admin                             # Логин от панели
PANEL_PASSWORD=your_password                     # Пароль от панели
```

> **Как узнать свой Telegram ID**: напишите боту [@userinfobot](https://t.me/userinfobot)

### 5. Запуск

```bash
python bot.py
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и список команд |
| `/status` | Проверка подключения к панели |
| `/inbounds` | Список всех инбаундов с деталями |
| `/create` | Интерактивное создание нового клиента |

## Процесс создания клиента (`/create`)

1. Бот запрашивает список активных инбаундов из панели
2. Вы выбираете инбаунд нажатием на inline-кнопку
3. Вводите имя/email клиента
4. Указываете лимит IP-подключений (0 = без ограничений)
5. Указываете срок действия в днях (0 = бессрочно)
6. Указываете лимит трафика в ГБ (0 = без ограничений)
7. Бот создаёт клиента и возвращает ссылку для подключения

Привязка клиента к Telegram ID происходит **автоматически** — используется `id` того, кто выполняет команду `/create`.

## Требования к 3x-ui

- Версия 3x-ui: **2.x и выше**
- API должен быть включён в настройках панели
- Панель должна быть доступна по сети с сервера, где запущен бот

## API Endpoints используемые ботом

| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/login` | Авторизация |
| GET | `/xui/API/inbounds` | Список всех инбаундов |
| GET | `/xui/API/inbounds/get/{id}` | Данные инбаунда |
| POST | `/xui/API/inbounds/addClient` | Добавление клиента |
| GET | `/xui/API/inbounds/getClientUrl/{id}/{email}` | Ссылка клиента |
| GET | `/xui/API/inbounds/getClientTraffics/{email}` | Трафик клиента |
| POST | `/xui/API/inbounds/{id}/delClient/{uuid}` | Удаление клиента |
| POST | `/xui/API/inbounds/{id}/resetClientTraffic/{email}` | Сброс трафика |

## Запуск как systemd-сервис (Linux)

Создайте файл `/etc/systemd/system/3xui-bot.service`:

```ini
[Unit]
Description=3x-ui Telegram Bot
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/3xui-telegram-bot
ExecStart=/opt/3xui-telegram-bot/venv/bin/python bot.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/3xui-telegram-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable 3xui-bot
sudo systemctl start 3xui-bot
sudo systemctl status 3xui-bot
```

## Устранение проблем

| Проблема | Решение |
|---------|---------|
| `❌ Не удалось подключиться` | Проверьте PANEL_URL, доступность панели, правильность логина/пароля |
| `Протокол не поддерживается` | Убедитесь что инбаунд использует vmess/vless/trojan/shadowsocks |
| `SSL ошибки` | Если панель на HTTP — убедитесь что URL начинается с `http://` |
| Бот не отвечает | Проверьте BOT_TOKEN, убедитесь что бот не запущен дважды |

## Лицензия

MIT License
