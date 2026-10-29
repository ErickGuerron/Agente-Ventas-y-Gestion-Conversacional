# Arquitectura técnica del MVP
## Ecosistema Multi-Agente para Ventas y Gestión Conversacional

**Hackathon UTA 2026 — Documento de diseño e implementación**  
**Versión:** 1.0  
**Fecha:** 29 de octubre de 2026  
**Alcance:** MVP de Telegram con agente académico y comercial, dashboard con intervención humana y memoria conversacional.

> **Decisión principal:** monolito modular con principios de arquitectura hexagonal, orquestación con LangGraph y procesamiento asíncrono. Para el conocimiento oficial de cursos se usa un catálogo JSON; para recordar el contexto de la conversación se utiliza el *checkpointer* `InMemorySaver` de LangGraph. No se implementa RAG vectorial ni Mem0 en el MVP.

## 1. Contexto, objetivo y alcance

El reto oficial solicita un agente con LLM en Telegram capaz de perfilar prospectos, explicar el pénsum, gestionar objeciones comerciales y orientar la inscripción. También exige un dashboard web reactivo con conversaciones activas, indicadores de intención y **handover**: un operador puede asumir el hilo, suspender respuestas de IA y responder desde la misma identidad del bot. Se evalúan resiliencia frente a inyecciones de prompt, gestión de tokens y estabilidad de la demostración.

### Funcionalidades imprescindibles

1. Recibir y responder mensajes reales de Telegram.
2. Consultar datos oficiales de cursos sin inventar precios ni promociones.
3. Reconocer preguntas académicas, intereses comerciales y casos de frustración.
4. Mantener el contexto de una conversación mediante un identificador estable.
5. Mostrar chats y métricas en el dashboard en tiempo real.
6. Permitir al operador tomar el control, contestar desde Telegram y devolver el control a la IA.
7. Guardar mensajes, estados y eventos relevantes de forma consistente.

**Fuera del alcance inmediato:** WhatsApp real, entrenamiento de modelos propios, Mem0, pgvector, RAG documental, Kubernetes, Kafka y microservicios independientes. La arquitectura conserva adaptadores para añadir canales posteriormente.

## 2. Arquitectura recomendada

**Estilo:** monolito modular + separación por puertos/adaptadores (hexagonal) + procesamiento asíncrono orientado a eventos. La API y los módulos de negocio se mantienen en un único proyecto; el worker puede ejecutarse como proceso independiente usando el mismo código y contratos.

```text
              +-------------+      +-----------------+
              | Telegram    |      | Dashboard web   |
              | (aiogram)   |      | Streamlit       |
              +------+------+      +--------+--------+
                     | webhook               | REST / WebSocket
                     v                       v
              +----------------------------------------+
              | FastAPI                                |
              | Webhooks | REST | WebSockets | Auth    |
              +------------------+---------------------+
                                 |
                                 v
              +----------------------------------------+
              | CONVERSATION MANAGER                   |
              | Persistencia, ownership, estado y      |
              | control de handover / idempotencia     |
              +------------------+---------------------+
                                 |
                   trabajo de IA (si AI_ACTIVE)
                                 v
              +----------------------------------------+
              | Worker + LangGraph                      |
              | Clasificador / enrutador               |
              |  +---------------+  +----------------+ |
              |  | Académico     |  | Comercial      | |
              |  | courses.json  |  | Leads / ventas | |
              |  +---------------+  +----------------+ |
              |        LangChain + Google Gemini        |
              +------------------+---------------------+
                                 |
              +------------------+---------------------+
              | Supabase PostgreSQL                     |
              | chats, mensajes, leads, jobs, eventos  |
              +------------------+---------------------+
                                 |
                       eventos / WebSockets
                                 v
                           Dashboard
```

El diagrama es lógico: el envío a Telegram pasa siempre por el adaptador del canal. El dashboard jamás envía mensajes a Telegram directamente ni accede al token del bot.

### Responsabilidades por módulo

