let currentBatchId = null;
const $ = (id) => document.getElementById(id);
async function api(url, options={}) {
  const response = await fetch(url, options);
  let data = {};
  try { data = await response.json(); } catch (_) {}
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function setMessage(id, message, kind="") {
  const el = $(id); el.textContent = message; el.className = `message ${kind}`;
}
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
async function loadDashboard() {
  try {
    const d = await api("/api/dashboard");
    $("total").textContent = d.total; $("generated").textContent = d.generated;
    $("sent").textContent = d.sent; $("failed").textContent = d.failed;
  } catch (e) { console.error(e); }
}
async function loadTemplates() {
  try {
    const items = await api("/api/templates");
    $("templateList").innerHTML = items.map(t => `
      <div class="template-card">
        <strong>${esc(t.type)}</strong>
        <span class="badge ${t.available ? "valid" : "invalid"}">${t.available ? "Available" : "Missing"}</span>
        <p class="muted">${esc(t.filename)}</p>
        <form class="template-upload" data-type="${esc(t.type)}">
          <input type="file" name="file" accept=".png,.jpg,.jpeg" required>
          <button class="button secondary" type="submit">Replace template</button>
        </form>
      </div>`).join("");
    document.querySelectorAll(".template-upload").forEach(form => form.addEventListener("submit", async e => {
      e.preventDefault();
      const type = form.dataset.type, fd = new FormData(form);
      try {
        await api(`/api/templates/${encodeURIComponent(type)}`, {method:"POST", body:fd});
        await loadTemplates(); alert("Template uploaded.");
      } catch (err) { alert(err.message); }
    }));
  } catch (e) { console.error(e); }
}
function renderPreview(data) {
  $("previewBody").innerHTML = data.rows.map(r => {
    const d = r.data || {};
    const status = r.valid ? '<span class="badge valid">Valid</span>' : `<span class="badge invalid">${esc((r.issues||[]).join("; "))}</span>`;
    return `<tr><td>${r.row_number}</td><td>${esc(d.Name)}</td><td>${esc(d.Email)}</td><td>${esc(d["Event Name"])}</td><td>${esc(d["Certificate Type"])}</td><td>${status}</td></tr>`;
  }).join("");
  $("validationSummary").textContent = `${data.valid_rows} valid · ${data.invalid_rows} invalid · ${data.total_rows} total rows`;
  $("previewWrap").hidden = false;
  $("generateBtn").disabled = data.valid_rows === 0;
}
$("uploadForm").addEventListener("submit", async e => {
  e.preventDefault(); setMessage("uploadMessage", "Uploading and validating spreadsheet…");
  const file = $("spreadsheet").files[0];
  if (!file) return;
  const fd = new FormData(); fd.append("file", file);
  try {
    const data = await api("/api/upload", {method:"POST", body:fd});
    currentBatchId = data.batch_id;
    renderPreview(data);
    setMessage("uploadMessage", "Spreadsheet validated. Review the preview before generating.", "success");
    setMessage("generationMessage", "");
  } catch (err) { setMessage("uploadMessage", err.message, "error"); }
});
$("generateBtn").addEventListener("click", async () => {
  if (!currentBatchId) return;
  $("generateBtn").disabled = true;
  setMessage("generationMessage", "Processing rows, generating PDFs, and attempting email delivery. This may take a while…");
  try {
    const result = await api("/api/generate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({batch_id:currentBatchId})});
    const errors = result.row_errors?.length ? ` Row errors: ${result.row_errors.map(x=>`${x.name}: ${x.error}`).join(" | ")}` : "";
    setMessage("generationMessage", `Complete — ${result.generated} PDFs generated, ${result.emails_sent} emails sent, ${result.emails_failed} email failures, ${result.invalid_rows} invalid rows.${errors}`, "success");
    currentBatchId = null;
    await Promise.all([loadDashboard(), loadCertificates()]);
  } catch (err) { setMessage("generationMessage", err.message, "error"); $("generateBtn").disabled = false; }
});
async function loadCertificates() {
  const params = new URLSearchParams();
  if ($("search").value.trim()) params.set("q", $("search").value.trim());
  if ($("typeFilter").value) params.set("type", $("typeFilter").value);
  try {
    const rows = await api(`/api/certificates?${params}`);
    $("certificatesBody").innerHTML = rows.map(r => {
      const status = String(r.email_status || "Pending").toLowerCase();
      return `<tr><td>${esc(r.participant_name)}</td><td>${esc(r.email)}</td><td>${esc(r.event_name)}</td><td>${esc(r.certificate_type)}</td><td>${esc(r.created_at)}</td><td><span class="badge ${esc(status)}">${esc(r.email_status)}</span></td><td><a class="download-link" href="/api/certificates/${r.id}/download">Download PDF</a></td><td>${r.email_status === "Sent" ? "—" : `<button class="retry" data-id="${r.id}">Retry email</button>`}</td></tr>`;
    }).join("");
    $("emptyState").hidden = rows.length > 0;
    document.querySelectorAll(".retry").forEach(btn => btn.addEventListener("click", async () => {
      btn.disabled = true;
      try { await api(`/api/certificates/${btn.dataset.id}/retry-email`, {method:"POST"}); await Promise.all([loadDashboard(), loadCertificates()]); }
      catch (err) { alert(err.message); btn.disabled = false; }
    }));
  } catch (e) { console.error(e); }
}
$("refreshBtn").addEventListener("click", () => Promise.all([loadDashboard(), loadCertificates(), loadTemplates()]));
$("search").addEventListener("input", () => { clearTimeout(window.searchTimer); window.searchTimer=setTimeout(loadCertificates, 250); });
$("typeFilter").addEventListener("change", loadCertificates);
loadDashboard(); loadCertificates(); loadTemplates();
