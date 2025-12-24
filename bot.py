import asyncio
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from typing import Optional
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import os

TOKEN = os.getenv("7952414869:AAFMBkAHgcTcFaEjb8EabLSBZkEWj5h2Vjw")
ADMIN_ID = int(os.getenv("72213910"))

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
DB = "bot.db"


async def delete_message_safely(chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass


def format_time_left(end_date: str) -> str:
    """
    Принимает строку ISO с датой окончания, возвращает строку вида 'X дн. Y ч.'
    """
    try:
        end_dt = datetime.fromisoformat(end_date)
        delta = end_dt - datetime.now()
        if delta.total_seconds() <= 0:
            return "срок истёк"
        days = delta.days
        hours = delta.seconds // 3600
        return f"{days} дн. {hours} ч."
    except:
        return "ошибка даты"


async def delete_later(message: types.Message, delay: int = 2):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        print(f"Ошибка: {e}")



# ================= FSM =================
class AdminStates(StatesGroup):
    add_key_name = State()
    add_key_config = State()
    set_days = State()


# ================= KEYBOARDS =================
def user_main_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")]
    ])

@dp.message(lambda m: m.text == "🔑 Мои ключи" and m.from_user.id != ADMIN_ID)
async def user_my_keys(message: types.Message):
    uid = message.from_user.id

    async with aiosqlite.connect(DB) as db:
        keys = await (await db.execute(
            "SELECT id, name, end_date FROM vless WHERE owner=?", (uid,)
        )).fetchall()

    if not keys:
        await message.answer("🔒 У вас пока нет ключей", reply_markup=user_reply_kb())
        return

    inline_keyboard = []
    for kid, name, end in keys:
        days_text = f"({format_time_left(end)})" if end else "(нет срока)"
        inline_keyboard.append([InlineKeyboardButton(
            text=f"🔑 {name} {days_text}",
            callback_data=f"showkey_{kid}_user"
        )])

    await message.answer(
        "🔑 Ваши ключи:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    )



def admin_main_inline_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="users")],
        [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
        [InlineKeyboardButton(text="➕ Добавить ключ", callback_data=f"addkey_{ADMIN_ID}")],
    ])



def user_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Мои ключи", callback_data="my_keys")],
    ])


def user_admin_kb(uid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить ключ", callback_data=f"addkey_{uid}")],
        [InlineKeyboardButton(text="🔑 Ключи пользователя", callback_data=f"userkeys_{uid}")],
        [InlineKeyboardButton(text="❌ Удалить пользователя", callback_data=f"deluser_{uid}")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="users")]
    ])
def user_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔑 Мои ключи")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def add_key_choice_kb(uid):
    back_callback = "admin_back" if uid == ADMIN_ID else f"user_{uid}"

    keyboard = [
        [InlineKeyboardButton(text="➕ Создать новый", callback_data=f"create_new_{uid}")]
    ]

    # Показываем кнопку "использовать существующий" только для обычных пользователей
    if uid != ADMIN_ID:
        keyboard.append([InlineKeyboardButton(text="🔁 Использовать существующий", callback_data=f"choose_existing_{uid}")])

    keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)



