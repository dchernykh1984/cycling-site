// The protocol page: size the framed protocol to its content, offer fullscreen, and keep a live
// protocol current.
//
// The live loop trusts only what arrives together with the content it puts on screen. Asking
// "has anything changed?" and fetching the content are two requests, and a newer upload can land
// between them -- so the answer to the first is a hint, and the version actually shown, whether it
// is still live and which form it takes are read off the content itself. A newer version is loaded
// into a second, hidden frame and swapped in only once that frame reports it loaded; a frame's load
// event cannot say so (it fires for an error page too, and a sandboxed frame cannot be looked into),
// so until the report arrives the protocol already on screen stays there.
(function () {
  "use strict";

  var wrap = document.getElementById("protocol-wrap");
  if (!wrap) return;
  // A protocol shown as HTML lives in a frame; one drawn from its document is part of the page.
  var frame = document.getElementById("protocol-frame");

  var banner = document.getElementById("live-banner");
  var error = document.getElementById("live-error");
  var data = wrap.dataset;
  var pageFormat = data.format;
  var interval = Number(data.interval) || 60000;
  var loadTimeout = Number(data.loadTimeout) || 20000;
  var shown = { hash: data.hash, isLive: data.live === "true", format: pageFormat };

  var pending = null; // {frame, resolve, reject, timer, size}
  var currentSize = null;
  var inFlight = false;
  var timer = null;
  var stopped = !shown.isLive;

  function applySize(target, size) {
    if (!size) return;
    var h = Math.min(Math.max(size.h, 0), 30000);
    var w = Math.min(Math.max(size.w, 0), 10000);
    target.style.height = h + "px";
    target.style.width = Math.max(wrap.clientWidth, w) + "px";
  }

  window.addEventListener("message", function (e) {
    var msg = e.data;
    if (!msg || typeof msg !== "object") return;
    var fromCurrent = !!frame && e.source === frame.contentWindow;
    var fromPending = pending && e.source === pending.frame.contentWindow;
    if (!fromCurrent && !fromPending) return;
    if (msg.type === "protocol-resize") {
      if (typeof msg.h !== "number" || typeof msg.w !== "number") return;
      var size = { h: msg.h, w: msg.w };
      if (fromCurrent) {
        currentSize = size;
        applySize(frame, size);
      } else {
        pending.size = size;
      }
    } else if (msg.type === "protocol-loaded" && fromPending) {
      if (typeof msg.hash !== "string" || typeof msg.is_live !== "boolean") return;
      var done = pending;
      pending = null;
      clearTimeout(done.timer);
      done.resolve({ hash: msg.hash, isLive: msg.is_live, format: String(msg.shown), frame: done.frame, size: done.size });
    }
  });

  // The frame may have loaded and reported its size before this script started listening.
  if (frame) frame.contentWindow.postMessage({ type: "protocol-measure" }, "*");

  var fsBtn = document.getElementById("fullscreen-btn");
  if (fsBtn && frame) {
    fsBtn.addEventListener("click", function () {
      // An iPhone has no fullscreen for a frame: open the protocol on its own instead. Where the
      // browser refuses the request, the "open separately" link next to the button does the same.
      var request = frame.requestFullscreen || frame.webkitRequestFullscreen;
      if (!request) {
        window.open(document.getElementById("protocol-open-separately").href, "_blank", "noopener");
        return;
      }
      var result = request.call(frame);
      if (result && typeof result.catch === "function") result.catch(function () {});
    });
  }

  if (stopped) return;

  function loadHtml(hash) {
    return new Promise(function (resolve, reject) {
      var next = frame.cloneNode(false);
      next.removeAttribute("id");
      // Laid out off screen rather than hidden, so the size it reports is the size it will have.
      next.style.position = "absolute";
      next.style.left = "-10000px";
      next.style.top = "0";
      next.style.visibility = "hidden";
      next.style.width = wrap.clientWidth + "px";
      next.setAttribute("aria-hidden", "true");
      var attempt = { frame: next, resolve: resolve, reject: reject, size: null };
      attempt.timer = setTimeout(function () {
        if (pending === attempt) pending = null;
        next.remove();
        reject(new Error("protocol did not load"));
      }, loadTimeout);
      pending = attempt;
      next.src = data.htmlUrl + "?v=" + encodeURIComponent(hash);
      wrap.appendChild(next);
    });
  }

  // The drawn document: the response carries the state of the row it was drawn from, and a body
  // only while the protocol still has a document -- an empty one with "html" means it no longer does.
  function loadDocument() {
    return fetch(data.fragmentUrl, { cache: "no-store" }).then(function (r) {
      var hash = r.headers.get("X-Protocol-Hash");
      var type = r.headers.get("Content-Type") || "";
      if (!r.ok || hash === null || type.indexOf("text/html") !== 0) throw new Error("status " + r.status);
      var meta = {
        hash: hash,
        isLive: r.headers.get("X-Protocol-Live") === "true",
        format: r.headers.get("X-Protocol-Shown"),
      };
      if (meta.format !== pageFormat) return meta;
      return r.text().then(function (html) {
        var holder = document.createElement("div");
        holder.innerHTML = html;
        meta.root = holder.querySelector("#protocol-doc");
        if (!meta.root) throw new Error("no document in the response");
        return meta;
      });
    });
  }

  function swapDocument(loaded) {
    var old = document.getElementById("protocol-doc");
    old.replaceWith(loaded.root);
    if (window.ProtocolDocument) window.ProtocolDocument.mount(loaded.root);
  }

  function swapIn(loaded) {
    var old = frame;
    var next = loaded.frame;
    next.style.position = "";
    next.style.left = "";
    next.style.top = "";
    next.style.visibility = "";
    next.removeAttribute("aria-hidden");
    next.id = "protocol-frame";
    frame = next;
    old.remove();
    currentSize = loaded.size || currentSize;
    applySize(frame, currentSize);
  }

  function finish() {
    stopped = true;
    clearTimeout(timer);
    if (banner) {
      banner.className = "alert alert-success mb-3";
      banner.textContent = data.textFinal;
    }
  }

  function schedule(delay) {
    clearTimeout(timer);
    timer = null;
    if (stopped || document.hidden) return;
    timer = setTimeout(poll, delay);
  }

  function poll() {
    if (inFlight || stopped) return;
    inFlight = true;
    clearTimeout(timer);
    fetch(data.pollUrl, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error("status " + r.status);
        return r.json();
      })
      .then(function (meta) {
        if (meta.file_hash === shown.hash && meta.is_live === shown.isLive && meta.shown === pageFormat) return;
        // The fragment answers for either form (its headers carry the row's state), so it is
        // asked whenever the page draws a document or the hint names one; a framed HTML page
        // asks it too when the frame fails, in case the HTML is gone because the protocol
        // became data only between the hint and the load.
        var load =
          pageFormat === "document" || meta.shown === "document"
            ? loadDocument()
            : loadHtml(meta.file_hash).catch(function (failure) {
                return loadDocument().then(function (state) {
                  if (state.format === pageFormat) throw failure;
                  return state;
                });
              });
        return load.then(function (loaded) {
          if (loaded.format !== pageFormat) {
            // The protocol now takes another form: the server draws that page, not this one.
            if (loaded.frame) loaded.frame.remove();
            stopped = true;
            window.location.reload();
            return;
          }
          if (pageFormat === "document") swapDocument(loaded);
          else swapIn(loaded);
          shown = { hash: loaded.hash, isLive: loaded.isLive, format: loaded.format };
          if (!shown.isLive) finish();
        });
      })
      .then(function () {
        if (error) error.hidden = true;
      })
      .catch(function () {
        // Keep what is on screen; the next round tries again, final or not, so the last results
        // still arrive after a failed attempt.
        if (error) error.hidden = false;
      })
      .then(function () {
        inFlight = false;
        schedule(interval);
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      clearTimeout(timer);
      timer = null;
    } else if (!inFlight) {
      poll();
    }
  });

  schedule(interval);
})();
