# 🏨 Hotel Scraper AI

Sistema de scraping inteligente de sitios web hoteleros, potenciado por **Gemini AI** y orquestado con **LangGraph**. Extrae habitaciones, precios, turnos e imágenes de forma automática y expone una interfaz web con **Flask** donde podés ingresar múltiples URLs, visualizar los resultados y chatear con un asistente IA sobre los datos extraídos.

---

## 📋 Tabla de Contenidos

- [¿Qué hace esta app?](#-qué-hace-esta-app)
- [Tecnologías](#-tecnologías)
- [Arquitectura del proyecto](#-arquitectura-del-proyecto)
- [Flujo de la aplicación](#-flujo-de-la-aplicación)
- [Sistema de extracción inteligente](#-sistema-de-extracción-inteligente)
- [Requisitos previos](#-requisitos-previos)
- [Instalación paso a paso](#-instalación-paso-a-paso)
- [Configuración del .env](#-configuración-del-env)
- [Cómo usar la app web](#-cómo-usar-la-app-web)
- [Cómo usar la CLI](#-cómo-usar-la-cli)
- [Estructura de los archivos de salida](#-estructura-de-los-archivos-de-salida)
- [Para desarrolladores](#-para-desarrolladores)
- [Preguntas frecuentes](#-preguntas-frecuentes)

---

## ¿Qué hace esta app?

1. **Recibe URLs** de sitios web de hoteles (uno o varios a la vez).
2. **Detecta automáticamente** si el sitio es estático (HTML plano) o dinámico (React, Vue, Angular, etc.).
3. **Intenta extraer con 25+ selectores CSS** las unidades de alojamiento: habitaciones, cuartos, suites, departamentos, cabañas, bungalows, villas y más.
4. Si los selectores no son suficientes, **activa Gemini AI** en una cadena de 3 intentos progresivos:
   - **Descubre el selector correcto**: el LLM analiza el HTML del sitio e identifica el selector CSS específico que usa ese hotel.
   - **Navega autónomamente**: si la página actual no tiene habitaciones, el LLM lee el menú de navegación, elige la subpágina más relevante (ej. `suites.php`, `habitaciones.html`, `turnos-tarifas`) y hace scraping ahí.
   - **Extrae directo del HTML**: como último recurso, el LLM lee el HTML completo y devuelve los datos estructurados.
5. **Filtra automáticamente** imágenes genéricas (logos, íconos, flechas, redes sociales) para mostrar solo fotos de habitaciones.
6. **Filtra precios inválidos**: descarta números de calle, teléfonos y códigos postales.
7. **Asocia imágenes a su habitación**: cada foto se vincula al bloque HTML de la room específica, no se distribuyen globalmente.
8. **Descarga imágenes** a tu disco local de forma asíncrona y paralela.
9. **Exporta** los resultados a `data.json`, `rooms.csv` y `prices.csv` en una carpeta con timestamp.
10. **Muestra los resultados** en una interfaz web con cards detalladas: rango de precios, fotos, capacidad, amenities, check-in/out.
11. **Chat con IA**: el asistente tiene contexto de **todos los hoteles** scraped en la sesión. Podés comparar propiedades, hacer preguntas y disparar re-extracciones desde el chat.

---

## 🛠️ Tecnologías

| Categoría | Tecnología | Para qué se usa |
|-----------|-----------|----------------|
| **Orquestación** | [LangGraph](https://github.com/langchain-ai/langgraph) | Pipeline de scraping como grafo de estados con bordes condicionales |
| **IA / LLM** | [Google Gemini 2.5 Flash](https://ai.google.dev/) | Descubrimiento de selectores, navegación autónoma, extracción fallback y chat |
| **Web Framework** | [Flask](https://flask.palletsprojects.com/) | Servidor web + API REST |
| **Frontend** | HTML + CSS + JS vanilla | Interfaz de usuario (dark mode, glassmorphism) |
| **Scraping estático** | [Requests](https://requests.readthedocs.io/) + [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) | Fetch y parseo de HTML |
| **Scraping dinámico** | [Playwright](https://playwright.dev/python/) | Sitios que requieren JavaScript (React, Vue, etc.) |
| **Modelos de datos** | [Pydantic](https://docs.pydantic.dev/) | Validación y serialización de Hotel, Room, Price, etc. |
| **Descarga de imágenes** | [aiohttp](https://docs.aiohttp.org/) | Descarga asíncrona paralela de imágenes |
| **Exportación** | [Pandas](https://pandas.pydata.org/) | Generación de archivos CSV |
| **Logging** | [Loguru](https://github.com/Delgan/loguru) | Logs con colores y niveles |
| **Configuración** | [python-dotenv](https://github.com/theskumar/python-dotenv) | Carga de variables de entorno desde `.env` |

---

## 🏗️ Arquitectura del proyecto

```
hotel_scraper/
│
├── graph/                      # Orquestación con LangGraph
│   ├── state.py                # ScraperState: el estado compartido entre nodos
│   ├── nodes.py                # Un nodo Python por cada step del pipeline
│   └── graph.py                # Construcción del grafo con bordes condicionales
│
├── scraper/                    # Capa de fetching
│   ├── detector.py             # Detecta si el sitio es estático o dinámico
│   ├── static_fetcher.py       # Descarga HTML con requests
│   └── dynamic_fetcher.py      # Descarga HTML con Playwright (JS rendering)
│
├── parser/                     # Capa de extracción
│   ├── html_parser.py          # Inicializa BeautifulSoup
│   ├── room_extractor.py       # 25+ selectores CSS + extracción de imágenes por bloque
│   ├── price_extractor.py      # Extrae precios con regex y selectores
│   ├── shift_extractor.py      # Extrae check-in / check-out
│   └── image_extractor.py      # Extrae URLs de imágenes (filtra logos e íconos)
│
├── llm/                        # Capa de IA
│   ├── llm_client.py           # Cliente de Gemini (google-genai SDK)
│   └── prompts.py              # Templates de prompts para extracción, navegación y descubrimiento
│
├── downloader/
│   └── image_downloader.py     # Descarga asíncrona de imágenes con aiohttp
│
├── exporter/
│   ├── json_exporter.py        # Serializa Hotel a data.json
│   └── csv_exporter.py         # Exporta rooms.csv y prices.csv
│
├── models/
│   └── hotel_data.py           # Modelos Pydantic: Hotel, Room, Price, Shift, RoomImage
│
├── web/                        # Flask App
│   ├── app.py                  # create_app() factory
│   ├── routes.py               # GET /, POST /api/scrape, GET /api/status, POST /api/chat
│   ├── job_store.py            # Estado en memoria de los jobs en curso
│   ├── templates/index.html    # Frontend HTML
│   └── static/
│       ├── css/style.css       # Estilos dark mode con glassmorphism
│       └── js/app.js           # Lógica frontend: polling, render de cards, chat
│
├── orchestrator.py             # Punto de entrada del pipeline (delega a LangGraph)
├── main.py                     # CLI entry point
├── run.py                      # Entry point del servidor Flask
├── config.py                   # Configuración global desde .env
├── requirements.txt
└── .env                        # Variables de entorno (no subir a Git)
```

---

## 🔄 Flujo de la aplicación

### Grafo LangGraph — pipeline completo

```
[1. Detectar tipo de sitio] → static / dynamic
          ↓
[2. Fetch HTML]
          ↓
[3. Extraer con 25+ selectores CSS]
          ↓
    ¿Habitaciones válidas?
    /                      \
  SÍ                        NO + use_llm=True
  |                              |
  |                   [3b. LLM descubre selector CSS
  |                        específico para este sitio]
  |                              |
  |                    ¿Selector descubierto?
  |                    /                   \
  |                  SÍ                    NO
  |                   |                    |
  |               Re-extrae          [4a. LLM navega:
  |               con nuevo               elige la mejor
  |               selector               sub-URL del sitio]
  |                   |                    |
  |                   |           ¿Habitaciones ahora?
  |                   |           /                  \
  |                   |         SÍ                   NO
  |                   |          |                    |
  |                   |          |         [4b. LLM extrae
  |                   |          |              directo del HTML]
  |                   |          |                    |
  └───────────────────┴──────────┴────────────────────┘
                               ↓
              [5. Ensamblar objetos Room con
                 imágenes y precios por habitación]
                               ↓
              [6. Descargar imágenes (async)]
                               ↓
              [7. Exportar JSON + CSV → disco local]
```

### Sistema de detección de falsos positivos
Si el extractor CSS encuentra exactamente **1 room** pero:
- Su nombre contiene `/` (típico de ítems de menú como "TURNOS / TARIFAS")
- Su nombre está en la lista de palabras de navegación (FAQ, CONTACTO, UBICACIÓN, etc.)
- No tiene imágenes propias y su descripción es muy corta

→ La descarta y activa el modo LLM.

### Flujo del frontend

```
Usuario ingresa URLs → POST /api/scrape → Job ID
         ↓
Polling cada 1.2s → GET /api/status/<job_id>
         ↓
Cards se renderizan en tiempo real por hotel
         ↓
Chat siempre visible → POST /api/chat
         ↓
Gemini recibe contexto de TODOS los hoteles scraped + mensaje
         ↓
Respuesta + botón de re-scraping si el LLM lo sugiere
```

---

## 🧠 Sistema de extracción inteligente

### Los 25+ selectores CSS (Capa 1)

El extractor prueba selectores en orden de especificidad. El primero que devuelve habitaciones válidas gana.

**Español:**
`habitacion`, `habitaci` (variantes de encoding), `cuarto`, `suite`, `departamento`, `depto`, `cabana`, `caba` (cabaña/cabañas), `alojamiento`, `hospedaje`, `apto`, `apartamento`

**Inglés:**
`room`, `cabin`, `bungalow`, `accommodation`, `lodge`, `cottage`, `villa`

**Patrones genéricos de CMS hoteleros:**
`unit`, `tipo`, `category`, `categoria`, `tarifa`, `plan`

**Fallbacks estructurales:**
`article`, `.card`

### Descubrimiento de selectores con LLM (Capa 2)

Si los 25 selectores devuelven 0 resultados, Gemini analiza los primeros 8.000 caracteres del HTML e identifica el selector CSS específico que usa ese sitio (por ejemplo `.accommodation-item`, `.product-box`, `.tipo-habitacion`). Si la confianza es ≥ 40%, se aplica ese selector y se re-extrae.

### Navegación autónoma (Capa 3a)

El LLM analiza **todos los links** del menú de navegación y elige la subpágina más relevante, reconociendo términos en español e inglés:

| Español | Inglés |
|---|---|
| Habitaciones, Cuartos, Suites, Cabañas, Departamentos, Alojamiento, Hospedaje, Tarifas, Turnos, Tipos de alojamiento | Rooms, Suites, Cabins, Accommodation, Lodging, Rates, Tariffs, Our Rooms, Stay |

### Extracción directa por LLM (Capa 3b)

Como último recurso, Gemini lee el HTML completo (hasta 18.000 caracteres) y devuelve directamente la lista de habitaciones con nombre, descripción, capacidad, amenities, precios e imágenes.

---

## ✅ Requisitos previos

Antes de instalar, asegurate de tener:

- **Python 3.11 o superior** ([descargar](https://www.python.org/downloads/))
- **pip** actualizado
- Una **API Key de Google Gemini** (gratis en [aistudio.google.com](https://aistudio.google.com/))

---

## 🚀 Instalación paso a paso

### 1. Clonar o abrir el proyecto

Si lo descargaste, navegá hasta la carpeta `hotel_scraper/`:
```bash
cd ruta/a/tu/proyecto/hotel_scrapper/hotel_scraper
```

### 2. Crear y activar un entorno virtual

**Windows (PowerShell):**
```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv env
source env/bin/activate
```

> 💡 Sabrás que el entorno está activo cuando veas `(env)` al inicio de tu terminal.

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Instalar Playwright (para sitios dinámicos)

```bash
playwright install chromium
```

> Solo necesitás hacerlo una vez. Instala el navegador headless para sitios con React, Vue, etc.

---

## ⚙️ Configuración del .env

Abrí el archivo `.env` y completá tu API Key de Gemini:

```env
GEMINI_API_KEY=TU_API_KEY_AQUÍ

# Opcionales (tienen valores por defecto):
SCRAPER_DELAY_MIN=1.5
SCRAPER_DELAY_MAX=4.0
MAX_CONCURRENT_IMAGES=5
SCRAPER_TIMEOUT=30
SCRAPER_MAX_RETRIES=3
```

> 🔑 **¿Cómo conseguir la API Key de Gemini?**
> 1. Entrá a [aistudio.google.com](https://aistudio.google.com/)
> 2. Iniciá sesión con tu cuenta de Google
> 3. Click en "Get API Key" → "Create API Key"
> 4. Copiá la key y pegala en el `.env`

---

## 🌐 Cómo usar la app web

### 1. Levantar el servidor

Desde la carpeta `hotel_scraper/`:

```bash
python run.py
```

Deberías ver:
```
Hotel Scraper Web App running at http://localhost:5000
 * Running on http://127.0.0.1:5000
```

### 2. Abrir el navegador

Entrá a [http://localhost:5000](http://localhost:5000)

### 3. Hacer un scraping

1. **Ingresá las URLs** en el textarea (una por línea):
   ```
   https://hotelhaedo.com/
   https://www.jondehotel.com.ar/
   https://hotelthepalms.com.ar/
   ```

2. **Activá el Modo IA** (toggle — recomendado): activa las 3 capas de inteligencia.

3. **(Opcional)** Cambiá la carpeta de salida si querés guardar los archivos en otro lugar.

4. **Click en "Iniciar Extracción"**: la barra de progreso y los logs aparecen en tiempo real.

5. **Los resultados se muestran** como cards por hotel con:
   - Badge de fuente: `⚡ Selectores CSS` / `🤖 LLM navegó + extrajo` / `🌐 Playwright (JS)`
   - Rango de precios y total de fotos en el encabezado
   - Cards por habitación con tarifas, amenities, capacidad, check-in/out y galería de fotos

### 4. Usar el chat

El panel de chat está **siempre visible** a la izquierda y tiene contexto de **todos los hoteles scraped** en la sesión. Podés preguntar sobre uno o varios hoteles:

- *"¿Cuántas habitaciones tiene Hotel Haedo?"*
- *"¿Cuál es el precio más alto encontrado en todos los hoteles?"*
- *"Compará los dos hoteles"*
- *"¿Qué amenities tiene la suite Jonde Gold?"*
- *"Revisá mejor las imágenes de Jonde Hotel"* → el LLM propone un re-scraping con botón

> 💡 Si el LLM sugiere una re-extracción, aparece un botón `🔄 Re-extraer` en la respuesta. Al hacerle click se dispara automáticamente.

---

## 💻 Cómo usar la CLI

La interfaz de línea de comandos funciona independientemente de la web.

### Uso básico (sin IA)
```bash
python main.py --url "https://hotelhaedo.com/habitaciones.html" --output "./output"
```

### Uso con IA activada (recomendado)
```bash
python main.py --url "https://hotelhaedo.com/" --output "./output" --llm
```

### Con jondehotel (demuestra la navegación autónoma)
```bash
python main.py --url "https://www.jondehotel.com.ar/" --output "./output" --llm
```
> El LLM detectará que la home no tiene habitaciones válidas, navegará a `turnos-tarifas` y extraerá las 6 suites con sus precios.

### Opciones disponibles

| Flag | Descripción | Default |
|------|-------------|---------|
| `--url` | URL del hotel a scrapear | *requerido* |
| `--output` | Carpeta donde guardar los resultados | `./output` |
| `--llm` | Activa las 3 capas de IA | desactivado |
| `--log-level` | Nivel de logs: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

---

## 📁 Estructura de los archivos de salida

Cada scraping genera una carpeta con timestamp:

```
output/
└── hotelhaedo_com_20260430_220417/
    ├── data.json          # Todos los datos del hotel en formato JSON
    ├── rooms.csv          # Una fila por habitación con sus precios
    ├── prices.csv         # Todos los precios encontrados, con contexto
    └── images/
        ├── img_001.jpg
        ├── img_002.jpg
        └── ...
```

### Ejemplo de `data.json`

```json
{
  "name": "hotelhaedo.com",
  "url": "https://hotelhaedo.com/",
  "scraped_at": "2026-04-30T22:04:22",
  "source_type": "llm_assisted",
  "rooms": [
    {
      "name": "HABITACIÓN SINGLE / DOBLE",
      "description": "Ideal para una o dos personas...",
      "capacity": 2,
      "amenities": ["Wi-Fi", "Aire acondicionado", "TV LED 32'"],
      "prices": [
        { "amount": 32000.0, "currency": "ARS", "period": null }
      ],
      "shifts": [
        { "check_in": null, "check_out": "17:00" }
      ],
      "images": [
        { "url": "https://...", "filename": "img_001.jpg", "downloaded": true }
      ]
    }
  ]
}
```

---

## 🔧 Para desarrolladores

### Agregar más sinónimos de habitación (selectores CSS)

Editá `parser/room_extractor.py`, en la lista `ROOM_SELECTORS`. Cada selector se prueba en orden; el primero que retorne rooms válidas gana.

### Agregar más términos de navegación al LLM

Editá `llm/prompts.py`, en `LINK_NAVIGATION_PROMPT`. Agregá los términos en la sección correspondiente al idioma.

### Agregar un nuevo nodo al grafo LangGraph

1. Definí tu función en `graph/nodes.py` con firma `(state: ScraperState) -> dict`.
2. Registralo en `graph/graph.py` con `g.add_node("mi_nodo", mi_funcion)`.
3. Conectalo con `g.add_edge(...)` o `g.add_conditional_edges(...)`.

### Cambiar el modelo de Gemini

En `llm/llm_client.py`, cambiá el valor de `self._model_name`:
```python
self._model_name = "gemini-2.0-flash"
```

### Ajustar el umbral de confianza del selector discovery

En `graph/nodes.py`, función `_llm_discover_selector`, cambiá el valor de `confidence >= 40` según qué tan agresivo querés que sea el descubrimiento automático.

---

## ❓ Preguntas frecuentes

**¿Necesito la API Key de Groq?**
No. La app usa únicamente Gemini. La variable `GROQ_API_KEY` está en el `.env` por compatibilidad futura.

**¿El scraper funciona sin activar el Modo IA?**
Sí, pero solo usará los 25 selectores CSS. Si el sitio tiene una estructura HTML no estándar o usa JavaScript para cargar las habitaciones, probablemente devuelva 0 resultados. Con `--llm` activado, el sistema tiene 3 capas de fallback.

**¿Los datos se guardan aunque cierre el navegador?**
Sí. Los archivos JSON, CSV e imágenes se guardan en disco en el momento que termina el scraping. El servidor Flask solo mantiene en memoria el estado de los jobs activos mientras esté corriendo.

**¿Por qué el hotel X devuelve 0 habitaciones?**
Las posibles causas son:
1. Las habitaciones se cargan con JavaScript → usá `--llm` y el sistema intentará con Playwright.
2. El sitio tiene protección anti-bot → el scraper puede ser bloqueado.
3. La información está en una subpágina que el LLM no identificó correctamente → probá pasando directamente la URL de la sección de habitaciones.

**¿Qué pasa si el sitio usa React/Vue/Angular?**
El detector automático identifica señales de frameworks JS. Si las detecta, usa Playwright para renderizar la página completa antes de parsearla.

**¿Puedo correr varios hoteles al mismo tiempo?**
Desde la web, sí: ingresá múltiples URLs (una por línea). Se procesan secuencialmente dentro del mismo job y los resultados aparecen a medida que se completan. Desde la CLI, corrés `main.py` una vez por URL.

---

## 📦 Dependencias principales

```
google-genai       # SDK de Gemini (nuevo, reemplaza al deprecado google-generativeai)
langgraph          # Orquestación como grafo de estados con bordes condicionales
flask              # Servidor web
flask-cors         # CORS para la API REST
beautifulsoup4     # Parseo de HTML
playwright         # Scraping de sitios dinámicos (JS)
pydantic           # Validación de modelos de datos
aiohttp            # Descarga asíncrona de imágenes
pandas             # Exportación a CSV
loguru             # Logging elegante
python-dotenv      # Variables de entorno
```
