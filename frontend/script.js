// ============================================================
// КОНФИГ
// ============================================================
const API_BASE = '';
const COLUMN_ORDER = ['Бэклог', 'В работе', 'Ревью', 'Готово'];


// ============================================================
// УТИЛИТЫ
// ============================================================

function $(id) { return document.getElementById(id); }

function animateValue(id, target, duration = 1000, suffix = '') {
    const el = $(id);
    if (!el) return;
    const startTime = performance.now();
    function update(now) {
        const progress = Math.min((now - startTime) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = Math.floor(target * eased);
        el.textContent = value.toLocaleString('ru-RU') + suffix;
        if (progress < 1) requestAnimationFrame(update);
        else el.textContent = target.toLocaleString('ru-RU') + suffix;
    }
    requestAnimationFrame(update);
}

function showSkeletons() {
    ['m-total', 'm-overdue', 'm-wip', 'm-closed', 'f-velocity', 'f-cycle', 'f-predict', 'f-forecast'].forEach(id => {
        const el = $(id);
        if (el) { el.textContent = ''; el.classList.add('skeleton'); }
    });
}

function hideSkeletons() {
    document.querySelectorAll('.skeleton').forEach(el => el.classList.remove('skeleton'));
}


// ============================================================
// ЗАГРУЗКА
// ============================================================

async function loadDashboard() {
    try {
        const r = await fetch(API_BASE + '/api/dashboard');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        hideSkeletons();
        renderMetrics(data);
        renderFlow(data);
        renderChart(data);
        renderWorkload(data);
        renderOverdue(data);
    } catch (e) {
        console.error('Ошибка загрузки дашборда:', e);
        hideSkeletons();
    }
}

async function loadBurndown() {
    try {
        const r = await fetch(API_BASE + '/api/burndown');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        renderBurndown(data);
    } catch (e) { console.error('Ошибка burndown:', e); }
}

async function loadAiStats() {
    try {
        const r = await fetch(API_BASE + '/api/ai-stats');
        if (!r.ok) return;
        const data = await r.json();
        renderAiLimit(data);
    } catch (e) { /* тихо */ }
}

async function loadChatStats() {
    try {
        const r = await fetch(API_BASE + '/api/chat-stats');
        if (!r.ok) return;
        const data = await r.json();
        renderChatLimit(data);
    } catch (e) { /* тихо */ }
}


// ============================================================
// 1. КЛЮЧЕВЫЕ МЕТРИКИ
// ============================================================

function renderMetrics(data) {
    const m = data.metrics || {};
    animateValue('m-total', m.total || 0);
    animateValue('m-overdue', m.overdue_count || 0);
    animateValue('m-wip', (data.flow && data.flow.wip) || 0);
    animateValue('m-closed', m.recently_closed_count || 0);
}


// ============================================================
// 2. FLOW-МЕТРИКИ
// ============================================================

function renderFlow(data) {
    const f = data.flow || {};
    const forecast = data.forecast || {};
    animateValue('f-velocity', f.velocity_7d || 0);
    animateValue('f-cycle', f.stuck || 0);
    animateValue('f-predict', f.predictability_percent || 0, 1200, '%');
    const fEl = $('f-forecast');
    if (fEl) fEl.textContent = forecast.forecast_date || '—';
}


// ============================================================
// 3. ГРАФИК ПО КОЛОНКАМ
// ============================================================

let columnsChart = null;

function renderChart(data) {
    const byColumn = (data.metrics && data.metrics.by_column) || {};
    const orderedLabels = COLUMN_ORDER.filter(col => col in byColumn);
    const values = orderedLabels.map(col => byColumn[col]);
    const ctx = $('chart-columns');
    if (!ctx) return;
    if (columnsChart) columnsChart.destroy();

    const colors = [
        { bg: 'rgba(255,215,0,0.6)', bd: '#ffd700' },
        { bg: 'rgba(0,212,255,0.6)', bd: '#00d4ff' },
        { bg: 'rgba(255,107,107,0.6)', bd: '#ff6b6b' },
        { bg: 'rgba(74,222,128,0.6)', bd: '#4ade80' }
    ];

    columnsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: orderedLabels,
            datasets: [{
                data: values,
                backgroundColor: colors.map(c => c.bg),
                borderColor: colors.map(c => c.bd),
                borderWidth: 2,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            animation: { duration: 1500, easing: 'easeOutQuart' },
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: 'rgba(255,255,255,0.5)', font: { size: 12 } }, grid: { display: false } },
                y: { beginAtZero: true, ticks: { color: 'rgba(255,255,255,0.4)', font: { size: 11 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}


// ============================================================
// 4. ДИАГРАММА СГОРАНИЯ (адаптивная под мобильные)
// ============================================================

let burndownChart = null;

function renderBurndown(data) {
    const ctx = $('chart-burndown');
    if (!ctx) return;
    if (burndownChart) burndownChart.destroy();

    burndownChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [
                {
                    label: 'Идеальная линия',
                    data: data.ideal,
                    borderColor: 'rgba(255,255,255,0.25)',
                    borderDash: [6, 6],
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0,
                    spanGaps: false
                },
                {
                    label: 'Реальная линия',
                    data: data.real,
                    borderColor: '#ffd700',
                    backgroundColor: 'rgba(255,215,0,0.1)',
                    fill: true,
                    borderWidth: 3,
                    pointRadius: 0,
                    tension: 0.3,
                    spanGaps: false
                },
                {
                    label: 'Прогноз',
                    data: data.forecast,
                    borderColor: '#00d4ff',
                    borderDash: [4, 4],
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.3,
                    spanGaps: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 2000, easing: 'easeOutQuart' },
            plugins: {
                legend: {
                    labels: {
                        color: 'rgba(255,255,255,0.6)',
                        font: { size: 11 },
                        boxWidth: 12
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: 'rgba(255,255,255,0.4)',
                        font: { size: 9 },
                        maxRotation: 45,
                        minRotation: 0,
                        autoSkip: true,
                        autoSkipPadding: 15
                    },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255,255,255,0.4)',
                        font: { size: 10 },
                        stepSize: 5,
                        precision: 0
                    },
                    grid: { color: 'rgba(255,255,255,0.05)' }
                }
            }
        }
    });
}


