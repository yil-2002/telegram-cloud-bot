import os
import asyncio
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.utils import executor

BOT_TOKEN = os.getenv("BOT_TOKEN")
PASSWORD = os.getenv("BOT_PASSWORD", "Sobirjon2005")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

authorized_users = set()
db_pool = None

PAGE_SIZE = 5

# ─── States ───────────────────────────────────────────────────────────────────

class AuthState(StatesGroup):
    waiting_password = State()

class SearchState(StatesGroup):
    waiting_query = State()

class NewFolderState(StatesGroup):
    waiting_name = State()

class MoveState(StatesGroup):
    waiting_folder = State()

# ─── DB ───────────────────────────────────────────────────────────────────────

async def create_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                file_id TEXT,
                file_name TEXT,
                category TEXT,
                size BIGINT,
                date TEXT,
                folder TEXT DEFAULT 'umumiy',
                pinned INTEGER DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE,
                date TEXT
            )
        """)

async def save_file(user_id, file_id, file_name, category, size):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO files (user_id, file_id, file_name, category, size, date, folder, pinned) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            user_id, file_id, file_name, category, size,
            datetime.now().strftime("%Y-%m-%d %H:%M"), "umumiy", 0
        )

async def get_files(where="", order="date DESC", params=(), limit=PAGE_SIZE, offset=0):
    async with db_pool.acquire() as conn:
        q = (
            f"SELECT id, file_id, file_name, category, size, date, folder, pinned "
            f"FROM files WHERE 1=1 {where} ORDER BY {order} "
            f"LIMIT {limit} OFFSET {offset}"
        )
        return await conn.fetch(q, *params)

async def get_total(where="", params=()):
    async with db_pool.acquire() as conn:
        q = f"SELECT COUNT(*) FROM files WHERE 1=1 {where}"
        return await conn.fetchval(q, *params)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_auth(user_id):
    return user_id in authorized_users

def get_icon(cat):
    return {"video": "🎬", "photo": "🖼️", "apk": "🤖", "ipa": "🍎"}.get(cat, "📄")

def get_category(ext):
    if ext == "apk":   return "apk"
    if ext == "ipa":   return "ipa"
    if ext in ["mp4", "mov", "avi", "mkv", "webm"]: return "video"
    if ext in ["jpg", "jpeg", "png", "gif", "webp"]: return "photo"
    return "other"

# ─── Keyboards ────────────────────────────────────────────────────────────────

def main_menu_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎬 Videolar", callback_data="cat:video:0"),
        InlineKeyboardButton("🖼️ Rasmlar",  callback_data="cat:photo:0"),
        InlineKeyboardButton("🤖 APK/IPA",  callback_data="cat:apps:0"),
        InlineKeyboardButton("📄 Boshqalar", callback_data="cat:other:0"),
    )
    kb.add(
        InlineKeyboardButton("📋 Barchasi",   callback_data="cat:all:0"),
        InlineKeyboardButton("📌 Muhimlar",   callback_data="cat:pinned:0"),
    )
    kb.add(
        InlineKeyboardButton("📁 Papkalar",   callback_data="folders:0"),
        InlineKeyboardButton("🔍 Qidirish",   callback_data="search"),
    )
    kb.add(
        InlineKeyboardButton("📊 Statistika", callback_data="stats"),
        InlineKeyboardButton("➕ Papka qo'sh", callback_data="newfolder"),
    )
    return kb

def file_actions_kb(file_id_db, pinned, folder):
    """Har bir fayl ostidagi tugmalar"""
    kb = InlineKeyboardMarkup(row_width=3)
    pin_btn = (
        InlineKeyboardButton("📌 Pin olish", callback_data=f"unpin:{file_id_db}")
        if pinned else
        InlineKeyboardButton("📌 Pin",       callback_data=f"pin:{file_id_db}")
    )
    kb.add(
        pin_btn,
        InlineKeyboardButton("📁 Ko'chirish", callback_data=f"move:{file_id_db}"),
        InlineKeyboardButton("🗑️ O'chirish",  callback_data=f"delete:{file_id_db}"),
    )
    return kb

def pagination_kb(ctx, page, total):
    """Sahifalash tugmalari"""
    kb = InlineKeyboardMarkup(row_width=3)
    total_pages = (total - 1) // PAGE_SIZE + 1
    btns = []
    if page > 0:
        btns.append(InlineKeyboardButton("⬅️", callback_data=f"{ctx}:{page-1}"))
    btns.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if (page + 1) * PAGE_SIZE < total:
        btns.append(InlineKeyboardButton("➡️", callback_data=f"{ctx}:{page+1}"))
    kb.add(*btns)
    kb.add(InlineKeyboardButton("🏠 Menyu", callback_data="menu"))
    return kb

def folders_kb(folders_list, page=0):
    kb = InlineKeyboardMarkup(row_width=2)
    # Default papka
    kb.add(InlineKeyboardButton("📂 umumiy", callback_data="folder:umumiy:0"))
    for f in folders_list:
        kb.add(InlineKeyboardButton(f"📂 {f['name']}", callback_data=f"folder:{f['name']}:0"))
    kb.add(InlineKeyboardButton("➕ Yangi papka", callback_data="newfolder"))
    kb.add(InlineKeyboardButton("🏠 Menyu", callback_data="menu"))
    return kb

def confirm_delete_kb(file_id_db):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha, o'chir", callback_data=f"confirmdelete:{file_id_db}"),
        InlineKeyboardButton("❌ Yo'q",       callback_data="menu"),
    )
    return kb

def move_folders_kb(file_id_db, folders_list):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📂 umumiy", callback_data=f"domove:{file_id_db}:umumiy"))
    for f in folders_list:
        kb.add(InlineKeyboardButton(f"📂 {f['name']}", callback_data=f"domove:{file_id_db}:{f['name']}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="menu"))
    return kb

# ─── Auth ─────────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["start"])
async def start(message: Message):
    if is_auth(message.from_user.id):
        await message.answer(
            "☁️ <b>Shaxsiy Bulut Xotirangiz</b>\n\n"
            "📤 Fayl yuboring — avtomatik saqlanadi!\n"
            "Quyidagi menyudan tanlang:",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    else:
        await message.answer("🔐 Parolni kiriting:")
        await AuthState.waiting_password.set()

@dp.message_handler(state=AuthState.waiting_password)
async def check_password(message: Message, state: FSMContext):
    if message.text == PASSWORD:
        authorized_users.add(message.from_user.id)
        await state.finish()
        await message.answer(
            "✅ <b>Xush kelibsiz!</b>\n\nMenyudan tanlang:",
            parse_mode="HTML",
            reply_markup=main_menu_kb()
        )
    else:
        await message.answer("❌ Noto'g'ri parol! Qayta kiriting:")

# ─── Menu callback ────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data == "menu")
async def cb_menu(call: CallbackQuery):
    await call.message.edit_text(
        "☁️ <b>Shaxsiy Bulut Xotirangiz</b>\n\nMenyudan tanlang:",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()

# ─── File upload handlers ──────────────────────────────────────────────────────

@dp.message_handler(content_types=types.ContentType.VIDEO)
async def handle_video(message: Message):
    if not is_auth(message.from_user.id): return
    v = message.video
    name = v.file_name or f"video_{v.file_id[:8]}.mp4"
    await save_file(message.from_user.id, v.file_id, name, "video", v.file_size)
    mb = round(v.file_size / 1024 / 1024, 2)
    await message.answer(f"🎬 <b>Saqlandi!</b>\n📄 {name}\n💾 {mb} MB", parse_mode="HTML")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_photo(message: Message):
    if not is_auth(message.from_user.id): return
    p = message.photo[-1]
    name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    await save_file(message.from_user.id, p.file_id, name, "photo", p.file_size)
    mb = round(p.file_size / 1024 / 1024, 2)
    await message.answer(f"🖼️ <b>Saqlandi!</b>\n📄 {name}\n💾 {mb} MB", parse_mode="HTML")

@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: Message):
    if not is_auth(message.from_user.id): return
    d = message.document
    name = d.file_name or "nomsiz_fayl"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    category = get_category(ext)
    await save_file(message.from_user.id, d.file_id, name, category, d.file_size)
    mb = round(d.file_size / 1024 / 1024, 2)
    icon = get_icon(category)
    await message.answer(f"{icon} <b>Saqlandi!</b>\n📄 {name}\n💾 {mb} MB", parse_mode="HTML")

# ─── Show files with pagination ───────────────────────────────────────────────

async def send_file_safe(chat_id, file_id, cat, caption, reply_markup=None):
    try:
        if cat == "video":
            await bot.send_video(chat_id, file_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        elif cat == "photo":
            await bot.send_photo(chat_id, file_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await bot.send_document(chat_id, file_id, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        await bot.send_message(chat_id, caption, reply_markup=reply_markup, parse_mode="HTML")

async def show_files_page(chat_id, ctx, page=0, where="", order="date DESC", params=()):
    total = await get_total(where, params)
    if total == 0:
        await bot.send_message(
            chat_id,
            "😔 Hozircha fayl yo'q.\n📤 Fayl yuboring — saqlanadi!",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🏠 Menyu", callback_data="menu")
            )
        )
        return

    offset = page * PAGE_SIZE
    rows = await get_files(where, order, params, limit=PAGE_SIZE, offset=offset)

    # Har bir fayl alohida xabar
    for i, row in enumerate(rows):
        db_id, file_id, name, cat, size, date, folder, pinned = row
        mb = round(size / 1024 / 1024, 2)
        pin_icon = "📌 " if pinned else ""
        caption = (
            f"{pin_icon}{get_icon(cat)} <b>{name}</b>\n"
            f"💾 {mb} MB  |  📅 {date}\n"
            f"📁 {folder}"
        )
        # Oxirgi faylga pagination tugmalarini qo'shish
        if i == len(rows) - 1:
            actions_kb = file_actions_kb(db_id, pinned, folder)
            # Pagination qatorini actions_kb ga qo'shamiz
            total_pages = (total - 1) // PAGE_SIZE + 1
            nav_btns = []
            if page > 0:
                nav_btns.append(InlineKeyboardButton("⬅️", callback_data=f"{ctx}:{page-1}"))
            nav_btns.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
            if (page + 1) * PAGE_SIZE < total:
                nav_btns.append(InlineKeyboardButton("➡️", callback_data=f"{ctx}:{page+1}"))
            if nav_btns:
                actions_kb.add(*nav_btns)
            actions_kb.add(InlineKeyboardButton("🏠 Menyu", callback_data="menu"))
            await send_file_safe(chat_id, file_id, cat, caption, reply_markup=actions_kb)
        else:
            await send_file_safe(
                chat_id, file_id, cat, caption,
                reply_markup=file_actions_kb(db_id, pinned, folder)
            )

# ─── Category callbacks ───────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    if not is_auth(call.from_user.id):
        await call.answer("🔐 Avval /start orqali kiring!", show_alert=True)
        return
    _, cat, page = call.data.split(":")
    page = int(page)

    cat_map = {
        "video":  ("AND category='video'",                  (),   "cat:video"),
        "photo":  ("AND category='photo'",                  (),   "cat:photo"),
        "apps":   ("AND category IN ('apk','ipa')",         (),   "cat:apps"),
        "other":  ("AND category='other'",                  (),   "cat:other"),
        "all":    ("",                                       (),   "cat:all"),
        "pinned": ("AND pinned=1",                          (),   "cat:pinned"),
    }
    cat_names = {
        "video": "🎬 Videolar", "photo": "🖼️ Rasmlar",
        "apps": "🤖 APK/IPA",  "other": "📄 Boshqalar",
        "all": "📋 Barcha fayllar", "pinned": "📌 Muhim fayllar",
    }

    if cat not in cat_map:
        await call.answer()
        return

    where, params, ctx = cat_map[cat]
    await call.message.delete()
    await bot.send_message(
        call.message.chat.id,
        f"<b>{cat_names[cat]}</b> — {page*PAGE_SIZE+1}-{(page+1)*PAGE_SIZE} ko'rsatilmoqda:",
        parse_mode="HTML"
    )
    await show_files_page(call.message.chat.id, ctx, page, where, params=params)
    await call.answer()

# ─── Folder callbacks ─────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data == "folders:0" or c.data.startswith("folders:"))
async def cb_folders(call: CallbackQuery):
    if not is_auth(call.from_user.id):
        await call.answer("🔐 Avval /start orqali kiring!", show_alert=True)
        return
    async with db_pool.acquire() as conn:
        folders = await conn.fetch("SELECT name FROM folders ORDER BY name")
    await call.message.edit_text(
        "📁 <b>Papkalar</b>\n\nPapkani tanlang:",
        parse_mode="HTML",
        reply_markup=folders_kb(folders)
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("folder:"))
async def cb_folder(call: CallbackQuery):
    if not is_auth(call.from_user.id):
        await call.answer()
        return
    parts = call.data.split(":")
    folder_name = parts[1]
    page = int(parts[2])
    ctx = f"folder:{folder_name}"
    await call.message.delete()
    await bot.send_message(
        call.message.chat.id,
        f"📂 <b>{folder_name}</b> papkasi:",
        parse_mode="HTML"
    )
    await show_files_page(
        call.message.chat.id, ctx, page,
        where="AND folder=$1", params=(folder_name,)
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("folder:") and c.data.count(":") == 2)
async def cb_folder_page(call: CallbackQuery):
    # folder:name:page -> handled above
    await call.answer()

# ─── Pagination for folder and category ──────────────────────────────────────

# cat:video:2 etc. handled in cb_category
# folder:name:2 handled in cb_folder

# ─── Pin / Unpin ──────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("pin:"))
async def cb_pin(call: CallbackQuery):
    db_id = int(call.data.split(":")[1])
    async with db_pool.acquire() as conn:
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
        await conn.execute("UPDATE files SET pinned=1 WHERE id=$1", db_id)
    await call.answer(f"📌 {name} muhim belgilandi!", show_alert=False)
    # Tugmani yangilash
    try:
        row = await (await db_pool.acquire()).__aenter__()
    except Exception:
        pass
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, pinned, folder FROM files WHERE id=$1", db_id)
    new_kb = file_actions_kb(row["id"], row["pinned"], row["folder"])
    try:
        await call.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        pass

@dp.callback_query_handler(lambda c: c.data.startswith("unpin:"))
async def cb_unpin(call: CallbackQuery):
    db_id = int(call.data.split(":")[1])
    async with db_pool.acquire() as conn:
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
        await conn.execute("UPDATE files SET pinned=0 WHERE id=$1", db_id)
    await call.answer(f"✅ {name} dan pin olindi!", show_alert=False)
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT id, pinned, folder FROM files WHERE id=$1", db_id)
    new_kb = file_actions_kb(row["id"], row["pinned"], row["folder"])
    try:
        await call.message.edit_reply_markup(reply_markup=new_kb)
    except Exception:
        pass

# ─── Delete ───────────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("delete:"))
async def cb_delete(call: CallbackQuery):
    db_id = int(call.data.split(":")[1])
    async with db_pool.acquire() as conn:
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
    await call.message.reply(
        f"🗑️ <b>{name}</b> ni o'chirishni tasdiqlaysizmi?",
        parse_mode="HTML",
        reply_markup=confirm_delete_kb(db_id)
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("confirmdelete:"))
async def cb_confirm_delete(call: CallbackQuery):
    db_id = int(call.data.split(":")[1])
    async with db_pool.acquire() as conn:
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
        await conn.execute("DELETE FROM files WHERE id=$1", db_id)
    await call.message.edit_text(f"🗑️ <b>{name}</b> o'chirildi!", parse_mode="HTML")
    await call.answer("O'chirildi!")

# ─── Move to folder ───────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("move:"))
async def cb_move(call: CallbackQuery):
    db_id = int(call.data.split(":")[1])
    async with db_pool.acquire() as conn:
        folders = await conn.fetch("SELECT name FROM folders ORDER BY name")
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
    await call.message.reply(
        f"📁 <b>{name}</b> ni qaysi papkaga ko'chirish?",
        parse_mode="HTML",
        reply_markup=move_folders_kb(db_id, folders)
    )
    await call.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("domove:"))
async def cb_do_move(call: CallbackQuery):
    parts = call.data.split(":", 2)
    db_id = int(parts[1])
    folder_name = parts[2]
    async with db_pool.acquire() as conn:
        name = await conn.fetchval("SELECT file_name FROM files WHERE id=$1", db_id)
        await conn.execute("UPDATE files SET folder=$1 WHERE id=$2", folder_name, db_id)
    await call.message.edit_text(
        f"✅ <b>{name}</b> → 📁 {folder_name}",
        parse_mode="HTML"
    )
    await call.answer()

# ─── New folder ───────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data == "newfolder")
async def cb_newfolder(call: CallbackQuery):
    await call.message.answer("📁 Yangi papka nomini yozing:")
    await NewFolderState.waiting_name.set()
    await call.answer()

@dp.message_handler(state=NewFolderState.waiting_name)
async def process_newfolder(message: Message, state: FSMContext):
    name = message.text.strip()
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO folders (name, date) VALUES ($1,$2)",
                name, datetime.now().strftime("%Y-%m-%d %H:%M")
            )
            await message.answer(
                f"✅ <b>{name}</b> papkasi yaratildi!",
                parse_mode="HTML",
                reply_markup=main_menu_kb()
            )
        except Exception:
            await message.answer(
                f"❌ <b>{name}</b> papkasi allaqachon mavjud!",
                parse_mode="HTML"
            )
    await state.finish()

# ─── Search ───────────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data == "search")
async def cb_search(call: CallbackQuery):
    await call.message.answer("🔍 Qidiruv so'zini yozing:")
    await SearchState.waiting_query.set()
    await call.answer()

@dp.message_handler(state=SearchState.waiting_query)
async def process_search(message: Message, state: FSMContext):
    keyword = f"%{message.text.strip()}%"
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, file_id, file_name, category, size, date, folder, pinned "
            "FROM files WHERE file_name ILIKE $1 ORDER BY date DESC",
            keyword
        )
    await state.finish()
    if not rows:
        await message.answer(
            "🔍 Hech narsa topilmadi.",
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("🏠 Menyu", callback_data="menu")
            )
        )
        return

    await message.answer(f"🔍 <b>{len(rows)} ta natija:</b>", parse_mode="HTML")
    for row in rows:
        db_id, file_id, name, cat, size, date, folder, pinned = row
        mb = round(size / 1024 / 1024, 2)
        pin_icon = "📌 " if pinned else ""
        caption = (
            f"{pin_icon}{get_icon(cat)} <b>{name}</b>\n"
            f"💾 {mb} MB  |  📅 {date}\n"
            f"📁 {folder}"
        )
        await send_file_safe(
            message.chat.id, file_id, cat, caption,
            reply_markup=file_actions_kb(db_id, pinned, folder)
        )

# ─── Stats ────────────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data == "stats")
async def cb_stats(call: CallbackQuery):
    if not is_auth(call.from_user.id):
        await call.answer("🔐 Kiring!", show_alert=True)
        return
    async with db_pool.acquire() as conn:
        total     = await conn.fetchrow("SELECT COUNT(*), SUM(size) FROM files")
        vid_cnt   = await conn.fetchval("SELECT COUNT(*) FROM files WHERE category='video'")
        photo_cnt = await conn.fetchval("SELECT COUNT(*) FROM files WHERE category='photo'")
        app_cnt   = await conn.fetchval("SELECT COUNT(*) FROM files WHERE category IN ('apk','ipa')")
        other_cnt = await conn.fetchval("SELECT COUNT(*) FROM files WHERE category='other'")
        pin_cnt   = await conn.fetchval("SELECT COUNT(*) FROM files WHERE pinned=1")
        fold_cnt  = await conn.fetchval("SELECT COUNT(*) FROM folders")

    mb = round((total[1] or 0) / 1024 / 1024, 2)
    gb = round(mb / 1024, 3)

    text = (
        f"📊 <b>Statistika</b>\n\n"
        f"📄 Jami fayllar: <b>{total[0] or 0}</b>\n"
        f"💾 Umumiy hajm: <b>{mb} MB ({gb} GB)</b>\n\n"
        f"🎬 Videolar: <b>{vid_cnt}</b>\n"
        f"🖼️ Rasmlar: <b>{photo_cnt}</b>\n"
        f"🤖 APK/IPA: <b>{app_cnt}</b>\n"
        f"📄 Boshqalar: <b>{other_cnt}</b>\n\n"
        f"📌 Muhim fayllar: <b>{pin_cnt}</b>\n"
        f"📁 Papkalar: <b>{(fold_cnt or 0) + 1}</b>"
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🏠 Menyu", callback_data="menu")
        )
    )
    await call.answer()

# ─── /menu command ────────────────────────────────────────────────────────────

@dp.message_handler(commands=["menu"])
async def cmd_menu(message: Message):
    if not is_auth(message.from_user.id):
        await message.answer("🔐 Avval /start orqali kiring!")
        return
    await message.answer(
        "☁️ <b>Shaxsiy Bulut Xotirangiz</b>\n\nMenyudan tanlang:",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )

# ─── Startup ──────────────────────────────────────────────────────────────────

async def on_startup(dp):
    await create_db()
    from aiohttp import web
    async def health(request):
        return web.Response(text="OK")
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Bot ishga tushdi! Port: {port}")

if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
