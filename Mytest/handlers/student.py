# handlers/student.py
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import database as db
from config import SUBJECTS, ADMIN_ID

router = Router()

# ── FSM стани ────────────────────────────────────────

class AddHomework(StatesGroup):
    entering_text     = State()
    entering_deadline = State()
    waiting_file      = State()

class EditHomework(StatesGroup):
    choosing_field = State()
    entering_text  = State()
    entering_deadline = State()

# ── Клавіатури ────────────────────────────────────────

def main_menu():
    kb = ReplyKeyboardBuilder()
    for s in SUBJECTS:
        kb.button(text=s)
    kb.button(text="📋 Всі ДЗ на тиждень")
    kb.button(text="⚙️ Налаштування")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def subject_menu(subject: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Сьогодні",  callback_data=f"view_today:{subject}")
    kb.button(text="📆 Тиждень",   callback_data=f"view_week:{subject}")
    kb.button(text="🗓 Місяць",    callback_data=f"view_month:{subject}")
    kb.button(text="📋 Всі ДЗ",   callback_data=f"view_all:{subject}")
    kb.button(text="➕ Додати ДЗ", callback_data=f"add:{subject}")
    kb.adjust(2, 2, 1)
    return kb.as_markup()

def back_kb(subject: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="◀️ Назад", callback_data=f"subject:{subject}")
    return kb.as_markup()

def dates_kb(dates: list[str], subject: str):
    """Клавіатура з датами для вибору."""
    # Використовуємо індекс предмету щоб не перевищити ліміт callback_data
    subj_idx = SUBJECTS.index(subject) if subject in SUBJECTS else 0
    kb = InlineKeyboardBuilder()
    for iso_date in dates:
        y, m, d = iso_date.split("-")
        kb.button(text=f"📅 {d}.{m}.{y}", callback_data=f"vd:{subj_idx}:{iso_date}")
    kb.button(text="◀️ Назад", callback_data=f"subject:{subject}")
    kb.adjust(2)
    return kb.as_markup()

def skip_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏭ Пропустити", callback_data="skip_file")
    return kb.as_markup()

def hw_actions_kb(hw_id: int, is_done: bool, user_id: int = 0, added_by: int = 0):
    """Кнопки дій під кожним ДЗ."""
    kb = InlineKeyboardBuilder()
    done_btn = "✅ Виконано" if is_done else "🔲 Не виконано"
    kb.button(text=done_btn, callback_data=f"btn_done:{hw_id}")    # Редагувати і видалити — тільки своє або адмін
    if user_id == added_by or user_id == ADMIN_ID:
        kb.button(text="✏️ Редагувати", callback_data=f"btn_edit:{hw_id}")
        kb.button(text="🗑 Видалити",   callback_data=f"btn_del:{hw_id}")
        kb.adjust(1, 2)
    else:
        kb.adjust(1)
    return kb.as_markup()

# ── Надіслати список ДЗ (з файлами якщо є) ───────────

async def send_homeworks(chat_id: int, bot, homeworks: list, title: str, subject: str, done_ids: set = None, user_id: int = 0):
    if done_ids is None:
        done_ids = set()
    for hw in homeworks:
        y, m, d = hw["deadline"].split("-")
        is_done = hw["id"] in done_ids
        added_by_name = f"👤 {hw['added_by_name']}" if hw["added_by_name"] else ""
        caption = (
            f"📚 <b>{hw['subject']}</b>\n"
            f"📝 {hw['description']}\n"
            f"📅 {d}.{m}.{y}\n"
            f"{added_by_name}"
        )
        kb = hw_actions_kb(hw["id"], is_done, user_id=user_id, added_by=hw["added_by"])
        if hw["file_id"] and hw["file_type"] == "photo":
            await bot.send_photo(chat_id, hw["file_id"], caption=caption, parse_mode="HTML", reply_markup=kb)
        elif hw["file_id"] and hw["file_type"] == "document":
            await bot.send_document(chat_id, hw["file_id"], caption=caption, parse_mode="HTML", reply_markup=kb)
        else:
            await bot.send_message(chat_id, caption, parse_mode="HTML", reply_markup=kb)

async def view_homeworks(callback: CallbackQuery, homeworks: list, title: str, subject: str):
    if not homeworks:
        await callback.message.edit_text(
            f"🎉 Немає ДЗ",
            reply_markup=back_kb(subject)
        )
        return
    done_ids = await db.get_done_ids(callback.from_user.id)
    await callback.message.edit_text(
        f"<b>{title}</b>",
        parse_mode="HTML",
        reply_markup=back_kb(subject)
    )
    await send_homeworks(callback.message.chat.id, callback.bot, homeworks, title, subject, done_ids, user_id=callback.from_user.id)

# ── /start ────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db.register_user(message.from_user.id, message.from_user.username or "")
    await message.answer(
        f"👋 Привіт, <b>{message.from_user.first_name}</b>!\n\nОбери предмет 👇",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )

# ── Натискання на предмет ─────────────────────────────

@router.message(F.text.in_(SUBJECTS))
async def open_subject(message: Message, state: FSMContext):
    await state.clear()
    subject = message.text
    await state.update_data(subject=subject)
    await message.answer(
        f"<b>{subject}</b>\n\nОбери період 👇",
        parse_mode="HTML",
        reply_markup=subject_menu(subject),
    )

# ── Callback: повернутися до меню предмету ────────────

@router.callback_query(F.data.startswith("subject:"))
async def cb_open_subject(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.split(":", 1)[1]
    await state.clear()
    await state.update_data(subject=subject)
    await callback.message.edit_text(
        f"<b>{subject}</b>\n\nОбери період 👇",
        parse_mode="HTML",
        reply_markup=subject_menu(subject),
    )

# ── ДЗ на сьогодні ───────────────────────────────────

@router.callback_query(F.data.startswith("view_today:"))
async def view_today(callback: CallbackQuery):
    subject = callback.data.split(":", 1)[1]
    today = date.today().isoformat()
    today_ua = date.today().strftime("%d.%m.%Y")
    homeworks = await db.get_homeworks_by_subject_and_date(subject, today, today)
    await view_homeworks(callback, homeworks, f"📅 {subject} — {today_ua}", subject)

# ── ДЗ на тиждень ─────────────────────────────────────

@router.callback_query(F.data.startswith("view_week:"))
async def view_week(callback: CallbackQuery):
    subject = callback.data.split(":", 1)[1]
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    homeworks = await db.get_homeworks_by_subject_and_date(subject, today, week_end)
    await view_homeworks(callback, homeworks, f"📆 {subject} — тиждень", subject)

# ── ДЗ на місяць — показуємо список дат ──────────────

def month_dates_kb(dates: list[str], subject: str):
    subj_idx = SUBJECTS.index(subject) if subject in SUBJECTS else 0
    kb = InlineKeyboardBuilder()
    for iso_date in dates:
        y, m, d = iso_date.split("-")
        kb.button(text=f"📅 {d}.{m}.{y}", callback_data=f"md:{subj_idx}:{iso_date}")
    kb.button(text="◀️ Назад", callback_data=f"subject:{subject}")
    kb.adjust(2)
    return kb.as_markup()

@router.callback_query(F.data.startswith("view_month:"))
async def view_month(callback: CallbackQuery):
    subject = callback.data.split(":", 1)[1]
    today = date.today().isoformat()
    month_end = (date.today() + timedelta(days=30)).isoformat()
    homeworks = await db.get_homeworks_by_subject_and_date(subject, today, month_end)

    if not homeworks:
        await callback.message.edit_text(
            f"🎉 На місяць немає ДЗ з {subject}",
            reply_markup=back_kb(subject)
        )
        return

    unique_dates = list(dict.fromkeys(hw["deadline"] for hw in homeworks))
    await callback.message.edit_text(
        f"<b>🗓 {subject} — місяць</b>\n\nОбери дату 👇",
        parse_mode="HTML",
        reply_markup=month_dates_kb(unique_dates, subject)
    )

@router.callback_query(F.data.startswith("md:"))
async def view_month_by_date(callback: CallbackQuery):
    _, subj_idx, iso_date = callback.data.split(":", 2)
    subject = SUBJECTS[int(subj_idx)]
    homeworks = await db.get_homeworks_by_subject_and_date(subject, iso_date, iso_date)
    y, m, d = iso_date.split("-")
    await view_homeworks(callback, homeworks, f"📅 {subject} — {d}.{m}.{y}", subject)

# ── Всі ДЗ — показуємо список дат ────────────────────

@router.callback_query(F.data.startswith("view_all:"))
async def view_all_dates(callback: CallbackQuery):
    subject = callback.data.split(":", 1)[1]
    today = date.today().isoformat()
    homeworks = await db.get_homeworks_by_subject_and_date(subject, today, "9999-12-31")

    if not homeworks:
        await callback.message.edit_text(
            f"🎉 Немає жодного ДЗ з {subject}",
            reply_markup=back_kb(subject)
        )
        return

    # Збираємо унікальні дати
    unique_dates = list(dict.fromkeys(hw["deadline"] for hw in homeworks))

    await callback.message.edit_text(
        f"<b>📋 {subject} — всі ДЗ</b>\n\nОбери дату 👇",
        parse_mode="HTML",
        reply_markup=dates_kb(unique_dates, subject)
    )

# ── Всі ДЗ — показуємо ДЗ на обрану дату ────────────

@router.callback_query(F.data.startswith("vd:"))
async def view_by_date(callback: CallbackQuery):
    _, subj_idx, iso_date = callback.data.split(":", 2)
    subject = SUBJECTS[int(subj_idx)]
    homeworks = await db.get_homeworks_by_subject_and_date(subject, iso_date, iso_date)
    y, m, d = iso_date.split("-")
    await view_homeworks(callback, homeworks, f"📅 {subject} — {d}.{m}.{y}", subject)

# ── Всі ДЗ на тиждень — спочатку вибір предмету ──────

def week_subjects_kb(subjects: list[str]):
    """Список предметів які мають ДЗ + кнопка 'Всі предмети'."""
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Всі предмети", callback_data="week_subject:__all__")
    for s in subjects:
        kb.button(text=s, callback_data=f"week_subject:{s}")
    kb.adjust(1, 2)
    return kb.as_markup()

@router.message(F.text == "📋 Всі ДЗ на тиждень")
async def view_week_all(message: Message):
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    subjects = await db.get_subjects_with_homeworks(today, week_end)

    if not subjects:
        await message.answer("🎉 На тиждень немає жодних ДЗ!", reply_markup=main_menu())
        return

    await message.answer(
        "<b>📋 ДЗ на тиждень</b>\n\nОбери предмет 👇",
        parse_mode="HTML",
        reply_markup=week_subjects_kb(subjects),
    )

@router.callback_query(F.data.startswith("week_subject:"))
async def week_by_subject(callback: CallbackQuery):
    subject = callback.data.split(":", 1)[1]
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()

    if subject == "__all__":
        homeworks = await db.get_homeworks_week(today, week_end)
        title = "📋 Всі ДЗ на тиждень"
    else:
        homeworks = await db.get_homeworks_by_subject_and_date(subject, today, week_end)
        title = f"📆 {subject} — тиждень"

    # Кнопка назад до вибору предмету
    back = InlineKeyboardBuilder()
    back.button(text="◀️ Назад", callback_data="week_back")

    if not homeworks:
        await callback.message.edit_text(
            f"🎉 На тиждень немає ДЗ",
            reply_markup=back.as_markup()
        )
        return

    await callback.message.edit_text(
        f"<b>{title}</b>",
        parse_mode="HTML",
        reply_markup=back.as_markup()
    )
    done_ids = await db.get_done_ids(callback.from_user.id)
    await send_homeworks(callback.message.chat.id, callback.bot, homeworks, title, subject, done_ids, user_id=callback.from_user.id)

@router.callback_query(F.data == "week_back")
async def week_back(callback: CallbackQuery):
    today = date.today().isoformat()
    week_end = (date.today() + timedelta(days=7)).isoformat()
    subjects = await db.get_subjects_with_homeworks(today, week_end)
    await callback.message.edit_text(
        "<b>📋 ДЗ на тиждень</b>\n\nОбери предмет 👇",
        parse_mode="HTML",
        reply_markup=week_subjects_kb(subjects),
    )

# ── Додати ДЗ: крок 1 ────────────────────────────────

@router.callback_query(F.data.startswith("add:"))
async def add_start(callback: CallbackQuery, state: FSMContext):
    subject = callback.data.split(":", 1)[1]
    await state.update_data(subject=subject)
    await callback.message.edit_text(
        f"➕ Додаємо ДЗ з <b>{subject}</b>\n\n📝 Введи текст завдання:",
        parse_mode="HTML",
    )
    await state.set_state(AddHomework.entering_text)

# ── Додати ДЗ: крок 2 ────────────────────────────────

@router.message(AddHomework.entering_text)
async def add_text(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    await message.answer(
        f"📅 Введи дедлайн у форматі <b>ДД.ММ.РРРР</b>\nНаприклад: <code>{tomorrow}</code>",
        parse_mode="HTML",
    )
    await state.set_state(AddHomework.entering_deadline)

# ── Додати ДЗ: крок 3 ────────────────────────────────

@router.message(AddHomework.entering_deadline)
async def add_deadline(message: Message, state: FSMContext):
    raw = message.text.strip()
    parts = raw.split(".")

    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        await message.answer("⚠️ Невірний формат! Введи дату як <b>ДД.ММ.РРРР</b>", parse_mode="HTML")
        return

    day, month, year = parts
    deadline_iso = f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    if deadline_iso < date.today().isoformat():
        await message.answer("⚠️ Дата вже минула! Введи майбутню дату.", parse_mode="HTML")
        return

    await state.update_data(deadline=deadline_iso, deadline_raw=raw)

    # Перевірка на дублікат
    data = await state.get_data()
    is_duplicate = await db.check_duplicate(data["subject"], deadline_iso)
    if is_duplicate:
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Так, додати",   callback_data="confirm_add:yes")
        kb.button(text="❌ Скасувати",     callback_data="confirm_add:no")
        kb.adjust(2)
        await message.answer(
            f"⚠️ <b>ДЗ з {data['subject']} на цю дату вже існує!</b>\n\n"
            f"Все одно додати?",
            parse_mode="HTML",
            reply_markup=kb.as_markup()
        )
        return

    await message.answer(
        "📎 Прикріпи фото або файл до завдання\n"
        "або натисни <b>Пропустити</b>",
        parse_mode="HTML",
        reply_markup=skip_kb(),
    )
    await state.set_state(AddHomework.waiting_file)

# ── Підтвердження додавання дубліката ────────────────

@router.callback_query(F.data.startswith("confirm_add:"))
async def confirm_add(callback: CallbackQuery, state: FSMContext):
    answer = callback.data.split(":")[1]
    if answer == "no":
        await state.clear()
        await callback.message.edit_text("❌ Скасовано.")
        await callback.message.answer("Обери предмет 👇", reply_markup=main_menu())
        return

    await callback.message.edit_text(
        "📎 Прикріпи фото або файл до завдання\n"
        "або натисни <b>Пропустити</b>",
        parse_mode="HTML",
        reply_markup=skip_kb()
    )
    await state.set_state(AddHomework.waiting_file)

# ── Додати ДЗ: крок 4а — фото ────────────────────────

@router.message(AddHomework.waiting_file, F.photo)
async def add_photo(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await save_homework(message, state, file_id=file_id, file_type="photo")

# ── Додати ДЗ: крок 4б — документ ───────────────────

@router.message(AddHomework.waiting_file, F.document)
async def add_document(message: Message, state: FSMContext):
    file_id = message.document.file_id
    await save_homework(message, state, file_id=file_id, file_type="document")

# ── Додати ДЗ: крок 4в — пропустити ──────────────────

@router.callback_query(F.data == "skip_file")
async def skip_file(callback: CallbackQuery, state: FSMContext):
    await callback.message.delete()
    await save_homework(callback.message, state, file_id=None, file_type=None)

# ── Зберегти ДЗ в БД ─────────────────────────────────

async def save_homework(message: Message, state: FSMContext, file_id, file_type):
    data = await state.get_data()
    subject = data["subject"]
    first = message.chat.first_name or ""
    last = message.chat.last_name or ""
    name = f"{first} {last}".strip() or message.chat.username or "Невідомо"

    await db.add_homework(
        subject=subject,
        description=data["description"],
        deadline=data["deadline"],
        added_by=message.chat.id,
        file_id=file_id,
        file_type=file_type,
        added_by_name=name,
    )
    await state.clear()

    attachment_text = "📎 Файл прикріплено" if file_id else "Без вкладень"
    await message.answer(
        f"✅ <b>ДЗ додано!</b>\n\n"
        f"📚 {subject}\n"
        f"📝 {data['description']}\n"
        f"📅 Дедлайн: {data['deadline_raw']}\n"
        f"{attachment_text}\n\n"
        "Обери предмет 👇",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )

# ── Кнопка: Видалити ─────────────────────────────────

# ── Кнопка: Видалити ─────────────────────────────────

def confirm_del_kb(hw_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Так, видалити", callback_data=f"confirm_del:{hw_id}")
    kb.button(text="❌ Скасувати",     callback_data=f"cancel_del:{hw_id}")
    kb.adjust(2)
    return kb.as_markup()

@router.callback_query(F.data.startswith("btn_del:"))
async def btn_delete(callback: CallbackQuery):
    hw_id = int(callback.data.split(":")[1])
    hw = await db.get_homework_by_id(hw_id)

    if not hw:
        await callback.answer("⚠️ ДЗ не знайдено!", show_alert=True)
        return

    if hw["added_by"] != callback.from_user.id and callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ Можна видаляти лише своє ДЗ!", show_alert=True)
        return

    # Замінюємо кнопки на підтвердження прямо в повідомленні
    try:
        await callback.message.edit_reply_markup(reply_markup=confirm_del_kb(hw_id))
    except Exception:
        await callback.message.edit_caption(caption=callback.message.caption, reply_markup=confirm_del_kb(hw_id))
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_del:"))
async def confirm_delete(callback: CallbackQuery):
    hw_id = int(callback.data.split(":")[1])
    if callback.from_user.id == ADMIN_ID:
        await db.admin_delete_homework(hw_id)
    else:
        await db.delete_homework(hw_id, callback.from_user.id)
    await callback.message.delete()
    await callback.answer("🗑 Видалено!")

@router.callback_query(F.data.startswith("cancel_del:"))
async def cancel_delete(callback: CallbackQuery):
    hw_id = int(callback.data.split(":")[1])
    hw = await db.get_homework_by_id(hw_id)
    # Повертаємо оригінальні кнопки
    done_ids = await db.get_done_ids(callback.from_user.id)
    is_done = hw_id in done_ids
    try:
        await callback.message.edit_reply_markup(
            reply_markup=hw_actions_kb(hw_id, is_done, user_id=callback.from_user.id, added_by=hw["added_by"])
        )
    except Exception:
        await callback.message.edit_caption(
            caption=callback.message.caption,
            reply_markup=hw_actions_kb(hw_id, is_done, user_id=callback.from_user.id, added_by=hw["added_by"])
        )
    await callback.answer("Скасовано")

# ── Кнопка: Виконано ──────────────────────────────────

@router.callback_query(F.data.startswith("btn_done:"))
async def btn_done(callback: CallbackQuery):
    hw_id = int(callback.data.split(":")[1])
    is_done = await db.toggle_homework_done(hw_id, callback.from_user.id)

    hw = await db.get_homework_by_id(hw_id)
    y, m, d = hw["deadline"].split("-")
    added_by_name = f"👤 {hw['added_by_name']}" if hw["added_by_name"] else ""
    caption = (
        f"📚 <b>{hw['subject']}</b>\n"
        f"📝 {hw['description']}\n"
        f"📅 {d}.{m}.{y}\n"
        f"{added_by_name}"
    )
    new_kb = hw_actions_kb(hw_id, is_done, user_id=callback.from_user.id, added_by=hw["added_by"])
    try:
        await callback.message.edit_caption(caption=caption, parse_mode="HTML", reply_markup=new_kb)
    except Exception:
        await callback.message.edit_text(caption, parse_mode="HTML", reply_markup=new_kb)
    await callback.answer("✅ Виконано!" if is_done else "🔲 Не виконано!")

# ── Кнопка: Редагувати ────────────────────────────────

def edit_field_kb(hw_id: int):
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Змінити текст",    callback_data=f"edit_text:{hw_id}")
    kb.button(text="📅 Змінити дедлайн", callback_data=f"edit_date:{hw_id}")
    kb.button(text="❌ Скасувати",        callback_data="edit_cancel")
    kb.adjust(2, 1)
    return kb.as_markup()

@router.callback_query(F.data.startswith("btn_edit:"))
async def btn_edit(callback: CallbackQuery, state: FSMContext):
    hw_id = int(callback.data.split(":")[1])
    hw = await db.get_homework_by_id(hw_id)

    if not hw:
        await callback.answer("⚠️ ДЗ не знайдено!", show_alert=True)
        return

    if hw["added_by"] != callback.from_user.id and callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ Можна редагувати лише своє ДЗ!", show_alert=True)
        return

    y, m, d = hw["deadline"].split("-")
    await state.update_data(hw_id=hw_id)
    await state.set_state(EditHomework.choosing_field)
    await callback.message.answer(
        f"✏️ <b>Редагування ДЗ:</b>\n\n"
        f"📚 {hw['subject']}\n"
        f"📝 {hw['description']}\n"
        f"📅 {d}.{m}.{y}\n\n"
        f"Що змінити?",
        parse_mode="HTML",
        reply_markup=edit_field_kb(hw_id)
    )
    await callback.answer()

@router.callback_query(EditHomework.choosing_field, F.data.startswith("edit_text:"))
async def edit_text_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введи новий текст завдання:")
    await state.set_state(EditHomework.entering_text)

@router.callback_query(EditHomework.choosing_field, F.data.startswith("edit_date:"))
async def edit_date_start(callback: CallbackQuery, state: FSMContext):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
    await callback.message.edit_text(
        f"📅 Введи новий дедлайн у форматі <b>ДД.ММ.РРРР</b>\nНаприклад: <code>{tomorrow}</code>",
        parse_mode="HTML"
    )
    await state.set_state(EditHomework.entering_deadline)

@router.callback_query(EditHomework.choosing_field, F.data == "edit_cancel")
async def edit_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.answer("Скасовано")

@router.message(EditHomework.entering_text)
async def edit_text_save(message: Message, state: FSMContext):
    data = await state.get_data()
    hw = await db.get_homework_by_id(data["hw_id"])
    editor_id = message.from_user.id if message.from_user.id != ADMIN_ID else hw["added_by"]
    await db.update_homework(data["hw_id"], editor_id, message.text, hw["deadline"])
    await state.clear()
    await message.answer("✅ Текст оновлено!\n\nОбери предмет 👇", reply_markup=main_menu())

@router.message(EditHomework.entering_deadline)
async def edit_date_save(message: Message, state: FSMContext):
    raw = message.text.strip()
    parts = raw.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        await message.answer("⚠️ Невірний формат! Введи дату як <b>ДД.ММ.РРРР</b>", parse_mode="HTML")
        return
    day, month, year = parts
    deadline_iso = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    if deadline_iso < date.today().isoformat():
        await message.answer("⚠️ Дата вже минула! Введи майбутню дату.", parse_mode="HTML")
        return
    data = await state.get_data()
    hw = await db.get_homework_by_id(data["hw_id"])
    editor_id = message.from_user.id if message.from_user.id != ADMIN_ID else hw["added_by"]
    await db.update_homework(data["hw_id"], editor_id, hw["description"], deadline_iso)
    await state.clear()
    await message.answer("✅ Дедлайн оновлено!\n\nОбери предмет 👇", reply_markup=main_menu())

# ── Налаштування ──────────────────────────────────────

def reminder_kb():
    kb = InlineKeyboardBuilder()
    hours = [5, 6, 7, 8, 9, 10, 18, 19, 20, 21]
    for h in hours:
        kb.button(text=f"🕐 {h:02d}:00", callback_data=f"set_reminder:{h}")
    kb.button(text="🔕 Вимкнути", callback_data="set_reminder:off")
    kb.adjust(5)
    return kb.as_markup()

@router.message(F.text == "⚙️ Налаштування")
async def settings(message: Message):
    await message.answer(
        "⚙️ <b>Налаштування</b>\n\n"
        "🔔 Обери час нагадування про ДЗ на завтра:",
        parse_mode="HTML",
        reply_markup=reminder_kb()
    )

@router.callback_query(F.data.startswith("set_reminder:"))
async def set_reminder(callback: CallbackQuery):
    value = callback.data.split(":")[1]
    if value == "off":
        await db.set_reminder_hour(callback.from_user.id, -1)
        await callback.message.edit_text(
            "🔕 Нагадування вимкнено.",
            parse_mode="HTML"
        )
    else:
        hour = int(value)
        await db.set_reminder_hour(callback.from_user.id, hour)
        await callback.message.edit_text(
            f"✅ Нагадування встановлено на <b>{hour:02d}:00</b>!",
            parse_mode="HTML"
        )
    await callback.answer()
