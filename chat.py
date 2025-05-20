import os
import logging
import asyncio
import concurrent.futures
import html
import base64
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from openai import OpenAI

# 🔑 Получение API ключей из переменных окружения
API_KEY = os.getenv("OPENROUTER_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
)

available_models = [
    "deepseek/deepseek-r1:free",
]

user_model_choice = {}

def ask_ai(model, prompt):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024
        )
        return model, response.choices[0].message.content
    except Exception as e:
        return model, f"[Ошибка]: {e}"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    user_id = update.message.from_user.id
    model = user_model_choice.get(user_id, available_models[0])

    await update.message.reply_text(
        f"🕐 Отправляю в модель:\n<code>{html.escape(model)}</code>",
        parse_mode="HTML"
    )

    loop = asyncio.get_running_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = loop.run_in_executor(executor, ask_ai, model, prompt)
        model, answer = await future

    await update.message.reply_text(
        f"🧠 <b>{html.escape(model)}</b> ответила:\n{html.escape(answer)}",
        parse_mode='HTML'
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    model = user_model_choice.get(user_id, available_models[0])

    if "vision" not in model:
        await update.message.reply_text("❌ Выбранная модель не поддерживает изображение.")
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_path = await file.download_to_drive()

    await update.message.reply_text(
        f"📷 Фото получено. Отправляю в модель:\n<code>{html.escape(model)}</code>",
        parse_mode="HTML"
    )

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{encoded}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": "Что на изображении?"},
                    {"type": "image_url", "image_url": {"url": data_url}}
                ]}
            ],
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        await update.message.reply_text(
            f"🧠 <b>{html.escape(model)}</b> ответила:\n{html.escape(answer)}",
            parse_mode="HTML"
        )

    except Exception as e:
        await update.message.reply_text(f"[Ошибка при обработке изображения]: {e}")

async def choose_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(model, callback_data=f"model|{model}")]
        for model in available_models
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)

async def handle_model_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("model|"):
        model = data.split("|", 1)[1]
        user_id = query.from_user.id
        user_model_choice[user_id] = model
        await query.edit_message_text(
            f"✅ Вы выбрали модель:\n<code>{html.escape(model)}</code>",
            parse_mode="HTML"
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📍 Выбрать модель", callback_data="open_model_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Привет! Просто напишите сообщение, и я отправлю его выбранной ИИ-модели.",
        reply_markup=reply_markup
    )

async def open_model_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = [
        [InlineKeyboardButton(model, callback_data=f"model|{model}")]
        for model in available_models
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите модель:", reply_markup=reply_markup)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("models", choose_model))
    app.add_handler(CallbackQueryHandler(handle_model_choice, pattern=r"^model\|"))
    app.add_handler(CallbackQueryHandler(open_model_menu, pattern="open_model_menu"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("✅ Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
