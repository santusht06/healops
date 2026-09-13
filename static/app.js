/* HealOps Mission Control: REST and WebSocket client. */

let ws = null;
let reconnectTimer = null;
let reconnectAttempt = 0;
let currentApprovalId = null;
let pollTimer = null;
let activeRequest = false;

const $ = (id) => document.getElementById(id);
const cpuVal = $("cpu-val");
const ramVal = $("ram-val");
const diskVal = $("disk-val");
const redisVal = $("redis-val");
const cpuBar = $("cpu-bar");
const ramBar = $("ram-bar");
const diskBar = $("disk-bar");
const redisBar = $("redis-bar");
const servicesContainer = $("services-container");
const serviceCount = $("service-count");
const auditContainer = $("audit-stream-container");
const postmortemContainer = $("postmortem-container");
const postmortemCount = $("postmortem-count");
const agentFeed = $("agent-feed-container");
const incidentBanner = $("incident-banner");
const bannerTitle = $("banner-title");
const bannerSub = $("banner-sub");
const bannerStage = $("banner-stage");
const agentStatusText = $("agent-status-text");
const agentPulseDot = $("agent-pulse-dot");
const hitlCard = $("hitl-approval-card");
const hitlPromptText = $("hitl-prompt-text");
const hitlTool = $("hitl-tool");
const hitlTarget = $("hitl-target");
const wsIndicator = $("ws-indicator");
const wsStatusText = $("ws-status-text");
const actionStatus = $("action-status");
const promptInput = $("custom-prompt-input");
const injectButton = $("btn-inject-chaos");
const resetButton = $("btn-reset-chaos");
const triageButton = $("btn-manual-triage");
const approveButton = $("btn-hitl-approve");
const denyButton = $("btn-hitl-deny");

const stageCopy = {
  IDLE: { title: "System operational", sub: "Autonomous watcher scanning telemetry every 5s", status: "Agent idle / monitoring", mode: "idle" },
  DETECTED: { title: "Incident detected", sub: "Failure signal received. Preparing investigation.", status: "Incident detected", mode: "alert" },
  INVESTIGATING: { title: "Investigation in progress", sub: "HealOps is collecting evidence and correlating known incidents.", status: "Agent investigating", mode: "active" },
  "AWAITING APPROVAL": { title: "Remediation approval required", sub: "Cedar has paused the proposed critical action.", status: "Cedar gate / sign-off needed", mode: "alert" },
  REMEDIATING: { title: "Remediation in progress", sub: "Approved action is being executed and verified.", status: "Agent remediating", mode: "active" },
  RESOLVED: { title: "Incident resolved", sub: "Service recovery verified. Runbook memory updated.", status: "Agent idle / incident resolved", mode: "idle" },
  ABORTED: { title: "Remediation aborted", sub: "Operator denied the action. Escalation is required.", status: "Remediation denied / escalate", mode: "alert" }
};

window.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  fetchInitialData();
  pollTimer = window.setInterval(fetchTelemetry, 5000);
  $("prompt-form").addEventListener("submit", (event) => {
    event.preventDefault();
    submitCustomPrompt();
  });
  injectButton.addEventListener("click", injectChaos);
  resetButton.addEventListener("click", resetChaos);
  triageButton.addEventListener("click", () => triggerTriage());
  approveButton.addEventListener("click", () => resolveApproval(true));
  denyButton.addEventListener("click", () => resolveApproval(false));
});

function initWebSocket() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${protocol}//${window.location.host}/ws/stream`);
  ws.onopen = () => {
    reconnectAttempt = 0;
    setConnectionState(true);
    if (reconnectTimer) window.clearTimeout(reconnectTimer);
  };
  ws.onmessage = (event) => {
    try { handleLiveEvent(JSON.parse(event.data)); } catch (error) { console.error("[HealOps WS] Parse error", error); }
  };
  ws.onerror = () => setConnectionState(false, "Socket error");
  ws.onclose = () => {
    setConnectionState(false, "Reconnecting...");
    const delay = Math.min(30000, 1000 * (2 ** reconnectAttempt));
    reconnectAttempt += 1;
    reconnectTimer = window.setTimeout(initWebSocket, delay);
  };
}

