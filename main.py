import telebot
from telebot import types
import sqlite3
import random
import string
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

# Загружаем user_id из файла .env
load_dotenv()
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

# Создаем экземпляр бота
TOKEN = os.getenv('YOUR_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

# Создаем соединение с базой данных
conn = sqlite3.connect('checklist_bot.db', check_same_thread=False)
cursor = conn.cursor()

# Создаем таблицы, если их еще нет
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        last_check DATE,
        coupon TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        cleaner_name TEXT,
        address TEXT,
        cleaning_type TEXT,
        surfaces INTEGER,
        floor INTEGER,
        bathrooms INTEGER,
        kitchen INTEGER,
        trash INTEGER,
        mirror INTEGER,
        windows INTEGER,
        cobweb INTEGER,
        balcony INTEGER,
        cleaner_rating INTEGER,
        manager_rating INTEGER,
        recommendation_rating INTEGER,
        suggestions TEXT,
        date TIMESTAMP
    )
''')

# Функция для удаления сообщений
def delete_messages(bot, user_id, last_bot_message_id, count=20):
    last_bot_message_id += 2
    for _ in range(count):
        if last_bot_message_id > 0:
            last_bot_message_id -= 1
            try:
                bot.delete_message(chat_id=user_id, message_id=last_bot_message_id)
            except telebot.apihelper.ApiException as e:
                if "message to delete not found" in str(e):
                    print(f"Message {last_bot_message_id} not found and could not be deleted.")
                else:
                    raise

# Функция для генерации купона
def generate_coupon():
    return ''.join(random.choices(string.ascii_uppercase, k=6))

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "Добро пожаловать в чек-лист бота Rate Cleaning! Как Вас зовут?")
    bot.register_next_step_handler(message, get_name)

# Обработчик команды /get_db, доступный только администратору
@bot.message_handler(commands=['get_db'])
def send_database(message):
    user_id = message.chat.id
    if str(user_id) == ADMIN_USER_ID:  # Проверка, что команду выполняет администратор
        try:
            # Создание датафреймов из таблиц базы данных
            users_df = pd.read_sql_query("SELECT * FROM users", conn)
            feedback_df = pd.read_sql_query("SELECT * FROM feedback", conn)

            # Запись в Excel файл
            excel_path = "checklist_bot_db.xlsx"
            with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                users_df.to_excel(writer, sheet_name="Users", index=False)
                feedback_df.to_excel(writer, sheet_name="Feedback", index=False)

            # Отправка файла администратору
            with open(excel_path, "rb") as file:
                bot.send_document(user_id, file)

            # Удаление локального файла после отправки
            os.remove(excel_path)
        except Exception as e:
            bot.send_message(user_id, f"Ошибка при создании или отправке файла: {str(e)}")
    else:
        bot.send_message(user_id, "У вас нет доступа к этой команде.")

# Функция для получения имени клиента
def get_name(message):
    user_id = message.chat.id
    name = message.text

    # Проверяем, существует ли пользователь
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()

    if user:
        cursor.execute('UPDATE users SET name = ? WHERE user_id = ?', (name, user_id))
    else:
        cursor.execute('INSERT INTO users (user_id, name, last_check, coupon) VALUES (?, ?, ?, ?)', 
                       (user_id, name, None, None))
    conn.commit()

    # Переход к выбору имени клинера
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Илья", callback_data=f'nc_Ilya_{user_id}'),
               types.InlineKeyboardButton("Алексей", callback_data=f'nc_Alexey_{user_id}'))
    bot.send_message(message.chat.id, "Выберите, кто проводил клининг:", reply_markup=markup)

# Обработчик выбора имени клинера
@bot.callback_query_handler(func=lambda call: call.data.startswith('nc_'))
def handle_cleaner_selection(call):
    data = call.data.split('_')
    cleaner_name = data[1]

    bot.answer_callback_query(call.id)

    # Переход к следующему шагу - запрос адреса
    bot.send_message(call.message.chat.id, "Теперь укажите ваш адрес")
    bot.register_next_step_handler(call.message, get_cleaning_type, cleaner_name)

# Функция для выбора типа уборки
def get_cleaning_type(message, cleaner_name):
    address = message.text
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("Генеральная", callback_data=f'ct_g_{cleaner_name}_{address}'),
               types.InlineKeyboardButton("Поддерживающая", callback_data=f'ct_m_{cleaner_name}_{address}'))
    bot.send_message(message.chat.id, "Выберите тип уборки:", reply_markup=markup)

# Обработчик выбора типа уборки
@bot.callback_query_handler(func=lambda call: call.data.startswith('ct_'))
def handle_cleaning_type(call):
    data = call.data.split('_')
    cleaning_type = data[1]
    cleaner_name = data[2]
    address = data[3]

    bot.answer_callback_query(call.id)

    if cleaning_type == "g":
        # Переход к следующему шагу - вопросы по генеральной уборке
        get_general_cleaning_questions(call.message, cleaner_name, cleaning_type, address)
    else:
        # Переход к следующему шагу - поддерживающая уборка
        get_surfaces_status(call.message, cleaner_name, cleaning_type, address)

# Вопросы по генеральной уборке
def get_general_cleaning_questions(message, cleaner_name, cleaning_type, address):
    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Мойка окон:", reply_markup=markup)
    bot.register_next_step_handler(message, get_cobweb_status, cleaner_name, cleaning_type, address)

def get_cobweb_status(message, cleaner_name, cleaning_type, address):
    windows_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Чисто ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Удаление паутины:", reply_markup=markup)
    bot.register_next_step_handler(message, get_balcony_status, cleaner_name, cleaning_type, address, windows_status)

def get_balcony_status(message, cleaner_name, cleaning_type, address, windows_status):
    cobweb_status = 1 if message.text == 'Чисто ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Уборка балкона и террасной зоны:", reply_markup=markup)
    bot.register_next_step_handler(message, get_surfaces_status, cleaner_name, cleaning_type, address, windows_status, cobweb_status)

# Функция для проверки состояния поверхностей (общая для обоих типов уборки)
def get_surfaces_status(message, cleaner_name, cleaning_type, address, windows_status=None, cobweb_status=None, balcony_status=None):
    if cleaning_type == "g":
        balcony_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Пыль и загрязнения на различных поверхностях:", reply_markup=markup)
    bot.register_next_step_handler(message, get_floor_status, cleaner_name, cleaning_type, address, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния пола
def get_floor_status(message, cleaner_name, cleaning_type, address, windows_status=None, cobweb_status=None, balcony_status=None):
    surfaces_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Сухая и влажная уборка полов:", reply_markup=markup)
    bot.register_next_step_handler(message, get_bathrooms_status, cleaner_name, cleaning_type, address, surfaces_status, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния санузлов
def get_bathrooms_status(message, cleaner_name, cleaning_type, address, surfaces_status, windows_status=None, cobweb_status=None, balcony_status=None):
    floor_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Санузлы (смесители, унитаз):", reply_markup=markup)
    bot.register_next_step_handler(message, get_kitchen_status, cleaner_name, cleaning_type, address, surfaces_status, floor_status, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния кухни
def get_kitchen_status(message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, windows_status=None, cobweb_status=None, balcony_status=None):
    bathrooms_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Убрали ✅'), types.KeyboardButton('НЕ убрали ❌'))
    bot.send_message(message.chat.id, "Кухня (плита, столешницы, посуда, раковина, фасады):", reply_markup=markup)
    bot.register_next_step_handler(message, get_trash_status, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния мусора
def get_trash_status(message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, windows_status=None, cobweb_status=None, balcony_status=None):
    kitchen_status = 1 if message.text == 'Убрали ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Вынесли ✅'), types.KeyboardButton('НЕ вынесли ❌'))
    bot.send_message(message.chat.id, "Мусор:", reply_markup=markup)
    bot.register_next_step_handler(message, get_mirror_status, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния мусора
def get_mirror_status(message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, windows_status=None, cobweb_status=None, balcony_status=None):
    trash_status = 1 if message.text == 'Вынесли ✅' else 0

    markup = types.ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True)
    markup.add(types.KeyboardButton('Помыли ✅'), types.KeyboardButton('НЕ помыли ❌'))
    bot.send_message(message.chat.id, "Зеркала:", reply_markup=markup)
    bot.register_next_step_handler(message, get_cleaner_rating, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, windows_status, cobweb_status, balcony_status)

# Функция для проверки состояния зеркал
def get_cleaner_rating(message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, windows_status=None, cobweb_status=None, balcony_status=None):
    mirror_status = 1 if message.text == 'Помыли ✅' else 0

    # Очистка клавиатуры перед оценкой работы клинера
    markup = types.ReplyKeyboardRemove()
    markup = types.InlineKeyboardMarkup(row_width=2)
    for i in range(1, 11):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f'cln_{i}_{cleaner_name}_{cleaning_type}_{address}_{surfaces_status}_{floor_status}_{bathrooms_status}_{kitchen_status}_{trash_status}_{mirror_status}_{windows_status}_{cobweb_status}_{balcony_status}'))
    bot.send_message(message.chat.id, "Оцените работу клинера от 1 до 10:", reply_markup=markup)
# Функция для обработки нажатий инлайн-кнопок (оценка работы клинера)
@bot.callback_query_handler(func=lambda call: call.data.startswith('cln_'))
def handle_cleaner_rating(call):
    data = call.data.split('_')
    cleaner_rating = int(data[1])
    cleaner_name = data[2]
    cleaning_type = data[3]
    address = data[4]
    surfaces_status = int(data[5])
    floor_status = int(data[6])
    bathrooms_status = int(data[7])
    kitchen_status = int(data[8])
    trash_status = int(data[9])
    mirror_status = int(data[10])
    
    # Для поддерживающей уборки эти значения будут None
    windows_status = int(data[11]) if data[11] != 'None' else None
    cobweb_status = int(data[12]) if data[12] != 'None' else None
    balcony_status = int(data[13]) if data[13] != 'None' else None

    bot.answer_callback_query(call.id)

    # Переход к следующему шагу - оценка менеджера
    markup = types.InlineKeyboardMarkup(row_width=5)
    for i in range(1, 11):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f'mgr_{i}_{cleaner_name}_{cleaning_type}_{address}_{surfaces_status}_{floor_status}_{bathrooms_status}_{kitchen_status}_{trash_status}_{mirror_status}_{windows_status}_{cobweb_status}_{balcony_status}_{cleaner_rating}'))
    bot.send_message(call.message.chat.id, "Оцените работу менеджера от 1 до 10:", reply_markup=markup)

# Функция для обработки нажатий инлайн-кнопок (оценка работы менеджера)
@bot.callback_query_handler(func=lambda call: call.data.startswith('mgr_'))
def handle_manager_rating(call):
    data = call.data.split('_')
    manager_rating = int(data[1])
    cleaner_name = data[2]
    cleaning_type = data[3]
    address = data[4]
    surfaces_status = int(data[5])
    floor_status = int(data[6])
    bathrooms_status = int(data[7])
    kitchen_status = int(data[8])
    trash_status = int(data[9])
    mirror_status = int(data[10])
    
    # Для поддерживающей уборки эти значения будут None
    windows_status = int(data[11]) if data[11] != 'None' else None
    cobweb_status = int(data[12]) if data[12] != 'None' else None
    balcony_status = int(data[13]) if data[13] != 'None' else None
    cleaner_rating = int(data[14])

    bot.answer_callback_query(call.id)

    # Переход к следующему шагу - готовность рекомендовать
    markup = types.InlineKeyboardMarkup(row_width=5)
    for i in range(1, 11):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f'rec_{i}_{cleaner_name}_{cleaning_type}_{address}_{surfaces_status}_{floor_status}_{bathrooms_status}_{kitchen_status}_{trash_status}_{mirror_status}_{windows_status}_{cobweb_status}_{balcony_status}_{cleaner_rating}_{manager_rating}'))
    bot.send_message(call.message.chat.id, "Готовы ли вы рекомендовать нас от 1 до 10?", reply_markup=markup)

# Функция для обработки нажатий инлайн-кнопок (готовность рекомендовать)
@bot.callback_query_handler(func=lambda call: call.data.startswith('rec_'))
def handle_recommendation_rating(call):
    data = call.data.split('_')
    recommendation_rating = int(data[1])
    cleaner_name = data[2]
    cleaning_type = data[3]
    address = data[4]
    surfaces_status = int(data[5])
    floor_status = int(data[6])
    bathrooms_status = int(data[7])
    kitchen_status = int(data[8])
    trash_status = int(data[9])
    mirror_status = int(data[10])
    
    # Для поддерживающей уборки эти значения будут None
    windows_status = int(data[11]) if data[11] != 'None' else None
    cobweb_status = int(data[12]) if data[12] != 'None' else None
    balcony_status = int(data[13]) if data[13] != 'None' else None
    cleaner_rating = int(data[14])
    manager_rating = int(data[15])

    bot.answer_callback_query(call.id)

    # Переход к следующему шагу - сбор предложений/замечаний
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton('Нет', callback_data=f'sug_n_{cleaner_name}_{cleaning_type}_{address}_{surfaces_status}_{floor_status}_{bathrooms_status}_{kitchen_status}_{trash_status}_{mirror_status}_{windows_status}_{cobweb_status}_{balcony_status}_{cleaner_rating}_{manager_rating}_{recommendation_rating}'))
    bot.send_message(call.message.chat.id, "Есть ли замечания или предложения? Напишите их ниже или нажмите 'Нет':", reply_markup=markup)
    bot.register_next_step_handler(call.message, finalize_feedback, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, mirror_status, windows_status, cobweb_status, balcony_status, cleaner_rating, manager_rating, recommendation_rating)

# Обработчик инлайн-кнопки "нет"
@bot.callback_query_handler(func=lambda call: call.data.startswith('sug_n_'))
def handle_no_suggestions(call):
    data = call.data.split('_')
    print(data)
    cleaner_name = data[2]
    cleaning_type = data[3]
    address = data[4]
    surfaces_status = int(data[5])
    floor_status = int(data[6])
    bathrooms_status = int(data[7])
    kitchen_status = int(data[8])
    trash_status = int(data[9])
    mirror_status = int(data[10])
    
    # Для поддерживающей уборки эти значения будут None
    windows_status = int(data[11]) if data[11] != 'None' else None
    cobweb_status = int(data[12]) if data[12] != 'None' else None
    balcony_status = int(data[13]) if data[13] != 'None' else None
    cleaner_rating = int(data[14])
    manager_rating = int(data[15])
    recommendation_rating = int(data[16])

    # Пользователь выбрал "нет", отправляем пустое предложение в функцию финализации
    finalize_feedback(call.message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, mirror_status, windows_status, cobweb_status, balcony_status, cleaner_rating, manager_rating, recommendation_rating)

# Финализация фидбека
def finalize_feedback(message, cleaner_name, cleaning_type, address, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, mirror_status, windows_status=None, cobweb_status=None, balcony_status=None, cleaner_rating=None, manager_rating=None, recommendation_rating=None, suggestions=None):
    if isinstance(message, types.CallbackQuery):
        suggestions = ''
        user_id = message.chat.id
    else:
        suggestions = message.text if message.text != 'нет' else ''
        user_id = message.chat.id

    now = datetime.now()

    cursor.execute('SELECT name, last_check, coupon FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    name = result[0]
    last_check = result[1]
    coupon = result[2]

    if last_check:
        if last_check:
            if isinstance(last_check, int):  # Если last_check уже является числом (в формате таймстемпа)
                last_check_date = datetime.fromtimestamp(last_check)
            else:
                last_check_date = datetime.strptime(last_check, "%Y-%m-%d %H:%M:%S")
            
        if now - last_check_date < timedelta(days=3):
            bot.send_message(message.chat.id, "Вы уже проходили чек-лист после последнего клининга 👾")
            return

    del_count = 22

    if suggestions.endswith(':'):
        suggestions = ''
    else:
        del_count += 1

    if cleaning_type == 'g':
        del_count += 7

    # Генерируем новый купон
    coupon = generate_coupon()

    # Обновляем информацию о пользователе
    cursor.execute('UPDATE users SET last_check = ?, coupon = ? WHERE user_id = ?',
                   (now.strftime("%Y-%m-%d %H:%M:%S"), coupon, user_id))
    conn.commit()

    # Сохраняем фидбек
    cursor.execute('''
        INSERT INTO feedback (user_id, name, cleaner_name, address, cleaning_type, surfaces, floor, bathrooms, kitchen, trash, mirror, windows, cobweb, balcony, cleaner_rating, manager_rating, recommendation_rating, suggestions, date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, name, cleaner_name, address, cleaning_type, surfaces_status, floor_status, bathrooms_status, kitchen_status, trash_status, mirror_status, windows_status, cobweb_status, balcony_status, cleaner_rating, manager_rating, recommendation_rating, suggestions, now))
    conn.commit()

    chat_id = message.chat.id
    message_id = message.message_id

    delete_messages(bot, chat_id, message_id, del_count)

    bot.send_message(message.chat.id, f"Спасибо, {name}! Мы собираем эти данные, чтобы улучшить работу нашего клининга! В благодарность мы предлагаем вам купон на скидку 10% при следующем обращении! Ваш купон: {coupon}")
    
    report = f"""
    ___Новый отчет___

    Клиент: {name} 👤
    Купон: {coupon} 💸

    Клиннер: {cleaner_name} 👨🏼‍🚀
    Адрес: {address} 📍
    Тип уборки: {"Генеральная" if cleaning_type == "g" else "Поддерживающая"}

    Поверхности: {'✅' if surfaces_status else '❌'}
    Пол: {'✅' if floor_status else '❌'}
    Санузлы: {'✅' if bathrooms_status else '❌'}
    Кухня: {'✅' if kitchen_status else '❌'}
    Мусор: {'✅' if trash_status else '❌'}
    Зеркала: {'✅' if mirror_status else '❌'}
    Окна: {'✅' if windows_status else '❌'} (только для генеральной)
    Паутина: {'✅' if cobweb_status else '❌'} (только для генеральной)
    Балкон/Терраса: {'✅' if balcony_status else '❌'} (только для генеральной)
    
    Оценка клинера: {cleaner_rating}
    Оценка менеджера: {manager_rating}
    Готовность рекомендовать: {recommendation_rating}

    Замечания/Предложения: {suggestions}
    """
    bot.send_message(ADMIN_USER_ID, report)

# Запускаем бота
bot.polling(none_stop=True)


