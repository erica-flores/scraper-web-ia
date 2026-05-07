/* ===================================================
   Hotel Scraper AI — Frontend Logic
   =================================================== */

// ---- State ----
let currentJobId = null;
let pollInterval = null;
let chatHistory = [];
let allHotels = [];    // accumulated across all jobs in session

// ---- LLM Toggle UI ----
document.getElementById('useLlm').addEventListener('change', function () {
  document.getElementById('llmHint').textContent = this.checked
    ? 'Activado — Gemini navega y extrae'
    : 'Desactivado — solo selectores CSS';
});

// ---- Scrape ----
async function startScrape() {
  const rawUrls = document.getElementById('urlsInput').value.trim();
  const urls = rawUrls.split('\n').map(u => u.trim()).filter(Boolean);
  if (!urls.length) { alert('Ingresá al menos una URL.'); return; }

  const useLlm = document.getElementById('useLlm').checked;
  const outputDir = document.getElementById('outputDir').value.trim() || './output';

  // UI state
  document.getElementById('scrapeBtn').disabled = true;
  const progressWrap = document.getElementById('progressWrap');
  progressWrap.style.display = 'block';
  document.getElementById('progressLog').innerHTML = '';
  setProgress(5);

  try {
    const res = await fetch('/api/scrape', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ urls, use_llm: useLlm, output_dir: outputDir }),
    });
    const data = await res.json();
    if (data.error) { showError(data.error); return; }

    currentJobId = data.job_id;
    startPolling(urls.length);
  } catch (e) {
    showError(e.message);
  }
}

