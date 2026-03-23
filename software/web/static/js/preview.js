async function fetchStatus() {
    try {
      const response = await fetch("/status");
      const data = await response.json();
      applyStatus(data);
    } catch (error) {
      applyDisconnectedState();
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
  
    statusText.textContent = data.status_text || "Ready";
  
    if (data.connected) {
      statusDot.classList.add("live");
    } else {
      statusDot.classList.remove("live");
    }
  
    resolutionValue.textContent = data.resolution ?? "--";
    fpsValue.textContent = data.target_fps ?? "--";
    frameCountValue.textContent = data.frame_count ?? "--";
    uptimeValue.textContent = data.uptime ?? "--";
  
    leftIndexValue.textContent = data.left_camera_index ?? "--";
    rightIndexValue.textContent = data.right_camera_index ?? "--";
    frameAgeValue.textContent = data.last_frame_age ?? "--";
}
  
function applyDisconnectedState() {
    const statusText = document.getElementById("status-text");
    const statusDot = document.getElementById("status-dot");
  
    statusText.textContent = "Disconnected";
    statusDot.classList.remove("live");
}
  
document.addEventListener("DOMContentLoaded", () => {
    const refreshButton = document.getElementById("refresh-status-btn");
  
    fetchStatus();
    setInterval(fetchStatus, 1000);
  
    if (refreshButton) {
      refreshButton.addEventListener("click", fetchStatus);
    }
});