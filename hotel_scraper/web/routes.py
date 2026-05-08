"""Flask routes for the hotel scraper web app."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

# Add parent dir to sys.path so hotel_scraper modules are importable
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from web.job_store import (
    all_jobs_results,
    append_log,
    append_result,
    create_job,
    get_job,
    set_status,
)

bp = Blueprint("main", __name__)


# Module-level LLMClient singleton — reuses the shared router/cache.
_llm_singleton = None


def _get_llm_client():
    """Lazy-init a single LLMClient for chat/observability."""
    global _llm_singleton
    if _llm_singleton is None:
        from llm.llm_client import LLMClient
        _llm_singleton = LLMClient()
    return _llm_singleton


# ---------------------------------------------------------------------------
# Helper: run a single URL scrape in background
# ---------------------------------------------------------------------------

def _run_scrape_job(job_id: str, urls: list[str], use_llm: bool, output_dir: str) -> None:
    from orchestrator import scrape

    set_status(job_id, "running")
    append_log(job_id, f"Starting job with {len(urls)} URL(s)...")

    for url in urls:
        try:
            append_log(job_id, f"Scraping: {url}")
            hotel = scrape(url=url, output_dir=output_dir, use_llm=use_llm)
            hotel_dict = hotel.model_dump()
            append_result(job_id, hotel_dict)

            n = len(hotel.rooms)
            if n == 0:
                append_log(
                    job_id,
                    f"⚠️ {hotel.name}: se completó pero no se encontraron habitaciones. "
                    "Probá activar el Modo IA o pasá directamente la URL de la sección de habitaciones."
                )
            else:
                append_log(job_id, f"✅ {hotel.name} — {n} habitación{'es' if n != 1 else ''} encontrada{'s' if n != 1 else ''}")
        except Exception as e:
            err = str(e)
            if "503" in err or "UNAVAILABLE" in err or "unavailable" in err.lower():
                append_log(
                    job_id,
                    f"⚠️ La IA de Gemini está saturada en este momento para {url}. "
                    "Esperá unos segundos y volvé a intentarlo."
                )
            elif "429" in err or "RATE_LIMIT" in err:
                append_log(job_id, f"⚠️ Límite de cuota de Gemini alcanzado para {url}. Esperá 1 minuto.")
            else:
                append_log(job_id, f"ERROR scraping {url}: {e}")

    set_status(job_id, "done")
    append_log(job_id, "All URLs processed.")



# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.route("/")
def index():
    return render_template("index.html")


@bp.route("/api/scrape", methods=["POST"])
def api_scrape():
    """Start a scraping job.

    Body JSON:
        urls (list[str]): URLs to scrape.
        use_llm (bool): Whether to use LLM fallback.
        output_dir (str, optional): Base output directory.
    """
    data = request.get_json(force=True)
    urls = [u.strip() for u in data.get("urls", []) if u.strip()]
    use_llm = bool(data.get("use_llm", True))
    output_dir = data.get("output_dir", "./output")

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    job_id = create_job()
    thread = threading.Thread(
        target=_run_scrape_job,
        args=(job_id, urls, use_llm, output_dir),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@bp.route("/api/status/<job_id>")
def api_status(job_id: str):
    """Poll job status and partial results."""
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@bp.route("/api/chat", methods=["POST"])
def api_chat():
    """Chat endpoint. Sends user message + all scraped hotel context to Gemini.

    Body JSON:
        message (str): User message.
        history (list[{role, content}]): Previous chat turns.
    """
    data = request.get_json(force=True)
    message = data.get("message", "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"error": "Empty message"}), 400

    # Build context from all scraped hotels in this session
    all_hotels = all_jobs_results()

    if all_hotels:
        # Compact JSON with only the most relevant fields
        compact = []
        for h in all_hotels:
            compact.append({
                "hotel": h.get("name"),
                "url": h.get("url"),
                "source_type": h.get("source_type"),
                "rooms_count": len(h.get("rooms", [])),
                "rooms": [
                    {
                        "name": r["name"],
                        "description": (r.get("description") or "")[:200],
                        "capacity": r.get("capacity"),
                        "amenities": r.get("amenities", []),
                        "prices": [
                            {"amount": p["amount"], "currency": p["currency"], "period": p.get("period")}
                            for p in r.get("prices", [])[:5]
                        ],
                        "images_count": len(r.get("images", [])),
                    }
                    for r in h.get("rooms", [])
                ],
            })
        context_str = json.dumps(compact, ensure_ascii=False, indent=2)
    else:
        context_str = "No hay datos scraped todavía en esta sesión."

    system_prompt = f"""Eres un asistente inteligente de análisis hotelero. Tienes acceso a los datos extraídos de sitios web de hoteles por el sistema de scraping.

Datos disponibles de esta sesión:
{context_str}

Instrucciones:
- Responde preguntas sobre los hoteles, habitaciones, precios y amenities.
- Si el usuario pide re-scrapear o revisar un hotel, responde con un JSON especial al final:
  [ACTION: {{"action": "rescrape", "url": "<url>", "use_llm": true}}]
- Sé conciso pero completo. Responde en el mismo idioma que el usuario.
- Si no hay datos suficientes, dilo claramente."""

    # Build conversation for the LLM
    turns = []
    for turn in history[-6:]:  # last 6 turns max
        turns.append(f"{turn['role'].upper()}: {turn['content']}")
    turns.append(f"USER: {message}")
    full_prompt = system_prompt + "\n\n" + "\n".join(turns) + "\nASSISTANT:"

    try:
        client = _get_llm_client()
        reply = client.generate_text(full_prompt)

        # Detect if there's an embedded ACTION
        action = None
        if "[ACTION:" in reply:
            try:
                action_part = reply.split("[ACTION:")[1].split("]")[0].strip()
                action = json.loads(action_part)
                reply = reply.split("[ACTION:")[0].strip()
            except Exception:
                pass

        return jsonify({"reply": reply, "action": action})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

