#BOT_TOKEN
#ADMIN_ID
#STORAGE_CHANNEL_ID

import asyncio
from datetime import date, datetime
import logging
import os
import html
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
STORAGE_CHANNEL_ID = int(os.getenv("STORAGE_CHANNEL_ID", "0"))

router = Router()

BTN_BACK = "Назад"
BTN_FAQ = "Ответы на вопросы"
BTN_SUBJECTS = "Выбор предмета"
BTN_HEADMAN = "Запросить права старосты"
BTN_RULES = "Регламент"
BTN_ASK = "Задать вопрос по материалам"
BTN_VIDEO = "Добавить видео"
BTN_LECTURES = "Лекции"
BTN_NOTES = "Конспекты"
BTN_LECTURE = "Лекция"
BTN_PRACTICE = "Практика"

#ЗАГЛУШКИ----------------------------------------------------------------------------------------------

async def db_find_group(group_name: str) -> dict:
    known = {"бивт-25-6-1"}
    if group_name.strip().lower() in known:
        return {"id": 1, "name": group_name.strip().upper()}
    return None
    #Проверка наличия введённого названия группы group_name в базе данных названий групп


FAQ_DB: list[dict] = [
    {"q": "Где найти домашние задания и сроки сдачи?", "a": "Выберите предмет, затем Регламент."},
    {"q": "Где найти записи лекций?", "a": "Выберите предмет, затем Лекции."},
]
PENDING_QUESTIONS: dict[int, dict] = {}
_question_seq = 0

async def db_get_faq() -> list[dict]:
    return list(FAQ_DB)
    #Получение всех вопросов и ответов из базы данных


async def db_save_pending_question(user_id: int, question: str, admin_message_id: int) -> int:
    global _question_seq
    _question_seq += 1
    PENDING_QUESTIONS[admin_message_id] = {
        "id": _question_seq,
        "user_id": user_id,
        "question": question,
        "admin_message_id": admin_message_id,
    }
    return _question_seq
    #Сохранение нового вопроса пользователя, ожидающего ответа админа, в базу данных

async def db_get_pending_question(admin_message_id: int) -> dict:
    return PENDING_QUESTIONS.get(admin_message_id)
    #Поиск неотвеченного вопроса по id сообщения в чате админа в базе данных


async def db_answer_question(question_id: int, answer: str, publish: bool) -> None:
    for key, q in list(PENDING_QUESTIONS.items()):
        if q["id"] == question_id:
            del PENDING_QUESTIONS[key]
            if publish:
                FAQ_DB.append({"q": q["question"], "a": answer})
            break
    #Сохранение ответа админа в базу данных

async def db_get_subjects(group_id: int) -> list[dict]:
    return [
        {"id": 1, "name": "Введение в программирование на Python"},
        {"id": 2, "name": "Алгоритмы и структуры данных"},
        {"id": 3, "name": "Базы данных"},
    ]
    #Поиск существующих в группе предметов из базы данных

RULES_DB: dict[tuple[int, int], str] = {}

async def db_get_rules(group_id: int, subject_id: int) -> str:
    return RULES_DB.get((group_id, subject_id))
    #Получение регламента для предмета группы из базы данных


async def db_set_rules(group_id: int, subject_id: int, text: str, updated_by: int) -> None:
    RULES_DB[(group_id, subject_id)] = text
    #Сохранение регламента предмета для группы в базе данных


async def db_search_fragments(subject_id: int, question: str) -> list[dict]:
    return [
        {"lecture_date": "10.09.2026", "timecode": "00:12:30", "text": "Фрагмент 1 (заглушка)"},
        {"lecture_date": "17.09.2026", "timecode": "00:45:10", "text": "Фрагмент 2 (заглушка)"},
    ]
    #Поиск фрагментов лекций предмета, близких по смыслу к вопросу


