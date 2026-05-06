import asyncio
import logging
import sqlite3
import html
from pathlib import Path
from urllib.parse import quote

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    BufferedInputFile,
)
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest, TelegramRetryAfter

BOT_TOKEN = "8649986734:AAEPEY3qI8OHOzAz7PUKnxDUmoNHxkXwBNc"
ADMIN_ID = 7078570432

BANK_NAME = "MB Bank"
BANK_BIN = "970422"
BANK_ACCOUNT = "07007003005"
ACCOUNT_NAME = "VU VAN CUONG"

SUPPORT_USERNAME = "@tai_khoan_xin"
BASE_DIR = Path(__file__).resolve().parent
DB_NAME = "/data/shop_bot.db"

DEFAULT_PRODUCTS = {
    "sp1": {"ten": "Adobe Creative Cloud 3 Tháng", "gia": 159000, "sl": 5, "nhom": "Adobe"},
    "sp2": {"ten": "Acc Shoppe Ngâm 5 Tháng Voucher 80k - 100k", "gia": 29000, "sl": 5, "nhom": "Shopee"},
    "sp3": {"ten": "Đặt Đơn Shopee Giảm 100k", "gia": 59000, "sl": 5, "nhom": "Shopee"},
    "sp4": {"ten": "Canva Edu 1 Năm", "gia": 149000, "sl": 5, "nhom": "Canva"},
    "sp5": {"ten": "Canva Pro 1 Năm", "gia": 289000, "sl": 5, "nhom": "Canva"},
    "sp6": {"ten": "CapCut Pro 14 Ngày_BHF", "gia": 25000, "sl": 7, "nhom": "CapCut"},
    "sp7": {"ten": "CapCut Pro 35d_BHF", "gia": 45000, "sl": 5, "nhom": "CapCut"},
    "sp8": {"ten": "CapCut Pro 1 Năm_BHF", "gia": 450000, "sl": 5, "nhom": "CapCut"},
    "sp9": {"ten": "ChatGPT Plus 1 Tháng", "gia": 99000, "sl": 9, "nhom": "ChatGPT + Gemini"},
    "sp10": {"ten": "Gemini 2TB AI PRO 12 tháng", "gia": 199000, "sl": 2, "nhom": "ChatGPT + Gemini"},
    "sp11": {"ten": "Youtube Premium 1 Tháng", "gia": 55000, "sl": 5, "nhom": "Youtube"},
    "sp12": {"ten": "Youtube 3 Tháng", "gia": 159000, "sl": 5, "nhom": "Youtube"},
    "sp13": {"ten": "Mã Highlands Coffee Nước Free", "gia": 15000, "sl": 5, "nhom": "Mã Highlands Coffee Free"},
}

CATEGORY_ORDER = [
    "Adobe",
    "Shopee",
    "Canva",
    "CapCut",
    "ChatGPT + Gemini",
    "Youtube",
    "Mã Highlands Coffee Free",
]

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()


class BuyFlow(StatesGroup):
    cho_so_luong = State()
    cho_bill = State()


class AdminFlow(StatesGroup):
    nhap_noi_dung = State()
    update_so_luong = State()
    sua_gia = State()
    them_ten = State()
    them_gia = State()
    them_so_luong = State()
    them_nhom = State()
    thong_bao = State()
    xoa_san_pham = State()


def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def save_user_info(user):
    if not user:
        return

    conn = db()
    cur = conn.cursor()
    username = f"@{user.username}" if user.username else ""
    full_name = user.full_name or ""

    cur.execute("""
        INSERT INTO users(user_id, full_name, username, is_active)
        VALUES(?,?,?,1)
        ON CONFLICT(user_id) DO UPDATE SET
            full_name=excluded.full_name,
            username=excluded.username,
            is_active=1
    """, (user.id, full_name, username))

    conn.commit()
    conn.close()


def deactivate_user(user_id: int):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_active=0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_code TEXT,
            product TEXT,
            price INTEGER,
            quantity INTEGER DEFAULT 1,
            status TEXT,
            proof TEXT,
            delivery TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("PRAGMA table_info(users)")
    user_cols = [row["name"] for row in cur.fetchall()]
    if "is_active" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    cur.execute("PRAGMA table_info(orders)")
    cols = [row["name"] for row in cur.fetchall()]

    if "product" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN product TEXT")

    if "price" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN price INTEGER DEFAULT 0")

    if "quantity" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN quantity INTEGER DEFAULT 1")

    if "product_code" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN product_code TEXT")

    if "proof" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN proof TEXT")

    if "delivery" not in cols:
         cur.execute("ALTER TABLE orders ADD COLUMN delivery TEXT")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS products(
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL DEFAULT 'Mã Highlands Coffee Free'
        )
    """)

    cur.execute("PRAGMA table_info(products)")
    product_cols = [row["name"] for row in cur.fetchall()]

    if "category" not in product_cols:
        cur.execute("ALTER TABLE products ADD COLUMN category TEXT NOT NULL DEFAULT 'Mã Highlands Coffee Free'")

    for code, info in DEFAULT_PRODUCTS.items():
        cur.execute("SELECT code FROM products WHERE code=?", (code,))
        row = cur.fetchone()

        if row is None:
            active = 1 if info["sl"] > 0 else 0
            cur.execute("""
                INSERT INTO products(code, name, price, stock, active, category)
                VALUES(?,?,?,?,?,?)
            """, (code, info["ten"], info["gia"], info["sl"], active, info.get("nhom", "Mã Highlands Coffee Free")))
        else:
            cur.execute("""
                UPDATE products
                SET name=?, price=?, category=?
                WHERE code=?
            """, (info["ten"], info["gia"], info.get("nhom", "Mã Highlands Coffee Free"), code))

    conn.commit()
    conn.close()


def tao_qr(order_id, amount):
    noi_dung = f"DH{order_id}"
    return (
        f"https://img.vietqr.io/image/"
        f"{BANK_BIN}-{BANK_ACCOUNT}-compact2.png"
        f"?amount={amount}&addInfo={quote(noi_dung)}&accountName={quote(ACCOUNT_NAME)}"
    )


async def tao_qr_file(order_id, amount):
    qr_url = tao_qr(order_id, amount)

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(qr_url) as resp:
            if resp.status != 200:
                raise Exception(f"Không tải được ảnh QR, status={resp.status}")

            data = await resp.read()
            if not data:
                raise Exception("Ảnh QR trả về rỗng")

            return BufferedInputFile(data, filename=f"qr_{order_id}.png")


def menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛍 Xem nhóm sản phẩm", callback_data="sp")],
            [InlineKeyboardButton(text="☎️ Hỗ trợ", callback_data="contact")],
        ]
    )


def category_sort_key(cat_name: str):
    try:
        return CATEGORY_ORDER.index(cat_name)
    except ValueError:
        return 999


def get_categories():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT category FROM products")
    rows = [r["category"] for r in cur.fetchall()]
    conn.close()

    known = [c for c in CATEGORY_ORDER if c in rows]
    extra = sorted([c for c in rows if c not in CATEGORY_ORDER], key=lambda x: x.lower())
    return known + extra


def get_product_by_code(pid: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT code, name, price, stock, active, category
        FROM products
        WHERE code=?
    """, (pid,))
    row = cur.fetchone()
    conn.close()
    return row


