import sqlite3

def init_db():
    conn = sqlite3.connect('bored_bot.db')
    cursor = conn.cursor()
    
    # جدول تنظیمات گروه
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            lock_links INTEGER DEFAULT 1,
            lock_badwords INTEGER DEFAULT 1,
            lock_spam INTEGER DEFAULT 1,
            captcha_enabled INTEGER DEFAULT 1,
            max_warns INTEGER DEFAULT 3,
            welcome_msg TEXT DEFAULT 'سلام {name} عزیز! به گروه bored خوش آمدید. ⚡'
        )
    ''')
    
    # جدول اخطارهای کاربران
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_warns (
            chat_id INTEGER,
            user_id INTEGER,
            warn_count INTEGER DEFAULT 0,
            PRIMARY KEY (chat_id, user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_settings(chat_id):
    conn = sqlite3.connect('bored_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT lock_links, lock_badwords, lock_spam, captcha_enabled, max_warns, welcome_msg FROM group_settings WHERE chat_id = ?', (chat_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute('INSERT INTO group_settings (chat_id) VALUES (?)', (chat_id,))
        conn.commit()
        cursor.execute('SELECT lock_links, lock_badwords, lock_spam, captcha_enabled, max_warns, welcome_msg FROM group_settings WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
    conn.close()
    return {
        'lock_links': row[0],
        'lock_badwords': row[1],
        'lock_spam': row[2],
        'captcha_enabled': row[3],
        'max_warns': row[4],
        'welcome_msg': row[5]
    }

def toggle_setting(chat_id, setting_name):
    conn = sqlite3.connect('bored_bot.db')
    cursor = conn.cursor()
    get_settings(chat_id)
    cursor.execute(f'UPDATE group_settings SET {setting_name} = CASE WHEN {setting_name} = 1 THEN 0 ELSE 1 END WHERE chat_id = ?', (chat_id,))
    conn.commit()
    conn.close()

def add_warn(chat_id, user_id):
    conn = sqlite3.connect('bored_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT warn_count FROM user_warns WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
    row = cursor.fetchone()
    if row:
        new_count = row[0] + 1
        cursor.execute('UPDATE user_warns SET warn_count = ? WHERE chat_id = ? AND user_id = ?', (new_count, chat_id, user_id))
    else:
        new_count = 1
        cursor.execute('INSERT INTO user_warns (chat_id, user_id, warn_count) VALUES (?, ?, 1)', (chat_id, user_id))
    conn.commit()
    conn.close()
    return new_count

def reset_warns(chat_id, user_id):
    conn = sqlite3.connect('bored_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_warns WHERE chat_id = ? AND user_id = ?', (chat_id, user_id))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()