"""
Chat Agent
Парсит команды пользователя через AI и выполняет их через Kaiten API.
"""

import os
import json
import re
from datetime import datetime, timezone
import aiohttp
import requests
from dotenv import load_dotenv

load_dotenv()

TIMEWEB_CHAT_KEY = os.getenv("TIMEWEB_CHAT_KEY")
TIMEWEB_CHAT_URL = os.getenv("TIMEWEB_CHAT_URL")
KAITEN_URL = os.getenv("KAITEN_URL")
KAITEN_TOKEN = os.getenv("KAITEN_TOKEN")
KAITEN_BOARD_ID = int(os.getenv("KAITEN_BOARD_ID", "0"))

import kaiten_analyzer as ka

HEADERS = {
    "Authorization": f"Bearer {KAITEN_TOKEN}",
    "Content-Type": "application/json"
}

COLUMN_IDS = {
    "Бэклог": 6575984,
    "В работе": 6575985,
    "Ревью": 6575986,
    "Готово": 6576071,
}


SYSTEM_PROMPT = """Ты — AI-агент для управления проектами в Kaiten. Твоя задача — понимать команды пользователя и превращать их в JSON-действия.

Сегодняшняя дата: {today}

Доступные действия:

1. list_user_tasks — показать все задачи указанного пользователя
   Пример: {"action": "list_user_tasks", "user": "Маша"}

2. list_overdue — показать все просроченные задачи
   Пример: {"action": "list_overdue"}

3. list_column — показать задачи в указанной колонке
   Пример: {"action": "list_column", "column": "Ревью"}

4. close_task — закрыть задачу (переместить в «Готово»)
   Пример: {"action": "close_task", "task_title": "Сделать сайт"}

5. move_task — переместить задачу в указанную колонку
   Пример: {"action": "move_task", "task_title": "Разработать дизайн-систему", "column": "В работе"}
   Пример: {"action": "move_task", "task_title": "Настроить API", "column": "Бэклог"}

6. add_task — создать новую задачу на указанного пользователя
   Пример: {"action": "add_task", "title": "Нарисовать картошку", "user": "Иван"}
   Пример: {"action": "add_task", "title": "Проверить дизайн", "user": "Руководитель", "due_date": "2026-11-10"}

7. update_due_date — изменить срок задачи
   Пример: {"action": "update_due_date", "task_title": "Подготовить отчёт", "due_date": "2026-10-10"}

8. add_member — добавить участника в задачу
   Пример: {"action": "add_member", "task_title": "Подготовить ТЗ на интеграцию с CRM", "user": "Иван"}
   Пример: {"action": "add_member", "task_title": "Разработать дизайн-систему", "user": "Маша"}

9. unknown — если команда непонятна
   Пример: {"action": "unknown", "reason": "Не удалось распознать команду"}

ВАЖНО:
- Для перемещения между колонками ВСЕГДА используй move_task.
- close_task — только когда пользователь явно говорит «закрой», «заверши», «готово».
- add_member — когда пользователь говорит «добавь участника», «добавь в участники», «назначь соисполнителем».
- Даты ВСЕГДА возвращай в формате YYYY-MM-DD.
- Названия колонок: «Бэклог», «В работе», «Ревью», «Готово».
- Возвращай ТОЛЬКО валидный JSON, без markdown-обёрток, без пояснений.
"""


# ============================================================
# AI: парсинг команды
# ============================================================

