from rubpy import Client, filters
from rubpy.types import Update
from re import search , IGNORECASE
from random import shuffle ,choice ,randint
from sqlite3 import connect
from jdatetime import date
from datetime import datetime ,timedelta

conn = connect('data.db',check_same_thread=False)
cursor = conn.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS user_profiles (
    user_guid TEXT,
    chat_guid TEXT,
    original_text TEXT,
    PRIMARY KEY (user_guid, chat_guid)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS warning_settings (
    chat_guid TEXT PRIMARY KEY,
    max_warnings INTEGER DEFAULT 3
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS welcome_messages (
    chat_guid TEXT PRIMARY KEY,
    message TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS mutes (
    user_guid TEXT,
    chat_guid TEXT,
    until INTEGER, -- زمان پایان سکوت به صورت timestamp (ثانیه)
    PRIMARY KEY (user_guid, chat_guid)
)
""")


# ایجاد جدول لقب‌ها اگر وجود نداشت
cursor.execute("""
CREATE TABLE IF NOT EXISTS titles (
    user_guid TEXT,
    chat_guid TEXT,
    title TEXT,
    PRIMARY KEY (user_guid, chat_guid)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS group_info (
    chat_guid TEXT PRIMARY KEY,
    owner_guid TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_guid TEXT,
    chat_guid TEXT,
    name TEXT,
    message_count INTEGER,
    PRIMARY KEY (user_guid, chat_guid)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS keyword_replies (
    chat_guid TEXT,
    keyword TEXT,
    reply TEXT,
    PRIMARY KEY (chat_guid, keyword)
)
""")

# جدول اخطار کاربران
cursor.execute("""
CREATE TABLE IF NOT EXISTS warnings (
    user_guid TEXT PRIMARY KEY,
    count INTEGER
)
""")
# در بخش ایجاد جداول دیتابیس (بالای کد)
cursor.execute("""
CREATE TABLE IF NOT EXISTS bot_status (
    chat_guid TEXT PRIMARY KEY,
    is_active INTEGER DEFAULT 0
)
""")


conn.commit()


active_games = {}
bot = Client(name='rubpy')

async def download_file(url, local_path):
    from aiohttp import ClientSession
    async with ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                content = await response.read()
                with open(local_path, 'wb') as f:
                    f.write(content)
                return True
            return False

async def restart_bot():
    """تابع ریستارت ربات برای محیط سرور"""
    try:
        
        from os import path
        from sys import exit
        from subprocess import Popen
        # اجرای اسکریپت ریستارت
        script_path = path.join(path.dirname(__file__), "restart.sh")
        Popen(["/bin/bash", script_path])
        exit(0)
    except Exception as e:
        print(f"Restart failed: {e}")
        exit(1)


    # تابع بررسی وضعیت ربات
async def is_bot_active(chat_guid):
    cursor.execute("SELECT is_active FROM bot_status WHERE chat_guid = ?", (chat_guid,))
    result = cursor.fetchone()
    return result[0] == 1 if result else False

async def is_special_admin(user_guid):
    return user_guid == "u0HXkpO07ea05449373fa9cfa8b81b65"
active_voice_chats = {}
async def tag_members(update: Update, limit=50):
    try:
        chat_guid = update.object_guid

        # دریافت لیست اعضا
        try:
            members = await bot.get_group_all_members(group_guid=chat_guid)
            if not members or not hasattr(members, 'in_chat_members'):
                await update.reply("❌ لیست اعضا دریافت نشد")
                return
        except Exception as e:
            await update.reply("❌ خطا در دریافت لیست اعضا")
            print(f"Error getting members: {str(e)}")
            return

        # دریافت 50 کاربر برتر از دیتابیس
        cursor.execute("""
            SELECT user_guid FROM stats 
            WHERE chat_guid = ? AND user_guid != ?
            ORDER BY message_count DESC 
            LIMIT ?
        """, (chat_guid, update.author_guid, limit))
        top_users = cursor.fetchall()
        top_user_guids = [row[0] for row in top_users] if top_users else []

        # ساخت لیست تگ‌ها
        mentions = []
        tagged_count = 0
        already_tagged = set()

        # اول کاربران پرکاربرد را تگ می‌کنیم (به جز خود کاربر)
        for user_guid in top_user_guids:
            if user_guid == update.author_guid:
                continue  # از تگ کردن خود کاربر جلوگیری می‌کنیم

            try:
                user_info = await bot.get_user_info(user_guid=user_guid)
                username = getattr(getattr(user_info, 'user', None), 'username', None)
                if username:
                    mentions.append(f"@{username}")
                else:
                    name = getattr(getattr(user_info, 'user', None), 'first_name', 'کاربر')
                    mentions.append(f"[{name}](mention:{user_guid})")
                tagged_count += 1
                already_tagged.add(user_guid)
            except Exception as e:
                print(f"Error tagging user {user_guid}: {str(e)}")
                continue

        # سپس بقیه اعضا را به ترتیب تصادفی تگ می‌کنیم (به جز خود کاربر)
        all_members = [m for m in getattr(members, 'in_chat_members', []) 
                      if m.member_guid not in already_tagged 
                      and m.member_guid != update.author_guid]

        shuffle(all_members)

        for member in all_members[:limit - tagged_count]:
            try:
                user_info = await bot.get_user_info(user_guid=member.member_guid)
                username = getattr(getattr(user_info, 'user', None), 'username', None)
                if username:
                    mentions.append(f"@{username}")
                else:
                    name = getattr(getattr(user_info, 'user', None), 'first_name', 'کاربر')
                    mentions.append(f"[{name}](mention:{member.member_guid})")
            except Exception as e:
                print(f"Error tagging member {member.member_guid}: {str(e)}")
                continue

        if not mentions:
            await update.reply("⚠️ هیچ کاربری برای تگ کردن یافت نشد")
            return

        # ارسال پیام تگ
        message = "👥 تگ اعضا:\n" + " ".join(mentions[:limit])  # محدودیت نهایی
        await update.reply(message)

    except Exception as e:
        await update.reply(f"❌ خطای سیستمی: لطفاً بعداً تلاش کنید")
        print(f"Error in tag_members: {str(e)}")
@bot.on_message_updates(filters.text)
async def updates(update: Update ):
    text = update.message.text.strip()
    name = await update.get_author(update.object_guid)
    user_guid = update.author_guid
    user_name = name.chat.last_message.author_title or "کاربر"
    chat_guid = update.object_guid  # شناسه گروه
    admin_or_not = await bot.user_is_admin(update.object_guid, update.author_object_guid)
    special_admin = await is_special_admin(update.author_guid)
    # --- مهم: مقداردهی پیش‌فرض تا UnboundLocalError پیش نیاد ---
    result = None
    # update stats
    cursor.execute("SELECT message_count FROM stats WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
    row = cursor.fetchone()
    if row:
        new_count = row[0] + 1
        cursor.execute("UPDATE stats SET message_count = ?, name = ? WHERE user_guid = ? AND chat_guid = ?",
                       (new_count, user_name, user_guid, chat_guid))
    else:
        cursor.execute("INSERT INTO stats (user_guid, chat_guid, name, message_count) VALUES (?, ?, ?, ?)",
                       (user_guid, chat_guid, user_name, 1))

    conn.commit()
    if text == "ربات روشن" and special_admin:
        cursor.execute("""
        INSERT OR REPLACE INTO bot_status (chat_guid, is_active)
        VALUES (?, 1)
        """, (chat_guid,))
        conn.commit()
        await update.reply("✅ ربات در این گروه فعال شد! @link4yu")

    elif text == "ربات خاموش" and special_admin:
        cursor.execute("""
            INSERT OR REPLACE INTO bot_status (chat_guid, is_active)
            VALUES (?, 0)
        """, (chat_guid,))
        conn.commit()
        await update.reply("🔴 ربات در این گروه غیرفعال شد! @link4yu")

        # در ابتدای تابع on_message_updates (قبل از پردازش هر پیام)
    if not await is_bot_active(update.object_guid):
            return

    if update.type == "AddedToGroup":
            cursor.execute("""
            INSERT OR IGNORE INTO bot_status (chat_guid, is_active)
            VALUES (?, 0)
            """, (update.object_guid,))
            conn.commit()
            await bot.send_message(
                update.object_guid,
                "🤖 ربات با موفقیت به گروه اضافه شد!\n"
                "برای فعال کردن دستورات از:\n"
                "`ربات روشن` استفاده کنید\n\n"
                "دستورات فقط توسط ادمین‌ها قابل اجرا هستند."
            )

    now_ts = int(datetime.now().timestamp())
    cursor.execute("SELECT until FROM mutes WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
    mute_data = cursor.fetchone()
    if mute_data:
        until = mute_data[0]
        if until is None or until > now_ts:
            await update.delete()
            return
        else:
            # سکوت تمام شده → حذف رکورد
            cursor.execute("DELETE FROM mutes WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
            conn.commit()


    if text in ["اپدیت", "update"] and await is_special_admin(update.author_guid):
            try:
                await update.reply("⏳ در حال دریافت آخرین نسخه از گیت‌هاب...")
                
                # URL فایل اصلی در گیت‌هاب
                github_url = "https://raw.githubusercontent.com/yasin115/rubypy/refs/heads/main/main.py"
                temp_file = "bot_new.py"
                success = await download_file(github_url, temp_file)
                
                if not success:
                    await update.reply("❌ خطا در دریافت فایل از گیت‌هاب")
                    return
                from os import replace,chmod
                # جایگزینی فایل فعلی
                current_file = __file__
                replace(temp_file, current_file)
                
                await update.reply("✅ اپدیت با موفقیت انجام شد! ربات در حال ریستارت...")
                
                # ایجاد فایل اسکریپت ریستارت
                restart_script = """
#!/bin/bash
sleep 3
nohup python passenger_wsgi.py > output.log 2>&1 &
                """
                
                with open("restart.sh", "w") as f:
                    f.write(restart_script)
                chmod("restart.sh", 0o755)  # اجازه اجرا
                
                # ریستارت ربات
                await restart_bot()
                
            except Exception as e:
                await update.reply(f"❌ خطا در فرآیند اپدیت: {str(e)}")
                print(f"Update error: {str(e)}")
        
    # ثبت اصل توسط ادمین (با ریپلای بر پیام کاربر - نسخه گروه‌بندی شده)
    if update.reply_message_id and text == "ثبت اصل":
        # بررسی ادمین بودن
        if not await bot.user_is_admin(chat_guid, user_guid):
            await update.reply("❌ فقط ادمین‌ها می‌توانند ثبت اصل انجام دهند")
            return

        try:
            # دریافت پیام اصلی که ریپلای شده
            replied_msg = await bot.get_messages_by_id(
                object_guid=update.object_guid,
                message_ids=[update.message.reply_to_message_id]
            )

            if not replied_msg or not hasattr(replied_msg, 'messages') or not replied_msg.messages:
                await update.reply("❌ پیام مورد نظر یافت نشد")
                return

            target_msg = replied_msg.messages[0]
            target_guid = target_msg.author_object_guid
            target_name = target_msg.author_title or "کاربر"

            # استخراج متن اصل از پیام کاربر
            original_text = target_msg.text

            if not original_text:
                await update.reply("❌ متن اصل کاربر خالی است")
                return

            # ذخیره در دیتابیس با در نظر گرفتن گروه
            cursor.execute("""
            INSERT OR REPLACE INTO user_profiles 
            (user_guid, chat_guid, original_text) 
            VALUES (?, ?, ?)
            """, (target_guid, chat_guid, original_text))
            conn.commit()

            await update.reply(f"✅ اصل {target_name} در این گروه با موفقیت ثبت شد:\n{original_text} ")

        except Exception as e:
            await update.reply("❌ خطا در پردازش پیام ریپلای شده")
            print(f"Error in ثبت اصل: {str(e)}")
    # مشاهده اصل (برای همه)
 # مشاهده اصل (با در نظر گرفتن گروه)
    elif update.reply_message_id and text == "اصل":
        try:
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            cursor.execute("""
            SELECT original_text FROM user_profiles 
            WHERE user_guid = ? AND chat_guid = ?
            """, (target_guid, chat_guid))
            result = cursor.fetchone()

            if result:
                await update.reply(f"📌 اصل {target_name} در این گروه:\n{result[0]}")
            else:
                await update.reply(f"ℹ️ برای {target_name} در این گروه اصل ثبت نشده است")

        except Exception as e:
            await update.reply("❌ خطا در دریافت اطلاعات")
            print(f"Error in مشاهده اصل: {str(e)}")
    # حذف اصل (فقط ادمین)
    elif update.reply_message_id and text == "حذف اصل":
        if not await bot.user_is_admin(chat_guid, user_guid):
            await update.reply("❌ فقط ادمین‌ها می‌توانند اصل را حذف کنند")
            return

        target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
        target_guid = target.user.user_guid
        target_name = target.user.first_name or "کاربر"

        cursor.execute("DELETE FROM user_profiles WHERE user_guid = ?", (target_guid,))
        conn.commit()

        await update.reply(f"✅ اصل {target_name} حذف شد")
    if text == "کال" and (admin_or_not or special_admin):
        try:
            # بررسی وجود ویس چت فعال
            if chat_guid in active_voice_chats:
                await update.reply("⚠️ از قبل یک ویس چت فعال دارید!")
                return

            result = await bot.create_group_voice_chat(group_guid=chat_guid)

            # ذخیره اطلاعات ویس چت
            active_voice_chats[chat_guid] = {
                'voice_chat_id': result.voice_chat_id,
                'title': 'ویس چت گروه'
            }

            await update.reply("🎤 ویس چت با موفقیت ایجاد شد!\nبرای پیوستن از دکمه ویس چت در گروه استفاده کنید.")
        except Exception as e:
            await update.reply(f"❌ خطا در ایجاد ویس چت: {str(e)}")

    if text.startswith("//"):
        parts = text.split()[1:]
        query = " ".join(parts)
        
        # ارسال پیام اولیه
        msg = await bot.send_message(
            object_guid=update.object_guid,
            text='لطفا کمی صبر کنید...',
            reply_to_message_id=update.message_id
        )
        
        object_guid = msg.object_guid
        message_id = msg.message_id
        
        try:
            from aiohttp import ClientSession, ClientTimeout
            timeout = ClientTimeout(total=30)  # تنظیم تایم‌اوت 30 ثانیه
            
            async with ClientSession(timeout=timeout) as session:
                async with session.get(
                    'https://shython-apis.liara.run/ai',
                    params={'prompt': query}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        # ویرایش پیام با استفاده از کلاینت اصلی
                        await bot.edit_message(
                            object_guid=object_guid,
                            message_id=message_id,
                            text=data['data']
                        )
                    else:
                        await bot.edit_message(
                            object_guid=object_guid,
                            message_id=message_id,
                            text='⚠ خطا در دریافت پاسخ از سرور'
                        )
                        
        except Exception as e:
            # نمایش خطا با ویرایش همان پیام
            error_msg = f'⚠ خطا: {str(e)}'[:4000]  # محدودیت طول پیام
            await bot.edit_message(
                object_guid=object_guid,
                message_id=message_id,
                text=error_msg
            )
    if text == "تایم":
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        await update.reply(f"⏰ ساعت فعلی: {current_time}")

    if text == "تاریخ":
        today_jalali = date.today()
        date_str = today_jalali.strftime("%Y/%m/%d")
        await update.reply(f"📅 تاریخ امروز (شمسی): {date_str}")


        # سکوت عادی یا زمان‌دار
    if update.reply_message_id and text.startswith("سکوت"):
        if (admin_or_not or special_admin):
            target = await update.get_reply_author(chat_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            # Check if target is admin or special user
            target_is_admin = await bot.user_is_admin(chat_guid, target_guid)
            target_is_special = await is_special_admin(target_guid)
            if target_is_admin or target_is_special:
                await update.reply("🤖 این کاربر قابل سکوت کردن نیست!")
                
                return

            parts = text.split()
            until_ts = None
            if len(parts) == 2 and parts[1].isdigit():
                minutes = int(parts[1])
                until_ts = int((datetime.now() + timedelta(minutes=minutes)).timestamp())

            cursor.execute("INSERT OR REPLACE INTO mutes (user_guid, chat_guid, until) VALUES (?, ?, ?)",
                        (target_guid, chat_guid, until_ts))
            conn.commit()

            if until_ts:
                await update.reply(f"🔇 {target_name} به مدت {minutes} دقیقه ساکت شد.")
            else:
                await update.reply(f"🔇 {target_name} در این گروه ساکت شد (دائمی).")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند سکوت بدهند.")
    # حذف سکوت
    elif text == "لیست سکوت" and (admin_or_not or special_admin):  # فقط ادمین‌ها می‌توانند لیست را ببینند
        try:
            now_ts = int(datetime.now().timestamp())

            # دریافت لیست کاربران سکوت شده در این گروه (هم دائمی و هم موقت)
            cursor.execute("""
                SELECT user_guid, until FROM mutes 
                WHERE chat_guid = ? AND (until IS NULL OR until > ?)
                ORDER BY until
            """, (chat_guid, now_ts))

            muted_users = cursor.fetchall()

            if not muted_users:
                await update.reply("🔊 هیچ کاربری در حال حاضر سکوت نشده است.")
                return

            message = " 🔇 لیست کاربران سکوت شده:\n\n"

            for user_guid, until_ts in muted_users:
                user_info = await bot.get_user_info(user_guid=user_guid)
                username = getattr(getattr(user_info, 'user', None), 'username', None)
                name = getattr(getattr(user_info, 'user', None), 'first_name', 'کاربر')

                if until_ts is None:
                    mute_status = "🔴 دائمی"
                else:
                    remaining_minutes = (until_ts - now_ts) // 60
                    mute_status = f"⏳ {remaining_minutes} دقیقه باقی‌مانده"

                if username:
                    message += f"➖ @{username} ({mute_status})\n"
                else:
                    message += f"➖ {name} ({mute_status})\n"

            await update.reply(message)

        except Exception as e:
            await update.reply("❌ خطا در دریافت لیست سکوت‌شده‌ها")
            print(f"Error in لیست سکوت: {str(e)}")
    if update.reply_message_id and text == "حذف سکوت":
        
        if (admin_or_not or special_admin):
            target = await update.get_reply_author(chat_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            cursor.execute("DELETE FROM mutes WHERE user_guid = ? AND chat_guid = ?", (target_guid, chat_guid))
            conn.commit()
            await update.reply(f"🔊 سکوت {target_name} برداشته شد.")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند سکوت کاربر را بردارند.")

    if text.startswith("ثبت پاسخ "):
        if (admin_or_not or special_admin):
            try:
                # حذف بخش ابتدایی دستور
                data = text.replace("ثبت پاسخ ", "", 1)
                # جدا کردن کلمه و پاسخ با اولین فاصله
                keyword, reply_text = data.split(" ", 1)

                cursor.execute("REPLACE INTO keyword_replies (chat_guid, keyword, reply) VALUES (?, ?, ?)", 
                            (chat_guid, keyword, reply_text))
                conn.commit()

                await update.reply(f"✅ پاسخ کلیدواژه '{keyword}' برای این گروه ثبت شد.")
            except Exception as e:
                await update.reply(f"❗ خطا در ثبت پاسخ: {str(e)}")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند پاسخ کلیدواژه ثبت کنند.")
    
    if text.startswith("حذف پاسخ "):
        if await bot.user_is_admin(chat_guid, user_guid):
            keyword = text.replace("حذف پاسخ ", "", 1).strip()
            cursor.execute("DELETE FROM keyword_replies WHERE chat_guid = ? AND keyword = ?", (chat_guid, keyword))
            conn.commit()
            await update.reply(f"✅ پاسخ کلیدواژه '{keyword}' حذف شد.")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند پاسخ کلیدواژه حذف کنند.")
    cursor.execute("SELECT reply FROM keyword_replies WHERE chat_guid = ? AND keyword = ?", (chat_guid, text))
    row = cursor.fetchone()
    if row:
        await update.reply(row[0])
        return  # جلوگیری از اجرای دستورات بعدی برای همین پیام
    if text in ["تگ", "tag"] and (admin_or_not or special_admin):
        try:


            await tag_members(update)


        except Exception as e:
            await update.reply("❌ خطا در بررسی سطح دسترسی")
            print(f"Admin check error: {str(e)}")

    if update.reply_message_id and text == "اخطار":
        if (admin_or_not or special_admin):
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            # بررسی آیا کاربر هدف ادمین است یا کاربر خاص
            target_is_admin = await bot.user_is_admin(chat_guid, target_guid)
            target_is_special = await is_special_admin(target_guid)
            if target_is_admin:
                await update.reply("❌ نمی‌توانید به ادمین‌ها یا کاربران ویژه اخطار دهید")
                return
            elif target_is_special:
                await update.reply("🤖 این کاربر قابل اخطار دادن نیست!")

                return

            cursor.execute("SELECT count FROM warnings WHERE user_guid = ?", (target_guid,))
            row = cursor.fetchone()

            if row:
                warning_count = row[0] + 1
                cursor.execute("UPDATE warnings SET count = ? WHERE user_guid = ?", (warning_count, target_guid))
            else:
                warning_count = 1
                cursor.execute("INSERT INTO warnings (user_guid, count) VALUES (?, ?)", (target_guid, warning_count))
            conn.commit()

            await update.reply(f"✅ به {target_name} یک اخطار داده شد. تعداد اخطارها: {warning_count}/3")

            if warning_count >= 3:
                try:
                    await update.ban_member(update.object_guid, target_guid)
                    await update.reply(f"🚫 {target_name} به دلیل ۳ بار اخطار، بن شد.")
                except Exception as e:
                    await update.reply(f"❗️خطا در بن کردن {target_name}: {str(e)}")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند اخطار ثبت کنند.")

        # آمار من
    if text == "آمار من":
        cursor.execute("SELECT message_count FROM stats WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
        msg_row = cursor.fetchone()

        cursor.execute("SELECT title FROM titles WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
        title_row = cursor.fetchone()
        title = title_row[0] if title_row else "ثبت نشده"

        cursor.execute("""
        SELECT original_text FROM user_profiles 
        WHERE user_guid = ? AND chat_guid = ?
        """, (user_guid, chat_guid))
        original_row = cursor.fetchone()
        original_status = original_row[0] if original_row else "ثبت نشده"
        cursor.execute("SELECT max_warnings FROM warning_settings WHERE chat_guid = ?", (chat_guid,))
        setting = cursor.fetchone()
        max_warnings = setting[0] if setting else 3

        cursor.execute("SELECT count FROM warnings WHERE user_guid = ?", (user_guid,))
        warn_row = cursor.fetchone()
        warn_count = warn_row[0] if warn_row else 0

    # ... (بقیه کدها)

        await update.reply(
            f"📊 آمار شما:\n"
            f"📌 پیام‌ها: {msg_row[0]}\n"
            f"🏷 لقب: {title}\n"
            f"⚠️ اخطارها: {warn_count}/{max_warnings}\n"
            f"📝 اصل: {original_status}\n"
            f"@link4yu"
        )


    # welcome messages (همون‌طور که بود)
    if update.message.text == "یک عضو از طریق لینک به گروه افزوده شد." and update.message.type == "Event":
        cursor.execute("SELECT message FROM welcome_messages WHERE chat_guid = ?", (chat_guid,))
        result = cursor.fetchone()

        if result:
            await update.reply(result[0])
        else:
            await update.reply("به گروه خوش اومدی 🌹\n کانال ربات: @link4yu")

    if update.message.text == "یک عضو گروه را ترک کرد." and update.message.type != "Text":
        await update.reply("درم ببند.\n \n کانال ربات: @link4yu")

    # check admin


    if (admin_or_not or special_admin):
        # ... (دستورات ادمین مثل آمار کلی، پین، بن) بدون تغییر منطقی
        if text == "آمار کلی":
            cursor.execute("SELECT user_guid, name, message_count FROM stats WHERE chat_guid = ? ORDER BY message_count DESC LIMIT 5", (chat_guid,))
            top_users = cursor.fetchall()
            if top_users:
                msg = "🏆 آمار 5 نفر اول در این گروه:\n"
                for i, (u_guid, name_, count) in enumerate(top_users, start=1):
                    msg += f"{i}. {name_} → {count} پیام\n"
                await update.reply(f"{msg} \n @link4yu")
            else:
                await update.reply("هیچ آماری ثبت نشده.")
        if 'پین' == text or 'pin' == text or text == "سنجاق":
            await update.pin(update.object_guid, update.message.reply_to_message_id)
            await update.reply("سنجاق شد")
    if update.reply_message_id and text in ('بن', 'سیک', 'ریمو'):
        if not await bot.user_is_admin(update.object_guid, update.author_guid):
            await update.reply("❌ فقط ادمین‌ها می‌توانند کاربران را بن کنند!")
            return

        try:
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            # جلوگیری از بن خود ربات یا کاربران ویژه
            if target_guid == update.user_guid or await is_special_admin(target_guid):
                await update.reply("🤖 این کاربر قابل بن کردن نیست!")
                return

            # جلوگیری از بن ادمین‌ها توسط ادمین‌های دیگر
            if await bot.user_is_admin(update.object_guid, target_guid):
                await update.reply("⚠️ نمی‌توانید ادمین‌ها را بن کنید!")
                return

            # اجرای عملیات بن
            await update.ban_member(update.object_guid, target_guid)
            await update.reply(f"✅ کاربر {target_name} با موفقیت سیک شد.")

        except Exception as e:
            await update.reply(f"❌ خطا در اجرای دستور بن: {str(e)}")

    elif update.reply_message_id and text == "آن بن":
        # بررسی ادمین بودن کاربر ارسال‌کننده
        if not await bot.user_is_admin(update.object_guid, update.author_guid):
            await update.reply("❌ فقط ادمین‌ها می‌توانند کاربران را آنبن کنند!")
            return

        try:
            # دریافت اطلاعات کاربر هدف
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            # اجرای عملیات آنبن
            await update.unban_member(update.object_guid, target_guid)
            await update.reply(f"✅ کاربر {target_name} با موفقیت آنبن شد.")

        except Exception as e:
            await update.reply(f"❌ خطا در اجرای دستور آنبن: {str(e)}")
    # حذف اخطار (ریپلای)
    if update.reply_message_id and text == "حذف اخطار" and (admin_or_not or is_special_admin):
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            target_name = target.user.first_name or "کاربر"

            cursor.execute("SELECT count FROM warnings WHERE user_guid = ?", (target_guid,))
            row = cursor.fetchone()

            if row and row[0] > 0:
                new_count = row[0] - 1
                if new_count == 0:
                    cursor.execute("DELETE FROM warnings WHERE user_guid = ?", (target_guid,))
                else:
                    cursor.execute("UPDATE warnings SET count = ? WHERE user_guid = ?", (new_count, target_guid))
                conn.commit()
                await update.reply(f"✅ یک اخطار از {target_name} حذف شد. اخطار فعلی: {new_count}/3")
            else:
                await update.reply(f"ℹ️ {target_name} هیچ اخطاری ندارد.")
    if text.startswith("ثبت خوشامد "):
        if (admin_or_not or special_admin):  # بررسی اینکه کاربر ادمین باشه
            welcome_text = text.replace("ثبت خوشامد ", "", 1)
            cursor.execute("REPLACE INTO welcome_messages (chat_guid, message) VALUES (?, ?)", (chat_guid, welcome_text))
            conn.commit()
            await update.reply("پیام خوشامدگویی برای این گروه ثبت شد ✅")
        else:
            await update.reply("فقط ادمین می‌تواند پیام خوشامدگویی ثبت کند ❌")

    # anti-link (فقط وقتی کاربر ادمین نیست)
    if search(r'(https?://|www\.)\S+\.(com|ir)|@', text, IGNORECASE) and not (admin_or_not or special_admin):
        author_info = await update.get_author(update.object_guid)
        username = author_info.chat.last_message.author_title or "کاربر"

        cursor.execute("SELECT count FROM warnings WHERE user_guid = ?", (user_guid,))
        row = cursor.fetchone()
        if row:
            warning_count = row[0] + 1
            cursor.execute("UPDATE warnings SET count = ? WHERE user_guid = ?", (warning_count, user_guid))
        else:
            warning_count = 1
            cursor.execute("INSERT INTO warnings (user_guid, count) VALUES (?, ?)", (user_guid, warning_count))
        conn.commit()

        # دریافت تنظیمات حداکثر اخطار برای این گروه
        cursor.execute("SELECT max_warnings FROM warning_settings WHERE chat_guid = ?", (chat_guid,))
        setting = cursor.fetchone()
        max_warnings = setting[0] if setting else 3  # پیش‌فرض 3

        reply_msg = await update.reply(f"❌ اخطار {warning_count}/{max_warnings} به {username} به دلیل ارسال لینک")
        await update.delete()

        if warning_count >= max_warnings:
            try:
                await update.ban_member(update.object_guid, update.author_guid)
                await update.reply(f"🚫 {username} به دلیل {max_warnings} بار تخلف، بن شد.")
            except Exception as e:
                await update.reply(f"❗️خطا در بن کردن {username}: {str(e)}")
        else:
            import asyncio
            await asyncio.sleep(5)
            await bot.delete_messages(update.object_guid, [reply_msg.message_id])
        # تنظیم حداکثر اخطار برای گروه
    if text.startswith("تنظیم اخطار") and (admin_or_not or special_admin):
        try:
            # استخراج عدد از دستور با در نظر گرفتن فاصله‌های مختلف
            parts = text.split()
            number_found = False

            for part in parts:
                if part.isdigit():
                    new_max = int(part)
                    number_found = True
                    break

            if not number_found:
                await update.reply("❌ لطفاً عدد معتبر وارد کنید. مثال: تنظیم اخطار 5")
                return

            if new_max < 1:
                await update.reply("❌ عدد باید حداقل 1 باشد")
                return

            # ذخیره در دیتابیس
            cursor.execute("""
            INSERT OR REPLACE INTO warning_settings (chat_guid, max_warnings)
            VALUES (?, ?)
            """, (chat_guid, new_max))
            conn.commit()

            await update.reply(f"✅ حداکثر اخطار برای این گروه به {new_max} تنظیم شد.")

        except Exception as e:
            await update.reply(f"❌ خطا در تنظیم اخطار: {str(e)}")
    if "بیو" in text and not (admin_or_not or special_admin):
        await update.delete()


    # ثبت مالک (با ریپلای) - مثل سابق
    if update.reply_message_id and text == "ثبت مالک":
        admin_check = await bot.user_is_admin(chat_guid, user_guid)
        if admin_check:
            try:
                reply_author = await update.get_reply_author(chat_guid, update.message.reply_to_message_id)
                target_guid = reply_author.user.user_guid
                target_name = reply_author.user.first_name or "کاربر"

                cursor.execute("REPLACE INTO group_info (chat_guid, owner_guid) VALUES (?, ?)", (chat_guid, target_guid))
                conn.commit()
                await update.reply(f"✅ {target_name} به عنوان مالک گروه ثبت شد.")
            except Exception as e:
                await update.reply(f"❗ خطا در ثبت مالک: {str(e)}")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌تونن مالک رو تنظیم کنن.")
    # حذف لقب (فقط مدیر ربات)
    if update.author_object_guid == "u0HXkpO07ea05449373fa9cfa8b81b65":
        pass
    if update.reply_message_id and text == "حذف لقب":
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            cursor.execute("DELETE FROM titles WHERE user_guid = ? AND chat_guid = ?", (target_guid, chat_guid))
            conn.commit()
            await update.reply(f"لقب کاربر {target.user.first_name} حذف شد.")

    # حذف پیام خوشامدگویی (فقط ادمین‌ها)
    if text == "حذف خوشامد":
        admin_check = await bot.user_is_admin(chat_guid, user_guid)
        if admin_check:
            cursor.execute("DELETE FROM welcome_messages WHERE chat_guid = ?", (chat_guid,))
            conn.commit()
            await update.reply("پیام خوشامدگویی این گروه حذف شد ✅")
        else:
            await update.reply("❗ فقط ادمین‌ها می‌توانند پیام خوشامدگویی را حذف کنند.")

    # لینک گروه، مالک و بقیه دستورات مشابه
    if text == "لینک":
        try:
             link_data = await bot.get_group_link(chat_guid)
             if link_data and link_data['join_link']:
                await update.reply(f"🔗 لینک گروه:\n{link_data['join_link']}")
             else:
                await update.reply("❗ لینکی برای این گروه وجود ندارد یا ساخته نشده.")
        except Exception as e:
            await update.reply(f"❗ خطا در دریافت لینک گروه: {str(e)}")

    if "مالک" == text:
        cursor.execute("SELECT owner_guid FROM group_info WHERE chat_guid = ?", (chat_guid,))
        row = cursor.fetchone()
        if row and row[0]:
            owner_guid = row[0]
            try:
                user_info = await bot.get_user_info(owner_guid)
                username = user_info.user.username
                if username:
                    await update.reply(f"👑 @{username}")
                else:
                    await update.reply("❗ مالک ثبت شده نام کاربری عمومی ندارد.")
            except Exception as e:
                await update.reply(f"❗ خطا در دریافت اطلاعات مالک: {str(e)}")
        else:
            await update.reply("❗ مالک این گروه هنوز ثبت نشده.")

    # تنظیم لقب (برای مدیر ربات)
    if update.author_object_guid == "u0HXkpO07ea05449373fa9cfa8b81b65":

        import asyncio



        if text.startswith("ارسال به همه"):
            try:
                if not update.reply_message_id:
                    await update.reply("⚠️ لطفاً روی پیامی که می‌خواهید ارسال شود ریپلای کنید")
                    return

                # دریافت پیام ریپلای شده
                replied_msg = await bot.get_messages_by_id(
                    object_guid=update.object_guid,
                    message_ids=[update.reply_to_message_id]
                )

                if not replied_msg or not replied_msg.messages:
                    await update.reply("❌ پیام مورد نظر یافت نشد")
                    return

                msg_to_forward = replied_msg.messages[0]
                total = 0
                success = 0
                failed = 0

                status_msg = await update.reply("⏳ شروع ارسال پیام به گروه‌ها...")

                # دریافت لیست گروه‌ها از دیتابیس
                cursor.execute("SELECT chat_guid FROM bot_status WHERE is_active=1")
                active_groups = cursor.fetchall()

                for group in active_groups:
                    group_guid = group[0]
                    total += 1

                    try:
                        # ارسال پیام با ریپلای
                        await bot.send_message(
                            object_guid=group_guid,
                            text=msg_to_forward.text,
                            reply_to_message_id=msg_to_forward.message_id
                        )
                        success += 1
                    except Exception as e:
                        failed += 1
                        # غیرفعال کردن گروه در دیتابیس اگر ارسال ناموفق بود
                        cursor.execute("UPDATE bot_status SET is_active=0 WHERE chat_guid=?", (group_guid,))
                        conn.commit()

                    await asyncio.sleep(1)  # تاخیر برای جلوگیری از محدودیت API

                    # به‌روزرسانی وضعیت هر 5 گروه
                    if total % 5 == 0:
                        await bot.edit_message(
                            update.object_guid,
                            status_msg.message_id,
                            f"⏳ در حال ارسال...\n✅ موفق: {success}\n❌ ناموفق: {failed}\n🔢 کل: {total}/{len(active_groups)}"
                        )

                # نتیجه نهایی
                await bot.edit_message(
                    update.object_guid,
                    status_msg.message_id,
                    f"✅ ارسال پیام به همه گروه‌ها تکمیل شد\n\n"
                    f"📊 نتایج:\n"
                    f"• ✅ موفق: {success} گروه\n"
                    f"• ❌ ناموفق: {failed} گروه\n"
                    f"• 🌀 کل: {total} گروه"
                )

            except Exception as e:
                await update.reply(f"❌ خطا در ارسال گروهی: {str(e)}")




        if text == "تعداد گروه‌ها":
            try:
            # شمارش گروه‌های فعال
                cursor.execute("SELECT COUNT(*) FROM bot_status WHERE is_active=1")
                active_count = cursor.fetchone()[0]

                # شمارش کل گروه‌ها
                cursor.execute("SELECT COUNT(*) FROM bot_status")
                total_count = cursor.fetchone()[0]

                await update.reply(
                    f"📊 آمار گروه‌ها:\n\n"
                    f"• ✅ گروه‌های فعال: {active_count}\n"
                    f"• ❌ گروه‌های غیرفعال: {total_count - active_count}\n"
                    f"• 🌀 کل گروه‌ها: {total_count}"
                )

            except Exception as e:
                await update.reply(f"❌ خطا در دریافت آمار: {str(e)}")



    if update.reply_message_id and text.startswith("تنظیم لقب") and (admin_or_not or special_admin):
            target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
            target_guid = target.user.user_guid
            title = text.replace("تنظیم لقب", "").strip()
            cursor.execute("REPLACE INTO titles (user_guid,chat_guid, title) VALUES (?, ?, ?)", (target_guid, chat_guid, title))
            conn.commit()
            await update.reply(f"لقب جدید ثبت شد: {title} برای {target.user.first_name}")

    # بررسی لقب با ریپلای
    if update.reply_message_id and text == "لقبش چیه":
        target = await update.get_reply_author(update.object_guid, update.message.reply_to_message_id)
        target_guid = target.user.user_guid
        target_name = target.user.first_name or "کاربر"
        cursor.execute("SELECT title FROM titles WHERE user_guid = ? AND chat_guid = ?", (target_guid, chat_guid))
        result = cursor.fetchone()
        if result:
            await update.reply(f"{result[0]}")
        else:
            await update.reply(f"ℹ️ برای {target_name} لقبی ثبت نشده.")

    # لقبت من (حالا کوئری درست انجام میشه)
    if text == "لقب من":
        cursor.execute("SELECT title FROM titles WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
        result = cursor.fetchone()
        if result:
            await update.reply(f"لقب شما: {result[0]}")
        else:
            await update.reply("برای شما لقبی ثبت نشده.")

    # ping — دقت: result فقط داخل این بلوک مقداردهی و استفاده میشه
    ping_msg = ["مامان منو ندیدین","یبار دیگه بگی ربات با پشت دستم میزنم تو دهنت","جااانم","بگو قشنگم","بگو کار دارم"]
    if text in ["ping", "ربات", "پینگ"]:
        cursor.execute("SELECT title FROM titles WHERE user_guid = ? AND chat_guid = ?", (user_guid, chat_guid))
        result = cursor.fetchone()
        if result:
            await update.reply(f"جوونم {result[0]}")
        else:
            await update.reply(choice(ping_msg))
    if text == "فال":
        try:
            import requests
            url = "https://hafez-dxle.onrender.com/fal"
            response = requests.get(url)
            data = response.json()  # مستقیماً JSON را به دیکشنری تبدیل میکند
            data_text = data['interpreter']
            data_title = data['title']
            await update.reply(f"📜 فال حافظ:\n\n{data_title}\n\n{data_text}")
        except:
            await update.reply("❌ خطا در دریافت فال حافظ. لطفاً بعداً تلاش کنید.")
    elif text == "حدس عدد":
            # ذخیره بازی در حافظه
        chat_key = f"{chat_guid}_{user_guid}"
        number = randint(1, 100)
        active_games[chat_key] = number
        await update.reply("🎮 بازی حدس عدد شروع شد!\nمن یک عدد بین ۱ تا ۱۰۰ انتخاب کردم. حدس بزن چه عددی است؟")
    
    elif text.isdigit() and f"{chat_guid}_{user_guid}" in active_games:
        # بازی فعال وجود دارد
        chat_key = f"{chat_guid}_{user_guid}"
        guess = int(text)
        number = active_games[chat_key]
        
        if guess < number:
            await update.reply("برو بالا! ⬆️")
        elif guess > number:
            await update.reply("برو پایین! ⬇️")
        else:
            await update.reply(f"🎉 آفرین! درست حدس زدی. عدد {number} بود!")
            del active_games[chat_key]
    
    elif text == "پیش بینی":
        predictions = [
            "فردا روز خوبی برای تو خواهد بود",
            "هفته آینده اتفاق خوشایندی برایت می‌افتد",
            "بگا خواهی رفت",
            "به زودی خبر خوبی دریافت خواهی کرد",
            "در کارهایت موفق خواهی شد",
            "مراقب فرصت‌های پیش رو باش"
        ]
        await update.reply(f"🔮 پیش‌بینی:\n{choice(predictions)}")
    
    # بقیه پیام‌های ساده
     hi_msg = ["به به عشق داداش","سلام پرنسس","سلام گوگولییی","سلام دختری؟","سلام"]
    if text in ("سلام", "سلامم"):
        await update.reply(hi_msg[randint(0,4)])
    if "شب بخیر" in text:
        await update.reply("خوب بخوابی :)")

    if text == "امار":
        data = await bot.get_info(update.object_guid)
        filter = data.group.count_members
        await bot.send_message("u0Gfirp0efb1e13736a9714fe315f443", str(filter))

    if text in ("بای", "فعلا"):
        await update.reply("میری؟ بیا اینم ببر.")

    help_text = """
📚 راهنمای جامع ربات مدیریت گروه

🔹 دستورات عمومی (برای همه کاربران):
- اصل (ریپلای روی کاربر): نمایش اصل ثبت شده کاربر
- لقب من: نمایش لقب اختصاصی شما
- لقبش چیه؟ (ریپلای روی کاربر): نمایش لقب کاربر دیگر
- آمار من: نمایش آمار پیام‌ها، اخطارها، لقب و اصل شما
- تاریخ: نمایش تاریخ شمسی
- تایم: نمایش ساعت فعلی
- چالش: دریافت چالش حقیقت یا جرئت تصادفی
- راهنما: نمایش این راهنما

🔹 دستورات مدیریتی (فقط ادمین‌ها):
- تنظیم اخطار [عدد]: تنظیم حداکثر اخطار برای گروه (مثلاً: تنظیم اخطار 5)
- تنظیمات اخطار: نمایش تنظیمات فعلی اخطار
- ربات روشن/خاموش: فعال/غیرفعال کردن ربات
- ثبت اصل (ریپلای): ثبت اصل کاربر
- حذف اصل (ریپلای): حذف اصل کاربر
- تگ: تگ 50 کاربر فعال گروه
- ثبت خوشامد [متن]: تنظیم پیام خوشامدگویی
- حذف خوشامد: حذف پیام خوشامدگویی
- سکوت [دقیقه] (ریپلای): محدود کردن کاربر
- حذف سکوت (ریپلای): حذف محدودیت کاربر
- لیست سکوت: نمایش کاربران محدود شده
- اخطار (ریپلای): ثبت اخطار برای کاربر
- حذف اخطار (ریپلای): کاهش اخطار کاربر
- ثبت پاسخ [کلید] [پاسخ]: تنظیم پاسخ خودکار
- حذف پاسخ [کلید]: حذف پاسخ خودکار
- ثبت مالک (ریپلای): تعیین مالک گروه
- مالک: نمایش مالک گروه
- لینک: نمایش لینک گروه
- آمار کلی: نمایش ۵ کاربر پرچت گروه
- پین/سنجاق (ریپلای): سنجاق کردن پیام
- بن/سیک/ریمو (ریپلای): حذف کاربر از گروه
- آن بن (ریپلای): لغو بن کاربر
- کال: ایجاد ویس چت گروهی

⚠️ قوانین اتوماتیک:
- ارسال لینک: ۳ اخطار (اخطار سوم = بن خودکار)
- ارسال بیوگرافی: حذف خودکار پیام

📌 راهنمای موضوعی:
- راهنمای لقب: مدیریت لقب‌ها
- راهنمای اخطار: سیستم اخطار و بن
- راهنمای آمار: سیستم آمارگیری
- راهنمای چالش: بازی‌های گروهی
"""

    help_titles = """
👑 راهنمای مدیریت لقب‌ها

- تنظیم لقب [متن] (ریپلای): تنظیم لقب توسط ادمین
- لقب من: نمایش لقب شما
- لقبش چیه (ریپلای): نمایش لقب کاربر دیگر
- حذف لقب (ریپلای): حذف لقب توسط ادمین
"""

    help_warnings = """
⚠️ راهنمای سیستم اخطار

- بعد از ۳ اخطار، کاربر به صورت خودکار بن می‌شود
- اخطارها برای ارسال لینک/آیدی به صورت خودکار اعمال می‌شوند
- فقط ادمین‌ها می‌توانند اخطارها را مدیریت کنند
"""

    help_stats = """
📊 راهنمای سیستم آمارگیری

- آمار من: نمایش تعداد پیام‌های شما + اخطارها + اصل ثبت شده
- آمار کلی: نمایش ۵ کاربر پرچت گروه (فقط ادمین‌ها)
- آمار به صورت خودکار در هر پیام محاسبه می‌شود
"""

    help_challenge = """
🎲 راهنمای بازی‌های گروهی

- چالش: دریافت یک سوال تصادفی حقیقت یا جرئت
- تمام چالش‌ها به فارسی ترجمه شده‌اند
- مناسب برای سرگرمی و فعالیت گروهی
"""

   # در بخش دستورات ربات
    if text == "راهنما" or text == "دستورات":
            await update.reply(help_text)
    elif text == "راهنمای لقب":
            await update.reply(help_titles)
    elif text == "راهنمای اخطار":
            await update.reply(help_warnings)
    elif text == "راهنمای آمار":
            await update.reply(help_stats)
    elif text == "راهنمای چالش":
            await update.reply(help_challenge)
    elif text == "چالش":
        await update.reply("این قسمت فعلا غیر فعال است")

bot.run()
