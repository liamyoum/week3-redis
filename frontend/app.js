const persistenceDemoStorageKey = "mini-redis-persistence-demo";

const state = {
  products: [],
  selectedProductId: null,
  sessionId: globalThis.crypto?.randomUUID?.() ?? `demo-${Date.now()}`,
  holdTimer: null,
  persistenceDemo: {
    pollTimer: null,
    phase: "idle",
    apiReachable: true,
    awaitingRecovery: false,
    exists: false,
    crashEnabled: null,
    currentValue: null,
    currentUpdatedAtMs: null,
    lastWrittenValue: null,
    lastWrittenAtMs: null,
    errorMessage: null,
  },
};

const cacheStatusLabel = {
  bypass: "우회",
  miss: "미스",
  hit: "히트",
  invalidated: "무효화됨",
};

const sourceLabel = {
  direct: "원본 경로",
  cache: "캐시 경로",
  seed: "시드 데이터",
  "seed-fallback": "시드 데이터",
  mongo: "MongoDB",
};

function resolveApiBase() {
  if (window.location.protocol === "file:") {
    return "http://127.0.0.1:8000";
  }
  if (window.location.port === "8080") {
    return "/api";
  }
  return "";
}

const apiBase = resolveApiBase();

const nodes = {
  originSource: document.getElementById("origin-source"),
  productGrid: document.getElementById("product-grid"),
  selectedTitle: document.getElementById("selected-title"),
  directLatency: document.getElementById("direct-latency"),
  directStatus: document.getElementById("direct-status"),
  directSource: document.getElementById("direct-source"),
  directPayload: document.getElementById("direct-payload"),
  cacheLatency: document.getElementById("cache-latency"),
  cacheStatus: document.getElementById("cache-status"),
  cacheSource: document.getElementById("cache-source"),
  cachePayload: document.getElementById("cache-payload"),
  directBar: document.getElementById("direct-bar"),
  cacheBar: document.getElementById("cache-bar"),
  directAverage: document.getElementById("direct-average"),
  cacheAverage: document.getElementById("cache-average"),
  holdStatus: document.getElementById("hold-status"),
  holdDetail: document.getElementById("hold-detail"),
  snapshotStatus: document.getElementById("snapshot-status"),
  aofStatus: document.getElementById("aof-status"),
  currentStock: document.getElementById("current-stock"),
  snapshotFileStatus: document.getElementById("snapshot-file-status"),
  snapshotFileUpdated: document.getElementById("snapshot-file-updated"),
  snapshotFileDetail: document.getElementById("snapshot-file-detail"),
  aofFileStatus: document.getElementById("aof-file-status"),
  aofFileUpdated: document.getElementById("aof-file-updated"),
  aofFileDetail: document.getElementById("aof-file-detail"),
  persistenceFlowTitle: document.getElementById("persistence-flow-title"),
  persistenceFlowDetail: document.getElementById("persistence-flow-detail"),
  persistenceFlowNote: document.getElementById("persistence-flow-note"),
  persistenceDemoStatus: document.getElementById("persistence-demo-status"),
  persistenceDemoDetail: document.getElementById("persistence-demo-detail"),
  persistenceDemoLastWritten: document.getElementById("persistence-demo-last-written"),
  persistenceDemoLastWrittenAt: document.getElementById("persistence-demo-last-written-at"),
  persistenceDemoCurrentValue: document.getElementById("persistence-demo-current-value"),
  persistenceDemoCurrentUpdated: document.getElementById("persistence-demo-current-updated"),
  snapshotMeta: document.getElementById("snapshot-meta"),
  snapshotPayload: document.getElementById("snapshot-payload"),
  aofMeta: document.getElementById("aof-meta"),
  aofPayload: document.getElementById("aof-payload"),
};

function parsePayload(text) {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    const trimmed = text.trim();
    if (trimmed.startsWith("<")) {
      return { detail: "서버가 JSON이 아닌 오류 화면을 반환했습니다." };
    }
    return { detail: trimmed };
  }
}