| Módulo | Responsabilidad | Regla de desacoplamiento |
|---|---|---|
| `channels` | Adaptadores Telegram y futuros canales | Convierte mensajes externos a un DTO interno |
| `conversations` | Historial, propietarios, estados, coordinación | Es la fuente de verdad del handover |
| `ai_engine` | Grafo LangGraph, llamadas a Gemini, clasificación | No conoce las APIs concretas de Telegram |
| `courses` | Catálogo oficial y reglas comerciales | Datos autorizados, no memorizados por el LLM |
| `leads` | Perfil comercial e inscripción | No concede descuentos autónomamente |
| `analytics` | Eventos, métricas, estado de prospectos | Lee eventos persistidos, no trazas efímeras |
| `realtime` | Emisión WebSocket a operadores autorizados | No modifica directamente reglas de negocio |

## 3. Tecnologías y elección

| Capa | Tecnología | Uso en el MVP | Evolución |
|---|---|---|---|
| Lenguaje | Python | Backend y worker | Se conserva |
| Servidor HTTP | FastAPI | Webhooks, REST y WS | Escalable horizontalmente |
| Bot | aiogram | Telegram Bot API | Adaptadores adicionales |
| Modelo | Google Gemini | Clasificación, argumentación y respuestas | Proveedor intercambiable |
| Integración LLM | LangChain + `langchain-google-genai` | Invocar Gemini y herramientas | Más modelos/herramientas |
| Orquestador | LangGraph | Estado y rutas académico/comercial | Flujos con aprobación humana |
| Memoria corta | `InMemorySaver` | Contexto por `thread_id` | Checkpointer PostgreSQL |
| Conocimiento de cursos | `courses.json` | Fuente oficial simple | Tabla `courses` o búsqueda documental |
| Persistencia negocio | Supabase PostgreSQL | Conversaciones, mensajes, leads, estados | Índices, colas, particiones |
| Dashboard | Streamlit + Plotly | Indicadores y UI rápida | Angular u otra UI sin cambiar la API |
| Canal bidireccional | FastAPI WebSockets | Mensajes y control de operador en vivo | Pub/Sub para varias instancias |
| Ejecución asíncrona | Worker Python + tabla `jobs` | No bloquear el webhook | Redis Streams / cola administrada |
| Entorno | Docker / Docker Compose | Reproducción local | Despliegue administrado |

**Nota sobre Streamlit:** sus componentes habituales no constituyen por sí solos un cliente de chat WebSocket persistente. La bandeja instantánea puede implementarse con un componente web personalizado conectado a FastAPI; para las gráficas puede emplearse actualización periódica. Si construir dicho componente implica riesgo para la entrega, se debe priorizar una interfaz web mínima de chat con JavaScript/WebSocket y conservar Streamlit para las estadísticas.

## 4. Conocimiento de cursos y memoria: solución mínima

Son dos problemas diferentes:

- **Conocimiento oficial**: datos vigentes sobre cursos, horarios, precios, promociones y pénsum. Almacenarlos en `courses.json` y cargar el archivo una vez al iniciar el proceso. Para un catálogo pequeño, pasarlo como contexto o consultarlo mediante una función `get_course_catalog()`; no hacer embeddings.
- **Memoria conversacional**: lo que el usuario ya ha dicho, por ejemplo «quiero Python virtual y tengo presupuesto limitado». Utilizar LangGraph con un `thread_id` estable de la conversación; para el prototipo basta `InMemorySaver`.

### Ejemplo de `courses.json`

```json
[
  {
    "id": "python-basico",
    "nombre": "Python desde Cero",
    "modalidad": "Virtual",
    "duracion_horas": 40,
    "precio_usd": 80,
    "descripcion": "Fundamentos de programación con Python",
    "temas": ["Variables", "Funciones", "POO"],
    "promociones_autorizadas": []
  },
  {
    "id": "ia-intro",
    "nombre": "Introducción a la IA",
    "modalidad": "Virtual",
    "duracion_horas": 60,
    "precio_usd": 120,
    "descripcion": "Conceptos y aplicaciones de IA",
    "temas": ["Machine Learning", "LLM", "Agentes"],
    "promociones_autorizadas": []
  }
]
```

**Los valores son demostrativos y deben reemplazarse por información aprobada.** El LLM nunca debe crear promociones por su cuenta. Los precios visibles o utilizados en inscripciones deben validarse desde la fuente autorizada en el backend.

