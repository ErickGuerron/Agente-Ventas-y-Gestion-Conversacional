Feature: operator-dashboard | Branch: feat/operator-dashboard | Delivery: ask-on-risk
Test runner: `& "C:\Users\erick\miniconda3\envs\hackathon\python.exe" -m pytest backend/tests/unit -q`
Source of truth for requirements: Arquitectura_Hackathon_UTA_2026.md sections 1, 7, 9, 10, 12.4 and 14.

## Specs
S1: Dashboard lists conversations with last interaction, commercial thermometer (lead_status), and an AI/Human indicator (status AI_ACTIVE / HUMAN_ACTIVE). Source: sec. 9 "lista de chats activos, última interacción, termómetro comercial, indicador IA/Humano".
S2: Dashboard shows the full history of one conversation, and an operator reply box. Controls "Tomar control" and "Reanudar IA". Source: sec. 9.
S3: Operator replies only while the conversation is HUMAN_ACTIVE. Replies under AI_ACTIVE are rejected with 409. Source: sec. 5 step 5 and sec. 7 ("los nuevos mensajes... sin programar respuestas automáticas"). ASSUMPTION: the reply guard is the handover rule applied to replies.
S4: Every REST and WebSocket operation of the dashboard requires the operator key. Without a configured key, the API refuses everything (fail closed). Source: sec. 10 "Autenticar y autorizar operaciones del dashboard en cada solicitud REST y conexión WebSocket".
S5: CORS allows only configured dashboard origins. No wildcard origin with credentials. Source: sec. 12.3 / 12.4 "URL pública de dashboard sin fallos CORS".
S6: Metrics: active conversations, messages per hour, hot leads (LEAD_CALIENTE), intent distribution, human escalations, response times, failures. Source: sec. 9 "Métricas recomendadas".
S7: The dashboard never talks to Telegram and never holds the bot token. Source: sec. 2 and sec. 10.
S8: Real-time updates over WebSocket for messages and status changes. Source: sec. 9 "Tiempo real: WebSockets autenticados".

## Tasks
T1 | S4, S5 | inline | [x] | RED: 5 failing (401/503/CORS) in test_operator_auth.py; GREEN: 64 unit passing
T2 | S3 | inline | [x] | RED: test_operator_reply_rejected_while_ai_is_active failed (200 instead of 409); GREEN: guard added
T3 | S1, S2 (GET /{id}, lead_status in list) | inline | [x] | RED: 2 failing (thermometer, detail); GREEN: 78 unit passing
T4 | S6 (GET /api/analytics/summary) | inline | [x] | RED: pure aggregation (9 tests) and endpoint tests; GREEN: 84 unit passing
T5 | S1, S2, S7 (Streamlit UI + api_client) | inline | [x] | RED: api_client tests (6); GREEN; UI verified with AppTest (no config, unreachable API)
T6 | S8 (WebSocket) | inline | [~] | auth done in T1; real-time is polling 3 s/10 s in Streamlit, documented as a limit in README

Route declaration: all inline. Trigger evidence: none fired (small units, under 100 changed lines each).

## Log
L1 (2026-10-29, verbatim from user): "ahora neceisto que implementes el dashboard de monitorieo del bot como se lo especifica en als indicaciones de la hackathon y que soluciones erroes que vallas encontrando"
L2: Mapping (explorer) found: no auth on REST/WS; CORS wildcard with credentials; reply without status guard; no GET /{id}; no analytics; analytics and leads modules are stubs; token_usage never populated; conversation_events and conversation_analysis never read.
L3: Decision: operator key via header X-Operator-Key for REST; WS uses ?token= query parameter because browsers cannot set headers on WebSocket. The key is never logged.
L4: Errors found and fixed during T1: (a) aiogram was declared in requirements.txt but missing from the hackathon env; installed with requirements-dev.txt. (b) CORS allow_origins=* with allow_credentials=True; now an explicit allow-list from DASHBOARD_ALLOWED_ORIGINS, credentials off. (c) APIRouter(dependencies=...) also applies to WebSocket handshakes in FastAPI 0.162, so the WS now lives in its own router with ?token= auth.
L5: Behavior change in T2: POST /reply now returns 409 unless the conversation is HUMAN_ACTIVE. test_operator_reply was updated to set HUMAN_ACTIVE, which is the handover flow from sec. 7.
L6: T3-T5 done. Lead thermometer comes from the latest conversation_analysis row per conversation.
L7: Error found by AppTest: an unreachable API raised httpx.ConnectError and crashed the Streamlit script. Fixed in api_client (maps transport errors to OperatorApiError 503).
L8: Lint: ruff check and ruff format are clean for the whole repo. pythonpath now includes dashboard/ for the client tests.
L9: Deployment documented in README (API on HTTPS, dashboard on Streamlit Community Cloud, local run). .env.example was not updated because reading and editing .env* files is blocked by a permission rule in this environment.
L10: Not verified end-to-end against PostgreSQL: integration tests need DATABASE_URL.