function formatTimestamp(ms) {
  if (typeof ms !== "number" || !Number.isFinite(ms)) {
    return "-";
  }
  return new Date(ms).toLocaleString("ko-KR", { hour12: false });
}

function formatBytes(value) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return "-";
  }
  if (value < 1024) {
    return `${value.toLocaleString("ko-KR")} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

async function api(path, options = {}) {
  const response = await fetch(`${apiBase}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
    ...options,
  });

  const payload = parsePayload(await response.text());
  if (!response.ok) {
    throw new Error(payload?.detail ?? `Request failed: ${response.status}`);
  }
  return payload;
}

function loadPersistenceDemoMemory() {
  try {
    const raw = window.localStorage.getItem(persistenceDemoStorageKey);
    if (!raw) {
      return;
    }

    const payload = JSON.parse(raw);
    if (typeof payload.lastWrittenValue === "string") {
      state.persistenceDemo.lastWrittenValue = payload.lastWrittenValue;
    }
    if (typeof payload.lastWrittenAtMs === "number") {
      state.persistenceDemo.lastWrittenAtMs = payload.lastWrittenAtMs;
    }
  } catch {
    window.localStorage?.removeItem?.(persistenceDemoStorageKey);
  }
}

function savePersistenceDemoMemory() {
  try {
    window.localStorage.setItem(
      persistenceDemoStorageKey,
      JSON.stringify({
        lastWrittenValue: state.persistenceDemo.lastWrittenValue,
        lastWrittenAtMs: state.persistenceDemo.lastWrittenAtMs,
      }),
    );
  } catch {
    // localStorage is best-effort only.
  }
}

function renderProducts() {
  nodes.productGrid.innerHTML = "";
  for (const product of state.products) {
    const card = document.createElement("button");
    card.className = "product-card";
    if (product.id === state.selectedProductId) {
      card.classList.add("selected");
    }
    card.innerHTML = `
      <img src="${product.image_url}" alt="${product.name}" />
      <div class="content">
        <span class="badge">${product.badge}</span>
        <div class="emoji">${product.emoji}</div>
        <h3>${product.name}</h3>
        <p>${product.tagline}</p>
        <div class="product-meta">
          <strong>${product.price.toLocaleString()}원</strong>
          <span>재고 ${product.stock}</span>
        </div>
      </div>
    `;
    card.addEventListener("click", () => {
      state.selectedProductId = product.id;
      nodes.selectedTitle.textContent = `${product.name} 비교`;
      nodes.currentStock.textContent = String(product.stock);
      renderProducts();
    });
    nodes.productGrid.appendChild(card);
  }
}

function renderPersistenceDemo() {
  const demo = state.persistenceDemo;
  let status = "기록 없음";
  let detail = "복구 데모 설정을 확인하는 중입니다.";

  if (demo.crashEnabled === false) {
    detail = "강제 종료 데모는 현재 환경에서 비활성화되어 있습니다.";
  } else if (demo.crashEnabled) {
    detail = "먼저 `복구용 데이터 생성` 버튼으로 기준값을 만드세요.";
  }

  if (demo.errorMessage) {
    status = "작업 실패";
    detail = demo.errorMessage;
  } else if (demo.phase === "crashing") {
    status = "API 종료 요청됨";
    detail = "응답을 돌려준 뒤 API 프로세스를 비정상 종료하는 중입니다.";
  } else if (!demo.apiReachable || demo.phase === "down") {
    status = "API 중단됨";
    detail = "프론트는 열려 있습니다. 터미널에서 `docker compose up -d api` 를 실행하면 자동으로 복구를 확인합니다.";
  } else if (demo.phase === "recovered") {
    status = "복구 확인";
    detail = "마지막으로 쓴 값이 재시작 후에도 그대로 남아 있습니다.";
  } else if (demo.phase === "written") {
    status = "기록 완료";
    detail = "현재 값이 메모리와 AOF에 반영된 상태입니다. 이제 강제 종료를 눌러도 됩니다.";
  } else if (demo.exists) {
    status = "서버 기록 존재";
    detail = "서버에서 데모용 영속성 값을 확인했습니다.";
  }

  nodes.persistenceDemoStatus.textContent = status;
  nodes.persistenceDemoDetail.textContent = detail;
  nodes.persistenceDemoLastWritten.textContent = demo.lastWrittenValue ?? "-";
  nodes.persistenceDemoLastWrittenAt.textContent = demo.lastWrittenAtMs
    ? `브라우저 기준 ${formatTimestamp(demo.lastWrittenAtMs)}`
    : "브라우저에 저장된 기준값이 없습니다.";
  nodes.persistenceDemoCurrentValue.textContent = demo.exists ? demo.currentValue ?? "-" : "-";
  nodes.persistenceDemoCurrentUpdated.textContent = demo.exists && demo.currentUpdatedAtMs
    ? `서버 마지막 업데이트 ${formatTimestamp(demo.currentUpdatedAtMs)}`
    : demo.apiReachable
      ? "아직 서버에 저장된 데모 값이 없습니다."
      : "API가 내려가 있어 현재 서버 값을 읽을 수 없습니다.";
}

