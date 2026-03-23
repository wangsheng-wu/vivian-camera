let frameRefreshTimer = null;
let isPreviewRunning = false;

async function fetchStatus() {
  try {
    const response = await fetch("/status", { cache: "no-store" });
    const data = await response.json();
    applyStatus(data);

    if (data.connected) {
      startPreviewLoop();
    } else {
      stopPreviewLoop();
    }
  } catch (error) {
    applyDisconnectedState();
    stopPreviewLoop();
  }
}

function applyStatus(data) {
  const statusText = document.getElementById("status-text");
  const statusDot = document.getElementById("status-dot");

  const resolutionValue = document.getElementById("resolution-value");
  const fpsValue = document.getElementById("fps-value");
  const frameCountValue = document.getElementById("frame-count-value");
  const uptimeValue = document.getElementById("uptime-value");

  const leftIndexValue = document.getElementById("left-index-value");
  const rightIndexValue = document.getElementById("right-index-value");
  const frameAgeValue = document.getElementById("frame-age-value");

  if (statusText) {
    statusText.textContent = data.status_text || "Ready";
  }

  if (statusDot) {
    if (data.connected) {
      statusDot.classList.add("live");
    } else {
      statusDot.classList.remove("live");
    }
  }

  if (resolutionValue) resolutionValue.textContent = data.resolution ?? "--";
  if (fpsValue) fpsValue.textContent = data.target_fps ?? "--";
  if (frameCountValue) frameCountValue.textContent = data.frame_count ?? "--";
  if (uptimeValue) uptimeValue.textContent = data.uptime ?? "--";

  if (leftIndexValue) leftIndexValue.textContent = data.left_camera_index ?? "--";
  if (rightIndexValue) rightIndexValue.textContent = data.right_camera_index ?? "--";
  if (frameAgeValue) frameAgeValue.textContent = data.last_frame_age ?? "--";
}

function applyDisconnectedState() {
  const statusText = document.getElementById("status-text");
  const statusDot = document.getElementById("status-dot");

  if (statusText) {
    statusText.textContent = "Disconnected";
  }

  if (statusDot) {
    statusDot.classList.remove("live");
  }
}

function refreshPreviewFrame() {
  const previewImage = document.getElementById("preview-image");
  if (!previewImage) return;

  const cacheBust = `t=${Date.now()}`;
  previewImage.src = `/frame.jpg?${cacheBust}`;
}

function startPreviewLoop() {
  if (isPreviewRunning) return;

  isPreviewRunning = true;
  refreshPreviewFrame();

  frameRefreshTimer = window.setInterval(() => {
    refreshPreviewFrame();
  }, 120);
}

function stopPreviewLoop() {
  if (frameRefreshTimer !== null) {
    window.clearInterval(frameRefreshTimer);
    frameRefreshTimer = null;
  }
  isPreviewRunning = false;
}

document.addEventListener("DOMContentLoaded", () => {
  const refreshButton = document.getElementById("refresh-status-btn");

  fetchStatus();
  window.setInterval(fetchStatus, 1000);

  if (refreshButton) {
    refreshButton.addEventListener("click", fetchStatus);
  }
});