### Checkpointer en LangGraph

```python
from langgraph.checkpoint.memory import InMemorySaver

# builder es un StateGraph previamente definido.
graph = builder.compile(checkpointer=InMemorySaver())

config = {"configurable": {"thread_id": f"telegram:{chat_id}"}}
# El estado debe declarar messages con el reductor add_messages.
result = graph.invoke(
    {"messages": [HumanMessage(content=user_message)]},
    config=config,
)
```

`InMemorySaver` conserva contexto mientras viva el proceso y **no sobrevive reinicios ni comparte estados entre múltiples workers**. Si se ejecutan varios workers, migrar a un checkpointer persistente o limitar explícitamente la ejecución del grafo a un único proceso. La persistencia del historial de negocio en PostgreSQL sigue siendo necesaria.

**¿Por qué no Mem0 ahora?** Mem0 resulta útil para extraer y recuperar preferencias semánticas entre sesiones, pero introduce otro circuito de almacenamiento y recuperación. Para el jurado es más importante que el bot recuerde el contexto reciente y responda con datos oficiales correctos. Mem0 puede añadirse después.

## 5. Flujo de mensajes extremo a extremo

1. **Entrada:** Telegram envía una actualización al webhook HTTPS de FastAPI.
2. **Validación:** se valida el secreto configurado del webhook, la estructura del evento y se detectan duplicados por identificador externo.
3. **Normalización:** el adaptador convierte la actualización en un mensaje de dominio con `channel_id`, `external_chat_id`, `message_id` y contenido.
4. **Persistencia:** se guarda el mensaje y se consulta el estado de la conversación (`AI_ACTIVE` o `HUMAN_ACTIVE`).
5. **Enrutamiento:** si está bajo control humano, se notifica al dashboard y no se genera respuesta IA. Si está bajo control de IA, se crea un trabajo de inferencia.
6. **Procesamiento:** el worker recupera historial y contexto, invoca LangGraph y selecciona el agente académico, comercial o la solicitud de intervención.
7. **Conocimiento:** el agente académico consulta `courses.json`; el comercial usa el mismo catálogo oficial y las reglas autorizadas.
8. **Control previo al envío:** se verifica nuevamente que la conversación siga en estado `AI_ACTIVE` y que la versión/propietario no haya cambiado.
9. **Respuesta:** el adaptador Telegram envía el mensaje; se registra el resultado (incluidos errores/reintentos).
10. **Analítica:** se persisten intención, categoría del prospecto, latencia, uso de tokens y eventos; el dashboard recibe la actualización WebSocket.

### Secuencia simplificada

```text
Prospecto -> Telegram -> FastAPI -> PostgreSQL: mensaje
FastAPI -> Worker: trabajo de inferencia (solo AI_ACTIVE)
Worker -> LangGraph: estado + historial
LangGraph -> courses.json: catálogo autorizado
LangGraph -> Gemini: clasificación y respuesta
Worker -> Conversation Manager: comprobar ownership/version
Conversation Manager -> Telegram: enviar si sigue AI_ACTIVE
Conversation Manager -> PostgreSQL: registrar salida y evento
Backend -> WebSocket -> Dashboard: actualizar chat y KPIs
```

## 6. Orquestación LangGraph

Se propone **un grafo con dos agentes especializados y un supervisor de enrutamiento**. El supervisor puede ser una función determinista que usa una clasificación estructurada de Gemini; no es obligatorio un tercer agente LLM.

```text
START
  |
  v
analyze_intent_and_lead_status
  |
  v
route_decision
  +--> academic_agent -> answer / request_human
  +--> sales_agent    -> answer / request_human
  +--> human_review   -> suspend_auto_reply
  |
  v
persist_analysis -> END
```

**Estado sugerido:** `conversation_id`, `messages`, `intent`, `lead_status`, `selected_agent`, `requires_human`, `response`. Mantener separado el estado conversacional del grafo y el **estado de autorización** persistido de cada conversación.

