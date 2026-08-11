/* Broadlink2MQTT docs — signal rendering and the capture demo.
 *
 * The waveforms on this page are not decorative. NEC frames are generated from
 * a real address/command pair, and the base64 shown underneath is produced by
 * the same packet encoding the add-on uses (broadlink.remote.pulses_to_data,
 * 32.84 us tick, 0x26 header, repeat count in byte 1).
 */
(function () {
  "use strict";

  var TICK = 32.84;

  /* ---- IR protocol -------------------------------------------------- */

  /** Build a 32-bit NEC frame as signed microsecond timings. */
  function nec(address, command) {
    var t = [9000, -4500];
    var bytes = [address, 255 - address, command, 255 - command];
    bytes.forEach(function (b) {
      for (var i = 0; i < 8; i++) {
        t.push(560);
        t.push((b >> i) & 1 ? -1690 : -560); // LSB first
      }
    });
    t.push(560); // trailer
    return t;
  }

  /** Encode timings into a Broadlink IR packet. Mirrors codec.timings_to_packet. */
  function pulsesToData(timings, repeat) {
    var out = [0x26, repeat || 0, 0, 0];
    timings.forEach(function (t) {
      var n = Math.floor(Math.abs(t) / TICK);
      var div = Math.floor(n / 256);
      var mod = n % 256;
      if (div) {
        out.push(0, div);
      }
      out.push(mod);
    });
    var len = out.length - 4;
    out[2] = len & 0xff;
    out[3] = len >> 8;
    return out;
  }

  function toBase64(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) {
      s += String.fromCharCode(bytes[i]);
    }
    return btoa(s);
  }

  /* ---- Waveform ------------------------------------------------------ */

  /** Square-wave path: positive timings ride high (carrier on), negative low. */
  function wavePath(timings, w, h, pad) {
    var total = timings.reduce(function (a, t) {
      return a + Math.abs(t);
    }, 0);
    if (!total) return "";

    var hi = pad;
    var lo = h - pad;
    var x = 0;
    var d = "";

    timings.forEach(function (t, i) {
      var y = t > 0 ? hi : lo;
      var dx = (Math.abs(t) / total) * w;
      d += (i === 0 ? "M0," : " L" + x.toFixed(2) + ",") + y;
      x += dx;
      d += " L" + x.toFixed(2) + "," + y;
    });

    return d;
  }

  function renderWave(host, timings, animate) {
    var w = 1000;
    var h = 120;
    var d = wavePath(timings, w, h, 20);

    host.innerHTML =
      '<svg viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="none" role="img" ' +
      'aria-label="Infrared signal, ' + timings.length + ' edges">' +
      "<defs>" +
      '<linearGradient id="waveGrad" x1="0" y1="0" x2="1" y2="0">' +
      '<stop offset="0%" stop-color="#ff4a38"/>' +
      '<stop offset="100%" stop-color="#ff7a52"/>' +
      "</linearGradient>" +
      "</defs>" +
      '<path class="wave-path' + (animate ? " wave-draw" : "") + '" d="' + d + '"/>' +
      "</svg>";

    if (animate) {
      var path = host.querySelector("path");
      try {
        var len = path.getTotalLength();
        path.style.setProperty("--len", len);
      } catch (e) {
        /* getTotalLength is unavailable in some headless contexts; the path
           still renders, just without the draw-on animation. */
      }
    }
  }

  function setReadout(scope, timings) {
    var total = timings.reduce(function (a, t) {
      return a + Math.abs(t);
    }, 0);
    var edges = scope.querySelector("[data-edges]");
    var dur = scope.querySelector("[data-duration]");
    if (edges) edges.textContent = timings.length;
    if (dur) dur.textContent = (total / 1000).toFixed(1) + " ms";

    var chip = scope.querySelector("[data-code]");
    if (chip) {
      var b64 = toBase64(pulsesToData(timings, 0));
      chip.innerHTML =
        "base64 <b>" + b64.slice(0, 46) + (b64.length > 46 ? "…" : "") + "</b>";
      chip.title = b64;
    }
  }

  /* ---- Capture demo -------------------------------------------------- */

  // Four plausible remotes, so repeated presses show genuinely different frames.
  var SAMPLES = [
    { name: "TV · Power", timings: nec(0x04, 0x08) },
    { name: "TV · Volume up", timings: nec(0x04, 0x02) },
    { name: "Air conditioner · Mode", timings: nec(0x5e, 0x1a) },
    { name: "Soundbar · Input", timings: nec(0x7f, 0x51) }
  ];

  function initDemo() {
    var scope = document.querySelector("[data-scope]");
    if (!scope) return;

    var body = scope.querySelector("[data-wave]");
    var button = document.querySelector("[data-capture]");
    var status = scope.querySelector("[data-status]");
    var label = scope.querySelector("[data-sample]");
    var index = 0;
    var busy = false;

    // Show the first frame immediately so the panel is never empty.
    renderWave(body, SAMPLES[0].timings, true);
    setReadout(scope, SAMPLES[0].timings);
    if (label) label.textContent = SAMPLES[0].name;

    if (!button) return;

    button.addEventListener("click", function () {
      if (busy) return;
      busy = true;

      button.classList.add("is-listening");
      button.textContent = "Listening…";
      if (status) {
        status.textContent = "learning mode ON";
        status.className = "scope-title";
      }
      body.innerHTML = '<div class="scope-empty">waiting for a signal…</div>';

      window.setTimeout(function () {
        index = (index + 1) % SAMPLES.length;
        var sample = SAMPLES[index];

        renderWave(body, sample.timings, true);
        setReadout(scope, sample.timings);
        if (label) label.textContent = sample.name;
        if (status) status.textContent = "captured";

        button.classList.remove("is-listening");
        button.textContent = "Capture a code";
        busy = false;
      }, 1250);
    });
  }

  /* ---- Static waveforms ---------------------------------------------- */

  function initStaticWaves() {
    document.querySelectorAll("[data-wave-static]").forEach(function (host) {
      renderWave(host, nec(0x04, 0x08), false);
    });
  }

  /* ---- Chrome -------------------------------------------------------- */

  function initNav() {
    var here = location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll(".nav-links a").forEach(function (a) {
      if (a.getAttribute("href") === here) {
        a.setAttribute("aria-current", "page");
      }
    });
  }

  function initReveal() {
    var items = document.querySelectorAll(".reveal");
    if (!items.length) return;

    if (!("IntersectionObserver" in window)) {
      items.forEach(function (el) {
        el.classList.add("in");
      });
      return;
    }

    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
            io.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );

    items.forEach(function (el) {
      io.observe(el);
    });
  }

  function init() {
    initNav();
    initReveal();
    initStaticWaves();
    initDemo();
  }

  // Exported so the encoding can be checked against the add-on's Python codec.
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { nec: nec, pulsesToData: pulsesToData, toBase64: toBase64, wavePath: wavePath };
    return;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