function startPolling(totalUrls) {
  let seenLogs = 0;
  let resultsRendered = new Set();

  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/status/${currentJobId}`);
      const job = await res.json();

      // Update progress log
      const logEl = document.getElementById('progressLog');
      const newLogs = job.progress.slice(seenLogs);
      newLogs.forEach(msg => {
        seenLogs++;
        const line = document.createElement('div');
        line.className = 'progress-log-line' +
          (msg.startsWith('Done') || msg.startsWith('All') ? ' success' : '') +
          (msg.startsWith('ERROR') ? ' error' : '');
        line.textContent = '› ' + msg;
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;
      });

      // Update progress bar
      const pct = job.status === 'done' ? 100 :
        Math.min(10 + Math.round((seenLogs / Math.max(totalUrls * 8, 1)) * 80), 90);
      setProgress(pct);

      // Render new results as they arrive
      job.results.forEach(hotel => {
        if (!resultsRendered.has(hotel.url)) {
          resultsRendered.add(hotel.url);
          addHotelToSession(hotel);
          renderHotelCard(hotel);
        }
      });

      if (job.status === 'done') {
        clearInterval(pollInterval);
        setProgress(100);
        document.getElementById('scrapeBtn').disabled = false;
        document.getElementById('resultsSection').style.display = 'block';
        updateHeaderStats();
      }
    } catch (e) {
      console.error('Poll error:', e);
    }
  }, 1200);
}

function setProgress(pct) {
  document.getElementById('progressFill').style.width = pct + '%';
}

function showError(msg) {
  document.getElementById('scrapeBtn').disabled = false;
  const logEl = document.getElementById('progressLog');
  const line = document.createElement('div');
  line.className = 'progress-log-line error';
  line.textContent = '✗ Error: ' + msg;
  logEl.appendChild(line);
}

// ---- Hotel rendering ----
function addHotelToSession(hotel) {
  // Replace if same URL was scraped before (re-scrape)
  const idx = allHotels.findIndex(h => h.url === hotel.url);
  if (idx >= 0) allHotels[idx] = hotel;
  else allHotels.push(hotel);
}

function renderHotelCard(hotel) {
  document.getElementById('resultsSection').style.display = 'block';
  const grid = document.getElementById('resultsGrid');

  const existing = document.getElementById('hotel-' + btoa(hotel.url).replace(/[^a-z0-9]/gi, ''));
  if (existing) existing.remove();

  const card = document.createElement('div');
  card.className = 'hotel-card';
  card.id = 'hotel-' + btoa(hotel.url).replace(/[^a-z0-9]/gi, '');

  const src = hotel.source_type || 'static';
  const srcLabel = src === 'llm_assisted' ? '🤖 LLM navegó + extrajo'
    : src === 'static' ? '⚡ Selectores CSS'
    : src === 'dynamic' ? '🌐 Playwright (JS)'
    : src;
  const srcClass = src.includes('llm') ? 'badge-llm' : 'badge-static';

  // Summary stats
  const allPrices = hotel.rooms.flatMap(r => r.prices || []).map(p => p.amount).filter(a => a > 0);
  const minP = allPrices.length ? Math.min(...allPrices) : null;
  const maxP = allPrices.length ? Math.max(...allPrices) : null;
  const currency = hotel.rooms.flatMap(r => r.prices || [])[0]?.currency || 'ARS';
  const priceRange = (minP !== null)
    ? (minP === maxP ? `${currency} ${fmtNum(minP)}` : `${currency} ${fmtNum(minP)} – ${fmtNum(maxP)}`)
    : 'Sin precios';
  const totalImgs = hotel.rooms.reduce((a, r) => a + (r.images || []).length, 0);

  card.innerHTML = `
    <div class="hotel-card-header">
      <div class="hotel-card-title">
        <span class="hotel-emoji">🏨</span>
        <div>
          <div class="hotel-name">${escHtml(hotel.name)}</div>
          <a class="hotel-url" href="${escHtml(hotel.url)}" target="_blank">${escHtml(hotel.url)}</a>
        </div>
      </div>
      <div class="hotel-meta">
        <span class="badge ${srcClass}">${srcLabel}</span>
        <span class="badge badge-count">${hotel.rooms.length} habitación${hotel.rooms.length !== 1 ? 'es' : ''}</span>
        <span class="badge badge-count">💰 ${priceRange}</span>
        <span class="badge badge-count">🖼️ ${totalImgs} fotos</span>
        <span class="badge badge-count" style="font-size:10px;color:var(--text-muted)">${fmtDate(hotel.scraped_at)}</span>
      </div>
    </div>
    <div class="hotel-card-body">
      <div class="rooms-grid">
        ${hotel.rooms.length
          ? hotel.rooms.map(r => renderRoomCard(r)).join('')
          : '<p style="color:var(--text-muted);font-size:13px;">No se encontraron habitaciones. Intentá con --llm activado.</p>'
        }
      </div>
    </div>`;

  grid.prepend(card);
}

function renderRoomCard(room) {
  // Prices — filter out implausible values (< 100 for ARS are likely numbers, not prices)
  const validPrices = (room.prices || []).filter(p => {
    const a = parseFloat(p.amount);
    return !isNaN(a) && a > 99;
  }).slice(0, 4);

  const pricesHtml = validPrices.length
    ? validPrices.map(p => {
        const label = p.period ? ` / ${p.period}` : '';
        return `<span class="price-chip">💲 ${p.currency} ${fmtNum(p.amount)}${label}</span>`;
      }).join('')
    : '';

  // Amenities
  const amenitiesHtml = (room.amenities || []).slice(0, 8).map(a =>
    `<span class="amenity-chip">✓ ${escHtml(a)}</span>`
  ).join('');

  // Capacity
  const capacityHtml = room.capacity
    ? `<span class="room-meta-chip">👥 ${room.capacity} personas</span>`
    : '';

  // Check-in / Check-out from shifts
  const shift = (room.shifts || [])[0];
  const shiftHtml = shift && (shift.check_in || shift.check_out)
    ? `<span class="room-meta-chip">🕐 Entrada ${shift.check_in || '?'} · Salida ${shift.check_out || '?'}</span>`
    : '';

  // Images — only show those with valid URLs
  const images = (room.images || []).filter(img => img.url && !img.url.includes('placeholder'));
  const thumbsHtml = images.slice(0, 8).map(img =>
    `<img class="room-thumb" src="${escHtml(img.url)}" alt="${escHtml(room.name)}" loading="lazy"
      onclick="openModal('${escHtml(img.url)}','${escHtml(room.name)}')" />`
  ).join('');

  const metaRow = [capacityHtml, shiftHtml].filter(Boolean).join('');

  return `
    <div class="room-card">
      <div class="room-header">
        <div class="room-name">${escHtml(room.name)}</div>
        ${metaRow ? `<div class="room-meta-row">${metaRow}</div>` : ''}
        ${room.description ? `<div class="room-desc">${escHtml(room.description)}</div>` : ''}
      </div>
      <div class="room-body">
        ${pricesHtml ? `<div><div class="prices-title">Tarifas</div><div class="prices-list">${pricesHtml}</div></div>` : '<div class="prices-empty">Sin tarifas disponibles</div>'}
        ${amenitiesHtml ? `<div><div class="prices-title">Amenities</div><div class="amenities-list">${amenitiesHtml}</div></div>` : ''}
      </div>
      ${thumbsHtml
        ? `<div class="room-images">${thumbsHtml}<span class="img-count">${images.length} foto${images.length !== 1 ? 's' : ''}</span></div>`
        : '<p class="room-no-images">Sin imágenes disponibles</p>'
      }
    </div>`;
}

function clearResults() {
  document.getElementById('resultsGrid').innerHTML = '';
  document.getElementById('resultsSection').style.display = 'none';
  allHotels = [];
  updateHeaderStats();
}

function updateHeaderStats() {
  const statEl = document.getElementById('headerStats');
  const hotelsEl = document.getElementById('statHotels');
  const roomsEl = document.getElementById('statRooms');
  const total = allHotels.reduce((acc, h) => acc + (h.rooms || []).length, 0);
  hotelsEl.textContent = allHotels.length + ' hotel' + (allHotels.length !== 1 ? 'es' : '');
  roomsEl.textContent = total + ' habitación' + (total !== 1 ? 'es' : '');
  statEl.style.display = allHotels.length ? 'flex' : 'none';
}

// ---- Image Modal ----
function openModal(url, caption) {
  document.getElementById('modalImg').src = url;
  document.getElementById('modalCaption').textContent = caption;
  document.getElementById('imageModal').style.display = 'flex';
}

function closeModal() {
  document.getElementById('imageModal').style.display = 'none';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ---- Chat ----
document.getElementById('chatForm').addEventListener('submit', async function (e) {
  e.preventDefault();
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  addChatBubble('user', msg);
  const loadingId = addChatBubble('assistant', '...', true);

  document.getElementById('chatSend').disabled = true;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: chatHistory }),
    });
    const data = await res.json();
    removeBubble(loadingId);

    if (data.error) {
      addChatBubble('assistant', 'Error: ' + data.error);
    } else {
      const bubbleId = addChatBubble('assistant', data.reply);

      // If the LLM suggests a re-scrape action, show a button
      if (data.action && data.action.action === 'rescrape') {
        const btn = document.createElement('button');
        btn.className = 'bubble-action';
        btn.textContent = '🔄 Re-extraer: ' + data.action.url;
        btn.onclick = () => triggerRescrape(data.action.url, data.action.use_llm !== false);
        document.getElementById(bubbleId).querySelector('.bubble-content').appendChild(btn);
      }

      chatHistory.push({ role: 'user', content: msg });
      chatHistory.push({ role: 'assistant', content: data.reply });
      if (chatHistory.length > 20) chatHistory = chatHistory.slice(-20);
    }
  } catch (err) {
    removeBubble(loadingId);
    addChatBubble('assistant', 'Error de conexión: ' + err.message);
  }

  document.getElementById('chatSend').disabled = false;
});

function addChatBubble(role, text, loading = false) {
  const id = 'bubble-' + Date.now() + Math.random().toString(36).slice(2);
  const container = document.getElementById('chatMessages');

  const div = document.createElement('div');
  div.id = id;
  div.className = 'chat-bubble ' + role + (loading ? ' loading' : '');

  const avatar = role === 'user' ? '👤' : '🤖';

  div.innerHTML = `
    <div class="bubble-avatar">${avatar}</div>
    <div class="bubble-content">${formatChatText(text)}</div>`;

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return id;
}

function removeBubble(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function formatChatText(text) {
  return escHtml(text)
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code style="background:#ffffff12;padding:1px 5px;border-radius:3px">$1</code>');
}

async function triggerRescrape(url, useLlm) {
  document.getElementById('urlsInput').value = url;
  document.getElementById('useLlm').checked = useLlm;
  addChatBubble('assistant', `Iniciando re-extracción de: ${url}`);
  await startScrape();
}

// ---- Utilities ----
function escHtml(str) {
  if (typeof str !== 'string') return str ?? '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function fmtDate(iso) {
  try {
    return new Date(iso).toLocaleString('es-AR', { dateStyle: 'short', timeStyle: 'short' });
  } catch { return iso || ''; }
}

function fmtNum(n) {
  try {
    return Number(n).toLocaleString('es-AR');
  } catch { return n; }
}