function setConnectionState(connected, label) {
  wsIndicator.className = `connection-status ${connected ? "connected" : "disconnected"}`;
  wsStatusText.textContent = label || (connected ? "Live socket" : "Socket offline");
}

function handleLiveEvent(message) {
  const data = message.data || {};
  const time = message.timestamp ? message.timestamp.split(" ")[1] : new Date().toLocaleTimeString();
  switch (message.event_type) {
    case "INITIAL_STATE":
      if (data.telemetry) updateTelemetryUI(data.telemetry, data.redis);
      if (data.services) renderServices(data.services);
      if (data.incident) {
        if (data.incident.is_active) setIncidentState(data.incident);
        else resetIncidentUI();
      }
      break;
    case "INCIDENT_TRIGGERED":
      setIncidentState(data);
      appendAgentFeedItem({ title: `Incident detected: ${data.service}`, text: `Symptom: ${data.description}\nAuto-dispatching SRE investigation.`, tool: "health_watcher", time, type: "DETECTION", alert: true });
      fetchServices();
      window.setTimeout(() => triggerTriage(data.service), 800);
      break;
    case "CHAOS_RESET":
      resetIncidentUI();
      fetchServices();
      appendAgentFeedItem({ title: "Topology restored", text: "All cluster services reset to healthy baseline state.", tool: "chaos_reset", time, type: "RECOVERY", resolved: true });
      break;
    case "TRIAGE_STARTED":
      setIncidentStage("INVESTIGATING", data.service);
      break;
    case "AGENT_THOUGHT":
      if ((data.title || "").toLowerCase().includes("aborted")) setIncidentStage("ABORTED");
      appendAgentFeedItem({ title: data.title || "Agent update", text: data.thought, tool: data.tool, time, type: eventTypeForTool(data.tool), alert: (data.title || "").toLowerCase().includes("aborted") });
      break;
    case "APPROVAL_REQUIRED":
      setIncidentStage("AWAITING APPROVAL", data.service_name);
      showHitlApproval(data);
      appendAgentFeedItem({ title: "Cedar policy intervention", text: data.prompt || data.policy, tool: data.tool_name, time, type: "POLICY", intervention: true });
      break;
    case "INCIDENT_RESOLVED":
      setResolvedUI(data);
      appendAgentFeedItem({ title: `Incident healed: ${data.service}`, text: `Remediation verified.\nDetails: ${data.result}\nMTTR: ${data.duration}\nPost-mortem indexed to runbook memory.`, tool: "postmortem_indexer", time, type: "RESOLUTION", resolved: true });
      fetchServices();
      fetchAuditLogs();
      fetchPostmortems();
      break;
    default:
      console.debug("[HealOps WS] Unhandled event", message.event_type);
  }
}