def main_reply_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Меню")]],
        resize_keyboard=True
    )

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            start_date TEXT,
            end_date TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS vless (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            config TEXT,
            owner INTEGER,
            start_date TEXT,
            end_date TEXT,
            notified_3days INTEGER DEFAULT 0,
            notified_1day INTEGER DEFAULT 0
        )
        """)
        await db.commit()

@dp.callback_query(lambda c: c.data == "admin_back")
async def admin_back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🛠 <b>Меню администратора</b>",
        reply_markup=admin_main_inline_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ================= START =================
@dp.message(Command("start"))
async def start(message: types.Message):
    uid = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # ---------- регистрация пользователя ----------
    async with aiosqlite.connect(DB) as db:
        user = await (await db.execute(
            "SELECT tg_id FROM users WHERE tg_id=?", (uid,)
        )).fetchone()

        if not user:
            await db.execute(
                "INSERT INTO users (tg_id) VALUES (?)", (uid,)
            )
            await db.commit()
            new_user = True
        else:
            new_user = False

    # ---------- если новый пользователь — уведомляем админа ----------
    if new_user:
        display_name = f"@{username}" if username else first_name

        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="⚙️ Управлять пользователем",
                callback_data=f"user_{uid}"
            )]
        ])

        await bot.send_message(
            ADMIN_ID,
            f"🆕 Новый пользователь: <a href='tg://user?id={uid}'>{display_name}</a>",
            reply_markup=admin_kb,
            parse_mode="HTML"
        )

    # ---------- ОБЩЕЕ СООБЩЕНИЕ + КНОПКА МЕНЮ ----------
    await message.answer(
        "Добро пожаловать 👋\nНажмите «📋 Меню» для управления",
        reply_markup=main_reply_kb()
    )


@dp.message(lambda m: m.text == "📋 Меню" and m.from_user.id == ADMIN_ID)
async def admin_menu(message: types.Message):
    try:
        await message.delete()  # удаляем сообщение с ReplyKeyboard
    except Exception as e:
        print(f"Ошибка: {e}")

    await message.answer(
        "🛠 <b>Меню администратора</b>",
        reply_markup=admin_main_inline_kb(),
        parse_mode="HTML"
    )
@dp.callback_query(lambda c: c.data == "user_menu_back")
async def user_menu_back(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "👤 <b>Меню пользователя</b>",
        reply_markup=user_main_inline_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


# ================= ADMIN =================
@dp.message(Command("admin"))
async def admin(message: types.Message):
    if message.from_user.id == ADMIN_ID:

        await message.answer(
            "Выберите действие или воспользуйтесь командой /admin:",
            reply_markup=admin_main_inline_kb()
        )


@dp.message(lambda m: m.text == "👥 Пользователи" and m.from_user.id == ADMIN_ID)
async def admin_users_reply(message: types.Message):
    async with aiosqlite.connect(DB) as db:
        users = await (await db.execute("SELECT tg_id FROM users")).fetchall()

    kb = []
    text = "👥 <b>Пользователи:</b>\n\n"


    for (uid,) in users:
        try:
            user = await bot.get_chat(uid)
            name = f"@{user.username}" if user.username else user.first_name
        except:
            name = f"ID {uid}"

        text += f"👤 <a href='tg://user?id={uid}'>{name}</a>\n"
        kb.append([
            InlineKeyboardButton(
                text=f"⚙️ {name}",
                callback_data=f"user_{uid}"
            )
        ])

    kb.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="admin_back")
    ])

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )


@dp.callback_query(lambda c: c.data.startswith("create_new_"))
async def create_new_key(callback: types.CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[2])
    await state.update_data(uid=uid)
    msg = await callback.message.answer("Введите название нового ключа:")
    await remember_message(state, msg)
    await state.set_state(AdminStates.add_key_name)


@dp.callback_query(lambda c: c.data.startswith("choose_existing_"))
async def choose_existing_key(callback: types.CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[2])  # кому добавляем

    async with aiosqlite.connect(DB) as db:
        keys = await (await db.execute(
            "SELECT id, name FROM vless WHERE owner=?",
            (ADMIN_ID,)
        )).fetchall()

    if not keys:
        await callback.answer("❌ У вас нет существующих ключей", show_alert=True)
        return

    kb = []
    for kid, name in keys:
        kb.append([
            InlineKeyboardButton(
                text=name,
                callback_data=f"use_existing_{kid}_{uid}"
            )
        ])

    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data=f"addkey_{uid}")])

    await callback.message.edit_text(
        "🔁 Выберите существующий ключ:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("use_existing_"))
async def use_existing_key(callback: types.CallbackQuery, state: FSMContext):
    _, _, kid, uid = callback.data.split("_")
    kid = int(kid)
    uid = int(uid)

    async with aiosqlite.connect(DB) as db:
        row = await (await db.execute(
            "SELECT name, config FROM vless WHERE id=? AND owner=?",
            (kid, ADMIN_ID)
        )).fetchone()

    if not row:
        await callback.answer("❌ Ключ не найден", show_alert=True)
        return

    name, config = row

    await state.update_data(
        uid=uid,
        name=name,
        config=config
    )

    await callback.message.edit_text(
        "⏳ Введите количество дней подписки:"
    )
    await state.set_state(AdminStates.set_days)
    await callback.answer()


# ================= USERS LIST =================
@dp.callback_query(lambda c: c.data == "users")
async def users_list(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        users = await (await db.execute("SELECT tg_id FROM users")).fetchall()

    kb = []
    text = "👥 <b>Пользователи:</b>\n\n"
    for (uid,) in users:
        try:
            u = await bot.get_chat(uid)
            name = f"@{u.username}" if u.username else u.first_name
        except:
            name = f"ID {uid}"
        text += f"👤 <a href='tg://user?id={uid}'>{name}</a>\n"
        kb.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"user_{uid}")])

    kb.append([
        InlineKeyboardButton(text="⬅ Назад", callback_data="admin_back")
    ])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )


# ================= USER MENU =================
@dp.callback_query(lambda c: c.data.startswith("user_"))
async def user_menu(callback: types.CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[1])

    # Получаем данные для админа
    text = f"⚙️ Управление пользователем\nID: {uid}"
    keyboard = user_admin_kb(uid)

    await callback.message.edit_text(
        text,
        reply_markup=keyboard
    )
    await callback.answer()

# ================= USER MY KEYS =================
@dp.callback_query(lambda c: c.data == "my_keys")
async def my_keys(callback: types.CallbackQuery):
    uid = callback.from_user.id
    is_admin = uid == ADMIN_ID

    async with aiosqlite.connect(DB) as db:
        keys = await (await db.execute(
            "SELECT id, name, end_date FROM vless WHERE owner=?", (uid,)
        )).fetchall()

    inline_keyboard = []

    if keys:
        for kid, name, end in keys:
            days_text = f"({format_time_left(end)})" if end else "(нет срока)"
            button_text = f"🔑 {name} {days_text}"

            if is_admin:
                # Админ может удалять
                inline_keyboard.append([
                    InlineKeyboardButton(text=button_text, callback_data=f"showkey_{kid}"),
                    InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delkey_{kid}")
                ])
            else:
                inline_keyboard.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"showkey_{kid}_user"
                    )
                ])


    else:
        inline_keyboard.append([InlineKeyboardButton(text="🔒 Ключей нет", callback_data="noop")])

    # Кнопка добавления ключа только для админа
    if is_admin:
        inline_keyboard.insert(0, [InlineKeyboardButton(text="➕ Добавить ключ", callback_data=f"addkey_{uid}")])

    # Кнопка "Назад"
    back_callback = "admin_back" if is_admin else "user_menu_back"

    inline_keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])

    await callback.message.edit_text(
        "🔑 Ваши ключи:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    )
    await callback.answer()

# ================= ADD KEY =================
@dp.callback_query(lambda c: c.data.startswith("addkey_"))
async def add_key(callback: types.CallbackQuery, state: FSMContext):
    uid = int(callback.data.split("_")[1])

    # Отправляем сообщение и сохраняем его для последующего удаления
    msg = await callback.message.edit_text(
        "➕ Как вы хотите добавить ключ?",
        reply_markup=add_key_choice_kb(uid)
    )
    await remember_message(state, msg)  # сохраняем для удаления

    await callback.answer()


@dp.message(AdminStates.add_key_name)
async def add_key_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())

    await remember_message(state, message)

    prompt = await message.answer("Вставьте конфигурацию ключа:")
    await remember_message(state, prompt)

    await state.set_state(AdminStates.add_key_config)


@dp.message(AdminStates.add_key_config)
async def add_key_config(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("uid")
    key_name = data.get("name")
    config_text = message.text.strip()
    await state.update_data(config=config_text)


    # ✅ если админ добавляет ключ СЕБЕ
    if uid == ADMIN_ID:
        now = datetime.now()

        async with aiosqlite.connect(DB) as db:
            await db.execute(
                """
                INSERT INTO vless (owner, name, config, start_date, end_date)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (uid, key_name, config_text, now.isoformat())
            )
            await db.commit()
        await remember_message(state, message)

        confirm = await message.answer("✅ Ключ добавлен")
        await remember_message(state, confirm)
        data = await state.get_data()
        msg_ids = data.get("cleanup_messages", [])
        for mid in msg_ids:
            try:
                await bot.delete_message(message.chat.id, mid)
            except Exception as e:
                print(f"Ошибка: {e}")

        await state.clear()
        return

    # 👤 если пользователю
    await remember_message(state, message)
    prompt = await message.answer("⏳ Введите количество дней подписки:")
    await remember_message(state, prompt)
    await state.set_state(AdminStates.set_days)



