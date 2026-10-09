import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import database as db

# تنظیمات لوگ
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔑 توکن اختصاصی ربات گروه BORED
TOKEN = "8976851857:AAFhA50ROdFvmSrRCvQOV8Qqbd-4KW5SfIg"

# مقداردهی اولیه دیتابیس
db.init_db()

# ----------------- بررسی دسترسی مدیر -----------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

# ----------------- پنل مدیریت شیشه‌ای -----------------
def build_panel_keyboard(chat_id):
    s = db.get_settings(chat_id)
    keyboard = [
        [
            InlineKeyboardButton(f"🔗 قفل لینک: {'✅' if s['lock_links'] else '❌'}", callback_data="toggle_lock_links"),
            InlineKeyboardButton(f"🤖 کپچای ورودی: {'✅' if s['captcha_enabled'] else '❌'}", callback_data="toggle_captcha_enabled")
        ],
        [
            InlineKeyboardButton(f"🤬 فیلتر الفاظ: {'✅' if s['lock_badwords'] else '❌'}", callback_data="toggle_lock_badwords"),
            InlineKeyboardButton(f"⚡ ضد اسپم: {'✅' if s['lock_spam'] else '❌'}", callback_data="toggle_lock_spam")
        ],
        [
            InlineKeyboardButton("❌ بستن پنل", callback_data="close_panel")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /panel برای باز کردن پنل مدیریت شیشه‌ای"""
    if update.effective_chat.type == "private":
        await update.message.reply_text("این دستور فقط داخل گروه قابل استفاده است.")
        return

    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ این دستور مخصوص مدیران گروه bored است!")
        return

    chat_id = update.effective_chat.id
    reply_markup = build_panel_keyboard(chat_id)
    await update.message.reply_text(
        "🎛 **پنل مدیریت هوشمند گروه BORED**\n\nبرای تغییر تنظیمات روی دکمه‌های زیر کلیک کنید:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک روی دکمه‌های شیشه‌ای پنل"""
    query = update.callback_query
    chat_id = query.message.chat.id
    user_id = query.from_user.id

    # بررسی مدیر بودن کلیک‌کننده
    member = await context.bot.get_chat_member(chat_id, user_id)
    if member.status not in ['administrator', 'creator']:
        await query.answer("⚠️ شما مدیر نیستید!", show_alert=True)
        return

    data = query.data
    if data == "close_panel":
        await query.message.delete()
        return

    if data.startswith("toggle_"):
        setting_name = data.replace("toggle_", "")
        db.toggle_setting(chat_id, setting_name)
        await query.answer("تغییرات اعمال شد.")
        reply_markup = build_panel_keyboard(chat_id)
        await query.message.edit_reply_markup(reply_markup=reply_markup)

# ----------------- کپچا و خوش‌آمدگویی -----------------
async def welcome_and_captcha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    settings = db.get_settings(chat_id)

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            continue

        if settings['captcha_enabled']:
            # محدود کردن دسترسی کاربر تا زمان حل کپچا
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=member.id,
                permissions=ChatPermissions(can_send_messages=False)
            )

            keyboard = [[
                InlineKeyboardButton("✅ من ربات نیستم (تأیید)", callback_data=f"verify_captcha_{member.id}")
            ]]
            markup = InlineKeyboardMarkup(keyboard)

            msg = await update.message.reply_text(
                f"سلام {member.full_name} عزیز! 🌹\n"
                f"به گروه **bored** خوش آمدید.\n\n"
                f"⚠️ برای ارسال پیام، روی دکمه زیر کلیک کنید تا انسان بودن شما تأیید شود:",
                reply_markup=markup,
                parse_mode="Markdown"
            )
        else:
            welcome_text = settings['welcome_msg'].format(name=member.full_name)
            await update.message.reply_text(welcome_text)

async def captcha_verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    target_user_id = int(query.data.split("_")[-1])

    if user_id != target_user_id:
        await query.answer("⚠️ این دکمه مخصوص شما نیست!", show_alert=True)
        return

    # باز کردن دسترسی‌های کاربر
    full_permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=full_permissions)
    await query.answer("✅ تأیید شدید! خوش آمدید.")
    await query.message.delete()

