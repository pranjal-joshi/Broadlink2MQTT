# Broadlink2MQTT Docs Site

Static documentation site for the Broadlink2MQTT Home Assistant add-on, served
by GitHub Pages at **https://pranjal-joshi.github.io/Broadlink2MQTT/**.

## How it's deployed

- Source: the `docs/` folder on the `main` branch.
- Deployed by `.github/workflows/pages.yml` using the GitHub Pages actions.
- Pure static HTML, CSS and one JS file — no build step. Edits go live on push.

## Pages

| File | Purpose |
|---|---|
| `index.html` | Landing page — signal path, capture demo, entities, hardware |
| `install.html` | Add-on repository install, plain Docker, architecture support |
| `configuration.html` | Every option, plus the MQTT topic map |
| `usage.html` | Capturing, sending, and automation recipes |
| `faq.html` | FAQ and troubleshooting |
| `404.html` | Error page |
| `assets/style.css` | Design system |
| `assets/app.js` | Waveform rendering, capture demo, scroll reveal |

## Design

The site is built around one idea: **the page is the bridge it describes.**

- **Infrared red** `#ff4a38` is the device side. **Home Assistant blue**
  `#41bdf5` is the HA side. A red-to-blue gradient means a signal is being
  converted between them — it is never used decoratively.
- Card and device geometry echoes the RM4 mini's rounded-square silhouette
  (20–24px radii).
- Dark only, deliberately: the hardware is matte black, and the IR glow only
  reads against a dark ground.
- Fonts: Sora (headings), Inter (body), JetBrains Mono (code and readouts).

This intentionally **does not** share the NeuraMesh theme used by `opencode`
and `moodlights` — it is device-specific by request.

## The waveforms are real

`assets/app.js` generates genuine 32-bit NEC frames from an address/command
pair, and encodes them with the same packet format the add-on uses:
32.84 µs tick, `0x26` header, repeat count in byte 1.

The output is verified byte-identical to the Python codec:

```bash
# reference, from the add-on's own codec
PYTHONPATH=broadlink2mqtt/src python -c "..."   # see git history

# the browser implementation
node -e "const b=require('./docs/assets/app.js'); \
         console.log(b.toBase64(b.pulsesToData(b.nec(4,8),0)))"
```

`app.js` exports `nec`, `pulsesToData`, `toBase64` and `wavePath` under
CommonJS specifically so this check can be run.

## Local preview

```bash
cd docs && python -m http.server 8000
# then open http://localhost:8000
```

Opening `index.html` directly over `file://` also works.
