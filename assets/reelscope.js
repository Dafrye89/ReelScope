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
    mobileCarouselView: $("mobileCarouselView"),
    mobileVideoView: $("mobileVideoView"),
    mobileGridView: $("mobileGridView"),
    frameGrid: $("frameGrid"),
    loadMoreFrames: $("loadMoreFrames"),
    gridSelectionBar: $("gridSelectionBar"),
    gridSelectionCount: $("gridSelectionCount"),
    downloadSelectedFrames: $("downloadSelectedFrames"),
    clearSelectedFrames: $("clearSelectedFrames"),
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
    downloadFrameOverlay: $("downloadFrameOverlay"),
    downloadZip: $("downloadZip"),
    transcriptionModel: $("transcriptionModel"),
    transcriptionModelHelp: $("transcriptionModelHelp"),
    transcriptionLanguage: $("transcriptionLanguage"),
    transcriptionProvider: $("transcriptionProvider"),
    localTranscriptionSettings: $("localTranscriptionSettings"),
    elevenLabsSettings: $("elevenLabsSettings"),
    elevenLabsApiKey: $("elevenLabsApiKey"),
    elevenLabsKeyStatus: $("elevenLabsKeyStatus"),
    removeElevenLabsKey: $("removeElevenLabsKey"),
    elevenLabsModel: $("elevenLabsModel"),
    elevenLabsModelHelp: $("elevenLabsModelHelp"),
    elevenLabsLanguage: $("elevenLabsLanguage"),
    elevenLabsTimestamps: $("elevenLabsTimestamps"),
    elevenLabsAudioEvents: $("elevenLabsAudioEvents"),
    elevenLabsNoVerbatim: $("elevenLabsNoVerbatim"),
    elevenLabsDiarize: $("elevenLabsDiarize"),
    elevenLabsSpeakerLabels: $("elevenLabsSpeakerLabels"),
    elevenLabsSpeakerLibrary: $("elevenLabsSpeakerLibrary"),
    elevenLabsSpeakerRoles: $("elevenLabsSpeakerRoles"),
    elevenLabsMultiChannel: $("elevenLabsMultiChannel"),
    elevenLabsLogging: $("elevenLabsLogging"),
    elevenLabsNumSpeakers: $("elevenLabsNumSpeakers"),
    elevenLabsDiarizationThreshold: $("elevenLabsDiarizationThreshold"),
    elevenLabsMultiChannelStyle: $("elevenLabsMultiChannelStyle"),
    elevenLabsTemperature: $("elevenLabsTemperature"),
    elevenLabsSeed: $("elevenLabsSeed"),
    elevenLabsKeyterms: $("elevenLabsKeyterms"),
    elevenLabsEntityDetection: $("elevenLabsEntityDetection"),
    elevenLabsEntityRedaction: $("elevenLabsEntityRedaction"),
    elevenLabsRedactionMode: $("elevenLabsRedactionMode"),
    elevenLabsExportSpeakers: $("elevenLabsExportSpeakers"),
    elevenLabsExportTimestamps: $("elevenLabsExportTimestamps"),
    elevenLabsExportSilence: $("elevenLabsExportSilence"),
    elevenLabsExportDuration: $("elevenLabsExportDuration"),
    elevenLabsExportChars: $("elevenLabsExportChars"),
    elevenLabsExportLineChars: $("elevenLabsExportLineChars"),
    saveTranscriptionSettings: $("saveTranscriptionSettings"),
    transcribeButton: $("transcribeButton"),
    transcriptionStatus: $("transcriptionStatus"),
    transcriptionStatusText: $("transcriptionStatusText"),
    downloadTranscript: $("downloadTranscript"),
    downloadTranscriptOverlay: $("downloadTranscriptOverlay"),
    transcriptExportLinks: $("transcriptExportLinks"),
    transcriptWorkspace: $("transcriptWorkspace"),
    transcriptCues: $("transcriptCues"),
    transcriptCueCount: $("transcriptCueCount"),
    transcriptSaveState: $("transcriptSaveState"),
    copyTranscript: $("copyTranscript"),
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
    selectedGridFrames: new Set(),
    transcriptionSettingsLoaded: false,
    elevenLabsKeyConfigured: false,
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

  function formatTranscriptTime(seconds) {
    const total = Math.max(0, Number(seconds) || 0);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = Math.floor(total % 60);
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }

  function setTranscriptDirty(dirty) {
    state.transcriptDirty = Boolean(dirty);
    elements.saveTranscript.disabled = !state.transcriptDirty;
    elements.transcriptSaveState.textContent = state.transcriptDirty ? "Unsaved changes" : "Saved";
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
    if (!document.activeElement?.classList.contains("transcript-word")) cueElement?.scrollIntoView({ block: "nearest", behavior: "smooth" });
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

  function groupTranscriptCues(cues) {
    const lines = [];
    let current = [];
    cues.forEach((cue) => {
      const previous = current[current.length - 1];
      const sentenceEnded = previous && /[.!?]["']?$/.test(String(previous.text).trim());
      const timingGap = previous && Number(cue.start) - Number(previous.end) > 1.1;
      if (current.length && (sentenceEnded || timingGap || current.length >= 14)) {
        lines.push(current);
        current = [];
      }
      current.push(cue);
    });
    if (current.length) lines.push(current);
    return lines;
  }

  function renderTranscriptCues() {
    elements.transcriptCues.replaceChildren();
    state.transcriptCueElements = [];
    const cueIndexes = new Map(state.transcriptCues.map((cue, index) => [cue, index]));
    groupTranscriptCues(state.transcriptCues).forEach((lineCues) => {
      const line = document.createElement("article");
      line.className = "transcript-line";
      const time = document.createElement("button");
      time.className = "transcript-time";
      time.type = "button";
      time.textContent = formatTranscriptTime(lineCues[0].start);
      time.setAttribute("aria-label", `Seek video to ${formatTranscriptTime(lineCues[0].start)}`);
      time.addEventListener("click", () => seekToTranscriptCue(lineCues[0]));
      const text = document.createElement("div");
      text.className = "transcript-line-text";
      lineCues.forEach((cue) => {
        const cueIndex = cueIndexes.get(cue);
        const word = document.createElement("span");
        word.className = "transcript-word";
        word.textContent = cue.text;
        word.setAttribute("contenteditable", "plaintext-only");
        word.setAttribute("role", "textbox");
        word.setAttribute("aria-label", `Transcript word ${cue.index}`);
        word.setAttribute("spellcheck", "true");
        word.addEventListener("keydown", (event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            word.blur();
          }
        });
        word.addEventListener("input", () => {
          cue.text = String(word.textContent || "").replace(/\s+/g, " ");
          setTranscriptDirty(true);
        });
        text.appendChild(word);
        state.transcriptCueElements[cueIndex] = word;
      });
      line.append(time, text);
      elements.transcriptCues.appendChild(line);
    });
    const wordTimed = state.transcriptCues.every((cue) => !/\s/.test(String(cue.text).trim()));
    const unit = wordTimed ? (state.transcriptCues.length === 1 ? "word" : "words") : (state.transcriptCues.length === 1 ? "cue" : "cues");
    elements.transcriptCueCount.textContent = `${formatNumber(state.transcriptCues.length)} ${unit}`;
    elements.transcriptWorkspace.classList.toggle("is-hidden", state.transcriptCues.length === 0);
    setTranscriptDirty(false);
    const initialSeconds = state.viewMode === "video" ? elements.sourceVideo.currentTime : frameSecondsFromFilename(state.frames[state.index]);
    if (initialSeconds !== null) updateActiveTranscriptCue(initialSeconds);
  }

  async function copyTranscriptText() {
    const text = groupTranscriptCues(state.transcriptCues)
      .map((line) => line.map((cue) => cue.text).join(" "))
      .join("\n");
    if (!text) return;
    let copied = false;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("clipboard API unavailable");
      await Promise.race([
        navigator.clipboard.writeText(text),
        new Promise((_, reject) => window.setTimeout(() => reject(new Error("clipboard timed out")), 600)),
      ]);
      copied = true;
    } catch (_error) {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      copied = document.execCommand("copy");
      textarea.remove();
    }
    showToast(copied ? "Transcript copied." : "The transcript could not be copied.", copied ? "info" : "error");
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
    const target = panel === "history" ? elements.historyPanel : elements.inspectorPanel;
    const shouldOpen = !target.classList.contains("is-open");
    elements.historyPanel.classList.remove("is-open");
    elements.inspectorPanel.classList.remove("is-open");
    if (shouldOpen) target.classList.add("is-open");
    elements.drawerBackdrop.classList.toggle("is-hidden", !shouldOpen);
    $("historyToggle").setAttribute("aria-expanded", String(shouldOpen && panel === "history"));
    $("historyToggle").setAttribute("aria-label", shouldOpen && panel === "history" ? "Close menu" : "Open menu");
  }

  function closeDrawers() {
    elements.historyPanel.classList.remove("is-open");
    elements.inspectorPanel.classList.remove("is-open");
    elements.drawerBackdrop.classList.add("is-hidden");
    $("historyToggle").setAttribute("aria-expanded", "false");
    $("historyToggle").setAttribute("aria-label", "Open menu");
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
    const maxWidth = stageBounds.width * (window.innerWidth <= 700 ? 0.9 : 0.50);
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
      const card = document.createElement("article");
      card.className = `grid-item${state.selectedGridFrames.has(index) ? " is-selected" : ""}`;
      const openButton = document.createElement("button");
      openButton.className = "grid-frame-button";
      openButton.type = "button";
      openButton.setAttribute("aria-label", `Open frame ${index + 1}`);
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = `Frame ${index + 1}`;
      img.src = currentFrameUrl(index);
      const label = document.createElement("span");
      label.textContent = `${formatNumber(index + 1)} · ${timestampFromFilename(state.frames[index]) || state.frames[index]}`;
      openButton.append(img, label);
      openButton.addEventListener("click", () => {
        state.viewMode = "carousel";
        updateViewMode();
        goToFrame(index);
      });
      const selectionLabel = document.createElement("label");
      selectionLabel.className = "grid-checkbox";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = state.selectedGridFrames.has(index);
      checkbox.setAttribute("aria-label", `Select frame ${index + 1}`);
      selectionLabel.append(checkbox, icon("check"));
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) state.selectedGridFrames.add(index);
        else state.selectedGridFrames.delete(index);
        card.classList.toggle("is-selected", checkbox.checked);
        updateGridSelectionBar();
      });
      card.append(openButton, selectionLabel);
      elements.frameGrid.appendChild(card);
    });
    elements.loadMoreFrames.classList.toggle("is-hidden", state.frames.length <= state.gridLimit || state.gridLimit >= 800);
    elements.loadMoreFrames.textContent = `Show more of ${formatNumber(state.frames.length)} frames`;
    updateGridSelectionBar();
  }

  function updateGridSelectionBar() {
    const count = state.selectedGridFrames.size;
    elements.gridSelectionCount.textContent = formatNumber(count);
    elements.gridSelectionBar.classList.toggle("is-visible", count > 0);
    elements.downloadSelectedFrames.disabled = count === 0;
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
    [
      [elements.mobileCarouselView, "carousel"],
      [elements.mobileVideoView, "video"],
      [elements.mobileGridView, "grid"],
    ].forEach(([button, mode]) => {
      button.classList.toggle("is-active", state.viewMode === mode);
      button.setAttribute("aria-pressed", state.viewMode === mode ? "true" : "false");
    });
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

  function nullableNumber(input) {
    const value = String(input.value || "").trim();
    return value === "" ? null : Number(value);
  }

  function splitSettingLines(value) {
    return String(value || "")
      .replace(/\r/g, "\n")
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setNullableValue(input, value) {
    input.value = value === null || value === undefined ? "" : String(value);
  }

  function selectedElevenLabsFormats() {
    return Array.from(document.querySelectorAll('input[name="elevenLabsFormat"]:checked')).map((input) => input.value);
  }

  function collectElevenLabsSettings() {
    const combinedMultiChannel = elements.elevenLabsMultiChannel.checked && elements.elevenLabsMultiChannelStyle.value === "combined";
    const activeDiarization = elements.elevenLabsDiarize.checked && !elements.elevenLabsMultiChannel.checked;
    const speakerCount = activeDiarization ? nullableNumber(elements.elevenLabsNumSpeakers) : null;
    return {
      model_id: elements.elevenLabsModel.value,
      language_code: elements.elevenLabsLanguage.value.trim().toLowerCase() || "auto",
      tag_audio_events: elements.elevenLabsAudioEvents.checked,
      timestamps_granularity: elements.elevenLabsTimestamps.value,
      diarize: activeDiarization,
      num_speakers: speakerCount,
      diarization_threshold: activeDiarization && speakerCount === null ? nullableNumber(elements.elevenLabsDiarizationThreshold) : null,
      no_verbatim: elements.elevenLabsNoVerbatim.checked,
      use_speaker_library: elements.elevenLabsSpeakerLibrary.checked && !elements.elevenLabsMultiChannel.checked,
      detect_speaker_roles: elements.elevenLabsSpeakerRoles.checked && !elements.elevenLabsMultiChannel.checked,
      include_speaker_labels: elements.elevenLabsSpeakerLabels.checked,
      temperature: nullableNumber(elements.elevenLabsTemperature),
      seed: nullableNumber(elements.elevenLabsSeed),
      use_multi_channel: elements.elevenLabsMultiChannel.checked,
      multichannel_output_style: elements.elevenLabsMultiChannelStyle.value,
      entity_detection: combinedMultiChannel ? [] : splitSettingLines(elements.elevenLabsEntityDetection.value),
      entity_redaction: combinedMultiChannel ? [] : splitSettingLines(elements.elevenLabsEntityRedaction.value),
      entity_redaction_mode: elements.elevenLabsRedactionMode.value,
      keyterms: splitSettingLines(elements.elevenLabsKeyterms.value),
      enable_logging: elements.elevenLabsLogging.checked,
      additional_formats: selectedElevenLabsFormats(),
      export_include_speakers: elements.elevenLabsExportSpeakers.checked,
      export_include_timestamps: elements.elevenLabsExportTimestamps.checked,
      export_segment_on_silence: nullableNumber(elements.elevenLabsExportSilence),
      export_max_segment_duration: nullableNumber(elements.elevenLabsExportDuration),
      export_max_segment_chars: nullableNumber(elements.elevenLabsExportChars),
      export_max_characters_per_line: nullableNumber(elements.elevenLabsExportLineChars),
    };
  }

  function collectAccountTranscriptionSettings() {
    return {
      provider: elements.transcriptionProvider.value,
      api_key: elements.elevenLabsApiKey.value.trim(),
      local: {
        model: elements.transcriptionModel.value,
        language: elements.transcriptionLanguage.value,
      },
      elevenlabs: collectElevenLabsSettings(),
    };
  }

  function syncElevenLabsDependencies() {
    const multiChannel = elements.elevenLabsMultiChannel.checked;
    const diarize = elements.elevenLabsDiarize.checked && !multiChannel;
    const fixedSpeakers = String(elements.elevenLabsNumSpeakers.value || "").trim() !== "";
    elements.elevenLabsDiarize.disabled = multiChannel;
    elements.elevenLabsNumSpeakers.disabled = !diarize;
    elements.elevenLabsDiarizationThreshold.disabled = !diarize || fixedSpeakers;
    elements.elevenLabsSpeakerLibrary.disabled = !diarize;
    elements.elevenLabsSpeakerRoles.disabled = !diarize || multiChannel;
    elements.elevenLabsMultiChannelStyle.disabled = !multiChannel;
    const entityDisabled = multiChannel && elements.elevenLabsMultiChannelStyle.value === "combined";
    elements.elevenLabsEntityDetection.disabled = entityDisabled;
    elements.elevenLabsEntityRedaction.disabled = entityDisabled;
    elements.elevenLabsRedactionMode.disabled = entityDisabled || !elements.elevenLabsEntityRedaction.value.trim();
    const scribeV2 = elements.elevenLabsModel.value === "scribe_v2";
    elements.elevenLabsNoVerbatim.disabled = !scribeV2;
    if (!scribeV2) elements.elevenLabsNoVerbatim.checked = false;
  }

  function syncTranscriptionProvider() {
    const isElevenLabs = elements.transcriptionProvider.value === "elevenlabs";
    elements.localTranscriptionSettings.classList.toggle("is-hidden", isElevenLabs);
    elements.elevenLabsSettings.classList.toggle("is-hidden", !isElevenLabs);
    syncElevenLabsDependencies();
  }

  function applyAccountTranscriptionSettings(payload) {
    const local = payload?.local || {};
    const cloud = payload?.elevenlabs || {};
    elements.transcriptionProvider.value = payload?.provider === "elevenlabs" ? "elevenlabs" : "local";
    elements.transcriptionModel.value = local.model || "whisper-turbo";
    elements.transcriptionLanguage.value = local.language || "auto";
    elements.elevenLabsModel.value = cloud.model_id || "scribe_v2";
    elements.elevenLabsLanguage.value = cloud.language_code || "auto";
    elements.elevenLabsTimestamps.value = cloud.timestamps_granularity || "word";
    elements.elevenLabsAudioEvents.checked = cloud.tag_audio_events !== false;
    elements.elevenLabsNoVerbatim.checked = Boolean(cloud.no_verbatim);
    elements.elevenLabsDiarize.checked = Boolean(cloud.diarize);
    elements.elevenLabsSpeakerLabels.checked = Boolean(cloud.include_speaker_labels);
    elements.elevenLabsSpeakerLibrary.checked = Boolean(cloud.use_speaker_library);
    elements.elevenLabsSpeakerRoles.checked = Boolean(cloud.detect_speaker_roles);
    elements.elevenLabsMultiChannel.checked = Boolean(cloud.use_multi_channel);
    elements.elevenLabsLogging.checked = cloud.enable_logging !== false;
    setNullableValue(elements.elevenLabsNumSpeakers, cloud.num_speakers);
    setNullableValue(elements.elevenLabsDiarizationThreshold, cloud.diarization_threshold);
    elements.elevenLabsMultiChannelStyle.value = cloud.multichannel_output_style || "combined";
    setNullableValue(elements.elevenLabsTemperature, cloud.temperature);
    setNullableValue(elements.elevenLabsSeed, cloud.seed);
    elements.elevenLabsKeyterms.value = (cloud.keyterms || []).join("\n");
    elements.elevenLabsEntityDetection.value = (cloud.entity_detection || []).join(", ");
    elements.elevenLabsEntityRedaction.value = (cloud.entity_redaction || []).join(", ");
    elements.elevenLabsRedactionMode.value = cloud.entity_redaction_mode || "enumerated_entity_type";
    document.querySelectorAll('input[name="elevenLabsFormat"]').forEach((input) => {
      input.checked = (cloud.additional_formats || []).includes(input.value);
    });
    elements.elevenLabsExportSpeakers.checked = cloud.export_include_speakers !== false;
    elements.elevenLabsExportTimestamps.checked = cloud.export_include_timestamps !== false;
    setNullableValue(elements.elevenLabsExportSilence, cloud.export_segment_on_silence);
    setNullableValue(elements.elevenLabsExportDuration, cloud.export_max_segment_duration);
    setNullableValue(elements.elevenLabsExportChars, cloud.export_max_segment_chars);
    setNullableValue(elements.elevenLabsExportLineChars, cloud.export_max_characters_per_line);
    state.elevenLabsKeyConfigured = Boolean(payload?.api_key_configured);
    elements.elevenLabsApiKey.value = "";
    elements.elevenLabsApiKey.placeholder = state.elevenLabsKeyConfigured
      ? `Saved key ending in ${payload.api_key_suffix || "••••"}`
      : "Paste a new ElevenLabs key";
    elements.removeElevenLabsKey.disabled = !state.elevenLabsKeyConfigured;
    elements.elevenLabsKeyStatus.textContent = state.elevenLabsKeyConfigured
      ? `Connected${payload.elevenlabs_tier ? ` · ${payload.elevenlabs_tier} plan` : ""}. The encrypted key remains on this ReelScope server.`
      : "No key saved. Keys are encrypted on this ReelScope server and are never returned to the browser.";
    const localModel = (config.transcriptionModels || []).find((model) => model.key === elements.transcriptionModel.value);
    elements.transcriptionModelHelp.textContent = localModel?.description || "Local timestamped speech-to-text.";
    const cloudModel = (config.elevenlabsModels || []).find((model) => model.id === elements.elevenLabsModel.value);
    elements.elevenLabsModelHelp.textContent = cloudModel?.description || "ElevenLabs batch speech-to-text.";
    syncTranscriptionProvider();
    state.transcriptionSettingsLoaded = true;
  }

  async function loadAccountTranscriptionSettings() {
    try {
      applyAccountTranscriptionSettings(await fetchJson("/api/account/transcription-settings"));
    } catch (error) {
      showToast(`Could not load transcription settings: ${error.message}`, "error");
    }
  }

  async function saveAccountTranscriptionSettings({ silent = false } = {}) {
    elements.saveTranscriptionSettings.disabled = true;
    try {
      const saved = await fetchJson("/api/account/transcription-settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectAccountTranscriptionSettings()),
      });
      applyAccountTranscriptionSettings(saved);
      if (!silent) showToast("Transcription provider settings saved.");
      return saved;
    } finally {
      elements.saveTranscriptionSettings.disabled = false;
    }
  }

  async function removeElevenLabsApiKey() {
    if (!state.elevenLabsKeyConfigured) return;
    if (!window.confirm("Remove your saved ElevenLabs API key and switch automatic transcription back to local?")) return;
    try {
      const saved = await fetchJson("/api/account/transcription-settings", { method: "DELETE" });
      applyAccountTranscriptionSettings(saved);
      showToast("ElevenLabs API key removed. Automatic transcription is local again.");
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function renderAdditionalTranscriptExports(status) {
    elements.transcriptExportLinks.replaceChildren();
    const exports = Array.isArray(status?.additional_formats) ? status.additional_formats : [];
    exports.forEach((item) => {
      if (!item?.download_url) return;
      const link = document.createElement("a");
      link.className = "secondary-button";
      link.href = item.download_url;
      link.download = "";
      link.append(icon("download"), document.createTextNode(` Download ElevenLabs ${String(item.format || "export").toUpperCase()}`));
      elements.transcriptExportLinks.appendChild(link);
    });
    elements.transcriptExportLinks.classList.toggle("is-hidden", elements.transcriptExportLinks.childElementCount === 0);
  }

  function renderTranscription(status = { state: "idle" }) {
    const transcriptionState = status?.state || "idle";
    elements.transcriptionStatus.dataset.state = transcriptionState;
    elements.transcribeButton.disabled = !state.currentJob?.video_available || state.currentJob?.state !== "done" || ["queued", "running"].includes(transcriptionState);
    elements.downloadTranscript.classList.toggle("is-hidden", transcriptionState !== "done");
    elements.downloadTranscriptOverlay.classList.toggle("is-hidden", transcriptionState !== "done");
    renderAdditionalTranscriptExports(transcriptionState === "done" ? status : null);
    if (transcriptionState === "done") {
      elements.downloadTranscript.href = status.download_url;
      elements.downloadTranscriptOverlay.href = status.download_url;
      const resultCount = status.words ?? status.segments;
      const resultUnit = status.words ? "timestamped words" : "subtitle cues";
      elements.transcriptionStatusText.textContent = `${status.model_label || "Speech model"} created ${formatNumber(resultCount)} ${resultUnit} on ${String(status.device || "local").toUpperCase()}.`;
      elements.transcribeButton.replaceChildren(icon("refresh"), document.createTextNode(" Regenerate SRT"));
      loadTranscript(state.currentJobId);
    } else if (transcriptionState === "running" || transcriptionState === "queued") {
      const progress = Number(status.progress_seconds || 0);
      const prefix = status.automatic ? "Automatically transcribing" : "Transcribing";
      const preparing = status.provider === "elevenlabs" ? "securely sending the original video to ElevenLabs" : "loading the local model and preparing audio";
      elements.transcriptionStatusText.textContent = progress > 0 ? `${prefix}… ${progress.toFixed(1)} seconds processed.` : `${prefix}… ${preparing}.`;
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
      await saveAccountTranscriptionSettings({ silent: true });
      const status = await fetchJson(`/api/jobs/${encodeURIComponent(state.currentJobId)}/transcribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
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
    state.selectedGridFrames.clear();
    updateGridSelectionBar();
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
    elements.downloadFrameOverlay.disabled = !isDone;
    elements.downloadZip.disabled = !isDone;
    elements.videoViewButton.disabled = !isDone || !job.video_available;
    elements.mobileVideoView.disabled = !isDone || !job.video_available;
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

  async function downloadSelectedGridFrames() {
    const indices = Array.from(state.selectedGridFrames).sort((left, right) => left - right);
    if (!state.currentJobId || !indices.length) return;
    elements.downloadSelectedFrames.disabled = true;
    elements.downloadSelectedFrames.replaceChildren(icon("refresh"), document.createTextNode(" Preparing download"));
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(state.currentJobId)}/download-selected.zip`, {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": config.csrfToken,
        },
        body: JSON.stringify({ indices }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `Download failed (${response.status})`);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const filenameMatch = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i);
      const filename = filenameMatch ? decodeURIComponent(filenameMatch[1].replace(/\"$/, "")) : "selected-frames.zip";
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      showToast(`${formatNumber(indices.length)} selected frames downloaded.`);
      state.selectedGridFrames.clear();
      renderGrid();
    } catch (error) {
      showToast(error.message, "error");
    } finally {
      elements.downloadSelectedFrames.replaceChildren(icon("download"), document.createTextNode(" Download selected"));
      elements.downloadSelectedFrames.disabled = state.selectedGridFrames.size === 0;
    }
  }

  function bindEvents() {
    [$("importButton"), $("newJobButton"), $("railImport"), $("mobileImportButton"), elements.dropZone].forEach((button) => button.addEventListener("click", () => {
      closeDrawers();
      chooseFile();
    }));
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

    [$("themeToggle"), $("railTheme"), $("mobileThemeButton")].forEach((button) => button.addEventListener("click", toggleTheme));
    $("historyToggle").addEventListener("click", () => openDrawer("history"));
    $("inspectorToggle").addEventListener("click", () => openDrawer("inspector"));
    $("mobileInspectorButton").addEventListener("click", () => openDrawer("inspector"));
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
    elements.mobileCarouselView.addEventListener("click", () => {
      state.viewMode = "carousel";
      updateViewMode();
      renderCurrentFrame();
      closeDrawers();
    });
    elements.mobileGridView.addEventListener("click", () => {
      state.viewMode = "grid";
      updateViewMode();
      closeDrawers();
    });
    elements.mobileVideoView.addEventListener("click", () => {
      if (!state.currentJob?.video_available) return;
      state.viewMode = "video";
      updateViewMode();
      closeDrawers();
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
    [elements.downloadCurrent, elements.downloadFrameOverlay].forEach((button) => button.addEventListener("click", downloadCurrent));
    elements.downloadZip.addEventListener("click", downloadZip);
    elements.downloadSelectedFrames.addEventListener("click", downloadSelectedGridFrames);
    elements.clearSelectedFrames.addEventListener("click", () => {
      state.selectedGridFrames.clear();
      renderGrid();
    });
    elements.transcribeButton.addEventListener("click", startTranscription);
    elements.saveTranscriptionSettings.addEventListener("click", async () => {
      try {
        await saveAccountTranscriptionSettings();
      } catch (error) {
        showToast(error.message, "error");
      }
    });
    elements.removeElevenLabsKey.addEventListener("click", removeElevenLabsApiKey);
    elements.transcriptionProvider.addEventListener("change", syncTranscriptionProvider);
    elements.copyTranscript.addEventListener("click", copyTranscriptText);
    elements.saveTranscript.addEventListener("click", saveTranscriptEdits);
    elements.transcriptionModel.addEventListener("change", () => {
      const selected = (config.transcriptionModels || []).find((model) => model.key === elements.transcriptionModel.value);
      elements.transcriptionModelHelp.textContent = selected?.description || "Local timestamped speech-to-text.";
      elements.transcriptionLanguage.disabled = elements.transcriptionModel.value === "distil-large-v3.5";
      if (elements.transcriptionLanguage.disabled) elements.transcriptionLanguage.value = "en";
    });
    [
      elements.elevenLabsModel,
      elements.elevenLabsDiarize,
      elements.elevenLabsNumSpeakers,
      elements.elevenLabsMultiChannel,
      elements.elevenLabsMultiChannelStyle,
      elements.elevenLabsEntityRedaction,
    ].forEach((control) => control.addEventListener("change", () => {
      const selected = (config.elevenlabsModels || []).find((model) => model.id === elements.elevenLabsModel.value);
      elements.elevenLabsModelHelp.textContent = selected?.description || "ElevenLabs batch speech-to-text.";
      syncElevenLabsDependencies();
    }));
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
    await Promise.all([loadAccountTranscriptionSettings(), refreshHistory(true)]);
  }

  initialize();
})();
