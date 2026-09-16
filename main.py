"""
PM Assistant API
"""

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import kaiten_analyzer as ka
import ai_advisor
import chat_agent

app = FastAPI(title="PM Assistant API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    text: str


def get_client_ip(request: Request):
    """Извлекает IP клиента с учётом X-Forwarded-For."""
    client_ip = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    return client_ip


def collect_dashboard_data():
    columns = ka.get_columns()
    users = ka.get_users()
    cards = ka.get_cards()

    metrics = ka.calculate_metrics(cards, columns)
    workload = ka.calculate_workload(cards, columns, users)
    forecast = ka.calculate_forecast(metrics)
    flow = ka.calculate_flow_metrics(cards, columns, metrics)

    return {
        "metrics": {
            "total": metrics["total"],
            "by_column": metrics["by_column"],
            "overdue_count": len(metrics["overdue"]),
            "overdue": [
                {
                    "id": c["id"],
                    "title": c["title"],
                    "due_date": c.get("due_date"),
                    "responsible_id": ka.get_responsible_id(c),
                }
                for c in metrics["overdue"]
            ],
            "recently_closed_count": len(metrics["recently_closed"]),
        },
        "forecast": forecast,
        "flow": flow,
        "workload": workload,
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
def get_dashboard():
    return collect_dashboard_data()


@app.get("/api/burndown")
def get_burndown(days: int = Query(14)):
    columns = ka.get_columns()
    cards = ka.get_cards()
    return ka.calculate_burndown(cards, columns, days=days)


@app.get("/api/ai-advice")
async def get_ai_advice(request: Request, force: bool = Query(False)):
    client_ip = get_client_ip(request)
    dashboard_data = collect_dashboard_data()
    result = await ai_advisor.get_ai_advice(dashboard_data, client_ip=client_ip, force_refresh=force)
    return result


@app.get("/api/ai-stats")
def get_ai_stats(request: Request):
    client_ip = get_client_ip(request)
    return ai_advisor.get_stats(client_ip)


@app.post("/api/chat")
async def chat(message: ChatMessage, request: Request):
    """Обрабатывает команду пользователя через AI-агента."""
    if not message.text.strip():
        return {"result": "❌ Пустая команда"}

    client_ip = get_client_ip(request)

    # Проверяем лимит
    allowed, reason = ai_advisor.check_chat_limit(client_ip)
    if not allowed:
        return {
            "result": reason,
            "rate_limited": True,
            "parsed": {"action": "rate_limit"},
        }

    # Выполняем команду
    result = await chat_agent.handle_command(message.text.strip())

    # Логируем только если это не ошибка
    if result.get("parsed", {}).get("action") != "error":
        ai_advisor.log_chat_request(client_ip)

    return result


@app.get("/api/chat-stats")
def get_chat_stats(request: Request):
    client_ip = get_client_ip(request)
    return ai_advisor.get_chat_stats(client_ip)
