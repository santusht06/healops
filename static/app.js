/**
 * HealOps Autonomous SRE Mission Control Frontend
 * Real-time WebSocket + REST Client for Strands Agent & Cedar Guardrails
 */

let ws = null;
let currentApprovalId = null;
let pollTimer = null;

// DOM Elements
const cpuVal = document.getElementById("cpu-val");
const cpuBar = document.getElementById("cpu-bar");
const ramVal = document.getElementById("ram-val");
const ramBar = document.getElementById("ram-bar");
const diskVal = document.getElementById("disk-val");
const diskBar = document.getElementById("disk-bar");
const redisVal = document.getElementById("redis-val");

const servicesContainer = document.getElementById("services-container");
const serviceCount = document.getElementById("service-count");
const telemetryRefreshTime = document.getElementById("telemetry-refresh-time");

const incidentBanner = document.getElementById("incident-banner");
const bannerTitle = document.getElementById("banner-title");
const bannerSub = document.getElementById("banner-sub");
const bannerStage = document.getElementById("banner-stage");
const agentStatusText = document.getElementById("agent-status-text");
const agentPulseDot = document.getElementById("agent-pulse-dot");

const hitlCard = document.getElementById("hitl-approval-card");
const hitlPromptText = document.getElementById("hitl-prompt-text");
const hitlTool = document.getElementById("hitl-tool");
const hitlTarget = document.getElementById("hitl-target");

const agentFeed = document.getElementById("agent-feed-container");
const auditContainer = document.getElementById("audit-stream-container");
const postmortemContainer = document.getElementById("postmortem-container");
const postmortemCount = document.getElementById("postmortem-count");

const wsIndicator = document.getElementById("ws-indicator");
const wsStatusText = document.getElementById("ws-status-text");
const customPromptInput = document.getElementById("custom-prompt-input");

// ==========================================================
// Initialization
// ==========================================================
document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  fetchInitialData();

  // Periodic telemetry refresh every 5s
  pollTimer = setInterval(fetchTelemetry, 5000);

  // Enter key for prompt
  customPromptInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitCustomPrompt();
  });
});

// ==========================================================
// WebSocket Handling
// ==========================================================
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host || "localhost:8000";
  const wsUrl = `${protocol}//${host}/ws/stream`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[HealOps WS] Connected to agent event stream");
    wsIndicator.className = "connection-status connected";
    wsStatusText.textContent = "Live Socket";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleLiveEvent(msg);
    } catch (err) {
      console.error("[HealOps WS] Parse error", err);
    }
  };

  ws.onclose = () => {
    console.warn("[HealOps WS] Disconnected. Reconnecting in 3s...");
    wsIndicator.className = "connection-status disconnected";
    wsStatusText.textContent = "Reconnecting...";
    setTimeout(initWebSocket, 3000);
  };

  ws.onerror = (err) => {
    console.error("[HealOps WS] Socket error:", err);
  };
}

