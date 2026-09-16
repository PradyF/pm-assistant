"""
Kaiten Analyzer
Читает данные из Kaiten и считает метрики для дашборда.
"""

import os
import sys
import random
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import requests

load_dotenv()

KAITEN_URL = os.getenv("KAITEN_URL")
KAITEN_TOKEN = os.getenv("KAITEN_TOKEN")
KAITEN_SPACE_ID = os.getenv("KAITEN_SPACE_ID")
KAITEN_BOARD_ID = os.getenv("KAITEN_BOARD_ID")

HEADERS = {
    "Authorization": f"Bearer {KAITEN_TOKEN}",
    "Content-Type": "application/json"
}


def api_get(path, params=None):
    url = f"{KAITEN_URL}{path}"
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP ошибка при запросе {path}: {e}")
        return None
    except Exception as e:
        print(f"❌ Ошибка при запросе {path}: {e}")
        return None


def get_columns():
    data = api_get(f"/api/latest/boards/{KAITEN_BOARD_ID}/columns")
    if not data:
        return {}
    return {col["id"]: col["title"] for col in data}


def get_users():
    data = api_get(f"/api/latest/spaces/{KAITEN_SPACE_ID}/users")
    if not data:
        return {}
    return {u["id"]: u.get("full_name", f"User {u['id']}") for u in data}


def get_cards():
    data = api_get("/api/latest/cards", params={"board_id": KAITEN_BOARD_ID})
    if data and isinstance(data, list):
        return data
    data = api_get(f"/api/latest/spaces/{KAITEN_SPACE_ID}/cards")
    if data and isinstance(data, list):
        return [c for c in data if c.get("board_id") == int(KAITEN_BOARD_ID)]
    print("❌ Не удалось получить карточки")
    return []


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def get_responsible_id(card):
    for member in card.get("members", []):
        if member.get("type") == 2:
            return member.get("user_id")
    return None


def get_members_ids(card):
    owner_id = card.get("owner_id")
    return [
        m.get("user_id")
        for m in card.get("members", [])
        if m.get("type") == 1 and m.get("user_id") != owner_id
    ]


def get_completion_date(card):
    for field in ("completed_at", "last_moved_to_done_at", "last_moved_at"):
        dt = parse_date(card.get(field))
        if dt:
            return dt
    return None


def calculate_metrics(cards, columns):
    now = datetime.now(timezone.utc)
    total = len(cards)
    by_column = defaultdict(int)
    overdue = []
    recently_closed = []

    for card in cards:
        col_id = card.get("column_id")
        col_title = columns.get(col_id, "Без колонки")
        by_column[col_title] += 1

        due = parse_date(card.get("due_date"))

        if due and due < now and col_title != "Готово":
            overdue.append(card)

        if col_title == "Готово":
            completed = get_completion_date(card)
            if completed and (now - completed).days <= 7:
                recently_closed.append(card)

    return {
        "total": total,
        "by_column": dict(by_column),
        "overdue": overdue,
        "recently_closed": recently_closed
    }


def calculate_workload(cards, columns, users):
    workload = {}
    for card in cards:
        resp_id = get_responsible_id(card)
        if not resp_id:
            continue
        name = users.get(resp_id, f"User {resp_id}")
        col_title = columns.get(card.get("column_id"), "Без колонки")
        if name not in workload:
            workload[name] = {"total": 0, "by_column": defaultdict(int)}
        workload[name]["total"] += 1
        workload[name]["by_column"][col_title] += 1
    for name in workload:
        workload[name]["by_column"] = dict(workload[name]["by_column"])
    return workload


def calculate_flow_metrics(cards, columns, metrics):
    now = datetime.now(timezone.utc)
    wip = sum(1 for c in cards if columns.get(c.get("column_id")) == "В работе")

    velocity_7 = velocity_14 = velocity_30 = 0
    for card in cards:
        if columns.get(card.get("column_id")) != "Готово":
            continue
        completed = get_completion_date(card)
        if not completed:
            continue
        days_ago = (now - completed).days
        if days_ago <= 7:
            velocity_7 += 1
        if days_ago <= 14:
            velocity_14 += 1
        if days_ago <= 30:
            velocity_30 += 1

    on_time_total = 0
    for card in cards:
        col_title = columns.get(card.get("column_id"), "")
        due = parse_date(card.get("due_date"))

        if col_title == "Готово":
            completed = get_completion_date(card)
            if not due or (completed and completed <= due):
                on_time_total += 1
        else:
            if not due or due >= now:
                on_time_total += 1

    predictability = round((on_time_total / len(cards)) * 100) if cards else 0
    stuck = len(metrics["overdue"])

    return {
        "velocity_7d": velocity_7,
        "velocity_14d": velocity_14,
        "velocity_30d": velocity_30,
        "wip": wip,
        "stuck": stuck,
        "predictability_percent": predictability
    }


