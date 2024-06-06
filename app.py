import cv2
import streamlit as st
import easyocr
import re
import sqlite3
import time
import pandas as pd
from datetime import datetime, timedelta

# Загрузка каскада Хаара для детекции номерных знаков
harcascade = "model/haarcascade_russian_plate_number.xml"
plate_cascade = cv2.CascadeClassifier(harcascade)

# Инициализация EasyOCR
reader = easyocr.Reader(["en"], gpu=True)

min_area = 500
pattern = r"^kz\d{3}[A-Z]{3}\d{2}$"
pattern2 = r"^\d{3}[A-Z]{3}\d{2}$"

# Переменная для хранения времени последней обработки номера
last_processed_plate = {}
processing_interval = 30  # Интервал в секундах для обработки одного и того же номера


# Функции для работы с базой данных
def check_recent_arrival(plate_number):
    conn = sqlite3.connect("parking.db")
    c = conn.cursor()

    # Проверка на наличие похожих записей за последние 30 секунд
    thirty_seconds_ago = datetime.now() - timedelta(seconds=30)
    c.execute(
        "SELECT * FROM arrivals WHERE plate_number = ? AND timestamp >= ?",
        (plate_number, thirty_seconds_ago),
    )
    result = c.fetchone()

    conn.close()
    return result is not None


def log_arrival(plate_number):
    if not check_recent_arrival(plate_number):
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
    else:
        return False


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
        st.session_state.gate_status = "Открыты"
        st.success(f"Доступ для номера {plate_number} разрешен. Ворота открыты.")
    else:
        st.session_state.gate_status = "Закрыты"
        st.warning(f"Доступ для номера {plate_number} запрещен. Ворота закрыты.")
    return access_granted


def process_frame(cap):
    ret, frame = cap.read()
    if ret:
        img_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        plates = plate_cascade.detectMultiScale(img_gray, 1.1, 4)

        for x, y, w, h in plates:
            area = w * h
            if area > min_area:
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                img_roi = frame[y : y + h, x : x + w]

                results = reader.readtext(img_roi)
                for bbox, text, prob in results:
                    clean_text = text.strip().replace(" ", "").upper()
                    if len(clean_text) <= 10 and (
                        re.fullmatch(pattern, clean_text)
                        or re.fullmatch(pattern2, clean_text)
                    ):
                        current_time = datetime.now()
                        last_time = last_processed_plate.get(
                            clean_text,
                            current_time - timedelta(seconds=processing_interval + 1),
                        )

                        if (
                            current_time - last_time
                        ).total_seconds() > processing_interval:
                            # Удаление старого уведомления перед добавлением нового
                            notification_placeholder = st.empty()
                            if log_arrival_and_check_access(clean_text):
                                notification_placeholder.success(
                                    f"Обнаружена машина с номером: {clean_text}. Ворота открыты."
                                )
                            else:
                                notification_placeholder.warning(
                                    f"Обнаружена машина с номером: {clean_text}. Ворота закрыты."
                                )
                            last_processed_plate[clean_text] = current_time
        return frame
    else:
        return None


