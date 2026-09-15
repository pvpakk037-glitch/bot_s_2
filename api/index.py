import os
import logging
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update)

# ----------------- НАСТРОЙКИ (берутся из Vercel) -----------------
TOKEN = os.getenv("BOT_TOKEN", "")
# Используем int() потому что из переменных среды приходят строки
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
# -----------------------------------------------------------------

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
app = FastAPI()

SEEN_ALBUMS = set()

KEYBOARD = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="В тгк 📢", callback_data="publish"),
            InlineKeyboardButton(text="Не пересылать ❌", callback_data="reject")
        ]
    ]
)


def build_admin_text(content_text: str | None) -> str:
    text = "👤 <b>Вам пришло новое сообщение:</b>"
    if content_text:
        safe_content = html.quote(content_text)
        text += f"\n\n<code>{safe_content}</code>"
    return text


def extract_original_text(html_text: str | None) -> str | None:
    if html_text and "<code>" in html_text and "</code>" in html_text:
        return html_text.split("<code>")[1].split("</code>")[0]
    return None


@dp.message(CommandStart())
async def cmd_start(message: Message):
    await message.reply(
        "Здравствуйте, официальный бот https://t.me/nsk217s. "
        "Отправляйте свой пост (текст, фото или видео по одному), и он попадет в канал!"
    )


@dp.message(F.media_group_id)
async def reject_album(message: Message):
    group_id = message.media_group_id
    if group_id not in SEEN_ALBUMS:
        SEEN_ALBUMS.add(group_id)
        if len(SEEN_ALBUMS) > 50:
            SEEN_ALBUMS.clear()
        await message.answer(
            "⚠️ Бот принимает только текст, фото и видео (по 1 фото/видео за раз).")


@dp.message(F.text)
async def handle_text(message: Message):
    await message.answer("Отлично! Сообщение передано админу.")
    final_text = build_admin_text(message.text)
    await bot.send_message(chat_id=ADMIN_ID, text=final_text, reply_markup=KEYBOARD)


@dp.message(F.photo)
async def handle_photo(message: Message):
    await message.answer("Отлично! Фото передано админу.")
    final_text = build_admin_text(message.caption)
    await bot.send_photo(chat_id=ADMIN_ID, photo=message.photo[-1].file_id, caption=final_text, reply_markup=KEYBOARD)


@dp.message(F.video)
async def handle_video(message: Message):
    await message.answer("Отлично! Видео передано админу.")
    final_text = build_admin_text(message.caption)
    await bot.send_video(chat_id=ADMIN_ID, video=message.video.file_id, caption=final_text, reply_markup=KEYBOARD)


@dp.callback_query(F.data == "reject")
async def reject_post(callback: CallbackQuery):
    await callback.answer("❌ Пост отклонён!", show_alert=False)
    await callback.message.edit_reply_markup(reply_markup=None)


@dp.callback_query(F.data == "publish")
async def publish_to_channel(callback: CallbackQuery):
    msg = callback.message
    clean_text = extract_original_text(msg.html_text)

    try:
        if msg.photo:
            await bot.send_photo(chat_id=CHANNEL_ID, photo=msg.photo[-1].file_id, caption=clean_text)
        elif msg.video:
            await bot.send_video(chat_id=CHANNEL_ID, video=msg.video.file_id, caption=clean_text)
        elif msg.text:
            await bot.send_message(chat_id=CHANNEL_ID, text=clean_text)

        await callback.answer("✅ Успешно опубликовано в канал!", show_alert=False)
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await callback.answer("❌ Ошибка публикации. Проверьте права бота.", show_alert=True)


@dp.message()
async def handle_other_types(message: Message):
    await message.answer("⚠️ Бот принимает только текст, фото и видео.")


# =================================================================
# FastAPI ЭНДПОИНТЫ ДЛЯ VERCEL
# =================================================================

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    """Сюда Telegram будет присылать обновления"""
    try:
        update_data = await request.json()
        update = Update(**update_data)
        await dp.feed_update(bot, update)
    except Exception as e:
        logging.error(f"Ошибка при обработке обновления: {e}")

    return {"status": "ok"}


@app.get("/set_webhook")
async def set_webhook(request: Request):
    """Секретная ссылка для привязки бота к Vercel"""
    # request.base_url автоматически получает адрес вашего Vercel проекта (например https://my-bot.vercel.app/)
    url = f"{request.base_url}api/webhook"

    # Говорим Telegram'у присылать все сообщения на этот URL
    success = await bot.set_webhook(url=url, drop_pending_updates=True)

    return {
        "status": "ok",
        "webhook_url_set": url,
        "success": success
    }
