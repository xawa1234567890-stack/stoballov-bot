import asyncio
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from openai import AsyncOpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = "man_937"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

AI_URL = "https://" + "models.github.ai" + "/inference"
PAY_URL = "https://" + "t.me/" + ADMIN_USERNAME

client = AsyncOpenAI(
    base_url=AI_URL,
    api_key=GITHUB_TOKEN,
)

users_db = {}

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📐 Математика"), KeyboardButton(text="✍️ Русский язык")],
        [KeyboardButton(text="🇬🇧 Английский язык"), KeyboardButton(text="📚 Все предметы ЦТ/ЦЭ")],
        [KeyboardButton(text="📝 Мини-тест РИКЗ"), KeyboardButton(text="💎 Купить безлимит")]
    ],
    resize_keyboard=True
)

SYSTEM_PROMPT = """
Ты — профессиональный репетитор из Беларуси по подготовке к ЦТ и ЦЭ (стандарты РИКЗ) по всем предметам (Математика, Русский, Английский, Физика, Химия, Биология, История Беларуси, Обществоведение).
Правила:
1. Точные науки: сначала дай четкий ответ, затем распиши пошаговое решение с формулами и укажи ловушки РИКЗ (ОДЗ, знаки, единицы СИ).
2. Языки: объясняй правила орфографии, пунктуации и грамматики строго по программам РБ. Выделяй верные буквы/слова и кратко поясняй.
3. Если ученик просит мини-тест — составь 3 задания в формате ЦТ с вариантами ответов и жди его ответа для проверки.
Отвечай понятно, дружелюбно, без воды.
"""

def get_user(user_id):
    if user_id not in users_db:
        users_db[user_id] = {
            "tries": 0,
            "vip": False,
            "history": [{"role": "system", "content": SYSTEM_PROMPT}]
        }
    return users_db[user_id]

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user = get_user(message.from_user.id)
    left = "Безлимит (VIP)" if user["vip"] else f"{max(0, 3 - user['tries'])} из 3"
    await message.answer(
        f"Привет, {message.from_user.first_name}! 🎓\n"
        f"Я **100 Баллов AI** — твой репетитор для подготовки к **ЦТ и ЦЭ**.\n\n"
        f"🎁 Бесплатных разборов осталось: **{left}**\n"
        f"Выбери предмет кнопкой ниже или сразу напиши задачу 👇",
        reply_markup=main_kb,
        parse_mode="Markdown"
    )

@dp.message(Command("vip"))
async def cmd_vip(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split()
        target_id = int(parts.pop())
        user = get_user(target_id)
        user["vip"] = True
        await message.answer(f"✅ Пользователю `{target_id}` активирован VIP-безлимит!", parse_mode="Markdown")
        await bot.send_message(target_id, "🎉 **Оплата подтверждена!** Вам открыт безлимитный доступ ко всем предметам на 30 дней!", parse_mode="Markdown")
    except Exception:
        await message.answer("Используйте формат: `/vip ID_ученика`", parse_mode="Markdown")

@dp.message(F.text == "💎 Купить безлимит")
async def buy_vip(message: types.Message):
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Написать для оплаты (35 BYN/мес)", url=PAY_URL)]
    ])
    await message.answer(
        f"🚀 **Безлимитный доступ к 100 Баллов AI на 30 дней**\n\n"
        f"✅ Разбор любых задач по всем предметам ЦТ и ЦЭ\n"
        f"✅ Объяснение всех ловушек РИКЗ\n"
        f"✅ Генерация тренировочных тестов 24/7\n\n"
        f"💰 Стоимость: **25 BYN** (дешевле одного занятия с репетитором).\n"
        f"Ваш ID для активации: `{message.from_user.id}`\n\n"
        f"Нажмите кнопку ниже, чтобы получить реквизиты (карта РБ / ЕРИП):",
        reply_markup=pay_kb,
        parse_mode="Markdown"
    )

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id)

    if not user["vip"] and user["tries"] >= 3 and user_id != ADMIN_ID:
        await buy_vip(message)
        return

    subjects = ["📐 Математика", "✍️ Русский язык", "🇬🇧 Английский язык", "📚 Все предметы ЦТ/ЦЭ", "📝 Мини-тест РИКЗ"]
    if message.text in subjects:
        user["history"].append({"role": "user", "content": f"Я выбрал раздел: {message.text}. Поприветствуй и предложи прислать задание или начать тест."})
    else:
        if not user["vip"] and user_id != ADMIN_ID:
            user["tries"] += 1
        user["history"].append({"role": "user", "content": message.text})

    while len(user["history"]) > 11:
        user["history"].pop(1)

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response = await client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=user["history"],
            temperature=0.6
        )
        first_choice = next(iter(response.choices))
        reply = first_choice.message.content
        user["history"].append({"role": "assistant", "content": reply})
        await message.answer(reply)
    except Exception as e:
        print("Ошибка API:", e)
        await message.answer("⏳ Нейросеть сейчас обрабатывает много запросов. Попробуйте отправить задание еще раз через 5 секунд!")

async def health_check(request):
    return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
