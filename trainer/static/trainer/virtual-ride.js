// "Open full screen" puts the trainer's frame on the whole screen, as a protocol's button does, and Escape brings the
// page back. Where a frame cannot go full screen (an iPhone) the link does what it says without a script: it opens
// the trainer on a page of its own.
(function () {
  var link = document.getElementById("virtual-ride-fullscreen");
  var frame = document.querySelector(".virtual-ride-frame");
  if (!link || !frame) return;
  link.addEventListener("click", function (event) {
    var request = frame.requestFullscreen || frame.webkitRequestFullscreen;
    if (!request || !(document.fullscreenEnabled || document.webkitFullscreenEnabled)) return;
    event.preventDefault();
    var result = request.call(frame);
    frame.focus(); // the trainer's keys (power, gears, pause) reach it, not the page behind
    if (result && typeof result.catch === "function") result.catch(function () {});
  });
})();