// ============================================================
// 5. НАГРУЗКА
// ============================================================

function renderWorkload(data) {
    const workload = data.workload || {};
    const container = $('workload-list');
    if (!container) return;

    const entries = Object.entries(workload).sort((a, b) => b[1].total - a[1].total);
    if (entries.length === 0) {
        container.innerHTML = '<div class="overdue-empty">Нет данных</div>';
        return;
    }

    const maxTotal = Math.max(...entries.map(([, d]) => d.total));

    container.innerHTML = entries.map(([name, d]) => {
        const cols = Object.entries(d.by_column).map(([c, n]) => `${c}: ${n}`).join(' · ');
        return `
            <div class="workload-item">
                <div class="workload-head">
                    <span class="workload-name">${name}</span>
                    <span class="workload-total">${d.total}</span>
                </div>
                <div class="workload-bar"><div class="workload-fill" style="width:0%"></div></div>
                <div class="workload-cols">${cols}</div>
            </div>
        `;
    }).join('');

    requestAnimationFrame(() => {
        const fills = container.querySelectorAll('.workload-fill');
        fills.forEach((fill, i) => {
            const total = entries[i][1].total;
            const pct = maxTotal > 0 ? (total / maxTotal) * 100 : 0;
            setTimeout(() => {
                fill.style.transition = 'width 1s ease-out';
                fill.style.width = pct + '%';
            }, i * 100);
        });
    });
}


// ============================================================
// 6. ПРОСРОЧЕННЫЕ
// ============================================================

