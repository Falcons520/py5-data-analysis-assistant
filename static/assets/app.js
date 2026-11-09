(function () {
  "use strict";

  const state = {
    dataset: null,
    jobId: null,
    timer: null,
    running: false,
    result: null,
  };

  const $ = (id) => document.getElementById(id);
  const MAX_UPLOAD_MB = 25;
  const DOWNLOAD_META = {
    markdown: { icon: "MD", title: "Markdown", desc: "完整文本报告", suffix: "_分析报告.md" },
    word: { icon: "DOC", title: "Word 文档", desc: "结构化排版 + 图表", suffix: "_报告.docx" },
    excel: { icon: "XLS", title: "Excel 附件", desc: "清洗后数据 + 统计", suffix: "_数据附件.xlsx" },
    summary: { icon: "TXT", title: "文本摘要", desc: "100 字核心结论", suffix: "_摘要.txt" },
  };

  // ── 访问口令 ──────────────────────────────────────────────────────

  const TOKEN_KEY = "analysis_access_token";
  let accessToken = localStorage.getItem(TOKEN_KEY) || "";

  function setToken(value) {
    accessToken = (value || "").trim();
    if (accessToken) {
      localStorage.setItem(TOKEN_KEY, accessToken);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  function withToken(url) {
    if (!accessToken || !url) return url;
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}token=${encodeURIComponent(accessToken)}`;
  }

  function showGate(message) {
    const gate = $("gate");
    show(gate);
    if (message) setStatus("gateStatus", message, "err");
    $("gateInput").value = "";
    window.setTimeout(() => $("gateInput").focus(), 60);
  }

  // ── 通用工具 ──────────────────────────────────────────────────────

  async function api(path, options) {
    const opts = Object.assign({}, options || {});
    const headers = new Headers(opts.headers || {});
    if (accessToken) headers.set("X-Access-Token", accessToken);
    opts.headers = headers;

    const response = await fetch(path, opts);
    const type = response.headers.get("content-type") || "";
    const payload = type.includes("application/json")
      ? await response.json().catch(() => null)
      : null;

    if (response.status === 401) {
      setToken("");
      showGate("口令无效或已失效，请重新输入");
      throw new Error("需要访问口令");
    }

    if (!response.ok) {
      const detail = payload && (payload.detail || payload.message);
      const message = typeof detail === "string" ? detail : `请求失败（HTTP ${response.status}）`;
      throw new Error(message);
    }
    return payload;
  }

  function show(el) {
    el.classList.remove("hidden");
  }

  function hide(el) {
    el.classList.add("hidden");
  }

  function setStatus(id, text, kind) {
    const el = $(id);
    el.textContent = text || "";
    el.className = "status-text" + (kind ? " " + kind : "");
  }

  let toastTimer = null;
  function toast(message, isError) {
    const el = $("toast");
    el.textContent = message;
    el.className = "toast show" + (isError ? " err" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.className = "toast";
    }, isError ? 6000 : 3000);
  }

  function sanitizeFragment(html) {
    const template = document.createElement("template");
    template.innerHTML = html || "";
    template.content
      .querySelectorAll("script, iframe, object, embed, link, meta, style, form, base")
      .forEach((node) => node.remove());
    template.content.querySelectorAll("*").forEach((el) => {
      Array.from(el.attributes).forEach((attr) => {
        const name = attr.name.toLowerCase();
        const value = (attr.value || "").trim().toLowerCase();
        const dangerousUrl =
          (name === "href" || name === "src") &&
          /^(javascript|vbscript|data:text\/html)/.test(value);
        if (name.startsWith("on") || dangerousUrl) {
          el.removeAttribute(attr.name);
        }
      });
    });
    return template.content;
  }

  function renderHtml(target, html, emptyText) {
    target.replaceChildren();
    if (!html) {
      const tip = document.createElement("p");
      tip.className = "empty";
      tip.textContent = emptyText;
      target.appendChild(tip);
      return;
    }
    target.appendChild(sanitizeFragment(html));
  }

  // ── 健康检查 ──────────────────────────────────────────────────────

  async function checkHealth() {
    const pill = $("healthPill");
    try {
      const data = await api("/api/health");
      if (data.key_configured) {
        pill.textContent = `服务在线 · ${data.model}`;
        pill.className = "pill ok";
      } else {
        pill.textContent = "服务在线 · 未配置 API Key";
        pill.className = "pill warn";
      }
    } catch (err) {
      pill.textContent = "服务不可用";
      pill.className = "pill warn";
    }
  }

  // ── 数据集渲染 ────────────────────────────────────────────────────

  function renderPreview(columns, rows) {
    const table = $("previewTable");
    const thead = table.querySelector("thead");
    const tbody = table.querySelector("tbody");
    thead.replaceChildren();
    tbody.replaceChildren();

    const headRow = document.createElement("tr");
    columns.forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        if (typeof cell === "number") {
          td.className = "num";
          td.textContent = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 4 }).format(cell);
        } else {
          td.textContent = cell === null || cell === undefined ? "" : String(cell);
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  function applyDataset(payload, previewHint) {
    state.dataset = payload.dataset;
    const ds = payload.dataset;

    $("dsName").textContent = ds.name;
    const cleanedInfo = ds.cleaned ? ` · 已清洗（${ds.cleaned_rows} 行）` : "";
    $("dsMeta").textContent = `${ds.rows} 行 × ${ds.cols} 列${cleanedInfo}`;
    $("previewHint").textContent = previewHint || "仅展示前 10 行";

    renderPreview(ds.columns, payload.preview || []);

    show($("cardDataset"));
    show($("cardQuery"));
    hide($("cardProgress"));
    hide($("cardResult"));

    if (ds.cleaning_report) {
      $("cleanReport").textContent = ds.cleaning_report;
      show($("cleanReport"));
    } else {
      hide($("cleanReport"));
    }
    setStatus("cleanStatus", "");
  }

  async function uploadFile(file) {
    if (!file) return;
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      toast(`文件超过 ${MAX_UPLOAD_MB}MB，请先精简数据`, true);
      return;
    }

    setStatus("uploadStatus", "正在上传并解析…");
    try {
      const form = new FormData();
      form.append("file", file);
      const payload = await api("/api/datasets", { method: "POST", body: form });
      applyDataset(payload);
      setStatus("uploadStatus", `已载入 ${file.name}`, "ok");
      toast("数据已就绪，可以开始清洗或直接分析");
      $("cardDataset").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setStatus("uploadStatus", err.message, "err");
      toast(err.message, true);
    } finally {
      $("fileInput").value = "";
    }
  }

  async function loadDemo() {
    setStatus("uploadStatus", "正在载入示例数据…");
    try {
      const payload = await api("/api/datasets/demo", { method: "POST" });
      applyDataset(payload, "示例数据 · 仅展示前 10 行");
      setStatus("uploadStatus", "已载入示例数据 lesson_data.csv", "ok");
      $("cardDataset").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      setStatus("uploadStatus", err.message, "err");
      toast(err.message, true);
    }
  }

  // ── 数据清洗 ──────────────────────────────────────────────────────

  async function runCleaning() {
    if (!state.dataset) {
      toast("请先上传数据", true);
      return;
    }
    const button = $("cleanBtn");
    button.disabled = true;
    setStatus("cleanStatus", "正在清洗…");

    try {
      const payload = await api(`/api/datasets/${state.dataset.id}/clean`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fill_strategy: $("fillStrategy").value,
          outlier_method: $("outlierMethod").value,
          remove_duplicates: $("removeDup").checked,
        }),
      });

      state.dataset.cleaned = true;
      state.dataset.cleaned_rows = payload.rows;
      state.dataset.cleaning_report = payload.report;

      $("dsMeta").textContent = `${state.dataset.rows} 行 × ${state.dataset.cols} 列 · 已清洗（${payload.rows} 行）`;
      $("previewHint").textContent = "以下为清洗后的前 10 行";
      renderPreview(payload.columns, payload.preview);

      $("cleanReport").textContent = payload.report;
      show($("cleanReport"));
      setStatus("cleanStatus", `清洗完成，保留 ${payload.rows} 行`, "ok");
      toast("数据清洗完成，后续分析将使用清洗后的数据");
    } catch (err) {
      setStatus("cleanStatus", err.message, "err");
      toast(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  // ── 分析任务 ──────────────────────────────────────────────────────

  function updateProgress(percent, stage) {
    const value = Math.max(0, Math.min(100, Number(percent) || 0));
    $("progressBar").style.width = value + "%";
    $("progressPct").textContent = value + "%";
    $("stageText").textContent = stage || "分析中…";
  }

  async function startAnalysis() {
    if (!state.dataset) {
      toast("请先上传数据", true);
      return;
    }
    const query = $("queryInput").value.trim();
    if (!query) {
      toast("请先描述你的分析需求", true);
      $("queryInput").focus();
      return;
    }
    if (state.running) return;

    state.running = true;
    $("analyzeBtn").disabled = true;
    $("analyzeBtn").textContent = "分析中…";
    setStatus("analyzeStatus", "");
    hide($("cardResult"));
    show($("cardProgress"));
    updateProgress(1, "正在创建分析任务…");
    $("cardProgress").scrollIntoView({ behavior: "smooth", block: "center" });

    try {
      const payload = await api("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataset_id: state.dataset.id, query }),
      });
      state.jobId = payload.job_id;
      pollJob();
    } catch (err) {
      finishRunning();
      hide($("cardProgress"));
      setStatus("analyzeStatus", err.message, "err");
      toast(err.message, true);
    }
  }

  function pollJob() {
    clearTimeout(state.timer);
    state.timer = setTimeout(async () => {
      try {
        const payload = await api(`/api/jobs/${state.jobId}`);
        updateProgress(payload.progress, payload.stage);

        if (payload.status === "succeeded" && payload.result) {
          finishRunning();
          renderResult(payload.result);
          return;
        }
        if (payload.status === "failed") {
          finishRunning();
          hide($("cardProgress"));
          setStatus("analyzeStatus", payload.error || "分析失败", "err");
          toast(payload.error || "分析失败，请重试", true);
          return;
        }
        pollJob();
      } catch (err) {
        finishRunning();
        hide($("cardProgress"));
        setStatus("analyzeStatus", err.message, "err");
        toast(err.message, true);
      }
    }, 1200);
  }

  function finishRunning() {
    clearTimeout(state.timer);
    state.timer = null;
    state.running = false;
    $("analyzeBtn").disabled = false;
    $("analyzeBtn").textContent = "开始分析";
  }

  // ── 结果渲染 ──────────────────────────────────────────────────────

  function renderCharts(result) {
    const list = $("chartList");
    list.replaceChildren();

    const urls = result.chart_urls || [];
    if (!urls.length) {
      const tip = document.createElement("p");
      tip.className = "hint";
      tip.textContent = "本次分析未生成图表，可在需求中明确指定图表类型后重试。";
      list.appendChild(tip);
      return;
    }

    urls.forEach((url, index) => {
      const figure = document.createElement("figure");
      const img = document.createElement("img");
      img.src = withToken(url);
      img.alt = `分析图表 ${index + 1}`;
      img.loading = "lazy";
      figure.appendChild(img);
      list.appendChild(figure);
    });
  }

  function renderDownloads(result) {
    const box = $("downloads");
    box.replaceChildren();
    const downloads = result.downloads || {};

    Object.keys(DOWNLOAD_META).forEach((kind) => {
      if (!downloads[kind]) return;
      const meta = DOWNLOAD_META[kind];
      const link = document.createElement("a");
      link.className = "download-card";
      link.href = withToken(downloads[kind]);
      link.setAttribute("download", "");

      const icon = document.createElement("span");
      icon.className = "download-icon";
      icon.textContent = meta.icon;

      const text = document.createElement("span");
      text.className = "download-meta";
      const title = document.createElement("strong");
      title.textContent = meta.title;
      const desc = document.createElement("span");
      desc.textContent = meta.desc;
      text.append(title, desc);

      link.append(icon, text);
      box.appendChild(link);
    });
  }

  function renderResult(result) {
    state.result = result;
    hide($("cardProgress"));
    show($("cardResult"));

    $("shortSummary").textContent = result.short_summary || "未生成摘要";

    const summaryBox = $("analysisSummary");
    summaryBox.textContent = result.analysis_summary || "";

    renderCharts(result);
    renderHtml($("reportBody"), result.report_html, "本次未生成详细报告。");
    renderHtml($("cleaningBody"), result.cleaning_report, "本次分析未执行数据清洗。");
    renderDownloads(result);

    setStatus("analyzeStatus", "分析完成", "ok");
    setStatus("emailStatus", "");
    switchTab("charts");

    $("cardResult").scrollIntoView({ behavior: "smooth", block: "start" });
    toast("分析完成，可查看图表或下载报告");
  }

  function switchTab(name) {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.classList.toggle("active", tab.dataset.tab === name);
    });
    ["charts", "report", "cleaning"].forEach((key) => {
      const panel = $("tab" + key.charAt(0).toUpperCase() + key.slice(1));
      panel.classList.toggle("hidden", key !== name);
    });
  }

  // ── 邮件 ──────────────────────────────────────────────────────────

  async function sendEmail() {
    if (!state.jobId) {
      toast("请先完成一次分析", true);
      return;
    }
    const sender = $("emailSender").value.trim();
    const authCode = $("emailAuth").value.trim();
    const receiver = $("emailReceiver").value.trim();

    if (!sender || !authCode || !receiver) {
      toast("请填写发件邮箱、授权码和收件邮箱", true);
      return;
    }

    const button = $("emailBtn");
    button.disabled = true;
    setStatus("emailStatus", "正在发送…");

    try {
      const payload = await api(`/api/jobs/${state.jobId}/email`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sender, auth_code: authCode, receiver }),
      });
      setStatus("emailStatus", `已发送至 ${payload.receiver}`, "ok");
      toast("邮件发送成功");
      $("emailAuth").value = "";
    } catch (err) {
      setStatus("emailStatus", err.message, "err");
      toast(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  // ── 口令校验 ──────────────────────────────────────────────────────

  async function bootstrapGate() {
    let health = null;
    try {
      health = await api("/api/health");
    } catch (err) {
      health = null;
    }

    if (!health || !health.auth_required) {
      hide($("gate"));
      checkHealth();
      return;
    }

    if (!accessToken) {
      showGate();
      checkHealth();
      return;
    }

    try {
      await api("/api/auth");
      hide($("gate"));
    } catch (err) {
      setToken("");
      showGate("口令无效或已失效，请重新输入");
    }
    checkHealth();
  }

  async function submitGate(event) {
    event.preventDefault();
    const value = $("gateInput").value.trim();
    if (!value) return;

    const button = $("gateBtn");
    button.disabled = true;
    setStatus("gateStatus", "校验中…");
    setToken(value);

    try {
      await api("/api/auth");
      hide($("gate"));
      setStatus("gateStatus", "");
      toast("验证通过");
      checkHealth();
    } catch (err) {
      setToken("");
      setStatus("gateStatus", "口令不正确，请重新输入", "err");
    } finally {
      button.disabled = false;
    }
  }

  // ── 事件绑定 ──────────────────────────────────────────────────────

  function bindEvents() {
    const dropzone = $("dropzone");
    const fileInput = $("fileInput");

    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });

    ["dragenter", "dragover"].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((type) => {
      dropzone.addEventListener(type, (event) => {
        event.preventDefault();
        dropzone.classList.remove("dragover");
      });
    });

    dropzone.addEventListener("drop", (event) => {
      const file = event.dataTransfer && event.dataTransfer.files[0];
      uploadFile(file);
    });

    fileInput.addEventListener("change", () => uploadFile(fileInput.files[0]));

    $("demoBtn").addEventListener("click", loadDemo);
    $("cleanBtn").addEventListener("click", runCleaning);
    $("analyzeBtn").addEventListener("click", startAnalysis);
    $("emailBtn").addEventListener("click", sendEmail);
    $("gateForm").addEventListener("submit", submitGate);

    $("queryChips").addEventListener("click", (event) => {
      const button = event.target.closest("button[data-q]");
      if (!button) return;
      $("queryInput").value = button.dataset.q;
      $("queryInput").focus();
    });

    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchTab(tab.dataset.tab));
    });

    $("queryInput").addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        startAnalysis();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    bindEvents();
    bootstrapGate();
  });
})();
