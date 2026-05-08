# SDD: LLM Multi-Proveedor con Fallback Chain y Routing por Tarea

> Generado: 2026-05-08. Estado: en progreso. Tipo: Full-SDD.

## Resumen ejecutivo

- **Causa raíz del incidente reportado**: el slot primario del fallback chain en `llm/llm_client.py` apunta a `gemini-2.0-flash`, modelo retirado por Google el 3 de marzo de 2026. Cada request quema ~4s en reintentos antes de pegarle al primer modelo vivo.
- **Refactor objetivo**: reemplazar el cliente Gemini-only por una abstracción `LLMProvider` con implementaciones drop-in vía OpenAI SDK (Groq, Cerebras, OpenRouter) + Gemini nativo (google-genai), seleccionables por configuración.
- **Routing por tarea**: prompts cortos (link-nav, selector-discovery) usan chain "fast" donde Cerebras es viable; prompts largos (HTML extraction, chat) usan chain "long-context" sin Cerebras (cap de 8k tokens en free tier).
- **Cache opcional** de respuestas LLM por `hash(prompt)` en SQLite local — evita re-quemar cuota cuando el usuario re-scrapea el mismo hotel.
- **Compatibilidad hacia atrás**: la API pública (`extract_json`, `generate_text`) se mantiene intacta — los 3 nodos del graph y el endpoint de chat no se modifican en lo esencial.

## 1. Visión

- **Objetivo principal**: eliminar la dependencia exclusiva de Gemini para que el scraper siga operativo cuando un proveedor está saturado, deprecado o limitado por geografía. Convertir la capa LLM en un componente robusto con fallback automático entre proveedores heterogéneos.

- **Métricas de éxito**:
  - 0% de requests perdidos por modelo deprecado (validado por tests que verifican que `_MODEL_CHAIN` no contiene IDs retirados).
  - Latencia P50 de `extract_json` ≤ 3s en el primary slot vivo (era ~7s con el modelo retirado en cabeza).
  - El sistema completa un scrape end-to-end con `--llm` aunque el primary provider devuelva 429/503 en el primer intento (verificable con tests de integración mockeados).
  - Cobertura mínima de tests del router LLM ≥ 80% en líneas.

- **Casos de uso**:
  1. **Scrape con extracción larga**: el orchestrator llama `extract_json(prompt_18k_chars)` para `node_llm_extract`. El router elige chain "long-context": prueba `gemini-2.5-flash-lite` → Groq `llama-3.3-70b-versatile` → `gemini-2.5-flash`. Devuelve el primer JSON válido.
  2. **Scrape con tarea corta**: `_llm_discover_selector` llama `extract_json(prompt_8k_chars)`. El router elige chain "fast" donde Cerebras `llama-3.3-70b` puede entrar como primario por velocidad.
  3. **Re-scrape del mismo hotel**: el cache LLM intercepta el `prompt` por hash y devuelve la respuesta cacheada sin pegar a ningún proveedor (TTL configurable, default 24h).
  4. **Chat conversacional**: `/api/chat` llama `generate_text(prompt_5k)` y obtiene respuesta libre del primer proveedor disponible.

- **Fuera de alcance**:
  - Rediseño del pipeline de scraping (LangGraph, parsers, fetchers) — sólo se tocan los puntos donde se instancia el cliente LLM.
  - Cambios al schema Pydantic de `Hotel/Room/Price/Shift/RoomImage`.
  - Frontend / UI nueva (la app web sigue igual; sólo verá logs más informativos).
  - Métricas exportadas a sistemas externos (Prometheus, Grafana). El observability scope se limita a logs estructurados con loguru.
  - Multi-tenancy o gestión de múltiples API keys por proveedor.
  - Streaming de respuestas LLM (todas las llamadas son síncronas y completas).

## 2. Arquitectura