function renderOverdue(data) {
    const overdue = (data.metrics && data.metrics.overdue) || [];
    const container = $('overdue-list');
    if (!container) return;

    if (overdue.length === 0) {
        container.innerHTML = '<div class="overdue-empty">🎉 Просроченных задач нет!</div>';
        return;
    }

    container.innerHTML = overdue.map(task => {
        const due = task.due_date ? task.due_date.slice(0, 10) : '—';
        return `
            <div class="overdue-item">
                <span class="overdue-title">${task.title}</span>
                <span class="overdue-date">до ${due}</span>
            </div>
        `;
    }).join('');
}


// ============================================================
// 7. AI-СОВЕТНИК
// ============================================================

function renderAiLimit(stats) {
    const el = $('ai-limit');
    if (!el) return;
    if (!stats.enabled) { el.textContent = ''; return; }
    const used = stats.ip_used;
    const limit = stats.ip_limit;
    el.textContent = `Осталось запросов сегодня: ${limit - used} из ${limit}`;
    el.style.color = used >= limit ? '#ff6b6b' : 'rgba(255,255,255,0.4)';
}

async function askAI() {
    const btn = $('btn-ai');
    const status = $('ai-status');
    const adviceBox = $('ai-advice');

    btn.disabled = true;
    btn.textContent = '⏳ AI думает...';
    status.textContent = 'Анализируем метрики проекта...';
    status.style.display = 'block';
    adviceBox.classList.remove('visible');

    try {
        const r = await fetch(API_BASE + '/api/ai-advice');
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();

        if (data.rate_limited) {
            adviceBox.textContent = data.advice;
            adviceBox.classList.add('visible');
            adviceBox.style.color = '#ff6b6b';
            status.textContent = '⏳ Лимит исчерпан — попробуйте завтра';
            status.style.display = 'block';
            btn.textContent = '✨ Получить рекомендации';
            loadAiStats();
            return;
        }

        adviceBox.style.color = '';
        status.style.display = 'none';
        adviceBox.textContent = data.advice || 'Пустой ответ';
        adviceBox.classList.add('visible');
        btn.textContent = '✨ Обновить совет';
        loadAiStats();
    } catch (e) {
        status.textContent = '❌ Ошибка: ' + e.message;
        adviceBox.classList.remove('visible');
    } finally {
        btn.disabled = false;
    }
}


// ============================================================
// 8. ЧАТ-АГЕНТ
// ============================================================

function renderChatLimit(stats) {
    const el = $('chat-limit');
    if (!el) return;
    if (!stats.enabled) { el.textContent = ''; return; }
    const used = stats.ip_used;
    const limit = stats.ip_limit;
    const left = limit - used;
    el.textContent = `Команд сегодня: ${used} из ${limit} · осталось ${left}`;
    el.style.color = left <= 3 ? '#ff6b6b' : (left <= 10 ? '#ffd700' : 'rgba(255,255,255,0.3)');
}

function addChatMessage(text, type = 'bot') {
    const history = $('chat-history');
    if (!history) return;
    const hint = history.querySelector('.chat-hint');
    if (hint) hint.remove();
    const msg = document.createElement('div');
    msg.className = `chat-msg ${type}`;
    msg.textContent = text;
    history.appendChild(msg);
    history.scrollTop = history.scrollHeight;
    return msg;
}

async function sendChatCommand(text) {
    if (!text || !text.trim()) return;
    const input = $('chat-input');
    const sendBtn = $('chat-send');

    addChatMessage(text, 'user');
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    const thinking = addChatMessage('🤖 AI анализирует команду...', 'thinking');

    try {
        const r = await fetch(API_BASE + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const data = await r.json();
        thinking.remove();

        if (data.parsed && data.parsed.action === 'error') {
            addChatMessage('❌ ' + data.parsed.reason, 'error');
            loadChatStats();
            return;
        }

        addChatMessage(data.result || 'Пустой ответ', 'bot');
        loadChatStats();
    } catch (e) {
        thinking.remove();
        addChatMessage('❌ Ошибка: ' + e.message, 'error');
        loadChatStats();
    } finally {
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

function initChat() {
    const sendBtn = $('chat-send');
    const input = $('chat-input');
    if (sendBtn) sendBtn.addEventListener('click', () => sendChatCommand(input.value));
    if (input) input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); sendChatCommand(input.value); }
    });
    document.querySelectorAll('.chat-quick').forEach(btn => {
        btn.addEventListener('click', () => sendChatCommand(btn.getAttribute('data-cmd')));
    });
}