def get_all_products():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT code, name, price, stock, active, category
        FROM products
    """)
    rows = cur.fetchall()
    conn.close()

    rows = sorted(
        rows,
        key=lambda p: (category_sort_key(p["category"]), p["category"].lower(), p["name"].lower())
    )
    return rows


def get_next_product_code():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT code FROM products")
    rows = cur.fetchall()
    conn.close()

    max_num = 0
    for row in rows:
        code = row["code"]
        if code.startswith("sp"):
            so = code[2:]
            if so.isdigit():
                max_num = max(max_num, int(so))

    return f"sp{max_num + 1}"


def category_menu():
    rows = []

    for cat in get_categories():
        rows.append([
            InlineKeyboardButton(
                text=f"📂 {cat}",
                callback_data=f"cat_{cat}"
            )
        ])

    rows.append([InlineKeyboardButton(text="🏠 Menu", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def list_sp_by_category(category_name: str):
    rows = []
    products = [p for p in get_all_products() if p["category"] == category_name]

    for i, p in enumerate(products, start=1):
        stock = p["stock"]
        active = p["active"]

        if active == 1 and stock > 0:
            label = f"[{i}] {p['name']} | {p['price'] // 1000}k | Còn: {stock}"
        else:
            label = f"[{i}] {p['name']} | {p['price'] // 1000}k | Hết hàng"

        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"buy_{p['code']}"
            )
        ])

    if not products:
        rows.append([
            InlineKeyboardButton(
                text="Không có sản phẩm trong nhóm này",
                callback_data="none"
            )
        ])

    rows.append([InlineKeyboardButton(text="⬅️ Quay lại nhóm", callback_data="sp")])
    rows.append([InlineKeyboardButton(text="🏠 Menu", callback_data="menu")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


async def safe_broadcast_to_user(uid: int, text: str):
    try:
        await bot.send_message(uid, text)
        return True, ""
    except TelegramRetryAfter as e:
        wait_time = max(int(e.retry_after), 1)
        logging.warning(f"Rate limit khi gửi tới {uid}, chờ {wait_time}s rồi thử lại")
        await asyncio.sleep(wait_time)
        try:
            await bot.send_message(uid, text)
            return True, ""
        except Exception as e2:
            logging.exception(f"Lỗi sau khi retry tới {uid}: {e2}")
            return False, f"retry_fail: {str(e2)}"
    except TelegramForbiddenError as e:
        logging.warning(f"User {uid} đã chặn bot hoặc bot không được phép nhắn: {e}")
        deactivate_user(uid)
        return False, "blocked_or_forbidden"
    except TelegramBadRequest as e:
        err = str(e).lower()
        logging.warning(f"BadRequest tới {uid}: {e}")
        if "chat not found" in err or "user not found" in err:
            deactivate_user(uid)
            return False, "chat_not_found"
        return False, f"bad_request: {str(e)}"
    except Exception as e:
        logging.exception(f"Lỗi không xác định khi gửi tới {uid}: {e}")
        return False, f"other_error: {str(e)}"


@dp.message(Command("start"))
async def start(m: Message):
    save_user_info(m.from_user)
    text = (
        "Chào bạn 👋\n\n"
        "Các lệnh có thể dùng:\n"
        "/start - Bắt đầu\n"
        "/menu - Xem nhóm sản phẩm\n"
        "/help - Hỗ trợ\n"
        "/donhang - Đơn hàng đã mua\n\n"
        f"Nếu cần hỗ trợ thêm, nhắn {SUPPORT_USERNAME}"
    )
    await m.answer(text, reply_markup=menu())


@dp.message(Command("menu"))
async def menu_command(m: Message):
    save_user_info(m.from_user)
    await m.answer("🛍 Chọn nhóm sản phẩm:", reply_markup=category_menu())


@dp.message(Command("help"))
async def help_command(m: Message):
    save_user_info(m.from_user)
    text = (
        "<b>Hỗ trợ sử dụng bot</b>\n\n"
        "/start - Bắt đầu\n"
        "/menu - Xem nhóm sản phẩm\n"
        "/help - Hỗ trợ\n"
        "/donhang - Xem đơn hàng đã mua\n"
        "/update - Cập nhật số lượng sản phẩm (chỉ admin)\n"
        "/suagia - Sửa giá sản phẩm (chỉ admin)\n"
        "/tonkho - Xem tồn kho nhanh (chỉ admin)\n"
        "/themsp - Thêm sản phẩm mới (chỉ admin)\n"
        "/xoasp - Xoá sản phẩm ngay trong bot (chỉ admin)\n"
        "/thongbao - Gửi thông báo tới tất cả user đã từng nhắn bot (chỉ admin)\n"
        "/users - Xem danh sách user đã từng nhắn bot (chỉ admin)\n\n"
        f"Liên hệ hỗ trợ: {SUPPORT_USERNAME}"
    )
    await m.answer(text)


@dp.message(Command("donhang"))
async def donhang_command(m: Message):
    save_user_info(m.from_user)
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, product, price, quantity, status
        FROM orders
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 10
    """, (m.from_user.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await m.answer("Bạn chưa có đơn hàng nào.", reply_markup=menu())
        return

    trang_thai_map = {
        "pay": "Chờ thanh toán",
        "check": "Chờ admin duyệt",
        "approved": "Đã duyệt",
        "done": "Đã giao hàng",
        "reject": "Đã từ chối",
    }

    text = "<b>🧾 Đơn hàng của bạn:</b>\n\n"
    for row in rows:
        text += (
            f"🆔 Đơn <b>#{row['id']}</b>\n"
            f"📦 Sản phẩm: <b>{html.escape(row['product'])}</b>\n"
            f"🔢 Số lượng: <b>{row['quantity']}</b>\n"
            f"💰 Tổng tiền: <b>{row['price']:,}đ</b>\n"
            f"📌 Trạng thái: <b>{trang_thai_map.get(row['status'], row['status'])}</b>\n\n"
        )

    await m.answer(text, reply_markup=menu())


@dp.message(Command("tonkho"))
async def tonkho_command(m: Message):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    products = get_all_products()

    if not products:
        await m.answer("Chưa có sản phẩm nào trong kho.")
        return

    text = "<b>📦 TỒN KHO HIỆN TẠI</b>\n\n"
    for i, p in enumerate(products, start=1):
        trang_thai = "Đang bán" if p["active"] == 1 and p["stock"] > 0 else "Hết hàng / Đang khóa"
        text += (
            f"{i}. <b>{html.escape(p['name'])}</b>\n"
            f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
            f"💰 Giá: <b>{p['price']:,}đ</b>\n"
            f"📦 Tồn kho: <b>{p['stock']}</b>\n"
            f"📌 Trạng thái: <b>{trang_thai}</b>\n\n"
        )

    await m.answer(text)


@dp.message(Command("users"))
async def users_command(m: Message):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, full_name, username, is_active
        FROM users
        ORDER BY user_id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await m.answer("Chưa có user nào từng nhắn bot.")
        return

    text = "<b>👥 DANH SÁCH USER ĐÃ TỪNG NHẮN BOT</b>\n\n"

    for i, row in enumerate(rows, start=1):
        full_name = html.escape(row["full_name"] or "Không có tên")
        username = html.escape(row["username"] or "Không có username")
        user_id = row["user_id"]
        status_text = "Hoạt động" if row["is_active"] == 1 else "Không nhận được tin"

        block = (
            f"{i}. 👤 <b>{full_name}</b>\n"
            f"🔗 Username: <b>{username}</b>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📌 Trạng thái: <b>{status_text}</b>\n\n"
        )

        if len(text) + len(block) > 3800:
            await m.answer(text)
            text = ""

        text += block

    if text:
        await m.answer(text)
@dp.message(Command("backup"))
async def backup_db(m: Message):
    import os

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    if not os.path.exists(DB_NAME):
        await m.answer(f"Chưa có dữ liệu!\nĐường dẫn DB hiện tại: <code>{html.escape(DB_NAME)}</code>")
        return

    try:
        with open(DB_NAME, "rb") as f:
            data = f.read()

        file = BufferedInputFile(data, filename="shop_bot_backup.db")

        # gửi file thẳng về chat admin
        await bot.send_document(
            ADMIN_ID,
            file,
            caption=(
                "📦 <b>BACKUP DỮ LIỆU BOT</b>\n\n"
                f"🗂 File: <code>shop_bot_backup.db</code>\n"
                f"📍 Nguồn: <code>{html.escape(DB_NAME)}</code>\n"
                f"👤 Yêu cầu bởi admin ID: <code>{m.from_user.id}</code>"
            )
        )

        if m.chat.id == ADMIN_ID:
            await m.answer("✅ Đã gửi file backup vào chat admin này.")
        else:
            await m.answer("✅ Đã gửi file backup về admin.")
    except Exception as e:
        logging.exception(f"Lỗi backup DB: {e}")
        await m.answer(f"❌ Backup thất bại: <code>{html.escape(str(e))}</code>")
@dp.message(Command("id"))
async def get_my_id(m: Message):
    await m.answer(f"ID của bạn là: <code>{m.from_user.id}</code>")


@dp.message(Command("testdb"))
async def test_db(m: Message):
    import os
    await m.answer(
        f"ADMIN_ID = <code>{ADMIN_ID}</code>\n"
        f"ID hiện tại = <code>{m.from_user.id}</code>\n"
        f"DB_NAME = <code>{html.escape(DB_NAME)}</code>\n"
        f"Tồn tại file DB = <b>{os.path.exists(DB_NAME)}</b>"
    )

@dp.message(Command("themsp"))
async def themsp_command(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    await state.set_state(AdminFlow.them_ten)
    await m.answer(
        "➕ <b>Thêm sản phẩm mới</b>\n\n"
        "Nhập <b>tên sản phẩm</b>.\n"
        "Muốn thoát thì nhập: <code>huy</code>"
    )


@dp.message(AdminFlow.them_ten)
async def themsp_nhap_ten(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""
    if not text:
        await m.answer("Tên sản phẩm không được để trống.")
        return

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ thêm sản phẩm.")
        return

    await state.update_data(ten=text)
    await state.set_state(AdminFlow.them_gia)
    await m.answer("Nhập <b>giá sản phẩm</b> bằng số.\nVí dụ: <code>15000</code>")


@dp.message(AdminFlow.them_gia)
async def themsp_nhap_gia(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ thêm sản phẩm.")
        return

    if not text.isdigit():
        await m.answer("Giá phải là số. Ví dụ: <code>15000</code>")
        return

    gia = int(text)
    if gia <= 0:
        await m.answer("Giá phải lớn hơn 0.")
        return

    await state.update_data(gia=gia)
    await state.set_state(AdminFlow.them_so_luong)
    await m.answer("Nhập <b>số lượng</b> ban đầu.\nVí dụ: <code>5</code>")


@dp.message(AdminFlow.them_so_luong)
async def themsp_nhap_so_luong(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ thêm sản phẩm.")
        return

    if not text.isdigit():
        await m.answer("Số lượng phải là số. Ví dụ: <code>5</code>")
        return

    sl = int(text)
    if sl < 0:
        await m.answer("Số lượng không hợp lệ.")
        return

    await state.update_data(sl=sl)
    await state.set_state(AdminFlow.them_nhom)

    ds_nhom = "\n".join([f"- {html.escape(cat)}" for cat in get_categories()])
    await m.answer(
        "Nhập <b>nhóm sản phẩm</b>.\n"
        "Bạn có thể nhập nhóm cũ hoặc nhóm mới.\n\n"
        f"<b>Các nhóm hiện có:</b>\n{ds_nhom}\n\n"
        "Ví dụ: <code>CapCut</code>"
    )


@dp.message(AdminFlow.them_nhom)
async def themsp_nhap_nhom(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    nhom = m.text.strip() if m.text else ""

    if not nhom:
        await m.answer("Nhóm sản phẩm không được để trống.")
        return

    if nhom.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ thêm sản phẩm.")
        return

    data = await state.get_data()
    ten = data.get("ten")
    gia = data.get("gia")
    sl = data.get("sl")

    if ten is None or gia is None or sl is None:
        await state.clear()
        await m.answer("Thiếu dữ liệu. Hãy dùng /themsp lại từ đầu.")
        return

    code = get_next_product_code()
    active = 1 if sl > 0 else 0

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO products(code, name, price, stock, active, category)
        VALUES(?,?,?,?,?,?)
    """, (code, ten, gia, sl, active, nhom))
    conn.commit()
    conn.close()

    await m.answer(
        f"✅ <b>Đã thêm sản phẩm mới</b>\n\n"
        f"🆔 Mã: <b>{html.escape(code)}</b>\n"
        f"📦 Tên: <b>{html.escape(ten)}</b>\n"
        f"📂 Nhóm: <b>{html.escape(nhom)}</b>\n"
        f"💰 Giá: <b>{gia:,}đ</b>\n"
        f"📦 Số lượng: <b>{sl}</b>"
    )
    await state.clear()


@dp.message(Command("xoasp"))
async def xoasp_command(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    products = get_all_products()

    if not products:
        await m.answer("Hiện không có sản phẩm nào để xoá.")
        return

    text = "<b>🗑 DANH SÁCH SẢN PHẨM CÓ THỂ XOÁ</b>\n\n"
    for i, p in enumerate(products, start=1):
        text += (
            f"{i}. <b>{html.escape(p['name'])}</b>\n"
            f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
            f"💰 Giá: <b>{p['price']:,}đ</b>\n"
            f"📦 Tồn kho: <b>{p['stock']}</b>\n\n"
        )

    text += (
        "Nhập <b>STT sản phẩm</b> muốn xoá.\n"
        "Ví dụ: <code>3</code>\n\n"
        "Muốn thoát thì nhập: <code>huy</code>"
    )

    await state.set_state(AdminFlow.xoa_san_pham)
    await m.answer(text)


@dp.message(AdminFlow.xoa_san_pham)
async def xoasp_save(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ xoá sản phẩm.")
        return

    if not text.isdigit():
        await m.answer(
            "Vui lòng nhập đúng STT sản phẩm muốn xoá.\n"
            "Ví dụ: <code>3</code>\n"
            "Hoặc nhập <code>huy</code> để thoát."
        )
        return

    stt = int(text)
    products = get_all_products()

    if stt <= 0 or stt > len(products):
        await m.answer("STT sản phẩm không hợp lệ.")
        return

    p = products[stt - 1]

    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE code=?", (p["code"],))
    conn.commit()
    conn.close()

    await m.answer(
        f"✅ Đã xoá sản phẩm thành công.\n\n"
        f"🆔 Mã: <b>{html.escape(p['code'])}</b>\n"
        f"📦 Tên: <b>{html.escape(p['name'])}</b>\n"
        f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
        f"💰 Giá: <b>{p['price']:,}đ</b>"
    )

    await state.clear()


@dp.message(Command("thongbao"))
async def thongbao_command(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    await state.set_state(AdminFlow.thong_bao)
    await m.answer(
        "📢 <b>Gửi thông báo hàng loạt</b>\n\n"
        "Hãy nhập nội dung thông báo muốn gửi tới tất cả user đã từng nhắn bot.\n"
        "Muốn thoát thì nhập: <code>huy</code>"
    )


@dp.message(AdminFlow.thong_bao)
async def thongbao_send(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text if m.text else ""

    if text.strip().lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ gửi thông báo.")
        return

    if not text.strip():
        await m.answer("Nội dung thông báo không được để trống.")
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, full_name, username
        FROM users
        WHERE is_active=1
        ORDER BY user_id ASC
    """)
    users = cur.fetchall()
    conn.close()

    if not users:
        await m.answer("Không có user nào khả dụng để gửi thông báo.")
        await state.clear()
        return

    sent = 0
    fail = 0
    fail_list = []

    notify_text = (
        f"📢 <b>THÔNG BÁO TỪ SHOP</b>\n\n"
        f"{text}\n\n"
        f"Nếu cần hỗ trợ, nhắn {SUPPORT_USERNAME}"
    )

    await m.answer(f"⏳ Bắt đầu gửi thông báo tới <b>{len(users)}</b> user...")

    for row in users:
        uid = row["user_id"]
        ok, reason = await safe_broadcast_to_user(uid, notify_text)

        if ok:
            sent += 1
        else:
            fail += 1
            fail_list.append(
                f"ID {uid} | "
                f"{row['full_name'] or 'Khong co ten'} | "
                f"{row['username'] or 'Khong co username'} | "
                f"{reason}"
            )

        await asyncio.sleep(0.05)

    result = (
        f"✅ Đã gửi thông báo xong.\n"
        f"📨 Gửi thành công: <b>{sent}</b>\n"
        f"❌ Gửi lỗi: <b>{fail}</b>"
    )

    await m.answer(result)

    if fail_list:
        chunk = "<b>Danh sách user gửi lỗi:</b>\n\n"
        for i, item in enumerate(fail_list, start=1):
            line = f"{i}. {html.escape(item)}\n"
            if len(chunk) + len(line) > 3800:
                await m.answer(chunk)
                chunk = ""
            chunk += line

        if chunk:
            await m.answer(chunk)

    await state.clear()


@dp.callback_query(F.data == "menu")
async def back(c: CallbackQuery):
    save_user_info(c.from_user)
    await c.message.edit_text("🏠 Menu chính:", reply_markup=menu())
    await c.answer()


@dp.callback_query(F.data == "sp")
async def sp(c: CallbackQuery):
    save_user_info(c.from_user)
    await c.message.edit_text("🛍 Chọn nhóm sản phẩm:", reply_markup=category_menu())
    await c.answer()


@dp.callback_query(F.data == "contact")
async def contact(c: CallbackQuery):
    save_user_info(c.from_user)
    await c.message.edit_text(
        f"☎️ Hỗ trợ: {SUPPORT_USERNAME}",
        reply_markup=menu()
    )
    await c.answer()


@dp.callback_query(F.data == "none")
async def none_callback(c: CallbackQuery):
    save_user_info(c.from_user)
    await c.answer()


@dp.callback_query(F.data.startswith("cat_"))
async def show_category(c: CallbackQuery):
    save_user_info(c.from_user)
    category_name = c.data.split("_", 1)[1]
    await c.message.edit_text(
        f"🛍 Nhóm sản phẩm: <b>{html.escape(category_name)}</b>",
        reply_markup=list_sp_by_category(category_name)
    )
    await c.answer()


@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: CallbackQuery, state: FSMContext):
    save_user_info(c.from_user)

    if c.from_user.id == ADMIN_ID:
        await c.answer(
            "Admin không thể mua hàng bằng bot này. Hãy dùng tài khoản Telegram khác để test như khách.",
            show_alert=True
        )
        return

    pid = c.data.split("_", 1)[1]
    p = get_product_by_code(pid)

    if not p:
        await c.answer("Không tìm thấy sản phẩm.", show_alert=True)
        return

    if p["active"] != 1 or p["stock"] <= 0:
        await c.answer("❌ Sản phẩm này hiện đã hết hàng. Chờ admin cập nhật lại số lượng.", show_alert=True)
        return

    await state.set_state(BuyFlow.cho_so_luong)
    await state.update_data(pid=pid)

    await c.message.answer(
        f"📦 Sản phẩm: <b>{html.escape(p['name'])}</b>\n"
        f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
        f"💰 Đơn giá: <b>{p['price']:,}đ</b>\n"
        f"📦 Còn lại: <b>{p['stock']}</b>\n\n"
        "Vui lòng nhập số lượng muốn mua:\nVí dụ: 1 - 2 - 3 - 4"
    )
    await c.answer()


@dp.message(BuyFlow.cho_so_luong)
async def chon_so_luong(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id == ADMIN_ID:
        await m.answer("Admin không thể mua hàng bằng bot này. Hãy dùng tài khoản Telegram khác để test như khách.")
        await state.clear()
        return

    text = m.text.strip() if m.text else ""

    if not text.isdigit():
        await m.answer("Vui lòng nhập số lượng bằng số. Ví dụ: <code>2</code>")
        return

    so_luong = int(text)

    if so_luong <= 0:
        await m.answer("Số lượng phải lớn hơn 0.")
        return

    data = await state.get_data()
    pid = data.get("pid")

    if not pid:
        await m.answer("Không tìm thấy sản phẩm. Vui lòng chọn lại từ menu.")
        await state.clear()
        return

    p = get_product_by_code(pid)

    if not p:
        await m.answer("Không tìm thấy sản phẩm. Vui lòng chọn lại từ menu.")
        await state.clear()
        return

    if p["active"] != 1 or p["stock"] <= 0:
        await m.answer("❌ Sản phẩm này hiện đã hết hàng. Chờ admin cập nhật lại số lượng.")
        await state.clear()
        return

    if so_luong > p["stock"]:
        await m.answer(
            f"❌ Số lượng vượt quá tồn kho.\n"
            f"Hiện chỉ còn: <b>{p['stock']}</b>"
        )
        return

    tong_tien = p["price"] * so_luong

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, product_code, product, price, quantity, status)
        VALUES(?,?,?,?,?,?)
    """, (m.from_user.id, pid, p["name"], tong_tien, so_luong, "pay"))
    oid = cur.lastrowid
    conn.commit()
    conn.close()

    await state.set_state(BuyFlow.cho_bill)
    await state.update_data(oid=oid)

    qr = tao_qr(oid, tong_tien)

    caption = (
        f"<b>Đơn #{oid}</b>\n"
        f"📦 Sản phẩm: <b>{html.escape(p['name'])}</b>\n"
        f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
        f"🔢 Số lượng: <b>{so_luong}</b>\n"
        f"💰 Đơn giá: <b>{p['price']:,}đ</b>\n"
        f"💵 Tổng tiền: <b>{tong_tien:,}đ</b>\n\n"
        f"🏦 Ngân hàng: <b>{BANK_NAME}</b>\n"
        f"👤 Chủ tài khoản: <b>{html.escape(ACCOUNT_NAME)}</b>\n"
        f"🔢 Số tài khoản: <b>{BANK_ACCOUNT}</b>\n"
        f"📌 Nội dung chuyển khoản: <code>DH{oid}</code>\n\n"
        "Chuyển khoản xong vui lòng gửi bill vào khung chat này."
    )

    try:
        photo = await tao_qr_file(oid, tong_tien)
        await bot.send_photo(m.from_user.id, photo, caption=caption)
    except Exception as e:
        logging.exception(f"Lỗi gửi QR đơn #{oid}: {e}")
        await m.answer(
            caption + f"\n\n🔗 Link QR: {html.escape(qr)}\n\n"
            "⚠️ Nếu ảnh chưa hiện, bạn vẫn có thể bấm link QR hoặc chuyển khoản thủ công theo thông tin trên rồi gửi bill.",
            reply_markup=menu()
        )


@dp.message(BuyFlow.cho_bill, F.photo)
async def bill(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id == ADMIN_ID:
        await m.answer("Admin không thể gửi bill như khách hàng. Hãy dùng tài khoản Telegram khác để test.")
        await state.clear()
        return

    data = await state.get_data()
    oid = data.get("oid")

    if not oid:
        await m.answer("Không tìm thấy đơn hàng đang chờ bill. Vui lòng đặt lại đơn.")
        await state.clear()
        return

    file_id = m.photo[-1].file_id

    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT id, product, price, quantity, status FROM orders WHERE id=?", (oid,))
    order_row = cur.fetchone()

    if not order_row:
        conn.close()
        await m.answer("Không tìm thấy đơn hàng.", reply_markup=menu())
        await state.clear()
        return

    if order_row["status"] != "pay":
        conn.close()
        await m.answer("Đơn này không còn ở trạng thái chờ bill.", reply_markup=menu())
        await state.clear()
        return

    cur.execute(
        "UPDATE orders SET proof=?, status='check' WHERE id=?",
        (file_id, oid)
    )
    conn.commit()
    conn.close()

    user = m.from_user
    username = f"@{user.username}" if user.username else "Không có"
    full_name = html.escape(user.full_name)

    caption_admin = (
        f"🧾 <b>Đơn #{oid}</b>\n"
        f"📦 Sản phẩm: <b>{html.escape(order_row['product'])}</b>\n"
        f"🔢 Số lượng: <b>{order_row['quantity']}</b>\n"
        f"💰 Tổng tiền: <b>{order_row['price']:,}đ</b>\n\n"
        f"👤 Tên: <b>{full_name}</b>\n"
        f"🔗 Username: <b>{html.escape(username)}</b>\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        "Vui lòng chọn thao tác:"
    )

    await bot.send_photo(
        ADMIN_ID,
        file_id,
        caption=caption_admin,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="DUYỆT", callback_data=f"ok_{oid}")],
                [InlineKeyboardButton(text="HUỶ", callback_data=f"no_{oid}")]
            ]
        )
    )

    await m.answer("✅ Đã gửi bill, vui lòng chờ admin duyệt.", reply_markup=menu())
    await state.clear()


@dp.message(BuyFlow.cho_bill)
async def nhac_gui_bill(m: Message):
    save_user_info(m.from_user)
    await m.answer("Vui lòng gửi <b>ảnh bill</b> để xác nhận thanh toán.")


@dp.callback_query(F.data.startswith("ok_"))
async def ok(c: CallbackQuery):
    save_user_info(c.from_user)
    oid = int(c.data.split("_")[1])

    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("BEGIN IMMEDIATE")

        cur.execute("""
            SELECT id, user_id, product_code, product, price, quantity, status
            FROM orders
            WHERE id=?
        """, (oid,))
        order_row = cur.fetchone()

        if not order_row:
            conn.rollback()
            conn.close()
            await c.answer("Không tìm thấy đơn.", show_alert=True)
            return

        if order_row["status"] != "check":
            conn.rollback()
            conn.close()
            await c.answer("Đơn này đã được xử lý trước đó.", show_alert=True)
            return

        cur.execute("""
            SELECT code, name, price, stock, active, category
            FROM products
            WHERE code=?
        """, (order_row["product_code"],))
        product_row = cur.fetchone()

        if not product_row:
            conn.rollback()
            conn.close()
            await c.answer("❌ Không tìm thấy sản phẩm trong kho.", show_alert=True)
            return

        if product_row["active"] != 1 or product_row["stock"] <= 0:
            conn.rollback()
            conn.close()
            await c.answer("❌ Sản phẩm đang hết hàng. Chỉ khi admin update lại số lượng mới bán tiếp được.", show_alert=True)
            return

        if product_row["stock"] < order_row["quantity"]:
            conn.rollback()
            conn.close()
            await c.answer("❌ Không đủ tồn kho để duyệt đơn này.", show_alert=True)
            return

        stock_moi = product_row["stock"] - order_row["quantity"]
        active_moi = 1 if stock_moi > 0 else 0

        cur.execute("""
            UPDATE products
            SET stock=?, active=?
            WHERE code=?
        """, (stock_moi, active_moi, product_row["code"]))

        cur.execute("""
            UPDATE orders
            SET status='approved'
            WHERE id=?
        """, (oid,))

        conn.commit()

        uid = order_row["user_id"]
        product_name = order_row["product"]
        price = order_row["price"]
        quantity = order_row["quantity"]

    except Exception:
        conn.rollback()
        conn.close()
        await c.answer("Có lỗi khi duyệt đơn.", show_alert=True)
        return

    conn.close()

    msg_admin = (
        f"✅ Đã duyệt đơn #{oid}\n"
        f"📦 Sản phẩm: <b>{html.escape(product_name)}</b>\n"
        f"🔢 Số lượng: <b>{quantity}</b>\n"
        f"💰 Tổng tiền: <b>{price:,}đ</b>\n"
    )

    if stock_moi > 0:
        msg_admin += f"📦 Tồn kho còn lại: <b>{stock_moi}</b>\n\n"
    else:
        msg_admin += "📦 Tồn kho còn lại: <b>0</b>\n⚠️ Sản phẩm này đã hết hàng và bị khóa bán cho tới khi admin /update lại.\n\n"

    msg_admin += (
        "Để giao đúng đơn này, hãy dùng lệnh:\n"
        f"<code>/gui {oid}</code>"
    )

    await c.message.answer(
        msg_admin,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📦 Giao hàng", callback_data=f"deliver_{oid}")]
            ]
        )
    )

    msg_user = (
        f"✅ Đơn #{oid} đã được duyệt\n"
        f"📦 Sản phẩm: <b>{html.escape(product_name)}</b>\n"
        f"🔢 Số lượng: <b>{quantity}</b>\n"
        f"💰 Tổng tiền: <b>{price:,}đ</b>\n\n"
        "Admin đang chuẩn bị giao hàng cho bạn."
    )

    await bot.send_message(uid, msg_user)
    await c.answer("Đã duyệt đơn.")


@dp.message(Command("gui"))
async def chon_don_gui(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    parts = m.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await m.answer("Cách dùng đúng: <code>/gui 12</code>")
        return

    oid = int(parts[1])

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, product, price, quantity, status
        FROM orders
        WHERE id=?
    """, (oid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await m.answer(
            f"Không tìm thấy đơn hàng #{oid}.\n"
            f"Bot đang dùng database: <code>{html.escape(DB_NAME)}</code>"
        )
        return

    if row["status"] not in ("approved", "done"):
        await m.answer(
            "Đơn này chưa ở trạng thái được giao.\n"
            "Hãy bấm DUYỆT trước rồi mới dùng /gui."
        )
        return

    await state.set_state(AdminFlow.nhap_noi_dung)
    await state.update_data(oid=oid)

    await m.answer(
        f"📌 Đã chọn đơn #{oid}\n"
        f"📦 Sản phẩm: <b>{html.escape(row['product'])}</b>\n"
        f"🔢 Số lượng: <b>{row['quantity']}</b>\n"
        f"💰 Tổng tiền: <b>{row['price']:,}đ</b>\n\n"
        "Bây giờ bạn nhập nội dung giao hàng dạng text."
    )


@dp.message(AdminFlow.nhap_noi_dung)
async def deliver(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    data = await state.get_data()
    oid = data.get("oid")

    if not oid:
        await m.answer("Chưa chọn đơn để giao. Dùng <code>/gui mã_đơn</code> trước.")
        await state.clear()
        return

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, product, quantity
        FROM orders
        WHERE id=?
    """, (oid,))
    row = cur.fetchone()

    if not row:
        conn.close()
        await m.answer("Không tìm thấy đơn hàng.")
        await state.clear()
        return

    uid = row["user_id"]
    product_name = row["product"]
    quantity = row["quantity"]

    raw_text = m.text.strip() if m.text else ""
    if not raw_text:
        await m.answer("Bạn hãy nhập nội dung giao hàng dạng text.")
        conn.close()
        return

    safe_text = html.escape(raw_text)
    safe_product = html.escape(product_name)

    cur.execute(
        "UPDATE orders SET delivery=?, status='done' WHERE id=?",
        (raw_text, oid)
    )
    conn.commit()
    conn.close()

    await bot.send_message(
        uid,
        f"🎉 <b>Đã giao hàng thành công</b>\n\n"
        f"🧾 Mã đơn: <b>#{oid}</b>\n"
        f"📦 Sản phẩm: <b>{safe_product}</b>\n"
        f"🔢 Số lượng: <b>{quantity}</b>\n\n"
        f"📌 Nội dung nhận hàng:\n<code>{safe_text}</code>\n\n"
        "Nhấn giữ vào phần trong khung để sao chép nhanh."
    )

    await m.answer(
        f"✅ Đã giao đơn #{oid}\n"
        f"📦 Sản phẩm: <b>{safe_product}</b>\n"
        f"🔢 Số lượng: <b>{quantity}</b>"
    )

    await state.clear()


@dp.callback_query(F.data.startswith("deliver_"))
async def deliver_button(c: CallbackQuery, state: FSMContext):
    save_user_info(c.from_user)

    if c.from_user.id != ADMIN_ID:
        await c.answer("Bạn không có quyền dùng nút này.", show_alert=True)
        return

    oid = int(c.data.split("_")[1])

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, product, price, quantity, status
        FROM orders
        WHERE id=?
    """, (oid,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await c.answer("Không tìm thấy đơn hàng.", show_alert=True)
        return

    if row["status"] not in ("approved", "done"):
        await c.answer("Đơn này chưa sẵn sàng để giao.", show_alert=True)
        return

    await state.set_state(AdminFlow.nhap_noi_dung)
    await state.update_data(oid=oid)

    await c.message.answer(
        f"📌 Đã chọn đơn #{oid}\n"
        f"📦 Sản phẩm: <b>{html.escape(row['product'])}</b>\n"
        f"🔢 Số lượng: <b>{row['quantity']}</b>\n"
        f"💰 Tổng tiền: <b>{row['price']:,}đ</b>\n\n"
        "Bây giờ bạn nhập nội dung giao hàng dạng text."
    )
    await c.answer("Đã chọn đơn để giao.")


@dp.callback_query(F.data.startswith("no_"))
async def no(c: CallbackQuery):
    save_user_info(c.from_user)
    oid = int(c.data.split("_")[1])

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, product, price, quantity, status
        FROM orders
        WHERE id=?
    """, (oid,))
    row = cur.fetchone()

    if not row:
        conn.close()
        await c.answer("Không tìm thấy đơn.", show_alert=True)
        return

    if row["status"] not in ("check", "pay"):
        conn.close()
        await c.answer("Đơn này đã được xử lý trước đó.", show_alert=True)
        return

    cur.execute("UPDATE orders SET status='reject' WHERE id=?", (oid,))
    conn.commit()
    conn.close()

    await bot.send_message(
        row["user_id"],
        f"❌ Đơn #{oid} đã bị từ chối\n"
        f"📦 Sản phẩm: <b>{html.escape(row['product'])}</b>\n"
        f"🔢 Số lượng: <b>{row['quantity']}</b>\n"
        f"💰 Tổng tiền: <b>{row['price']:,}đ</b>\n\n"
        f"Nếu cần hỗ trợ, vui lòng liên hệ {SUPPORT_USERNAME}"
    )

    await c.answer("Đã huỷ đơn.")


@dp.message(Command("update"))
async def update_stock_menu(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    products = get_all_products()

    text = "<b>Danh sách sản phẩm:</b>\n\n"
    for i, p in enumerate(products, start=1):
        trang_thai = "Đang bán" if p["active"] == 1 and p["stock"] > 0 else "Hết hàng / Đang khóa"
        text += (
            f"{i}. {html.escape(p['name'])} | "
            f"Nhóm: {html.escape(p['category'])} | "
            f"Còn: {p['stock']} | "
            f"Trạng thái: {trang_thai}\n"
        )

    text += (
        "\nNhập theo mẫu:\n"
        "<code>1 5</code>\n"
        "Nghĩa là: sản phẩm số 1 cập nhật còn 5.\n"
        "Nếu nhập 0 thì sản phẩm sẽ bị khóa bán.\n\n"
        "Muốn thoát thì nhập: <code>huy</code>"
    )

    await state.set_state(AdminFlow.update_so_luong)
    await m.answer(text)


@dp.message(AdminFlow.update_so_luong)
async def update_stock_save(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ cập nhật số lượng.")
        return

    parts = text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await m.answer(
            "Sai định dạng.\n"
            "Nhập theo mẫu: <code>1 5</code>\n"
            "Nghĩa là sản phẩm số 1 còn 5."
        )
        return

    stt = int(parts[0])
    so_luong_moi = int(parts[1])

    products = get_all_products()

    if stt <= 0 or stt > len(products):
        await m.answer("Số thứ tự sản phẩm không hợp lệ.")
        return

    p = products[stt - 1]
    active_moi = 1 if so_luong_moi > 0 else 0

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE products
        SET stock=?, active=?
        WHERE code=?
    """, (so_luong_moi, active_moi, p["code"]))
    conn.commit()
    conn.close()

    trang_thai = "Đang bán" if active_moi == 1 else "Hết hàng / Đang khóa"

    await m.answer(
        f"✅ Đã cập nhật:\n"
        f"📦 Sản phẩm: <b>{html.escape(p['name'])}</b>\n"
        f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
        f"📌 Số lượng mới: <b>{so_luong_moi}</b>\n"
        f"📌 Trạng thái mới: <b>{trang_thai}</b>\n\n"
        "Tiếp tục nhập theo mẫu <code>stt số_lượng</code> nếu muốn sửa thêm,\n"
        "hoặc nhập <code>huy</code> để thoát."
    )


@dp.message(Command("suagia"))
async def suagia_command(m: Message, state: FSMContext):
    save_user_info(m.from_user)

    if m.from_user.id != ADMIN_ID:
        await m.answer("Bạn không có quyền dùng lệnh này.")
        return

    products = get_all_products()

    if not products:
        await m.answer("Chưa có sản phẩm nào để sửa giá.")
        return

    text = "<b>💰 DANH SÁCH SẢN PHẨM CÓ THỂ SỬA GIÁ</b>\n\n"
    for i, p in enumerate(products, start=1):
        text += (
            f"{i}. <b>{html.escape(p['name'])}</b>\n"
            f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
            f"💰 Giá hiện tại: <b>{p['price']:,}đ</b>\n"
            f"📦 Tồn kho: <b>{p['stock']}</b>\n\n"
        )

    text += (
        "Nhập theo mẫu:\n"
        "<code>1 99000</code>\n"
        "Nghĩa là: sản phẩm số 1 sửa giá thành 99.000đ.\n\n"
        "Muốn thoát thì nhập: <code>huy</code>"
    )

    await state.set_state(AdminFlow.sua_gia)
    await m.answer(text)


@dp.message(AdminFlow.sua_gia)
async def suagia_save(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        return

    text = m.text.strip() if m.text else ""

    if text.lower() == "huy":
        await state.clear()
        await m.answer("Đã huỷ sửa giá sản phẩm.")
        return

    parts = text.split()
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        await m.answer(
            "Sai định dạng.\n"
            "Nhập theo mẫu: <code>1 99000</code>\n"
            "Nghĩa là sản phẩm số 1 có giá mới là 99.000đ."
        )
        return

    stt = int(parts[0])
    gia_moi = int(parts[1])

    if gia_moi <= 0:
        await m.answer("Giá mới phải lớn hơn 0.")
        return

    products = get_all_products()

    if stt <= 0 or stt > len(products):
        await m.answer("Số thứ tự sản phẩm không hợp lệ.")
        return

    p = products[stt - 1]

    conn = db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE products
        SET price=?
        WHERE code=?
    """, (gia_moi, p["code"]))
    conn.commit()
    conn.close()

    await m.answer(
        f"✅ Đã cập nhật giá sản phẩm:\n"
        f"📦 Sản phẩm: <b>{html.escape(p['name'])}</b>\n"
        f"📂 Nhóm: <b>{html.escape(p['category'])}</b>\n"
        f"💰 Giá mới: <b>{gia_moi:,}đ</b>\n\n"
        "Tiếp tục nhập theo mẫu <code>stt giá_mới</code> nếu muốn sửa thêm,\n"
        "hoặc nhập <code>huy</code> để thoát."
    )


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
