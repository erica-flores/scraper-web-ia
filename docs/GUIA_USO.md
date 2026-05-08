# Guía de uso — Hotel Scraper con LLM multi-proveedor

> Esta guía cubre el setup completo después del refactor descripto en
> [`docs/sdd/llm-multi-proveedor-fallback.md`](sdd/llm-multi-proveedor-fallback.md).
> Si venís del README original (`hotel_scraper/README.md`), lo único que cambió
> sustancialmente es **cómo configurás los proveedores de LLM**: ahora hay
> fallback automático entre Gemini, Groq, Cerebras y (opcional) OpenRouter.

## Tabla de contenidos
1. [Resumen de qué hace la app](#1-resumen-de-qué-hace-la-app)
2. [Prerrequisitos](#2-prerrequisitos)
3. [Instalación paso a paso](#3-instalación-paso-a-paso)
4. [`.env` — qué tiene que estar y de dónde sacarlo](#4-env--qué-tiene-que-estar-y-de-dónde-sacarlo)
5. [Cómo funciona la fallback chain](#5-cómo-funciona-la-fallback-chain)
6. [Cómo correr la app](#6-cómo-correr-la-app)
7. [Cómo leer los logs](#7-cómo-leer-los-logs)
8. [Cómo personalizar `providers.yaml`](#8-cómo-personalizar-providersyaml)
9. [Tests](#9-tests)
10. [Troubleshooting](#10-troubleshooting)

---

## 1. Resumen de qué hace la app

1. Recibe URLs de hoteles (CLI o vía web app).
2. Detecta si el sitio es estático (HTML plano) o dinámico (React/Vue/Angular).
3. Intenta extraer las habitaciones con 25+ selectores CSS (`habitación`, `cuarto`, `suite`, `cabaña`, `bungalow`, `departamento`, etc.).
4. Si los selectores fallan **y** activás `--llm` (o el toggle de la web), el LLM:
   - **descubre** un selector CSS específico para ese sitio,
   - **navega** autónomamente al sub-link correcto si la página actual no tiene habitaciones,
   - **extrae** las rooms directamente del HTML como último recurso.
5. Descarga las imágenes en paralelo y exporta `data.json`, `rooms.csv`, `prices.csv`.
6. La web app además te deja **chatear** sobre todos los hoteles scraped en la sesión.

**Lo nuevo del refactor** es que el LLM ya no depende sólo de Gemini: si Gemini está saturado, deprecado o sin cuota, el sistema cae automáticamente a Groq → Cerebras → OpenRouter (en el orden y combinación que vos elijas).

---

## 2. Prerrequisitos

- **Python 3.11+** (verificá con `python --version`).
- **pip** y **venv** disponibles.
- Conexión a internet desde Argentina sin VPN (todos los proveedores recomendados andan desde AR).
- ~5 minutos para crear cuentas en Groq y opcionalmente Cerebras (gratis, sólo email).

---

## 3. Instalación paso a paso

```bash
# 1. Posicionate en el directorio del scraper
cd hotel_scraper

# 2. Creá un virtualenv aislado
python -m venv venv

# 3. Activalo
#    Windows (PowerShell):
venv\Scripts\Activate.ps1
#    Windows (cmd / Git Bash):
venv\Scripts\activate
#    Linux/Mac:
source venv/bin/activate

# 4. Instalá las dependencias (incluye openai, pyyaml, pytest, pytest-mock nuevos)
pip install -r requirements.txt

# 5. Instalá el navegador para sitios dinámicos
playwright install chromium

# 6. Copiá el template de .env y editalo (siguiente sección)
cp .env.example .env
```

---

## 4. `.env` — qué tiene que estar y de dónde sacarlo

Esta es la parte más importante. El `.env` vive en `hotel_scraper/.env` (el `.gitignore` lo excluye, **nunca** lo subas).

### 4.1 Estructura mínima

```dotenv
# --- LLM providers (al menos uno tiene que estar lleno) ---
GEMINI_API_KEY=...
GROQ_API_KEY=...
GROQ_BASE_URL=https://api.groq.com/openai/v1

# --- Opcionales (pero recomendados para mayor robustez) ---
CEREBRAS_API_KEY=...
CEREBRAS_BASE_URL=https://api.cerebras.ai/v1

OPENROUTER_API_KEY=
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# --- Cache ---
LLM_CACHE_ENABLED=true

# --- Scraper ---
SCRAPER_DELAY_MIN=1.5
SCRAPER_DELAY_MAX=4.0
MAX_CONCURRENT_IMAGES=5
SCRAPER_TIMEOUT=30
SCRAPER_MAX_RETRIES=3
```

### 4.2 Cada variable explicada

#### `GEMINI_API_KEY` *(recomendado)*
- **Para qué se usa**: slot **primario** de la chain `extraction_long` (HTML completo, hasta ~18k chars) y de la chain `chat`. También aparece como **terciario** en `quick`.
- **Modelos que cubre**: `gemini-2.5-flash-lite` (default) y `gemini-2.5-flash` (red de seguridad).
- **Tier free a mayo 2026**:
  - `gemini-2.5-flash-lite`: 15 RPM, **1.000 RPD**, 1M context
  - `gemini-2.5-flash`: 10 RPM, 500 RPD, 1M context
- **Dónde sacar la key**: <https://aistudio.google.com/app/apikey> — solo email, sin tarjeta.
- **Importante**: **NO** usar `gemini-2.0-flash` ni `gemini-2.0-flash-lite`. Google los retiró el 3 de marzo de 2026 y son la causa original del problema que resolvió este refactor.

#### `GROQ_API_KEY` *(recomendado)*
- **Para qué se usa**: slot **secundario** de `extraction_long` y de `chat`. Slot **secundario** de `quick`. Es la red de seguridad más confiable cuando Gemini está saturado.
- **Modelo que cubre**: `llama-3.3-70b-versatile` (mismo Llama-70B en las 3 chains, pero con context disponible 128k para HTML largo).
- **Tier free a mayo 2026**: 30 RPM / 6.000 TPM / 1.000 RPD.
- **Dónde sacar la key**: <https://console.groq.com/keys> — solo email, sin tarjeta. **Latencia <1s, top-tier.**
- **Base URL**: `https://api.groq.com/openai/v1` (default en `.env.example`, no la cambies salvo que Groq la mueva).

#### `CEREBRAS_API_KEY` *(opcional, pero MUY recomendado)*
- **Para qué se usa**: slot **primario** de la chain `quick` — donde caen los prompts cortos: link selection (`node_llm_navigate`) y discovery de selector CSS (`_llm_discover_selector`). Es el más rápido para ese caso.
- **Modelo que cubre**: `llama-3.3-70b`.
- **Tier free a mayo 2026**: 30 RPM, 1.000.000 tokens/día (!), pero con **cap de 8.192 tokens de contexto en free**. Por eso solo lo metimos en chain `quick`, donde los prompts son ~2k–6k tokens.
- **Dónde sacar la key**: <https://cloud.cerebras.ai/platform/api-keys> — solo email, sin tarjeta.
- **Base URL**: `https://api.cerebras.ai/v1`.
- **Si la dejás vacía**: la chain `quick` salta directo al slot 2 (Groq), sin error. Funciona, pero pierde un poco de velocidad en navigation/selector discovery.

#### `OPENROUTER_API_KEY` *(opcional)*
- **Para qué se usa**: en el `providers.yaml` por default está **comentado**. Hay que descomentar el bloque para agregarlo a alguna chain.
- **Modelos sugeridos**: `deepseek/deepseek-chat-v3:free`, `meta-llama/llama-3.3-70b-instruct:free`.
- **Tier free a mayo 2026**: 50 RPD, 20 RPM en cuenta sin créditos. **Si cargás $10 una vez (no recurrente), sube a 1.000 RPD permanentes** y queda como red de seguridad muy generosa.
- **Dónde sacar la key**: <https://openrouter.ai/keys>.
- **Base URL**: `https://openrouter.ai/api/v1`.
- **Cuándo activarlo**: si ves logs frecuentes de `Todos los proveedores LLM fallaron`, o querés diversificar más allá de Gemini/Groq/Cerebras.

#### `LLM_CACHE_ENABLED` *(default `true`)*
- Cuando es `true`, las respuestas LLM se cachean en `hotel_scraper/.cache/llm_cache.sqlite` por 24hs (TTL configurable en `providers.yaml`). Re-scrapear el mismo hotel dentro de ese plazo no quema cuota.
- Ponelo en `false` mientras desarrollás prompts (sino las "iteraciones" no llaman al LLM y parece que no cambia nada).

#### Variables del scraper (las dejás como están salvo que tengas un caso especial)
- `SCRAPER_DELAY_MIN` / `SCRAPER_DELAY_MAX`: delay aleatorio entre fetches HTTP (cortesía con el server del hotel).
- `MAX_CONCURRENT_IMAGES`: cuántas imágenes baja en paralelo por hotel.
- `SCRAPER_TIMEOUT`: timeout HTTP por request.
- `SCRAPER_MAX_RETRIES`: reintentos de fetch antes de bandera roja.

### 4.3 Configuración mínima funcional vs. recomendada

| Setup | Qué keys necesitás | Robustez |
|---|---|---|
| **Mínimo absoluto** | Solo `GEMINI_API_KEY` | Funciona pero te exponés a 429 cuando Gemini se satura |
| **Recomendado** | `GEMINI_API_KEY` + `GROQ_API_KEY` | 2.000 RPD agregados, fallback automático, cubre el 99% de los casos |
| **Robusto** | `GEMINI_API_KEY` + `GROQ_API_KEY` + `CEREBRAS_API_KEY` | + 1M tokens/día gratis para tareas cortas |
| **Paranoico** | Los 3 anteriores + `OPENROUTER_API_KEY` (con $10 cargados) | + 1.000 RPD adicionales, 4 proveedores en cascada |

---

## 5. Cómo funciona la fallback chain

El sistema tiene **3 chains independientes**, una por cada tipo de tarea LLM:

| Chain | Cuándo se usa | Slots por default (en orden) |
|---|---|---|
| `extraction_long` | Extraer rooms del HTML completo (hasta 18k chars). Llamado desde `node_llm_extract`. | 1️⃣ Gemini 2.5 Flash-Lite → 2️⃣ Groq Llama-3.3-70B → 3️⃣ Gemini 2.5 Flash |
| `quick` | Tareas cortas: elegir el mejor link de un menú (`node_llm_navigate`), descubrir selector CSS (`_llm_discover_selector`). | 1️⃣ Cerebras Llama-3.3-70B → 2️⃣ Groq → 3️⃣ Gemini 2.5 Flash-Lite |
| `chat` | Endpoint `/api/chat` de la web app. | 1️⃣ Gemini 2.5 Flash-Lite → 2️⃣ Groq |

### Lógica de cada llamada

Para cada slot en el orden definido:

1. **¿Está disabled?** Si la `api_key_env` (o `base_url_env`) que requiere ese slot no está en tu `.env`, se loguea `[llm] skipped (missing env GROQ_API_KEY)` y pasa al siguiente. **No falla la app.**
2. **¿Cabe el prompt?** Estima `len(prompt) // 4` y compara con `max_input_tokens` del slot. Si no entra, se loguea `[llm] skipped (oversized prompt 4500 > cap 7000)` y pasa al siguiente. (Esto es lo que evita mandar HTML de 18k chars al slot Cerebras-quick que tiene cap de 7k.)
3. **Llamada al provider** con tenacity:
   - **3 intentos totales** (1 inicial + 2 retries).
   - Backoff exponencial 2-10s.
   - **Sólo retrae en `RetryableError`** (429, 503, timeout, connection). `FatalError` (401, 403, 400) corta seco y va al siguiente slot.
4. Si **algún slot devuelve éxito** → se loguea `[llm] success (850ms, model=llama-3.3-70b-versatile)`, el response se guarda en cache y la función retorna.
5. Si **TODOS los slots fallan** → `RuntimeError: Todos los proveedores LLM fallaron para 'extraction_long'. Último error: …`

### Cache

- Cada llamada exitosa se guarda con clave `sha256(task + prompt)` en `.cache/llm_cache.sqlite`.
- TTL default: **24 horas** (configurable en `providers.yaml` → `cache.ttl_hours`).
- En el log aparece como `[llm] cache hit (...)` cuando reusa.

---

## 6. Cómo correr la app

### Web app (recomendado)

```bash
cd hotel_scraper
venv\Scripts\activate    # o source venv/bin/activate
python run.py
```

Abrí <http://localhost:5000> en el navegador. Pegás 1 o varias URLs, activás el toggle "Modo IA", y mirás cómo trabaja en vivo.

### CLI (para 1 URL puntual)

```bash
# Modo automático (sin LLM, sólo selectores CSS)
python -m main --url https://hotelhaedo.com/

# Con LLM (recomendado): activa la fallback chain completa
python -m main --url https://hotelhaedo.com/ --llm

# Con logs detallados
python -m main --url https://hotelhaedo.com/ --llm --log-level DEBUG

# Custom output dir
python -m main --url https://hotelhaedo.com/ --llm --output ./mis_scrapes
```

Cada run genera una carpeta con timestamp en `output/<dominio>_<fecha_hora>/` con `data.json`, `rooms.csv`, `prices.csv` e `images/<nombre_room>/`.

---

## 7. Cómo leer los logs

Después del refactor, cada llamada al LLM aparece en los logs y en la UI con esta forma:

```
[llm] success (847ms, model=llama-3.3-70b-versatile)     ← provider primario respondió OK
[llm] cache hit (gemini-2.5-flash-lite)                  ← respuesta cacheada
[llm] skipped (missing env CEREBRAS_API_KEY)             ← slot deshabilitado por falta de key
[llm] skipped (oversized prompt 4500 > cap 7000)         ← prompt no entra en este slot
[llm] retry exhausted: HTTP 429                          ← slot agotó sus 3 intentos
[llm] fatal: invalid api key                             ← slot tiró error permanente
```

Y en la UI vas a ver, abajo de cada paso del pipeline:

```
[4/7] LLM → 'habitaciones.html' (link a la sección de rooms) (via groq:llama-3.3-70b-versatile, 850ms)
[4b/7] LLM extract: 8 rooms (via gemini:gemini-2.5-flash-lite, 1240ms)
```

Si ves `(via xxx, cached)` significa que ese paso vino del cache local — no quemó cuota.

---

## 8. Cómo personalizar `providers.yaml`

El archivo vive en `hotel_scraper/llm/providers.yaml`. Editalo si querés:

### Cambiar el orden de fallback
Cambiá el orden de los items dentro de cada chain. El primero que tenga env válida y prompt que entre es el que se prueba primero.

### Activar OpenRouter
Descomentá los renglones del final del archivo y agregalos a la chain donde lo quieras. Ejemplo, agregar OpenRouter como red final en `extraction_long`:

```yaml
chains:
  extraction_long:
    - provider: gemini
      model: gemini-2.5-flash-lite
      api_key_env: GEMINI_API_KEY
      max_input_tokens: 900000
    - provider: openai_compatible
      model: llama-3.3-70b-versatile
      base_url_env: GROQ_BASE_URL
      api_key_env: GROQ_API_KEY
      max_input_tokens: 120000
    - provider: gemini
      model: gemini-2.5-flash
      api_key_env: GEMINI_API_KEY
      max_input_tokens: 900000
    - provider: openai_compatible           # <-- nuevo slot OpenRouter
      model: deepseek/deepseek-chat-v3:free
      base_url_env: OPENROUTER_BASE_URL
      api_key_env: OPENROUTER_API_KEY
      max_input_tokens: 60000
```

### Cambiar el TTL del cache
```yaml
cache:
  enabled: true
  db_path: .cache/llm_cache.sqlite
  ttl_hours: 168    # 7 días, por ejemplo
```

### Desactivar cache permanentemente
```yaml
cache:
  enabled: false
```
o ponelo `false` solo en una sesión vía `.env`: `LLM_CACHE_ENABLED=false`.

---

## 9. Tests

```bash
cd hotel_scraper
venv\Scripts\activate
pytest tests/ -v
```

Lo que cubren:
- `tests/test_parsers.py` — parsers CSS de habitaciones, precios, turnos, imágenes (preexistente).
- `tests/test_llm_router.py` — fallback chain: retryable → next slot, fatal → next slot, oversized skip, disabled skip, all-fail raise, **regresión: el YAML default no debe contener `gemini-2.0-flash` ni `gemini-2.0-flash-lite`**.
- `tests/test_llm_cache.py` — hit, miss, TTL expiration, disabled bypass, clear, separación de hash por TaskKind.

---

## 10. Troubleshooting

### "ImportError: No module named 'openai'"
No instalaste las dependencias nuevas. Volvé a correr `pip install -r requirements.txt` con el venv activado.

### "RuntimeError: Todos los proveedores LLM fallaron para 'extraction_long'"
Ningún slot pudo responder. Posibles causas:
1. Todas las keys que tenés son inválidas o están vacías → revisá `.env`.
2. Estás pegando 429s en Gemini Y en Groq al mismo tiempo (raro pero posible) → esperá 60s y volvé a probar, o agregá Cerebras/OpenRouter.
3. Tu IP está bloqueada por uno o más proveedores → probá desde otra red.

Buscá en los logs los `[llm] skipped` y `[llm] fail` para ver exactamente qué falló.

### "Validation error en providers.yaml"
El YAML tiene una key faltante o un tipo incorrecto. El mensaje de Pydantic te dice qué línea. Lo más común: `max_input_tokens` con un valor no numérico, o un slot al que le faltan campos.

### El cache me molesta mientras desarrollo prompts
`LLM_CACHE_ENABLED=false` en tu `.env`, o:
```bash
# borrar todo el cache una sola vez
python -c "from llm.llm_client import _get_router; _get_router(); from llm.llm_client import _cache; print('borradas:', _cache.clear())"
```

### ¿Cómo verifico que mis keys funcionan sin lanzar un scrape entero?
```bash
python _test_llm.py   # script existente
```
Te dice qué modelos de Gemini responden y prueba el `LLMClient` con la chain completa.

### Algo más raro que esto
Activá logs detallados:
```bash
python -m main --url <url> --llm --log-level DEBUG
```
o, en la web, mirá la consola donde corriste `python run.py`.
