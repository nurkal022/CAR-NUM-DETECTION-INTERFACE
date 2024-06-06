import sqlite3

# Создание соединения с базой данных
conn = sqlite3.connect("parking.db")
c = conn.cursor()

# Создание таблицы для всех прибывших автомобилей
c.execute(
    """
CREATE TABLE if not exists arrivals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""
)

# Создание таблицы для "белого" списка номеров
c.execute(
    """
CREATE TABLE if not exists whitelist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plate_number TEXT UNIQUE NOT NULL
)
"""
)

conn.commit()
conn.close()


def log_arrival(plate_number):
    conn = sqlite3.connect("parking.db")
    c = conn.cursor()

    # Добавление номера в таблицу прибытых автомобилей
    c.execute("INSERT INTO arrivals (plate_number) VALUES (?)", (plate_number,))

    # Проверка номера в "белом" списке
    c.execute("SELECT * FROM whitelist WHERE plate_number = ?", (plate_number,))
    result = c.fetchone()

    conn.commit()
    conn.close()

    # Если номер найден в "белом" списке, возвращаем True
    return result is not None


def add_to_whitelist(plate_number):
    conn = sqlite3.connect("parking.db")
    c = conn.cursor()

    try:
        # Попытка добавить номер в "белый" список
        c.execute("INSERT INTO whitelist (plate_number) VALUES (?)", (plate_number,))
        conn.commit()
        print(f"Номер {plate_number} успешно добавлен в 'белый' список.")
    except sqlite3.IntegrityError:
        print(f"Номер {plate_number} уже существует в 'белом' списке.")
    finally:
        conn.close()


def log_arrival_and_check_access(plate_number):
    access_granted = log_arrival(plate_number)
    if access_granted:
        print(f"Доступ для номера {plate_number} разрешен. Шлагбаум открыт.")
    else:
        print(f"Доступ для номера {plate_number} запрещен. Шлагбаум закрыт.")
    return access_granted


# Добавление номеров в "белый" список
# add_to_whitelist("019KAZ02")
# add_to_whitelist("444BOP02")

# Проверка доступа
plate_number = "444BOP02"
if log_arrival(plate_number):
    print("Открываю шлагбаум")
else:
    print("Доступ запрещен")