function showPersistenceDemoError(message) {
  state.persistenceDemo.errorMessage = message;
  renderPersistenceDemo();
}

function startPersistenceDemoPolling() {
  if (state.persistenceDemo.pollTimer !== null) {
    return;
  }
  state.persistenceDemo.pollTimer = window.setInterval(() => {
    void fetchPersistenceDemoStatus({ silent: true });
  }, 2000);
}

function stopPersistenceDemoPolling() {
  if (state.persistenceDemo.pollTimer === null) {
    return;
  }
  window.clearInterval(state.persistenceDemo.pollTimer);
  state.persistenceDemo.pollTimer = null;
}

function applyPersistenceDemoPayload(payload) {
  state.persistenceDemo.apiReachable = true;
  state.persistenceDemo.exists = payload.exists;
  state.persistenceDemo.crashEnabled = Boolean(payload.crash_enabled);
  state.persistenceDemo.currentValue = payload.value ?? null;
  state.persistenceDemo.currentUpdatedAtMs = payload.updated_at_ms ?? null;
  state.persistenceDemo.errorMessage = null;
}

async function fetchPersistenceDemoStatus({ silent = false } = {}) {
  try {
    const payload = await api("/admin/persistence-demo");
    const wasUnreachable = !state.persistenceDemo.apiReachable;
    const wasAwaitingRecovery = state.persistenceDemo.awaitingRecovery;

    applyPersistenceDemoPayload(payload);

    if (!payload.exists && state.persistenceDemo.phase !== "recovered") {
      state.persistenceDemo.phase = "idle";
      if (wasAwaitingRecovery) {
        state.persistenceDemo.awaitingRecovery = false;
        state.persistenceDemo.errorMessage = "재시작 후 마지막으로 쓴 값이 복구되지 않았습니다.";
      }
    } else if (
      payload.exists &&
      state.persistenceDemo.lastWrittenValue &&
      payload.value === state.persistenceDemo.lastWrittenValue &&
      wasAwaitingRecovery
    ) {
      state.persistenceDemo.phase = "recovered";
      state.persistenceDemo.awaitingRecovery = false;
    } else if (payload.exists && state.persistenceDemo.phase !== "recovered") {
      state.persistenceDemo.phase = "written";
      if (wasAwaitingRecovery && state.persistenceDemo.lastWrittenValue && payload.value !== state.persistenceDemo.lastWrittenValue) {
        state.persistenceDemo.awaitingRecovery = false;
        state.persistenceDemo.errorMessage = `복구 후 값이 달라졌습니다: ${payload.value}`;
      }
    }

    renderPersistenceDemo();
    stopPersistenceDemoPolling();

    if (wasUnreachable) {
      await Promise.allSettled([loadProducts(), refreshState()]);
    }

    return payload;
  } catch (error) {
    const wasReachable = state.persistenceDemo.apiReachable;
    state.persistenceDemo.apiReachable = false;
    if (state.persistenceDemo.awaitingRecovery || state.persistenceDemo.phase === "crashing") {
      state.persistenceDemo.phase = "down";
      startPersistenceDemoPolling();
    }
    renderPersistenceDemo();
    if (wasReachable && !silent) {
      console.error(error);
    }
    return null;
  }
}

