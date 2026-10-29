-- ==============================================================================
-- SCHEMA SUPABASE: Ecosistema Multi-Agente Ventas & Gestión Conversacional
-- Reto Oficial Hackathon 2026 - FISEI / UTA (Aliado Oficial: Supabase)
-- ==============================================================================

-- 1. Tabla: PROSPECTOS (Leads captados)
CREATE TABLE IF NOT EXISTS prospectos (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    telegram_chat_id TEXT UNIQUE NOT NULL,
    primer_nombre TEXT,
    username TEXT,
    telefono TEXT,
    email TEXT,
    nivel_interes TEXT DEFAULT 'DUDOSO' CHECK (nivel_interes IN ('FRIO', 'DUDOSO', 'INTERESADO', 'CALIENTE')),
    creado_en TIMESTAMPTZ DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Tabla: CONVERSACIONES (Hilos de atención y estado de Handover)
CREATE TABLE IF NOT EXISTS conversaciones (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    prospecto_id BIGINT REFERENCES prospectos(id) ON DELETE CASCADE,
    canal TEXT DEFAULT 'TELEGRAM' CHECK (canal IN ('TELEGRAM', 'WEB')),
    ia_pausada BOOLEAN DEFAULT FALSE,
    estado_handover TEXT DEFAULT 'BOT_ACTIVO' CHECK (estado_handover IN ('BOT_ACTIVO', 'OPERADOR_ACTIVO', 'CERRADO')),
    termometro TEXT DEFAULT 'INTERESADO' CHECK (termometro IN ('INTERESADO', 'DUDOSO', 'FRUSTRADO', 'CALIENTE')),
    ultima_interaccion TIMESTAMPTZ DEFAULT NOW(),
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Tabla: MENSAJES (Historial de interacciones con trazabilidad)
CREATE TABLE IF NOT EXISTS mensajes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    conversacion_id BIGINT REFERENCES conversaciones(id) ON DELETE CASCADE,
    remitente TEXT NOT NULL CHECK (remitente IN ('PROSPECTO', 'BOT_IA', 'OPERADOR_HUMANO')),
    contenido TEXT NOT NULL,
    intencion_detectada TEXT,
    enviado_en TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Tabla: CURSOS_PENSUM (Catálogo académico oficial para inferencia del LLM)
CREATE TABLE IF NOT EXISTS cursos_pensum (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo TEXT UNIQUE NOT NULL,
    nombre TEXT NOT NULL,
    duracion TEXT NOT NULL,
    precio NUMERIC(10, 2) NOT NULL,
    precio_promocional NUMERIC(10, 2),
    descripcion TEXT,
    temario_resumido JSONB,
    activo BOOLEAN DEFAULT TRUE
);

-- 5. Tabla: AUDITORIA_INFERENCIA (Métricas de tokens, latencia y seguridad)
CREATE TABLE IF NOT EXISTS auditoria_inferencia (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mensaje_id BIGINT REFERENCES mensajes(id) ON DELETE SET NULL,
    modelo TEXT DEFAULT 'gemini-1.5-flash',
    tokens_prompt INT DEFAULT 0,
    tokens_completion INT DEFAULT 0,
    latencia_ms INT DEFAULT 0,
    bloqueo_seguridad BOOLEAN DEFAULT FALSE,
    regla_activada TEXT,
    registrado_en TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Inserción de Cursos Oficiales Iniciales
INSERT INTO cursos_pensum (codigo, nombre, duracion, precio, precio_promocional, descripcion, temario_resumido)
VALUES 
    (
        'PY-IA-101', 
        'Desarrollo de Inteligencia Artificial con Python', 
        '8 Semanas (60 Horas)', 
        180.00, 
        149.99,
        'Domina Python para Machine Learning, LLMs, Agentes Inteligentes y RAG con FastAPI.',
        '["Sintaxis Moderna & Async", "LangChain & Gemini API", "Vector Stores & Embeddings", "Despliegue en Cloud"]'::jsonb
    ),
    (
        'CLOUD-DEV-201', 
        'Cloud Computing & DevOps con AWS y Docker', 
        '6 Semanas (45 Horas)', 
        160.00, 
        135.00,
        'Aprende contenedores Docker, CI/CD pipelines, despliegues serverless y arquitectura cloud.',
        '["Docker & Kubernetes Básico", "AWS Lambda & S3", "GitHub Actions CI/CD", "Monitoreo & Logs"]'::jsonb
    ),
    (
        'CYBER-SEC-301', 
        'Ciberseguridad Ofensiva y Pentesting Ético', 
        '10 Semanas (80 Horas)', 
        220.00, 
        190.00,
        'Auditoría de vulnerabilidades, análisis de malware, seguridad en redes y pruebas de penetración.',
        '["Hacking Ético Fundamentos", "Seguridad Web & OWASP Top 10", "Análisis de Redes con Wireshark", "Reportes de Auditoría"]'::jsonb
    )
ON CONFLICT (codigo) DO NOTHING;

-- Habilitar Supabase Realtime en las tablas clave
ALTER PUBLICATION supabase_realtime ADD TABLE conversaciones;
ALTER PUBLICATION supabase_realtime ADD TABLE mensajes;