function handleLiveEvent(msg) {
  const { event_type, data, timestamp } = msg;
  const timeStr = timestamp ? timestamp.split(" ")[1] : new Date().toLocaleTimeString();

  switch (event_type) {
    case "INITIAL_STATE":
      if (data.telemetry) updateTelemetryUI(data.telemetry);
      if (data.services) renderServices(data.services);
      if (data.incident && data.incident.is_active) {
        setIncidentState(data.incident);
      }
      break;

    case "INCIDENT_TRIGGERED":
      setIncidentState(data);
      appendAgentFeedItem({
        title: `🚨 Incident Detected: ${data.service}`,
        text: `Symptom: ${data.description}\nAuto-dispatching Strands SRE Agent for root-cause analysis...`,
        tool: "health_watcher",
        time: timeStr,
        isAlert: true
      });
      fetchServices();
      // Automatically trigger triage sequence if not already running
      setTimeout(() => {
        triggerTriage(data.service);
      }, 800);
      break;

    case "CHAOS_RESET":
      resetIncidentUI();
      fetchServices();
      appendAgentFeedItem({
        title: "Topology Restored",
        text: "All cluster microservices reset to healthy baseline state.",
        tool: "chaos_reset",
        time: timeStr
      });
      break;

    case "TRIAGE_STARTED":
      bannerStage.textContent = "INVESTIGATING";
      agentStatusText.textContent = `Agent Triage • ${data.service}`;
      agentPulseDot.className = "pulse-dot active";
      break;

    case "AGENT_THOUGHT":
      appendAgentFeedItem({
        title: `Step ${data.step}: ${data.title}`,
        text: data.thought,
        tool: data.tool,
        time: timeStr
      });
      break;

    case "APPROVAL_REQUIRED":
      showHitlApproval(data);
      agentStatusText.textContent = "Cedar Gate: Operator Sign-off Needed";
      agentPulseDot.className = "pulse-dot alert";
      bannerStage.textContent = "AWAITING APPROVAL";
      break;

    case "INCIDENT_RESOLVED":
      hitlCard.classList.add("hidden");
      currentApprovalId = null;
      setResolvedUI(data);
      appendAgentFeedItem({
        title: `✅ Incident Healed: ${data.service}`,
        text: `Remediation executed cleanly!\nDetails: ${JSON.stringify(data.result)}\nMTTR: ${data.duration}\nPost-Mortem auto-indexed to Runbook Memory.`,
        tool: "postmortem_indexer",
        time: timeStr,
        isResolved: true
      });
      fetchServices();
      fetchAuditLogs();
      fetchPostmortems();
      break;

    default:
      console.log("[HealOps WS] Unhandled event:", event_type, data);
  }
}

// ==========================================================
// REST Fetchers & UI Updaters
// ==========================================================
async function fetchInitialData() {
  fetchTelemetry();
  fetchServices();
  fetchAuditLogs();
  fetchPostmortems();
}

async function fetchTelemetry() {
  try {
    const res = await fetch("/api/telemetry");
    if (!res.ok) return;
    const data = await res.json();
    if (data.system) updateTelemetryUI(data.system, data.redis);
    telemetryRefreshTime.textContent = new Date().toLocaleTimeString();
  } catch (err) {
    console.error("Telemetry fetch error:", err);
  }
}

function updateTelemetryUI(sys, redis) {
  if (sys.cpu_percent !== undefined) {
    cpuVal.textContent = `${sys.cpu_percent.toFixed(1)}%`;
    cpuBar.style.width = `${Math.min(sys.cpu_percent, 100)}%`;
  }
  if (sys.ram_percent !== undefined) {
    ramVal.textContent = `${sys.ram_percent.toFixed(1)}%`;
    ramBar.style.width = `${Math.min(sys.ram_percent, 100)}%`;
  }
  if (sys.disk_percent !== undefined) {
    diskVal.textContent = `${sys.disk_percent.toFixed(1)}%`;
    diskBar.style.width = `${Math.min(sys.disk_percent, 100)}%`;
  }
  if (redis && redis.used_memory_human) {
    redisVal.textContent = redis.used_memory_human;
  }
}

async function fetchServices() {
  try {
    const res = await fetch("/api/services");
    if (!res.ok) return;
    const data = await res.json();
    renderServices(data.services || []);
  } catch (err) {
    console.error("Services fetch error:", err);
  }
}

function renderServices(services) {
  servicesContainer.innerHTML = "";
  serviceCount.textContent = services.length;

  services.forEach((s) => {
    const isDegraded = s.status === "degraded" || s.health.includes("502");
    const item = document.createElement("div");
    item.className = `service-item ${isDegraded ? "degraded" : ""}`;
    item.innerHTML = `
      <div class="service-meta-left">
        <span class="service-status-dot ${isDegraded ? "degraded" : "running"}"></span>
        <div>
          <div class="service-name">${s.name}</div>
          <div class="service-meta-sub">${s.type} • :${s.port}</div>
        </div>
      </div>
      <div>
        <span class="service-badge ${isDegraded ? "error" : "healthy"}">${s.health}</span>
      </div>
    `;
    servicesContainer.appendChild(item);
  });
}

