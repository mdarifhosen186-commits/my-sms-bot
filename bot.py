import sqlite3
import requests
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from datetime import datetime

# ==================== কনফিগারেশন ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@yourchannel")
GROUP_ID = os.environ.get("GROUP_ID", "-1001234567890")

# Admin IDs (comma-separated in env)
ADMIN_IDS = [int(x) for x in os.environ.get("ADMIN_IDS", "123456789").split(",") if x.strip()]

# রেফারেল সেটিংস
POINTS_PER_REFERRAL = 5
POINTS_PER_SMS = 1

# Conversation States
BROADCAST_MESSAGE = 1

# ==================== ডেটাবেজ ====================
DB_PATH = os.environ.get("DB_PATH", "users.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            points INTEGER DEFAULT 0,
            referred_by INTEGER,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sms_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            to_number TEXT,
            message TEXT,
            sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, referred_by=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                   (user_id, username, referred_by))
    conn.commit()
    conn.close()

def update_points(user_id, points):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()

def get_points(user_id):
    user = get_user(user_id)
    return user[2] if user else 0

def update_last_active(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_active = ? WHERE user_id = ?", 
                   (datetime.now(), user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, points FROM users")
    users = cursor.fetchall()
    conn.close()
    return users

def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(points) FROM users")
    total_points = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM sms_history WHERE status LIKE '%success%'")
    total_sms = cursor.fetchone()[0]
    
    conn.close()
    return {
        'users': total_users,
        'points': total_points,
        'sms_sent': total_sms
    }

def log_sms(user_id, to_number, message, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO sms_history (user_id, to_number, message, status)
        VALUES (?, ?, ?, ?)
    """, (user_id, to_number, message, status))
    conn.commit()
    conn.close()

# ==================== Helper ====================
def is_admin(user_id):
    return user_id in ADMIN_IDS

async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        channel_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        group_member = await context.bot.get_chat_member(GROUP_ID, user_id)
        
        if channel_member.status in ['left', 'kicked'] or group_member.status in ['left', 'kicked']:
            keyboard = [
                [InlineKeyboardButton("📢 চ্যানেল জয়েন করুন", url=f"https://t.me/{CHANNEL_ID[1:]}")],
                [InlineKeyboardButton("👥 গ্রুপ জয়েন করুন", url=f"https://t.me/c/{GROUP_ID[4:]}")],
            ]
            await update.message.reply_text(
                "⚠️ বট ব্যবহার করতে প্রথমে চ্যানেল ও গ্রুপে জয়েন করুন!\n\n"
                "জয়েন করার পর আবার /start দিন।",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return False
    except Exception as e:
        print(f"Membership check error: {e}")
        return False
    
    return True

# ==================== User Commands ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    
    update_last_active(user_id)
    
    # রেফারেল চেক
    if context.args and context.args[0].startswith("ref_"):
        try:
            referred_by = int(context.args[0].split("_")[1])
            if referred_by != user_id and get_user(referred_by):
                update_points(referred_by, POINTS_PER_REFERRAL)
                try:
                    await context.bot.send_message(
                        referred_by,
                        f"🎉 অভিনন্দন! নতুন রেফার থেকে আপনি {POINTS_PER_REFERRAL} পয়েন্ট পেয়েছেন!"
                    )
                except:
                    pass
        except:
            pass
    
    if not await check_membership(update, context):
        return
    
    if not get_user(user_id):
        add_user(user_id, username)
        update_points(user_id, 3)  # Welcome bonus
    
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    points = get_points(user_id)
    
    admin_cmds = ""
    if is_admin(user_id):
        admin_cmds = "\n\n🔐 ADMIN COMMANDS:\n/admin /broadcast /stats /users /addpoints"
    
    await update.message.reply_text(
        f"👋 স্বাগতম {username}!\n\n"
        f"💰 আপনার পয়েন্ট: {points}\n"
        f"🔗 রেফার লিংক:\n`{ref_link}`\n\n"
        f"📌 কমান্ডসমূহ:\n"
        f"/sms +8801XXX মেসেজ - SMS পাঠান\n"
        f"/balance - পয়েন্ট দেখুন\n"
        f"/refer - রেফার লিংক\n"
        f"/history - SMS হিস্টরি"
        f"{admin_cmds}\n\n"
        f"⚡ প্রতি রেফারে {POINTS_PER_REFERRAL} পয়েন্ট পাবেন!",
        parse_mode='Markdown'
    )

async def send_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_last_active(user_id)
    
    if not await check_membership(update, context):
        return
    
    points = get_points(user_id)
    if points < POINTS_PER_SMS:
        ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        await update.message.reply_text(
            f"⚠️ পর্যাপ্ত পয়েন্ট নেই!\n\n"
            f"💰 বর্তমান পয়েন্ট: {points}\n"
            f"🔗 রেফার করুন:\n`{ref_link}`",
            parse_mode='Markdown'
        )
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ সঠিক ফরম্যাট:\n/sms +8801XXXXXXXXX আপনার মেসেজ"
        )
        return
    
    to_number = context.args[0]
    message = " ".join(context.args[1:])
    
    try:
        response = requests.post('https://textbelt.com/text', {
            'phone': to_number,
            'message': message,
            'key': 'textbelt',
        }, timeout=10)
        
        result = response.json()
        
        if result.get('success'):
            update_points(user_id, -POINTS_PER_SMS)
            new_balance = get_points(user_id)
            log_sms(user_id, to_number, message, 'success')
            
            await update.message.reply_text(
                f"✅ SMS সফলভাবে পাঠানো হয়েছে!\n"
                f"📱 নম্বর: {to_number}\n"
                f"💰 বাকি পয়েন্ট: {new_balance}"
            )
        else:
            log_sms(user_id, to_number, message, 'failed')
            await update.message.reply_text(
                f"❌ SMS পাঠাতে ব্যর্থ!\n"
                f"কারণ: {result.get('error', 'Unknown error')}"
            )
    except Exception as e:
        log_sms(user_id, to_number, message, 'error')
        await update.message.reply_text(f"❌ এরর: {str(e)}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = get_points(user_id)
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    
    await update.message.reply_text(
        f"💰 আপনার পয়েন্ট: {points}\n\n"
        f"🔗 রেফার লিংক:\n`{ref_link}`",
        parse_mode='Markdown'
    )

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    
    await update.message.reply_text(
        f"🔗 আপনার রেফার লিংক:\n`{ref_link}`\n\n"
        f"✨ প্রতি রেফারে {POINTS_PER_REFERRAL} পয়েন্ট পাবেন!",
        parse_mode='Markdown'
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT to_number, message, sent_date, status 
        FROM sms_history WHERE user_id = ? 
        ORDER BY sent_date DESC LIMIT 10
    """, (user_id,))
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        await update.message.reply_text("📭 কোনো SMS হিস্টরি নেই।")
        return
    
    text = "📜 আপনার শেষ ১০টি SMS:\n\n"
    for rec in records:
        emoji = "✅" if "success" in rec[3] else "❌"
        msg_preview = rec[1][:30] + "..." if len(rec[1]) > 30 else rec[1]
        text += f"{emoji} {rec[0]}\n📝 {msg_preview}\n🕐 {rec[2]}\n\n"
    
    await update.message.reply_text(text)

# ==================== ADMIN Commands ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ শুধুমাত্র Admin এই কমান্ড ব্যবহার করতে পারবেন!")
        return
    
    stats = get_stats()
    
    await update.message.reply_text(
        f"🔐 ADMIN PANEL\n\n"
        f"👥 মোট ইউজার: {stats['users']}\n"
        f"💰 মোট পয়েন্ট: {stats['points']}\n"
        f"📱 পাঠানো SMS: {stats['sms_sent']}\n\n"
        f"📌 কমান্ডসমূহ:\n"
        f"/stats - বিস্তারিত পরিসংখ্যান\n"
        f"/users - ইউজার লিস্ট\n"
        f"/addpoints [user_id] [points] - পয়েন্ট যোগ\n"
        f"/broadcast - সবাইকে SMS পাঠান"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    stats = get_stats()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(join_date) = DATE('now')")
    today_users = cursor.fetchone()[0]
    conn.close()
    
    await update.message.reply_text(
        f"📊 SYSTEM STATISTICS\n\n"
        f"👥 মোট ইউজার: {stats['users']}\n"
        f"🆕 আজকের নতুন ইউজার: {today_users}\n"
        f"💰 মোট পয়েন্ট: {stats['points']}\n"
        f"📱 মোট SMS: {stats['sms_sent']}"
    )

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    users = get_all_users()[:20]
    
    text = "👥 USER LIST (Top 20 by Points):\n\n"
    for idx, u in enumerate(users, 1):
        text += f"{idx}. ID: {u[0]}\n   @{u[1] or 'No username'}\n   💰 {u[2]} points\n\n"
    
    await update.message.reply_text(text)

async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ সঠিক ফরম্যাট:\n"
            "/addpoints [user_id] [points]\n\n"
            "উদাহরণ: /addpoints 123456789 50"
        )
        return
    
    try:
        target_user = int(context.args[0])
        points = int(context.args[1])
        
        if not get_user(target_user):
            await update.message.reply_text("❌ ইউজার খুঁজে পাওয়া যায়নি!")
            return
        
        update_points(target_user, points)
        
        await update.message.reply_text(
            f"✅ সফলভাবে {points} পয়েন্ট যোগ করা হয়েছে!\n"
            f"ইউজার ID: {target_user}"
        )
        
        try:
            await context.bot.send_message(
                target_user,
                f"🎁 Admin আপনাকে {points} পয়েন্ট দিয়েছেন!\n"
                f"💰 নতুন ব্যালেন্স: {get_points(target_user)}"
            )
        except:
            pass
            
    except ValueError:
        await update.message.reply_text("❌ ভুল ফরম্যাট! শুধুমাত্র সংখ্যা ব্যবহার করুন।")

# ==================== BROADCAST ====================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return ConversationHandler.END
    
    await update.message.reply_text(
        "📢 BROADCAST SMS TO ALL USERS\n\n"
        "ফরম্যাট: +নম্বর | মেসেজ\n\n"
        "উদাহরণ:\n"
        "+8801712345678 | এটি সবার জন্য একটি টেস্ট মেসেজ\n\n"
        "❌ বাতিল করতে /cancel টাইপ করুন"
    )
    
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    if "|" not in message:
        await update.message.reply_text(
            "❌ ভুল ফরম্যাট!\n\n"
            "সঠিক: +8801XXXXXXXXX | আপনার মেসেজ"
        )
        return BROADCAST_MESSAGE
    
    parts = message.split("|", 1)
    to_number = parts[0].strip()
    sms_text = parts[1].strip()
    
    users = get_all_users()
    total = len(users)
    
    await update.message.reply_text(
        f"📤 {total} জন ইউজারের কাছে SMS পাঠানো হচ্ছে...\n"
        f"⏳ অনুগ্রহ করে অপেক্ষা করুন..."
    )
    
    success = 0
    failed = 0
    
    for user in users:
        user_id = user[0]
        if get_points(user_id) >= POINTS_PER_SMS:
            try:
                response = requests.post('https://textbelt.com/text', {
                    'phone': to_number,
                    'message': sms_text,
                    'key': 'textbelt',
                }, timeout=5)
                
                if response.json().get('success'):
                    update_points(user_id, -POINTS_PER_SMS)
                    log_sms(user_id, to_number, sms_text, 'broadcast_success')
                    success += 1
                else:
                    failed += 1
                    log_sms(user_id, to_number, sms_text, 'broadcast_failed')
            except:
                failed += 1
        else:
            failed += 1
    
    await update.message.reply_text(
        f"✅ BROADCAST সম্পন্ন হয়েছে!\n\n"
        f"📊 মোট ইউজার: {total}\n"
        f"✅ সফল: {success}\n"
        f"❌ ব্যর্থ: {failed}"
    )
    
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Broadcast বাতিল করা হয়েছে।")
    return ConversationHandler.END

# ==================== MAIN ====================
def main():
    print("🔄 Initializing database...")
    init_db()
    
    print("🤖 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sms", send_sms))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("refer", refer))
    app.add_handler(CommandHandler("history", history))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CommandHandler("addpoints", add_points_command))
    
    # Broadcast handler
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)]
        },
        fallbacks=[CommandHandler("cancel", cancel_broadcast)]
    )
    app.add_handler(broadcast_handler)
    
    print("✅ Bot is running successfully!")
    print(f"👥 Admin IDs: {ADMIN_IDS}")
    app.run_polling()

if __name__ == "__main__":
    main()
