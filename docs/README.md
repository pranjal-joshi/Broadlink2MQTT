# Broadlink2MQTT Docs Site

Static documentation site for the Broadlink2MQTT Home Assistant add-on, served
by GitHub Pages at **https://pranjal-joshi.github.io/Broadlink2MQTT/**.

## How it's deployed

- Source: the `docs/` folder on the `main` branch.
- Deployed by `.github/workflows/pages.yml` using the GitHub Pages actions.
- Pure static HTML + CSS — no build step. Edits to `docs/` go live on push.

## Pages

| File | Purpose |
|---|---|
| `index.html` | Landing page — why the add-on exists, entities, supported devices |
| `install.html` | Add-on repository install, plain Docker, architecture support |
| `configuration.html` | Every option, plus the MQTT topic map |
| `usage.html` | Capturing, sending, and automation recipes |
| `faq.html` | FAQ and troubleshooting |
| `404.html` | Error page |
| `assets/style.css` | Shared dark NeuraMesh theme |

## Theme

Dark theme: background `#0b1326`, primary `#4edea3`, gold `#e9c349`, blue
`#5ea0ff`. Fonts: Space Grotesk (headings), Manrope (body), JetBrains Mono
(code).

Shared with the [opencode](https://github.com/pranjal-joshi/opencode) docs site.
The only local addition is a `blockquote` rule, used on the landing page to
quote the core PR review.
