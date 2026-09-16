"""
AI Advisor с кэшированием и rate limit.
"""

import os
import json
import hashlib
import sqlite3
from datetime import datetime, timezone, timedelta
import aiohttp
from dotenv import load_dotenv

load_dotenv()

TIMEWEB_CHAT_KEY = os.getenv("TIMEWEB_CHAT_KEY")
TIMEWEB_CHAT_URL = os.getenv("TIMEWEB_CHAT_URL")

# Лимиты для AI-советника
AI_RATE_LIMIT_ENABLED = os.getenv("AI_RATE_LIMIT_ENABLED", "true").lower() == "true"
AI_RATE_LIMIT_PER_IP = int(os.getenv("AI_RATE_LIMIT_PER_IP", "5"))
AI_RATE_LIMIT_GLOBAL = int(os.getenv("AI_RATE_LIMIT_GLOBAL", "30"))

# Лимиты для чата
CHAT_RATE_LIMIT_ENABLED = os.getenv("CHAT_RATE_LIMIT_ENABLED", "true").lower() == "true"
CHAT_RATE_LIMIT_COOLDOWN = int(os.getenv("CHAT_RATE_LIMIT_COOLDOWN", "3"))
CHAT_RATE_LIMIT_PER_IP = int(os.getenv("CHAT_RATE_LIMIT_PER_IP", "30"))
CHAT_RATE_LIMIT_GLOBAL = int(os.getenv("CHAT_RATE_LIMIT_GLOBAL", "200"))

CACHE_DB = "/root/pm_assistant/ai_cache.db"


SYSTEM_PROMPT = """Ты — опытный Project Manager с 10+ летним стажем. Анализируешь метрики проекта из трекера Kaiten и даёшь конкретные, практичные рекомендации.

Твои принципы:
1. Рекомендации должны быть конкретными и действенными, а не общими фразами.
2. Указывай на риски: просрочки, перегрузы, узкие места в процессе.
3. Предлагай решения: что перераспределить, кого разгрузить, какой процесс ускорить.
4. Будь краток: максимум 3–5 рекомендаций. Каждая — 1–2 предложения.
5. Пиши по-русски, деловым, но живым языком.

Формат ответа:
🎯 Главный риск: <одно предложение>
💡 Рекомендации:
1. <рекомендация>
2. <рекомендация>
3. <рекомендация>
"""


# ============================================================
# ИНИЦИАЛИЗАЦИЯ БД
# ============================================================

