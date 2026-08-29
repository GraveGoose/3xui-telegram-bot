import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from panel_api import XUIPanel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else []))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
panel = XUIPanel(
    base_url=os.getenv("PANEL_URL"),
    username=os.getenv("PANEL_USERNAME"),
    password=os.getenv("PANEL_PASSWORD")
)


class CreateClientStates(StatesGroup):
    choosing_inbound = State()
    entering_email = State()
    entering_limit_ip = State()
    entering_expiry_days = State()
    entering_traffic_gb = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer(
        "👋 Добро пожаловать в 3x-ui Bot!\n\n"
        "Команды:\n"
        "/inbounds — список инбаундов\n"
        "/create — создать клиента\n"
        "/status — статус панели"
    )


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    ok = await panel.login()
    if ok:
        await message.answer("✅ Панель доступна, авторизация успешна.")
    else:
        await message.answer("❌ Не удалось подключиться к панели. Проверьте настройки .env")


@dp.message(Command("inbounds"))
async def cmd_inbounds(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("⏳ Получаю список инбаундов...")
    inbounds = await panel.get_inbounds()
    if not inbounds:
        await message.answer("❌ Не удалось получить инбаунды или список пуст.")
        return
    text = "📋 <b>Список инбаундов:</b>\n\n"
    for ib in inbounds:
        status = "🟢" if ib.get("enable") else "🔴"
        text += (
            f"{status} <b>ID {ib['id']}</b> | {ib.get('remark', 'без имени')}\n"
            f"   Протокол: <code>{ib.get('protocol', '?')}</code>\n"
            f"   Порт: <code>{ib.get('port', '?')}</code>\n"
            f"   Клиентов: {ib.get('clientStats', []) and len(ib.get('clientStats', [])) or 0}\n\n"
        )
    await message.answer(text, parse_mode="HTML")


@dp.message(Command("create"))
async def cmd_create(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён.")
        return
    await message.answer("⏳ Получаю инбаунды...")
    inbounds = await panel.get_inbounds()
    if not inbounds:
        await message.answer("❌ Не удалось получить инбаунды.")
        return

    buttons = []
    for ib in inbounds:
        if not ib.get("enable"):
            continue
        label = f"ID {ib['id']} | {ib.get('remark', '?')} | {ib.get('protocol', '?')} :{ib.get('port', '?')}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"sel_inbound:{ib['id']}")])

    if not buttons:
        await message.answer("⚠️ Нет активных инбаундов.")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("🔌 Выберите инбаунд для нового клиента:", reply_markup=kb)
    await state.set_state(CreateClientStates.choosing_inbound)


@dp.callback_query(F.data.startswith("sel_inbound:"), CreateClientStates.choosing_inbound)
async def cb_select_inbound(callback: types.CallbackQuery, state: FSMContext):
    inbound_id = int(callback.data.split(":")[1])
    await state.update_data(inbound_id=inbound_id)
    tg_id = callback.from_user.id
    await state.update_data(tg_user_id=tg_id)
    await callback.message.edit_text(
        f"✅ Инбаунд ID <b>{inbound_id}</b> выбран.\n\n"
        f"Ваш Telegram ID: <code>{tg_id}</code>\n\n"
        "Введите <b>email/имя</b> для клиента (латиница, без пробелов):",
        parse_mode="HTML"
    )
    await state.set_state(CreateClientStates.entering_email)
    await callback.answer()


@dp.message(CreateClientStates.entering_email)
async def process_email(message: types.Message, state: FSMContext):
    email = message.text.strip().lower().replace(" ", "_")
    if not email.isalnum() and not all(c.isalnum() or c in "_-." for c in email):
        await message.answer("⚠️ Используйте только латинские буквы, цифры, дефис и точку.")
        return
    await state.update_data(email=email)
    await message.answer("🔢 Лимит одновременных IP-подключений (0 = без ограничений):")
    await state.set_state(CreateClientStates.entering_limit_ip)


@dp.message(CreateClientStates.entering_limit_ip)
async def process_limit_ip(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text.strip())
        if limit < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите целое число >= 0.")
        return
    await state.update_data(limit_ip=limit)
    await message.answer("📅 Срок действия в днях (0 = без ограничения):")
    await state.set_state(CreateClientStates.entering_expiry_days)


@dp.message(CreateClientStates.entering_expiry_days)
async def process_expiry(message: types.Message, state: FSMContext):
    try:
        days = int(message.text.strip())
        if days < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите целое число >= 0.")
        return
    await state.update_data(expiry_days=days)
    await message.answer("📦 Лимит трафика в ГБ (0 = без ограничения):")
    await state.set_state(CreateClientStates.entering_traffic_gb)


@dp.message(CreateClientStates.entering_traffic_gb)
async def process_traffic(message: types.Message, state: FSMContext):
    try:
        gb = float(message.text.strip())
        if gb < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число >= 0.")
        return
    await state.update_data(traffic_gb=gb)

    data = await state.get_data()
    await message.answer("⏳ Создаю клиента...")

    result = await panel.add_client(
        inbound_id=data["inbound_id"],
        email=data["email"],
        tg_id=str(data["tg_user_id"]),
        limit_ip=data["limit_ip"],
        expiry_days=data["expiry_days"],
        traffic_gb=data["traffic_gb"],
    )

    if result and result.get("success"):
        # Получаем ссылку для подключения
        link = await panel.get_client_link(data["inbound_id"], data["email"])
        text = (
            f"✅ <b>Клиент создан!</b>\n\n"
            f"Email: <code>{data['email']}</code>\n"
            f"Инбаунд ID: <code>{data['inbound_id']}</code>\n"
            f"Telegram ID: <code>{data['tg_user_id']}</code>\n"
        )
        if link:
            text += f"\n🔗 <b>Ссылка подключения:</b>\n<code>{link}</code>"
        await message.answer(text, parse_mode="HTML")
    else:
        err = result.get("msg", "Неизвестная ошибка") if result else "Нет ответа от панели"
        await message.answer(f"❌ Ошибка создания клиента: {err}")

    await state.clear()


async def main():
    logger.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
