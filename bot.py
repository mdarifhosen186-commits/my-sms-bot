import sqlite3
import requests
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from datetime import datetime

# ==================== Environment Variables ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8947264322:AAGAfmgfzPxCzq_lHaAiSImEPteW20KIF78")
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Tg_Petshala")
GROUP_ID = os.environ.get("GROUP_ID", "@Tg_Petshalaa")

# Admin IDs (comma-separated)
admin_ids_str = os.environ.get("ADMIN_IDS", "1771051433")
ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip()]

POINTS_PER_REFERRAL = int(os.environ.get("POINTS_PER_REFERRAL", "5"))
POINTS_PER_SMS = int(os.environ.get("POINTS_PER_SMS", "1"))

BROADCAST_MESSAGE = 1

# ==================== Database Functions ====================
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0,
        referred_by INTEGER, join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS sms_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, to_number TEXT,
        message TEXT, sent_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, status TEXT)''')
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(user_id, username, referred_by=None):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                   (user_id, username, referred_by))
    conn.commit()
    conn.close()

def update_points(user_id, points):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (points, user_id))
    conn.commit()
    conn.close()

def get_points(user_id):
    user = get_user(user_id)
    return user[2] if user else 0

def update_last_active(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (datetime.now(), user_id))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, points FROM users ORDER BY points DESC")
    users = cursor.fetchall()
    conn.close()
    return users

def get_stats():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(points) FROM users")
    total_points = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM sms_history WHERE status LIKE '%success%'")
    total_sms = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE DATE(join_date) = DATE('now')")
    today_users = cursor.fetchone()[0]
    conn.close()
    return {'users': total_users, 'points': total_points, 'sms_sent': total_sms, 'today_users': today_users}

def log_sms(user_id, to_number, message, status):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sms_history (user_id, to_number, message, status) VALUES (?, ?, ?, ?)",
                   (user_id, to_number, message, status))
    conn.commit()
    conn.close()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# ==================== Helper Functions ====================
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        channel_member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        group_member = await context.bot.get_chat_member(GROUP_ID, user_id)
        if channel_member.status in ['left', 'kicked'] or group_member.status in ['left', 'kicked']:
            keyboard = [[InlineKeyboardButton("📢 চ্যানেল", url=f"https://t.me/{CHANNEL_ID[1:]}")],
                       [InlineKeyboardButton("👥 গ্রুপ", url=f"https://t.me/{GROUP_ID[1:]}")]]
            await update.message.reply_text("⚠️ প্রথমে চ্যানেল ও গ্রুপে জয়েন করুন!\n\nজয়েন করার পর /start দিন।",
                                           reply_markup=InlineKeyboardMarkup(keyboard))
            return False
    except Exception as e:
        print(f"Membership check error: {e}")
        return False
    return True

# ==================== Command Handlers ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "User"
    update_last_active(user_id)
    
    if context.args and context.args[0].startswith("ref_"):
        try:
            referred_by = int(context.args[0].split("_")[1])
            if referred_by != user_id and get_user(referred_by):
                update_points(referred_by, POINTS_PER_REFERRAL)
                try:
                    await context.bot.send_message(referred_by, f"🎉 নতুন রেফার! +{POINTS_PER_REFERRAL} পয়েন্ট")
                except:
                    pass
        except:
            pass
    
    if not await check_membership(update, context):
        return
    
    if not get_user(user_id):
        add_user(user_id, username)
        update_points(user_id, 3)
    
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    points = get_points(user_id)
    admin_cmds = "\n\n🔐 ADMIN:\n/admin /broadcast /stats /users /addpoints" if is_admin(user_id) else ""
    
    await update.message.reply_text(
        f"👋 স্বাগতম {username}!\n\n💰 পয়েন্ট: {points}\n🔗 রেফার:\n`{ref_link}`\n\n"
        f"📌 কমান্ড:\n/sms +8801XXX মেসেজ\n/balance /refer /history{admin_cmds}\n\n⚡ প্রতি রেফারে {POINTS_PER_REFERRAL} পয়েন্ট!",
        parse_mode='Markdown')

async def send_sms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    update_last_active(user_id)
    if not await check_membership(update, context):
        return
    
    points = get_points(user_id)
    if points < POINTS_PER_SMS:
        ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
        await update.message.reply_text(f"⚠️ পয়েন্ট নেই!\n\n💰 বর্তমান: {points}\n🔗 রেফার:\n`{ref_link}`", parse_mode='Markdown')
        return
    
    if len(context.args) < 2:
        await update.message.reply_text("❌ Format: /sms +8801XXX মেসেজ")
        return
    
    to_number = context.args[0]
    message = " ".join(context.args[1:])
    
    try:
        response = requests.post('https://textbelt.com/text', {'phone': to_number, 'message': message, 'key': 'textbelt'}, timeout=10)
        result = response.json()
        
        if result.get('success'):
            update_points(user_id, -POINTS_PER_SMS)
            new_balance = get_points(user_id)
            log_sms(user_id, to_number, message, 'success')
            await update.message.reply_text(f"✅ SMS পাঠানো হয়েছে!\n📱 {to_number}\n💰 বাকি: {new_balance}")
        else:
            log_sms(user_id, to_number, message, 'failed')
            await update.message.reply_text(f"❌ ব্যর্থ: {result.get('error', 'Unknown')}")
    except Exception as e:
        log_sms(user_id, to_number, message, 'error')
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = get_points(user_id)
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    await update.message.reply_text(f"💰 পয়েন্ট: {points}\n\n🔗 রেফার:\n`{ref_link}`", parse_mode='Markdown')

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref_link = f"https://t.me/{context.bot.username}?start=ref_{user_id}"
    await update.message.reply_text(f"🔗 রেফার লিংক:\n`{ref_link}`\n\n✨ প্রতি রেফারে {POINTS_PER_REFERRAL} পয়েন্ট!", parse_mode='Markdown')

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT to_number, message, sent_date, status FROM sms_history WHERE user_id = ? ORDER BY sent_date DESC LIMIT 10", (user_id,))
    records = cursor.fetchall()
    conn.close()
    
    if not records:
        await update.message.reply_text("📭 কোনো হিস্টরি নেই")
        return
    
    text = "📜 শেষ ১০টি SMS:\n\n"
    for rec in records:
        emoji = "✅" if "success" in rec[3] else "❌"
        text += f"{emoji} {rec[0]} - {rec[2]}\n"
    await update.message.reply_text(text)

# ==================== Admin Commands ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only!")
        return
    stats = get_stats()
    await update.message.reply_text(
        f"🔐 ADMIN PANEL\n━━━━━━━━━━━━\n\n👥 ইউজার: {stats['users']}\n🆕 আজকের: {stats['today_users']}\n"
        f"💰 পয়েন্ট: {stats['points']}\n📱 SMS: {stats['sms_sent']}\n\n"
        f"📌 /stats /users /addpoints /broadcast")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    stats = get_stats()
    await update.message.reply_text(f"📊 STATS\n\n👥 {stats['users']}\n🆕 {stats['today_users']}\n💰 {stats['points']}\n📱 {stats['sms_sent']}")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    users = get_all_users()[:20]
    text = "👥 TOP 20:\n\n"
    for idx, u in enumerate(users, 1):
        text += f"{idx}. {u[0]} | @{u[1] or 'N/A'} | 💰{u[2]}\n"
    await update.message.reply_text(text)

async def add_points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) != 2:
        await update.message.reply_text("❌ Format: /addpoints USER_ID POINTS")
        return
    
    try:
        target_user = int(context.args[0])
        points = int(context.args[1])
        if not get_user(target_user):
            await update.message.reply_text("❌ User not found!")
            return
        update_points(target_user, points)
        await update.message.reply_text(f"✅ Added {points} points to {target_user}")
        try:
            await context.bot.send_message(target_user, f"🎁 Admin gave you {points} points!")
        except:
            pass
    except ValueError:
        await update.message.reply_text("❌ Invalid format!")

# ==================== Broadcast ====================
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text("📢 BROADCAST\n\nFormat: +নম্বর | মেসেজ\n\n/cancel to stop")
    return BROADCAST_MESSAGE

async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    if "|" not in message:
        await update.message.reply_text("❌ Wrong format!")
        return BROADCAST_MESSAGE
    
    parts = message.split("|", 1)
    to_number = parts[0].strip()
    sms_text = parts[1].strip()
    users = get_all_users()
    total = len(users)
    
    await update.message.reply_text(f"📤 Sending to {total} users...")
    
    success = 0
    failed = 0
    for user in users:
        user_id = user[0]
        if get_points(user_id) >= POINTS_PER_SMS:
            try:
                response = requests.post('https://textbelt.com/text', {'phone': to_number, 'message': sms_text, 'key': 'textbelt'}, timeout=5)
                if response.json().get('success'):
                    update_points(user_id, -POINTS_PER_SMS)
                    log_sms(user_id, to_number, sms_text, 'broadcast_success')
                    success += 1
                else:
                    failed += 1
            except:
                failed += 1
        else:
            failed += 1
    
    await update.message.reply_text(f"✅ COMPLETE!\n\nTotal: {total}\n✅ {success}\n❌ {failed}")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled")
    return ConversationHandler.END

# ==================== Main ====================
def main():
    print("━━━━━━━━━━━━━━━━━━━━")
    print("🤖 SMS REFER BOT")
    print("━━━━━━━━━━━━━━━━━━━━")
    print(f"📢 Channel: {CHANNEL_ID}")
    print(f"👥 Group: {GROUP_ID}")
    print(f"👨‍💼 Admins: {ADMIN_IDS}")
    print(f"⚡ Points/Referral: {POINTS_PER_REFERRAL}")
    print(f"💰 Points/SMS: {POINTS_PER_SMS}")
    print("━━━━━━━━━━━━━━━━━━━━")
    
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sms", send_sms))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("refer", refer))
    app.add_handler(CommandHandler("history", history))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_list))
    app.add_handler(CommandHandler("addpoints", add_points_command))
    
    broadcast_handler = ConversationHandler(
        entry_points=[CommandHandler("broadcast", broadcast_start)],
        states={BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message)]},
        fallbacks=[CommandHandler("cancel", cancel_broadcast)])
    app.add_handler(broadcast_handler)
    
    print("✅ Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