async def db_get_dates(group_id: int, subject_id: int, kind: str) -> list[dict]:
    if kind == "lectures":
        videos = await db_get_videos(group_id, subject_id)
        return [
            {"id": v["id"],
             "title": f"{v['lecture_date']:%d.%m.%Y} - {v['title']} ({v['kind']})"}
            for v in videos
        ]
    return [
        {"id": 1, "title": "10.09.2026 - Введение"},
        {"id": 2, "title": "17.09.2026 - Типы данных"},
        {"id": 3, "title": "24.09.2026 - Функции"},
    ]
    #Получение дат и тем для существующих конспектов, лекций из базы данных


async def db_get_lecture_or_note(subject_id: int, kind: str, item_id: int) -> dict:
    return {
        "title": f"Урок №{item_id}",
        "url": f"https://example.com/{kind}/{item_id}",
        "text": "Содержимое конспекта (заглушка).",
    }
    #Получение материала по выбранной дате из базы данных


async def db_user_has_upload_rights(user_id: int) -> bool:
    return user_id == ADMIN_ID or await db_is_headman(user_id)
    #Проверка наличия прав старосты или администратора по базе данных


VIDEOS_DB: dict[int, dict] = {}
_video_seq = 0

async def db_save_video(
    group_id: int,
    subject_id: int,
    kind: str,
    title: str,
    lecture_date: date,
    channel_message_id: int,
    uploaded_by: int,
) -> int:
    global _video_seq
    _video_seq += 1
    VIDEOS_DB[_video_seq] = {
        "id": _video_seq,
        "group_id": group_id,
        "subject_id": subject_id,
        "kind": kind,
        "title": title,
        "lecture_date": lecture_date,
        "channel_message_id": channel_message_id,
        "uploaded_by": uploaded_by,
    }
    return _video_seq
    #Сохранение метаданных видео в базу данных


async def db_get_videos(group_id: int, subject_id: int) -> list[dict]:
    videos = [
        v for v in VIDEOS_DB.values()
        if v["group_id"] == group_id and v["subject_id"] == subject_id
    ]
    return sorted(videos, key=lambda v: v["lecture_date"])
    #Получение списка всех видео предмета для группы из базы данных, отсортированного по дате занятия


async def db_get_video(video_id: int) -> dict | None:
    return VIDEOS_DB.get(video_id)
    #Получение видео по айди из базы данных


USERS_DB: dict[int, dict] = {}

async def db_register_user(user_id: int, username: str | None, full_name: str) -> None:
    user = USERS_DB.setdefault(user_id, {"user_id": user_id, "is_headman": False})
    user["username"] = username
    user["full_name"] = full_name
    #Добавление пользователя в базу данных


async def db_find_user_by_username(username: str) -> dict | None:
    for user in USERS_DB.values():
        if (user.get("username") or "").lower() == username.lower():
            return user
    return None
    #Поиск пользователя по @username из базы данных


async def db_is_headman(user_id: int) -> bool:
    return USERS_DB.get(user_id, {}).get("is_headman", False)
    #Проверка пользователя на старосту по базе данных


async def db_grant_headman_rights(user_id: int) -> None:
    user = USERS_DB.setdefault(user_id, {"user_id": user_id, "username": None, "full_name": ""})
    user["is_headman"] = True
    logging.info("Права старосты выданы пользователю %s", user_id)
    #Выдача прав старосты (изменение данных о пользователе в базе данных)


async def db_revoke_headman_rights(user_id: int) -> None:
    if user_id in USERS_DB:
        USERS_DB[user_id]["is_headman"] = False
    logging.info("Права старосты сняты у пользователя %s", user_id)
    #Снятие прав старосты (изменение данных о пользователе в базе данных)


async def ml_generate_answer(question: str, fragments: list[dict]) -> str:
    refs = "\n".join(
        f"• {f['lecture_date']}, таймкод {f['timecode']}" for f in fragments
    )
    return f"Поиск ответа на вопрос: «{question}» в конспектах (заглушка)\n\nИсточники:\n{refs}"
    #Генерация ответа по найденным фрагментам из коспектов при помощи ИИ