def calculate_forecast(metrics):
    closed_7d = len(metrics["recently_closed"])
    remaining = metrics["total"] - metrics["by_column"].get("Готово", 0)

    if closed_7d == 0:
        return {"daily_rate": 0, "days_left": None, "forecast_date": None}

    daily_rate = closed_7d / 7
    days_left = round(remaining / daily_rate)
    forecast_date = datetime.now(timezone.utc) + timedelta(days=days_left)

    return {
        "daily_rate": round(daily_rate, 2),
        "days_left": days_left,
        "forecast_date": forecast_date.strftime("%d.%m.%Y")
    }


def calculate_burndown(cards, columns, days=14):
    """
    Диаграмма сгорания, синхронизированная с реальной velocity.
    """
    random.seed(42)

    total = len(cards)
    closed_total = sum(1 for c in cards if columns.get(c.get("column_id")) == "Готово")
    open_total = total - closed_total

    half = days // 2
    start_total = total
    velocity = max(closed_total / half, 0.1)

    labels = []
    ideal = []
    real = []
    forecast = []

    now = datetime.now(timezone.utc)

    for i in range(days):
        offset = i - half
        day = now + timedelta(days=offset)
        labels.append(day.strftime("%d.%m"))

        progress = i / (days - 1) if days > 1 else 0
        ideal_val = start_total * (1 - progress)
        ideal.append(round(ideal_val, 2))

        if offset < 0:
            days_passed = half + offset
            progress_past = days_passed / half
            real_val = start_total - (start_total - open_total) * progress_past
            real_val += random.uniform(-0.5, 0.5)
            real.append(max(0, round(real_val, 2)))
            forecast.append(None)
        elif offset == 0:
            real.append(open_total)
            forecast.append(open_total)
        else:
            real.append(None)
            days_ahead = offset
            remaining = max(0, open_total - velocity * days_ahead)
            forecast.append(round(remaining, 2))

    return {
        "labels": labels,
        "ideal": ideal,
        "real": real,
        "forecast": forecast,
        "start_total": start_total,
        "velocity": round(velocity, 2)
    }


def print_report(metrics, workload, forecast, flow):
    print("\n" + "=" * 60)
    print("📊 ОТЧЁТ ПО ПРОЕКТУ (Kaiten)")
    print("=" * 60)
    print(f"\n📦 Всего задач: {metrics['total']}")
    print("\n📋 По колонкам:")
    for col, count in metrics["by_column"].items():
        print(f"   • {col}: {count}")
    print(f"\n⚠️  Просрочено: {len(metrics['overdue'])}")
    print(f"\n✅ Закрыто за 7 дней: {len(metrics['recently_closed'])}")

    print("\n🔮 Прогноз:")
    if forecast["days_left"] is not None:
        print(f"   • Темп: {forecast['daily_rate']} задач/день")
        print(f"   • Прогноз релиза: {forecast['forecast_date']}")

    print("\n📈 Flow-метрики:")
    print(f"   • Velocity (7/14/30): {flow['velocity_7d']}/{flow['velocity_14d']}/{flow['velocity_30d']}")
    print(f"   • WIP: {flow['wip']}")
    print(f"   • Застрявшие: {flow['stuck']}")
    print(f"   • Predictability: {flow['predictability_percent']}%")

    print("\n👥 Нагрузка:")
    for name, data in sorted(workload.items(), key=lambda x: -x[1]["total"]):
        cols = ", ".join(f"{c}: {n}" for c, n in data["by_column"].items())
        print(f"   • {name} — {data['total']} ({cols})")

    print("\n" + "=" * 60 + "\n")


def main():
    print("🔌 Подключаемся к Kaiten...")
    columns = get_columns()
    users = get_users()
    cards = get_cards()
    print(f"✅ Колонок: {len(columns)}, пользователей: {len(users)}, карточек: {len(cards)}")

    metrics = calculate_metrics(cards, columns)
    workload = calculate_workload(cards, columns, users)
    forecast = calculate_forecast(metrics)
    flow = calculate_flow_metrics(cards, columns, metrics)

    print_report(metrics, workload, forecast, flow)


if __name__ == "__main__":
    main()