**Termómetro del prospecto:** `INTERESADO`, `DUDOSO`, `FRUSTRADO`, `LEAD_CALIENTE`. No confundir estas categorías con los estados operativos `AI_ACTIVE` y `HUMAN_ACTIVE`.

## 7. Handover humano: flujo crítico

La transferencia debe ser una operación controlada por backend, no una decisión ejecutada libremente por el LLM.

1. El cliente manifiesta frustración o el operador hace clic en «Tomar control».
2. FastAPI comprueba permisos y cambia atómicamente la conversación a `HUMAN_ACTIVE` incrementando un número de versión.
3. El backend registra `handover_started` y avisa al dashboard por WebSocket.
4. Los nuevos mensajes se registran y presentan al operador, sin programar respuestas automáticas.
5. Si Gemini ya estaba generando, su respuesta **no se envía** si el estado/versión fue modificado.
6. El operador redacta y envía desde el dashboard; FastAPI usa **el mismo bot de Telegram** para entregar la respuesta.
7. El operador selecciona «Reanudar IA»; se registra el cambio a `AI_ACTIVE` y se notifica a la interfaz.

**Concurrencia:** serializar por conversación las transiciones de ownership y los envíos; usar transacciones y verificaciones condicionales para evitar respuestas simultáneas del operador y la IA. La cancelación del proceso de Gemini por sí sola no garantiza seguridad.

## 8. Base de datos mínima

| Tabla | Campos conceptuales |
|---|---|
| `conversations` | `id`, `channel`, `external_chat_id`, `status`, `owner_id`, `version`, `created_at` |
| `messages` | `id`, `conversation_id`, `external_message_id`, `sender_type`, `content`, `created_at` |
| `leads` | `id`, `conversation_id`, `name`, `interested_course`, `stage` |
| `conversation_analysis` | `id`, `message_id`, `intent`, `lead_status`, `latency_ms`, `token_usage` |
| `conversation_events` | `id`, `conversation_id`, `type`, `payload`, `created_at` |
| `operators` | `id`, `display_name`, `role` |
| `jobs` | `id`, `conversation_id`, `status`, `attempt_count`, `available_at` |

Usar claves únicas para `(channel, external_chat_id)` y para mensajes externos identificados por canal, además de índices por `conversation_id` y fechas. Evitar almacenar tokens o secretos en tablas de conversación.

## 9. Dashboard y métricas

**Interfaz mínima:** lista de chats activos, última interacción, termómetro comercial, indicador IA/Humano, historial instantáneo, caja de respuesta del operador, controles «Tomar control» y «Reanudar IA».

**Métricas recomendadas:** conversaciones activas, mensajes por hora, leads calientes, distribución por intención, escalaciones humanas, tiempos de respuesta y fallos. Para MVP bastan consultas SQL sencillas; evitar infraestructura analítica separada.

**Tiempo real:** WebSockets autenticados en FastAPI para mensajes, estados y comandos del operador; reconectar y recuperar mensajes desde REST al perder la conexión. No transmitir indiscriminadamente conversaciones a todos los clientes conectados.

## 10. Seguridad y pruebas críticas

- Proteger el token del bot y las credenciales de Gemini/Supabase en variables de entorno; no exponerlos en Streamlit ni en el navegador.
- Autenticar y autorizar operaciones del dashboard en cada solicitud REST y conexión WebSocket.
- Bloquear descuentos, matrículas o gratuidades no autorizadas mediante reglas del backend y catálogo validado.
- Tratar mensajes del usuario y documentos como datos, no instrucciones privilegiadas.
- Limitar longitud del historial/contexto y controlar cuotas, latencia y reintentos del LLM.
- Probar expresiones con errores ortográficos, cambios de tema, solicitudes de descuentos, prompt injection y frustración.
- Verificar que no se envíen respuestas IA después del handover ni se pierdan mensajes cuando el operador responde.
- Validar que el webhook responda oportunamente y que los mensajes duplicados no creen respuestas repetidas.

## 11. Estructura sugerida del repositorio

