import os
import asyncio
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import Message
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
PASSWORD = "Sobirjon2005"
DB_NAME = "cloud.db"

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

authorized_users = set()

class AuthState(StatesGroup):
    waiting_password = State()

async def create_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_id TEXT,
                file_name TEXT,
                category TEXT,
                size INTEGER,
                date TEXT
            )
        """)
        await db.commit()

async def save_file(user_id, file_id, file_name, category, size):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO files (user_id, file_id, file_name, category, size, date) VALUES (?,?,?,?,?,?)",
            (user_id, file_id, file_name, category, size, datetime.now().strftime("%Y-%m-%d %H:%M"))
        )
        await db.commit()

def is_auth(user_id):
    return user_id in authorized_users

@dp.message_handler(commands=["start"])
async def start(message: Message):
    if is_auth(message.from_user.id):
        await message.answer(
            "☁️ Shaxsiy Bulut Xotirangiz\n\n"
            "Fayl yuboring — avtomatik saqlanadi!\n\n"
            "/list — barcha fayllar\n"
            "/videos — videolar\n"
            "/photos — rasmlar\n"
            "/apps — APK va IPA\n"
            "/bysize — hajm boyicha\n"
            "/bytime — vaqt boyicha\n"
            "/search nom — qidirish"
        )
    else:
        await message.answer("🔐 Parolni kiriting:")
        await AuthState.waiting_password.set()

@dp.message_handler(state=AuthState.waiting_password)
async def check_password(message: Message, state: FSMContext):
    if message.text == PASSWORD:
        authorized_users.add(message.from_user.id)
        await state.finish()
        await message.answer("✅ Xush kelibsiz!\n\n/start — menyuni ko'rish")
    else:
        await message.answer("❌ Noto'g'ri parol! Qayta urinib ko'ring:")

@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_video(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    v = message.video
    size_mb = round(v.file_size / 1024 / 1024, 2)
    name = v.file_name or f"video_{v.file_id[:8]}.mp4"
    await save_file(message.from_user.id, v.file_id, name, "video", v.file_size)
    await message.answer(f"🎬 Saqlandi!\n{name}\n{size_mb} MB")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    p = message.photo[-1]
    size_mb = round(p.file_size / 1024 / 1024, 2)
    name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await save_file(message.from_user.id, p.file_id, name, "photo", p.file_size)
    await message.answer(f"🖼️ Saqlandi!\n{name}\n{size_mb} MB")

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    d = message.document
    size_mb = round(d.file_size / 1024 / 1024, 2)
    name = d.file_name or "nomsiz_fayl"
    ext = name.split(".")[-1].lower()

    if ext == "apk":
        category, icon = "apk", "🤖"
    elif ext == "ipa":
        category, icon = "ipa", "🍎"
    elif ext in ["mp4", "mov", "avi", "mkv"]:
        category, icon = "video", "🎬"
    elif ext in ["jpg", "jpeg", "png", "gif"]:
        category, icon = "photo", "🖼️"
    else:
        category, icon = "other", "📄"

    await save_file(message.from_user.id, d.file_id, name, category, d.file_size)
    await message.answer(f"{icon} Saqlandi!\n{name}\n{size_mb} MB\n{category.upper()}")

async def show_files(message, where="", order="date DESC"):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    uid = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        q = f"SELECT file_id, file_name, category, size, date FROM files WHERE user_id=? {where} ORDER BY {order}"
        async with db.execute(q, (uid,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("📭 Hozircha fayl yoq.")
        return

    icons = {"video":"🎬","photo":"🖼️","apk":"🤖","ipa":"🍎","other":"📄"}
    text = ""
    for file_id, name, cat, size, date in rows:
        mb = round(size / 1024 / 1024, 2)
        text += f"{icons.get(cat,'📄')} {name}\n{mb} MB | {date}\n\n"
    await message.answer(text[:4000])

@dp.message_handler(commands=["list"])
async def cmd_list(message: Message):
    await show_files(message)

@dp.message_handler(commands=["videos"])
async def cmd_videos(message: Message):
    await show_files(message, "AND category='video'")

@dp.message_handler(commands=["photos"])
async def cmd_photos(message: Message):
    await show_files(message, "AND category='photo'")

@dp.message_handler(commands=["apps"])
async def cmd_apps(message: Message):
    await show_files(message, "AND category IN ('apk','ipa')")

@dp.message_handler(commands=["bysize"])
async def cmd_bysize(message: Message):
    await show_files(message, order="size DESC")

@dp.message_handler(commands=["bytime"])
async def cmd_bytime(message: Message):
    await show_files(message, order="date DESC")

@dp.message_handler(commands=["search"])
async def cmd_search(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /search fayl_nomi")
        return
    keyword = f"%{args[1]}%"
    uid = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT file_name, category, size, date FROM files WHERE user_id=? AND file_name LIKE ?",
            (uid, keyword)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("🔍 Topilmadi.")
        return

    text = ""
    for name, cat, size, date in rows:
        mb = round(size / 1024 / 1024, 2)
        text += f"📁 {name}\n{mb} MB | {date}\n\n"
    await message.answer(text[:4000])

async def on_startup(_):
    await create_db()
    print("Bot ishga tushdi!")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)