def init_cache():
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metrics_hash TEXT UNIQUE,
                advice TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT,
                created_at TEXT
            )
        """)
        conn.commit()


# ============================================================
# RATE LIMIT: AI-СОВЕТНИК
# ============================================================

def check_rate_limit(ip):
    if not AI_RATE_LIMIT_ENABLED:
        return True, ""

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    with sqlite3.connect(CACHE_DB) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM ai_requests WHERE ip = ? AND created_at > ?",
            (ip, day_ago)
        )
        ip_count = cur.fetchone()[0]
        if ip_count >= AI_RATE_LIMIT_PER_IP:
            return False, f"Превышен лимит с вашего IP ({AI_RATE_LIMIT_PER_IP} запросов в сутки). Попробуйте завтра."

        cur = conn.execute(
            "SELECT COUNT(*) FROM ai_requests WHERE created_at > ?",
            (day_ago,)
        )
        global_count = cur.fetchone()[0]
        if global_count >= AI_RATE_LIMIT_GLOBAL:
            return False, f"Превышен общий лимит запросов ({AI_RATE_LIMIT_GLOBAL} в сутки). Попробуйте завтра."

    return True, ""


def log_request(ip):
    if not AI_RATE_LIMIT_ENABLED:
        return
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT INTO ai_requests (ip, created_at) VALUES (?, ?)",
            (ip, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()


def get_stats(ip):
    if not AI_RATE_LIMIT_ENABLED:
        return {"enabled": False}

    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    with sqlite3.connect(CACHE_DB) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM ai_requests WHERE ip = ? AND created_at > ?",
            (ip, day_ago)
        )
        ip_used = cur.fetchone()[0]

        cur = conn.execute(
            "SELECT COUNT(*) FROM ai_requests WHERE created_at > ?",
            (day_ago,)
        )
        global_used = cur.fetchone()[0]

    return {
        "enabled": True,
        "ip_used": ip_used,
        "ip_limit": AI_RATE_LIMIT_PER_IP,
        "global_used": global_used,
        "global_limit": AI_RATE_LIMIT_GLOBAL,
    }


# ============================================================
# RATE LIMIT: ЧАТ
# ============================================================

def check_chat_limit(ip):
    """Проверяет: cooldown + суточный лимит по IP + общий."""
    if not CHAT_RATE_LIMIT_ENABLED:
        return True, ""

    init_cache()
    now = datetime.now(timezone.utc)

    with sqlite3.connect(CACHE_DB) as conn:
        # 1. Cooldown
        cur = conn.execute(
            "SELECT created_at FROM chat_requests WHERE ip = ? ORDER BY id DESC LIMIT 1",
            (ip,)
        )
        row = cur.fetchone()
        if row:
            last_dt = datetime.fromisoformat(row[0])
            delta = (now - last_dt).total_seconds()
            if delta < CHAT_RATE_LIMIT_COOLDOWN:
                wait = int(CHAT_RATE_LIMIT_COOLDOWN - delta) + 1
                return False, f"⏳ Слишком часто. Подождите {wait} сек."

        # 2. Суточный лимит по IP
        day_ago = (now - timedelta(hours=24)).isoformat()
        cur = conn.execute(
            "SELECT COUNT(*) FROM chat_requests WHERE ip = ? AND created_at > ?",
            (ip, day_ago)
        )
        ip_count = cur.fetchone()[0]
        if ip_count >= CHAT_RATE_LIMIT_PER_IP:
            return False, f"⏳ Дневной лимит ({CHAT_RATE_LIMIT_PER_IP} команд). Попробуйте завтра."

        # 3. Общий лимит
        cur = conn.execute(
            "SELECT COUNT(*) FROM chat_requests WHERE created_at > ?",
            (day_ago,)
        )
        global_count = cur.fetchone()[0]
        if global_count >= CHAT_RATE_LIMIT_GLOBAL:
            return False, "⏳ Общий дневной лимит исчерпан. Попробуйте завтра."

    return True, ""


def log_chat_request(ip):
    if not CHAT_RATE_LIMIT_ENABLED:
        return
    init_cache()
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT INTO chat_requests (ip, created_at) VALUES (?, ?)",
            (ip, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()


def get_chat_stats(ip):
    if not CHAT_RATE_LIMIT_ENABLED:
        return {"enabled": False}

    init_cache()
    now = datetime.now(timezone.utc)
    day_ago = (now - timedelta(hours=24)).isoformat()

    with sqlite3.connect(CACHE_DB) as conn:
        cur = conn.execute(
            "SELECT COUNT(*) FROM chat_requests WHERE ip = ? AND created_at > ?",
            (ip, day_ago)
        )
        ip_used = cur.fetchone()[0]

        cur = conn.execute(
            "SELECT COUNT(*) FROM chat_requests WHERE created_at > ?",
            (day_ago,)
        )
        global_used = cur.fetchone()[0]

    return {
        "enabled": True,
        "ip_used": ip_used,
        "ip_limit": CHAT_RATE_LIMIT_PER_IP,
        "global_used": global_used,
        "global_limit": CHAT_RATE_LIMIT_GLOBAL,
    }


# ============================================================
# КЭШ
# ============================================================

def compute_hash(dashboard_data):
    metrics = dashboard_data.get("metrics", {})
    workload = dashboard_data.get("workload", {})
    forecast = dashboard_data.get("forecast", {})

    payload = {
        "total": metrics.get("total"),
        "by_column": metrics.get("by_column"),
        "overdue_count": metrics.get("overdue_count"),
        "recently_closed_count": metrics.get("recently_closed_count"),
        "workload": {name: data.get("total") for name, data in workload.items()},
        "forecast_days": forecast.get("days_left"),
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def get_cached(hash_value):
    with sqlite3.connect(CACHE_DB) as conn:
        cur = conn.execute(
            "SELECT advice, created_at FROM ai_cache WHERE metrics_hash = ?",
            (hash_value,)
        )
        row = cur.fetchone()
        if row:
            return {"advice": row[0], "created_at": row[1]}
    return None


def save_cache(hash_value, advice):
    with sqlite3.connect(CACHE_DB) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ai_cache (metrics_hash, advice, created_at) VALUES (?, ?, ?)",
            (hash_value, advice, datetime.now(timezone.utc).isoformat())
        )
        conn.commit()


# ============================================================
# ПРОМПТ
# ============================================================

def build_user_message(dashboard_data):
    metrics = dashboard_data.get("metrics", {})
    forecast = dashboard_data.get("forecast", {})
    workload = dashboard_data.get("workload", {})

    workload_lines = []
    for name, data in sorted(workload.items(), key=lambda x: -x[1]["total"]):
        cols = ", ".join(f"{c}: {n}" for c, n in data["by_column"].items())
        workload_lines.append(f"  • {name} — {data['total']} задач ({cols})")
    workload_str = "\n".join(workload_lines) if workload_lines else "  (нет данных)"

    overdue_lines = []
    for task in metrics.get("overdue", []):
        overdue_lines.append(f"  • {task['title']} (дедлайн: {task.get('due_date', '')[:10]})")
    overdue_str = "\n".join(overdue_lines) if overdue_lines else "  (нет просрочек)"

    return f"""Проанализируй метрики проекта:

📦 Всего задач: {metrics.get('total', 0)}
📋 По колонкам: {json.dumps(metrics.get('by_column', {}), ensure_ascii=False)}
⚠️ Просрочено: {metrics.get('overdue_count', 0)}
{overdue_str}
✅ Закрыто за 7 дней: {metrics.get('recently_closed_count', 0)}

🔮 Прогноз:
  • Темп: {forecast.get('daily_rate', 0)} задач/день
  • Осталось дней: {forecast.get('days_left', '—')}
  • Прогноз релиза: {forecast.get('forecast_date', '—')}

👥 Нагрузка команды:
{workload_str}

Дай анализ и 3–5 конкретных рекомендаций."""


# ============================================================
# AI-ЗАПРОС
# ============================================================

async def _call_ai(dashboard_data):
    if not TIMEWEB_CHAT_KEY or not TIMEWEB_CHAT_URL:
        return "❌ Не настроен AI: отсутствует TIMEWEB_CHAT_KEY или TIMEWEB_CHAT_URL в .env"

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(dashboard_data)}
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
                    text = await resp.text()
                    return f"❌ Ошибка AI ({resp.status}): {text[:300]}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Ошибка при обращении к AI: {e}"


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def get_ai_advice(dashboard_data, client_ip="unknown", force_refresh=False):
    init_cache()
    h = compute_hash(dashboard_data)

    if not force_refresh:
        cached = get_cached(h)
        if cached:
            return {
                "advice": cached["advice"],
                "from_cache": True,
                "cached_at": cached["created_at"],
            }

    allowed, reason = check_rate_limit(client_ip)
    if not allowed:
        return {
            "advice": reason,
            "from_cache": False,
            "rate_limited": True,
        }

    advice = await _call_ai(dashboard_data)
    save_cache(h, advice)
    log_request(client_ip)

    return {
        "advice": advice,
        "from_cache": False,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