```text
hackathon-uta-bot/
├── backend/
│   ├── src/
│   │   ├── main.py
│   │   ├── modules/
│   │   │   ├── channels/
│   │   │   ├── conversations/
│   │   │   ├── courses/
│   │   │   ├── ai_engine/
│   │   │   ├── leads/
│   │   │   └── analytics/
│   │   └── shared/
│   │       ├── config/
│   │       ├── database/
│   │       └── security/
│   ├── data/courses.json
│   └── tests/
├── worker/
│   └── main.py
├── dashboard/
│   └── app.py
├── .env.example
├── docker-compose.yml
└── README.md
```

**Separación hexagonal práctica:** contratos para `CourseRepository`, `ConversationRepository`, `LLMClient` y `ChannelSender`; implementar adaptadores JSON, PostgreSQL, Gemini y Telegram. No crear capas abstractas sin uso durante el MVP.

## 12. Plan de implementación por prioridad

| Prioridad | Implementación | Evidencia para jurado |
|---|---|---|
| P0 | Bot Telegram + Gemini | Conversación real accesible |
| P0 | Catálogo JSON + protección de precios | Respuestas correctas y rechazo de descuentos |
| P0 | Persistencia de mensajes/estado | Conversaciones visibles después de navegar |
| P0 | Handover y respuesta humana | IA se detiene y operador responde |
| P0 | Dashboard reactivo por WebSocket | Cambios sin recargar la página |
| P1 | LangGraph con agentes académico/comercial | Selección demostrable de rutas |
| P1 | Memoria conversacional | Reconoce preferencias ya mencionadas |
| P1 | KPIs e intención del prospecto | Termómetro y métricas en vivo |
| P2 | Resumen para operador o audio | Valor agregado si queda tiempo |

**Orden operativo recomendado:** primero el flujo completo Telegram → IA → Telegram; después persistencia y handover; luego dashboard y métricas; finalmente mejoras multiagente y extras. Reservar un período final para probar el despliegue, la URL del dashboard y los accesos externos.

## 13. Evolución posterior al hackathon

- **Memoria persistente:** pasar de `InMemorySaver` a un checkpointer PostgreSQL; incorporar Mem0 solo si se requieren recuerdos semánticos de largo plazo.
- **Conocimiento:** mover catálogo a PostgreSQL; adoptar RAG/pgvector únicamente si crece la documentación o las preguntas exigen búsqueda semántica.
- **Carga:** escalar workers IA independientemente del proceso web; añadir cola fiable y publicación de eventos entre instancias.
- **Canales:** incorporar WhatsApp/Messenger mediante adaptadores sin alterar el núcleo de decisiones.
- **Dashboard:** migrar a Angular si se requiere bandeja operativa compleja, manteniendo las APIs y eventos.
- **Observabilidad:** medir tiempos por nodo, costo de tokens, fallbacks y conversiones reales.

## 14. Validación frente a la rúbrica oficial

| Criterio oficial | Puntos | Evidencia propuesta |
|---|---:|---|
| Comportamiento y lógica del agente | 30 | Gemini, rutas académica/comercial, objeciones y defensas |
| Panel web e intervención humana | 30 | WebSocket, termómetro, handover y respuesta del operador |
| Arquitectura y eficiencia | 20 | Módulos, puertos/adaptadores, historial compacto y tokens |
| Innovación y sustentación | 20 | Resumen, métricas, demo estable y explicación de decisiones |
| **Total** | **100** | |

**Entregables:** bot de Telegram accesible, URL pública de dashboard sin fallos CORS, código fuente y documentación con variables de entorno y guía de despliegue.

## 15. Conclusión

Para la entrega inmediata, la opción con mejor relación entre complejidad y resultado es **FastAPI + aiogram + Gemini + LangChain + LangGraph + Supabase PostgreSQL + Streamlit/Plotly**, usando `courses.json` como catálogo autorizado e `InMemorySaver` como memoria de corto plazo. El **Conversation Manager** y la **intervención humana por WebSocket** son prioridades superiores a RAG, Mem0 o microservicios. Esta solución cumple el propósito del reto y deja una ruta explícita de crecimiento.

---

**Fuente:** Universidad Técnica de Ambato, *Hackathon 2026: Ecosistema Multi-Agente para Ventas y Gestión Conversacional*, documento técnico y rúbrica oficial facilitados para este proyecto, pp. 1–4.
