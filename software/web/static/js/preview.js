async function updateStatus() {
    const res = await fetch("/status");
    const data = await res.json();
  
    document.getElementById("status").innerText =
      `Frames: ${data.frame_count} | Uptime: ${data.uptime_sec}s`;
}
  
setInterval(updateStatus, 1000);
  
function capture() {
    alert("Capture coming next step 🚀");
}