// ============================================================
// 9. ГЛАЗА РОБОТА
// ============================================================

function initRobotEyes() {
    const robot = $('robot');
    const pupilLeft = $('pupil-left');
    const pupilRight = $('pupil-right');
    if (!robot || !pupilLeft || !pupilRight) return;

    const MAX_OFFSET = 2.5;

    function move(clientX, clientY) {
        const rect = robot.getBoundingClientRect();
        const dx = clientX - (rect.left + rect.width / 2);
        const dy = clientY - (rect.top + rect.height / 2);
        const angle = Math.atan2(dy, dx);
        const distance = Math.min(Math.hypot(dx, dy), 200) / 200;
        const offsetX = Math.cos(angle) * MAX_OFFSET * distance;
        const offsetY = Math.sin(angle) * MAX_OFFSET * distance;
        pupilLeft.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
        pupilRight.style.transform = `translate(${offsetX}px, ${offsetY}px)`;
    }

    document.addEventListener('mousemove', (e) => move(e.clientX, e.clientY));
    document.addEventListener('touchmove', (e) => {
        const touch = e.touches[0];
        if (touch) move(touch.clientX, touch.clientY);
    }, { passive: true });
}


// ============================================================
// 10. РАСКРЫВАЮЩИЙСЯ СПИСОК
// ============================================================

function initCapabilities() {
    const toggle = $('cap-toggle');
    const list = $('cap-list');
    if (!toggle || !list) return;
    toggle.addEventListener('click', () => {
        list.classList.toggle('open');
        toggle.classList.toggle('open');
    });
}


// ============================================================
// 11. LIGHTBOX
// ============================================================

function initLightbox() {
    const items = document.querySelectorAll('.gallery-item');
    const lightbox = $('lightbox');
    const img = $('lightbox-img');
    const counter = $('lightbox-counter');
    const closeBtn = $('lightbox-close');
    const prevBtn = $('lightbox-prev');
    const nextBtn = $('lightbox-next');
    if (!lightbox || items.length === 0) return;

    let current = 0;
    const total = items.length;

    function show(index) {
        current = (index + total) % total;
        const item = items[current];
        const src = item.querySelector('img').getAttribute('src');
        const alt = item.querySelector('img').getAttribute('alt') || '';
        img.src = src;
        img.alt = alt;
        counter.textContent = `${current + 1} / ${total}`;
    }

    function open(index) {
        show(index);
        lightbox.classList.add('open');
        document.body.style.overflow = 'hidden';
    }

    function close() {
        lightbox.classList.remove('open');
        document.body.style.overflow = '';
    }

    items.forEach((item, idx) => item.addEventListener('click', () => open(idx)));
    closeBtn.addEventListener('click', close);
    prevBtn.addEventListener('click', (e) => { e.stopPropagation(); show(current - 1); });
    nextBtn.addEventListener('click', (e) => { e.stopPropagation(); show(current + 1); });
    lightbox.addEventListener('click', (e) => { if (e.target === lightbox) close(); });
    document.addEventListener('keydown', (e) => {
        if (!lightbox.classList.contains('open')) return;
        if (e.key === 'Escape') close();
        if (e.key === 'ArrowLeft') show(current - 1);
        if (e.key === 'ArrowRight') show(current + 1);
    });
}


// ============================================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    showSkeletons();
    loadDashboard();
    loadBurndown();
    loadAiStats();
    loadChatStats();
    initChat();
    initRobotEyes();
    initCapabilities();
    initLightbox();

    const btn = $('btn-ai');
    if (btn) btn.addEventListener('click', () => askAI());
});
