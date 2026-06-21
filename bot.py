import asyncio
import aiosqlite
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, Document, PhotoSize
from aiogram.filters import CommandStart, Command

BOT_TOKEN = "SIZNING_TOKEN"
DB_NAME = "cloud.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ─── DATABASE ───────────────────────────────────────
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

# ─── START ──────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "☁️ <b>Shaxsiy Bulut Xotirangiz</b>\n\n"
        "📤 Fayl yuboring — avtomatik saqlanadi!\n\n"
        "📋 Buyruqlar:\n"
        "/list — barcha fayllar\n"
        "/videos — videolar\n"
        "/photos — rasmlar\n"
        "/apps — APK / IPA fayllar\n"
        "/bysize — hajm bo'yicha saralash\n"
        "/bytime — vaqt bo'yicha saralash\n"
        "/search nom — qidirish",
        parse_mode="HTML"
    )

# ─── FAYL QABUL QILISH ──────────────────────────────
@dp.message(F.video)
async def handle_video(message: Message):
    v = message.video
    size_mb = round(v.file_size / 1024 / 1024, 2)
    name = v.file_name or f"video_{v.file_id[:8]}.mp4"
    await save_file(message.from_user.id, v.file_id, name, "video", v.file_size)
    await message.answer(f"🎬 Video saqlandi!\n📁 {name}\n💾 {size_mb} MB")

@dp.message(F.photo)
async def handle_photo(message: Message):
    p = message.photo[-1]  # eng yuqori sifat
    size_mb = round(p.file_size / 1024 / 1024, 2)
    name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await save_file(message.from_user.id, p.file_id, name, "photo", p.file_size)
    await message.answer(f"🖼️ Rasm saqlandi!\n📁 {name}\n💾 {size_mb} MB")

@dp.message(F.document)
async def handle_document(message: Message):
    d = message.document
    size_mb = round(d.file_size / 1024 / 1024, 2)
    name = d.file_name or "nomsiz_fayl"
    ext = name.split(".")[-1].lower()

    if ext == "apk":
        category = "apk"
        icon = "🤖"
    elif ext == "ipa":
        category = "ipa"
        icon = "🍎"
    elif ext in ["mp4", "mov", "avi", "mkv"]:
        category = "video"
        icon = "🎬"
    elif ext in ["jpg", "jpeg", "png", "gif", "webp"]:
        category = "photo"
        icon = "🖼️"
    else:
        category = "other"
        icon = "📄"

    await save_file(message.from_user.id, d.file_id, name, category, d.file_size)
    await message.answer(f"{icon} Saqlandi!\n📁 {name}\n💾 {size_mb} MB\n🏷️ {category.upper()}")

# ─── RO'YXATLAR ─────────────────────────────────────
async def show_files(message, where_clause="", order="date DESC"):
    uid = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        query = f"SELECT file_id, file_name, category, size, date FROM files WHERE user_id=? {where_clause} ORDER BY {order}"
        async with db.execute(query, (uid,)) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("📭 Hozircha fayl yo'q.")
        return

    text = ""
    icons = {"video":"🎬","photo":"🖼️","apk":"🤖","ipa":"🍎","other":"📄"}
    for file_id, name, cat, size, date in rows:
        mb = round(size / 1024 / 1024, 2)
        icon = icons.get(cat, "📄")
        text += f"{icon} <b>{name}</b>\n💾 {mb} MB | 🕐 {date}\n\n"

    await message.answer(text[:4000], parse_mode="HTML")

@dp.message(Command("list"))
async def cmd_list(message: Message):
    await show_files(message)

@dp.message(Command("videos"))
async def cmd_videos(message: Message):
    await show_files(message, "AND category='video'")

@dp.message(Command("photos"))
async def cmd_photos(message: Message):
    await show_files(message, "AND category IN ('photo')")

@dp.message(Command("apps"))
async def cmd_apps(message: Message):
    await show_files(message, "AND category IN ('apk','ipa')")

@dp.message(Command("bysize"))
async def cmd_bysize(message: Message):
    await show_files(message, order="size DESC")

@dp.message(Command("bytime"))
async def cmd_bytime(message: Message):
    await show_files(message, order="date DESC")

# ─── QIDIRISH ───────────────────────────────────────
@dp.message(Command("search"))
async def cmd_search(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("❓ Misol: /search video_nomi")
        return
    keyword = f"%{args[1]}%"
    uid = message.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT file_id, file_name, category, size, date FROM files WHERE user_id=? AND file_name LIKE ?",
            (uid, keyword)
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await message.answer("🔍 Topilmadi.")
        return

    text = ""
    for file_id, name, cat, size, date in rows:
        mb = round(size / 1024 / 1024, 2)
        text += f"📁 <b>{name}</b>\n💾 {mb} MB | 🕐 {date}\n\n"
    await message.answer(text[:4000], parse_mode="HTML")

# ─── MAIN ───────────────────────────────────────────
async def main():
    await create_db()
    print("Bot ishga tushdi ✅")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
