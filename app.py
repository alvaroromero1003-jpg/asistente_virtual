import os
import json
import time
import uuid
from dotenv import load_dotenv
from datetime import datetime

import streamlit as st
import requests
from google.oauth2.service_account import Credentials
import gspread
import pdfplumber

# -------------------------------------
# Cargar las variables del archivo .env
# -------------------------------------
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ---------------------------------------------
# Verificar la API Key de OpenAI
# ---------------------------------------------
OPENAI_API_KEY = os.getenv("LLM_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("⚠️ No se encontró LLM_API_KEY en el archivo .env")

# -----------------------------
# Cargar prompt base
# -----------------------------
def load_prompt():
    with open("prompt.txt", "r", encoding="utf-8") as f:
        return f.read()

# -----------------------------
# Cargar knowledge.json
# -----------------------------
def load_knowledge():
    with open("knowledge.json", "r", encoding="utf-8") as f:
        return json.load(f)

# -----------------------------
# Cargar CV en PDF y extraer texto
# -----------------------------
def load_cv():
    cv_text = ""
    if os.path.exists("CV.pdf"):
        with pdfplumber.open("CV.pdf") as pdf:
            for page in pdf.pages:
                if page.extract_text():
                    cv_text += page.extract_text() + "\n"
    return cv_text.strip()

# -----------------------------
# Conectar con Google Sheets
# -----------------------------
def get_gsheets_client():
    try:
        SCOPE = ["https://www.googleapis.com/auth/spreadsheets"]
        
        # Cargar el JSON desde los secrets
        service_account_info = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPE)
        
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"❌ Error conectando con Google Sheets: {e}")
        return None

def log_interaction(user_input, assistant_reply, duration_ms, user_agent):
    try:
        client = get_gsheets_client()
        if not client:
            return

        sheet = client.open("estadisticas_asistente").worksheet("interacciones")

        row = [
            datetime.utcnow().isoformat(),
            str(st.session_state.session_id),
            user_input,
            assistant_reply,
            duration_ms,
            user_agent,
        ]

        try:
            # ✅ Intento 1: método clásico
            sheet.append_row(
                row, 
                value_input_option="RAW", 
                insert_data_option="INSERT_ROWS"
            )
        except Exception as e1:
            print(f"⚠️ append_row falló, probando con batch_update: {e1}")

            # ✅ Intento 2: método moderno y más confiable
            sheet.batch_update([{
                "range": f"A{sheet.row_count+1}",
                "values": [row],
            }])

    except Exception as e:
        st.error(f"No se pudo registrar en Google Sheets: {e}")

# -----------------------------
# Llamada al modelo LLM
# -----------------------------
def call_llm_api(messages):
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages}

    response = requests.post(api_url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# -----------------------------
# Interfaz principal Streamlit
# -----------------------------
def main():
    st.set_page_config(page_title="Asistente Virtual Personalizado", page_icon="🤖")
    st.title("Asistente Virtual Personalizado")

    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Cargar contexto inicial
    base_prompt = load_prompt()
    knowledge = load_knowledge()
    cv_text = load_cv()

    user_input = st.text_input("Hazme una pregunta:")

    if user_input:
        start_time = time.time()

        system_message = {
            "role": "system",
            "content": (
                f"{base_prompt}\n\n"
                f"Información de knowledge.json:\n{json.dumps(knowledge, indent=2, ensure_ascii=False)}\n\n"
                f"Extracto de CV:\n{cv_text}\n\n"
                f"Usa esta información para responder de manera precisa, clara y profesional."
            ),
        }

        messages = [system_message] + st.session_state.chat_history
        messages.append({"role": "user", "content": user_input})

        try:
            assistant_reply = call_llm_api(messages)
        except Exception as e:
            assistant_reply = f"Error consultando el modelo: {e}"

        duration_ms = int((time.time() - start_time) * 1000)
        user_agent = st.session_state.get("user_agent", "streamlit-client")

        st.session_state.chat_history.append({"role": "user", "content": user_input})
        st.session_state.chat_history.append({"role": "assistant", "content": assistant_reply})

        log_interaction(user_input, assistant_reply, duration_ms, user_agent)

    # Mostrar historial
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(f"**Tú:** {msg['content']}")
        else:
            st.markdown(f"**Asistente:** {msg['content']}")

if __name__ == "__main__":
    main()