- **Stack**:
  - Python 3.11+, type hints obligatorios.
  - **Nuevo**: `openai>=1.50.0` (cliente drop-in para Groq, Cerebras, OpenRouter — los tres exponen `/v1/chat/completions` compatible).
  - Existente: `google-genai`, `loguru`, `tenacity`, `python-dotenv`, `pydantic`.
  - **Cache**: `sqlite3` (stdlib, sin dependencias nuevas).
  - **Tests**: `pytest`, `pytest-mock` (agregar a requirements).

- **Patrón**: **Strategy + Chain of Responsibility** sobre la capa LLM.
  - `LLMProvider` (ABC) — contrato único: `complete(prompt, schema_mode) → str`.
  - Implementaciones concretas: `GeminiProvider`, `OpenAICompatibleProvider` (parametrizable con base_url + key + model_id; cubre Groq/Cerebras/OpenRouter).
  - `LLMRouter` — orquesta la chain por tipo de tarea (`TaskKind.EXTRACTION_LONG`, `TaskKind.QUICK`, `TaskKind.CHAT`), aplica retry/fallback, registra métricas y consulta el cache.
  - `LLMCache` — wrapper SQLite con `get(prompt_hash) / put(prompt_hash, response)`.
  - `LLMClient` (clase fachada existente) — mantiene la API pública intacta, internamente delega al router.

- **Integraciones**: APIs HTTP públicas de los 4 proveedores. Sin BD, sin colas, sin servicios externos.

- **Diagrama**:
  ```mermaid
  flowchart TD
      A[graph/nodes.py - node_llm_extract] -->|extract_json prompt 18k| C[LLMClient]
      B[graph/nodes.py - node_llm_navigate] -->|extract_json prompt 2k| C
      D[_llm_discover_selector] -->|extract_json prompt 8k| C
      E[web/routes.py - /api/chat] -->|generate_text prompt 5k| C
      C --> R[LLMRouter]
      R -->|TaskKind| K[LLMCache SQLite]
      K -- miss --> CH[Chain por TaskKind]
      K -- hit --> R
      CH --> P1[Provider primary]
      P1 -- 429/503/timeout --> P2[Provider secondary]
      P2 -- 429/503/timeout --> P3[Provider tertiary]
      P1 --> OUT[texto JSON o libre]
      P2 --> OUT
      P3 --> OUT
      OUT --> R
      R --> C
  ```

- **Configuración** (formato YAML en `hotel_scraper/llm/providers.yaml`, opcionalmente sobre-escrita por `.env`):
  ```yaml
  cache:
    enabled: true
    db_path: .cache/llm_cache.sqlite
    ttl_hours: 24
  chains:
    extraction_long:
      - { provider: gemini,            model: gemini-2.5-flash-lite, max_input_tokens: 900000 }
      - { provider: openai_compatible, model: llama-3.3-70b-versatile, base_url_env: GROQ_BASE_URL, api_key_env: GROQ_API_KEY, max_input_tokens: 120000 }
      - { provider: gemini,            model: gemini-2.5-flash,      max_input_tokens: 900000 }
    quick:
      - { provider: openai_compatible, model: llama-3.3-70b,         base_url_env: CEREBRAS_BASE_URL, api_key_env: CEREBRAS_API_KEY, max_input_tokens: 7000 }
      - { provider: openai_compatible, model: llama-3.3-70b-versatile, base_url_env: GROQ_BASE_URL, api_key_env: GROQ_API_KEY,   max_input_tokens: 120000 }
      - { provider: gemini,            model: gemini-2.5-flash-lite, max_input_tokens: 900000 }
    chat:
      - { provider: gemini,            model: gemini-2.5-flash-lite, max_input_tokens: 900000 }
      - { provider: openai_compatible, model: llama-3.3-70b-versatile, base_url_env: GROQ_BASE_URL, api_key_env: GROQ_API_KEY,   max_input_tokens: 120000 }
  ```
  Variables `.env` nuevas: `GROQ_API_KEY`, `GROQ_BASE_URL=https://api.groq.com/openai/v1`, `CEREBRAS_API_KEY`, `CEREBRAS_BASE_URL=https://api.cerebras.ai/v1`, `OPENROUTER_API_KEY` (opcional), `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`, `LLM_CACHE_ENABLED=true`.