async def ml_process_video(video_id: int, file_id: str, channel_message_id: int) -> None:
    logging.info("Видео %s (сообщение %s в канале) передано агенту",
                 video_id, channel_message_id)
    #Передача видео-файла ИИ-агенту


class Screen(StatesGroup):
    waiting_group = State()     # ввод учебной группы
    main_menu = State()         # главное меню
    faq = State()               # FAQ
    headman = State()           # заявка на права старосты
    subjects = State()          # выбор предмета
    actions = State()           # действия по предмету
    dates = State()             # выбор даты лекции/конспекта
    asking = State()            # вопрос по материалам
    video = State()             # ожидание видео
    video_title = State()       # ввод названия лекции
    video_date = State()        # ввод даты занятия
    video_kind = State()        # выбор: лекция или практика
    rules_subject = State()     # /rules: выбор предмета
    rules_text = State()        # /rules: ввод текста регламента


def make_kb(rows: list[list[str]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
    )


def main_menu_kb() -> ReplyKeyboardMarkup:
    return make_kb([[BTN_SUBJECTS], [BTN_FAQ, BTN_HEADMAN]])


def back_kb() -> ReplyKeyboardMarkup:
    return make_kb([[BTN_BACK]])


def actions_kb() -> ReplyKeyboardMarkup:
    return make_kb([
        [BTN_ASK, BTN_RULES],
        [BTN_LECTURES, BTN_NOTES],
        [BTN_VIDEO],
        [BTN_BACK],
    ])


def list_kb(titles: list[str], per_row: int = 1) -> ReplyKeyboardMarkup:
    rows = [titles[i:i + per_row] for i in range(0, len(titles), per_row)]
    return make_kb(rows + [[BTN_BACK]])


async def go_main_menu(message: Message, state: FSMContext):
    await state.set_state(Screen.main_menu)
    await message.answer("Главное меню", reply_markup=main_menu_kb())


async def go_subjects(message: Message, state: FSMContext):
    data = await state.get_data()
    subjects = await db_get_subjects(data["group_id"])
    await state.update_data(subjects_map={s["name"]: s["id"] for s in subjects})
    await state.set_state(Screen.subjects)
    await message.answer("Выберите предмет:",
                         reply_markup=list_kb([s["name"] for s in subjects], per_row=2))


async def go_actions(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(Screen.actions)
    await message.answer(f"{data['subject_name']}\nВыберите действие:", reply_markup=actions_kb())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await db_register_user(message.from_user.id, message.from_user.username,
                           message.from_user.full_name)
    await state.set_state(Screen.waiting_group)
    await message.answer(
        "Это ИИ-агент базы знаний для студентов.\n"
        "Помогу найти лекции, конспекты и ответить на вопросы по материалам.\n\n"
        "Для начала введите номер вашей учебной группы(заглушка, только бивт-25-6-1):",
        reply_markup=ReplyKeyboardRemove(),
    )


async def is_faq_answer(message: Message):
    if not message.from_user or message.from_user.id != ADMIN_ID:
        return False
    if not message.text or not message.reply_to_message:
        return False
    pending = await db_get_pending_question(message.reply_to_message.message_id)
    return {"pending": pending} if pending else False


@router.message(is_faq_answer)
async def admin_faq_answer(message: Message, bot: Bot, pending: dict):
    text = message.text.strip()
    publish = text.endswith("!")
    if publish:
        text = text.rstrip("!").rstrip() + "."

    await db_answer_question(pending["id"], text, publish)

    intro = ("Администратор ответил на ваш вопрос. Он добавлен в раздел «Ответы на вопросы»:"
             if publish else "Администратор ответил на ваш вопрос:")
    try:
        await bot.send_message(
            pending["user_id"],
            f"{intro}\n\n"
            f"<b>{html.escape(pending['question'])}</b>\n"
            f"{html.escape(text)}",
        )
    except TelegramAPIError:
        logging.exception("Не удалось отправить ответ пользователю %s", pending["user_id"])

    if publish:
        await message.answer("Ответ отправлен пользователю и добавлен в раздел «Ответы на вопросы».")
    else:
        await message.answer("Ответ отправлен только пользователю, в раздел «Ответы на вопросы» "
                             "он не добавлен.")


@router.message(Command("kick"))
async def cmd_kick(message: Message, command: CommandObject, bot: Bot):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Команда доступна только администратору.")
        return

    args = (command.args or "").split()
    if not args or not args[0].startswith("@") or len(args[0]) < 2:
        await message.answer("Использование: /kick @username")
        return

    username = args[0].lstrip("@")
    user = await db_find_user_by_username(username)
    if user is None:
        await message.answer(f"Пользователь @{html.escape(username)} не найден. ")
        return
    if not user["is_headman"]:
        await message.answer(f"@{html.escape(username)} не является старостой.")
        return

    await db_revoke_headman_rights(user["user_id"])
    try:
        await bot.send_message(user["user_id"], "Администратор снял с вас права старосты.")
    except TelegramAPIError:
        logging.exception("Не удалось уведомить пользователя %s", user["user_id"])
    await message.answer(f"С @{html.escape(username)} сняты права старосты.")


async def show_rules_subjects(message: Message, state: FSMContext):
    data = await state.get_data()
    subjects = await db_get_subjects(data["group_id"])
    await state.update_data(rules_subjects_map={s["name"]: s["id"] for s in subjects})
    await state.set_state(Screen.rules_subject)
    await message.answer("Для какого предмета вы хотите указать регламент?",
                         reply_markup=list_kb([s["name"] for s in subjects], per_row=2))


@router.message(Command("rules"))
async def cmd_rules(message: Message, state: FSMContext):
    if not await db_user_has_upload_rights(message.from_user.id):
        await message.answer("Команда доступна только старостам.")
        return
    data = await state.get_data()
    if "group_id" not in data:
        await message.answer("Сначала нажмите /start и выберите свою группу.")
        return
    await show_rules_subjects(message, state)


@router.message(Screen.rules_subject, F.text == BTN_BACK)
async def rules_subject_back(message: Message, state: FSMContext):
    await go_main_menu(message, state)


@router.message(Screen.rules_subject, F.text)
async def rules_choose_subject(message: Message, state: FSMContext):
    data = await state.get_data()
    subject_id = data["rules_subjects_map"].get(message.text)
    if subject_id is None:
        await message.answer("Выберите предмет с помощью кнопок внизу.")
        return
    await state.update_data(rules_subject_id=subject_id, rules_subject_name=message.text)
    await state.set_state(Screen.rules_text)

    current = await db_get_rules(data["group_id"], subject_id)
    note = "\n\nРегламент для этого предмета уже есть, новый текст заменит его." if current else ""
    await message.answer(
        f"Напишите регламент предмета «{html.escape(message.text)}» одним сообщением "
        "(домашние задания, сроки сдачи, требования). Студенты увидят его по кнопке "
        f"«Регламент».{note}",
        reply_markup=back_kb(),
    )


@router.message(Screen.rules_text, F.text == BTN_BACK)
async def rules_text_back(message: Message, state: FSMContext):
    await show_rules_subjects(message, state)


@router.message(Screen.rules_text, F.text)
async def rules_save(message: Message, state: FSMContext):
    if not await db_user_has_upload_rights(message.from_user.id):
        await message.answer("У вас больше нет прав старосты.")
        await go_main_menu(message, state)
        return
    data = await state.get_data()
    await db_set_rules(data["group_id"], data["rules_subject_id"],
                       message.text.strip(), message.from_user.id)
    await message.answer("Регламент сохранён. Теперь он показывается по кнопке «Регламент» "
                         f"у предмета «{html.escape(data['rules_subject_name'])}» в вашей группе.")
    await go_main_menu(message, state)


@router.message(Screen.waiting_group, F.text)
async def process_group(message: Message, state: FSMContext):
    group = await db_find_group(message.text)
    if group is None:
        await message.answer("Группа не найдена. Проверьте название и попробуйте ещё раз:")
        return
    await state.update_data(group_id=group["id"], group_name=group["name"])
    await message.answer(f"Группа {group['name']} найдена.")
    await go_main_menu(message, state)


@router.message(Screen.main_menu, F.text == BTN_FAQ)
async def menu_faq(message: Message, state: FSMContext):
    faq = await db_get_faq()
    text = "<b>Ответы на вопросы</b>\n\n" + "\n\n".join(
        f"<b>{i}. {html.escape(item['q'])}</b>\n{html.escape(item['a'])}"
        for i, item in enumerate(faq, 1)
    )
    text += ("\n\nНе нашли ответ? Напишите свой вопрос следующим сообщением, "
             "он уйдёт администратору.")
    await state.set_state(Screen.faq)
    await message.answer(text, reply_markup=back_kb())


@router.message(Screen.main_menu, F.text == BTN_SUBJECTS)
async def menu_subjects(message: Message, state: FSMContext):
    await go_subjects(message, state)


@router.message(Screen.main_menu, F.text == BTN_HEADMAN)
async def menu_headman(message: Message, state: FSMContext):
    await state.set_state(Screen.headman)
    await message.answer(
        "Введите ваши ФИО и группу одним сообщением.\n"
        "Например: <i>Иванов Иван Иванович, БПИ-231</i>",
        reply_markup=back_kb(),
    )


@router.message(Screen.faq, F.text == BTN_BACK)
async def faq_back(message: Message, state: FSMContext):
    await go_main_menu(message, state)


@router.message(Screen.faq, F.text)
async def faq_new_question(message: Message, state: FSMContext, bot: Bot):
    if not ADMIN_ID:
        await message.answer("Администратор бота не настроен, вопрос отправить нельзя.")
        await go_main_menu(message, state)
        return

    user = message.from_user
    author = f"@{user.username}" if user.username else user.full_name
    try:
        sent = await bot.send_message(
            ADMIN_ID,
            f"Новый вопрос от {html.escape(author)} (id {user.id}):\n\n"
            f"{html.escape(message.text)}\n\n"
            "Чтобы ответить, ответьте на это сообщение.\n"
            "Ответ, оканчивающийся на «!», попадёт в раздел «Ответы на вопросы» "
            "Без «!» ответ получит только автор вопроса.",
        )
    except TelegramAPIError:
        logging.exception("Не удалось отправить вопрос администратору")
        await message.answer("Не удалось отправить вопрос администратору. Попробуйте позже.")
        await go_main_menu(message, state)
        return

    await db_save_pending_question(user.id, message.text, sent.message_id)
    await message.answer(
        "Ваш вопрос отправлен администратору. Как только он ответит, вопрос и ответ "
        "появятся в разделе «Ответы на вопросы», а я пришлю вам уведомление."
    )
    await go_main_menu(message, state)


@router.message(Screen.headman, F.text == BTN_BACK)
async def headman_back(message: Message, state: FSMContext):
    await go_main_menu(message, state)


@router.message(Screen.headman, F.text)
async def headman_request(message: Message, state: FSMContext, bot: Bot):
    if not ADMIN_ID:
        await message.answer("Администратор бота не настроен, заявку отправить нельзя.")
        await go_main_menu(message, state)
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="Одобрить", callback_data=f"admin:approve:{message.from_user.id}")
    kb.button(text="Отклонить", callback_data=f"admin:reject:{message.from_user.id}")
    kb.adjust(2)
    await bot.send_message(
        ADMIN_ID,
        f"Заявка на права старосты\n"
        f"От: @{message.from_user.username} (id {message.from_user.id})\n"
        f"Данные: {message.text}",
        reply_markup=kb.as_markup(),
    )
    await message.answer("Заявка отправлена на модерацию администратору бота.")
    await go_main_menu(message, state)


@router.callback_query(F.data.startswith("admin:"))
async def admin_decision(call: CallbackQuery, bot: Bot):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Недостаточно прав", show_alert=True)
        return
    _, decision, user_id = call.data.split(":")
    user_id = int(user_id)
    if decision == "approve":
        await db_grant_headman_rights(user_id)
        await bot.send_message(user_id, "Ваша заявка одобрена: вам выданы права старосты.")
        await call.message.edit_text(call.message.text + "\n\nОдобрено")
    else:
        await bot.send_message(user_id, "Ваша заявка на права старосты отклонена.")
        await call.message.edit_text(call.message.text + "\n\nОтклонено")
    await call.answer()


@router.message(Screen.subjects, F.text == BTN_BACK)
async def subjects_back(message: Message, state: FSMContext):
    await go_main_menu(message, state)


@router.message(Screen.subjects, F.text)
async def choose_subject(message: Message, state: FSMContext):
    data = await state.get_data()
    subject_id = data["subjects_map"].get(message.text)
    if subject_id is None:
        await message.answer("Выберите предмет с помощью кнопок внизу.")
        return
    await state.update_data(subject_id=subject_id, subject_name=message.text)
    await go_actions(message, state)


@router.message(Screen.actions, F.text == BTN_BACK)
async def actions_back(message: Message, state: FSMContext):
    await go_subjects(message, state)


@router.message(Screen.actions, F.text == BTN_RULES)
async def act_rules(message: Message, state: FSMContext):
    data = await state.get_data()
    rules = await db_get_rules(data["group_id"], data["subject_id"])
    if not rules:
        await message.answer("Регламент для этого предмета пока не добавлен. "
                             "Староста может добавить его командой /rules.")
        return
    await message.answer(f"<b>Регламент: {html.escape(data['subject_name'])}</b>\n\n"
                         f"{html.escape(rules)}")


@router.message(Screen.actions, F.text == BTN_ASK)
async def act_ask(message: Message, state: FSMContext):
    await state.set_state(Screen.asking)
    await message.answer("Напишите свой вопрос по материалам предмета свободным текстом:",
                         reply_markup=back_kb())


@router.message(Screen.asking, F.text == BTN_BACK)
async def ask_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.asking, F.text)
async def process_question(message: Message, state: FSMContext):
    data = await state.get_data()
    wait = await message.answer("Ищу ответ в материалах...")
    fragments = await db_search_fragments(data["subject_id"], message.text)
    answer = await ml_generate_answer(message.text, fragments)
    await wait.edit_text(answer)


