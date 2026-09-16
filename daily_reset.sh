#!/bin/bash
# Ежедневный сброс демо-данных в Kaiten + очистка кэша AI

cd /root/pm_assistant
source venv/bin/activate

echo "=== $(date) Начинаем сброс ==="

# Пересоздаём задачи в Kaiten
python reset_kaiten.py

# Очищаем кэш AI (метрики изменились)
python -c "
import sqlite3
conn = sqlite3.connect('/root/pm_assistant/ai_cache.db')
conn.execute('DELETE FROM ai_cache')
conn.commit()
conn.close()
print('✅ Кэш AI очищен')
"

echo "=== $(date) Сброс завершён ==="