## 3. Ejecución

### Desglose técnico

1. **Bloque 1 — Definir contrato y configuración (no breaking)** ✓
   - [x] Crear `hotel_scraper/llm/types.py` con `TaskKind` (Enum: `EXTRACTION_LONG`, `QUICK`, `CHAT`), `ProviderConfig`, `RouterConfig`, `CacheConfig`, `LLMResponse` y `load_router_config(yaml_path)`.
   - [x] Crear `hotel_scraper/llm/providers.yaml` con la configuración default (3 chains × 3 slots, OpenRouter comentado).
   - [x] Actualizar `requirements.txt` (`openai`, `pyyaml`, `pytest`, `pytest-mock`) y crear `.env.example` con todas las vars nuevas.
   - _Nota: la lógica de "marcar slot disabled si falta la key" se implementa en el Bloque 3 (router), no en la carga de config — `RouterConfig` valida estructura, el router resuelve runtime._

2. **Bloque 2 — Implementar providers** ✓
   - [x] `hotel_scraper/llm/providers/base.py` → ABC `LLMProvider` + `LLMProviderError`, `RetryableError`, `FatalError`.
   - [x] `hotel_scraper/llm/providers/gemini.py` → `GeminiProvider` con `response_mime_type="application/json"` cuando `json_mode=True`. Clasificación por tokens en el mensaje de error.
   - [x] `hotel_scraper/llm/providers/openai_compatible.py` → `OpenAICompatibleProvider` con `response_format={"type":"json_object"}`. Friendly name auto-derivado del host (groq / cerebras / openrouter). Clasificación basada en las excepciones tipadas del SDK openai.
   - _Nota: la limpieza de markdown fences se hace en la fachada (Bloque 5), no en providers — Gemini con `application/json` y OpenAI con `json_object` ya devuelven JSON limpio; los fences sólo aparecen en `generate_text` libre._

3. **Bloque 3 — Router y fallback chain** ✓
   - [x] `hotel_scraper/llm/router.py` con `LLMRouter`:
     - [x] Constructor recibe `RouterConfig`. Cada slot envuelto en `_SlotState` (lazy: instancia el provider en el primer uso, recuerda el `disabled_reason` si falta env).
     - [x] `run(task, prompt, *, json_mode)` itera la chain: skipea `oversized` (estimado `len(prompt)//4` > `max_input_tokens`), skipea `disabled`, llama el provider con retry tenacity (3 intentos, exp 2-10s, sólo en `RetryableError`).
     - [x] Si todos fallan: `RuntimeError("Todos los proveedores LLM fallaron para '<task>'. Último error: …")`.
     - [x] Logs con `logger.bind(task, provider, model)`: `[llm] skipped (...)`, `[llm] success (Xms)`, `[llm] retry exhausted: …`, `[llm] fatal: …`.

4. **Bloque 4 — Cache LLM en SQLite** ✓
   - [x] `hotel_scraper/llm/cache.py` con `LLMCache(db_path, ttl_hours, enabled=True)`. Schema: `llm_cache(prompt_hash PK, task, text, provider, model, latency_ms, created_at)`.
   - [x] `_hash(task, prompt) = sha256("task.value|prompt")`.
   - [x] `get` verifica TTL; `put` hace `INSERT OR REPLACE`. `clear()` agregado para futura CLI.
   - [x] `.cache/` se crea on-demand. Conexión `check_same_thread=False` + `threading.Lock` para escrituras.
   - [x] Si `enabled=False` o falla la apertura del SQLite, todas las operaciones son no-op (con warning de loguru, sin tirar el sistema).
   - [x] Router cableado: lee cache antes de iterar, escribe al primer success. Log `[llm] cache hit (...)`.
   - _Nota: el flag `LLM_CACHE_ENABLED` del .env se aplica desde la fachada (Bloque 5) sobre `CacheConfig.enabled`._