# ----------------- فیلتر هوشمند پیام‌ها (ضد لینک / الفاظ) -----------------
async def message_filter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    settings = db.get_settings(chat_id)

    # اگر کاربر مدیر باشد، فیلتر اعمال نمی‌شود
    if await is_admin(update, context):
        return

    text = update.message.text

    # ۱. فیلتر لینک
    if settings['lock_links']:
        has_url = any(e.type in ["url", "text_link"] for e in (update.message.entities or []))
        if has_url or "t.me/" in text or "http" in text:
            await update.message.delete()
            warn_num = db.add_warn(chat_id, user_id)
            if warn_num >= settings['max_warns']:
                await context.bot.ban_chat_member(chat_id, user_id)
                db.reset_warns(chat_id, user_id)
                await context.bot.send_message(chat_id, f"🚫 کاربر @{update.effective_user.username or user_id} به دلیل ارسال لینک و رسیدن اخطارها به حد مجاز، بن شد.")
            else:
                await context.bot.send_message(chat_id, f"⚠️ کاربر @{update.effective_user.username or user_id}، ارسال لینک مجاز نیست! (اخطار {warn_num}/{settings['max_warns']})")
            return

# ----------------- دستورات مدیریتی متنی -----------------
async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("لطفاً این دستور را روی پیام کاربر موردنظر ریپلای کنید.")
        return

    chat_id = update.effective_chat.id
    target_user = update.message.reply_to_message.from_user
    settings = db.get_settings(chat_id)

    warn_num = db.add_warn(chat_id, target_user.id)
    if warn_num >= settings['max_warns']:
        await context.bot.ban_chat_member(chat_id, target_user.id)
        db.reset_warns(chat_id, target_user.id)
        await update.message.reply_text(f"🚫 کاربر {target_user.full_name} به دلیل دریافت {warn_num} اخطار از گروه بن شد.")
    else:
        await update.message.reply_text(f"⚠️ به کاربر {target_user.full_name} یک اخطار داده شد. ({warn_num}/{settings['max_warns']})")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("لطفاً این دستور را روی پیام کاربر موردنظر ریپلای کنید.")
        return
    target_user = update.message.reply_to_message.from_user
    await context.bot.ban_chat_member(update.effective_chat.id, target_user.id)
    await update.message.reply_text(f"🚫 کاربر {target_user.full_name} مسدود شد.")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("لطفاً این دستور را روی پیام کاربر موردنظر ریپلای کنید.")
        return
    target_user = update.message.reply_to_message.from_user
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        target_user.id,
        permissions=ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text(f"🤐 کاربر {target_user.full_name} سکوت شد.")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("لطفاً این دستور را روی پیام کاربر موردنظر ریپلای کنید.")
        return
    target_user = update.message.reply_to_message.from_user
    full_permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    await context.bot.restrict_chat_member(update.effective_chat.id, target_user.id, permissions=full_permissions)
    await update.message.reply_text(f"🔊 حالت سکوت کاربر {target_user.full_name} برداشته شد.")

# ----------------- راهنما و اجرا -----------------
async def start_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🤖 **ربات مدیریت پیشرفته گروه BORED**\n\n"
        "🛠 **دستورات مدیریتی:**\n"
        "🔹 `/panel` : باز کردن پنل تنظیمات شیشه‌ای\n"
        "🔹 `/warn` : دادن اخطار به کاربر (با ریپلای)\n"
        "🔹 `/ban` : مسدود کردن کاربر (با ریپلای)\n"
        "🔹 `/mute` : سکوت کردن کاربر (با ریپلای)\n"
        "🔹 `/unmute` : برداشتن حالت سکوت (با ریپلای)\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # ثبت Handlers
    app.add_handler(CommandHandler("start", start_help))
    app.add_handler(CommandHandler("help", start_help))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("warn", warn_user))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("mute", mute_user))
    app.add_handler(CommandHandler("unmute", unmute_user))

    # دکمه‌های شیشه‌ای
    app.add_handler(CallbackQueryHandler(panel_callback, pattern="^toggle_|^close_panel$"))
    app.add_handler(CallbackQueryHandler(captcha_verify_callback, pattern="^verify_captcha_"))

    # خوش‌آمدگویی و پیام‌ها
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_and_captcha))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_filter))

    print("⚡ ربات اختصاصی گروه BORED روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    main()