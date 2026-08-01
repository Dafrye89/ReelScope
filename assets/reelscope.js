(() => {
  "use strict";

  const config = window.REELSCOPE_CONFIG || { engine: "CPU", maxUpload: "Unlimited", csrfToken: "" };
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
    videoViewButton: $("videoViewButton"),
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
    videoCard: $("videoCard"),
    sourceVideo: $("sourceVideo"),
    videoSyncText: $("videoSyncText"),
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
    transcriptionModel: $("transcriptionModel"),
    transcriptionModelHelp: $("transcriptionModelHelp"),
    transcriptionLanguage: $("transcriptionLanguage"),
    transcribeButton: $("transcribeButton"),
    transcriptionStatus: $("transcriptionStatus"),
    transcriptionStatusText: $("transcriptionStatusText"),
    downloadTranscript: $("downloadTranscript"),
    transcriptWorkspace: $("transcriptWorkspace"),
    transcriptCues: $("transcriptCues"),
    transcriptCueCount: $("transcriptCueCount"),
    transcriptSaveState: $("transcriptSaveState"),
    saveTranscript: $("saveTranscript"),
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
    transcriptionTimer: null,
    transcriptJobId: null,
    transcriptLoadingJobId: null,
    transcriptCues: [],
    transcriptCueElements: [],
    activeTranscriptCue: -1,
    transcriptDirty: false,
  };

  function icon(name) {
    const span = document.createElement("span");
    span.className = "material-symbols-rounded";
    span.setAttribute("aria-hidden", "true");
    span.textContent = name;
    return span;
  }

  async function fetchJson(url, options = {}) {
    const requestOptions = { cache: "no-store", credentials: "same-origin", ...options };
    const method = String(requestOptions.method || "GET").toUpperCase();
    const headers = new Headers(requestOptions.headers || {});
    if (!["GET", "HEAD", "OPTIONS"].includes(method) && config.csrfToken) {
      headers.set("X-CSRF-Token", config.csrfToken);
    }
    requestOptions.headers = headers;
    const response = await fetch(url, requestOptions);
    let payload = {};
    try {
      payload = await response.json();
    } catch (_error) {
      payload = {};
    }
    if (response.status === 401) {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      throw new Error("Your session has expired.");
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

  function frameSecondsFromFilename(filename) {
    const timestamp = timestampFromFilename(filename);
    if (!timestamp) return null;
    const match = timestamp.match(/^(\d{2}):(\d{2}):(\d{2}\.\d{3})$/);
    if (!match) return null;
    return Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]);
  }

  function nearestFrameIndex(seconds) {
    if (!state.frames.length) return 0;
    let low = 0;
    let high = state.frames.length - 1;
    while (low < high) {
      const middle = Math.floor((low + high + 1) / 2);
      const value = frameSecondsFromFilename(state.frames[middle]);
      if (value === null || value > seconds) high = middle - 1;
      else low = middle;
    }
    const next = Math.min(state.frames.length - 1, low + 1);
    const lowTime = frameSecondsFromFilename(state.frames[low]) ?? 0;
    const nextTime = frameSecondsFromFilename(state.frames[next]) ?? lowTime;
    return Math.abs(nextTime - seconds) < Math.abs(seconds - lowTime) ? next : low;
  }

  function formatCueTime(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = Math.floor(total % 60);
    return hours > 0
      ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  function setTranscriptDirty(dirty) {
    state.transcriptDirty = Boolean(dirty);
    elements.saveTranscript.disabled = !state.transcriptDirty;
    elements.transcriptSaveState.textContent = state.transcriptDirty ? "Unsaved corrections" : "No unsaved changes";
  }

  function resetTranscript(jobId = null) {
    state.transcriptJobId = jobId;
    state.transcriptLoadingJobId = null;
    state.transcriptCues = [];
    state.transcriptCueElements = [];
    state.activeTranscriptCue = -1;
    elements.transcriptCues.replaceChildren();
    elements.transcriptCueCount.textContent = "0 words";
    elements.transcriptWorkspace.classList.add("is-hidden");
    setTranscriptDirty(false);
  }

  function updateActiveTranscriptCue(seconds) {
    if (!state.transcriptCues.length) return;
    const current = Number(seconds);
    let active = state.transcriptCues.findIndex((cue) => current >= Number(cue.start) && current < Number(cue.end));
    if (active === state.activeTranscriptCue) return;
    if (state.activeTranscriptCue >= 0) state.transcriptCueElements[state.activeTranscriptCue]?.classList.remove("is-active");
    state.activeTranscriptCue = active;
    if (active < 0) return;
    const cueElement = state.transcriptCueElements[active];
    cueElement?.classList.add("is-active");
    if (!document.activeElement?.classList.contains("transcript-text")) cueElement?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function seekToTranscriptCue(cue) {
    if (!state.currentJob?.video_available) return;
    if (state.viewMode !== "video") {
      state.viewMode = "video";
      updateViewMode();
    }
    const seconds = Number(cue.start) || 0;
    elements.sourceVideo.currentTime = seconds;
    goToFrame(nearestFrameIndex(seconds), { syncVideo: false });
    updateActiveTranscriptCue(seconds);
  }

  function renderTranscriptCues() {
    elements.transcriptCues.replaceChildren();
    state.transcriptCueElements = [];
    state.transcriptCues.forEach((cue, cueIndex) => {
      const row = document.createElement("span");
      row.className = "transcript-cue";
      row.dataset.cueIndex = String(cueIndex);
      const time = document.createElement("button");
      time.className = "transcript-time";
      time.type = "button";
      time.textContent = formatCueTime(cue.start);
      time.setAttribute("aria-label", `Seek video to ${formatCueTime(cue.start)}`);
      time.addEventListener("click", () => seekToTranscriptCue(cue));
      const wordInput = document.createElement("input");
      wordInput.className = "transcript-text";
      wordInput.type = "text";
      wordInput.value = cue.text;
      wordInput.style.width = `${Math.min(34, Math.max(4, Array.from(cue.text).length + 1))}ch`;
      wordInput.setAttribute("aria-label", `Transcript word ${cue.index}`);
      wordInput.addEventListener("input", () => {
        cue.text = wordInput.value;
        wordInput.style.width = `${Math.min(34, Math.max(4, Array.from(wordInput.value).length + 1))}ch`;
        setTranscriptDirty(true);
      });
      row.append(time, wordInput);
      elements.transcriptCues.appendChild(row);
      state.transcriptCueElements.push(row);
    });
    const wordTimed = state.transcriptCues.every((cue) => !/\s/.test(String(cue.text).trim()));
    const unit = wordTimed ? (state.transcriptCues.length === 1 ? "word" : "words") : (state.transcriptCues.length === 1 ? "cue" : "cues");
    elements.transcriptCueCount.textContent = `${formatNumber(state.transcriptCues.length)} ${unit}`;
    elements.transcriptWorkspace.classList.toggle("is-hidden", state.transcriptCues.length === 0);
    setTranscriptDirty(false);
    const initialSeconds = state.viewMode === "video" ? elements.sourceVideo.currentTime : frameSecondsFromFilename(state.frames[state.index]);
    if (initialSeconds !== null) updateActiveTranscriptCue(initialSeconds);
  }

  async function loadTranscript(jobId) {
    if (!jobId || state.transcriptLoadingJobId === jobId || state.transcriptJobId === jobId && state.transcriptCues.length) return;
    state.transcriptJobId = jobId;
    state.transcriptLoadingJobId = jobId;
    try {
      const payload = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/transcript`);
      if (state.currentJobId !== jobId) return;
      state.transcriptCues = Array.isArray(payload.cues) ? payload.cues : [];
      state.activeTranscriptCue = -1;
      renderTranscriptCues();
    } catch (error) {
      if (state.currentJobId === jobId) showToast(error.message, "error");
    } finally {
      if (state.transcriptLoadingJobId === jobId) state.transcriptLoadingJobId = null;
    }
  }

  async function saveTranscriptEdits() {
    if (!state.currentJobId || !state.transcriptDirty) return;
    elements.saveTranscript.disabled = true;
    elements.transcriptSaveState.textContent = "Saving corrections...";
    try {
      const payload = await fetchJson(`/api/jobs/${encodeURIComponent(state.currentJobId)}/transcript`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cues: state.transcriptCues.map(({ index, text }) => ({ index, text })) }),
      });
      state.transcriptCues = payload.cues;
      renderTranscriptCues();
      showToast("Transcript corrections saved to the SRT.");
    } catch (error) {
      elements.saveTranscript.disabled = false;
      elements.transcriptSaveState.textContent = "Save failed";
      showToast(error.message, "error");
    }
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

  function goToFrame(index, { syncVideo = true } = {}) {
    if (!state.frames.length) return;
    state.index = Math.max(0, Math.min(Number(index) || 0, state.frames.length - 1));
    renderCurrentFrame();
    if (syncVideo && state.viewMode === "video" && elements.sourceVideo.src) {
      const seconds = frameSecondsFromFilename(state.frames[state.index]);
      if (seconds !== null && Math.abs(elements.sourceVideo.currentTime - seconds) > 0.035) {
        elements.sourceVideo.currentTime = seconds;
      }
    }
    const frameSeconds = frameSecondsFromFilename(state.frames[state.index]);
    if (frameSeconds !== null) updateActiveTranscriptCue(frameSeconds);
  }

  function stopPlayback() {
    if (state.viewMode === "video" && !elements.sourceVideo.paused) elements.sourceVideo.pause();
    if (state.playTimer) window.clearInterval(state.playTimer);
    state.playTimer = null;
    elements.playFrames.replaceChildren(icon("play_arrow"));
    elements.playFrames.setAttribute("aria-label", "Play frames");
  }

  function togglePlayback() {
    if (state.viewMode === "video") {
      if (elements.sourceVideo.paused) elements.sourceVideo.play().catch((error) => showToast(error.message, "error"));
      else elements.sourceVideo.pause();
      return;
    }
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
    elements.carouselView.classList.toggle("is-hidden", !hasFrames || !["carousel", "video"].includes(state.viewMode));
    elements.gridView.classList.toggle("is-hidden", !hasFrames || state.viewMode !== "grid");
    elements.carouselViewButton.classList.toggle("is-active", state.viewMode === "carousel");
    elements.videoViewButton.classList.toggle("is-active", state.viewMode === "video");
    elements.gridViewButton.classList.toggle("is-active", state.viewMode === "grid");
    elements.carouselViewButton.setAttribute("aria-pressed", state.viewMode === "carousel" ? "true" : "false");
    elements.videoViewButton.setAttribute("aria-pressed", state.viewMode === "video" ? "true" : "false");
    elements.gridViewButton.setAttribute("aria-pressed", state.viewMode === "grid" ? "true" : "false");
    const videoMode = hasFrames && state.viewMode === "video" && state.currentJob?.video_available;
    elements.mediaStage.classList.toggle("is-video-mode", Boolean(videoMode));
    elements.videoCard.classList.toggle("is-hidden", !videoMode);
    if (videoMode) {
      const expectedUrl = state.currentJob.video_url;
      if (elements.sourceVideo.getAttribute("src") !== expectedUrl) {
        elements.sourceVideo.src = expectedUrl;
        elements.sourceVideo.load();
      }
      const seconds = frameSecondsFromFilename(state.frames[state.index]);
      if (seconds !== null && elements.sourceVideo.readyState >= 1) elements.sourceVideo.currentTime = seconds;
    } else if (!elements.sourceVideo.paused) {
      elements.sourceVideo.pause();
    }
    if (hasFrames && state.viewMode === "grid") renderGrid();
    if (hasFrames && state.viewMode !== "grid") renderCurrentFrame();
  }

  function renderTranscription(status = { state: "idle" }) {
    const transcriptionState = status?.state || "idle";
    elements.transcriptionStatus.dataset.state = transcriptionState;
    elements.transcribeButton.disabled = !state.currentJob?.video_available || state.currentJob?.state !== "done" || ["queued", "running"].includes(transcriptionState);
    elements.downloadTranscript.classList.toggle("is-hidden", transcriptionState !== "done");
    if (transcriptionState === "done") {
      elements.downloadTranscript.href = status.download_url;
      const resultCount = status.words ?? status.segments;
      const resultUnit = status.words ? "timestamped words" : "subtitle cues";
      elements.transcriptionStatusText.textContent = `${status.model_label || "Local model"} created ${formatNumber(resultCount)} ${resultUnit} on ${String(status.device || "local").toUpperCase()}.`;
      elements.transcribeButton.replaceChildren(icon("refresh"), document.createTextNode(" Regenerate SRT"));
      loadTranscript(state.currentJobId);
    } else if (transcriptionState === "running" || transcriptionState === "queued") {
      const progress = Number(status.progress_seconds || 0);
      const prefix = status.automatic ? "Automatically transcribing" : "Transcribing";
      elements.transcriptionStatusText.textContent = progress > 0 ? `${prefix}… ${progress.toFixed(1)} seconds processed.` : `${prefix}… loading the local model and preparing audio.`;
      elements.transcribeButton.replaceChildren(icon("refresh"), document.createTextNode(" Transcribing"));
      resetTranscript(state.currentJobId);
    } else if (transcriptionState === "error") {
      elements.transcriptionStatusText.textContent = status.error || "Transcription failed.";
      elements.transcribeButton.replaceChildren(icon("video_library"), document.createTextNode(" Try again"));
      resetTranscript(state.currentJobId);
    } else {
      elements.transcriptionStatusText.textContent = state.currentJob?.video_available ? "New uploads transcribe automatically. Generate a transcript for this existing video." : "Choose a completed video to transcribe.";
      elements.transcribeButton.replaceChildren(icon("video_library"), document.createTextNode(" Generate SRT"));
      resetTranscript(state.currentJobId);
    }
  }

  function stopTranscriptionPolling() {
    if (state.transcriptionTimer) window.clearTimeout(state.transcriptionTimer);
    state.transcriptionTimer = null;
  }

  async function pollTranscription(jobId) {
    stopTranscriptionPolling();
    try {
      const status = await fetchJson(`/api/jobs/${encodeURIComponent(jobId)}/transcription`);
      if (state.currentJobId !== jobId) return;
      state.currentJob.transcription = status;
      renderTranscription(status);
      if (["queued", "running"].includes(status.state)) {
        state.transcriptionTimer = window.setTimeout(() => pollTranscription(jobId), 1000);
      } else if (status.state === "done") {
        showToast("Your SRT transcript is ready.");
      } else if (status.state === "error") {
        showToast(status.error || "Transcription failed.", "error");
      }
    } catch (error) {
      renderTranscription({ state: "error", error: error.message });
    }
  }

  async function startTranscription() {
    if (!state.currentJobId) return;
    elements.transcribeButton.disabled = true;
    try {
      const status = await fetchJson(`/api/jobs/${encodeURIComponent(state.currentJobId)}/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: elements.transcriptionModel.value,
          language: elements.transcriptionLanguage.value,
        }),
      });
      state.currentJob.transcription = status;
      renderTranscription(status);
      pollTranscription(state.currentJobId);
    } catch (error) {
      renderTranscription({ state: "error", error: error.message });
      showToast(error.message, "error");
    }
  }

  function applyJob(job) {
    stopTranscriptionPolling();
    if (state.transcriptJobId !== job.id) resetTranscript(job.id);
    state.currentJob = job;
    state.currentJobId = job.id;
    state.frames = Array.isArray(job.frames) ? job.frames : [];
    state.index = 0;
    state.gridLimit = 80;
    state.viewMode = "carousel";
    elements.sourceVideo.pause();
    elements.sourceVideo.removeAttribute("src");
    elements.sourceVideo.load();

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
    elements.videoViewButton.disabled = !isDone || !job.video_available;
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
    renderTranscription(job.transcription);
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
    stopTranscriptionPolling();
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
      if (window.innerWidth <= 1080) openDrawer("history");
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
    elements.videoViewButton.addEventListener("click", () => {
      if (!state.currentJob?.video_available) return;
      state.viewMode = "video";
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
      const target = state.viewMode === "video" ? elements.sourceVideo : elements.primaryImage;
      if (target.requestFullscreen) target.requestFullscreen();
    });
    elements.downloadCurrent.addEventListener("click", downloadCurrent);
    elements.downloadZip.addEventListener("click", downloadZip);
    elements.transcribeButton.addEventListener("click", startTranscription);
    elements.saveTranscript.addEventListener("click", saveTranscriptEdits);
    elements.transcriptionModel.addEventListener("change", () => {
      const selected = (config.transcriptionModels || []).find((model) => model.key === elements.transcriptionModel.value);
      elements.transcriptionModelHelp.textContent = selected?.description || "Local timestamped speech-to-text.";
      elements.transcriptionLanguage.disabled = elements.transcriptionModel.value === "distil-large-v3.5";
      if (elements.transcriptionLanguage.disabled) elements.transcriptionLanguage.value = "en";
    });
    elements.sourceVideo.addEventListener("timeupdate", () => {
      if (state.viewMode !== "video" || !state.frames.length) return;
      const index = nearestFrameIndex(elements.sourceVideo.currentTime);
      if (index !== state.index) goToFrame(index, { syncVideo: false });
      updateActiveTranscriptCue(elements.sourceVideo.currentTime);
      elements.videoSyncText.textContent = `Frame ${formatNumber(state.index + 1)} selected at ${timestampFromFilename(state.frames[state.index]) || "current time"}`;
    });
    elements.sourceVideo.addEventListener("play", () => {
      elements.playFrames.replaceChildren(icon("pause"));
      elements.playFrames.setAttribute("aria-label", "Pause original video");
    });
    elements.sourceVideo.addEventListener("pause", () => {
      elements.playFrames.replaceChildren(icon("play_arrow"));
      elements.playFrames.setAttribute("aria-label", "Play original video");
    });
    elements.sourceVideo.addEventListener("loadedmetadata", () => {
      const seconds = frameSecondsFromFilename(state.frames[state.index]);
      if (seconds !== null) elements.sourceVideo.currentTime = seconds;
    });

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
      if (isTyping || !state.frames.length || state.viewMode === "grid") return;
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
      if (state.frames.length && state.viewMode !== "grid") {
        renderFilmstrip();
        updateFrameRatio();
      }
      if (window.innerWidth > 1080) closeDrawers();
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
