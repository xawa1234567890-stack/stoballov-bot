import asyncio
import os
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
# Ваш ID (8866302496)
ADMIN_ID = int(os.getenv("ADMIN_ID", "8866302496")) 

if not BOT_TOKEN or not GITHUB_TOKEN:
    raise ValueError("Не заданы BOT_TOKEN или GITHUB_TOKEN!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

client = AsyncOpenAI(
    base_url="https://models.github.ai/inference",
    api_key=GITHUB_TOKEN,
    timeout=60.0,
    max_retries=2
)

SYSTEM_PROMPT = """Ты — ИИ-репетитор "100 Баллов AI". Твоя специализация — подготовка к ЦТ и ЦЭ (Беларусь) по математике, русскому и английскому языкам.
Твои правила:
1. Решай задачи по строгим стандартам РИКЗ.
2. Объясняй правила и указывай на типичные "ловушки" в заданиях.
3. Если пользователь просит, составляй тренировочные тесты.
4. Общайся дружелюбно, мотивируй ученика.
5. Структурируй ответ: сначала краткий правильный ответ, затем подробное объяснение."""

DB_NAME = "users.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # ИЗМЕНЕНИЕ: Теперь по умолчанию выдается 1 запрос
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, requests_left INTEGER DEFAULT 1)")
        await db.commit()

async def get_user_limit(user_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT requests_left FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row is None:
                # ИЗМЕНЕНИЕ: При первом входе даем 1 запрос
                await db.execute("INSERT INTO users (user_id, requests_left) VALUES (?, 1)", (user_id,))
                await db.commit()
                return 1
            return row[0]

async def decrement_limit(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET requests_left = requests_left - 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def grant_unlimited(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, requests_left) VALUES (?, 9999) 
            ON CONFLICT(user_id) DO UPDATE SET requests_left = 9999
        """, (user_id,))
        await db.commit()

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="📐 Математика")
    builder.button(text="✍️ Русский язык")
    builder.button(text="🇬🇧 Английский язык")
    builder.button(text="📚 Все предметы ЦТ/ЦЭ")
    builder.button(text="📝 Мини-тест РИКЗ")
    builder.button(text="💎 Купить безлимит")
    builder.adjust(2, 2, 2) 
    return builder.as_markup(resize_keyboard=True)

def get_payment_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Написать для оплаты (35 BYN/мес)", url="https://t.me/man_937")
    return builder.as_markup()

async def send_payment_info(message_or_call, user_id: int):
    text = (
        "🚀 <b>Безлимитный доступ к 100 Баллов AI на 30 дней</b>\n\n"
        "✅ Разбор любых задач по всем предметам ЦТ и ЦЭ\n"
        "✅ Объяснение всех ловушек РИКЗ\n"
        "✅ Генерация тренировочных тестов 24/7\n\n"
        "💰 <b>Стоимость: 35 BYN</b> (дешевле одного занятия с репетитором).\n"
        f"<b>Ваш ID для активации:</b> <code>{user_id}</code>\n\n"
        "Нажмите кнопку ниже, чтобы получить реквизиты (карта РБ / ЕРИП):"
    )
    
    if isinstance(message_or_call, types.CallbackQuery):
        await message_or_call.message.answer(text, reply_markup=get_payment_keyboard(), parse_mode="HTML")
        await message_or_call.answer()
    else:
        await message_or_call.answer(text, reply_markup=get_payment_keyboard(), parse_mode="HTML")

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    limit = await get_user_limit(user_id)
    
    # ИЗМЕНЕНИЕ: Текст теперь говорит про 1 запрос
    welcome_text = (
        f"Привет, {message.from_user.first_name}! 🎓\n"
        f"Я 100 Баллов AI — твой репетитор для подготовки к ЦТ и ЦЭ.\n\n"
        f"🎁 Бесплатных разборов осталось: <b>{limit} из 1</b>\n"
        f"Выбери предмет кнопкой ниже или сразу напиши задачу 👇"
    )
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.callback_query(F.data == "buy_unlimited")
async def process_buy_callback(callback: types.CallbackQuery):
    await send_payment_info(callback, callback.from_user.id)

@dp.message(Command("grant"))
async def cmd_grant(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return 
    
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("⚠️ Использование: <code>/grant ID_клиента</code>", parse_mode="HTML")
        return
    
    client_id = int(args[1])
    await grant_unlimited(client_id)
    await message.answer(f"✅ Клиенту <code>{client_id}</code> успешно выдан безлимит!", parse_mode="HTML")
    
    try:
        await bot.send_message(client_id, "🎉 Ура! Ваш безлимитный доступ активирован. Можете задавать любые вопросы по ЦТ и ЦЭ!")
    except Exception:
        pass

@dp.message(Command("check"))
async def cmd_check(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("⚠️ Использование: <code>/check ID_клиента</code>", parse_mode="HTML")
        return
        
    client_id = int(args[1])
    limit = await get_user_limit(client_id)
    await message.answer(f"📊 У клиента <code>{client_id}</code> осталось запросов: <b>{limit}</b>", parse_mode="HTML")

@dp.message(F.text)
async def handle_question(message: types.Message):
    user_id = message.from_user.id
    text = message.text

    if text == "💎 Купить безлимит":
        await send_payment_info(message, user_id)
        return

    if text == "📝 Мини-тест РИКЗ":
        await message.answer("Отправь мне название предмета для мини-теста (например: 'Сделай мини-тест по математике').")
        return
        
    if text in ["📐 Математика", "✍️ Русский язык", "🇬🇧 Английский язык", "📚 Все предметы ЦТ/ЦЭ"]:
        await message.answer(f"Отлично! Выбран раздел: <b>{text}</b>. Отправь мне свою задачу или вопрос.", parse_mode="HTML")
        return

    limit = await get_user_limit(user_id)
    if limit <= 0:
        await message.answer(
            "😔 У тебя закончились бесплатные разборы.\n"
            "Купи безлимит, чтобы продолжить подготовку!",
            reply_markup=get_payment_keyboard()
        )
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            max_tokens=1500,
            temperature=0.5
        )
        
        answer = response.choices[0].message.content
        
        await decrement_limit(user_id)
        new_limit = limit - 1
        
        if new_limit <= 0:
            answer += "\n\n⚠️ <b>Это был твой единственный бесплатный разбор. Купи безлимит, чтобы продолжить!</b>"
            await message.answer(answer, parse_mode="HTML")
            await message.answer("👇", reply_markup=get_payment_keyboard())
        else:
            # На случай, если у пользователя уже есть купленный безлимит
            answer += f"\n\n🎁 <i>Осталось бесплатных разборов: {new_limit}</i>"
            await message.answer(answer, parse_mode="HTML")

    except TelegramBadRequest:
        await message.answer(answer) 
    except Exception as e:
        logging.error(f"Ошибка API: {e}")
        await message.answer("⚠️ Произошла ошибка на сервере ИИ. Попробуй еще раз.")

async def main():
    await init_db()
    logging.info("🚀 Бот '100 Баллов AI' успешно запущен!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