async function fetchAuditLogs() {
  try {
    const res = await fetch("/api/audit?limit=25");
    if (!res.ok) return;
    const data = await res.json();
    renderAuditLogs(data.audit_logs || []);
  } catch (err) {
    console.error("Audit fetch error:", err);
  }
}

function renderAuditLogs(logs) {
  auditContainer.innerHTML = "";
  if (!logs.length) {
    auditContainer.innerHTML = `<div class="loading-placeholder">No audit entries yet.</div>`;
    return;
  }

  logs.forEach((log) => {
    const item = document.createElement("div");
    item.className = "audit-item";
    const decisionLower = (log.decision || "allow").toLowerCase();

    item.innerHTML = `
      <div class="audit-header-row">
        <span class="audit-action">${log.tool_name || log.action}</span>
        <span class="audit-decision ${decisionLower}">${log.decision}</span>
      </div>
      <div class="audit-meta-row">
        <span>Caller: ${log.caller_role || "oncall"}</span>
        <span>${log.timestamp ? log.timestamp.split("T")[1].replace("Z", "") : ""}</span>
      </div>
    `;
    auditContainer.appendChild(item);
  });
}

async function fetchPostmortems() {
  try {
    const res = await fetch("/api/postmortems");
    if (!res.ok) return;
    const data = await res.json();
    renderPostmortems(data.postmortems || []);
  } catch (err) {
    console.error("Postmortem fetch error:", err);
  }
}

function renderPostmortems(pms) {
  postmortemContainer.innerHTML = "";
  postmortemCount.textContent = pms.length;

  if (!pms.length) {
    postmortemContainer.innerHTML = `<div class="loading-placeholder">No runbooks indexed.</div>`;
    return;
  }

  pms.slice(-4).reverse().forEach((pm) => {
    const item = document.createElement("div");
    item.className = "postmortem-item";
    item.innerHTML = `
      <div class="pm-header">
        <span class="pm-id">${pm.id}</span>
        <span class="pm-service">${pm.service} • ${pm.severity}</span>
      </div>
      <div class="pm-cause"><strong>Root Cause:</strong> ${pm.root_cause}</div>
    `;
    postmortemContainer.appendChild(item);
  });
}

// ==========================================================
// Agent Reasoning Stream UI
// ==========================================================
function appendAgentFeedItem({ title, text, tool, time, isAlert, isResolved }) {
  const item = document.createElement("div");
  item.className = `agent-step-item ${isResolved ? "resolved" : ""}`;

  let avatar = "⚙️";
  if (isAlert) avatar = "🚨";
  else if (isResolved) avatar = "🎉";
  else if (tool === "restart_service") avatar = "🔄";
  else if (tool === "lookup_past_incidents") avatar = "🧠";
  else if (tool === "inspect_service_logs") avatar = "🔍";

  item.innerHTML = `
    <div class="step-avatar">${avatar}</div>
    <div class="step-content">
      <div class="step-meta">
        <span class="step-title">${title}</span>
        <span class="step-time">${time}</span>
      </div>
      <p class="step-text">${escapeHtml(text)}</p>
      ${tool ? `<span class="step-tool-badge">tool: ${tool}</span>` : ""}
    </div>
  `;

  agentFeed.appendChild(item);
  agentFeed.scrollTop = agentFeed.scrollHeight;
}

// ==========================================================
// Incident & Cedar HITL Workflow
// ==========================================================
function setIncidentState(incident) {
  incidentBanner.className = "incident-banner banner-incident";
  bannerTitle.textContent = `CRITICAL INCIDENT: ${incident.service}`;
  bannerSub.textContent = incident.description || "Outage detected";
  bannerStage.textContent = incident.stage || "DETECTED";

  agentStatusText.textContent = `Incident Active • ${incident.service}`;
  agentPulseDot.className = "pulse-dot alert";
}

