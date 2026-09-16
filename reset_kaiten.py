"""
Reset Kaiten
Удаляет все карточки и создаёт 25 задач с ответственными, участниками и реалистичными датами.
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

COL = {
    "Бэклог": 6575984,
    "В работе": 6575985,
    "Ревью": 6575986,
    "Готово": 6576071,
}

USERS = {
    "Яков": 1715533,
    "Саша": 1715575,
    "Маша": 1715579,
    "Иван": 1715581,
}


def get_all_cards():
    r = requests.get(
        f"{KAITEN_URL}/api/latest/cards",
        headers=HEADERS,
        params={"board_id": KAITEN_BOARD_ID},
        timeout=15
    )
    if r.status_code != 200:
        return []
    return [c for c in r.json() if c.get("board_id") == KAITEN_BOARD_ID]


def delete_card(card_id):
    r = requests.delete(f"{KAITEN_URL}/api/latest/cards/{card_id}", headers=HEADERS, timeout=15)
    return r.status_code in (200, 204)


def delete_all_cards():
    cards = get_all_cards()
    print(f"🗑️  Найдено карточек для удаления: {len(cards)}")
    deleted = 0
    for card in cards:
        if delete_card(card["id"]):
            deleted += 1
    print(f"✅ Удалено: {deleted} из {len(cards)}\n")


def add_member(card_id, user_id):
    r = requests.post(
        f"{KAITEN_URL}/api/latest/cards/{card_id}/members",
        headers=HEADERS,
        json={"user_id": user_id},
        timeout=15
    )
    return r.status_code in (200, 201)


def create_card(title, column, responsible, members=None, due_date=None):
    payload = {
        "title": title,
        "board_id": KAITEN_BOARD_ID,
        "column_id": COL[column],
    }
    if responsible in USERS:
        payload["responsible_id"] = USERS[responsible]
    if due_date:
        payload["due_date"] = due_date

    r = requests.post(f"{KAITEN_URL}/api/latest/cards", headers=HEADERS, json=payload, timeout=15)
    if r.status_code not in (200, 201):
        print(f"  ⚠️  [{column}] {title} → {r.status_code} {r.text[:150]}")
        return None

    card_id = r.json().get("id")
    members_str = ", ".join(members) if members else "—"
    print(f"  ✅ [{column}] {title} → отв: {responsible} | уч: {members_str}")

    if members:
        for name in members:
            if name in USERS:
                add_member(card_id, USERS[name])

    return card_id


def iso(days_from_now, hour=18):
    dt = datetime.now(timezone.utc) + timedelta(days=days_from_now)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


def main():
    print("🔌 Подключаемся к Kaiten...\n")
    delete_all_cards()
    print("📥 Создаём 25 задач...\n")

    # Просроченные (3) — due в прошлом
    for title, col, resp, mem, due in [
        ("Настроить API интеграции с 1С", "В работе", "Саша", ["Яков"], -5),
        ("Согласовать ТЗ с заказчиком", "Ревью", "Маша", ["Яков", "Иван"], -3),
        ("Подготовить отчёт за август", "В работе", "Иван", ["Яков"], -2),
    ]:
        create_card(title, col, resp, mem, iso(due))

    # В работе (4)
    for title, col, resp, mem, due in [
        ("Разработать личный кабинет пользователя", "В работе", "Маша", ["Саша", "Яков"], 7),
        ("Оптимизировать базу данных", "В работе", "Иван", ["Саша"], 10),
        ("Настроить CI/CD пайплайн", "В работе", "Саша", ["Иван"], 5),
        ("Разработать систему уведомлений", "В работе", "Маша", ["Иван"], 12),
    ]:
        create_card(title, col, resp, mem, iso(due))

    # Ревью (5)
    for title, col, resp, mem, due in [
        ("Проверить код модуля авторизации", "Ревью", "Саша", ["Яков"], 2),
        ("Тестирование формы регистрации", "Ревью", "Маша", ["Саша"], 3),
        ("Проверить интеграцию с платёжной системой", "Ревью", "Иван", ["Яков"], 1),
        ("Согласовать UX главной страницы", "Ревью", "Яков", ["Маша", "Саша"], 4),
        ("Проверить миграции БД", "Ревью", "Саша", ["Иван"], 2),
    ]:
        create_card(title, col, resp, mem, iso(due))

    # Бэклог (8)
    for title, col, resp, mem, due in [
        ("Разработать концепцию мобильного приложения", "Бэклог", "Маша", [], 30),
        ("Исследовать конкурентов на рынке", "Бэклог", "Иван", [], 25),
        ("Подготовить ТЗ на интеграцию с CRM", "Бэклог", "Яков", [], 20),
        ("Провести аудит текущей архитектуры", "Бэклог", "Саша", [], 28),
        ("Настроить систему аналитики", "Бэклог", "Иван", [], 35),
        ("Разработать дизайн-систему", "Бэклог", "Маша", [], 40),
        ("Подготовить план релиза Q4", "Бэклог", "Яков", [], 15),
        ("Создать бэклог на следующий спринт", "Бэклог", "Яков", [], 14),
    ]:
        create_card(title, col, resp, mem, iso(due))

    # Готово (5) — due в будущем, закрыты заранее, значит в срок
    for title, col, resp, mem, due in [
        ("Настроить SSL сертификат", "Готово", "Саша", ["Яков"], 1),
        ("Обновить главную страницу", "Готово", "Маша", ["Яков"], 2),
        ("Исправить баг в корзине", "Готово", "Иван", ["Саша"], 1),
        ("Развернуть тестовый стенд", "Готово", "Яков", ["Иван"], 3),
        ("Подготовить отчёт за квартал", "Готово", "Яков", ["Маша"], 2),
    ]:
        create_card(title, col, resp, mem, iso(due))

    print("\n🎉 Готово! 25 задач создано.")


if __name__ == "__main__":
    main()
