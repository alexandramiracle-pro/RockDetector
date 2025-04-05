import streamlit as st
import pandas as pd
import json
import os
import hashlib
import requests
import joblib
import ast

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_score, recall_score, f1_score


# === Файлы ===
USER_DB = "users.json"
ML_MODEL_FILE = "ml_model.pkl"
VECTOR_FILE = "vectorizer.pkl"
FSTEC_DB_FILE = "fstec_db.json"
DATASET_FILE = "vulnerability_dataset.csv"
METRICS_FILE = "metrics.json"

# === Функции работы с пользователями ===
def load_users():
    return json.load(open(USER_DB, "r", encoding="utf-8")) if os.path.exists(USER_DB) else {}

def save_users(users):
    json.dump(users, open(USER_DB, "w", encoding="utf-8"), indent=4)

def register_user(username, password):
    users = load_users()
    if username in users:
        return "Пользователь уже существует"
    users[username] = hashlib.sha256(password.encode()).hexdigest()
    save_users(users)
    return "Регистрация успешна"

def login_user(username, password):
    users = load_users()
    return username in users and users[username] == hashlib.sha256(password.encode()).hexdigest()

# === Функция обучения модели ===
def train_ml_model():
    st.subheader("Обучение модели")
    try:
        data = pd.read_csv(DATASET_FILE)
    except FileNotFoundError:
        st.error("Файл датасета не найден.")
        return

    class_counts = data["label"].value_counts()
    data = data[data["label"].isin(class_counts[class_counts >= 2].index)]

    if data["label"].nunique() < 2:
        st.error("Ошибка: В датасете только один класс.")
        return
    
    X_train, X_test, y_train, y_test = train_test_split(
        data["code"], data["label"], test_size=0.2, random_state=42, stratify=data["label"]
    )
    
    vectorizer = TfidfVectorizer()
    X_train_tfidf = vectorizer.fit_transform(X_train)
    X_test_tfidf = vectorizer.transform(X_test)

    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train_tfidf, y_train)

    joblib.dump(model, ML_MODEL_FILE)
    joblib.dump(vectorizer, VECTOR_FILE)

    y_pred = model.predict(X_test_tfidf)
    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)

    json.dump({"precision": precision, "recall": recall, "f1_score": f1}, open(METRICS_FILE, "w"))
    st.success("Модель обучена и сохранена!")

# === Автоматическое дообучение ===
def auto_retrain_model(new_code, label):
    try:
        df = pd.read_csv(DATASET_FILE)
    except FileNotFoundError:
        df = pd.DataFrame(columns=["code", "label"])

    new_row = pd.DataFrame([[new_code, label]], columns=["code", "label"])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(DATASET_FILE, index=False)

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(df["code"])
    y = df["label"]

    model = RandomForestClassifier(n_estimators=100)
    model.fit(X, y)

    joblib.dump(model, ML_MODEL_FILE)
    joblib.dump(vectorizer, VECTOR_FILE)

# === Загрузка модели ===
def load_ml_model():
    try:
        return joblib.load(ML_MODEL_FILE), joblib.load(VECTOR_FILE)
    except FileNotFoundError:
        st.error("Обученная модель не найдена.")
        return None, None

# === Анализ кода через ML ===
def analyze_code_with_ml(code_snippet):
    model, vectorizer = load_ml_model()
    if model is None:
        return "Ошибка загрузки модели"
    vectorized_code = vectorizer.transform([code_snippet])
    prediction = model.predict(vectorized_code)[0]
    return f"Обнаружена уязвимость: {prediction}" if prediction != "safe" else "Код безопасен"

# === AST-анализ ===
def analyze_code_with_ast(code_snippet):
    try:
        tree = ast.parse(code_snippet)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and hasattr(node.func, "id"):
                if node.func.id == "eval":
                    return "Обнаружено использование eval — потенциальная уязвимость"
    except Exception as e:
        return f"Ошибка AST-анализа: {e}"
    return "AST-анализ: опасных конструкций не обнаружено"

# === Работа с БДУ ФСТЭК ===
def load_fstec_db():
    if os.path.exists(FSTEC_DB_FILE):
        with open(FSTEC_DB_FILE, "r", encoding="utf-8") as file:
            try:
                return json.load(file)
            except json.JSONDecodeError:
                st.error("Ошибка в файле базы ФСТЭК. Проверьте формат JSON.")
                return []
    return []

def compare_with_fstec(code_snippet):
    fstec_db = load_fstec_db()
    code_hash = hashlib.sha256(code_snippet.encode()).hexdigest()

    for vuln in fstec_db:
        if vuln.get("hash") == code_hash:
            return f"""**Совпадение с БДУ ФСТЭК найдено:**

**Уязвимость:** {vuln['description']}
**CVE:** {vuln['CVE']}
**Серьезность:** {vuln['severity']}"""

    return "Совпадений с БДУ ФСТЭК не найдено"

def update_fstec_db():
    st.subheader("Обновление БДУ ФСТЭК")
    api_url = st.text_input("Введите API-адрес")

    if st.button("Обновить базу"):
        try:
            response = requests.get(api_url)
            if response.status_code == 200:
                new_db = response.json()
                if isinstance(new_db, list):
                    for vuln in new_db:
                        if "pattern" in vuln:
                            vuln["hash"] = hashlib.sha256(vuln["pattern"].encode()).hexdigest()
                    json.dump(new_db, open(FSTEC_DB_FILE, "w", encoding="utf-8"), indent=4)
                    st.success("База ФСТЭК обновлена!")
                else:
                    st.error("Ошибка: Ожидался список уязвимостей в формате JSON.")
            else:
                st.error(f"Ошибка: Сервер вернул код {response.status_code}")
        except Exception as e:
            st.error(f"Ошибка: {e}")

# === Интерфейс Streamlit ===
def main():
    st.title("Система анализа уязвимостей")

    menu = st.sidebar.radio("Выберите модуль", ["Администрирование", "Обучение", "Эксплуатация", "Анализ кода", "Обновление ФСТЭК"])

    if menu == "Администрирование":
        st.subheader("Управление пользователями")
        choice = st.radio("Выберите действие", ["Вход", "Регистрация"])
        
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")

        if choice == "Регистрация" and st.button("Зарегистрироваться"):
            st.success(register_user(username, password))

        if choice == "Вход" and st.button("Войти"):
            if login_user(username, password):
                st.session_state["logged_in"] = True
                st.success("Успешный вход")
            else:
                st.error("Неверные данные")

    elif menu == "Обучение":
        train_ml_model()

    elif menu == "Эксплуатация":
        uploaded_file = st.file_uploader("Загрузите файл кода")
        if uploaded_file:
            code = uploaded_file.read().decode("utf-8")
            st.write("ML-анализ:", analyze_code_with_ml(code))
            st.write("AST-анализ:", analyze_code_with_ast(code))

    elif menu == "Анализ кода":
        code_input = st.text_area("Введите код")
        if st.button("Анализировать"):
            st.write("ML-анализ:", analyze_code_with_ml(code_input))
            st.write("AST-анализ:", analyze_code_with_ast(code_input))
            st.write("Сравнение с БДУ ФСТЭК:", compare_with_fstec(code_input))

            if st.checkbox("Добавить как новый обучающий пример"):
                label = st.text_input("Введите метку (например, sql_injection, xss, safe и т.д.):")
                if st.button("Добавить в датасет и переобучить"):
                    auto_retrain_model(code_input, label)
                    st.success("Добавлено и дообучено.")

    elif menu == "Обновление ФСТЭК":
        update_fstec_db()

if __name__ == "__main__":
    main()
