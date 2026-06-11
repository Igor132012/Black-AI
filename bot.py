import asyncio
import sqlite3
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp
import logging

logging.basicConfig(level=logging.WARNING)

BOT_TOKEN = "8273539178:AAHUNBQZjFf9lhGOyBrE91pb-OkeDBRlQoE"
OWNER_ID = 6941792152
CHANNEL_USERNAME = "@TMaster_channel"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Кнопки под строкой ввода
main_menu_buttons = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏠 Главное меню")],
        [KeyboardButton(text="🔙 Назад")]
    ],
    resize_keyboard=True
)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    
    cur.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        rights TEXT DEFAULT '{}'
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cur.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cur.fetchall()]
    if 'last_seen' not in columns:
        cur.execute("ALTER TABLE users ADD COLUMN last_seen TIMESTAMP")
        cur.execute("UPDATE users SET last_seen = first_seen")
    
    cur.execute('''CREATE TABLE IF NOT EXISTS blocked_users (
        user_id INTEGER PRIMARY KEY,
        blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS hidden_news (
        admin_id INTEGER,
        news_id INTEGER,
        PRIMARY KEY (admin_id, news_id)
    )''')
    
    cur.execute("PRAGMA table_info(admins)")
    columns = [col[1] for col in cur.fetchall()]
    if 'full_name' not in columns:
        cur.execute("ALTER TABLE admins ADD COLUMN full_name TEXT")
    if 'rights' not in columns:
        cur.execute("ALTER TABLE admins ADD COLUMN rights TEXT DEFAULT '{}'")
    
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        question TEXT,
        answered INTEGER DEFAULT 0,
        answer TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS news_suggestions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        text TEXT,
        photo_file_id TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS donations_crypto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        amount REAL,
        status TEXT DEFAULT 'pending'
    )''')
    
    cur.execute("INSERT OR IGNORE INTO admins (user_id, username, full_name, rights) VALUES (?, ?, ?, ?)",
                (OWNER_ID, "owner", "Владелец", '{"questions":1,"news":1,"donations":1,"admins":1,"notify":1,"users":1}'))
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('channel_id', '')")
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('wallet', 'EQD8kqYh3X7...ваш_кошелек')")
    conn.commit()
    conn.close()

init_db()

def get_setting(key):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def get_admin_rights(user_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT rights FROM admins WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return json.loads(row[0])
    return {}

def set_admin_rights(user_id, right, value):
    rights = get_admin_rights(user_id)
    rights[right] = value
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("UPDATE admins SET rights=? WHERE user_id=?", (json.dumps(rights), user_id))
    conn.commit()
    conn.close()

def add_admin(user_id, username, full_name):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO admins (user_id, username, full_name, rights) VALUES (?, ?, ?, ?)",
                (user_id, username, full_name, '{}'))
    conn.commit()
    conn.close()

def remove_admin(user_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM admins WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_admins():
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, full_name, rights FROM admins")
    rows = cur.fetchall()
    conn.close()
    return rows

def is_user_blocked(user_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,))
    res = cur.fetchone()
    conn.close()
    return res is not None

def block_user(user_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO blocked_users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def update_user_activity(user_id):
    if is_user_blocked(user_id):
        return
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def add_user(user_id, username, full_name):
    if is_user_blocked(user_id):
        return
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                (user_id, username, full_name))
    cur.execute("UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_active_users_count():
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(DISTINCT u.user_id) 
        FROM users u
        LEFT JOIN blocked_users b ON u.user_id = b.user_id
        WHERE b.user_id IS NULL
    """)
    count = cur.fetchone()[0]
    conn.close()
    return count

def get_last_active_users(limit=10):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("""
        SELECT u.user_id, u.username, u.full_name, u.last_seen
        FROM users u
        LEFT JOIN blocked_users b ON u.user_id = b.user_id
        WHERE b.user_id IS NULL
        ORDER BY u.last_seen DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows

def user_exists_in_db(username):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def hide_news(admin_id, news_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO hidden_news (admin_id, news_id) VALUES (?, ?)", (admin_id, news_id))
    conn.commit()
    conn.close()

def is_news_hidden(admin_id, news_id):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM hidden_news WHERE admin_id=? AND news_id=?", (admin_id, news_id))
    res = cur.fetchone()
    conn.close()
    return res is not None

async def get_ton_price():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd,rub") as resp:
                data = await resp.json()
                return data.get('the-open-network', {}).get('usd', 0), data.get('the-open-network', {}).get('rub', 0)
    except:
        return 0, 0

# ========== FSM ==========
class AskQuestion(StatesGroup):
    waiting = State()

class SuggestNews(StatesGroup):
    text_wait = State()
    photo_wait = State()

class ReplyQuestion(StatesGroup):
    answer_wait = State()

class CheckDonation(StatesGroup):
    amount_wait = State()

class SetChannel(StatesGroup):
    channel_wait = State()

class SetWalletState(StatesGroup):
    wallet_wait = State()

class AddAdminState(StatesGroup):
    username_wait = State()

class NotifyState(StatesGroup):
    waiting_for_message = State()

# ========== КЛАВИАТУРЫ ==========
def main_inline_keyboard(user_id):
    kb = [
        [InlineKeyboardButton(text="❓ Задать вопрос", callback_data="ask")],
        [InlineKeyboardButton(text="📰 Предложить новость", callback_data="news")],
        [InlineKeyboardButton(text="💰 Курс TON", callback_data="rate")],
        [InlineKeyboardButton(text="💎 Поддержать", callback_data="support")]
    ]
    if is_admin(user_id):
        kb.append([InlineKeyboardButton(text="⚙️ Админ-меню", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_inline_keyboard(user_id):
    rights = get_admin_rights(user_id)
    kb = []
    if rights.get('questions') or user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="❓ Вопросы", callback_data="admin_questions")])
    if rights.get('news') or user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="📰 Новости", callback_data="admin_news")])
    if user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="💸 Пожертвования", callback_data="admin_donations")])
    if rights.get('notify') or user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="📢 Оповестить", callback_data="admin_notify")])
    if rights.get('users') or user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")])
    if rights.get('admins') or user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="👥 Администраторы", callback_data="admin_list_menu")])
    if user_id == OWNER_ID:
        kb.append([InlineKeyboardButton(text="📢 Указать канал", callback_data="set_channel")])
        kb.append([InlineKeyboardButton(text="👛 Указать кошелёк", callback_data="set_wallet")])
        kb.append([InlineKeyboardButton(text="➕ Назначить админа", callback_data="add_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_list_keyboard(admins):
    kb = []
    for user_id, username, full_name, rights_str in admins:
        if user_id == OWNER_ID:
            display_name = full_name
        else:
            display_name = f"@{username}" if username and username != "owner" else full_name
        kb.append([InlineKeyboardButton(text=display_name, callback_data=f"admin_edit_{user_id}")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_edit_keyboard(user_id, rights):
    kb = []
    if user_id != OWNER_ID:
        kb.append([InlineKeyboardButton(text=f"❓ Вопросы: {'✅' if rights.get('questions') else '❌'}", 
                              callback_data=f"toggle_{user_id}_questions_{0 if rights.get('questions') else 1}")])
        kb.append([InlineKeyboardButton(text=f"📰 Новости: {'✅' if rights.get('news') else '❌'}", 
                              callback_data=f"toggle_{user_id}_news_{0 if rights.get('news') else 1}")])
        kb.append([InlineKeyboardButton(text=f"📢 Оповещение: {'✅' if rights.get('notify') else '❌'}", 
                              callback_data=f"toggle_{user_id}_notify_{0 if rights.get('notify') else 1}")])
        kb.append([InlineKeyboardButton(text=f"👥 Пользователи: {'✅' if rights.get('users') else '❌'}", 
                              callback_data=f"toggle_{user_id}_users_{0 if rights.get('users') else 1}")])
        kb.append([InlineKeyboardButton(text=f"👑 Назначение админов: {'✅' if rights.get('admins') else '❌'}", 
                              callback_data=f"toggle_{user_id}_admins_{0 if rights.get('admins') else 1}")])
        kb.append([InlineKeyboardButton(text="❌ Снять", callback_data=f"remove_{user_id}")])
    else:
        kb.append([InlineKeyboardButton(text="👑 Владелец", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_list_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def support_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Звёзды", callback_data="stars_donate")],
        [InlineKeyboardButton(text="🪙 TON", callback_data="crypto_donate")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ])

def stars_amount_keyboard():
    kb = [[InlineKeyboardButton(text=f"{s} ⭐", callback_data=f"star_{s}")] for s in [10,25,50,100,1000]]
    kb.append([InlineKeyboardButton(text="🔙 Назад", callback_data="support")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def news_skip_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Пропустить фото", callback_data="skip_photo")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_news")]
    ])

def news_action_keyboard(news_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👁️ Скрыть", callback_data=f"hide_news_{news_id}")]
    ])

def donation_confirm_keyboard(donation_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_donation_{donation_id}"),
         InlineKeyboardButton(text="❌ Отказать", callback_data=f"reject_donation_{donation_id}")]
    ])

# ========== ОБРАБОТЧИКИ ==========
@dp.message(F.text == "🏠 Главное меню")
async def back_to_main_menu(message: Message):
    if not is_user_blocked(message.from_user.id):
        update_user_activity(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_inline_keyboard(message.from_user.id))

@dp.message(F.text == "🔙 Назад")
async def back_button(message: Message):
    if not is_user_blocked(message.from_user.id):
        update_user_activity(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_inline_keyboard(message.from_user.id))

@dp.message(Command("start"))
async def start(message: Message):
    user_name = message.from_user.first_name or message.from_user.full_name
    username = message.from_user.username
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM blocked_users WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    
    add_user(message.from_user.id, username, user_name)
    
    if is_admin(message.from_user.id):
        conn = sqlite3.connect('ton_bot.db')
        cur = conn.cursor()
        cur.execute("UPDATE admins SET full_name=? WHERE user_id=?", (user_name, message.from_user.id))
        conn.commit()
        conn.close()
    
    await message.answer(
        f"Привет, {user_name}!\nЭто бот канала {CHANNEL_USERNAME}",
        reply_markup=main_menu_buttons
    )
    await message.answer("Выбери действие:", reply_markup=main_inline_keyboard(message.from_user.id))

@dp.message(Command("stop"))
async def stop_bot(message: Message):
    user_id = message.from_user.id
    block_user(user_id)
    await message.answer("👋 До свидания! Если захотите вернуться, просто напишите /start")
    await message.answer("Чат остановлен.", reply_markup=ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True))

@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    if not is_user_blocked(callback.from_user.id):
        update_user_activity(callback.from_user.id)
    await callback.message.edit_text("Выбери действие:", reply_markup=main_inline_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "ask")
async def ask_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_blocked(callback.from_user.id):
        update_user_activity(callback.from_user.id)
    await callback.message.answer("✍️ Напиши вопрос:", reply_markup=main_menu_buttons)
    await state.set_state(AskQuestion.waiting)
    await callback.answer()

@dp.message(AskQuestion.waiting)
async def ask_process(message: Message, state: FSMContext):
    if is_user_blocked(message.from_user.id):
        return
    update_user_activity(message.from_user.id)
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO questions (user_id, username, question) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username or message.from_user.full_name, message.text))
    conn.commit()
    conn.close()
    await message.answer("✅ Вопрос отправлен!", reply_markup=main_inline_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "news")
async def news_start(callback: CallbackQuery, state: FSMContext):
    if not is_user_blocked(callback.from_user.id):
        update_user_activity(callback.from_user.id)
    await callback.message.answer("📝 Напиши текст новости:", reply_markup=main_menu_buttons)
    await state.set_state(SuggestNews.text_wait)
    await callback.answer()

@dp.message(SuggestNews.text_wait)
async def news_text(message: Message, state: FSMContext):
    if is_user_blocked(message.from_user.id):
        return
    if message.text == "🔙 Назад":
        await message.answer("Отменено.", reply_markup=main_inline_keyboard(message.from_user.id))
        await state.clear()
        return
    await state.update_data(text=message.text)
    await message.answer("📸 Отправь фото:", reply_markup=news_skip_keyboard())
    await state.set_state(SuggestNews.photo_wait)

@dp.callback_query(F.data == "skip_photo")
async def skip_photo(callback: CallbackQuery, state: FSMContext):
    if is_user_blocked(callback.from_user.id):
        return
    data = await state.get_data()
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO news_suggestions (user_id, username, text) VALUES (?, ?, ?)",
                (callback.from_user.id, callback.from_user.username or callback.from_user.full_name, data['text']))
    conn.commit()
    conn.close()
    await callback.message.edit_text("✅ Новость отправлена!")
    await callback.message.answer("Главное меню:", reply_markup=main_inline_keyboard(callback.from_user.id))
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "cancel_news")
async def cancel_news(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_inline_keyboard(callback.from_user.id))
    await state.clear()
    await callback.answer()

@dp.message(SuggestNews.photo_wait)
async def news_photo(message: Message, state: FSMContext):
    if is_user_blocked(message.from_user.id):
        return
    data = await state.get_data()
    if not message.photo:
        await message.answer("❌ Отправь фото или нажми «Пропустить фото»")
        return
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO news_suggestions (user_id, username, text, photo_file_id) VALUES (?, ?, ?, ?)",
                (message.from_user.id, message.from_user.username or message.from_user.full_name, data['text'], message.photo[-1].file_id))
    conn.commit()
    conn.close()
    await message.answer("✅ Новость отправлена!", reply_markup=main_inline_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "rate")
async def rate(callback: CallbackQuery):
    if not is_user_blocked(callback.from_user.id):
        update_user_activity(callback.from_user.id)
    usd, rub = await get_ton_price()
    await callback.message.edit_text(f"💰 TON: ${usd:.2f} / {rub:.2f} ₽")
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    if not is_user_blocked(callback.from_user.id):
        update_user_activity(callback.from_user.id)
    await callback.message.edit_text("Способ поддержки:", reply_markup=support_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "stars_donate")
async def stars_donate(callback: CallbackQuery):
    await callback.message.edit_text("Выбери сумму:", reply_markup=stars_amount_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("star_"))
async def process_stars(callback: CallbackQuery):
    amount = int(callback.data.split("_")[1])
    await bot.send_invoice(callback.from_user.id, title="Поддержка TON", description=f"{amount} ⭐", payload=f"donate_{amount}", currency="XTR", prices=[types.LabeledPrice(label="Звёзды", amount=amount)], provider_token="")
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    amount = message.successful_payment.total_amount
    channel = get_setting('channel_id')
    if channel:
        await bot.send_message(channel, f"Спасибо @{message.from_user.username or message.from_user.full_name} за {amount} ⭐!")
    await message.answer(f"✨ Спасибо за {amount} ⭐!")

@dp.callback_query(F.data == "crypto_donate")
async def crypto_donate(callback: CallbackQuery):
    wallet = get_setting('wallet')
    await callback.message.edit_text(f"🪙 Кошелёк TON:\n`{wallet}`\n\nПереведи сумму и нажми «Проверить»", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверить", callback_data="check_crypto")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="support")]
    ]))
    await callback.answer()

@dp.callback_query(F.data == "check_crypto")
async def check_crypto(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💎 Введите количество TON, которое вы отправили:")
    await state.set_state(CheckDonation.amount_wait)
    await callback.answer()

@dp.message(CheckDonation.amount_wait)
async def crypto_amount(message: Message, state: FSMContext):
    if is_user_blocked(message.from_user.id):
        return
    try:
        amount = float(message.text.replace(',', '.'))
    except:
        await message.answer("❌ Введите число (например: 1.5 или 10)")
        return
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("INSERT INTO donations_crypto (user_id, username, amount) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username or message.from_user.full_name, amount))
    donation_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(OWNER_ID, f"💸 Новое пожертвование от @{message.from_user.username or message.from_user.full_name}\nСумма: {amount} TON", reply_markup=donation_confirm_keyboard(donation_id))
    except:
        pass
    
    await message.answer("✅ Заявка отправлена на проверку!", reply_markup=main_inline_keyboard(message.from_user.id))
    await state.clear()

# ========== АДМИНКА ==========
@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.message.edit_text("⚙️ Админ-панель:", reply_markup=admin_inline_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "admin_questions")
async def admin_questions(callback: CallbackQuery):
    rights = get_admin_rights(callback.from_user.id)
    if not rights.get('questions') and callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT id, username, question FROM questions WHERE answered=0")
    qs = cur.fetchall()
    conn.close()
    if not qs:
        await callback.message.edit_text("Нет вопросов", reply_markup=admin_inline_keyboard(callback.from_user.id))
        return
    for q in qs:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✏️ Ответить", callback_data=f"reply_{q[0]}")]])
        await callback.message.answer(f"❓ @{q[1]}\n{q[2]}", reply_markup=kb)
    await callback.answer()

@dp.callback_query(F.data.startswith("reply_"))
async def reply_start(callback: CallbackQuery, state: FSMContext):
    q_id = int(callback.data.split("_")[1])
    await state.update_data(q_id=q_id)
    await callback.message.answer("✍️ Введи ответ:")
    await state.set_state(ReplyQuestion.answer_wait)
    await callback.answer()

@dp.message(ReplyQuestion.answer_wait)
async def reply_process(message: Message, state: FSMContext):
    data = await state.get_data()
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, question FROM questions WHERE id=?", (data['q_id'],))
    row = cur.fetchone()
    if row:
        user_id, question = row
        answer_text = f"📩 Пришел ответ на вопрос \"{question}\"\n\n{message.text}"
        await bot.send_message(user_id, answer_text)
        cur.execute("UPDATE questions SET answered=1, answer=? WHERE id=?", (message.text, data['q_id']))
        conn.commit()
    conn.close()
    await message.answer("✅ Ответ отправлен", reply_markup=main_inline_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_news")
async def admin_news(callback: CallbackQuery):
    rights = get_admin_rights(callback.from_user.id)
    if not rights.get('news') and callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT id, username, text, photo_file_id FROM news_suggestions")
    all_news = cur.fetchall()
    conn.close()
    
    visible_news = []
    for n in all_news:
        if not is_news_hidden(callback.from_user.id, n[0]):
            visible_news.append(n)
    
    if not visible_news:
        await callback.message.edit_text("Нет новостей", reply_markup=admin_inline_keyboard(callback.from_user.id))
        return
    
    for n in visible_news:
        if n[3]:
            await bot.send_photo(callback.from_user.id, n[3], caption=f"📰 @{n[1]}\n{n[2]}", reply_markup=news_action_keyboard(n[0]))
        else:
            await callback.message.answer(f"📰 @{n[1]}\n{n[2]}", reply_markup=news_action_keyboard(n[0]))
    await callback.answer()

@dp.callback_query(F.data.startswith("hide_news_"))
async def hide_news_callback(callback: CallbackQuery):
    news_id = int(callback.data.split("_")[2])
    hide_news(callback.from_user.id, news_id)
    await callback.message.delete()
    await callback.answer("Новость скрыта", show_alert=True)

@dp.callback_query(F.data == "admin_donations")
async def admin_donations(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT id, username, amount FROM donations_crypto WHERE status='pending'")
    donations = cur.fetchall()
    conn.close()
    
    if not donations:
        await callback.message.edit_text("Нет пожертвований", reply_markup=admin_inline_keyboard(callback.from_user.id))
        return
    
    for d in donations:
        await callback.message.answer(f"💸 @{d[1]} — {d[2]} TON", reply_markup=donation_confirm_keyboard(d[0]))
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_donation_"))
async def confirm_donation(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    
    donation_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, amount FROM donations_crypto WHERE id=?", (donation_id,))
    row = cur.fetchone()
    if row:
        user_id, username, amount = row
        cur.execute("UPDATE donations_crypto SET status='confirmed' WHERE id=?", (donation_id,))
        conn.commit()
        channel = get_setting('channel_id')
        if channel:
            await bot.send_message(channel, f"Спасибо @{username} за {amount} TON! ❤️")
        await callback.message.edit_text(f"✅ Подтверждено: @{username} — {amount} TON")
        await bot.send_message(user_id, f"✅ Ваше пожертвование {amount} TON подтверждено! Спасибо за поддержку!")
    conn.close()
    await callback.answer()

@dp.callback_query(F.data.startswith("reject_donation_"))
async def reject_donation(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    
    donation_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id, username, amount FROM donations_crypto WHERE id=?", (donation_id,))
    row = cur.fetchone()
    if row:
        user_id, username, amount = row
        cur.execute("DELETE FROM donations_crypto WHERE id=?", (donation_id,))
        conn.commit()
        await callback.message.edit_text(f"❌ Отказано: @{username} — {amount} TON")
        await bot.send_message(user_id, "❌ Перевод не был получен. Если есть вопросы, задайте их в разделе «Вопрос».")
    conn.close()
    await callback.answer()

@dp.callback_query(F.data == "admin_notify")
async def admin_notify(callback: CallbackQuery, state: FSMContext):
    rights = get_admin_rights(callback.from_user.id)
    if not rights.get('notify') and callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    await callback.message.edit_text("📢 Напиши сообщение для рассылки:")
    await state.set_state(NotifyState.waiting_for_message)
    await callback.answer()

@dp.message(NotifyState.waiting_for_message)
async def process_notify(message: Message, state: FSMContext):
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM blocked_users)")
    users = cur.fetchall()
    conn.close()
    
    success = 0
    for user in users:
        try:
            await bot.send_message(user[0], f"📢 Оповещение\n\n{message.text}")
            success += 1
            await asyncio.sleep(0.05)
        except:
            pass
    
    await message.answer(f"✅ Отправлено: {success} пользователям", reply_markup=admin_inline_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):
    rights = get_admin_rights(callback.from_user.id)
    if not rights.get('users') and callback.from_user.id != OWNER_ID:
        await callback.answer("Нет прав")
        return
    
    total = get_active_users_count()
    last = get_last_active_users(10)
    
    text = f"👥 **Всего активных пользователей:** {total}\n\n"
    text += f"📋 **Последние 10 активных:**\n"
    
    for i, u in enumerate(last, 1):
        user_id, username, full_name, last_seen = u
        if username and username != "None" and username.strip():
            display = f"@{username}"
        else:
            name = full_name if full_name else str(user_id)
            display = f"{name} (нет username)"
        
        if last_seen:
            try:
                date_obj = datetime.strptime(last_seen, "%Y-%m-%d %H:%M:%S")
                date_str = date_obj.strftime("%d.%m.%Y %H:%M")
            except:
                date_str = last_seen[:16] if len(last_seen) >= 16 else last_seen
        else:
            date_str = "неизвестно"
        
        text += f"{i}. {display} — {date_str}\n"
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=admin_inline_keyboard(callback.from_user.id))
    await callback.answer()

@dp.callback_query(F.data == "admin_list_menu")
async def admin_list_menu(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        rights = get_admin_rights(callback.from_user.id)
        if not rights.get('admins'):
            await callback.answer("Нет прав")
            return
    admins = get_all_admins()
    await callback.message.edit_text("👥 Администраторы:", reply_markup=admin_list_keyboard(admins))
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_edit_"))
async def admin_edit(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        rights = get_admin_rights(callback.from_user.id)
        if not rights.get('admins'):
            await callback.answer("Нет прав")
            return
    
    user_id = int(callback.data.split("_")[2])
    rights = get_admin_rights(user_id)
    
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT username, full_name FROM admins WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    
    name = row[1] if row and row[1] else f"@{row[0]}" if row and row[0] else str(user_id)
    await callback.message.edit_text(f"Редактирование прав: {name}", reply_markup=admin_edit_keyboard(user_id, rights))
    await callback.answer()

@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_right(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец")
        return
    
    parts = callback.data.split("_")
    if len(parts) != 4:
        await callback.answer("Ошибка")
        return
    _, uid, right, val = parts
    user_id = int(uid)
    new_value = int(val)
    
    # Обновляем права в базе данных
    set_admin_rights(user_id, right, new_value)
    
    # Получаем обновлённые права
    rights = get_admin_rights(user_id)
    
    # Получаем имя администратора
    conn = sqlite3.connect('ton_bot.db')
    cur = conn.cursor()
    cur.execute("SELECT username, full_name FROM admins WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    
    name = row[1] if row and row[1] else f"@{row[0]}" if row and row[0] else str(user_id)
    
    # Создаём обновлённую клавиатуру
    new_keyboard = admin_edit_keyboard(user_id, rights)
    
    # Редактируем текущее сообщение (меняем только клавиатуру)
    await callback.message.edit_text(f"Редактирование прав: {name}", reply_markup=new_keyboard)
    await callback.answer("✅ Изменено")

@dp.callback_query(F.data.startswith("remove_"))
async def remove_admin_cmd(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец")
        return
    uid = int(callback.data.split("_")[1])
    remove_admin(uid)
    await callback.answer("✅ Администратор удалён")
    await admin_list_menu(callback)

@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

@dp.callback_query(F.data == "set_channel")
async def set_channel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец")
        return
    await callback.message.edit_text("Введи @username канала (бот должен быть админом):")
    await state.set_state(SetChannel.channel_wait)
    await callback.answer()

@dp.message(SetChannel.channel_wait)
async def save_channel(message: Message, state: FSMContext):
    channel = message.text.strip()
    try:
        await bot.get_chat(channel)
        set_setting('channel_id', channel)
        await message.answer(f"✅ Канал {channel} сохранён!", reply_markup=main_inline_keyboard(message.from_user.id))
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Ошибка: канал не найден. {e}")

@dp.callback_query(F.data == "set_wallet")
async def set_wallet(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец")
        return
    await callback.message.edit_text("Введи TON кошелёк для приёма пожертвований:")
    await state.set_state(SetWalletState.wallet_wait)
    await callback.answer()

@dp.message(SetWalletState.wallet_wait)
async def save_wallet(message: Message, state: FSMContext):
    set_setting('wallet', message.text.strip())
    await message.answer("✅ Кошелёк обновлён!", reply_markup=main_inline_keyboard(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data == "add_admin")
async def add_admin_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец")
        return
    await callback.message.edit_text("Введи @username пользователя, которого хочешь сделать администратором:\n\n⚠️ Пользователь должен хотя бы раз написать /start боту")
    await state.set_state(AddAdminState.username_wait)
    await callback.answer()

@dp.message(AddAdminState.username_wait)
async def add_admin_process(message: Message, state: FSMContext):
    username = message.text.strip().lstrip('@')
    user_id = user_exists_in_db(username)
    
    if user_id:
        conn = sqlite3.connect('ton_bot.db')
        cur = conn.cursor()
        cur.execute("SELECT full_name FROM users WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        conn.close()
        add_admin(user_id, username, row[0] if row else username)
        await message.answer(f"✅ @{username} теперь администратор!\nНазначьте права через «Администраторы» в админ-меню.", reply_markup=main_inline_keyboard(message.from_user.id))
        await bot.send_message(user_id, "🎉 Вы стали администратором бота! Напишите /start, чтобы увидеть админ-меню.")
    else:
        await message.answer(f"❌ @{username} не найден.\nПользователь должен написать боту /start, после чего повторите попытку.")
    await state.clear()

async def main():
    print("✅ Бот запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