async def show_dates(message: Message, state: FSMContext, kind: str):
    data = await state.get_data()
    dates = await db_get_dates(data["group_id"], data["subject_id"], kind)
    await state.update_data(dates_kind=kind, dates_map={d["title"]: d["id"] for d in dates})
    await state.set_state(Screen.dates)
    title = "Лекции" if kind == "lectures" else "Конспекты"
    await message.answer(f"{title}\nВыберите дату (тему):",
                         reply_markup=list_kb([d["title"] for d in dates]))


@router.message(Screen.actions, F.text == BTN_LECTURES)
async def act_lectures(message: Message, state: FSMContext):
    await show_dates(message, state, "lectures")


@router.message(Screen.actions, F.text == BTN_NOTES)
async def act_notes(message: Message, state: FSMContext):
    await show_dates(message, state, "notes")


@router.message(Screen.dates, F.text == BTN_BACK)
async def dates_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.dates, F.text)
async def choose_date(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    item_id = data["dates_map"].get(message.text)
    if item_id is None:
        await message.answer("Выберите дату с помощью кнопок внизу.")
        return
    kind = data["dates_kind"]

    if kind == "lectures":
        video = await db_get_video(item_id)
        if video is None:
            await message.answer("Видео не найдено.")
            return
        try:
            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=STORAGE_CHANNEL_ID,
                message_id=video["channel_message_id"],
                caption=f"{video['kind']}: {video['title']}\n{video['lecture_date']:%d.%m.%Y}",
            )
        except TelegramAPIError:
            logging.exception("Не удалось переслать видео %s", item_id)
            await message.answer("Не удалось получить видео. Попробуйте позже.")
        return

    item = await db_get_lecture_or_note(data["subject_id"], kind, item_id)

    await message.answer(f"<b>{item['title']}</b>\n{item['text']}\n\n{item['url']}")
    if kind == "notes":
        doc = BufferedInputFile(item["text"].encode("utf-8"), filename=f"{item['title']}.txt")
        await message.answer_document(doc)


