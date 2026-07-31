(() => {
  "use strict";

  const config = window.REELSCOPE_CONFIG || { engine: "CPU", maxUpload: "Unlimited" };
  const $ = (id) => document.getElementById(id);

  const elements = {
    body: document.body,
    historyPanel: $("historyPanel"),
    inspectorPanel: $("inspectorPanel"),
    historyList: $("historyList"),
    historyEmpty: $("historyEmpty"),
    historyCount: $("historyCount"),
    search: $("jobSearch"),
    fileInput: $("fileInput"),
    dropZone: $("dropZone"),
    emptyState: $("emptyState"),
    carouselView: $("carouselView"),
    gridView: $("gridView"),
    carouselViewButton: $("carouselViewButton"),
    gridViewButton: $("gridViewButton"),
    frameGrid: $("frameGrid"),
    loadMoreFrames: $("loadMoreFrames"),
    viewerTitle: $("viewerTitle"),
    viewerEyebrow: $("viewerEyebrow"),
    viewerMeta: $("viewerMeta"),
    stateBadge: $("stateBadge"),
    mediaStage: $("mediaStage"),
    primaryCard: $("primaryCard"),
    primaryImage: $("primaryImage"),
    previousCard: $("previousCard"),
    previousImage: $("previousImage"),
    previousFrame: $("previousFrame"),
    nextCard: $("nextCard"),
    nextImage: $("nextImage"),
    nextFrame: $("nextFrame"),
    timestampPill: $("timestampPill"),
    scrub: $("scrub"),
    timelineStart: $("timelineStart"),
    timelineCurrent: $("timelineCurrent"),
    timelineEnd: $("timelineEnd"),
    filmstrip: $("filmstrip"),
    frameReadout: $("frameReadout"),
    filenameReadout: $("filenameReadout"),
    playFrames: $("playFrames"),
    sourceName: $("sourceName"),
    sourceDimensions: $("sourceDimensions"),
    sourceFrameCount: $("sourceFrameCount"),
    sourceFps: $("sourceFps"),
    sourceDate: $("sourceDate"),
    extractRate: $("extractRate"),
    imageExt: $("imageExt"),
    zipSampleRate: $("zipSampleRate"),
    downloadCurrent: $("downloadCurrent"),
    downloadZip: $("downloadZip"),
    statusText: $("statusText"),
    statusDetail: $("statusDetail"),
    statusSection: $("statusSection"),
    progressTrack: $("progressTrack"),
    progressBar: $("progressBar"),
    progressLabel: $("progressLabel"),
    drawerBackdrop: $("drawerBackdrop"),
    toastRegion: $("toastRegion"),
  };

  const state = {
    jobs: [],
    currentJob: null,
    currentJobId: null,
    frames: [],
    index: 0,
    viewMode: "carousel",
    gridLimit: 80,
    searchTerm: "",
    polling: false,
    playTimer: null,
  };

  function icon(name) {
    const span = document.createElement("span");
    span.className = "material-symbols-rounded";
    span.setAttribute("aria-hidden", "true");
    span.textContent = name;
    return span;
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  function frameUrl(jobId, filename) {
    return `/jobs/${encodeURIComponent(jobId)}/frames/${encodeURIComponent(filename)}`;
  }

  function formatNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? new Intl.NumberFormat().format(parsed) : "—";
  }

  function formatDate(value, includeTime = false) {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    const options = includeTime
      ? { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }
      : { month: "short", day: "numeric", year: "numeric" };
    return new Intl.DateTimeFormat(undefined, options).format(date);
  }

  function relativeDateLabel(value) {
    if (!value) return "Recent";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Recent";
    const today = new Date();
    const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    const startDate = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const days = Math.round((startToday - startDate) / 86400000);
    if (days === 0) return "Today";
    if (days === 1) return "Yesterday";
    if (days < 7) return "This week";
    return new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(date);
  }

  function timestampFromFilename(filename) {
    const stem = String(filename || "").replace(/\.[^.]+$/, "");
    const match = stem.match(/_(\d{2})-(\d{2})-(\d{2}\.\d{3})$/);
    if (!match) return null;
    return `${match[1]}:${match[2]}:${match[3]}`;
  }

  function shortTimestamp(filename) {
    const full = timestampFromFilename(filename);
    if (!full) return "—";
    const match = full.match(/^\d{2}:(\d{2}):(\d{2})/);
    return match ? `${match[1]}:${match[2]}` : full;
  }

  function endTimestamp() {
    if (!state.frames.length) return "00:00:00";
    const timestamp = timestampFromFilename(state.frames[state.frames.length - 1]);
    if (timestamp) return timestamp.slice(0, 8);
    const fps = Number(state.currentJob?.source_fps || 0);
    if (!fps) return "00:00:00";
    const seconds = Math.floor(state.frames.length / fps);
    const hours = String(Math.floor(seconds / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, "0");
    const secs = String(seconds % 60).padStart(2, "0");
    return `${hours}:${minutes}:${secs}`;
  }

  function showToast(message, tone = "info") {
    const toast = document.createElement("div");
    toast.className = `toast${tone === "error" ? " is-error" : ""}`;
    toast.appendChild(icon(tone === "error" ? "info" : "check_circle"));
    const copy = document.createElement("span");
    copy.textContent = message;
    toast.appendChild(copy);
    elements.toastRegion.appendChild(toast);
    window.setTimeout(() => toast.remove(), 4200);
  }

  function setStatus(title, detail, tone = "neutral") {
    elements.statusText.textContent = title;
    elements.statusDetail.textContent = detail;
    elements.statusSection.dataset.tone = tone;
    elements.stateBadge.textContent = title;
    elements.stateBadge.className = "state-badge";
    if (tone === "running") elements.stateBadge.classList.add("is-running");
    if (tone === "done") elements.stateBadge.classList.add("is-done");
    if (tone === "error") elements.stateBadge.classList.add("is-error");
  }

  function setProgress(written, expected) {
    const hasProgress = Number(written) > 0 || Number(expected) > 0;
    elements.progressTrack.classList.toggle("is-hidden", !hasProgress);
    elements.progressLabel.classList.toggle("is-hidden", !hasProgress);
    const safeWritten = Number(written) || 0;
    const safeExpected = Number(expected) || 0;
    const percent = safeExpected ? Math.min(100, Math.round((safeWritten / safeExpected) * 100)) : 6;
    elements.progressBar.style.width = `${percent}%`;
    elements.progressLabel.textContent = safeExpected ? `${formatNumber(safeWritten)} / ${formatNumber(safeExpected)}` : `${formatNumber(safeWritten)} / ?`;
  }

  function clearProgress() {
    elements.progressTrack.classList.add("is-hidden");
    elements.progressLabel.classList.add("is-hidden");
    elements.progressBar.style.width = "0%";
  }

  function applyTheme(theme) {
    const normalized = theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = normalized;
    localStorage.setItem("reelscope-theme", normalized);
    const themeButton = $("themeToggle");
    themeButton.setAttribute("aria-label", normalized === "dark" ? "Switch to light mode" : "Switch to dark mode");
  }

  function toggleTheme() {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  }

  function initializeTheme() {
    const stored = localStorage.getItem("reelscope-theme");
    const preferred = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    applyTheme(stored || preferred);
  }

  function openDrawer(panel) {
    elements.historyPanel.classList.toggle("is-open", panel === "history");
    elements.inspectorPanel.classList.toggle("is-open", panel === "inspector");
    elements.drawerBackdrop.classList.remove("is-hidden");
  }

  function closeDrawers() {
    elements.historyPanel.classList.remove("is-open");
    elements.inspectorPanel.classList.remove("is-open");
    elements.drawerBackdrop.classList.add("is-hidden");
  }

  function historyCard(job) {
    const button = document.createElement("button");
    button.className = `history-card${job.id === state.currentJobId ? " is-selected" : ""}`;
    button.type = "button";
    button.dataset.jobId = job.id;

    const thumb = document.createElement("span");
    thumb.className = "history-thumbnail";
    if (job.thumbnail) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      img.src = frameUrl(job.id, job.thumbnail);
      thumb.appendChild(img);
    } else {
      thumb.appendChild(icon(job.state === "running" || job.state === "queued" ? "refresh" : "image"));
    }

    const copy = document.createElement("span");
    copy.className = "history-card-copy";
    const title = document.createElement("strong");
    title.textContent = job.filename || "Untitled video";
    const details = document.createElement("span");
    details.textContent = `${formatNumber(job.frames_count)} frames`;
    const date = document.createElement("span");
    date.textContent = formatDate(job.created_utc, true);
    copy.append(title, details, date);

    const status = document.createElement("span");
    status.className = `history-card-state is-${job.state}`;
    status.title = job.state;
    button.append(thumb, copy, status);
    button.addEventListener("click", () => {
      openJob(job.id);
      closeDrawers();
    });
    return button;
  }

  function renderHistory() {
    const term = state.searchTerm.trim().toLowerCase();
    const filtered = state.jobs.filter((job) => !term || String(job.filename || "").toLowerCase().includes(term));
    elements.historyList.replaceChildren();
    elements.historyEmpty.classList.toggle("is-hidden", filtered.length > 0);
    elements.historyCount.textContent = `${filtered.length} saved ${filtered.length === 1 ? "job" : "jobs"}`;
    if (!filtered.length) return;

    let lastGroup = null;
    filtered.forEach((job) => {
      const group = job.state === "running" || job.state === "queued" ? "Active" : relativeDateLabel(job.created_utc);
      if (group !== lastGroup) {
        const label = document.createElement("div");
        label.className = "history-group-label";
        label.textContent = group;
        elements.historyList.appendChild(label);
        lastGroup = group;
      }
      elements.historyList.appendChild(historyCard(job));
    });
  }

  async function refreshHistory(selectNewest = false) {
    try {
      const payload = await fetchJson("/api/jobs");
      state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      renderHistory();
      if ((selectNewest || !state.currentJobId) && state.jobs.length) {
        await openJob(state.jobs[0].id);
      }
    } catch (error) {
      showToast(`History unavailable: ${error.message}`, "error");
    }
  }

  function updateJobInHistory(job) {
    const index = state.jobs.findIndex((item) => item.id === job.id);
    if (index >= 0) state.jobs[index] = { ...state.jobs[index], ...job };
    else state.jobs.unshift(job);
    state.jobs.sort((a, b) => String(b.created_utc).localeCompare(String(a.created_utc)));
    renderHistory();
  }

  function currentFrameUrl(index = state.index) {
    const filename = state.frames[index];
    if (!state.currentJobId || !filename) return "";
    return frameUrl(state.currentJobId, filename);
  }

  function setImage(element, card, index) {
    if (index < 0 || index >= state.frames.length) {
      element.removeAttribute("src");
      card.classList.add("is-hidden");
      return;
    }
    card.classList.remove("is-hidden");
    element.src = currentFrameUrl(index);
  }

  function updateFrameRatio() {
    const width = elements.primaryImage.naturalWidth;
    const height = elements.primaryImage.naturalHeight;
    if (!width || !height) return;
    const ratio = width / height;
    const stageBounds = elements.mediaStage.getBoundingClientRect();
    const maxWidth = stageBounds.width * (window.innerWidth <= 700 ? 0.46 : 0.50);
    const maxHeight = Math.max(180, stageBounds.height - 20);
    let cardWidth = Math.min(maxWidth, maxHeight * ratio);
    let cardHeight = cardWidth / ratio;
    if (cardHeight > maxHeight) {
      cardHeight = maxHeight;
      cardWidth = cardHeight * ratio;
    }
    elements.primaryCard.style.setProperty("--frame-ratio", String(ratio));
    elements.primaryCard.style.width = `${Math.round(cardWidth)}px`;
    elements.primaryCard.style.height = `${Math.round(cardHeight)}px`;
    elements.primaryCard.dataset.ratio = ratio < 0.86 ? "portrait" : ratio > 1.72 ? "wide" : "standard";
  }

  function filmstripWindowSize() {
    if (window.innerWidth <= 700) return 5;
    if (window.innerWidth <= 1220) return 7;
    return 9;
  }

  function renderFilmstrip() {
    elements.filmstrip.replaceChildren();
    const count = filmstripWindowSize();
    const half = Math.floor(count / 2);
    const maxStart = Math.max(0, state.frames.length - count);
    const start = Math.max(0, Math.min(state.index - half, maxStart));
    const end = Math.min(state.frames.length, start + count);
    for (let i = start; i < end; i += 1) {
      const button = document.createElement("button");
      button.className = `filmstrip-item${i === state.index ? " is-selected" : ""}`;
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", i === state.index ? "true" : "false");
      button.setAttribute("aria-label", `Frame ${i + 1}`);
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      img.src = currentFrameUrl(i);
      const label = document.createElement("span");
      label.textContent = shortTimestamp(state.frames[i]) || String(i + 1);
      button.append(img, label);
      button.addEventListener("click", () => goToFrame(i));
      elements.filmstrip.appendChild(button);
    }
  }

  function renderCurrentFrame() {
    if (!state.frames.length) return;
    state.index = Math.max(0, Math.min(state.index, state.frames.length - 1));
    setImage(elements.previousImage, elements.previousCard, state.index - 1);
    setImage(elements.primaryImage, elements.primaryCard, state.index);
    setImage(elements.nextImage, elements.nextCard, state.index + 1);
    const filename = state.frames[state.index];
    const timestamp = timestampFromFilename(filename) || `Frame ${state.index + 1}`;
    elements.timestampPill.textContent = timestamp;
    elements.timelineCurrent.textContent = timestamp;
    elements.timelineEnd.textContent = endTimestamp();
    elements.scrub.max = String(Math.max(0, state.frames.length - 1));
    elements.scrub.value = String(state.index);
    elements.frameReadout.textContent = `${formatNumber(state.index + 1)} / ${formatNumber(state.frames.length)}`;
    elements.filenameReadout.textContent = filename;
    elements.previousFrame.disabled = state.index === 0;
    elements.nextFrame.disabled = state.index === state.frames.length - 1;
    $("firstFrame").disabled = state.index === 0;
    $("lastFrame").disabled = state.index === state.frames.length - 1;
    renderFilmstrip();
  }

  function goToFrame(index) {
    if (!state.frames.length) return;
    state.index = Math.max(0, Math.min(Number(index) || 0, state.frames.length - 1));
    renderCurrentFrame();
  }

  function stopPlayback() {
    if (state.playTimer) window.clearInterval(state.playTimer);
    state.playTimer = null;
    elements.playFrames.replaceChildren(icon("play_arrow"));
    elements.playFrames.setAttribute("aria-label", "Play frames");
  }

  function togglePlayback() {
    if (state.playTimer) {
      stopPlayback();
      return;
    }
    if (!state.frames.length) return;
    elements.playFrames.replaceChildren(icon("pause"));
    elements.playFrames.setAttribute("aria-label", "Pause frames");
    state.playTimer = window.setInterval(() => {
      if (state.index >= state.frames.length - 1) {
        stopPlayback();
        return;
      }
      goToFrame(state.index + 1);
    }, 140);
  }

  function sampledGridIndexes() {
    const total = state.frames.length;
    if (!total) return [];
    if (total <= state.gridLimit) return Array.from({ length: total }, (_item, index) => index);
    const step = (total - 1) / (state.gridLimit - 1);
    return Array.from({ length: state.gridLimit }, (_item, index) => Math.round(index * step));
  }

  function renderGrid() {
    elements.frameGrid.replaceChildren();
    const indexes = sampledGridIndexes();
    indexes.forEach((index) => {
      const button = document.createElement("button");
      button.className = "grid-item";
      button.type = "button";
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = `Frame ${index + 1}`;
      img.src = currentFrameUrl(index);
      const label = document.createElement("span");
      label.textContent = `${formatNumber(index + 1)} · ${timestampFromFilename(state.frames[index]) || state.frames[index]}`;
      button.append(img, label);
      button.addEventListener("click", () => {
        state.viewMode = "carousel";
        updateViewMode();
        goToFrame(index);
      });
      elements.frameGrid.appendChild(button);
    });
    elements.loadMoreFrames.classList.toggle("is-hidden", state.frames.length <= state.gridLimit || state.gridLimit >= 800);
    elements.loadMoreFrames.textContent = `Show more of ${formatNumber(state.frames.length)} frames`;
  }

  function updateViewMode() {
    const hasFrames = state.frames.length > 0;
    elements.emptyState.classList.toggle("is-hidden", hasFrames);
    elements.carouselView.classList.toggle("is-hidden", !hasFrames || state.viewMode !== "carousel");
    elements.gridView.classList.toggle("is-hidden", !hasFrames || state.viewMode !== "grid");
    elements.carouselViewButton.classList.toggle("is-active", state.viewMode === "carousel");
    elements.gridViewButton.classList.toggle("is-active", state.viewMode === "grid");
    elements.carouselViewButton.setAttribute("aria-pressed", state.viewMode === "carousel" ? "true" : "false");
    elements.gridViewButton.setAttribute("aria-pressed", state.viewMode === "grid" ? "true" : "false");
    if (hasFrames && state.viewMode === "grid") renderGrid();
  }

  function applyJob(job) {
    state.currentJob = job;
    state.currentJobId = job.id;
    state.frames = Array.isArray(job.frames) ? job.frames : [];
    state.index = 0;
    state.gridLimit = 80;

    elements.viewerEyebrow.textContent = job.state === "done" ? "Saved extraction" : "Current extraction";
    elements.viewerTitle.textContent = job.filename || "Untitled video";
    const dimensions = job.width && job.height ? `${job.width} × ${job.height}` : "Dimensions pending";
    elements.viewerMeta.textContent = `${dimensions} · ${formatNumber(job.frames_count || job.frames_written)} frames · ${formatDate(job.created_utc, true)}`;
    elements.sourceName.textContent = job.filename || "Untitled video";
    elements.sourceDimensions.textContent = job.width && job.height ? `${job.width} × ${job.height}` : "—";
    elements.sourceFrameCount.textContent = formatNumber(job.frames_count || job.frames_written);
    elements.sourceFps.textContent = job.source_fps ? `${Number(job.source_fps).toFixed(2)} fps` : "—";
    elements.sourceDate.textContent = formatDate(job.processed_utc || job.created_utc, true);

    const isDone = job.state === "done" && state.frames.length > 0;
    elements.downloadCurrent.disabled = !isDone;
    elements.downloadZip.disabled = !isDone;
    if (job.image_ext) elements.imageExt.value = String(job.image_ext).toLowerCase() === ".png" ? ".png" : ".jpg";
    elements.extractRate.value = job.sample_fps ? String(job.sample_fps) : "all";

    if (job.state === "done") {
      clearProgress();
      setStatus("Ready", `${formatNumber(state.frames.length)} frames are ready to inspect and export.`, "done");
    } else if (job.state === "error") {
      setStatus("Error", job.error || "The extraction could not be completed.", "error");
    } else {
      setStatus("Extracting", "Frames will appear here as soon as processing completes.", "running");
      setProgress(job.frames_written, job.expected_frames);
    }
    renderHistory();
    updateViewMode();
    if (isDone) renderCurrentFrame();
  }

  async function pollJob(jobId) {
    if (state.polling) return;
    state.polling = true;
    try {
      while (state.currentJobId === jobId) {
        const job = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
        updateJobInHistory(job);
        applyJob(job);
        if (job.state === "done") {
          showToast(`${job.filename} is ready.`);
          await refreshHistory(false);
          break;
        }
        if (job.state === "error") {
          showToast(job.error || "Extraction failed.", "error");
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 400));
      }
    } catch (error) {
      setStatus("Connection issue", error.message, "error");
      showToast(error.message, "error");
    } finally {
      state.polling = false;
    }
  }

  async function openJob(jobId) {
    stopPlayback();
    state.currentJobId = jobId;
    renderHistory();
    try {
      const job = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}`);
      applyJob(job);
      if (job.state === "queued" || job.state === "running") pollJob(jobId);
    } catch (error) {
      setStatus("Unable to open", error.message, "error");
      showToast(error.message, "error");
    }
  }

  async function uploadFile(file) {
    if (!file) return;
    stopPlayback();
    setStatus("Uploading", `${file.name} is being added to your workspace.`, "running");
    setProgress(0, 0);
    elements.viewerTitle.textContent = file.name;
    elements.viewerMeta.textContent = "Preparing extraction…";
    const form = new FormData();
    form.append("video", file);
    form.append("image_ext", elements.imageExt.value);
    form.append("sample_fps", elements.extractRate.value);
    try {
      const payload = await fetchJson("/api/jobs", { method: "POST", body: form });
      state.currentJobId = payload.job_id;
      await refreshHistory(false);
      await openJob(payload.job_id);
    } catch (error) {
      setStatus("Upload failed", error.message, "error");
      showToast(error.message, "error");
    } finally {
      elements.fileInput.value = "";
    }
  }

  function chooseFile() {
    elements.fileInput.click();
  }

  function downloadCurrent() {
    if (!state.currentJobId || !state.frames.length) return;
    window.location.href = `/api/jobs/${encodeURIComponent(state.currentJobId)}/frame/${state.index}/download.png`;
  }

  function downloadZip() {
    if (!state.currentJobId || !state.frames.length) return;
    const format = String(state.currentJob?.image_ext || ".jpg").toLowerCase() === ".png" ? "png" : "jpg";
    const params = new URLSearchParams({ format, sample_fps: elements.zipSampleRate.value || "all" });
    window.location.href = `/api/jobs/${encodeURIComponent(state.currentJobId)}/download.zip?${params}`;
  }

  function bindEvents() {
    [$("importButton"), $("newJobButton"), $("railImport"), elements.dropZone].forEach((button) => button.addEventListener("click", chooseFile));
    elements.fileInput.addEventListener("change", () => uploadFile(elements.fileInput.files?.[0]));
    $("refreshHistory").addEventListener("click", () => refreshHistory(false));
    elements.search.addEventListener("input", () => {
      state.searchTerm = elements.search.value;
      renderHistory();
    });
    elements.search.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        elements.search.value = "";
        state.searchTerm = "";
        renderHistory();
        elements.search.blur();
      }
    });

    [$("themeToggle"), $("railTheme")].forEach((button) => button.addEventListener("click", toggleTheme));
    $("historyToggle").addEventListener("click", () => openDrawer("history"));
    $("inspectorToggle").addEventListener("click", () => openDrawer("inspector"));
    $("railHistory").addEventListener("click", () => {
      if (window.innerWidth <= 980) openDrawer("history");
      else elements.search.focus();
    });
    elements.drawerBackdrop.addEventListener("click", closeDrawers);

    elements.carouselViewButton.addEventListener("click", () => {
      state.viewMode = "carousel";
      updateViewMode();
      renderCurrentFrame();
    });
    elements.gridViewButton.addEventListener("click", () => {
      state.viewMode = "grid";
      updateViewMode();
    });
    elements.loadMoreFrames.addEventListener("click", () => {
      state.gridLimit = Math.min(800, state.gridLimit + 80);
      renderGrid();
    });

    elements.previousFrame.addEventListener("click", () => goToFrame(state.index - 1));
    elements.nextFrame.addEventListener("click", () => goToFrame(state.index + 1));
    $("filmstripPrevious").addEventListener("click", () => goToFrame(state.index - filmstripWindowSize()));
    $("filmstripNext").addEventListener("click", () => goToFrame(state.index + filmstripWindowSize()));
    $("firstFrame").addEventListener("click", () => goToFrame(0));
    $("lastFrame").addEventListener("click", () => goToFrame(state.frames.length - 1));
    elements.playFrames.addEventListener("click", togglePlayback);
    elements.scrub.addEventListener("input", () => goToFrame(Number(elements.scrub.value)));
    elements.primaryImage.addEventListener("load", updateFrameRatio);
    $("fullscreenFrame").addEventListener("click", () => {
      if (elements.primaryImage.requestFullscreen) elements.primaryImage.requestFullscreen();
    });
    elements.downloadCurrent.addEventListener("click", downloadCurrent);
    elements.downloadZip.addEventListener("click", downloadZip);

    const dragTargets = [elements.dropZone, $("mediaStage")];
    dragTargets.forEach((target) => {
      target.addEventListener("dragenter", (event) => {
        event.preventDefault();
        elements.dropZone.classList.add("is-dragging");
      });
      target.addEventListener("dragover", (event) => event.preventDefault());
      target.addEventListener("dragleave", () => elements.dropZone.classList.remove("is-dragging"));
      target.addEventListener("drop", (event) => {
        event.preventDefault();
        elements.dropZone.classList.remove("is-dragging");
        uploadFile(event.dataTransfer?.files?.[0]);
      });
    });

    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const isTyping = target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        elements.search.focus();
        return;
      }
      if (isTyping || !state.frames.length || state.viewMode !== "carousel") return;
      if (event.key === "ArrowLeft") goToFrame(state.index - 1);
      if (event.key === "ArrowRight") goToFrame(state.index + 1);
      if (event.key === "Home") goToFrame(0);
      if (event.key === "End") goToFrame(state.frames.length - 1);
      if (event.key === " ") {
        event.preventDefault();
        togglePlayback();
      }
    });

    window.addEventListener("resize", () => {
      if (state.frames.length && state.viewMode === "carousel") {
        renderFilmstrip();
        updateFrameRatio();
      }
      if (window.innerWidth > 980) closeDrawers();
    });
  }

  async function initialize() {
    initializeTheme();
    bindEvents();
    setStatus("Ready", `${config.engine} extraction is available. Completed jobs remain in your library.`, "neutral");
    await refreshHistory(true);
  }

  initialize();
})();
