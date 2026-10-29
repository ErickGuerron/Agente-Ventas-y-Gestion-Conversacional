"""Operator monitoring dashboard (Streamlit). Reads and writes only through the operator API.

Configuration (Streamlit secrets or environment variables):
  API_BASE_URL      public HTTPS URL of the FastAPI backend, e.g. https://bot.example.com
  DASHBOARD_API_KEY the same key configured in the backend
"""

import os

import plotly.express as px
import streamlit as st

from api_client import OperatorApi, OperatorApiError

HUMAN = "HUMAN_ACTIVE"
LEAD_LABELS = {
    "LEAD_CALIENTE": "Lead caliente",
    "INTERESADO": "Interesado",
    "DUDOSO": "Dudoso",
    "FRUSTRADO": "Frustrado",
}
SENDER_LABELS = {"user": "Prospecto", "ai": "IA", "operator": "Operador"}


def _setting(name: str) -> str:
    try:
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.environ.get(name, "")


def _api() -> OperatorApi | None:
    base_url = _setting("API_BASE_URL")
    key = _setting("DASHBOARD_API_KEY")
    if not base_url or not key:
        return None
    return OperatorApi.from_config(base_url, key)


def _status_text(status: str) -> str:
    return "Humano activo" if status == HUMAN else "IA activa"


def _chat_label(conv: dict) -> str:
    lead = LEAD_LABELS.get(conv.get("lead_status") or "", "Sin clasificar")
    return f"{conv['external_chat_id']} · {_status_text(conv['status'])} · {lead}"


def _run_action(action, success: str) -> None:
    try:
        action()
        st.session_state["flash"] = success
    except OperatorApiError as error:
        st.session_state["flash"] = f"No se pudo completar la acción: {error}"


def _conversation_detail(api: OperatorApi, conv: dict) -> None:
    conv_id = conv["id"]
    st.subheader(f"Chat {conv['external_chat_id']}")
    st.caption(
        f"Estado: {_status_text(conv['status'])} · "
        f"Termómetro: {LEAD_LABELS.get(conv.get('lead_status') or '', 'Sin clasificar')}"
    )

    col_take, col_resume = st.columns(2)
    col_take.button(
        "Tomar control",
        key=f"take-{conv_id}",
        disabled=conv["status"] == HUMAN,
        on_click=_run_action,
        args=(lambda: api.takeover(conv_id), "Tomaste el control del chat."),
        use_container_width=True,
    )
    col_resume.button(
        "Reanudar IA",
        key=f"resume-{conv_id}",
        disabled=conv["status"] != HUMAN,
        on_click=_run_action,
        args=(lambda: api.resume(conv_id), "La IA volvió a responder en este chat."),
        use_container_width=True,
    )

    try:
        messages = api.messages(conv_id)
    except OperatorApiError as error:
        st.error(f"No se pudo cargar el historial: {error}")
        return

    for message in messages:
        role = "user" if message["sender_type"] == "user" else "assistant"
        with st.chat_message(role):
            st.caption(SENDER_LABELS.get(message["sender_type"], message["sender_type"]))
            st.write(message["content"])

    with st.form(f"reply-{conv_id}", clear_on_submit=True):
        text = st.text_area(
            "Respuesta del operador",
            max_chars=4000,
            disabled=conv["status"] != HUMAN,
            help="Solo se envía mientras tengas el control del chat.",
        )
        sent = st.form_submit_button("Enviar", disabled=conv["status"] != HUMAN)
    if sent and text.strip():
        _run_action(lambda: api.reply(conv_id, text.strip()), "Mensaje enviado por Telegram.")


@st.fragment(run_every=3)
def chats_panel(api: OperatorApi) -> None:
    try:
        conversations = api.list_conversations()
    except OperatorApiError as error:
        st.error(f"No se pudo leer el monitoreo: {error}")
        return

    if not conversations:
        st.info("Todavía no hay conversaciones.")
        return

    labels = {conv["id"]: _chat_label(conv) for conv in conversations}
    left, right = st.columns([1, 2])
    with left:
        selected_id = st.radio("Chats activos", list(labels), format_func=labels.get, key="chat")
    with right:
        selected = next(conv for conv in conversations if conv["id"] == selected_id)
        _conversation_detail(api, selected)


@st.fragment(run_every=10)
def metrics_panel(api: OperatorApi) -> None:
    try:
        data = api.summary()
    except OperatorApiError as error:
        st.error(f"No se pudieron cargar las métricas: {error}")
        return

    cols = st.columns(5)
    cols[0].metric("Conversaciones", data["active_conversations"])
    cols[1].metric("Escalaciones humanas", data["human_escalations"])
    cols[2].metric("Leads calientes", data["hot_leads"])
    avg = data["avg_response_ms"]
    cols[3].metric("Respuesta promedio", f"{avg} ms" if avg is not None else "Sin datos")
    cols[4].metric("Fallos de jobs", data["failed_jobs"])

    hours = data["messages_per_hour"]
    st.plotly_chart(
        px.bar(
            x=[h["hour"] for h in hours],
            y=[h["count"] for h in hours],
            labels={"x": "Hora (UTC)", "y": "Mensajes"},
            title="Mensajes por hora",
        ),
        use_container_width=True,
    )
    intents = data["intent_distribution"]
    if intents:
        st.plotly_chart(
            px.pie(names=list(intents), values=list(intents.values()), title="Intenciones"),
            use_container_width=True,
        )
    else:
        st.caption("Aún no hay intenciones clasificadas.")
    st.caption(f"Tokens consumidos: {data['total_tokens']}")


def main() -> None:
    st.set_page_config(page_title="Monitoreo del bot", layout="wide")
    st.title("Monitoreo del bot")
    api = _api()
    if api is None:
        st.error("Configura API_BASE_URL y DASHBOARD_API_KEY en los secrets de la app.")
        st.stop()

    if flash := st.session_state.pop("flash", None):
        st.toast(flash)

    tab_chats, tab_metrics = st.tabs(["Conversaciones", "Métricas"])
    with tab_chats:
        chats_panel(api)
    with tab_metrics:
        metrics_panel(api)


if __name__ == "__main__":
    main()