5. **Bloque 5 — Refactor de la fachada `LLMClient`** ✓
   - [x] `llm/llm_client.py` reescrito: 100 líneas, sin `_MODEL_CHAIN`, sin código de retry/fallback (quedó todo en el router).
   - [x] Singletons módulo: `_router` y `_cache` lazy. Inicialización vía `_get_router()`. Path del YAML: `Path(__file__).parent / "providers.yaml"`.
   - [x] `LLMClient.__init__()` dispara `_get_router()` para fallar temprano si el YAML está roto. No requiere API keys: las valida el router por slot.
   - [x] `_env_bool("LLM_CACHE_ENABLED", True)` aplicado sobre `CacheConfig.enabled` para honrar el override desde `.env`.
   - [x] `extract_json` → `EXTRACTION_LONG`, `json_mode=True`. `extract_json_quick` → `QUICK`. `generate_text` → `CHAT`, `json_mode=False`.
   - [x] `_strip_json_fences` centralizado en la fachada como red de seguridad por si un proveedor no honra `response_format`.
   - [x] Errores de parseo levantan `ValueError("LLM JSON parse failed: ...")` (compat con el contrato anterior).
   - [x] Confirmado: `grep gemini-2.0-flash llm/**/*.py` no devuelve nada.

6. **Bloque 6 — Adaptación mínima de callers + observabilidad** ✓
   - [x] `llm/llm_client.py`: agregada `LLMClient.last_response` (property sobre el module-global `_last_response`, set tras cada router.run exitoso).
   - [x] `graph/nodes.py`: helper `_get_llm_client()` (singleton lazy) + `_llm_meta_suffix()`. Las 3 llamadas a `LLMClient()` ahora pasan por el singleton.
   - [x] `web/routes.py`: mismo patrón singleton para `/api/chat`.
   - [x] Migrados a `extract_json_quick` (chain `QUICK`): `node_llm_navigate` (link selection) y `_llm_discover_selector` (selector CSS). `node_llm_extract` se queda en `extract_json` (chain `EXTRACTION_LONG`) por el HTML de 18k chars.
   - [x] Logs `[4/7]` y `[4b/7]` ahora terminan en ` (via provider:model, Xms)` o ` (via provider:model, cached)`. Visible en la UI vía el `progress` del job.

7. **Bloque 7 — Tests** ✓ (código completo; ejecución pendiente del usuario)
   - [x] `hotel_scraper/tests/conftest.py` — agrega `hotel_scraper/` y la raíz del repo al `sys.path` para que coexistan los imports `from llm.router import …` (codebase) y `from hotel_scraper.parser… import …` (test_parsers.py preexistente).
   - [x] `hotel_scraper/tests/test_llm_router.py` con 6 tests:
     - `test_chain_falls_back_on_retryable_error` — 3 retries del primero, fallback al secundario.
     - `test_chain_falls_back_on_fatal_without_retry` — `FatalError` → next slot sin retry.
     - `test_chain_skips_disabled_provider` — env vacía → slot disabled, salto al siguiente.
     - `test_chain_skips_oversized_prompt` — prompt > `max_input_tokens` → skip.
     - `test_chain_all_fail_raises` — `RuntimeError("Todos los proveedores LLM fallaron…")`.
     - `test_no_retired_models_in_default_config` — carga `llm/providers.yaml` y verifica que ningún chain liste `gemini-2.0-flash` o `gemini-2.0-flash-lite` (regresión del incidente original).
   - [x] `hotel_scraper/tests/test_llm_cache.py` con 6 tests: hit, miss, TTL expiration, disabled bypass, clear, hash separation por TaskKind.
   - [x] `tests/test_parsers.py` no modificado.
   - _Pendiente del usuario: `pip install -r requirements.txt && pytest tests/` para confirmar que pasan en su venv._

### Criterios de aceptación