@router.message(Screen.actions, F.text == BTN_VIDEO)
async def act_video(message: Message, state: FSMContext):
    if not await db_user_has_upload_rights(message.from_user.id):
        await message.answer("Нет прав старосты или администратора.")
        return
    if not STORAGE_CHANNEL_ID:
        await message.answer("Канал-хранилище видео не настроен (STORAGE_CHANNEL_ID).")
        return
    await state.set_state(Screen.video)
    await message.answer("Отправьте видео лекции или практики:",
                         reply_markup=back_kb())


@router.message(Screen.video, F.text == BTN_BACK)
async def video_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.video, F.video)
async def receive_video(message: Message, state: FSMContext):
    await state.update_data(pending_msg_id=message.message_id,
                            pending_file_id=message.video.file_id)
    await state.set_state(Screen.video_title)
    await message.answer("Введите название лекции (практики), например: Типы данных",
                         reply_markup=back_kb())


@router.message(Screen.video)
async def video_wrong_type(message: Message):
    await message.answer("Пожалуйста, отправьте именно видео-файл.")


@router.message(Screen.video_title, F.text == BTN_BACK)
async def video_title_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.video_title, F.text)
async def video_title(message: Message, state: FSMContext):
    await state.update_data(pending_title=message.text.strip())
    await state.set_state(Screen.video_date)
    await message.answer("Введите дату занятия в формате ДД.ММ.ГГГГ, например 10.09.2026:",
                         reply_markup=back_kb())


