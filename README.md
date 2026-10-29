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
dashboard/app.py           operador (pendiente)
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

| Variable | Uso |
|---|---|
| `LLM_PROVIDER` | `fake` (tests, local) o `gemini` |
| `GEMINI_API_KEY` | clave de Gemini (nunca en el repo) |
| `TELEGRAM_BOT_TOKEN` | token del bot |
| `TELEGRAM_WEBHOOK_SECRET` | secreto que valida cada webhook |
| `DATABASE_URL` | `postgresql+psycopg://usuario:clave@host:5432/base` |

Crea `.env.example` con estas variables (sin valores reales) y commitéalo; `.env` está en `.gitignore`.

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
