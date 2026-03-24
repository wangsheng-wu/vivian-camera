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

  if (cameraStatusDot) {
    cameraStatusDot.classList.remove("live", "mock");
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

function setupFixedControlHints() {
  const controls = document.querySelectorAll(".adjustable-control.is-disabled[data-fixed-hint]");

  controls.forEach((button) => {
    const valueEl = button.querySelector(".control-value");
    if (!valueEl) return;

    const originalValue = valueEl.textContent;
    const hintText = button.dataset.fixedHint;
    let resetTimer = null;

    button.addEventListener("click", () => {
      if (resetTimer) {
        clearTimeout(resetTimer);
      }

      valueEl.textContent = hintText;
      button.classList.add("show-hint");

      resetTimer = window.setTimeout(() => {
        valueEl.textContent = originalValue;
        button.classList.remove("show-hint");
        resetTimer = null;
      }, 1200);
    });
  });
}

function setupAdjustableControls() {
  const picker = document.getElementById("control-picker");
  const pickerTitle = document.getElementById("control-picker-title");
  const pickerCurrent = document.getElementById("control-picker-current");
  const pickerViewport = document.getElementById("control-picker-viewport");
  const pickerList = document.getElementById("control-picker-list");

  if (!picker || !pickerTitle || !pickerCurrent || !pickerViewport || !pickerList) {
    return;
  }

  const itemHeight = 40;
  const viewportHeight = 188;
  const centerY = (viewportHeight - itemHeight) / 2;

  let activeButton = null;
  let activeOptions = [];
  let selectedIndex = 0;
  let currentOffset = 0;

  let isDragging = false;
  let dragStartY = 0;
  let dragStartOffset = 0;
  let didDragDuringPointer = false;
  let suppressViewportClick = false;

  function clampIndex(index) {
    if (activeOptions.length === 0) return 0;
    return Math.max(0, Math.min(index, activeOptions.length - 1));
  }

  function getOffsetForIndex(index) {
    return centerY - index * itemHeight;
  }

  function getNearestIndexFromOffset(offset) {
    const rawIndex = (centerY - offset) / itemHeight;
    return clampIndex(Math.round(rawIndex));
  }

  function updateListTransform() {
    pickerList.style.transform = `translateY(${currentOffset}px)`;
  }

  function refreshItemStates() {
    const items = pickerList.querySelectorAll(".control-picker-item");
    items.forEach((item, index) => {
      item.classList.remove("is-selected", "is-near");

      if (index === selectedIndex) {
        item.classList.add("is-selected");
      } else if (Math.abs(index - selectedIndex) === 1) {
        item.classList.add("is-near");
      }
    });

    if (pickerCurrent) {
      pickerCurrent.textContent = activeOptions[selectedIndex] ?? "";
    }
  }

  function buildItems(options) {
    pickerList.innerHTML = "";
  
    options.forEach((value, index) => {
      const item = document.createElement("div");
      item.className = "control-picker-item";
      item.textContent = value;
      item.dataset.index = String(index);
  
      item.addEventListener("click", (event) => {
        event.stopPropagation();
  
        const isAlreadySelected = index === selectedIndex;
  
        selectedIndex = index;
        currentOffset = getOffsetForIndex(selectedIndex);
  
        updateListTransform();
        refreshItemStates();
        syncActiveButtonValue();
  
        if (isAlreadySelected) {
          commitSelection();
        }
      });
  
      pickerList.appendChild(item);
    });
  }

  function openPicker(button) {
    if (!button || button.classList.contains("is-disabled")) return;

    const options = (button.dataset.options || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    if (options.length === 0) return;

    document.querySelectorAll(".adjustable-control.is-open").forEach((el) => {
      el.classList.remove("is-open");
    });

    activeButton = button;
    activeOptions = options;

    const labelEl = button.querySelector(".control-label");
    const valueEl = button.querySelector(".control-value");

    const currentValue = valueEl ? valueEl.textContent.trim() : "";
    const matchedIndex = activeOptions.findIndex((option) => option === currentValue);

    selectedIndex = matchedIndex >= 0 ? matchedIndex : 0;
    currentOffset = getOffsetForIndex(selectedIndex);

    pickerTitle.textContent = labelEl ? labelEl.textContent.trim() : "Control";

    buildItems(activeOptions);
    updateListTransform();
    refreshItemStates();

    button.classList.add("is-open");
    picker.classList.add("is-visible");
    picker.setAttribute("aria-hidden", "false");
  }

  function closePicker() {
    picker.classList.remove("is-visible");
    picker.setAttribute("aria-hidden", "true");

    document.querySelectorAll(".adjustable-control.is-open").forEach((el) => {
      el.classList.remove("is-open");
    });

    activeButton = null;
    activeOptions = [];
    selectedIndex = 0;
    currentOffset = 0;
    isDragging = false;
  }

  function commitSelection() {
    closePicker();
  }

  function syncActiveButtonValue() {
    if (!activeButton) return;
  
    const valueEl = activeButton.querySelector(".control-value");
    const nextValue = activeOptions[selectedIndex];
  
    if (valueEl && nextValue) {
      valueEl.textContent = nextValue;
    }
  }

  function updateSelectionFromOffset(offset) {
    if (!activeOptions.length) return;
  
    const minOffset = getOffsetForIndex(activeOptions.length - 1);
    const maxOffset = getOffsetForIndex(0);
  
    currentOffset = Math.max(minOffset, Math.min(maxOffset, offset));
    selectedIndex = getNearestIndexFromOffset(currentOffset);
  
    updateListTransform();
    refreshItemStates();
    syncActiveButtonValue();
  }

  pickerViewport.addEventListener("pointerdown", (event) => {
    if (!activeButton) return;

    isDragging = true;
    dragStartY = event.clientY;
    dragStartOffset = currentOffset;
    didDragDuringPointer = false;

    pickerViewport.setPointerCapture(event.pointerId);
  });

  pickerViewport.addEventListener("pointermove", (event) => {
    if (!isDragging) return;

    const deltaY = event.clientY - dragStartY;
    if (Math.abs(deltaY) > 3) {
      didDragDuringPointer = true;
    }
    updateSelectionFromOffset(dragStartOffset + deltaY);
  });

  pickerViewport.addEventListener("pointerup", (event) => {
    if (!isDragging) return;
  
    isDragging = false;
    pickerViewport.releasePointerCapture(event.pointerId);
  
    currentOffset = getOffsetForIndex(selectedIndex);
    updateListTransform();
    refreshItemStates();

    if (didDragDuringPointer) {
      suppressViewportClick = true;
      window.setTimeout(() => {
        suppressViewportClick = false;
      }, 0);
    }
  });

  pickerViewport.addEventListener("pointercancel", () => {
    if (!isDragging) return;

    isDragging = false;
    currentOffset = getOffsetForIndex(selectedIndex);
    updateListTransform();
    refreshItemStates();
  });

  pickerViewport.addEventListener("click", (event) => {
    if (!activeButton) return;
    if (suppressViewportClick) return;

    const rect = pickerViewport.getBoundingClientRect();
    const clickY = event.clientY - rect.top;
    const highlightTop = centerY;
    const highlightBottom = centerY + itemHeight;

    if (clickY >= highlightTop && clickY <= highlightBottom) {
      commitSelection();
    }
  });

  document.querySelectorAll(".adjustable-control[data-control]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();

      const isPickerVisible = picker.classList.contains("is-visible");
      const isSameButton = activeButton === button;

      if (isPickerVisible && isSameButton) {
        closePicker();
        return;
      }

      openPicker(button);
    });
  });

  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
  
    if (picker.contains(target)) return;
    if (target.closest(".adjustable-control[data-control]")) return;
  
    closePicker();
  });

  document.addEventListener("keydown", (event) => {
    if (!picker.classList.contains("is-visible")) return;

    if (event.key === "Escape") {
      closePicker();
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      selectedIndex = clampIndex(selectedIndex - 1);
      currentOffset = getOffsetForIndex(selectedIndex);
      updateListTransform();
      refreshItemStates();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      selectedIndex = clampIndex(selectedIndex + 1);
      currentOffset = getOffsetForIndex(selectedIndex);
      updateListTransform();
      refreshItemStates();
      return;
    }

    if (event.key === "Enter") {
      event.preventDefault();
      commitSelection();
    }
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const refreshButton = document.getElementById("refresh-status-btn");

  fetchStatus();
  statusTimer = window.setInterval(fetchStatus, 1000);

  if (refreshButton) {
    refreshButton.addEventListener("click", fetchStatus);
  }

  setupPreviewHealthCheck();
  setupFixedControlHints();
  setupAdjustableControls();
});