async def parse_command(text):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system_prompt = SYSTEM_PROMPT.replace("{today}", today)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text}
    ]
    headers = {
        "Authorization": f"Bearer {TIMEWEB_CHAT_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"model": "gpt-4o-mini", "messages": messages}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TIMEWEB_CHAT_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                if resp.status != 200:
                    return {"action": "error", "reason": f"AI вернул {resp.status}"}
                data = await resp.json()
                raw = data["choices"][0]["message"]["content"].strip()

                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return {"action": "error", "reason": f"AI вернул не-JSON: {raw[:100]}"}
    except Exception as e:
        return {"action": "error", "reason": str(e)}


# ============================================================
# УТИЛИТЫ
# ============================================================

def _stem(word):
    return word.lower().strip()[:5]


def _find_user_id(users, name):
    if not name:
        return None, None

    name_words = [_stem(w) for w in name.split() if len(w) >= 3]
    if not name_words:
        return None, None

    best_uid = None
    best_score = 0
    best_name = None

    for uid, full_name in users.items():
        full_words = [_stem(w) for w in full_name.split() if len(w) >= 3]
        score = 0
        for nw in name_words:
            for fw in full_words:
                if nw == fw or nw in fw or fw in nw:
                    score += 1
                    break
        if score > best_score:
            best_score = score
            best_uid = uid
            best_name = full_name

    if best_score >= 1:
        return best_uid, best_name
    return None, None


def _find_card_by_title(cards, title):
    title_lower = title.lower().strip()
    for card in cards:
        if card.get("title", "").lower() == title_lower:
            return card
    for card in cards:
        if title_lower in card.get("title", "").lower():
            return card
    return None


def _resolve_column(name):
    name_lower = name.lower().strip()
    for col_name, col_id in COLUMN_IDS.items():
        if name_lower in col_name.lower() or col_name.lower() in name_lower:
            return col_name, col_id
    return None, None


def _iso_due(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.replace(hour=18, minute=0, second=0).isoformat() + "Z"
    except Exception:
        return None


# ============================================================
# ДЕЙСТВИЯ
# ============================================================

def action_list_user_tasks(params):
    users = ka.get_users()
    columns = ka.get_columns()
    cards = ka.get_cards()

    name = params.get("user", "")
    uid, full_name = _find_user_id(users, name)
    if not uid:
        return f"❌ Пользователь «{name}» не найден в спринте."

    user_cards = [c for c in cards if ka.get_responsible_id(c) == uid]
    if not user_cards:
        return f"У пользователя {full_name} нет задач."

    lines = [f"📋 У {full_name} {len(user_cards)} задач:"]
    for c in user_cards:
        col = columns.get(c.get("column_id"), "?")
        due = c.get("due_date", "")
        due_str = f" (до {due[:10]})" if due else ""
        lines.append(f"  • {c['title']} [{col}]{due_str}")
    return "\n".join(lines)


def action_list_overdue(params):
    columns = ka.get_columns()
    cards = ka.get_cards()
    now = datetime.now(timezone.utc)

    overdue = []
    for c in cards:
        due = ka.parse_date(c.get("due_date"))
        col = columns.get(c.get("column_id"), "")
        if due and due < now and col != "Готово":
            overdue.append(c)

    if not overdue:
        return "🎉 Просроченных задач нет!"

    lines = [f"⚠️ Просрочено задач: {len(overdue)}"]
    for c in overdue:
        due = c.get("due_date", "")[:10]
        lines.append(f"  • {c['title']} (до {due})")
    return "\n".join(lines)


def action_list_column(params):
    columns = ka.get_columns()
    cards = ka.get_cards()

    col_name = params.get("column", "").strip().lower()
    matched = None
    for cid, ctitle in columns.items():
        if col_name in ctitle.lower():
            matched = (cid, ctitle)
            break

    if not matched:
        return f"❌ Колонка «{params.get('column')}» не найдена."

    cid, ctitle = matched
    col_cards = [c for c in cards if c.get("column_id") == cid]

    if not col_cards:
        return f"В колонке «{ctitle}» нет задач."

    lines = [f"📋 В колонке «{ctitle}» {len(col_cards)} задач:"]
    for c in col_cards:
        lines.append(f"  • {c['title']}")
    return "\n".join(lines)


def _move_card_to_column(card, column_name):
    col_name, col_id = _resolve_column(column_name)
    if not col_id:
        return f"❌ Колонка «{column_name}» не найдена. Доступные: Бэклог, В работе, Ревью, Готово."

    payload = {
        "column_id": col_id,
        "board_id": KAITEN_BOARD_ID,
    }
    r = requests.patch(
        f"{KAITEN_URL}/api/latest/cards/{card['id']}",
        headers=HEADERS,
        json=payload,
        timeout=15
    )
    if r.status_code in (200, 201):
        return f"✅ Задача «{card['title']}» перемещена в «{col_name}»."
    return f"❌ Не удалось переместить: {r.status_code} {r.text[:150]}"


def action_close_task(params):
    columns = ka.get_columns()
    cards = ka.get_cards()

    title = params.get("task_title", "")
    card = _find_card_by_title(cards, title)
    if not card:
        return f"❌ Задача «{title}» не найдена."

    if columns.get(card.get("column_id")) == "Готово":
        return f"✅ Задача «{card['title']}» уже в колонке Готово."

    return _move_card_to_column(card, "Готово")


def action_move_task(params):
    columns = ka.get_columns()
    cards = ka.get_cards()

    title = params.get("task_title", "")
    column = params.get("column", "")

    if not column:
        return "❌ Не указана колонка для перемещения."

    card = _find_card_by_title(cards, title)
    if not card:
        return f"❌ Задача «{title}» не найдена."

    current_col = columns.get(card.get("column_id"))
    target_col, _ = _resolve_column(column)
    if current_col == target_col:
        return f"ℹ️ Задача «{card['title']}» уже в колонке «{current_col}»."

    return _move_card_to_column(card, column)


def action_add_task(params):
    users = ka.get_users()
    title = params.get("title", "").strip()
    user_name = params.get("user", "").strip()
    due_date_str = params.get("due_date", "").strip()

    if not title:
        return "❌ Не указано название задачи."

    uid, full_name = _find_user_id(users, user_name)
    if not uid:
        return f"❌ Пользователь «{user_name}» не найден в спринте."

    payload = {
        "title": title,
        "board_id": KAITEN_BOARD_ID,
        "column_id": COLUMN_IDS["В работе"],
        "responsible_id": uid,
    }

    due_iso = None
    if due_date_str:
        due_iso = _iso_due(due_date_str)
        if due_iso:
            payload["due_date"] = due_iso

    r = requests.post(
        f"{KAITEN_URL}/api/latest/cards",
        headers=HEADERS,
        json=payload,
        timeout=15
    )
    if r.status_code in (200, 201):
        due_msg = f" со сроком до {due_date_str}" if due_iso else ""
        return f"✅ Задача «{title}» создана на {full_name}{due_msg}."
    return f"❌ Не удалось создать задачу: {r.status_code} {r.text[:150]}"


def action_update_due_date(params):
    cards = ka.get_cards()
    title = params.get("task_title", "")
    due_date_str = params.get("due_date", "").strip()

    if not due_date_str:
        return "❌ Не указана новая дата."

    card = _find_card_by_title(cards, title)
    if not card:
        return f"❌ Задача «{title}» не найдена."

    due_iso = _iso_due(due_date_str)
    if not due_iso:
        return f"❌ Не удалось разобрать дату «{due_date_str}». Формат: YYYY-MM-DD."

    r = requests.patch(
        f"{KAITEN_URL}/api/latest/cards/{card['id']}",
        headers=HEADERS,
        json={"due_date": due_iso},
        timeout=15
    )
    if r.status_code in (200, 201):
        return f"✅ Срок задачи «{card['title']}» изменён на {due_date_str}."
    return f"❌ Не удалось изменить срок: {r.status_code} {r.text[:150]}"


def action_add_member(params):
    users = ka.get_users()
    cards = ka.get_cards()

    title = params.get("task_title", "")
    user_name = params.get("user", "")

    if not title:
        return "❌ Не указано название задачи."
    if not user_name:
        return "❌ Не указан пользователь."

    card = _find_card_by_title(cards, title)
    if not card:
        return f"❌ Задача «{title}» не найдена."

    uid, full_name = _find_user_id(users, user_name)
    if not uid:
        return f"❌ Пользователь «{user_name}» не найден в спринте."

    # Проверяем, не является ли он уже участником (или ответственным)
    existing_members = card.get("members", [])
    for m in existing_members:
        if m.get("user_id") == uid:
            role = "ответственным" if m.get("type") == 2 else "участником"
            return f"ℹ️ {full_name} уже является {role} задачи «{card['title']}»."

    r = requests.post(
        f"{KAITEN_URL}/api/latest/cards/{card['id']}/members",
        headers=HEADERS,
        json={"user_id": uid},
        timeout=15
    )
    if r.status_code in (200, 201):
        return f"✅ {full_name} добавлен(а) участником в задачу «{card['title']}»."
    return f"❌ Не удалось добавить участника: {r.status_code} {r.text[:150]}"


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def handle_command(text):
    parsed = await parse_command(text)
    action = parsed.get("action", "unknown")

    if action == "list_user_tasks":
        result = action_list_user_tasks(parsed)
    elif action == "list_overdue":
        result = action_list_overdue(parsed)
    elif action == "list_column":
        result = action_list_column(parsed)
    elif action == "close_task":
        result = action_close_task(parsed)
    elif action == "move_task":
        result = action_move_task(parsed)
    elif action == "add_task":
        result = action_add_task(parsed)
    elif action == "update_due_date":
        result = action_update_due_date(parsed)
    elif action == "add_member":
        result = action_add_member(parsed)
    elif action == "unknown":
        result = f"🤔 Не понял команду. {parsed.get('reason', '')}\n\nПримеры команд:\n• Покажи задачи Маши\n• Покажи просроченные\n• Перенеси задачу «Дизайн-система» в Ревью\n• Закрой задачу «Настроить API»\n• Добавь задачу «Нарисовать картошку» на Ивана\n• Измени срок задачи «Отчёт» на 10.10.2026\n• Добавь Ивана в задачу «Подготовить ТЗ»"
    else:
        result = f"❌ Неизвестное действие: {action}"

    return {
        "command": text,
        "parsed": parsed,
        "result": result,
    }