async function fetchInitialData() {
  await Promise.all([fetchHealth(), fetchTelemetry(), fetchServices(), fetchAuditLogs(), fetchPostmortems()]);
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

async function fetchHealth() {
  try {
    const data = await requestJson("/api/health");
    $("model-name").textContent = data.model_provider || "configured provider";
  } catch (error) { console.error("Health fetch error:", error); }
}

async function fetchTelemetry() {
  try {
    const data = await requestJson("/api/telemetry");
    updateTelemetryUI(data.system, data.redis);
    $("telemetry-refresh-time").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch (error) { console.error("Telemetry fetch error:", error); $("telemetry-refresh-time").textContent = "Stale"; }
}

function updateTelemetryUI(system, redis) {
  if (!system) return;
  updateMetric("cpu", system.cpu_percent, "%", system.cpu_percent > 80 ? "CRITICAL" : system.cpu_percent > 70 ? "WARNING" : "HEALTHY");
  updateMetric("ram", system.ram_percent, "%", system.ram_percent > 85 ? "CRITICAL" : system.ram_percent > 70 ? "WARNING" : "HEALTHY");
  updateMetric("disk", system.disk_percent, "%", system.disk_percent > 90 ? "CRITICAL" : "HEALTHY");
  if (redis) {
    const unavailable = ["UNAVAILABLE", "ERROR"].includes(redis.status);
    const value = redis.used_memory_human || (redis.used_memory_mb !== undefined ? `${Number(redis.used_memory_mb).toFixed(2)} MB` : "Unavailable");
    redisVal.textContent = value;
    setMetricHealth("redis", unavailable ? "WARNING" : "HEALTHY");
    const used = Number(redis.used_memory_mb);
    redisBar.style.width = Number.isFinite(used) ? `${Math.min(100, Math.max(3, used / 10))}%` : "0%";
    $("redis-note").textContent = unavailable ? "cache unavailable" : `${redis.total_keys ?? 0} keys observed`;
  }
}

function updateMetric(name, value, suffix, health) {
  if (!Number.isFinite(Number(value))) return;
  $(`${name}-val`).textContent = `${Number(value).toFixed(1)}${suffix}`;
  $(`${name}-bar`).style.width = `${Math.min(100, Math.max(0, Number(value)))}%`;
  setMetricHealth(name, health);
}

function setMetricHealth(name, health) {
  const element = $(`${name}-health`);
  element.textContent = health;
  element.className = `metric-health ${health.toLowerCase()}`;
  const bar = $(`${name}-bar`);
  if (health === "CRITICAL") bar.style.backgroundColor = "var(--red)";
  else if (health === "WARNING") bar.style.backgroundColor = "var(--amber)";
}

async function fetchServices() { try { const data = await requestJson("/api/services"); renderServices(data.services || []); } catch (error) { console.error("Services fetch error:", error); renderMessage(servicesContainer, "Service data unavailable", true); } }
function renderServices(services) {
  servicesContainer.replaceChildren();
  serviceCount.textContent = services.length;
  if (!services.length) { renderMessage(servicesContainer, "No managed services reported"); return; }
  services.forEach((service) => {
    const health = String(service.health || service.status || "unknown");
    const degraded = service.status === "degraded" || health.toLowerCase().includes("502") || health.toLowerCase().includes("critical");
    const item = document.createElement("div"); item.className = `service-item ${degraded ? "degraded" : ""}`;
    const left = document.createElement("div"); left.className = "service-meta-left";
    const dot = document.createElement("span"); dot.className = `service-status-dot ${degraded ? "degraded" : "running"}`; dot.setAttribute("aria-hidden", "true");
    const details = document.createElement("div");
    details.innerHTML = `<div class="service-name"></div><div class="service-meta-sub"></div>`;
    details.querySelector(".service-name").textContent = service.name || "unnamed-service";
    details.querySelector(".service-meta-sub").textContent = `${service.type || service.image || "managed service"} / ${service.port ? `:${service.port}` : service.ports || "port unknown"}`;
    left.append(dot, details);
    const badge = document.createElement("span"); badge.className = `service-badge ${degraded ? "error" : "healthy"}`; badge.textContent = health;
    item.append(left, badge); servicesContainer.appendChild(item);
  });
}

async function fetchAuditLogs() { try { const data = await requestJson("/api/audit?limit=25"); renderAuditLogs(data.audit_logs || []); } catch (error) { console.error("Audit fetch error:", error); renderMessage(auditContainer, "Audit data unavailable", true); } }
function renderAuditLogs(logs) {
  auditContainer.replaceChildren();
  if (!logs.length) { renderMessage(auditContainer, "No audit entries yet"); return; }
  logs.forEach((log) => {
    const item = document.createElement("div"); item.className = "audit-item";
    const header = document.createElement("div"); header.className = "audit-header-row";
    const action = document.createElement("span"); action.className = "audit-action"; action.textContent = log.tool_name || log.action || "unknown_action";
    const decision = document.createElement("span"); decision.className = `audit-decision ${String(log.decision || "other").toLowerCase()}`; decision.textContent = log.decision || "OTHER";
    header.append(action, decision);
    const meta = document.createElement("div"); meta.className = "audit-meta-row";
    const role = document.createElement("span"); role.textContent = `Role: ${log.role || log.caller_role || "oncall"}`;
    const time = document.createElement("time"); time.textContent = formatTime(log.timestamp);
    meta.append(role, time); item.append(header, meta); auditContainer.appendChild(item);
  });
}

async function fetchPostmortems() { try { const data = await requestJson("/api/postmortems"); renderPostmortems(data.postmortems || []); } catch (error) { console.error("Postmortem fetch error:", error); renderMessage(postmortemContainer, "Runbook memory unavailable", true); } }
function renderPostmortems(records) {
  postmortemContainer.replaceChildren(); postmortemCount.textContent = records.length;
  if (!records.length) { renderMessage(postmortemContainer, "No runbooks indexed"); return; }
  records.slice(-4).reverse().forEach((record, index) => {
    const item = document.createElement("article"); item.className = `postmortem-item ${index === 0 ? "latest" : ""}`;
    const header = document.createElement("div"); header.className = "pm-header";
    const id = document.createElement("span"); id.className = "pm-id"; id.textContent = record.id;
    const service = document.createElement("span"); service.className = "pm-service"; service.textContent = `${record.service} / ${record.severity}`;
    header.append(id, service);
    const cause = document.createElement("p"); cause.className = "pm-cause"; cause.append(document.createElement("strong"), document.createTextNode(` ${record.root_cause || "No root cause recorded."}`)); cause.firstChild.textContent = "Root cause:";
    item.append(header, cause); postmortemContainer.appendChild(item);
  });
}

function appendAgentFeedItem({ title, text, tool, time, type = "AGENT", alert = false, intervention = false, resolved = false }) {
  const item = document.createElement("article"); item.className = `agent-step-item ${alert ? "alert" : ""} ${intervention ? "intervention" : ""} ${resolved ? "resolved" : ""}`;
  const marker = document.createElement("div"); marker.className = "step-marker"; marker.textContent = String(agentFeed.children.length + 1).padStart(2, "0");
  const content = document.createElement("div"); content.className = "step-content";
  const meta = document.createElement("div"); meta.className = "step-meta";
  const eventType = document.createElement("span"); eventType.className = "step-type"; eventType.textContent = type;
  const timestamp = document.createElement("time"); timestamp.className = "step-time"; timestamp.textContent = time || "now";
  meta.append(eventType, timestamp);
  const heading = document.createElement("h3"); heading.textContent = title;
  const paragraph = document.createElement("p"); paragraph.textContent = text || "";
  content.append(meta, heading, paragraph);
  if (tool) { const badge = document.createElement("span"); badge.className = "step-tool-badge"; badge.textContent = `tool: ${tool}`; content.appendChild(badge); }
  item.append(marker, content); const nearBottom = agentFeed.scrollHeight - agentFeed.scrollTop - agentFeed.clientHeight < 80; agentFeed.appendChild(item); if (nearBottom) agentFeed.scrollTop = agentFeed.scrollHeight;
}

function eventTypeForTool(tool) { if (tool === "lookup_past_incidents") return "CORRELATION"; if (tool === "inspect_service_logs" || tool === "get_system_telemetry") return "DIAGNOSTIC"; if (tool === "restart_service") return "REMEDIATION"; return "AGENT"; }
function setIncidentState(incident) { setIncidentStage(incident.stage || "DETECTED", incident.service); const copy = stageCopy[incident.stage] || stageCopy.DETECTED; bannerSub.textContent = incident.description || copy.sub; }
function setIncidentStage(stage, service) { const normalized = String(stage || "IDLE").toUpperCase(); const copy = stageCopy[normalized] || stageCopy.IDLE; incidentBanner.className = `incident-banner ${normalized === "IDLE" || normalized === "RESOLVED" ? "banner-idle" : "banner-incident"} stage-${normalized.toLowerCase().replaceAll(" ", "-")}`; bannerTitle.textContent = service && normalized !== "IDLE" && normalized !== "RESOLVED" ? `${copy.title}: ${service}` : copy.title; bannerSub.textContent = copy.sub; bannerStage.textContent = normalized; agentStatusText.textContent = copy.status; agentPulseDot.className = `pulse-dot ${copy.mode}`; }
function resetIncidentUI() { currentApprovalId = null; hitlCard.classList.add("hidden"); setIncidentStage("IDLE"); }
function setResolvedUI(data) { currentApprovalId = null; hitlCard.classList.add("hidden"); setIncidentStage("RESOLVED", data.service); bannerSub.textContent = `Auto-healed in ${data.duration || "the recovery window"}. System running normally.`; }
function showHitlApproval(data) { currentApprovalId = data.approval_id; hitlTool.textContent = data.tool_name || "restart_service"; hitlTarget.textContent = data.service_name || "target"; hitlPromptText.textContent = data.prompt || data.policy || "Critical remediation requires operator approval."; hitlCard.classList.remove("hidden"); approveButton.focus(); }

async function resolveApproval(approved) { if (!currentApprovalId || activeRequest) return; const approvalId = currentApprovalId; setBusy([approveButton, denyButton], true); try { await requestJson("/api/remediation/decide", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: approvalId, approved }) }); hitlCard.classList.add("hidden"); appendAgentFeedItem({ title: approved ? "Operator approved remediation" : "Operator denied remediation", text: approved ? "Cedar authorization confirmed. Agent proceeding." : "Authorization denied. Agent escalated to on-call.", tool: "cedar_guard", time: new Date().toLocaleTimeString(), type: "POLICY", intervention: true, alert: !approved }); if (!approved) setIncidentStage("ABORTED"); } catch (error) { actionStatus.textContent = `Decision failed: ${error.message}`; actionStatus.className = "action-status error"; } finally { setBusy([approveButton, denyButton], false); } }
async function injectChaos() { if (activeRequest) return; appendAgentFeedItem({ title: "Chaos drill armed", text: "Injecting simulated HTTP 502 failure into api-gateway.", tool: "chaos_injector", time: new Date().toLocaleTimeString(), type: "DETECTION", alert: true }); await performAction("/api/chaos/inject", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ service_name: "api-gateway", failure_type: "502_bad_gateway" }) }, "Outage injected"); }
async function resetChaos() { await performAction("/api/chaos/reset", { method: "POST" }, "Healthy baseline restored"); }
async function triggerTriage(serviceName = "api-gateway") { if (activeRequest) return; try { await requestJson("/api/triage/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ service_name: serviceName, role: "oncall" }) }); } catch (error) { actionStatus.textContent = `Triage failed: ${error.message}`; actionStatus.className = "action-status error"; } }
async function submitCustomPrompt() { const prompt = promptInput.value.trim(); if (!prompt || activeRequest) return; promptInput.value = ""; appendAgentFeedItem({ title: "Operator prompt dispatched", text: prompt, tool: "user_dispatch", time: new Date().toLocaleTimeString(), type: "OPERATOR" }); let service = "api-gateway"; const lower = prompt.toLowerCase(); if (lower.includes("order")) service = "order-service"; else if (lower.includes("payment")) service = "payment-service"; else if (lower.includes("auth")) service = "auth-service"; try { await requestJson("/api/triage/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ service_name: service, incident_description: prompt, role: "oncall" }) }); } catch (error) { actionStatus.textContent = `Prompt dispatch failed: ${error.message}`; actionStatus.className = "action-status error"; } }
async function performAction(url, options, successMessage) { activeRequest = true; setBusy([injectButton, resetButton, triageButton], true); try { await requestJson(url, options); actionStatus.textContent = successMessage; actionStatus.className = "action-status"; } catch (error) { actionStatus.textContent = `Action failed: ${error.message}`; actionStatus.className = "action-status error"; } finally { activeRequest = false; setBusy([injectButton, resetButton, triageButton], false); } }
function setBusy(elements, busy) { elements.forEach((element) => { element.disabled = busy; }); }
function renderMessage(container, message, error = false) { container.replaceChildren(); const element = document.createElement("div"); element.className = `loading-placeholder ${error ? "error" : ""}`; element.textContent = message; container.appendChild(element); }
function formatTime(value) { if (!value) return ""; return value.includes("T") ? value.split("T")[1].replace("Z", "") : value; }