function setMetric(prefix, payload) {
  const latencyNode = prefix === "direct" ? nodes.directLatency : nodes.cacheLatency;
  const statusNode = prefix === "direct" ? nodes.directStatus : nodes.cacheStatus;
  const sourceNode = prefix === "direct" ? nodes.directSource : nodes.cacheSource;
  const payloadNode = prefix === "direct" ? nodes.directPayload : nodes.cachePayload;

  latencyNode.textContent = `${payload.latency_ms.toFixed(1)}ms`;
  statusNode.textContent = cacheStatusLabel[payload.cache_status] ?? payload.cache_status;
  statusNode.className = `pill ${payload.cache_status}`;
  sourceNode.textContent = `${sourceLabel[payload.source] ?? payload.source} · ${sourceLabel[payload.origin_source] ?? payload.origin_source}`;
  payloadNode.textContent = JSON.stringify(
    {
      상품명: payload.product.name,
      설명: payload.product.description,
      가격: `${payload.product.price.toLocaleString()}원`,
      재고: payload.product.stock,
      네임스페이스: payload.product.cache_namespace,
      이미지: payload.product.image_url,
    },
    null,
    2,
  );
  nodes.currentStock.textContent = String(payload.product.stock);

  const known = state.products.find((item) => item.id === payload.product.id);
  if (known) {
    known.stock = payload.product.stock;
    renderProducts();
  }
}

async function loadProducts() {
  const payload = await api("/store/products");
  state.products = payload.products;
  nodes.originSource.textContent = sourceLabel[payload.origin_source] ?? payload.origin_source;
  if (!state.selectedProductId && payload.products.length > 0) {
    state.selectedProductId = payload.products[0].id;
    nodes.selectedTitle.textContent = `${payload.products[0].name} 비교`;
    nodes.currentStock.textContent = String(payload.products[0].stock);
  }
  renderProducts();
}

function requireSelection() {
  if (!state.selectedProductId) {
    throw new Error("먼저 상품을 선택하세요.");
  }
  return state.selectedProductId;
}

async function loadDirect() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/direct`);
  setMetric("direct", payload);
}

async function loadCached() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/cached`);
  setMetric("cache", payload);
}

function setBenchmarkBars(directAverage, cacheAverage) {
  const max = Math.max(directAverage, cacheAverage, 1);
  nodes.directBar.style.width = `${(directAverage / max) * 100}%`;
  nodes.cacheBar.style.width = `${(cacheAverage / max) * 100}%`;
  nodes.directAverage.textContent = `${directAverage.toFixed(1)}ms`;
  nodes.cacheAverage.textContent = `${cacheAverage.toFixed(1)}ms`;
}

async function runBenchmark() {
  const productId = requireSelection();
  await api(`/store/products/${productId}/invalidate`, { method: "POST" });

  const directDurations = [];
  const cacheDurations = [];

  for (let index = 0; index < 5; index += 1) {
    const direct = await api(`/store/products/${productId}/direct`);
    directDurations.push(direct.latency_ms);
  }

  for (let index = 0; index < 5; index += 1) {
    const cached = await api(`/store/products/${productId}/cached`);
    cacheDurations.push(cached.latency_ms);
  }

  const directAverage = directDurations.reduce((sum, value) => sum + value, 0) / directDurations.length;
  const cacheAverage = cacheDurations.reduce((sum, value) => sum + value, 0) / cacheDurations.length;
  setBenchmarkBars(directAverage, cacheAverage);
}

