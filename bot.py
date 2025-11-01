# bot.py — УМНЫЙ БОТ-НАПОМИНАЛКА (aiogram 3.x) — УВЕДОМЛЕНИЯ 100%!
import os
import json
import pytz
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env!")

TIMEZONE = 'Europe/Moscow'
tz = pytz.timezone(TIMEZONE)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone=TIMEZONE)

REMINDERS_FILE = 'reminders.json'

# === ЗАГРУЗКА ===
try:
    with open(REMINDERS_FILE, 'r', encoding='utf-8') as f:
        reminders = json.load(f)
except:
    reminders = {}

def save_reminders():
    with open(REMINDERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reminders, f, indent=2, ensure_ascii=False)

# === FSM ===
class ReminderStates(StatesGroup):
    waiting_task = State()
    waiting_date = State()
    waiting_time = State()
    editing_task = State()
    editing_time = State()

# === ИНЛАЙН-КНОПКИ ===
def inline_main_menu():
    kb = [
        [InlineKeyboardButton(text="Добавить напоминание", callback_data="add_reminder")],
        [InlineKeyboardButton(text="Мои напоминания", callback_data="list_reminders")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_button(to_page):
    kb = [[InlineKeyboardButton(text="Назад", callback_data=f"back_to_{to_page}")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# === КАЛЕНДАРЬ ===
def get_calendar(year=None, month=None):
    now = datetime.now(tz)
    year = year or now.year
    month = month or now.month

    kb = []
    kb.append([
        InlineKeyboardButton(text="Previous", callback_data=f"cal_prev_{year}_{month}"),
        InlineKeyboardButton(text=f"{month:02d}.{year}", callback_data="ignore"),
        InlineKeyboardButton(text="Next", callback_data=f"cal_next_{year}_{month}")
    ])
    kb.append([InlineKeyboardButton(text=d, callback_data="ignore") for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]])

    from calendar import monthcalendar
    weeks = monthcalendar(year, month)
    for week in weeks:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
            else:
                today_emoji = " сегодня" if day == now.day and month == now.month and year == now.year else ""
                row.append(InlineKeyboardButton(text=f"{day}{today_emoji}", callback_data=f"cal_day_{year}_{month}_{day}"))
        kb.append(row)

    kb.append([InlineKeyboardButton(text="Назад", callback_data="back_to_list")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# === СТАРТ ===
@dp.message(CommandStart())
async def start(message: types.Message):
    msg = await message.answer(
        "Привет! Я — умный бот-напоминалка\n\n"
        "• Календарь\n"
        "• Время: <code>1830</code>\n"
        "• Только активные\n\n"
        "Выбери действие:",
        parse_mode="HTML",
        reply_markup=inline_main_menu()
    )

# === ГЛАВНОЕ МЕНЮ ===
async def show_main_menu(obj):
    if hasattr(obj, 'message'):
        msg = obj.message
    else:
        msg = obj
    await msg.edit_text(
        "Главное меню:",
        reply_markup=inline_main_menu()
    )

# === СПИСОК НАПОМИНАНИЙ ===
@dp.callback_query(F.data == "list_reminders")
async def inline_list_reminders(call: types.CallbackQuery, state: FSMContext):
    user_id = str(call.from_user.id)
    user_rems = reminders.get(user_id, [])
    now = datetime.now(tz)
    active_rems = [r for r in user_rems if datetime.fromisoformat(r["dt"]) > now]

    if not active_rems:
        await call.message.edit_text(
            "У тебя нет активных напоминаний.",
            reply_markup=back_button("main")
        )
        return

    text = "Твои напоминания:\n\n"
    for rem in active_rems:
        dt = datetime.fromisoformat(rem["dt"]).astimezone(tz)
        emoji = "Купить" if "куп" in rem['task'].lower() else \
                "Забрать" if "забрать" in rem['task'].lower() else \
                "Позвонить" if "звон" in rem['task'].lower() else \
                "Сделать" if "сдел" in rem['task'].lower() else \
                "Задача"
        text += f"{emoji} <b>{rem['task']}</b> — <code>{dt.strftime('%d.%m %H:%M')}</code>\n"

    kb_rows = []
    for rem in active_rems:
        kb_rows.append([
            InlineKeyboardButton(text="Редактировать", callback_data=f"edit_{user_id}_{rem['id']}"),
            InlineKeyboardButton(text="Отменить", callback_data=f"cancel_{user_id}_{rem['id']}")
        ])
    kb_rows.append([InlineKeyboardButton(text="Назад", callback_data="back_to_main")])
    final_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=final_kb
    )

# === РЕДАКТИРОВАНИЕ ===
@dp.callback_query(F.data.startswith("edit_"))
async def edit_reminder(call: types.CallbackQuery, state: FSMContext):
    _, user_id, rem_id = call.data.split("_")
    if str(call.from_user.id) != user_id:
        await call.answer("Это не твоё!", show_alert=True)
        return

    user_rems = reminders.get(user_id, [])
    rem = next((r for r in user_rems if r["id"] == rem_id), None)
    if not rem:
        await call.answer("Уже удалено.")
        return

    await state.set_state(ReminderStates.editing_task)
    await state.update_data(edit_rem_id=rem_id, old_msg_id=call.message.message_id)

    await call.message.edit_text(
        f"Редактируем: <b>{rem['task']}</b>\n\n"
        "Новое название (или оставь как есть):",
        parse_mode="HTML",
        reply_markup=back_button("list")
    )
    await call.answer()

@dp.message(ReminderStates.editing_task)
async def process_edit_task(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = str(message.from_user.id)
    rem_id = data["edit_rem_id"]
    old_msg_id = data["old_msg_id"]

    new_task = message.text.strip()
    if not new_task:
        new_task = reminders[user_id][int(rem_id)]["task"]

    reminders[user_id][int(rem_id)]["task"] = new_task
    save_reminders()

    await state.set_state(ReminderStates.editing_time)
    await state.update_data(edit_task=new_task)

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=old_msg_id,
        text=f"Новое название: <b>{new_task}</b>\n\n"
             "Новое время (например: <code>1830</code>):",
        parse_mode="HTML",
        reply_markup=back_button("list")
    )
    await message.delete()

@dp.message(ReminderStates.editing_time)
async def process_edit_time(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    cleaned = ''.join(filter(str.isdigit, raw))

    if len(cleaned) == 4:
        try:
            hour = int(cleaned[:2])
            minute = int(cleaned[2:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except:
            await message.answer("Неверное время! Пример: <code>1830</code>", parse_mode="HTML")
            return
    else:
        await message.answer("Неверный формат! Пример: <code>1830</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    user_id = str(message.from_user.id)
    rem_id = data["edit_rem_id"]
    old_msg_id = data["old_msg_id"]
    new_task = data["edit_task"]

    old_dt = datetime.fromisoformat(reminders[user_id][int(rem_id)]["dt"])
    new_dt = old_dt.replace(hour=hour, minute=minute)
    new_dt = tz.localize(new_dt)

    reminders[user_id][int(rem_id)]["dt"] = new_dt.isoformat()
    save_reminders()

    scheduler.remove_job(f"{user_id}_{rem_id}")
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=new_dt,
        id=f"{user_id}_{rem_id}",
        args=[int(user_id), reminders[user_id][int(rem_id)]]
    )

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=old_msg_id,
        text=f"Готово!\n\n"
             f"<b>{new_task}</b>\n"
             f"Время: <code>{new_dt.strftime('%d.%m %H:%M')}</code>",
        parse_mode="HTML",
        reply_markup=back_button("main")
    )
    await message.delete()
    await state.clear()

# === ОТМЕНА ИЗ СПИСКА ===
@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_from_list(call: types.CallbackQuery):
    _, user_id, rem_id = call.data.split("_")
    if str(call.from_user.id) != user_id:
        await call.answer("Это не твоё!", show_alert=True)
        return

    user_rems = reminders.get(user_id, [])
    rem = next((r for r in user_rems if r["id"] == rem_id), None)
    if not rem:
        await call.answer("Уже удалено.")
        return

    reminders[user_id] = [r for r in user_rems if r["id"] != rem_id]
    scheduler.remove_job(f"{user_id}_{rem_id}")
    save_reminders()

    await call.message.edit_text(f"Отменено: {rem['task']}", reply_markup=back_button("main"))
    await call.answer("Удалено!")

# === ДОБАВЛЕНИЕ ===
@dp.callback_query(F.data == "add_reminder")
async def add_reminder(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(ReminderStates.waiting_task)
    msg = await call.message.edit_text(
        "Что нужно сделать?\n\n"
        "Пример: <code>забрать заказ в озоне</code>",
        parse_mode="HTML",
        reply_markup=back_button("main")
    )
    await state.update_data(msg_id=msg.message_id)

@dp.message(ReminderStates.waiting_task)
async def process_task(message: types.Message, state: FSMContext):
    await state.update_data(task=message.text.strip())
    await state.set_state(ReminderStates.waiting_date)

    data = await state.get_data()
    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=data["msg_id"],
        text="Выбери дату:",
        reply_markup=get_calendar()
    )
    await message.delete()

@dp.callback_query(F.data.startswith("cal_"))
async def handle_calendar(call: types.CallbackQuery, state: FSMContext):
    data = call.data.split("_")
    action = data[1]

    if action == "ignore":
        await call.answer()
        return

    if action in ["prev", "next"]:
        year, month = int(data[2]), int(data[3])
        if action == "prev":
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        else:
            month += 1
            if month == 13:
                month = 1
                year += 1
        await call.message.edit_reply_markup(reply_markup=get_calendar(year, month))
        await call.answer()
        return

    if action == "day":
        year, month, day = int(data[2]), int(data[3]), int(data[4])
        await state.update_data(date=f"{year}-{month:02d}-{day:02d}")
        await state.set_state(ReminderStates.waiting_time)

        await call.message.edit_text(
            f"Дата: <b>{day:02d}.{month:02d}.{year}</b>\n\n"
            "Теперь время (например: <code>1830</code>):",
            parse_mode="HTML",
            reply_markup=back_button("calendar")
        )
        await call.answer()

@dp.message(ReminderStates.waiting_time)
async def process_time(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    cleaned = ''.join(filter(str.isdigit, raw))

    if len(cleaned) == 4:
        try:
            hour = int(cleaned[:2])
            minute = int(cleaned[2:])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError()
        except:
            await message.answer("Неверное время! Пример: <code>1830</code>", parse_mode="HTML")
            return
    else:
        await message.answer("Неверный формат! Пример: <code>1830</code>", parse_mode="HTML")
        return

    data = await state.get_data()
    task = data["task"]
    date_str = data["date"]
    remind_dt = datetime.strptime(f"{date_str} {hour:02d}:{minute:02d}", "%Y-%m-%d %H:%M")
    remind_dt = tz.localize(remind_dt)

    user_id = str(message.from_user.id)
    user_rems = reminders.get(user_id, [])
    rem_id = str(len(user_rems))

    reminder = {
        "id": rem_id,
        "task": task,
        "dt": remind_dt.isoformat(),
        "tz": TIMEZONE
    }
    user_rems.append(reminder)
    reminders[user_id] = user_rems
    save_reminders()

    job_id = f"{user_id}_{rem_id}"
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=remind_dt,
        id=job_id,
        args=[int(user_id), reminder]
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отложить 10 мин", callback_data=f"postpone_{user_id}_{rem_id}_10"),
            InlineKeyboardButton(text="Отложить 30 мин", callback_data=f"postpone_{user_id}_{rem_id}_30")
        ],
        [
            InlineKeyboardButton(text="Отменить", callback_data=f"cancel_{user_id}_{rem_id}")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main")]
    ])

    await bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=data["msg_id"],
        text=f"Напоминание создано!\n\n"
             f"<b>{task}</b>\n"
             f"Время: <code>{remind_dt.strftime('%d.%m %H:%M')}</code>",
        parse_mode="HTML",
        reply_markup=kb
    )
    await message.delete()
    await state.clear()

# === НАЗАД ===
@dp.callback_query(F.data.startswith("back_to_"))
async def back_navigation(call: types.CallbackQuery, state: FSMContext):
    target = call.data.split("_")[-1]

    if target == "main":
        await show_main_menu(call)
    elif target == "list":
        await inline_list_reminders(call, state)
    elif target == "calendar":
        await call.message.edit_reply_markup(reply_markup=get_calendar())
    await call.answer()

# === УВЕДОМЛЕНИЕ — ВСЕГДА НОВОЕ СООБЩЕНИЕ ===
async def send_reminder(user_id: int, reminder: dict):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Отложить 10 мин", callback_data=f"postpone_{user_id}_{reminder['id']}_10"),
            InlineKeyboardButton(text="Отложить 30 мин", callback_data=f"postpone_{user_id}_{reminder['id']}_30")
        ],
        [
            InlineKeyboardButton(text="Отменить", callback_data=f"cancel_{user_id}_{reminder['id']}")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main")]
    ])

    dt = datetime.fromisoformat(reminder["dt"]).astimezone(tz)
    text = f"Напоминание!\n\n" \
           f"<b>{reminder['task']}</b>\n" \
           f"Время: <code>{dt.strftime('%H:%M %d.%m')}</code>"

    # ВСЕГДА ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ
    await bot.send_message(
        user_id,
        text,
        parse_mode="HTML",
        reply_markup=kb
    )

# === ОТЛОЖКА ===
@dp.callback_query(F.data.startswith("postpone_"))
async def postpone_reminder(call: types.CallbackQuery):
    _, user_id, rem_id, minutes = call.data.split("_")
    if str(call.from_user.id) != user_id:
        await call.answer("Это не твоё!", show_alert=True)
        return

    minutes = int(minutes)
    user_rems = reminders.get(user_id, [])
    rem = next((r for r in user_rems if r["id"] == rem_id), None)
    if not rem:
        await call.answer("Уже удалено.")
        return

    old_dt = datetime.fromisoformat(rem["dt"])
    new_dt = old_dt + timedelta(minutes=minutes)
    rem["dt"] = new_dt.isoformat()
    save_reminders()

    scheduler.remove_job(f"{user_id}_{rem_id}")
    scheduler.add_job(
        send_reminder,
        'date',
        run_date=new_dt,
        id=f"{user_id}_{rem_id}",
        args=[int(user_id), rem]
    )

    await call.message.edit_text(
        f"Отложено на {minutes} мин\n\n"
        f"<b>{rem['task']}</b>\n"
        f"Новое время: <code>{new_dt.astimezone(tz).strftime('%H:%M %d.%m')}</code>",
        parse_mode="HTML",
        reply_markup=back_button("main")
    )
    await call.answer("Отложено!")

# === ЗАПУСК ===
async def main():
    now = datetime.now(tz)
    scheduler.remove_all_jobs()

    for user_id, user_rems in reminders.items():
        active_rems = []
        for rem in user_rems:
            dt = datetime.fromisoformat(rem["dt"])
            if dt > now:
                scheduler.add_job(
                    send_reminder,
                    'date',
                    run_date=dt,
                    id=f"{user_id}_{rem['id']}",
                    args=[int(user_id), rem]
                )
                active_rems.append(rem)
        reminders[user_id] = active_rems

    save_reminders()
    scheduler.start()
    print("БОТ ЗАПУЩЕН! Нажми /start в Telegram")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())