# ================= SET DAYS =================
@dp.message(AdminStates.set_days)
async def set_days(message: types.Message, state: FSMContext):


    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except ValueError:
        warn = await message.answer("❌ Введите корректное число дней")
        asyncio.create_task(delete_later(warn))
        return

    data = await state.get_data()
    extend_key_id = data.get("extend_key_id")
    key_name = data.get("name")
    key_config = data.get("config")
    uid = data.get("uid")

    now = datetime.now()
    new_end = now + timedelta(days=days)  # ✅ ВСЕГДА ОТ СЕЙЧАС

    async with aiosqlite.connect(DB) as db:

        # 🔁 ОБНОВЛЕНИЕ СУЩЕСТВУЮЩЕГО КЛЮЧА
        if extend_key_id:
            await db.execute(
                "UPDATE vless SET end_date=? WHERE id=?",
                (new_end.isoformat(), extend_key_id)
            )
            await db.commit()

            # уведомление пользователю
            async with aiosqlite.connect(DB) as db2:
                row = await (await db2.execute(
                    "SELECT owner FROM vless WHERE id=?",
                    (extend_key_id,)
                )).fetchone()

            if row:
                await bot.send_message(
                    row[0],
                    f"🔑 Срок действия ключа обновлён\n"
                    f"⏳ Активен на {days} дней"
                )

            ok = await message.answer("✅ Срок ключа обновлён")
            await remember_message(state, ok)

        # ➕ СОЗДАНИЕ НОВОГО КЛЮЧА
        else:
            await db.execute(
                """
                INSERT INTO vless (owner, name, config, start_date, end_date)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    uid,
                    key_name,
                    key_config,
                    now.isoformat(),
                    new_end.isoformat()
                )
            )
            await db.commit()

            await bot.send_message(
                uid,
                f"🔑 Ключ <b>{key_name}</b>\n"
                f"⏳ Активен на {days} дней",
                parse_mode="HTML"
            )

            ok =await message.answer("✅ Ключ успешно добавлен")
            await remember_message(state, ok)

    data = await state.get_data()
    msg_ids = data.get("cleanup_messages", [])

    for mid in msg_ids:
        try:
            await bot.delete_message(message.chat.id, mid)
        except Exception as e:
            print(f"Ошибка: {e}")

    # удаляем сообщение с числом дней
    try:
        await message.delete()
    except:
        pass

    await state.update_data(extend_key_id=None)
    await state.clear()


@dp.message(
    lambda m: (
        m.from_user.id != ADMIN_ID
        and m.text not in ["🔑 Мои ключи", "📋 Меню"]
    )
)
async def unknown_message(message: types.Message):
    await message.answer(
        "🤖 Я не умею отвечать на текстовые сообщения.\n"
        "Вы можете просмотреть свои ключи по кнопке ниже ⬇️",
        reply_markup=user_reply_kb()
    )

# ================= EXTEND KEYS =================
@dp.callback_query(lambda c: c.data.startswith("extendkey_"))
async def extend_days_input(callback: types.CallbackQuery, state: FSMContext):
    kid = int(callback.data.split("_")[1])
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return

    async with aiosqlite.connect(DB) as db:
        row = await (await db.execute(
            "SELECT owner FROM vless WHERE id=?", (kid,)
        )).fetchone()

    if not row:
        await callback.message.answer("❌ Ключ не найден")
        return

    uid = row[0]

    await state.update_data(
        extend_key_id=kid,
        uid=uid
    )

    msg = await callback.message.answer(
        "Введите количество дней для продления подписки:"
    )
    await remember_message(state, msg)

    await state.set_state(AdminStates.set_days)


async def build_user_keys_kb(uid, is_admin=False):
    async with aiosqlite.connect(DB) as db:
        keys = await (await db.execute(
            "SELECT id, name, end_date FROM vless WHERE owner=?",
            (uid,)
        )).fetchall()

    if not keys:
        return None

    inline_keyboard = []

    for kid, name, end in keys:
        if end:
            try:
                days_left = max(
                    (datetime.fromisoformat(end) - datetime.now()).days, 0
                )
                button_text = f"🔑 {name} ({days_left} дн.)"
            except:
                button_text = f"🔑 {name} (ошибка даты)"
        else:
            button_text = f"🔑 {name} (нет срока)"

        if is_admin:
            inline_keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"showkey_{kid}_admin"
                ),
                InlineKeyboardButton(
                    text="🗑",
                    callback_data=f"delkey_{kid}"
                )
            ])
        else:
            inline_keyboard.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"showkey_{kid}_user"
                )
            ])

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


# ================= USER KEYS =================
@dp.callback_query(lambda c: c.data.startswith("userkeys_"))
async def user_keys(callback: types.CallbackQuery):
    # Получаем UID пользователя, чьи ключи просматривает админ
    uid = int(callback.data.split("_")[1])
    is_admin = callback.from_user.id == ADMIN_ID

    async with aiosqlite.connect(DB) as db:
        user_keys_list = await (await db.execute(
            "SELECT id, name, end_date FROM vless WHERE owner=?", (uid,)
        )).fetchall()

    inline_keyboard = []

    if user_keys_list:
        for kid, name, end in user_keys_list:
            day_text = f"({format_time_left(end)})" if end else "(нет срока)"
            if is_admin:
                # Админ может смотреть, продлить и удалить
                inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"🔑 {name} {day_text}",
                        callback_data=f"showkey_{kid}_admin_{uid}"  # uid владельца
                    ),
                    InlineKeyboardButton(
                        text="➕ Продлить",
                        callback_data=f"extendkey_{kid}"
                    ),
                    InlineKeyboardButton(
                        text="🗑 Удалить",
                        callback_data=f"delkey_{kid}"
                    )
                ])
            else:
                # Для обычного пользователя
                inline_keyboard.append([
                    InlineKeyboardButton(
                        text=f"🔑 {name} {day_text}",
                        callback_data=f"showkey_{kid}_user"
                    )
                ])
    else:
        inline_keyboard.append([InlineKeyboardButton(text="🔒 Ключей нет", callback_data="noop")])

    # Кнопка "Назад"
    back_callback = f"user_{uid}" if is_admin else "my_keys"
    inline_keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])

    await callback.message.edit_text(
        f"🔑 <b>Ключи пользователя {uid}:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

# ================= SHOW KEY =================
@dp.callback_query(lambda c: c.data.startswith("showkey_"))
async def show_key(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    kid = int(parts[1])
    source = parts[2] if len(parts) > 2 else "user"
    owner_uid = int(parts[3]) if len(parts) > 3 else None  # UID владельца для админа

    async with aiosqlite.connect(DB) as db:
        row = await (await db.execute(
            "SELECT name, config, end_date FROM vless WHERE id=?",
            (kid,)
        )).fetchone()

    if not row:
        await callback.answer("❌ Ключ не найден", show_alert=True)
        return

    name, config, end_date = row
    days_text = format_time_left(end_date) if end_date else "срок не установлен"

    # Кнопка "Назад" корректно возвращает к ключам
    if source == "admin" and owner_uid is not None:
        back_callback = f"userkeys_{owner_uid}"
    else:
        back_callback = "my_keys"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)]
    ])

    await callback.message.edit_text(
        f"🔑 <b>{name}</b>\n"
        f"⏳ {days_text}\n\n"
        f"<code>{config}</code>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ================= DELETE KEY =================
@dp.callback_query(lambda c: c.data.startswith("deluser_"))
async def delete_user(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])

    # Отправляем уведомление пользователю перед удалением
    try:
        await bot.send_message(
            uid,
            "⚠️ Вы были удалены администратором. Все ваши ключи удалены."
        )
    except Exception as e:
        print(f"Ошибка: {e}")

    # Удаляем пользователя и его ключи из БД
    async with aiosqlite.connect(DB) as db:
        await db.execute("DELETE FROM vless WHERE owner=?", (uid,))
        await db.execute("DELETE FROM users WHERE tg_id=?", (uid,))
        await db.commit()

    # Обновляем список пользователей в меню
    async with aiosqlite.connect(DB) as db:
        users = await (await db.execute("SELECT tg_id FROM users")).fetchall()

    kb = []
    text = "👥 <b>Пользователи:</b>\n\n"
    for (user_id,) in users:
        try:
            user = await bot.get_chat(user_id)
            name = f"@{user.username}" if user.username else user.first_name
        except:
            name = f"ID {user_id}"
        text += f"👤 <a href='tg://user?id={user_id}'>{name}</a>\n"
        kb.append([InlineKeyboardButton(text=f"⚙️ {name}", callback_data=f"user_{user_id}")])

    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="admin_back")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
        parse_mode="HTML"
    )

    await callback.answer()


async def remember_message(state: FSMContext, message: types.Message):
    data = await state.get_data()
    msgs = data.get("cleanup_messages", [])
    msgs.append(message.message_id)
    await state.update_data(cleanup_messages=msgs)


@dp.callback_query(lambda c: c.data.startswith("delkey_"))
async def delete_key(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    kid = int(callback.data.split("_")[1])

    async with aiosqlite.connect(DB) as db:
        row = await (await db.execute("SELECT owner FROM vless WHERE id=?", (kid,))).fetchone()
        if not row:
            await callback.answer("❌ Ключ не найден", show_alert=True)
            return
        owner_id = row[0]

        await db.execute("DELETE FROM vless WHERE id=?", (kid,))
        await db.commit()

    await callback.answer("🗑 Ключ удалён", show_alert=True)

    # Обновляем меню ключей
    async with aiosqlite.connect(DB) as db:
        keys = await (await db.execute("SELECT id, name, end_date FROM vless WHERE owner=?", (owner_id,))).fetchall()

    inline_keyboard = []
    for kid, name, end in keys:
        day_text = f"({format_time_left(end)})" if end else "(нет срока)"
        if owner_id == ADMIN_ID:
            # Для админа: просмотр, продлить, удалить
            inline_keyboard.append([
                InlineKeyboardButton(text=f"🔑 {name} {day_text}", callback_data=f"showkey_{kid}"),
                InlineKeyboardButton(text="➕ Продлить", callback_data=f"extendkey_{kid}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delkey_{kid}")
            ])
        else:
            # Для пользователя
            inline_keyboard.append([
                InlineKeyboardButton(text=f"🔑 {name} {day_text}", callback_data=f"showkey_{kid}")
            ])

    if owner_id == ADMIN_ID:
        back_callback = "admin_back"
        text = "🔑 Ваши ключи:"
    else:
        back_callback = f"user_{owner_id}"
        text = f"🔑 <b>Ключи пользователя {owner_id}:</b>"

    inline_keyboard.append([InlineKeyboardButton(text="⬅ Назад", callback_data=back_callback)])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=inline_keyboard),
        parse_mode="HTML"
    )


@dp.message(lambda m: m.text == "📋 Меню" and m.from_user.id != ADMIN_ID)
async def user_menu_reply(message: types.Message):
    await message.delete()  # Удаляем ReplyKeyboard
    await message.answer(
        "👤 <b>Меню пользователя</b>",
        reply_markup=user_main_inline_kb(),
        parse_mode="HTML"
    )


# ================= SUBSCRIPTION WATCHER =================
async def watcher():
    while True:
        async with aiosqlite.connect(DB) as db:
            keys = await (await db.execute(
                "SELECT id, owner, end_date, notified_3days, notified_1day FROM vless WHERE end_date IS NOT NULL"
            )).fetchall()

            for kid, uid, end, notified_3, notified_1 in keys:
                end_dt = datetime.fromisoformat(end)
                delta_days = (end_dt - datetime.now()).days

                # Уведомление за 3 дня
                if delta_days == 3 and not notified_3:
                    await bot.send_message(uid, f"🔔 Ключ {kid} заканчивает действие через 3 дня")
                    await db.execute("UPDATE vless SET notified_3days = 1 WHERE id=?", (kid,))

                # Уведомление за 1 день
                elif delta_days == 1 and not notified_1:
                    await bot.send_message(uid, f"🔔 Ключ {kid} заканчивает действие завтра")
                    await db.execute("UPDATE vless SET notified_1day = 1 WHERE id=?", (kid,))

                # Ключ истёк
                elif delta_days < 0:
                    await db.execute("DELETE FROM vless WHERE id=?", (kid,))
                    await bot.send_message(uid, f"⛔ Ключ {kid} истёк и удалён")

            await db.commit()

        await asyncio.sleep(3600)  # проверка каждый час



# ================= MAIN =================
async def main():
    await init_db()
    asyncio.create_task(watcher())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