@router.message(Screen.video_date, F.text == BTN_BACK)
async def video_date_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.video_date, F.text)
async def video_date(message: Message, state: FSMContext):
    try:
        lecture_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await message.answer("Неверный формат даты. Пример: 10.09.2026")
        return
    await state.update_data(pending_date=lecture_date.isoformat())
    await state.set_state(Screen.video_kind)
    await message.answer("Это лекция или практика?",
                         reply_markup=make_kb([[BTN_LECTURE, BTN_PRACTICE], [BTN_BACK]]))


@router.message(Screen.video_kind, F.text == BTN_BACK)
async def video_kind_back(message: Message, state: FSMContext):
    await go_actions(message, state)


@router.message(Screen.video_kind, F.text.in_({BTN_LECTURE, BTN_PRACTICE}))
async def video_kind(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    kind = message.text
    title = data["pending_title"]
    lecture_date = date.fromisoformat(data["pending_date"])

    try:
        sent = await bot.copy_message(
            chat_id=STORAGE_CHANNEL_ID,
            from_chat_id=message.chat.id,
            message_id=data["pending_msg_id"],
            caption=(f"{data['group_name']} | {data['subject_name']}\n"
                     f"{kind}: {title}\n{lecture_date:%d.%m.%Y}"),
        )
    except TelegramAPIError:
        logging.exception("Не удалось отправить видео в канал-хранилище")
        await message.answer("Не удалось сохранить видео в канал. Проверьте, что бот "
                             "добавлен в канал как администратор с правом публикации.")
        await go_actions(message, state)
        return

    video_id = await db_save_video(
        group_id=data["group_id"],
        subject_id=data["subject_id"],
        kind=kind,
        title=title,
        lecture_date=lecture_date,
        channel_message_id=sent.message_id,
        uploaded_by=message.from_user.id,
    )

    await ml_process_video(video_id, data["pending_file_id"], sent.message_id)

    await message.answer("Видео сохранено и передано на обработку. "
                         "Конспект появится после завершения транскрибации.")
    await go_actions(message, state)


@router.message(Screen.video_kind)
async def video_kind_wrong(message: Message):
    await message.answer("Выберите тип занятия кнопками внизу.")


async def main():
    logging.basicConfig(level=logging.INFO)
    if not BOT_TOKEN:
        raise RuntimeError("Не задана переменная окружения BOT_TOKEN")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())