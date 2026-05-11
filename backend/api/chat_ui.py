CHAT_UI_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MITAOE Assistant</title>
  <style>
    :root { color-scheme: light; --bg:#f7f7f4; --card:#ffffff; --accent:#1f3a5f; --muted:#5c5c55; --good:#16a085; --bad:#c0392b; --warn:#f39c12; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: #1d1d1b; min-height: 100vh; display: flex; flex-direction: column; }
    header { padding: 14px 22px; background: var(--accent); color: white; display: flex; align-items: center; justify-content: space-between; }
    header h1 { margin: 0; font-size: 16px; font-weight: 600; }
    header .badge { font-size: 12px; opacity: 0.9; }
    main { flex: 1; max-width: 880px; width: 100%; margin: 0 auto; padding: 18px; display: flex; flex-direction: column; }
    #messages { flex: 1; display: flex; flex-direction: column; gap: 10px; min-height: 50vh; padding-bottom: 10px; }
    .msg { background: var(--card); border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }
    .msg.user { background: #e8eff7; align-self: flex-end; max-width: 80%; }
    .msg.assistant { border-left: 3px solid var(--good); max-width: 90%; }
    .msg.abstain { border-left: 3px solid var(--bad); background: #fff5f3; max-width: 90%; }
    .msg .body { white-space: pre-wrap; line-height: 1.5; font-size: 14px; }
    .msg .body a.cite { display: inline-block; vertical-align: text-top; padding: 0 4px; margin: 0 1px; background: var(--good); color: white; text-decoration: none; border-radius: 999px; font-size: 11px; font-weight: 600; line-height: 16px; }
    .msg .meta { font-size: 11px; color: var(--muted); margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .pill { background: #eef1f4; border-radius: 999px; padding: 2px 8px; font-size: 11px; color: #1d1d1b; }
    .pill.conf { background: #2980b9; color: white; }
    .pill.warn { background: var(--warn); color: white; }
    .pill.bad { background: var(--bad); color: white; }
    .pill.rewrite { background: #8e44ad; color: white; }
    .citations { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
    .citations a { background: #eef7ff; border: 1px solid #3498db; color: #174b7a; padding: 4px 8px; border-radius: 6px; text-decoration: none; font-size: 12px; }
    .citations a:hover { background: #d6ebff; }
    .controls { background: var(--card); border-radius: 10px; padding: 12px; box-shadow: 0 -1px 4px rgba(0,0,0,0.05); display: flex; gap: 8px; align-items: flex-end; }
    .controls textarea { flex: 1; resize: none; border: 1px solid #d9d9d2; border-radius: 8px; padding: 10px 12px; font: inherit; min-height: 44px; max-height: 160px; }
    .controls button { background: var(--accent); color: white; border: none; border-radius: 8px; padding: 10px 18px; font: inherit; font-weight: 600; cursor: pointer; }
    .controls button:disabled { opacity: 0.6; cursor: not-allowed; }
    .controls .secondary { background: white; color: var(--accent); border: 1px solid var(--accent); padding: 10px 14px; }
    .toolbar { display: flex; gap: 12px; align-items: center; padding: 6px 0; font-size: 12px; color: var(--muted); }
    .toolbar label { cursor: pointer; }
    .empty { text-align: center; color: var(--muted); padding: 60px 20px; font-size: 14px; }
    .empty .examples { margin-top: 20px; display: flex; flex-direction: column; gap: 8px; max-width: 380px; margin-left: auto; margin-right: auto; }
    .empty .examples button { background: white; border: 1px solid #d9d9d2; color: #1d1d1b; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-size: 13px; text-align: left; }
    .empty .examples button:hover { background: #eef7ff; }
    .streaming-cursor { display: inline-block; width: 8px; height: 14px; background: var(--good); vertical-align: text-bottom; animation: blink 1s infinite; }
    @keyframes blink { 0%, 50% { opacity: 1; } 51%, 100% { opacity: 0; } }
    details { font-size: 12px; color: var(--muted); margin-top: 8px; }
    details summary { cursor: pointer; }
    details pre { background: #fafaf8; padding: 8px; border-radius: 6px; font-size: 11px; overflow-x: auto; }
  </style>
</head>
<body>
  <header>
    <h1>MITAOE Assistant</h1>
    <div class="badge" id="providerBadge">provider: loading…</div>
  </header>
  <main>
    <div class="toolbar">
      <label><input type="checkbox" id="streamToggle" checked /> stream tokens</label>
      <label title="Adds 1 extra Gemini call per non-streaming answer for hallucination detection. Off by default to save quota."><input type="checkbox" id="judgeToggle" /> run hallucination judge (extra call)</label>
      <span id="usageBadge" class="pill" title="Gemini calls/tokens consumed this browser session">calls 0 · tokens 0/0</span>
      <span style="flex:1"></span>
      <button class="pill" id="resetBtn" type="button">reset chat</button>
    </div>
    <div id="messages">
      <div class="empty" id="emptyState">
        <div>Ask anything about MITAOE.</div>
        <div class="examples" id="examples">
          <button data-q="What is MCA eligibility?">What is MCA eligibility?</button>
          <button data-q="What is the fee structure for BTech?">What is the fee structure for BTech?</button>
          <button data-q="What hostel facilities are available?">What hostel facilities are available?</button>
          <button data-q="What is the BTech curriculum for E&TC Engineering?">What is the BTech curriculum for E&TC Engineering?</button>
        </div>
      </div>
    </div>
    <div class="controls">
      <textarea id="input" placeholder="Ask a question… (Enter to send, Shift+Enter for newline)"></textarea>
      <button id="sendBtn" type="button">Send</button>
    </div>
  </main>
  <script>
    const messagesEl = document.getElementById('messages');
    const emptyState = document.getElementById('emptyState');
    const inputEl = document.getElementById('input');
    const sendBtn = document.getElementById('sendBtn');
    const resetBtn = document.getElementById('resetBtn');
    const streamToggle = document.getElementById('streamToggle');
    const judgeToggle = document.getElementById('judgeToggle');
    const providerBadge = document.getElementById('providerBadge');
    const usageBadge = document.getElementById('usageBadge');
    let sessionId = localStorage.getItem('chat_session_id') || null;
    let busy = false;
    let sessionCalls = 0;
    let sessionInTokens = 0;
    let sessionOutTokens = 0;

    function updateUsage(usage) {
      if (!usage) return;
      sessionCalls += usage.total_calls || 0;
      sessionInTokens += (usage.input_tokens || 0) + (usage.judge_input_tokens || 0);
      sessionOutTokens += (usage.output_tokens || 0) + (usage.judge_output_tokens || 0);
      usageBadge.textContent = `calls ${sessionCalls} · tokens ${sessionInTokens}/${sessionOutTokens}`;
    }

    fetch('/chat/provider').then(r => r.json()).then(info => {
      providerBadge.textContent = `provider: ${info.provider} (${info.default_model})`;
      if (info.provider === 'mock') {
        providerBadge.style.color = '#f39c12';
        providerBadge.title = 'No API key set. Export GOOGLE_API_KEY (or add it to .env) and restart to use Gemini.';
      }
    }).catch(() => { providerBadge.textContent = 'provider: unknown'; });

    document.querySelectorAll('#examples button').forEach(btn => {
      btn.addEventListener('click', () => { inputEl.value = btn.dataset.q; sendQuery(); });
    });

    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); }
    });
    sendBtn.addEventListener('click', sendQuery);
    resetBtn.addEventListener('click', resetChat);

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
    }

    function renderAnswerText(text, citations) {
      const indexToUrl = {};
      (citations || []).forEach(c => { indexToUrl[c.index] = c.source_url; });
      const safe = escapeHtml(text);
      return safe.replace(/\\[(\\d+)\\]/g, (_match, n) => {
        const url = indexToUrl[Number(n)];
        if (!url) return `[${n}]`;
        return `<a class="cite" href="${escapeHtml(url)}" target="_blank">${n}</a>`;
      });
    }

    function citationsBlock(citations) {
      if (!citations || !citations.length) return '';
      return `<div class="citations">${citations.map(c => `
        <a href="${escapeHtml(c.source_url)}" target="_blank" title="${escapeHtml((c.section_path || []).join(' › '))}">
          [${c.index}] ${escapeHtml((c.title || '').slice(0, 60))}
        </a>
      `).join('')}</div>`;
    }

    function appendUser(content) {
      if (emptyState) emptyState.remove();
      const div = document.createElement('div');
      div.className = 'msg user';
      div.innerHTML = `<div class="body">${escapeHtml(content)}</div>`;
      messagesEl.appendChild(div);
      div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    function appendAssistantPlaceholder() {
      const div = document.createElement('div');
      div.className = 'msg assistant';
      div.innerHTML = `<div class="body"><span class="streaming-cursor"></span></div><div class="meta"></div>`;
      messagesEl.appendChild(div);
      div.scrollIntoView({ behavior: 'smooth', block: 'end' });
      return div;
    }

    function renderAssistant(div, payload) {
      const a = payload.answer;
      const conf = a.confidence || {};
      div.className = 'msg ' + (a.abstained ? 'abstain' : 'assistant');
      const metaParts = [];
      metaParts.push(`<span class="pill conf">confidence ${(conf.answer_confidence ?? 0).toFixed(2)}</span>`);
      metaParts.push(`<span class="pill">grounding ${(conf.grounding_confidence ?? 0).toFixed(2)}</span>`);
      metaParts.push(`<span class="pill">halluc.risk ${(conf.hallucination_risk ?? 0).toFixed(2)}</span>`);
      if (a.abstained) metaParts.push(`<span class="pill bad">abstained: ${escapeHtml(a.abstention_reason || '')}</span>`);
      if (payload.was_rewritten && payload.rewritten_query) {
        metaParts.push(`<span class="pill rewrite">rewrote → ${escapeHtml(payload.rewritten_query)}</span>`);
      }
      if ((a.grounding_warnings || []).length) {
        metaParts.push(`<span class="pill warn">⚠ ${escapeHtml(a.grounding_warnings.join('; '))}</span>`);
      }
      const debug = `
        <details>
          <summary>debug</summary>
          <pre>${escapeHtml(JSON.stringify({
            provider: a.provider, model: a.model,
            used_chunks: a.used_chunks,
            unsupported_claims: a.hallucination?.unsupported_claims || [],
            judge_error: a.hallucination?.judge_error || null,
          }, null, 2))}</pre>
        </details>
      `;
      div.innerHTML = `
        <div class="body">${renderAnswerText(a.answer, a.citations)}</div>
        <div class="meta">${metaParts.join(' ')}</div>
        ${citationsBlock(a.citations)}
        ${debug}
      `;
      div.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }

    async function sendQuery() {
      if (busy) return;
      const query = inputEl.value.trim();
      if (!query) return;
      busy = true; sendBtn.disabled = true;
      inputEl.value = '';
      appendUser(query);
      const placeholder = appendAssistantPlaceholder();
      try {
        if (streamToggle.checked) {
          await streamQuery(query, placeholder);
        } else {
          await syncQuery(query, placeholder);
        }
      } catch (err) {
        placeholder.className = 'msg abstain';
        placeholder.innerHTML = `<div class="body">Error: ${escapeHtml(err.message || String(err))}</div>`;
      } finally {
        busy = false; sendBtn.disabled = false; inputEl.focus();
      }
    }

    async function syncQuery(query, placeholder) {
      const response = await fetch('/chat', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          query, session_id: sessionId, top_k: 5, candidate_pool: 20,
          token_budget: 2000, run_judge: judgeToggle.checked,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      sessionId = data.session_id;
      localStorage.setItem('chat_session_id', sessionId);
      renderAssistant(placeholder, data);
      updateUsage(data.answer && data.answer.usage);
    }

    async function streamQuery(query, placeholder) {
      const bodyEl = placeholder.querySelector('.body');
      const metaEl = placeholder.querySelector('.meta');
      let buffer = '';
      let metaInfo = {};
      const response = await fetch('/chat/stream', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          query, session_id: sessionId, top_k: 5, candidate_pool: 20,
          token_budget: 2000, run_judge: false,
        }),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        pending += decoder.decode(value, { stream: true });
        let eventBoundary;
        while ((eventBoundary = pending.indexOf('\\n\\n')) !== -1) {
          const raw = pending.slice(0, eventBoundary);
          pending = pending.slice(eventBoundary + 2);
          const lines = raw.split('\\n');
          let evtName = 'message';
          let dataStr = '';
          for (const line of lines) {
            if (line.startsWith('event:')) evtName = line.slice(6).trim();
            else if (line.startsWith('data:')) dataStr += line.slice(5).trim();
          }
          if (!dataStr) continue;
          let payload;
          try { payload = JSON.parse(dataStr); } catch { continue; }
          if (evtName === 'meta') {
            metaInfo = payload;
            sessionId = payload.session_id || sessionId;
            if (sessionId) localStorage.setItem('chat_session_id', sessionId);
          } else if (evtName === 'abstain') {
            placeholder.className = 'msg abstain';
            bodyEl.textContent = 'I could not find reliable information about that in the MITAOE data.';
            metaEl.innerHTML = `<span class="pill bad">abstained: ${escapeHtml(payload.reason || 'unknown')}</span>`;
            return;
          } else if (evtName === 'error') {
            throw new Error(payload.error || 'stream error');
          } else if (payload.delta) {
            buffer += payload.delta;
            bodyEl.innerHTML = renderAnswerText(buffer, []) + '<span class="streaming-cursor"></span>';
          }
          if (payload.done) {
            bodyEl.innerHTML = renderAnswerText(buffer, []);
            const conf = `<span class="pill">grounding ${(metaInfo.grounding_confidence ?? 0).toFixed(2)}</span>`;
            const rewritten = metaInfo.was_rewritten
              ? `<span class="pill rewrite">rewrote → ${escapeHtml(metaInfo.rewritten_query || '')}</span>` : '';
            metaEl.innerHTML = `${conf} ${rewritten} <span class="pill">streamed</span>`;
            // Streaming endpoint doesn't surface token counts; count 1 call (plus 1 if rewritten).
            updateUsage({ total_calls: 1 + (metaInfo.was_rewritten ? 1 : 0) });
          }
        }
      }
    }

    async function resetChat() {
      if (sessionId) {
        try { await fetch(`/conversation/${sessionId}`, { method: 'DELETE' }); } catch {}
      }
      sessionId = null;
      localStorage.removeItem('chat_session_id');
      messagesEl.innerHTML = '';
      messagesEl.appendChild(emptyState);
    }
  </script>
</body>
</html>
"""