def manage_database():
    st.header("Управление базой данных")

    conn = sqlite3.connect("parking.db")
    c = conn.cursor()

    # Боковая панель для выбора таблицы
    table = st.sidebar.selectbox(
        "Выберите таблицу", ["История посещений", "Белый список"]
    )

    if table == "История посещений":
        st.subheader("История посещений")

        # Просмотр истории посещений
        c.execute("SELECT * FROM arrivals")
        arrivals_data = c.fetchall()
        df = pd.DataFrame(arrivals_data, columns=["ID", "Номер автомобиля", "Время"])
        df_display = df.drop(columns=["ID"])

        edited_df = st.data_editor(
            df_display, num_rows="dynamic", use_container_width=True
        )

        if st.button("Сохранить изменения"):
            for index, row in edited_df.iterrows():
                plate_number = row["Номер автомобиля"]
                timestamp = row["Время"]
                if index >= len(df):
                    if pd.notna(plate_number):
                        c.execute(
                            "INSERT INTO arrivals (plate_number) VALUES (?)",
                            (plate_number,),
                        )
                else:
                    id_value = df.loc[index, "ID"]
                    c.execute(
                        "UPDATE arrivals SET plate_number = ?, timestamp = ? WHERE id = ?",
                        (plate_number, timestamp, id_value),
                    )
            conn.commit()
            st.success("Изменения сохранены")

    elif table == "Белый список":
        st.subheader("Белый список")

        # Просмотр белого списка
        c.execute("SELECT * FROM whitelist")
        whitelist_data = c.fetchall()
        df = pd.DataFrame(whitelist_data, columns=["ID", "Номер автомобиля"])
        df_display = df.drop(columns=["ID"])

        edited_df = st.data_editor(
            df_display, num_rows="dynamic", use_container_width=True
        )

        if st.button("Сохранить изменения"):
            for index, row in edited_df.iterrows():
                plate_number = row["Номер автомобиля"]
                if index >= len(df):
                    if pd.notna(plate_number):
                        c.execute(
                            "INSERT INTO whitelist (plate_number) VALUES (?)",
                            (plate_number,),
                        )
                else:
                    id_value = df.loc[index, "ID"]
                    c.execute(
                        "UPDATE whitelist SET plate_number = ? WHERE id = ?",
                        (plate_number, id_value),
                    )
            conn.commit()
            st.success("Изменения сохранены")

    conn.close()


def main():
    st.set_page_config(
        layout="wide", page_title="SmartGate", page_icon="media/logo.png"
    )
    st.sidebar.image("media/logo.png", use_column_width=True)
    st.sidebar.title("Навигация")
    page = st.sidebar.selectbox(
        "Выберите страницу", ["Система управления доступом", "Управление базой данных"]
    )

    if page == "Система управления доступом":
        st.title("SmartGate - Система управления доступом автомобилей")
        st.subheader("Просмотр в реальном времени и управление воротами")

        # Инициализация статуса ворот
        if "gate_status" not in st.session_state:
            st.session_state.gate_status = "Закрыты"

        # Инициализация состояния для остановки
        if "stop" not in st.session_state:
            st.session_state.stop = False

        # Инициализация состояния для видеонаблюдения
        if "video_surveillance" not in st.session_state:
            st.session_state.video_surveillance = False

        # Боковая панель с кнопками
        st.sidebar.header("Управление воротами")
        if st.sidebar.button("Открыть ворота", key="open_gate"):
            st.session_state.gate_status = "Открыты"
            st.sidebar.write("Ворота открыты.")
            # Добавьте код для открытия ворот
        if st.sidebar.button("Закрыть ворота", key="close_gate"):
            st.session_state.gate_status = "Закрыты"
            st.sidebar.write("Ворота закрыты.")
            # Добавьте код для закрытия ворот
        if st.sidebar.button("Остановить", key="stop_button"):
            st.session_state.stop = True

        st.sidebar.header("Управление видеонаблюдением")
        if st.sidebar.button("Включить видеонаблюдение", key="start_video"):
            st.session_state.video_surveillance = True
        if st.sidebar.button("Выключить видеонаблюдение", key="stop_video"):
            st.session_state.video_surveillance = False

        # Основная панель
        if st.session_state.gate_status == "Открыты":
            st.markdown(
                f"<h2 style='color: green;'>Статус ворот: Открыты</h2>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<h2 style='color: red;'>Статус ворот: Закрыты</h2>",
                unsafe_allow_html=True,
            )

        # Место для отображения видео с камеры
        video_container = st.container()
        frame_placeholder = video_container.empty()

        # Запуск цикла для отображения видео с камеры
        cap = None
        if st.session_state.video_surveillance:
            cap = cv2.VideoCapture(0)

        while st.session_state.video_surveillance and not st.session_state.stop:
            frame = process_frame(cap)
            if frame is not None:
                frame_placeholder.image(frame, channels="BGR", width=800)
            time.sleep(
                0.1
            )  # Добавим небольшую задержку для снижения нагрузки на процессор

        if cap:
            cap.release()
    elif page == "Управление базой данных":
        manage_database()


if __name__ == "__main__":
    main()
