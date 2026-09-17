"""
Seed Kaiten
Создаёт виртуальных пользователей и 25 тестовых задач для демонстрации.
"""

import os
from datetime import datetime, timedelta, timezone
import requests
from dotenv import load_dotenv

load_dotenv()

KAITEN_URL = os.getenv("KAITEN_URL")
KAITEN_TOKEN = os.getenv("KAITEN_TOKEN")
KAITEN_BOARD_ID = int(os.getenv("KAITEN_BOARD_ID"))

HEADERS = {
    "Authorization": f"Bearer {KAITEN_TOKEN}",
    "Content-Type": "application/json"
}

# ID колонок
COL = {
    "Бэклог": 6575984,
    "В работе": 6575985,
    "Ревью": 6575986,
    "Готово": 6576071,
}

# Кэш пользователей
USERS = {}


def create_user(username, given, family, email):
    """Создаёт пользователя через SCIM API."""
    url = f"{KAITEN_URL}/scim/v2/Users"
    payload = {
        "userName": username,
        "name": {"givenName": given, "familyName": family},
        "emails": [{"value": email, "primary": True}]
    }
    r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
    if r.status_code in (200, 201):
        data = r.json()
        print(f"✅ Создан: {given} (id={data['id']})")
        return data["id"]
    else:
        print(f"⚠️  Ошибка {given}: {r.status_code} {r.text[:200]}")
        return None


def ensure_users():
    """Создаёт виртуальных пользователей, если их ещё нет."""
    # prady1 — уже есть, id=1715533
    USERS["Руководитель"] = 1715533

    # Саша уже создан
    USERS["Саша"] = 1715575

    # Создаём остальных
    masha_id = create_user("masha_demo", "Маша", "Демо", "masha@demo.local")
    if masha_id:
        USERS["Маша"] = masha_id

    ivan_id = create_user("ivan_demo", "Иван", "Демо", "ivan@demo.local")
    if ivan_id:
        USERS["Иван"] = ivan_id

    print(f"\n📋 Пользователи: {USERS}\n")


def create_card(title, column, owner_name=None, due_date=None, description=""):
    """Создаёт карточку в Kaiten."""
    url = f"{KAITEN_URL}/api/latest/cards"
    payload = {
        "title": title,
        "board_id": KAITEN_BOARD_ID,
        "column_id": COL[column],
        "description": description,
    }
    if owner_name and owner_name in USERS:
        payload["owner_id"] = USERS[owner_name]
    if due_date:
        payload["due_date"] = due_date

    r = requests.post(url, headers=HEADERS, json=payload, timeout=15)
    if r.status_code in (200, 201):
        print(f"  ✅ [{column}] {title} → {owner_name or 'без исполнителя'}")
        return r.json().get("id")
    else:
        print(f"  ⚠️  [{column}] {title} → {r.status_code} {r.text[:150]}")
        return None


def iso(days_from_now, hour=18):
    """Дата в ISO-формате относительно сегодня."""
    dt = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def main():
    print("🔌 Подключаемся к Kaiten...\n")
    ensure_users()

    print("📥 Создаём задачи...\n")

    # --- Просроченные (дедлайн в прошлом) ---
    overdue_tasks = [
        ("Настроить API интеграции с 1С", "В работе", "Саша", -5),
        ("Согласовать ТЗ с заказчиком", "Ревью", "Маша", -3),
        ("Подготовить отчёт за август", "В работе", "Иван", -2),
    ]
    for title, col, owner, days in overdue_tasks:
        create_card(title, col, owner, iso(days))

    # --- В работе (дедлайн в будущем) ---
    in_progress = [
        ("Разработать личный кабинет пользователя", "В работе", "Маша", 7),
        ("Оптимизировать базу данных", "В работе", "Иван", 10),
        ("Настроить CI/CD пайплайн", "В работе", "Саша", 5),
        ("Разработать систему уведомлений", "В работе", "Маша", 12),
    ]
    for title, col, owner, days in in_progress:
        create_card(title, col, owner, iso(days))

    # --- Ревью ---
    review = [
        ("Проверить код модуля авторизации", "Ревью", "Саша", 2),
        ("Тестирование формы регистрации", "Ревью", "Маша", 3),
        ("Проверить интеграцию с платежной системой", "Ревью", "Иван", 1),
        ("Согласовать UX главной страницы", "Ревью", "Руководитель", 4),
        ("Проверить миграции БД", "Ревью", "Саша", 2),
    ]
    for title, col, owner, days in review:
        create_card(title, col, owner, iso(days))

    # --- Бэклог ---
    backlog = [
        ("Разработать концепцию мобильного приложения", "Бэклог", "Маша", 30),
        ("Исследовать конкурентов на рынке", "Бэклог", "Иван", 25),
        ("Подготовить ТЗ на интеграцию с CRM", "Бэклог", "Руководитель", 20),
        ("Провести аудит текущей архитектуры", "Бэклог", "Саша", 28),
        ("Настроить систему аналитики", "Бэклог", "Иван", 35),
        ("Разработать дизайн-систему", "Бэклог", "Маша", 40),
        ("Подготовить план релиза Q4", "Бэклог", "Руководитель", 15),
        ("Создать бэклог на следующий спринт", "Бэклог", "Руководитель", 14),
    ]
    for title, col, owner, days in backlog:
        create_card(title, col, owner, iso(days))

    # --- Готово (закрыто недавно) ---
    done = [
        ("Настроить SSL сертификат", "Готово", "Саша"),
        ("Обновить главную страницу", "Готово", "Маша"),
        ("Исправить баг в корзине", "Готово", "Иван"),
        ("Развернуть тестовый стенд", "Готово", "Руководитель"),
        ("Подготовить отчёт за квартал", "Готово", "Руководитель"),
    ]
    for title, col, owner in done:
        create_card(title, col, owner, iso(-2))

    print("\n🎉 Готово! Проверьте Kaiten в браузере.")


if __name__ == "__main__":
    main()