- [ ] **CA-1 — Sin modelos retirados en cabeza**: `_MODEL_CHAIN` y cualquier referencia a `gemini-2.0-flash` o `gemini-2.0-flash-lite` está eliminada del código y reemplazada por la config YAML. Test `test_no_retired_models_in_default_config` pasa.
- [ ] **CA-2 — Fallback multi-proveedor funcional**: con `GEMINI_API_KEY` deliberadamente inválida y `GROQ_API_KEY` válida, un scrape con `--llm` completa exitosamente — el router salta a Groq sin intervención manual. Verificable con un test de integración mockeado y, si el usuario provee keys, con un smoke test real.
- [ ] **CA-3 — API pública intacta**: la firma de `LLMClient.extract_json(prompt) → dict | list` y `LLMClient.generate_text(prompt) → str` no cambia. Los 3 nodos de `graph/nodes.py` y `web/routes.py` no requieren cambios funcionales (sólo refactor a singleton, opcionalmente).
- [ ] **CA-4 — Cache reduce llamadas**: re-scrape de la misma URL en menos de 24h emite ≥1 evento de log `llm.cache_hit` y reduce a 0 las llamadas reales a proveedores LLM (verificable con mocks).
- [ ] **CA-5 — Observabilidad mínima**: cada llamada al router emite un log estructurado (loguru bind) con campos `task`, `provider`, `model`, `latency_ms`, `outcome`, `cached`. Inspeccionable a `INFO` en CLI y propagable al `progress` de `job_store` para que se vea en la UI.

## 4. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Groq/Cerebras cambian sus rate limits o retiran modelos en 2026-Q3 (como pasó con `gemini-2.0-flash`) | Media | Medio | Config en YAML separable del código + test que valida modelos no retirados; rollover a nuevo modelo es 1 línea de YAML |
| OpenAI SDK no es 100% drop-in para Groq/Cerebras en algún edge case (ej. `response_format`) | Media | Bajo | Detectar feature flags por proveedor en `OpenAICompatibleProvider`; degradar `json_mode` a system-prompt + parser tolerante si el endpoint no lo soporta |
| Cache SQLite corrupto bloquea la app | Baja | Medio | Wrap en try/except amplio: si el cache rompe, loguear warning y seguir sin cache (no fallar el scrape) |
| Hash colisiones del prompt (mismos chars, distinto contexto) | Muy baja | Bajo | SHA-256 sobre `task.value + prompt` — colisión es astronómicamente improbable |
| Re-instanciar `LLMClient` por nodo (estado actual) abre N conexiones SQLite | Media | Bajo | Bloque 6 lo resuelve con singleton lazy a nivel módulo |
| Algunos proveedores devuelven JSON con markdown fences o comentarios; el parser actual ya los maneja parcialmente | Alta | Bajo | Centralizar el saneo de respuesta en `extract_json` (strip de fences + tolerancia a basura post-JSON) y testear con fixtures de cada proveedor |
| El usuario activa el cache en desarrollo y no ve cambios al iterar prompts | Media | Bajo | Documentar `LLM_CACHE_ENABLED=false` para dev; agregar comando CLI `python -m hotel_scraper.llm.cache --clear` |

## 5. Open questions

- [ ] ¿Querés que el cache LLM también persista entre runs por **URL del hotel** (clave compuesta `hash(url + html_hash + task)`) además de por prompt? Esto evitaría re-procesar HTML idéntico aún si el prompt template cambia ligeramente.
- [ ] ¿Habilito OpenRouter como cuarto slot por default, o lo dejamos comentado en el YAML hasta que cargues los $10 que activan los 1000 RPD? Sin eso, sus 50 RPD diarios son margen muy chico.
- [ ] ¿Te interesa una verificación de cuota proactiva (ej. detectar 429 y "pausar" el slot por N segundos antes de reintentarlo) o alcanza con el retry exponencial actual?
- [ ] ¿Mantenemos `GROQ_API_KEY` como obligatoria para arrancar o el sistema debe poder correr sólo con Gemini (graceful degradation a chain de 2 slots Gemini)?
- [ ] ¿Querés un comando CLI nuevo (`python -m hotel_scraper.llm.providers --check`) que pruebe cada proveedor configurado al arranque y reporte estado, similar a `_test_llm.py`?
