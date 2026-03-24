let statusTimer = null;
let previewHealthTimer = null;

function applyStatus(data) {
  const statusText = document.getElementById("status-text");
  const statusDot = document.getElementById("status-dot");

  const cameraStatusText = document.getElementById("camera-status-text");
  const cameraStatusDot = document.getElementById("camera-status-dot");

  const resolutionValue = document.getElementById("resolution-value");
  const fpsValue = document.getElementById("fps-value");
  const frameCountValue = document.getElementById("frame-count-value");
  const uptimeValue = document.getElementById("uptime-value");

  const leftIndexValue = document.getElementById("left-index-value");
  const rightIndexValue = document.getElementById("right-index-value");
  const frameAgeValue = document.getElementById("frame-age-value");

  const kind = data.status_kind || "disconnected";

  if (statusText) {
    statusText.textContent = data.status_text || "Ready";
  }

  if (statusDot) {
    statusDot.classList.remove("live", "mock");
    if (kind === "ready") {
      statusDot.classList.add("live");
    } else if (kind === "mock") {
      statusDot.classList.add("mock");
    }
  }

  if (cameraStatusText) {
    if (kind === "ready") {
      cameraStatusText.textContent = "Dual cameras ready";
    } else if (kind === "mock") {
      cameraStatusText.textContent = "Cameras are not available in mock mode";
    } else {
      cameraStatusText.textContent = "Camera disconnected";
    }
  }

  if (cameraStatusDot) {
    cameraStatusDot.classList.remove("live", "mock");
    if (kind === "ready") {
      cameraStatusDot.classList.add("live");
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

  const cameraStatusText = document.getElementById("camera-status-text");
  const cameraStatusDot = document.getElementById("camera-status-dot");

  if (statusText) {
    statusText.textContent = "Disconnected";
  }

  if (statusDot) {
    statusDot.classList.remove("live", "mock");
  }

  if (cameraStatusText) {
    cameraStatusText.textContent = "Camera disconnected";
  }

}

async function fetchStatus() {
  try {
    const response = await fetch("/status", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Status HTTP ${response.status}`);
    }

    const data = await response.json();
    applyStatus(data);
  } catch (error) {
    applyDisconnectedState();
  }
}

function restartPreviewStream() {
  const previewImage = document.getElementById("preview-image");
  if (!previewImage) return;

  const nextSrc = `/stream.mjpg?t=${Date.now()}`;
  previewImage.src = nextSrc;
}

function setupPreviewHealthCheck() {
  const previewImage = document.getElementById("preview-image");
  if (!previewImage) return;

  previewImage.addEventListener("error", () => {
    setTimeout(() => {
      restartPreviewStream();
    }, 500);
  });

  previewHealthTimer = window.setInterval(async () => {
    try {
      const response = await fetch("/status", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("Status request failed");
      }

      const data = await response.json();
      applyStatus(data);

      if (!data.connected) {
        restartPreviewStream();
        return;
      }

      const ageText = String(data.last_frame_age ?? "");
      const ageValue = Number.parseFloat(ageText.replace("s", ""));
      if (!Number.isNaN(ageValue) && ageValue > 1.5) {
        restartPreviewStream();
      }
    } catch (error) {
      applyDisconnectedState();
      restartPreviewStream();
    }
  }, 2000);
}

document.addEventListener("DOMContentLoaded", () => {
  const refreshButton = document.getElementById("refresh-status-btn");

  fetchStatus();
  statusTimer = window.setInterval(fetchStatus, 1000);

  if (refreshButton) {
    refreshButton.addEventListener("click", fetchStatus);
  }

  setupPreviewHealthCheck();
});



function setupFixedControlHints() {
  const controls = document.querySelectorAll('.adjustable-control.is-disabled[data-fixed-hint]');

  controls.forEach((button) => {
    const valueEl = button.querySelector('.control-value');
    if (!valueEl) return;

    const originalValue = valueEl.textContent;
    const hintText = button.dataset.fixedHint;
    let resetTimer = null;

    button.addEventListener('click', () => {
      if (resetTimer) {
        clearTimeout(resetTimer);
      }

      valueEl.textContent = hintText;
      button.classList.add('show-hint');

      resetTimer = window.setTimeout(() => {
        valueEl.textContent = originalValue;
        button.classList.remove('show-hint');
        resetTimer = null;
      }, 1200);
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  setupFixedControlHints();
});