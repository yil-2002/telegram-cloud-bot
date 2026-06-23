import os
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
                date TEXT,
                folder TEXT DEFAULT 'umumiy',
                pinned INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                date TEXT
            )
        """)
        await db.commit()

async def save_file(user_id, file_id, file_name, category, size):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO files (user_id, file_id, file_name, category, size, date, folder, pinned) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, file_id, file_name, category, size, datetime.now().strftime("%Y-%m-%d %H:%M"), "umumiy", 0)
        )
        await db.commit()

def is_auth(user_id):
    return user_id in authorized_users

def get_icon(cat):
    return {"video":"ð¬","photo":"ð¼ï¸","apk":"ð¤","ipa":"ð"}.get(cat, "ð")

async def send_file(chat_id, file_id, cat, caption):
    try:
        if cat == "video":
            await bot.send_video(chat_id, file_id, caption=caption)
        elif cat == "photo":
            await bot.send_photo(chat_id, file_id, caption=caption)
        else:
            await bot.send_document(chat_id, file_id, caption=caption)
    except:
        await bot.send_message(chat_id, caption)

# âââ AUTH âââââââââââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["start"])
async def start(message: Message):
    if is_auth(message.from_user.id):
        await message.answer(
            "âï¸ Shaxsiy Bulut Xotirangiz\n\n"
            "ð¤ Fayl yuboring â saqlanadi!\n\n"
            "ð Asosiy:\n"
            "/list â barcha fayllar\n"
            "/videos â videolar\n"
            "/photos â rasmlar\n"
            "/apps â APK va IPA\n"
            "/bysize â hajm boyicha\n"
            "/bytime â vaqt boyicha\n"
            "/search nom â qidirish\n"
            "/delete nom â o'chirish\n\n"
            "ð Papkalar:\n"
            "/newfolder nom â papka yaratish\n"
            "/folders â papkalar ro'yxati\n"
            "/folder nom â papka ichini ko'rish\n"
            "/moveto fayl|papka â ko'chirish\n\n"
            "ð Muhim:\n"
            "/pin nom â muhim belgilash\n"
            "/unpin nom â belgini olish\n"
            "/pinned â muhim fayllar\n\n"
            "ð /stats â statistika"
        )
    else:
        await message.answer("ð Parolni kiriting:")
        await AuthState.waiting_password.set()

@dp.message_handler(state=AuthState.waiting_password)
async def check_password(message: Message, state: FSMContext):
    if message.text == PASSWORD:
        authorized_users.add(message.from_user.id)
        await state.finish()
        await message.answer("â Xush kelibsiz!\n\n/start â menyuni ko'rish")
    else:
        await message.answer("â Noto'g'ri parol!")

# âââ FAYL QABUL âââââââââââââââââââââââââââââââââââââ
@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_video(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    v = message.video
    size_mb = round(v.file_size / 1024 / 1024, 2)
    name = v.file_name or f"video_{v.file_id[:8]}.mp4"
    await save_file(message.from_user.id, v.file_id, name, "video", v.file_size)
    await message.answer(f"ð¬ Saqlandi!\n{name}\n{size_mb} MB")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    p = message.photo[-1]
    size_mb = round(p.file_size / 1024 / 1024, 2)
    name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await save_file(message.from_user.id, p.file_id, name, "photo", p.file_size)
    await message.answer(f"ð¼ï¸ Saqlandi!\n{name}\n{size_mb} MB")

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    d = message.document
    size_mb = round(d.file_size / 1024 / 1024, 2)
    name = d.file_name or "nomsiz_fayl"
    ext = name.split(".")[-1].lower()
    if ext == "apk":
        category, icon = "apk", "ð¤"
    elif ext == "ipa":
        category, icon = "ipa", "ð"
    elif ext in ["mp4", "mov", "avi", "mkv"]:
        category, icon = "video", "ð¬"
    elif ext in ["jpg", "jpeg", "png", "gif"]:
        category, icon = "photo", "ð¼ï¸"
    else:
        category, icon = "other", "ð"
    await save_file(message.from_user.id, d.file_id, name, category, d.file_size)
    await message.answer(f"{icon} Saqlandi!\n{name}\n{size_mb} MB")

# âââ RO'YXAT ââââââââââââââââââââââââââââââââââââââââ
async def show_files(message, where="", order="date DESC", params=()):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    async with aiosqlite.connect(DB_NAME) as db:
        q = f"SELECT file_id, file_name, category, size, date, folder, pinned FROM files WHERE 1=1 {where} ORDER BY {order}"
        async with db.execute(q, params) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await message.answer("ð­ Hozircha fayl yoq.")
        return
    for file_id, name, cat, size, date, folder, pinned in rows:
        mb = round(size / 1024 / 1024, 2)
        pin = "ð " if pinned else ""
        caption = f"{pin}{get_icon(cat)} {name}\nð¾ {mb} MB | ð {date}\nð {folder}"
        await send_file(message.chat.id, file_id, cat, caption)

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

# âââ QIDIRISH âââââââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["search"])
async def cmd_search(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /search fayl_nomi")
        return
    keyword = f"%{args[1]}%"
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT file_id, file_name, category, size, date, folder, pinned FROM files WHERE file_name LIKE ?",
            (keyword,)
        ) as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await message.answer("ð Topilmadi.")
        return
    for file_id, name, cat, size, date, folder, pinned in rows:
        mb = round(size / 1024 / 1024, 2)
        caption = f"{get_icon(cat)} {name}\nð¾ {mb} MB | ð {date}\nð {folder}"
        await send_file(message.chat.id, file_id, cat, caption)

# âââ O'CHIRISH ââââââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["delete"])
async def cmd_delete(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /delete fayl_nomi")
        return
    name = args[1]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM files WHERE file_name=?", (name,))
        await db.commit()
    await message.answer(f"ðï¸ {name} o'chirildi!")

# âââ PAPKALAR âââââââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["newfolder"])
async def cmd_newfolder(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /newfolder ish")
        return
    name = args[1]
    async with aiosqlite.connect(DB_NAME) as db:
        try:
            await db.execute(
                "INSERT INTO folders (name, date) VALUES (?,?)",
                (name, datetime.now().strftime("%Y-%m-%d %H:%M"))
            )
            await db.commit()
            await message.answer(f"ð '{name}' papkasi yaratildi!")
        except:
            await message.answer(f"â '{name}' papkasi allaqachon bor!")

@dp.message_handler(commands=["folders"])
async def cmd_folders(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT name FROM folders") as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await message.answer("ð­ Hozircha papka yoq.\n/newfolder nom â yaratish")
        return
    text = "ð Papkalar:\n\n"
    text += "ð umumiy\n"
    for (name,) in rows:
        text += f"ð {name}\n"
    await message.answer(text)

@dp.message_handler(commands=["folder"])
async def cmd_folder(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /folder ish")
        return
    folder_name = args[1]
    await show_files(message, "AND folder=?", params=(folder_name,))

@dp.message_handler(commands=["moveto"])
async def cmd_moveto(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "|" not in args[1]:
        await message.answer("Misol: /moveto fayl_nomi|papka_nomi")
        return
    parts = args[1].split("|")
    file_name = parts[0].strip()
    folder_name = parts[1].strip()
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "UPDATE files SET folder=? WHERE file_name=?",
            (folder_name, file_name)
        )
        await db.commit()
    await message.answer(f"â {file_name} â ð {folder_name}")

# âââ MUHIM FAYLLAR ââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["pin"])
async def cmd_pin(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /pin fayl_nomi")
        return
    name = args[1]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE files SET pinned=1 WHERE file_name=?", (name,))
        await db.commit()
    await message.answer(f"ð {name} muhim belgilandi!")

@dp.message_handler(commands=["unpin"])
async def cmd_unpin(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Misol: /unpin fayl_nomi")
        return
    name = args[1]
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE files SET pinned=0 WHERE file_name=?", (name,))
        await db.commit()
    await message.answer(f"â {name} dan muhim belgisi olindi!")

@dp.message_handler(commands=["pinned"])
async def cmd_pinned(message: Message):
    await show_files(message, "AND pinned=1")

# âââ STATISTIKA âââââââââââââââââââââââââââââââââââââ
@dp.message_handler(commands=["stats"])
async def cmd_stats(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("ð Avval /start orqali kiring!")
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*), SUM(size) FROM files") as cursor:
            total_count, total_size = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) FROM files WHERE category='video'") as cursor:
            video_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM files WHERE category='photo'") as cursor:
            photo_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM files WHERE category IN ('apk','ipa')") as cursor:
            app_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM files WHERE category='other'") as cursor:
            other_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM files WHERE pinned=1") as cursor:
            pinned_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM folders") as cursor:
            folder_count = (await cursor.fetchone())[0]

    total_mb = round((total_size or 0) / 1024 / 1024, 2)
    total_gb = round(total_mb / 1024, 3)

    await message.answer(
        f"ð Statistika\n\n"
        f"ð Jami fayllar: {total_count or 0}\n"
        f"ð¾ Umumiy hajm: {total_mb} MB ({total_gb} GB)\n\n"
        f"ð¬ Videolar: {video_count}\n"
        f"ð¼ï¸ Rasmlar: {photo_count}\n"
        f"ð¤ APK/IPA: {app_count}\n"
        f"ð Boshqalar: {other_count}\n\n"
        f"ð Muhim fayllar: {pinned_count}\n"
        f"ð Papkalar: {folder_count + 1}"
    )

# âââ MAIN âââââââââââââââââââââââââââââââââââââââââââ
async def on_startup(_):
    await create_db()
    print("Bot ishga tushdi!")
from aiogram.utils.executor import start_webhook

WEBHOOK_HOST = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.getenv("PORT", 8000))

async def on_startup(dp):
    await create_db()
    await bot.set_webhook(WEBHOOK_URL)
    print("Bot ishga tushdi!")

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )


