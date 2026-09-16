import asyncio
import kaiten_analyzer as ka
import ai_advisor

async def main():
    print("📥 Собираем метрики...")
    columns = ka.get_columns()
    users = ka.get_users()
    cards = ka.get_cards()

    metrics = ka.calculate_metrics(cards, columns)
    workload = ka.calculate_workload(cards, columns, users)
    time_metrics = ka.calculate_time_metrics(cards, columns)
    forecast = ka.calculate_forecast(metrics)

    dashboard_data = {
        "metrics": {
            "total": metrics["total"],
            "by_column": metrics["by_column"],
            "overdue_count": len(metrics["overdue"]),
            "overdue": [
                {
                    "id": c["id"],
                    "title": c["title"],
                    "due_date": c.get("due_date"),
                }
                for c in metrics["overdue"]
            ],
            "recently_closed_count": len(metrics["recently_closed"]),
        },
        "forecast": forecast,
        "workload": workload,
    }

    print("🤖 Отправляем в AI...\n")
    advice = await ai_advisor.get_ai_advice(dashboard_data)
    print(advice)

if __name__ == "__main__":
    asyncio.run(main())