async function reserveProduct() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/reserve`, {
    method: "POST",
    body: JSON.stringify({
      session_id: state.sessionId,
      ttl_ms: 15000,
    }),
  });
  startHoldCountdown(payload.expires_at_ms);
  await refreshState();
}

function startHoldCountdown(expiresAtMs) {
  window.clearInterval(state.holdTimer);
  const tick = () => {
    const remainingMs = expiresAtMs - Date.now();
    if (remainingMs <= 0) {
      nodes.holdStatus.textContent = "만료됨";
      nodes.holdDetail.textContent = "선택한 상품 캐시 TTL이 만료되어 다음 캐시 조회는 miss가 됩니다.";
      window.clearInterval(state.holdTimer);
      state.holdTimer = null;
      return;
    }
    nodes.holdStatus.textContent = `${Math.ceil(remainingMs / 1000)}초 남음`;
    nodes.holdDetail.textContent = `선택한 상품 캐시가 ${Math.ceil(remainingMs / 1000)}초 뒤 만료됩니다.`;
  };
  tick();
  state.holdTimer = window.setInterval(tick, 1000);
}

async function purchaseProduct() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/purchase`, {
    method: "POST",
    body: JSON.stringify({ quantity: 1 }),
  });
  nodes.currentStock.textContent = String(payload.stock);
  await loadProducts();
  await refreshState();
}