function resetIncidentUI() {
  incidentBanner.className = "incident-banner banner-idle";
  bannerTitle.textContent = "System Operational";
  bannerSub.textContent = "Autonomous watcher scanning telemetry every 5s";
  bannerStage.textContent = "IDLE";

  agentStatusText.textContent = "Agent Idle • Monitoring";
  agentPulseDot.className = "pulse-dot idle";
  hitlCard.classList.add("hidden");
  currentApprovalId = null;
}

function setResolvedUI(data) {
  incidentBanner.className = "incident-banner banner-idle";
  bannerTitle.textContent = `Resolved: ${data.service} Restored`;
  bannerSub.textContent = `Auto-healed in ${data.duration}. System running normally.`;
  bannerStage.textContent = "RESOLVED";

  agentStatusText.textContent = "Agent Idle • Incident Resolved";
  agentPulseDot.className = "pulse-dot idle";
}

function showHitlApproval(data) {
  currentApprovalId = data.approval_id;
  hitlPromptText.innerHTML = `HealOps proposes executing <code>${data.tool_name}</code> on <strong>${data.service_name}</strong>. ${data.policy}`;
  hitlTool.textContent = data.tool_name;
  hitlTarget.textContent = data.service_name;
  hitlCard.classList.remove("hidden");
}

async function resolveApproval(approved) {
  if (!currentApprovalId) return;

  try {
    const res = await fetch("/api/remediation/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        approval_id: currentApprovalId,
        approved: approved
      })
    });
    const data = await res.json();
    console.log("Decision recorded:", data);

    hitlCard.classList.add("hidden");
    appendAgentFeedItem({
      title: approved ? "Operator Approved Remediation" : "Operator Denied Remediation",
      text: approved
        ? "Authorization confirmed by human SRE. Strands Agent proceeding with service restart."
        : "Operator denied authorization. Remediation aborted.",
      tool: "cedar_guard",
      time: new Date().toLocaleTimeString()
    });
  } catch (err) {
    console.error("Decision error:", err);
  }
}

// ==========================================================
// Chaos Triggers & Triage Dispatch
// ==========================================================
async function injectChaos() {
  try {
    appendAgentFeedItem({
      title: "💥 Chaos Drill Triggered",
      text: "Simulating sudden connection pool exhaustion and HTTP 502 Bad Gateway on api-gateway...",
      tool: "chaos_injector",
      time: new Date().toLocaleTimeString()
    });

    const res = await fetch("/api/chaos/inject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service_name: "api-gateway", failure_type: "502_bad_gateway" })
    });
    const data = await res.json();
    console.log("Chaos injected:", data);
  } catch (err) {
    console.error("Chaos error:", err);
  }
}

async function resetChaos() {
  try {
    const res = await fetch("/api/chaos/reset", { method: "POST" });
    const data = await res.json();
    console.log("Chaos reset:", data);
  } catch (err) {
    console.error("Chaos reset error:", err);
  }
}

async function triggerTriage(serviceName = "api-gateway") {
  try {
    const res = await fetch("/api/triage/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service_name: serviceName, role: "oncall" })
    });
    const data = await res.json();
    console.log("Triage triggered:", data);
  } catch (err) {
    console.error("Triage dispatch error:", err);
  }
}

async function submitCustomPrompt() {
  const prompt = customPromptInput.value.trim();
  if (!prompt) return;

  customPromptInput.value = "";
  appendAgentFeedItem({
    title: "User Prompt Dispatched",
    text: prompt,
    tool: "user_dispatch",
    time: new Date().toLocaleTimeString()
  });

  // Extract service or default
  let service = "api-gateway";
  if (prompt.includes("order")) service = "order-service";
  else if (prompt.includes("payment")) service = "payment-service";
  else if (prompt.includes("auth")) service = "auth-service";

  await fetch("/api/triage/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      service_name: service,
      incident_description: prompt,
      role: "oncall"
    })
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
