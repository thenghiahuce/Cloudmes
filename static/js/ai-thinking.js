/* MES Phase 17: visible thinking state for Vanna SSE, minimum 3s.
   The real request starts immediately. No server-side latency, API or permissions changed. */
(() => {
  'use strict';
  if (window.__mesThinkingInstalled) return;
  window.__mesThinkingInstalled = true;

  const MIN_MS = 3000;
  const fetchOriginal = window.fetch.bind(window);
  const paths = new Set(['/api/vanna/v2/chat_sse', '/api/customer-orders/assistant/vanna-sse']);
  const pending = new WeakMap();

  function match(input) {
    try {
      const raw = typeof input === 'string' || input instanceof URL ? String(input) : input?.url;
      const u = new URL(raw, window.location.href);
      return u.origin === window.location.origin && paths.has(u.pathname) ? u.pathname : null;
    } catch (_) { return null; }
  }

  // Reject only known bootstrap/empty messages. Do not rely on one client payload format.
  function isUserQuestion(input, init) {
    const raw = init?.body;
    if (typeof raw !== 'string') return true; // Unknown format: a POST to chat SSE is a chat attempt.
    try {
      const data = JSON.parse(raw);
      if (data?.metadata?.starter_ui_request === true) return false;
      const values = [data?.message, data?.question, data?.prompt, data?.text];
      if (values.some(v => typeof v === 'string' && v.trim())) return true;
      if (Array.isArray(data?.messages)) {
        return data.messages.some(v => v?.role === 'user' &&
          (typeof v.content === 'string' ? v.content.trim() : Array.isArray(v.content) && v.content.length));
      }
      // An explicitly empty message is only a bootstrap/empty input.
      if (values.some(v => typeof v === 'string')) return false;
      return true;
    } catch (_) { return true; }
  }

  function show(path) {
    const mount = document.getElementById(path.includes('customer-orders') ? 'customerVannaMount' : 'vannaMount');
    const surface = mount?.closest('.vanna-container');
    if (!surface) return () => {};
    let status = surface.querySelector(':scope > .mes-thinking-indicator');
    if (!status) {
      status = document.createElement('div');
      status.className = 'mes-thinking-indicator';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      const pulse = document.createElement('span');
      pulse.className = 'mes-thinking-pulse';
      pulse.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) pulse.appendChild(document.createElement('i'));
      const text = document.createElement('span');
      text.textContent = 'AI đang xử lý câu hỏi...';
      status.append(pulse, text);
      surface.appendChild(status);
    }
    pending.set(surface, (pending.get(surface) || 0) + 1);
    surface.classList.add('mes-thinking-active');
    let finished = false;
    return () => {
      if (finished) return;
      finished = true;
      const remaining = Math.max(0, (pending.get(surface) || 1) - 1);
      if (remaining) { pending.set(surface, remaining); return; }
      pending.delete(surface);
      surface.classList.remove('mes-thinking-active');
      status.remove();
    };
  }

  function wait(ms, signal) {
    if (ms <= 0) return Promise.resolve();
    return new Promise((resolve, reject) => {
      if (signal?.aborted) return reject(signal.reason || new DOMException('Aborted', 'AbortError'));
      let timer;
      const cleanup = () => { clearTimeout(timer); signal?.removeEventListener('abort', onAbort); };
      const onAbort = () => { cleanup(); reject(signal.reason || new DOMException('Aborted', 'AbortError')); };
      timer = setTimeout(() => { cleanup(); resolve(); }, ms);
      signal?.addEventListener('abort', onAbort, {once: true});
    });
  }

  window.fetch = async function mesThinkingFetch(input, init) {
    const path = match(input);
    const method = String(init?.method || input?.method || 'GET').toUpperCase();
    if (!path || method !== 'POST' || !isUserQuestion(input, init)) return fetchOriginal(input, init);

    const since = performance.now();
    const hide = show(path);
    const signal = init?.signal || (input instanceof Request ? input.signal : undefined);
    try {
      const response = await fetchOriginal(input, init);
      // On HTTP errors, show the real error promptly; on success, keep indicator for 3 seconds.
      if (response.ok) await wait(Math.max(0, MIN_MS - (performance.now() - since)), signal);
      hide();
      return response; // Same unmodified response and streaming bytes.
    } catch (error) { hide(); throw error; }
  };
})();