async function restockProduct() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/restock`, {
    method: "POST",
    body: JSON.stringify({ quantity: 1 }),
  });
  nodes.currentStock.textContent = String(payload.stock);
  await loadProducts();
  await refreshState();
}

async function invalidateProduct() {
  const productId = requireSelection();
  await api(`/store/products/${productId}/invalidate`, { method: "POST" });
  nodes.cacheStatus.textContent = "무효화됨";
  nodes.cacheStatus.className = "pill miss";
  await refreshState();
}

async function saveSnapshot() {
  await api("/admin/snapshot", { method: "POST" });
  await refreshState();
}

async function refreshState() {
  const payload = await api("/store/state");
  nodes.originSource.textContent = sourceLabel[payload.origin_source] ?? payload.origin_source;
  nodes.snapshotStatus.textContent = payload.snapshot_exists
    ? `최근 스냅샷 ${formatTimestamp(payload.snapshot_updated_at_ms)}`
    : "스냅샷 없음";
  nodes.aofStatus.textContent = payload.aof_exists
    ? `AOF ${payload.aof_events.length}건 · ${formatTimestamp(payload.aof_updated_at_ms)}`
    : "AOF 없음";

  nodes.snapshotFileStatus.textContent = payload.snapshot_exists ? "저장된 Snapshot 있음" : "아직 Snapshot 없음";
  nodes.snapshotFileUpdated.textContent = payload.snapshot_exists
    ? `마지막 저장 ${formatTimestamp(payload.snapshot_updated_at_ms)}`
    : "아직 스냅샷을 저장하지 않았습니다.";
  nodes.snapshotFileDetail.textContent = payload.snapshot_exists
    ? `${formatBytes(payload.snapshot_size_bytes)} · ${payload.snapshot_path ?? "-"}`
    : payload.snapshot_path ?? "Snapshot 경로가 설정되지 않았습니다.";

  nodes.aofFileStatus.textContent = payload.aof_exists
    ? payload.aof_size_bytes > 0
      ? "변경분 기록 중"
      : "AOF 파일 준비됨"
    : "아직 AOF 없음";
  nodes.aofFileUpdated.textContent = payload.aof_exists
    ? `마지막 기록 ${formatTimestamp(payload.aof_updated_at_ms)}`
    : "아직 AOF 파일이 생성되지 않았습니다.";
  nodes.aofFileDetail.textContent = payload.aof_exists
    ? `${formatBytes(payload.aof_size_bytes)} · ${payload.aof_path ?? "-"}`
    : payload.aof_path ?? "AOF 경로가 설정되지 않았습니다.";

  nodes.persistenceFlowTitle.textContent = "Snapshot -> AOF Replay";
  nodes.persistenceFlowDetail.textContent = payload.snapshot_exists
    ? "시작 시 Snapshot을 먼저 불러오고, 그 뒤 AOF를 replay 해서 최신 상태를 맞춥니다."
    : "아직 Snapshot이 없어도, 남아 있는 AOF 변경분만으로 마지막 쓰기를 복구할 수 있습니다.";
  nodes.persistenceFlowNote.textContent = "종료 시 Snapshot 저장 · 비정상 종료 시 AOF가 마지막 변경분을 살립니다.";

  nodes.snapshotMeta.textContent = payload.snapshot_exists
    ? `${formatBytes(payload.snapshot_size_bytes)} · ${formatTimestamp(payload.snapshot_updated_at_ms)}`
    : "저장된 스냅샷 없음";
  nodes.snapshotPayload.textContent = payload.snapshot_payload
    ? JSON.stringify(payload.snapshot_payload, null, 2)
    : "저장된 스냅샷 없음";

  nodes.aofMeta.textContent = payload.aof_exists
    ? `${payload.aof_events.length}건 · ${formatBytes(payload.aof_size_bytes)} · ${formatTimestamp(payload.aof_updated_at_ms)}`
    : "AOF 이벤트 없음";
  nodes.aofPayload.textContent = payload.aof_events.length
    ? JSON.stringify(payload.aof_events, null, 2)
    : "AOF 이벤트 없음";
}

async function refreshPersistencePanel() {
  await Promise.allSettled([refreshState(), fetchPersistenceDemoStatus({ silent: true })]);
}

async function writePersistenceDemo() {
  const payload = await api("/admin/persistence-demo/write", { method: "POST" });
  applyPersistenceDemoPayload(payload);
  state.persistenceDemo.phase = "written";
  state.persistenceDemo.awaitingRecovery = false;
  state.persistenceDemo.lastWrittenValue = payload.value ?? null;
  state.persistenceDemo.lastWrittenAtMs = payload.updated_at_ms ?? Date.now();
  savePersistenceDemoMemory();
  stopPersistenceDemoPolling();
  renderPersistenceDemo();
  await refreshState();
}

async function crashApi() {
  if (!state.persistenceDemo.crashEnabled) {
    throw new Error("이 환경에서는 강제 종료 데모가 비활성화되어 있습니다.");
  }
  if (!state.persistenceDemo.lastWrittenValue) {
    throw new Error("먼저 `복구용 데이터 생성` 버튼으로 기준값을 쓰세요.");
  }

  const payload = await api("/admin/persistence-demo/crash", { method: "POST" });
  state.persistenceDemo.phase = "crashing";
  state.persistenceDemo.awaitingRecovery = true;
  state.persistenceDemo.errorMessage = null;
  renderPersistenceDemo();

  window.setTimeout(() => {
    void fetchPersistenceDemoStatus({ silent: true });
  }, payload.delay_ms + 450);
}

async function checkPersistenceDemo() {
  await fetchPersistenceDemoStatus();
}

function attachEvents() {
  document.getElementById("load-direct").addEventListener("click", () => wrapAction(loadDirect));
  document.getElementById("load-cached").addEventListener("click", () => wrapAction(loadCached));
  document.getElementById("run-benchmark").addEventListener("click", () => wrapAction(runBenchmark));
  document.getElementById("reserve-product").addEventListener("click", () => wrapAction(reserveProduct));
  document.getElementById("purchase-product").addEventListener("click", () => wrapAction(purchaseProduct));
  document.getElementById("restock-product").addEventListener("click", () => wrapAction(restockProduct));
  document.getElementById("invalidate-product").addEventListener("click", () => wrapAction(invalidateProduct));
  document.getElementById("save-snapshot").addEventListener("click", () => wrapAction(saveSnapshot));
  document.getElementById("refresh-state").addEventListener("click", () => wrapAction(refreshPersistencePanel));
  document.getElementById("write-persistence-demo").addEventListener("click", () => wrapAction(writePersistenceDemo, showPersistenceDemoError));
  document.getElementById("crash-api").addEventListener("click", () => wrapAction(crashApi, showPersistenceDemoError));
  document.getElementById("check-persistence-demo").addEventListener("click", () => wrapAction(checkPersistenceDemo, showPersistenceDemoError));
}

async function wrapAction(fn, onError = null) {
  try {
    await fn();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(error);
    if (onError) {
      onError(message);
    }
  }
}

async function bootstrap() {
  loadPersistenceDemoMemory();
  renderPersistenceDemo();
  attachEvents();
  await Promise.allSettled([loadProducts(), refreshPersistencePanel()]);
}

bootstrap().catch((error) => {
  console.error(error);
  showPersistenceDemoError(error instanceof Error ? error.message : String(error));
});
