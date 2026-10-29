# Hackathon UTA 2026: Bot multi-agente de ventas

Bot de Telegram con agentes académico y comercial, dashboard con handover humano y memoria conversacional.
Diseño completo: [Arquitectura_Hackathon_UTA_2026.md](Arquitectura_Hackathon_UTA_2026.md).

## Estructura

```text
backend/src/
  main.py                  FastAPI (health, webhooks, REST, WebSocket)
  modules/                 un módulo = un dueño (ver tabla de responsables)
    channels/              adaptador Telegram
    conversations/         ownership, estados, versión, handover
    courses/               catálogo oficial y reglas de precio
    ai_engine/             LangGraph, puerto LLMClient, Gemini
    leads/                 perfil comercial e inscripción
    analytics/             eventos y métricas
  shared/                  configuración, base de datos, seguridad
backend/data/courses.json  catálogo oficial (valores de ejemplo, reemplazar)
backend/tests/             unit/ (rápidas), integration/ (PostgreSQL), live/ (Gemini real, manual)
worker/main.py             proceso de IA (pendiente)
dashboard/app.py           monitoreo y handover para el operador (Streamlit)
dashboard/api_client.py    cliente HTTP de la API del operador (sin Telegram)
```

## Responsables por módulo

Reparto para trabajar en paralelo sin tocar los mismos archivos.

| Módulo | Responsable |
|---|---|
| `channels`, `main.py` (webhook) | _por definir_ |
| `conversations` (handover) | _por definir_ |
| `courses`, `ai_engine` | _por definir_ |
| `leads`, `analytics`, `dashboard/` | _por definir_ |

## Puesta en marcha local

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r backend/requirements-dev.txt
cp .env.example .env              # completar valores
pytest -m "not integration and not live"   # unit
pytest -m integration                      # requiere DATABASE_URL
ruff check . && ruff format --check .
uvicorn main:app --reload --app-dir backend/src
```

## Variables de entorno

Backend (`backend/.env` en local, variables de entorno en el host):

| Variable | Uso |
|---|---|
| `GEMINI_API_KEY` | clave de Gemini (nunca en el repo) |
| `GEMINI_MODEL` | modelo de Gemini (default `gemini-3.5-flash`) |
| `MINIMAX_API_KEY` | clave de MiniMax, proveedor de respaldo |
| `MINIMAX_MODEL` | modelo de MiniMax (default `MiniMax-M3.1-Flash`) |
| `CURSOR_API_KEY` | clave de Cursor; solo funciona en planes de pago |
| `TELEGRAM_BOT_TOKEN` | token del bot |
| `TELEGRAM_WEBHOOK_SECRET` | secreto que valida cada webhook |
| `DATABASE_URL` | `postgresql+psycopg://usuario:clave@host:5432/base` |
| `DASHBOARD_API_KEY` | clave del operador. Sin ella, la API responde 503 a todo (falla cerrado) |
| `DASHBOARD_ALLOWED_ORIGINS` | orígenes del dashboard separados por coma, p. ej. `https://tu-app.streamlit.app` |

Cadena de proveedores: Gemini, luego MiniMax, luego Cursor. Cada uno se activa solo si tiene clave, y cae al siguiente cuando no está disponible. `LLM_PROVIDER` ya no existe: la elección la decide la presencia de claves.

Dashboard (secrets de Streamlit o variables de entorno):

| Variable | Uso |
|---|---|
| `API_BASE_URL` | URL pública HTTPS de la API, sin barra final |
| `DASHBOARD_API_KEY` | la misma clave que el backend |

Crea `.env.example` con estas variables (sin valores reales) y commitéalo; `.env` está en `.gitignore`.

## Despliegue

El front es Streamlit y solo habla con la API de FastAPI. Nunca recibe el token del bot ni las claves de proveedores. Orden recomendado: primero la API, después el dashboard.

### 1. API en un host con HTTPS

Telegram exige HTTPS para el webhook, y el navegador exige HTTPS para llamar a la API desde el dashboard público. Cualquier host que sirva un proceso Python sirve (Render, Railway, un VPS con Caddy o Nginx). Comando de arranque:

```bash
uvicorn main:app --app-dir backend/src --host 0.0.0.0 --port $PORT
```

Configura en el host las variables del backend, con `DASHBOARD_ALLOWED_ORIGINS` apuntando a la URL del dashboard, por ejemplo `https://tu-app.streamlit.app`. Sin ese valor exacto, el navegador bloquea las llamadas por CORS.

### 2. Dashboard en Streamlit Community Cloud

1. En share.streamlit.io crea una app desde este repositorio.
2. *Main file path*: `dashboard/app.py`. Las dependencias salen de `dashboard/requirements.txt`.
3. En *Settings → Secrets* pega:

```toml
API_BASE_URL = "https://tu-api.ejemplo.com"
DASHBOARD_API_KEY = "la-misma-clave-del-backend"
```

4. Despliega. La URL resultante es la que va en `DASHBOARD_ALLOWED_ORIGINS` del backend.

### 3. Dashboard en local

```bash
pip install -r dashboard/requirements.txt
set API_BASE_URL=http://localhost:8000          # Windows (PowerShell: $env:API_BASE_URL=...)
set DASHBOARD_API_KEY=la-misma-clave
streamlit run dashboard/app.py
```

Para local, agrega `http://localhost:8501` a `DASHBOARD_ALLOWED_ORIGINS` (es el default).

### Verificación antes de la demo

- `GET {API_BASE_URL}/health` responde `{"status": "ok"}`.
- `GET {API_BASE_URL}/api/conversations` sin la cabecera `X-Operator-Key` responde 401. Con la clave responde 200.
- El dashboard muestra la lista de chats y las métricas, sin errores rojos en la consola del navegador.
- Una respuesta del operador llega al chat de Telegram. Si la conversación está en `AI_ACTIVE`, el dashboard la rechaza con 409, y eso es lo esperado.

### Límites conocidos

- El dashboard se actualiza por consulta cada 3 s (chats) y cada 10 s (métricas), no por WebSocket. La arquitectura lo permite porque Streamlit no mantiene un WebSocket persistente. El WebSocket de FastAPI sigue disponible para otros clientes.
- Los eventos en tiempo real viven en memoria de un solo proceso. Si el worker corre en otro proceso, sus eventos no llegan al dashboard hasta que se persistan y se consulten.
- Los `token_usage` todavía no se guardan, así que su métrica aparece en 0.
- `failed_jobs` cuenta jobs `FAILED`, pero el worker todavía no escribe jobs.

## Flujo de Git

- `main` es la rama estable. Nadie hace push directo a `main`.
- Cada tarea sale de `main` en una rama: `feat/<modulo>-<descripcion>`, `fix/<descripcion>`, `chore/<descripcion>`.
- Commits en formato Conventional Commits: `feat(courses): validate catalog prices`.
- Un Pull Request por tarea, pequeño (idealmente menos de 400 líneas cambiadas).
- El PR solo se mergea con el CI en verde (`lint`, `unit`, `integration`).
- Antes de empezar: `git pull` en `main`. Antes de abrir PR: `git pull --rebase origin main`.

## CI en GitHub Actions

- `.github/workflows/ci.yml`: en cada PR y en cada push a `main`. Ejecuta `ruff` (lint y formato), pruebas unitarias y pruebas de integración contra un PostgreSQL de servicio.
- `.github/workflows/live-llm.yml`: manual (`workflow_dispatch`). Llama a Gemini real con el secreto `GEMINI_API_KEY`. No se ejecuta en cada PR para no gastar cuota.

Para proteger `main`: en GitHub, *Settings → Branches → Add rule* para `main`, activar *Require a pull request before merging* y *Require status checks to pass* (seleccionar `Lint (ruff)`, `Unit tests` e `Integration tests`).

## Reglas del equipo

- Las pruebas de reglas de negocio (precios, descuentos, handover) no dependen del LLM real: usar `FakeLLMClient`.
- Nunca commitear `.env`, tokens ni claves.
- Los precios y promociones salen solo de `backend/data/courses.json` aprobado; el LLM no inventa ofertas.
