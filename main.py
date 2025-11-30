# bot.py  (полный, готовый к использованию)
import os
import time
import threading
import json
import sqlite3
import requests
from bs4 import BeautifulSoup
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# --- Настройки (НЕ меняй токен здесь, используй Environment Variable на Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Добавь BOT_TOKEN в Environment variables на Render")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Путь к базе и файлам
DB_PATH = "jobs.db"
SOURCES_FILE = "sources.json"
SCRAPE_INTERVAL_MIN = 30  # интервал фоновой проверки в минутах (можешь менять в sources.json или здесь)

# --- База данных: jobs, sent, users (настраиваемые параметры)
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        city TEXT,
        description TEXT,
        salary TEXT,
        schedule TEXT,
        link TEXT UNIQUE,
        source TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sent (
        chat_id INTEGER,
        job_id INTEGER,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (chat_id, job_id)
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        settings_json TEXT
    )
    """)
    conn.commit()
    return conn

db = init_db()
db_lock = threading.Lock()

# --- Пользовательские настройки (сохраняются в таблице users)
def get_user_settings(chat_id):
    cur = db.cursor()
    cur.execute("SELECT settings_json FROM users WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    if row:
        return json.loads(row[0])
    # дефолтные настройки
    settings = {
        "city": "Kaunas",
        "job": None,
        "salary": None,
        "schedule": None,
        "auto": False,
        "no_experience": False,
        "ukrainians": False,
        "no_lt": False,
        "no_en": False
    }
    save_user_settings(chat_id, settings)
    return settings

def save_user_settings(chat_id, settings):
    cur = db.cursor()
    j = json.dumps(settings, ensure_ascii=False)
    cur.execute("INSERT OR REPLACE INTO users (chat_id, settings_json) VALUES (?, ?)", (chat_id, j))
    db.commit()

# --- Работа с вакансиями в базе
def add_job_to_db(job):
    # job = dict with keys: title, city, description, salary, schedule, link, source
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO jobs (title, city, description, salary, schedule, link, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (job.get('title'), job.get('city'), job.get('description'),
              job.get('salary'), job.get('schedule'), job.get('link'), job.get('source')))
        db.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        # уже есть такая ссылка
        return None

def find_jobs_by_filters(settings, limit=20):
    # простая реализация: загружаем всё и фильтруем в питоне для гибкости
    cur = db.cursor()
    cur.execute("SELECT id, title, city, description, salary, schedule, link FROM jobs ORDER BY created_at DESC")
    rows = cur.fetchall()
    res = []
    keyword = (settings.get('job') or "").lower()
    city = (settings.get('city') or "").lower()
    min_salary = settings.get('salary')
    schedule = (settings.get('schedule') or "").lower()
    for r in rows:
        jid, title, city_v, desc, salary_v, schedule_v, link = r
        ok = True
        if keyword:
            if keyword not in (title or "").lower() and keyword not in (desc or "").lower():
                ok = False
        if city and city not in (city_v or "").lower():
            ok = False
        # salary - простая проверка: если пользователь ввёл число, проверим есть ли это в строке
        if min_salary:
            try:
                if int(min_salary) > 0:
                    if not salary_v:
                        ok = False
                    else:
                        # если зарплата указана как число в тексте — простая проверка на наличие цифр
                        # (улучшать можно парсингом числа из salary_v)
                        if str(min_salary) not in salary_v:
                            # не строгая — оставляем, но можно пометить как не прошедшее
                            ok = False
            except:
                pass
        if schedule and schedule not in (schedule_v or "").lower():
            ok = False
        # фильтры по ключевым словам в описании/заголовке
        if settings.get('no_experience'):
            if "без опыта" not in ((title or "") + " " + (desc or "")).lower():
                ok = False
        if settings.get('ukrainians'):
            if "украин" not in ((title or "") + " " + (desc or "")).lower() and "ukrain" not in ((title or "") + " " + (desc or "")).lower():
                ok = False
        if settings.get('no_lt'):
            # ищем упоминание "литов" или "lt" — если упоминаний нет, считаем OK; если вакансия требует литовский, в описании обычно указано
            if "литов" in ((title or "") + " " + (desc or "")).lower():
                ok = False
        if settings.get('no_en'):
            if "english" in ((title or "") + " " + (desc or "")).lower() or "англ" in ((title or "") + " " + (desc or "")).lower():
                ok = False
        if ok:
            res.append({
                "id": jid, "title": title, "city": city_v, "description": desc,
                "salary": salary_v, "schedule": schedule_v, "link": link
            })
        if len(res) >= limit:
            break
    return res

def mark_sent(chat_id, job_id):
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO sent (chat_id, job_id) VALUES (?, ?)", (chat_id, job_id))
        db.commit()
    except sqlite3.IntegrityError:
        pass

def is_sent(chat_id, job_id):
    cur = db.cursor()
    cur.execute("SELECT 1 FROM sent WHERE chat_id=? AND job_id=?", (chat_id, job_id))
    return cur.fetchone() is not None

# --- Источники: sources.json (настраиваемые правила)
# Пример формата sources.json:
# [
#   {
#     "name": "Example",
#     "url": "https://example.com/jobs",
#     "item_selector": ".job-item",
#     "title_selector": ".title",
#     "city_selector": ".city",
#     "description_selector": ".desc",
#     "salary_selector": ".salary",
#     "link_selector": "a"
#   }
# ]

def load_sources():
    if not os.path.exists(SOURCES_FILE):
        # создаём примерный файл
        sample = [
            {
                "name": "example",
                "url": "https://example.com/jobs",
                "item_selector": ".job-item",
                "title_selector": ".title",
                "city_selector": ".city",
                "description_selector": ".desc",
                "salary_selector": ".salary",
                "link_selector": "a"
            }
        ]
        with open(SOURCES_FILE, "w", encoding="utf-8") as f:
            json.dump(sample, f, ensure_ascii=False, indent=2)
        return sample
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def scrape_source(source):
    # пытаемся собрать вакансии по правилам
    try:
        r = requests.get(source['url'], timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.select(source.get('item_selector', ''))
        found = 0
        for it in items:
            title = it.select_one(source.get('title_selector', ''))
            title = title.get_text(strip=True) if title else (it.get_text(strip=True) or "Без заголовка")
            city = it.select_one(source.get('city_selector', ''))
            city = city.get_text(strip=True) if city else ""
            desc = it.select_one(source.get('description_selector', ''))
            desc = desc.get_text(strip=True) if desc else it.get_text(strip=True)
            salary = it.select_one(source.get('salary_selector', ''))
            salary = salary.get_text(strip=True) if salary else ""
            link_el = it.select_one(source.get('link_selector', 'a'))
            link = ""
            if link_el and link_el.has_attr("href"):
                link = link_el['href']
                if link.startswith("/"):
                    # привести к абсолютному, если нужно
                    from urllib.parse import urljoin
                    link = urljoin(source['url'], link)
            job = {
                "title": title,
                "city": city,
                "description": desc,
                "salary": salary,
                "schedule": "",
                "link": link,
                "source": source.get('name', source.get('url'))
            }
            if job['link']:
                added = add_job_to_db(job)
                if added:
                    found += 1
        return found
    except Exception as e:
        print("Scrape error for", source.get('url'), e)
        return 0

def scrape_all_sources():
    sources = load_sources()
    total_new = 0
    for s in sources:
        total_new += scrape_source(s)
    return total_new

# --- Фоновая задача: периодически сканируем и рассылаем новые вакансии
def background_worker():
    while True:
        try:
            print("Background: scraping sources...")
            new_count = scrape_all_sources()
            print("Background: new jobs:", new_count)
            # отправляем новые вакансии всем пользователям с auto=True
            cur = db.cursor()
            cur.execute("SELECT chat_id, settings_json FROM users WHERE settings_json IS NOT NULL")
            users = cur.fetchall()
            for chat_id, settings_json in users:
                settings = json.loads(settings_json)
                if settings.get('auto'):
                    # ищем подходящие вакансии (новые)
                    matches = find_jobs_by_filters(settings, limit=50)
                    for job in matches:
                        if not is_sent(chat_id, job['id']):
                            # отправляем и помечаем
                            text = f"<b>{job['title']}</b>\n{job['city']}\n{job['description']}\nЗарплата: {job['salary']}\n{job['link']}"
                            try:
                                bot.send_message(chat_id, text)
                                mark_sent(chat_id, job['id'])
                            except Exception as e:
                                print("Send error to", chat_id, e)
            # пауза
            interval = SCRAPE_INTERVAL_MIN * 60
            time.sleep(interval)
        except Exception as e:
            print("Background worker error:", e)
            time.sleep(60)

# --- Меню и Telegram-хендлеры
def main_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add(KeyboardButton("🔍 Поиск вакансий"))
    menu.add(KeyboardButton("⚙ Настройки поиска"))
    menu.add(KeyboardButton("🧩 Фильтры"))
    menu.add(KeyboardButton("📬 Авто уведомления"))
    menu.add(KeyboardButton("➕ Добавить вакансию"))
    menu.add(KeyboardButton("📋 Показать настройки"))
    return menu

def filters_menu(settings):
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add(KeyboardButton(f"Без опыта: {'ВКЛ' if settings['no_experience'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Берут украинцев: {'ВКЛ' if settings['ukrainians'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Без литовского: {'ВКЛ' if settings['no_lt'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Без английского: {'ВКЛ' if settings['no_en'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton("⬅ Назад"))
    return menu

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    # создаём настройки по умолчанию, если нет
    get_user_settings(chat_id)
    bot.send_message(chat_id, "Привет! Я ищу вакансии. Выбери действие:", reply_markup=main_menu())

@bot.message_handler(commands=['settings'])
def show_settings_cmd(message):
    s = get_user_settings(message.chat.id)
    bot.send_message(message.chat.id, "Твои настройки:\n" + json.dumps(s, ensure_ascii=False, indent=2))

@bot.message_handler(func=lambda m: True)
def all_messages_handler(message):
    chat_id = message.chat.id
    text = message.text or ""
    settings = get_user_settings(chat_id)

    # Главное меню
    if text == "🔍 Поиск вакансий":
        matches = find_jobs_by_filters(settings, limit=10)
        if not matches:
            bot.send_message(chat_id, "Вакансий не найдено.")
        else:
            for job in matches:
                txt = f"<b>{job['title']}</b>\n{job['city']}\n{job['description']}\nЗарплата: {job['salary']}\n{job['link']}"
                bot.send_message(chat_id, txt)

    elif text == "⚙ Настройки поиска":
        bot.send_message(chat_id,
                         "Напиши одно из слов: город, вакансия, зарплата, график\nНапример: город\nПосле этого введи значение.",
                         reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅ Назад")))

    elif text == "🧩 Фильтры":
        bot.send_message(chat_id, "Фильтры:", reply_markup=filters_menu(settings))

    elif text.startswith("Без опыта"):
        settings['no_experience'] = not settings.get('no_experience', False)
        save_user_settings(chat_id, settings)
        bot.send_message(chat_id, f"Без опыта: {'ВКЛ' if settings['no_experience'] else 'ВЫКЛ'}", reply_markup=filters_menu(settings))

    elif text.startswith("Берут украинцев"):
        settings['ukrainians'] = not settings.get('ukrainians', False)
        save_user_settings(chat_id, settings)
        bot.send_message(chat_id, f"Берут украинцев: {'ВКЛ' if settings['ukrainians'] else 'ВЫКЛ'}", reply_markup=filters_menu(settings))

    elif text.startswith("Без литовского"):
        settings['no_lt'] = not settings.get('no_lt', False)
        save_user_settings(chat_id, settings)
        bot.send_message(chat_id, f"Без литовского: {'ВКЛ' if settings['no_lt'] else 'ВЫКЛ'}", reply_markup=filters_menu(settings))

    elif text.startswith("Без английского"):
        settings['no_en'] = not settings.get('no_en', False)
        save_user_settings(chat_id, settings)
        bot.send_message(chat_id, f"Без английского: {'ВКЛ' if settings['no_en'] else 'ВЫКЛ'}", reply_markup=filters_menu(settings))

    elif text == "⬅ Назад":
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu())

    elif text == "📬 Авто уведомления":
        settings['auto'] = not settings.get('auto', False)
        save_user_settings(chat_id, settings)
        bot.send_message(chat_id, f"Авто-уведомления: {'ВКЛ' if settings['auto'] else 'ВЫКЛ'}", reply_markup=main_menu())

    elif text == "➕ Добавить вакансию":
        bot.send_message(chat_id, "Отправь вакансию в формате (через |):\nНазвание | Город | Краткое описание | Зарплата | График | Ссылка")
        bot.register_next_step_handler(message, manual_add_handler)

    elif text == "📋 Показать настройки":
        bot.send_message(chat_id, "Текущие настройки:\n" + json.dumps(settings, ensure_ascii=False, indent=2), reply_markup=main_menu())

    # обработка ключевых слов для настроек
    elif text.lower() in ["город", "vacancy", "вакансия", "зарплата", "график", "city", "job", "salary", "schedule"]:
        # если пользователь написал слово "город" — ждем ввода города
        ask = ""
        if "город" in text.lower() or "city" in text.lower():
            ask = "Введи город:"
            bot.register_next_step_handler(message, set_city)
        elif "вакансия" in text.lower() or "job" in text.lower() or "vacancy" in text.lower():
            ask = "Введи название вакансии (ключевое слово):"
            bot.register_next_step_handler(message, set_job)
        elif "зарплата" in text.lower() or "salary" in text.lower():
            ask = "Введи минимальную зарплату (число):"
            bot.register_next_step_handler(message, set_salary)
        elif "график" in text.lower() or "schedule" in text.lower():
            ask = "Введи график (полная/смены/полдня и т.д.):"
            bot.register_next_step_handler(message, set_schedule)
        if ask:
            bot.send_message(chat_id, ask)

    else:
        # общий текст — можно обработать как /search <ключ>
        if text.startswith("/search "):
            keyword = text.split("/search ",1)[1].strip()
            settings['job'] = keyword
            matches = find_jobs_by_filters(settings, limit=20)
            if not matches:
                bot.send_message(chat_id, "Ничего не найдено по запросу.")
            else:
                for job in matches:
                    txt = f"<b>{job['title']}</b>\n{job['city']}\n{job['description']}\n{job['salary']}\n{job['link']}"
                    bot.send_message(chat_id, txt)
        else:
            bot.send_message(chat_id, "Не понял. Используй меню или /search <слово>.", reply_markup=main_menu())

def manual_add_handler(message):
    chat_id = message.chat.id
    text = message.text or ""
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 6:
        bot.send_message(chat_id, "Неверный формат. Пример:\nНазвание | Город | Описание | Зарплата | График | Ссылка")
        return
    job = {
        "title": parts[0],
        "city": parts[1],
        "description": parts[2],
        "salary": parts[3],
        "schedule": parts[4],
        "link": parts[5],
        "source": f"manual:{chat_id}"
    }
    added = add_job_to_db(job)
    if added:
        bot.send_message(chat_id, "Вакансия добавлена и сохранена в базе.", reply_markup=main_menu())
    else:
        bot.send_message(chat_id, "Эта вакансия уже есть в базе.", reply_markup=main_menu())

def set_city(message):
    chat_id = message.chat.id
    settings = get_user_settings(chat_id)
    settings['city'] = message.text
    save_user_settings(chat_id, settings)
    bot.send_message(chat_id, "Город обновлён.", reply_markup=main_menu())

def set_job(message):
    chat_id = message.chat.id
    settings = get_user_settings(chat_id)
    settings['job'] = message.text
    save_user_settings(chat_id, settings)
    bot.send_message(chat_id, "Ключевое слово вакансии сохранено.", reply_markup=main_menu())

def set_salary(message):
    chat_id = message.chat.id
    settings = get_user_settings(chat_id)
    settings['salary'] = message.text
    save_user_settings(chat_id, settings)
    bot.send_message(chat_id, "Зарплата сохранена.", reply_markup=main_menu())

def set_schedule(message):
    chat_id = message.chat.id
    settings = get_user_settings(chat_id)
    settings['schedule'] = message.text
    save_user_settings(chat_id, settings)
    bot.send_message(chat_id, "График сохранён.", reply_markup=main_menu())

# --- Запуск фонового потока
bg_thread = threading.Thread(target=background_worker, daemon=True)
bg_thread.start()

# --- Запуск бота (polling)
if __name__ == "__main__":
    print("Bot started")
    bot.polling(none_stop=True)

