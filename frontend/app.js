const state = {
  products: [],
  selectedProductId: null,
  sessionId: globalThis.crypto?.randomUUID?.() ?? `demo-${Date.now()}`,
  holdTimer: null,
  events: [],
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
  mongo: "몽고DB",
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
  storageFlow: document.getElementById("storage-flow"),
  stateItems: document.getElementById("state-items"),
  snapshotMeta: document.getElementById("snapshot-meta"),
  snapshotPayload: document.getElementById("snapshot-payload"),
  aofMeta: document.getElementById("aof-meta"),
  aofPayload: document.getElementById("aof-payload"),
  eventLog: document.getElementById("event-log"),
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
  const date = new Date(ms);
  const base = date.toLocaleString("ko-KR", { hour12: false });
  return `${base}.${String(date.getMilliseconds()).padStart(3, "0")}`;
}

function formatBytes(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return `${value.toLocaleString("ko-KR")} bytes`;
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

function pushEvent(title, detail) {
  const item = {
    id: `${Date.now()}-${Math.random()}`,
    title,
    detail,
  };
  state.events = [item, ...state.events].slice(0, 8);
  renderEvents();
}

function renderEvents() {
  nodes.eventLog.innerHTML = "";
  for (const item of state.events) {
    const li = document.createElement("li");
    li.innerHTML = `<strong>${item.title}</strong><div class="hint">${item.detail}</div>`;
    nodes.eventLog.appendChild(li);
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
        <div class="emoji">${product.emoji}</div>
        <h3>${product.name}</h3>
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
  pushEvent("원본 직접 조회", `${productId} · ${payload.latency_ms.toFixed(1)}ms`);
}

async function loadCached() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/cached`);
  setMetric("cache", payload);
  pushEvent(
    "레디스 캐시 조회",
    `${productId} · ${cacheStatusLabel[payload.cache_status] ?? payload.cache_status} · ${payload.latency_ms.toFixed(1)}ms`,
  );
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
  pushEvent("5회 비교", `원본 ${directAverage.toFixed(1)}ms vs 캐시 ${cacheAverage.toFixed(1)}ms`);
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
  pushEvent("TTL 홀드", `${productId} · 캐시가 15초 뒤 만료되도록 설정됨`);
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
  pushEvent("카운터 감소", `${productId} 재고 1 차감 -> ${payload.stock}`);
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
  pushEvent("카운터 증가", `${productId} 재고 1 증가 -> ${payload.stock}`);
}

async function invalidateProduct() {
  const productId = requireSelection();
  const payload = await api(`/store/products/${productId}/invalidate`, { method: "POST" });
  nodes.cacheStatus.textContent = "무효화됨";
  nodes.cacheStatus.className = "pill miss";
  await refreshState();
  pushEvent("네임스페이스 무효화", `${payload.namespace} version ${payload.version}`);
}

async function saveSnapshot() {
  const payload = await api("/admin/snapshot", { method: "POST" });
  await refreshState();
  pushEvent("스냅샷 저장", `${formatTimestamp(payload.saved_at_ms)} · ${payload.path}`);
}

async function refreshState() {
  const payload = await api("/store/state");
  nodes.originSource.textContent = sourceLabel[payload.origin_source] ?? payload.origin_source;
  const lastAofEvent = payload.aof_events.length
    ? payload.aof_events[payload.aof_events.length - 1]
    : null;
  const lastAofLabel = lastAofEvent?.op ?? "없음";
  nodes.snapshotStatus.textContent = payload.snapshot_exists
    ? `최근 스냅샷 ${formatTimestamp(payload.snapshot_updated_at_ms)}`
    : "스냅샷 없음";
  nodes.aofStatus.textContent = payload.aof_exists
    ? `AOF ${payload.aof_events.length}건 · 마지막 ${lastAofLabel} · ${formatTimestamp(payload.aof_updated_at_ms)}`
    : "AOF 없음";

  const flowItems = [
    {
      label: "실시간 저장",
      title: "메모리 저장소",
      chip: "항상 활성",
      chipClass: "active",
      detail: "조회, TTL, 카운터, 무효화는 먼저 메모리에서 바로 처리됩니다.",
    },
    {
      label: "전체 저장본",
      title: payload.snapshot_exists ? "스냅샷 저장됨" : "스냅샷 대기",
      chip: payload.snapshot_exists ? formatBytes(payload.snapshot_size_bytes) : "미생성",
      chipClass: payload.snapshot_exists ? "active" : "pending",
      detail: payload.snapshot_exists
        ? `현재 메모리 상태를 통째로 저장한 복구 기준점입니다. 마지막 저장: ${formatTimestamp(payload.snapshot_updated_at_ms)}`
        : "스냅샷 저장 버튼을 누르면 현재 메모리 상태가 파일로 고정됩니다.",
    },
    {
      label: "변경 로그",
      title: payload.aof_exists ? "AOF 기록 중" : "AOF 대기",
      chip: payload.aof_exists ? formatBytes(payload.aof_size_bytes) : "변경 없음",
      chipClass: payload.aof_exists ? "active" : "pending",
      detail: payload.aof_exists
        ? `스냅샷 이후 변경된 연산 ${payload.aof_events.length}건을 추가로 쌓아 재시작 시 replay합니다.`
        : "스냅샷 이후 새 변경이 생기면 이 영역에 로그가 쌓입니다.",
    },
  ];

  nodes.storageFlow.innerHTML = flowItems
    .map(
      (item) => `
        <article class="storage-stage">
          <span class="hint">${item.label}</span>
          <strong>${item.title}</strong>
          <span class="storage-chip ${item.chipClass}">${item.chip}</span>
          <p>${item.detail}</p>
        </article>
      `,
    )
    .join("");

  const items = [
    ["원본 데이터", sourceLabel[payload.origin_source] ?? payload.origin_source],
    ["원본 지연", `${payload.origin_delay_ms} ms`],
    ["상품 수", String(payload.product_count)],
    ["스냅샷 경로", payload.snapshot_path ?? "-"],
    ["AOF 경로", payload.aof_path ?? "-"],
    ["스냅샷 수정 시각", formatTimestamp(payload.snapshot_updated_at_ms)],
    ["AOF 수정 시각", formatTimestamp(payload.aof_updated_at_ms)],
  ];

  nodes.stateItems.innerHTML = items
    .map(
      ([label, value]) => `
        <article class="state-item">
          <span class="hint">${label}</span>
          <strong>${value}</strong>
        </article>
      `,
    )
    .join("");

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

function attachEvents() {
  document.getElementById("load-direct").addEventListener("click", () => wrapAction(loadDirect));
  document.getElementById("load-cached").addEventListener("click", () => wrapAction(loadCached));
  document.getElementById("run-benchmark").addEventListener("click", () => wrapAction(runBenchmark));
  document.getElementById("reserve-product").addEventListener("click", () => wrapAction(reserveProduct));
  document.getElementById("purchase-product").addEventListener("click", () => wrapAction(purchaseProduct));
  document.getElementById("restock-product").addEventListener("click", () => wrapAction(restockProduct));
  document.getElementById("invalidate-product").addEventListener("click", () => wrapAction(invalidateProduct));
  document.getElementById("save-snapshot").addEventListener("click", () => wrapAction(saveSnapshot));
  document.getElementById("refresh-state").addEventListener("click", () => wrapAction(refreshState));
}

async function wrapAction(fn) {
  try {
    await fn();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(error);
    pushEvent("오류", message);
  }
}

async function bootstrap() {
  attachEvents();
  await loadProducts();
  await refreshState();
  pushEvent("세션 시작", `데모 세션 ${state.sessionId.slice(0, 8)} 시작`);
}

bootstrap().catch((error) => {
  console.error(error);
  pushEvent("오류", error instanceof Error ? error.message : String(error));
});
