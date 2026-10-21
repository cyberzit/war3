"""Modern 2026 AAA Esports Dark Glassmorphic Landing Page for MongolRanger (https://mongolranger.com)."""

PUBLIC_HTML = r"""<!DOCTYPE html>
<html lang="mn" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MongolRanger — Warcraft III &amp; DotA Online Gaming Platform</title>
<meta name="description" content="Монголын Warcraft III 1.26a болон DotA Allstars / LoD онлайн тоглоомын шинэ үеийн платформ. Албан ёсны суулгагч (Installer), 5-15ms Ping, 3 минутын Crash Reconnect, Anti-MapHack, ELO чансааны систем, WarKey.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Plus+Jakarta+Sans:wght@600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-deep: #05070e;
    --bg-surface: #0b0f1c;
    --glass-bg: rgba(16, 22, 38, 0.68);
    --glass-bg-hover: rgba(22, 30, 52, 0.82);
    --glass-border: rgba(255, 255, 255, 0.08);
    --glass-border-strong: rgba(139, 92, 246, 0.42);
    --text-main: #f8fafc;
    --text-sec: #94a3b8;
    --text-muted: #64748b;
    --violet: #8b5cf6;
    --violet-deep: #6d28d9;
    --indigo: #6366f1;
    --emerald: #10b981;
    --emerald-glow: #34d399;
    --amber: #f59e0b;
    --rose: #f43f5e;
  }

  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  html {
    scroll-behavior: smooth;
    background-color: var(--bg-deep);
    color: var(--text-main);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    -webkit-font-smoothing: antialiased;
  }

  body {
    min-height: 100vh;
    background-color: var(--bg-deep);
    overflow-x: hidden;
    position: relative;
    line-height: 1.6;
  }

  /* Atmospheric Ambient Mesh Glows */
  .ambient-canvas {
    position: fixed;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
  }
  .orb-violet {
    position: absolute;
    top: -180px;
    left: 12%;
    width: 760px;
    height: 540px;
    background: radial-gradient(circle, rgba(124, 58, 237, 0.22) 0%, rgba(99, 102, 241, 0.06) 45%, transparent 72%);
    filter: blur(60px);
  }
  .orb-emerald {
    position: absolute;
    top: 240px;
    right: -120px;
    width: 640px;
    height: 640px;
    background: radial-gradient(circle, rgba(16, 185, 129, 0.14) 0%, rgba(6, 182, 212, 0.05) 48%, transparent 72%);
    filter: blur(70px);
  }
  .grid-overlay {
    position: absolute;
    inset: 0;
    background-image:
      linear-gradient(to right, rgba(255,255,255,0.025) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(255,255,255,0.025) 1px, transparent 1px);
    background-size: 48px 48px;
    mask-image: radial-gradient(ellipse 80% 60% at 50% 25%, #000 30%, transparent 100%);
    -webkit-mask-image: radial-gradient(ellipse 80% 60% at 50% 25%, #000 30%, transparent 100%);
  }

  .container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 0 24px;
    position: relative;
    z-index: 1;
  }

  h1, h2, h3, h4, .brand-font {
    font-family: 'Plus Jakarta Sans', 'Inter', sans-serif;
    letter-spacing: -0.025em;
  }

  .mono {
    font-family: 'JetBrains Mono', monospace;
  }

  a {
    color: inherit;
    text-decoration: none;
  }

  /* Floating Glass Navbar */
  .nav-wrapper {
    position: sticky;
    top: 16px;
    z-index: 100;
    padding: 0 24px;
    margin-top: 16px;
  }
  .navbar {
    max-width: 1280px;
    margin: 0 auto;
    height: 68px;
    background: rgba(10, 14, 26, 0.82);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-radius: 18px;
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 18px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
    white-space: nowrap;
  }
  .brand-logo {
    width: 40px;
    height: 40px;
    border-radius: 11px;
    background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 55%, #10b981 100%);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 0 24px rgba(124, 58, 237, 0.45);
    flex-shrink: 0;
  }
  .brand-logo svg {
    width: 22px;
    height: 22px;
    fill: #fff;
  }
  .brand-name {
    font-size: 19px;
    font-weight: 800;
    color: #fff;
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }

  .nav-links {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    flex: 1;
  }
  .nav-links a {
    padding: 8px 13px;
    border-radius: 10px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-sec);
    transition: all 0.2s ease;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .nav-links a:hover {
    color: #fff;
    background: rgba(255, 255, 255, 0.06);
  }

  .nav-right {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }
  .live-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 7px 14px;
    border-radius: 999px;
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.28);
    font-size: 12.5px;
    font-weight: 600;
    color: #34d399;
    white-space: nowrap;
  }
  .pulse-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #10b981;
    box-shadow: 0 0 12px #10b981;
    animation: pulseGlow 2s infinite;
  }
  @keyframes pulseGlow {
    0%, 100% { transform: scale(1); opacity: 1; }
    50% { transform: scale(1.25); opacity: 0.65; }
  }

  .btn-nav-dl {
    padding: 9px 18px;
    border-radius: 11px;
    font-size: 13.5px;
    font-weight: 700;
    color: #fff;
    background: linear-gradient(135deg, #7c3aed 0%, #6366f1 100%);
    box-shadow: 0 6px 20px rgba(124, 58, 237, 0.38);
    transition: all 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    white-space: nowrap;
  }
  .btn-nav-dl:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(124, 58, 237, 0.55);
  }

  /* Hero Section */
  .hero {
    padding: 56px 0 48px;
    display: grid;
    grid-template-columns: 0.96fr 1.24fr;
    gap: 40px;
    align-items: center;
  }

  .release-pill {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 6px 14px 6px 8px;
    border-radius: 999px;
    background: rgba(139, 92, 246, 0.12);
    border: 1px solid rgba(139, 92, 246, 0.32);
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .release-pill .tag {
    background: linear-gradient(135deg, #7c3aed, #10b981);
    color: #fff;
    font-size: 11px;
    font-weight: 800;
    padding: 3px 9px;
    border-radius: 999px;
    letter-spacing: 0.04em;
  }
  .release-pill span {
    font-size: 13px;
    font-weight: 600;
    color: #ddd6fe;
  }

  .hero h1 {
    font-size: clamp(32px, 3.4vw, 44px);
    font-weight: 800;
    line-height: 1.15;
    margin-bottom: 18px;
    color: #ffffff;
  }
  .hero h1 .grad-text {
    background: linear-gradient(135deg, #a78bfa 0%, #60a5fa 50%, #34d399 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .hero-lead {
    font-size: 16px;
    color: var(--text-sec);
    margin-bottom: 26px;
    max-width: 560px;
    line-height: 1.68;
  }
  .hero-lead strong {
    color: #f1f5f9;
    font-weight: 600;
  }

  .hero-cta-group {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 22px;
  }

  .btn-hero-exe {
    display: inline-flex;
    align-items: center;
    gap: 14px;
    padding: 15px 26px;
    border-radius: 16px;
    background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
    color: #fff;
    box-shadow: 0 16px 40px rgba(124, 58, 237, 0.42), inset 0 1px 0 rgba(255, 255, 255, 0.25);
    transition: all 0.22s ease;
    border: 1px solid rgba(167, 139, 250, 0.4);
  }
  .btn-hero-exe:hover {
    transform: translateY(-2px);
    box-shadow: 0 20px 48px rgba(124, 58, 237, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.35);
  }
  .btn-hero-exe svg {
    width: 26px;
    height: 26px;
    fill: currentColor;
    flex-shrink: 0;
  }
  .btn-hero-exe .btn-text-col {
    display: flex;
    flex-direction: column;
    text-align: left;
  }
  .btn-hero-exe .main-lbl {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 16px;
    font-weight: 800;
    line-height: 1.2;
  }
  .btn-hero-exe .sub-lbl {
    font-size: 11.5px;
    color: rgba(255, 255, 255, 0.82);
    font-weight: 500;
    margin-top: 2px;
  }

  .btn-hero-secondary {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 15px 22px;
    border-radius: 16px;
    background: rgba(17, 24, 39, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #f8fafc;
    font-weight: 700;
    font-size: 14.5px;
    transition: all 0.2s ease;
    backdrop-filter: blur(12px);
  }
  .btn-hero-secondary:hover {
    background: rgba(30, 41, 59, 0.9);
    border-color: rgba(52, 211, 153, 0.45);
    transform: translateY(-2px);
  }

  .trust-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 9px;
  }
  .trust-chip {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 7px 12px;
    border-radius: 10px;
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.07);
    font-size: 12px;
    color: #cbd5e1;
    font-weight: 600;
  }
  .trust-chip svg {
    width: 15px;
    height: 15px;
    color: #34d399;
  }

  /* v4.8 Real Screenshot Showcase (Right Column) */
  .client-mockup-wrap {
    position: relative;
  }
  .client-glow-backdrop {
    position: absolute;
    inset: -16px;
    background: linear-gradient(135deg, rgba(124, 58, 237, 0.36), rgba(16, 185, 129, 0.24));
    filter: blur(38px);
    border-radius: 28px;
    z-index: 0;
    opacity: 0.8;
  }
  .client-window {
    position: relative;
    z-index: 1;
    background: #070a13;
    border: 1.5px solid rgba(139, 92, 246, 0.42);
    border-radius: 18px;
    overflow: hidden;
    box-shadow: 0 30px 80px rgba(0, 0, 0, 0.8);
  }
  .client-screenshot-img {
    width: 100%;
    height: auto;
    display: block;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .client-caption-bar {
    padding: 11px 16px;
    background: rgba(11, 15, 28, 0.95);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 12px;
    color: #cbd5e1;
  }

  /* Section Headers */
  .section {
    padding: 56px 0;
  }
  .sec-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 20px;
    margin-bottom: 32px;
    flex-wrap: wrap;
  }
  .sec-eyebrow {
    font-size: 12px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #a78bfa;
    margin-bottom: 8px;
  }
  .sec-title {
    font-size: clamp(26px, 3vw, 36px);
    font-weight: 800;
    color: #fff;
  }
  .sec-desc {
    color: var(--text-sec);
    font-size: 15px;
    max-width: 680px;
    margin-top: 6px;
  }

  /* Download Hub Cards */
  .dl-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
  }
  .steps-bar {
    margin-top: 24px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 18px;
  }
  .step-item {
    background: rgba(12, 17, 30, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
    padding: 20px 22px;
    display: flex;
    align-items: flex-start;
    gap: 14px;
  }
  .step-num {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: linear-gradient(135deg, #7c3aed, #10b981);
    color: #fff;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .step-body h4 {
    font-size: 15px;
    font-weight: 800;
    color: #fff;
    margin-bottom: 4px;
  }
  .step-body p {
    font-size: 13px;
    color: var(--text-sec);
    line-height: 1.55;
  }
  .dl-card {
    background: var(--glass-bg);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid var(--glass-border);
    border-radius: 22px;
    padding: 28px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
  }
  .dl-card.featured {
    border-color: rgba(139, 92, 246, 0.48);
    background: linear-gradient(180deg, rgba(124, 58, 237, 0.12) 0%, rgba(16, 22, 38, 0.78) 45%);
    box-shadow: 0 20px 50px rgba(124, 58, 237, 0.15);
  }
  .dl-card:hover {
    transform: translateY(-4px);
    border-color: rgba(139, 92, 246, 0.65);
    background: var(--glass-bg-hover);
  }

  .dl-card-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 18px;
  }
  .dl-os-icon {
    width: 52px;
    height: 52px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(139, 92, 246, 0.15);
    border: 1px solid rgba(139, 92, 246, 0.32);
    color: #c4b5fd;
  }
  .dl-os-icon svg {
    width: 26px;
    height: 26px;
    fill: currentColor;
  }
  .dl-ver-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    font-weight: 700;
    padding: 5px 11px;
    border-radius: 999px;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #34d399;
  }

  .dl-card h3 {
    font-size: 20px;
    font-weight: 800;
    margin-bottom: 6px;
    color: #fff;
  }
  .dl-platform {
    font-size: 12.5px;
    font-weight: 600;
    color: #a78bfa;
    margin-bottom: 14px;
  }
  .dl-desc {
    font-size: 13.5px;
    color: var(--text-sec);
    margin-bottom: 20px;
    line-height: 1.6;
  }
  .dl-check-list {
    list-style: none;
    margin-bottom: 24px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .dl-check-list li {
    font-size: 13px;
    color: #cbd5e1;
    position: relative;
    padding-left: 26px;
    line-height: 1.62;
    display: block;
  }
  .dl-check-list li::before {
    content: "✓";
    position: absolute;
    left: 0;
    top: 3px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 17px;
    height: 17px;
    border-radius: 50%;
    background: rgba(16, 185, 129, 0.18);
    color: #34d399;
    font-size: 10px;
    font-weight: 900;
  }
  .bento-card p strong,
  .dl-check-list li strong {
    color: #f8fafc;
    font-weight: 700;
  }
  .bento-card code,
  .dl-check-list code,
  .cmd-card code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 600;
    color: #ddd6fe;
    background: rgba(139, 92, 246, 0.16);
    border: 1px solid rgba(139, 92, 246, 0.3);
    padding: 1px 6px;
    border-radius: 5px;
    white-space: nowrap;
  }

  .btn-dl-action {
    width: 100%;
    padding: 13px 18px;
    border-radius: 13px;
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 14px;
    font-weight: 800;
    text-align: center;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 9px;
    transition: all 0.2s ease;
  }
  .btn-dl-action.primary {
    background: linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%);
    color: #fff;
    box-shadow: 0 10px 25px rgba(124, 58, 237, 0.35);
  }
  .btn-dl-action.primary:hover {
    box-shadow: 0 14px 32px rgba(124, 58, 237, 0.55);
  }
  .btn-dl-action.secondary {
    background: rgba(30, 41, 59, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #fff;
  }
  .btn-dl-action.secondary:hover {
    background: rgba(51, 65, 85, 0.95);
    border-color: rgba(167, 139, 250, 0.45);
  }

  /* Bento Advantages & Ping Comparison */
  .bento-grid {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 20px;
  }
  .bento-card {
    background: var(--glass-bg);
    backdrop-filter: blur(20px);
    border: 1px solid var(--glass-border);
    border-radius: 22px;
    padding: 26px;
    transition: all 0.25s ease;
  }
  .bento-card:hover {
    border-color: rgba(139, 92, 246, 0.42);
    transform: translateY(-2px);
  }
  .span-7 { grid-column: span 7; }
  .span-5 { grid-column: span 5; }
  .span-6 { grid-column: span 6; }
  .span-4 { grid-column: span 4; }
  .span-8 { grid-column: span 8; }
  .span-12 { grid-column: span 12; }

  .ping-bars {
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .ping-bar-item {
    background: rgba(10, 14, 24, 0.75);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 12px 15px;
  }
  .ping-bar-top {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    font-weight: 700;
    margin-bottom: 7px;
  }
  .ping-track {
    height: 8px;
    background: #161f33;
    border-radius: 99px;
    overflow: hidden;
  }
  .ping-fill {
    height: 100%;
    border-radius: 99px;
  }

  .feature-icon-box {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: rgba(139, 92, 246, 0.14);
    border: 1px solid rgba(139, 92, 246, 0.3);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    margin-bottom: 14px;
  }
  .bento-card h3 {
    font-size: 18.5px;
    font-weight: 800;
    margin-bottom: 8px;
    color: #fff;
  }
  .bento-card p {
    font-size: 13.5px;
    color: var(--text-sec);
    line-height: 1.65;
  }

  /* ELO System Rules Cards & Tier Table */
  .elo-formula-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-top: 16px;
  }
  .elo-stat-pill {
    background: rgba(10, 14, 26, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 14px;
  }
  .elo-stat-pill .val {
    font-family: 'JetBrains Mono', monospace;
    font-size: 19px;
    font-weight: 800;
    margin-bottom: 4px;
  }
  .elo-stat-pill .lbl {
    font-size: 12.5px;
    color: var(--text-sec);
  }

  .tier-grid {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
    margin-top: 16px;
  }
  .tier-box {
    background: rgba(10, 14, 26, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 12px;
    text-align: center;
  }
  .tier-box .t-lvl {
    font-weight: 800;
    font-size: 13.5px;
    margin-bottom: 3px;
  }
  .tier-box .t-range {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11.5px;
    color: #94a3b8;
  }

  /* Commands Grid */
  .cmd-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
    gap: 16px;
  }
  .cmd-card {
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    border-radius: 18px;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    transition: all 0.2s ease;
  }
  .cmd-card:hover {
    border-color: rgba(52, 211, 153, 0.45);
    transform: translateY(-2px);
  }
  .cmd-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
  }
  .cmd-code {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13.5px;
    font-weight: 700;
    color: #34d399;
    background: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.32);
    padding: 4px 10px;
    border-radius: 8px;
  }
  .cmd-role {
    font-size: 11px;
    font-weight: 700;
    padding: 3px 9px;
    border-radius: 99px;
    background: rgba(139, 92, 246, 0.16);
    color: #c4b5fd;
  }

  /* Maps Catalog Grid */
  .maps-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
    gap: 18px;
  }
  .map-card {
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    border-radius: 18px;
    padding: 22px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    transition: all 0.2s ease;
  }
  .map-card:hover {
    border-color: rgba(52, 211, 153, 0.45);
    transform: translateY(-2px);
  }
  .map-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin: 12px 0 16px;
  }
  .m-tag {
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 99px;
  }
  .m-tag.emerald {
    background: rgba(16, 185, 129, 0.14);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
  }
  .m-tag.violet {
    background: rgba(139, 92, 246, 0.14);
    color: #c4b5fd;
    border: 1px solid rgba(139, 92, 246, 0.3);
  }
  .map-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-top: 14px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
  }
  .btn-map-dl {
    padding: 8px 15px;
    border-radius: 10px;
    background: rgba(124, 58, 237, 0.2);
    border: 1px solid rgba(139, 92, 246, 0.4);
    color: #e9d5ff;
    font-size: 12.5px;
    font-weight: 700;
    transition: all 0.2s;
  }
  .btn-map-dl:hover {
    background: #7c3aed;
    color: #fff;
  }

  /* Live Lobbies Table */
  .lobby-glass-box {
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    border-radius: 20px;
    overflow: hidden;
  }
  .lobby-table {
    width: 100%;
    border-collapse: collapse;
  }
  .lobby-table th {
    text-align: left;
    padding: 15px 20px;
    font-size: 11.5px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    background: rgba(8, 12, 22, 0.65);
    border-bottom: 1px solid var(--glass-border);
  }
  .lobby-table td {
    padding: 16px 20px;
    font-size: 13.5px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  }
  .lobby-empty {
    padding: 36px 24px;
    text-align: center;
    color: var(--text-sec);
    font-size: 14px;
  }

  footer {
    margin-top: 60px;
    padding: 36px 0 48px;
    border-top: 1px solid rgba(255, 255, 255, 0.07);
    color: var(--text-muted);
    font-size: 13px;
  }
  .footer-flex {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 16px;
  }

  @media (max-width: 1024px) {
    .hero { grid-template-columns: 1fr; }
    .dl-grid { grid-template-columns: 1fr; }
    .steps-bar { grid-template-columns: 1fr; }
    .span-7, .span-5, .span-6, .span-4, .span-8, .span-12 { grid-column: span 12; }
    .tier-grid { grid-template-columns: repeat(2, 1fr); }
    .nav-links { display: none; }
  }
</style>
</head>
<body>

<div class="ambient-canvas">
  <div class="orb-violet"></div>
  <div class="orb-emerald"></div>
  <div class="grid-overlay"></div>
</div>

<!-- Sticky Glass Navigation -->
<div class="nav-wrapper">
  <header class="navbar">
    <a href="#" class="brand">
      <div class="brand-logo">
        <svg viewBox="0 0 24 24"><path d="M4 4h4l4 7 4-7h4v16h-3.5V10.5L12 18l-4.5-7.5V20H4V4z"/></svg>
      </div>
      <div class="brand-name brand-font">
        MongolRanger
      </div>
    </a>

    <nav class="nav-links">
      <a href="#downloads">Програм Татах</a>
      <a href="#advantages">Давуу Талууд</a>
      <a href="#elo-rules">ELO Дүрэм</a>
      <a href="#commands">Командууд</a>
      <a href="#maps">Газрын Зураг</a>
      <a href="#lobbies">Өрөөнүүд</a>
    </nav>

    <div class="nav-right">
      <div class="live-chip">
        <span class="pulse-dot"></span>
        <span id="navLiveStats">Онлайн • <strong id="statRooms">0</strong> өрөө</span>
      </div>
      <a id="navQuickDl" href="/api/downloads/client_win/file" class="btn-nav-dl">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        <span>Суулгагч Татах</span>
      </a>
    </div>
  </header>
</div>

<main class="container">
  <!-- Hero Section -->
  <section class="hero">
    <div>
      <div class="release-pill">
        <span class="tag">v4.8 ESPORT</span>
        <span>Шинэ ELO Чансаа • 3 мин Reconnect • Anti-MapHack • Ухаалаг WarKey</span>
      </div>

      <h1>
        Warcraft III &amp; DotA<br>
        <span class="grad-text">Монголын Esport Платформ</span>
      </h1>

      <p class="hero-lead">
        Нэг товчоор суудаг албан ёсны <strong>Installer</strong> суулгагчаа татаад шууд нэвтэрч тоглоорой.
        Дотоодын <strong>5–15ms Ping</strong>, <strong>3 минутын Crash Reconnect &amp; Rejoin</strong>, <strong>3 давхар Anti-MapHack</strong>, <strong>5v5 ELO Чансаа</strong> болон <strong>WarKey</strong> бүгд нэг дор бүрэн суурилагдсан.
      </p>

      <div class="hero-cta-group">
        <a id="heroWinBtn" href="/api/downloads/client_win/file" class="btn-hero-exe">
          <svg viewBox="0 0 24 24"><path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/></svg>
          <div class="btn-text-col">
            <span class="main-lbl" id="heroWinText">Програм Татах (Installer)</span>
            <span class="sub-lbl">Windows 7 / 8 / 10 / 11 • Автомат суулгагч</span>
          </div>
        </a>

        <a id="heroGameBtn" href="/api/downloads/game_full/file" class="btn-hero-secondary">
          <span>🎮</span>
          <span id="heroGameText">Warcraft III 1.26a Татах</span>
        </a>
      </div>

      <div class="trust-badges">
        <div class="trust-chip">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          3 Давхар Anti-MapHack
        </div>
        <div class="trust-chip">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
          Монгол дотор 5–15ms Ping
        </div>
        <div class="trust-chip">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          3 Минут Crash Reconnect
        </div>
        <div class="trust-chip">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>
          5v5 ELO Чансааны Систем
        </div>
      </div>
    </div>

    <!-- Real v4.8 Client UI Screenshot Showcase -->
    <div class="client-mockup-wrap">
      <div class="client-glow-backdrop"></div>
      <div class="client-window">
        <img src="/assets/mongolranger_v48_ui_preview.png" alt="MongolRanger v4.8 Esport Client Interface" class="client-screenshot-img">
        <div class="client-caption-bar">
          <span>✨ <strong>MongolRanger v4.8</strong> — 5 үндсэн газрын сан, Топ 100 ELO, Найзууд &amp; Чат, WarKey, Автомат War3 Patch</span>
          <a href="#downloads" style="color:#34d399;font-weight:800">Суулгагч татах →</a>
        </div>
      </div>
    </div>
  </section>

  <!-- 1. DOWNLOAD HUB -->
  <section id="downloads" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Official Downloads</div>
        <h2 class="sec-title">Тоглоомын Програм &amp; Бүрэн Багц Татах</h2>
        <p class="sec-desc">Windows 7 / 8 / 8.1 / 10 / 11 (32-bit ба 64-bit) бүх хувилбар дээр шууд сууж ажиллах албан ёсны суулгагч болон Warcraft III 1.26a бүрэн багц.</p>
      </div>
    </div>

    <div class="dl-grid" id="downloadsGrid">
      <div class="dl-card featured">
        <div>
          <div class="dl-card-top">
            <div class="dl-os-icon">
              <svg viewBox="0 0 24 24"><path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/></svg>
            </div>
            <span class="dl-ver-badge">v4.8 Installer</span>
          </div>
          <h3>MongolRanger Тоглоомын Програм (Windows)</h3>
          <div class="dl-platform">Windows 7 / 8 / 8.1 / 10 / 11 (32-bit &amp; 64-bit — Бүх хувилбарт ажиллана)</div>
          <p class="dl-desc">Windows-ийн бүх хувилбар дээр шууд сууж Desktop дээр дүрсээ үүсгээд нээгддэг албан ёсны суулгагч. 3 минутын Reconnect, Anti-MapHack, WarKey болон ELO чансаа багтсан.</p>
          <ul class="dl-check-list">
            <li>Windows 7, 8, 8.1, 10, 11 (32-bit &amp; 64-bit) бүрэн дэмжинэ</li>
            <li>Warcraft III хавтсыг өөрөө олж Reconnect Patch суулгана</li>
            <li>Суурилагдсан WarKey + 3 минутын Crash Reconnect</li>
          </ul>
        </div>
        <a href="/api/downloads/client_win/file" class="btn-dl-action primary">
          ⬇️ Програм Татах (Installer)
        </a>
      </div>

      <div class="dl-card">
        <div>
          <div class="dl-card-top">
            <div class="dl-os-icon">
              <svg viewBox="0 0 24 24"><path d="M12 2L4 5v6.09c0 5.05 3.41 9.76 8 10.91 4.59-1.15 8-5.86 8-10.91V5l-8-3zm0 4.5l4.5 1.75v4.2c0 3.1-2.02 5.95-4.5 6.85-2.48-.9-4.5-3.75-4.5-6.85v-4.2L12 6.5z"/></svg>
            </div>
            <span class="dl-ver-badge">1.26a Албан ёсны</span>
          </div>
          <h3>Warcraft III: Frozen Throne 1.26a + DotA Багц</h3>
          <div class="dl-platform">Windows 7 / 8 / 10 / 11 (Шууд тоглоход бэлэн • 847 MB)</div>
          <p class="dl-desc">Тоглоом суулгаагүй компьютер дээр задлаад шууд тоглоход бэлэн Warcraft III 1.26a үндсэн тоглоом болон 5 үндсэн DotA / LoD газрын зургийн бүрэн багц.</p>
          <ul class="dl-check-list">
            <li>Warcraft III 1.26a бэлэн тохиргоотой үндсэн тоглоом</li>
            <li>Албан ёсны 5 үндсэн DotA Allstars &amp; LoD газрын зураг</li>
            <li>MongolRanger програм автоматаар таньж холбоно</li>
          </ul>
        </div>
        <a href="/api/downloads/game_full/file" class="btn-dl-action secondary">
          ⬇️ Warcraft III 1.26a Татах
        </a>
      </div>
    </div>

    <div class="steps-bar">
      <div class="step-item">
        <div class="step-num">1</div>
        <div class="step-body">
          <h4>Програм суулгах</h4>
          <p><strong>MongolRanger</strong> суулгагчаа татаж ажиллуулна. Windows 7, 8, 10, 11 бүх хувилбар дээр Desktop дүрс үүсгэн шууд нээгдэнэ.</p>
        </div>
      </div>
      <div class="step-item">
        <div class="step-num">2</div>
        <div class="step-body">
          <h4>Warcraft III хавтас холбох</h4>
          <p>Тохиргоо цэсэнд өөрийн <strong>Warcraft III 1.26a</strong> хавтсыг зааж өгөхөд Reconnect Patch болон 5 үндсэн Map автоматаар сууна.</p>
        </div>
      </div>
      <div class="step-item">
        <div class="step-num">3</div>
        <div class="step-body">
          <h4>Өрөөнд нэгдэж тоглох</h4>
          <p>Лобби жагсаалтаас өрөө сонгоод <strong>«▶ Нэгдэх»</strong> дарахад тоглоом автоматаар асч <code>Local Area Network</code> дотор өрөө гарч ирнэ.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- 2. ALL PLATFORM ADVANTAGES BENTO GRID -->
  <section id="advantages" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Platform Advantages</div>
        <h2 class="sec-title">MongolRanger Платформын Бүх Давуу Талууд</h2>
        <p class="sec-desc">Хуучны P2P платформуудын гацалт, Fatal Error, MapHack болон Leaver-ийн асуудлыг орчин үеийн Төв Хост Серверийн технологиор 100% шийдвэрлэв.</p>
      </div>
    </div>

    <div class="bento-grid">
      <!-- Ping & Dedicated Host -->
      <div class="bento-card span-7">
        <div class="feature-icon-box">⚡</div>
        <h3>Монгол Төв Хост Сервер (5–15ms Ping &amp; 0% Lag)</h3>
        <p>
          Хуучны P2P платформууд дээр өрөө нээсэн (Host) хүний гэрийн интернэтээс хамаарч бусад тоглогчид гацах эсвэл нэг хүн гацахад бүх 10 тоглогч дагаж гацдаг.
          Харин <strong>MongolRanger</strong> дээр тоглогч бүр Улаанбаатар дахь Төв Сервертэй шууд холбогддог:
        </p>
        <div class="ping-bars">
          <div class="ping-bar-item">
            <div class="ping-bar-top">
              <span>🇲🇳 Улаанбаатар хот дотор (Univision / Mobinet / Skymedia)</span>
              <span style="color:#34d399">5 – 15 ms (LAN мэт шууд)</span>
            </div>
            <div class="ping-track"><div class="ping-fill" style="width:12%;background:linear-gradient(90deg,#10b981,#34d399)"></div></div>
          </div>
          <div class="ping-bar-item">
            <div class="ping-bar-top">
              <span>🏞️ Дархан, Эрдэнэт болон 21 Аймаг</span>
              <span style="color:#60a5fa">15 – 35 ms (Маш хурдан)</span>
            </div>
            <div class="ping-track"><div class="ping-fill" style="width:26%;background:linear-gradient(90deg,#3b82f6,#60a5fa)"></div></div>
          </div>
          <div class="ping-bar-item">
            <div class="ping-bar-top">
              <span>🌍 Гадаадаас (Солонгос, Япон, Европ, Америк)</span>
              <span style="color:#a78bfa">75 – 115 ms (Тогтвортой Dedicated)</span>
            </div>
            <div class="ping-track"><div class="ping-fill" style="width:52%;background:linear-gradient(90deg,#8b5cf6,#a78bfa)"></div></div>
          </div>
        </div>
      </div>

      <!-- 3-Minute Reconnect & Rejoin -->
      <div class="bento-card span-5" style="border-color:rgba(16,185,129,0.38)">
        <div class="feature-icon-box" style="background:rgba(16,185,129,0.16);border-color:rgba(16,185,129,0.4)">🔄</div>
        <h3>3 Минутын Crash Reconnect &amp; Rejoin</h3>
        <p style="margin-bottom:12px">
          Тоглолтын дунд <strong>Fatal Error</strong> заах, тог тасрах эсвэл интернэт унахад тоглолт шууд нурахгүй! Сервер <strong>180 секунд (3 минут)</strong> хүлээх бөгөөд та <strong>«🔄 ТОГЛОЛТОНД БУЦАЖ ОРОХ»</strong> товчийг дараад яг зогссон газраасаа баатар, алт, item, skill-тэйгээ буцаж орно.
        </p>
        <div style="background:rgba(16,185,129,0.09);border:1px solid rgba(16,185,129,0.3);border-radius:13px;padding:12px 14px;font-size:12.5px;color:#d1fae5">
          <strong>⏱️ +1 Минут Цаг Сунгах (-addtime):</strong> Найзын тань компьютер удаан асаж байвал багийнхан нь <code>-addtime</code> бичиж хүлээх хугацааг 3 удаа (+3 минут) сунгах боломжтой.
        </div>
      </div>

      <!-- 3-Layer Anti-MapHack & HWID Shield -->
      <div class="bento-card span-4">
        <div class="feature-icon-box">🛡️</div>
        <h3>3 Давхар Anti-MapHack &amp; HWID Shield</h3>
        <p>
          Warcraft III хавтас доторх хууль бус <code>.mix</code>, <code>.asi</code>, <code>.flt</code>, proxy <code>.dll</code> файлууд болон гадны MapHack процессуудыг автоматаар илрүүлж устгана. Компьютерийн <strong>HWID</strong> хамгаалалтаар хуурамч хаяг нээж тоглолт үймүүлэхийг бүрэн хязгаарлана.
        </p>
      </div>

      <!-- Alt+F4 Block & Anti-Leaver System -->
      <div class="bento-card span-4">
        <div class="feature-icon-box">🚫</div>
        <h3>Alt+F4 Хаалт &amp; Leaver Хамгаалалт</h3>
        <p>
          Тоглолт эхэлсэн үед <strong>Alt+F4</strong> товчийг автоматаар идэвхгүй болгоно. Өрөө нээхдээ <strong>«🛡️ Leaver оруулахгүй»</strong> сонголтыг асааж болно. Тоглолт хаясан хүний нэрний ард <strong>45 минутын турш улаан «🚨 Хаяж гарсан»</strong> тэмдэг бусад тоглогчдод ил харагдана.
        </p>
      </div>

      <!-- Smart Built-In WarKey & QuickChat -->
      <div class="bento-card span-4">
        <div class="feature-icon-box">⌨️</div>
        <h3>Ухаалаг WarKey &amp; QuickChat Макро</h3>
        <p>
          Гаднаас нэмэлт програм татахгүйгээр <strong>6 Inventory слот</strong>, <strong>8 Skill слот</strong> болон <strong>QuickChat</strong> хурдан мессежийг хүссэн товчин дээрээ тааруулна. Лобби болон тоглоом дотор Enter дарж чат бичих үед WarKey автоматаар унтарна (<code>Ctrl+F5</code>).
        </p>
      </div>

      <!-- 5 Official Maps Auto-Sync & Smart War3 Folder Detection -->
      <div class="bento-card span-6">
        <div class="feature-icon-box">🗺️</div>
        <h3>5 Үндсэн Газрын Сан &amp; Автомат War3 Patch</h3>
        <p>
          <strong>DotA v6.85m LoD, v6.74c LoD v5e, v6.83d Allstars, v6.85l LoD, v6.85k Allstars</strong> гэсэн 5 албан ёсны газрын зураг, <strong>4GB RAM Crash-Protect (LAA)</strong> болон Reconnect Patch автоматаар сууна. Та <code>D:\Games</code> гэх мэт ерөнхий хавтас сонгосон ч програм доторх дэд хавтаснаас Warcraft III-ийг өөрөө олж тохируулна!
        </p>
      </div>

      <!-- Social, Email Login & Name Change -->
      <div class="bento-card span-6">
        <div class="feature-icon-box">💬</div>
        <h3>И-мэйл Нэвтрэлт, Нэр Солих &amp; Найзуудын Систем</h3>
        <p>
          Тусгай тэмдэгттэй тоглолтын нэрээ санах шаардлагагүйгээр <strong>И-мэйл хаягаараа</strong> шууд нэвтэрч, нууц үгээ сэргээнэ. Хүссэн үедээ <strong>«✏️ Нэр»</strong> товчоор тоглолтын нэрээ солих, найз нэмэх, хувийн чат бичих, өрөөнд урих болон тоглогч бүрийн сүүлийн 10 тоглолтын түүхийг харна.
        </p>
      </div>
    </div>
  </section>

  <!-- 3. ELO SYSTEM RULES -->
  <section id="elo-rules" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Competitive Ranking Rules</div>
        <h2 class="sec-title">🏆 ELO Чансааны Систем ба Дүрэм</h2>
        <p class="sec-desc">MongolRanger-ийн ELO чансааны систем нь зөвхөн багийн ялалтаас гадна тоглогч бүрийн хувийн ур чадвар (Kill / Death / Assist)-ийг шударгаар үнэлдэг.</p>
      </div>
    </div>

    <div class="bento-grid">
      <!-- Rule 1 & 2: 5v5 Requirement & 10-Match Calibration -->
      <div class="bento-card span-6" style="border-color:rgba(139,92,246,0.4)">
        <div class="feature-icon-box">⏳</div>
        <h3>1. Түвшин Тогтоох 10 Тоглолт (5v5 Calibration)</h3>
        <p style="margin-bottom:12px">
          Хуурамч тоглолт (1v1, 2v2 найзтайгаа хуйвалдах)-аас сэргийлж <strong>зөвхөн 5v5 (10 тоглогчтой)</strong> бүрэлдэхүүнтэй эхэлж, үндсэн барилга (World Tree / Frozen Throne) нурж дууссан эсвэл <strong>15 минутаас хойш <code>-gg</code> командаар</strong> дууссан тоглолтонд ELO болон Kill тооцогдоно.
        </p>
        <ul class="dl-check-list" style="margin-bottom:0">
          <li>Эхний <strong>10 удаагийн 5v5 тоглолт</strong> дуустал ELO оноо нууцлагдмал (<code>⏳ X/10 (5v5)</code>) байна.</li>
          <li>Яг 10 дахь 5v5 тоглолт дуусмагц таны <strong>Winrate (Хожлын хувь)</strong>, <strong>K/D харьцаа</strong>, <strong>Дундаж Kill</strong> болон <strong>Leave</strong>-ээс хамаарч <strong>500 – 1800 ELO</strong> гарааны чансаа бодогдож нээгдэнэ.</li>
          <li>10 тоглолт гүйцээгээгүй тоглогч Топ 100 ELO самбарт харагдахгүй.</li>
        </ul>
      </div>

      <!-- Rule 3: Match ELO Formula -->
      <div class="bento-card span-6">
        <div class="feature-icon-box">📊</div>
        <h3>2. Тоглолт Бүрийн Оноо Бодох Зарчим</h3>
        <p>
          5v5 Ranked тоглолт бүрийн төгсгөлд багийн үр дүн дээр таны хувийн Kill, Assist, Death нэмэгдэж тооцогдоно (нэг тоглолтонд дээд тал нь <strong>+60 ELO</strong>, доод тал нь <strong>-45 ELO</strong>):
        </p>
        <div class="elo-formula-grid">
          <div class="elo-stat-pill">
            <div class="val" style="color:#34d399">+25 ELO</div>
            <div class="lbl">🏆 Баг хожиход (Үндсэн оноо)</div>
          </div>
          <div class="elo-stat-pill">
            <div class="val" style="color:#f87171">-15 ELO</div>
            <div class="lbl">💔 Баг хожигдоход (Үндсэн)</div>
          </div>
          <div class="elo-stat-pill">
            <div class="val" style="color:#38bdf8">+3 ELO</div>
            <div class="lbl">🗡️ 1 Kill хийх бүрд</div>
          </div>
          <div class="elo-stat-pill">
            <div class="val" style="color:#a78bfa">+1 ELO</div>
            <div class="lbl">🤝 1 Assist хийх бүрд</div>
          </div>
          <div class="elo-stat-pill">
            <div class="val" style="color:#fbbf24">-1 ELO</div>
            <div class="lbl">💀 3-аас дээших үхэл тутамд</div>
          </div>
          <div class="elo-stat-pill">
            <div class="val" style="color:#ef4444">-50 ELO</div>
            <div class="lbl">🚨 Тоглолт хаяж гарахад (Leave)</div>
          </div>
        </div>
      </div>

      <!-- Rule 4: Carry Protection, Feeder Damper & Redemption -->
      <div class="bento-card span-12">
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px">
          <div style="background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.28);border-radius:15px;padding:18px">
            <h4 style="color:#34d399;font-size:16px;font-weight:800;margin-bottom:6px">🔥 Carry Protection (Сайн тоглогчийн хамгаалалт)</h4>
            <p style="font-size:13px;color:#cbd5e1">
              Хэрэв таны баг хожигдсон ч та ганцаараа сайн тоглож <strong>10 болон түүнээс дээш Kill</strong> хийсэн бөгөөд <code>Kill &gt; Death</code> байвал таны ELO <strong>огт хасагдахгүй</strong> — харин ч доод тал нь <strong>+8 ELO</strong> (эсвэл түүнээс дээш) нэмэгдэнэ!
            </p>
          </div>
          <div style="background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.28);border-radius:15px;padding:18px">
            <h4 style="color:#fbbf24;font-size:16px;font-weight:800;margin-bottom:6px">🛑 Feeder Damper (Сул тоглолтын хязгаар)</h4>
            <p style="font-size:13px;color:#cbd5e1">
              Хэрэв баг тань хожсон ч та <strong>0 Kill</strong> хийж, <strong>8 ба түүнээс дээш удаа үхсэн (Death)</strong> бол багийн хожлын бүтэн оноог авахгүй бөгөөд дээд тал нь <strong>+5 ELO</strong> л авна.
            </p>
          </div>
          <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.28);border-radius:15px;padding:18px">
            <h4 style="color:#c4b5fd;font-size:16px;font-weight:800;margin-bottom:6px">🛡️ Redemption (Leave цэвэрших систем)</h4>
            <p style="font-size:13px;color:#cbd5e1">
              Тоглолт хаяж гарвал <strong>-50 ELO</strong> болон <strong>+1 Leave</strong> торгууль авна. Харин дараа нь <strong>3 удаа дараалан</strong> 5v5 тоглолтыг дундаас нь гаралгүй бүтэн дуусгавал таны Leave тоо автоматаар <strong>-1-ээр хасагдаж цэвэршинэ</strong>!
            </p>
          </div>
        </div>

        <h4 style="margin-top:24px;font-size:15px;font-weight:800;color:#fff">🎖️ ELO Түвшин ба Цолны Хүснэгт (LVL 1 – LVL 10)</h4>
        <div class="tier-grid">
          <div class="tier-box"><div class="t-lvl" style="color:#94a3b8">LVL 1 • Bronze</div><div class="t-range">100 – 599 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#a1a1aa">LVL 2 • Bronze</div><div class="t-range">600 – 899 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#34d399">LVL 3 • Silver</div><div class="t-range">900 – 1199 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#10b981">LVL 4 • Silver</div><div class="t-range">1200 – 1499 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#fbbf24">LVL 5 • Gold</div><div class="t-range">1500 – 1899 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#f59e0b">LVL 6 • Gold</div><div class="t-range">1900 – 2299 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#38bdf8">LVL 7 • Diamond</div><div class="t-range">2300 – 2799 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#818cf8">LVL 8 • Diamond</div><div class="t-range">2800 – 3399 ELO</div></div>
          <div class="tier-box"><div class="t-lvl" style="color:#f97316">LVL 9 • Master Pro</div><div class="t-range">3400 – 4199 ELO</div></div>
          <div class="tier-box" style="border-color:rgba(239,68,68,0.45)"><div class="t-lvl" style="color:#ef4444">👑 LVL 10 • LEGEND</div><div class="t-range">4200 – 5000 ELO</div></div>
        </div>
      </div>
    </div>
  </section>

  <!-- 4. IN-GAME & LOBBY COMMANDS GUIDE -->
  <section id="commands" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Commands &amp; Hotkeys</div>
        <h2 class="sec-title">⌨️ Тоглоомын Командууд ба Заавар</h2>
        <p class="sec-desc">Warcraft III лобби болон тоглолтын дундуур чат дээр бичиж ашиглах албан ёсны командууд.</p>
      </div>
    </div>

    <div class="cmd-grid">
      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-start &nbsp;/&nbsp; -s &nbsp;/&nbsp; -go</span>
          <span class="cmd-role">👑 Зөвхөн Host</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Тоглолт эхлүүлэх (Автомат мөнгө хасалт)</h4>
        <p style="font-size:13px;color:var(--text-sec)">Warcraft III лобби дотор Host бичиж тоглолтыг эхлүүлнэ. 1v1, 2v2, 3v3 үед хоосон суудлуудад автоматаар <code>Computer (Normal)</code> орж гарааны мөнгө 853 gold болно.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-1v1 &nbsp;/&nbsp; -normal &nbsp;/&nbsp; -close 2</span>
          <span class="cmd-role">👑 Зөвхөн Host</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Слот хааж Computer оруулах (Мөнгө хасах)</h4>
        <p style="font-size:13px;color:var(--text-sec)"><code>-1v1</code>, <code>-2v2</code>, <code>-3v3</code>, <code>-4v4</code> эсвэл <code>-easy</code>, <code>-normal</code>, <code>-insane</code>, <code>-close 2-5</code> бичиж хоосон суудалд Computer оруулна (<code>-open</code> буцааж нээх, эсвэл Host өөрийн мөрний <code>100%</code> цэсийг дарж тохируулна).</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-swap 2 6</span>
          <span class="cmd-role">👑 Зөвхөн Host</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Суудал солих (Swap Slots)</h4>
        <p style="font-size:13px;color:var(--text-sec)">Лобби дотор тоглолт эхлэхээс өмнө 2 болон 6-р суудлын тоглогчдын байрыг хооронд нь шууд солино.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-addtime &nbsp;/&nbsp; -wait</span>
          <span class="cmd-role">👥 Бүх тоглогч</span>
        </div>
        <h4 style="color:#fff;font-size:15px">+1 Минут хүлээх хугацаа сунгах</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглогч гараад хүлээж байх үед (Waiting цонх гарсан үед ч гаран дээр шууд бичихэд ажиллана) хүлээх цагийг +60 секундээр сунгана (3 эрхтэй).</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-rmk &nbsp;/&nbsp; -warda</span>
          <span class="cmd-role">👥 60% Саналаар</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Тоглолтыг дахин эхлүүлэх (Remake)</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглолтын эхний <strong>5 минутын дотор</strong> тоглогчдын олонх нь бичвэл ELO болон оноо тооцохгүйгээр тоглолтыг цуцалж шинээр эхлүүлнэ.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-gg &nbsp;/&nbsp; -ff</span>
          <span class="cmd-role">🏳️ 15+ Минутаас хойш</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Бууж өгөх санал (Forfeit)</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглолт эхлээд <strong>15 минут</strong> өнгөрсний дараа багийн олонх зөвшөөрвөл бууж өгч, эсрэг багт ялалт болон 5v5 ELO оноо тооцогдоно.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">-cam 2400 &nbsp;/&nbsp; -cam 1.4</span>
          <span class="cmd-role">🎥 Камер тохиргоо</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Камерын өндөр тааруулах</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглоом дотроо камерын зайг өөрийн дэлгэцэнд тохируулан <code>1.0–2.0</code> эсвэл <code>1650–2800</code> хооронд хүссэнээрээ холдуулж тааруулна.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">Ctrl + F5</span>
          <span class="cmd-role">⌨️ Гарны товч</span>
        </div>
        <h4 style="color:#fff;font-size:15px">WarKey шууд асаах / унтраах</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглоом дотроос Alt+Tab хийж гаралгүйгээр WarKey-г шууд идэвхжүүлэх эсвэл түр унтраана.</p>
      </div>

      <div class="cmd-card">
        <div class="cmd-head">
          <span class="cmd-code">Alt + F4 (Түгжигдсэн)</span>
          <span class="cmd-role">🛡️ Хамгаалалт</span>
        </div>
        <h4 style="color:#fff;font-size:15px">Санамсаргүй гарахаас сэргийлсэн</h4>
        <p style="font-size:13px;color:var(--text-sec)">Тоглолт эхэлсэн үед Alt+F4 автоматаар идэвхгүй болно. Зайлшгүй гарах шаардлагатай бол <code>F10 → Quit Mission</code> дарна.</p>
      </div>
    </div>
  </section>

  <!-- 5. OFFICIAL MAPS CATALOG -->
  <section id="maps" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Official Map Catalog</div>
        <h2 class="sec-title">Албан Ёсны 5 Үндсэн Газрын Зураг</h2>
        <p class="sec-desc">Програмаар өрөөнд ороход бүх газрын зураг автоматаар татагдана. Эсвэл доорх жагсаалтаас шууд татаж авах боломжтой.</p>
      </div>
    </div>
    <div id="mapsGrid" class="maps-grid">
      <div class="map-card">
        <div style="color:var(--text-sec)">Газрын зургийн жагсаалтыг ачаалж байна...</div>
      </div>
    </div>
  </section>

  <!-- 6. LIVE LOBBIES -->
  <section id="lobbies" class="section">
    <div class="sec-head">
      <div>
        <div class="sec-eyebrow">Real-Time Matchmaking</div>
        <h2 class="sec-title">Одоо Идэвхтэй Байгаа Өрөөнүүд</h2>
        <p class="sec-desc">MongolRanger програмаа нээгээд доорх өрөөнүүд рүү шууд нэгдэн тоглоорой.</p>
      </div>
    </div>

    <div class="lobby-glass-box">
      <table class="lobby-table">
        <thead>
          <tr>
            <th>Өрөөний нэр</th>
            <th>Газрын зураг (Map)</th>
            <th>Тоглогчид</th>
            <th>Төлөв</th>
          </tr>
        </thead>
        <tbody id="liveRoomsBody">
          <tr>
            <td colspan="4" class="lobby-empty">Ачаалж байна...</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</main>

<footer>
  <div class="container footer-flex">
    <div>© 2026 <strong>MongolRanger</strong> — Монголын Warcraft III &amp; DotA Esport Платформ</div>
    <div style="display:flex;gap:18px;flex-wrap:wrap">
      <a href="#downloads">Програм Татах</a>
      <a href="#advantages">Давуу Талууд</a>
      <a href="#elo-rules">ELO Дүрэм</a>
      <a href="#commands">Командууд</a>
      <a href="/admin">Admin</a>
    </div>
  </div>
</footer>

<script>
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
}

function cleanLabel(s) {
  if (!s) return '';
  return String(s)
    .replace(/\s*\([^)]*\.exe[^)]*\)/gi, ' (Installer)')
    .replace(/\bMongolRanger[-_A-Za-z0-9.]*\.exe\b/gi, 'Суулгагч (Installer)')
    .replace(/\.exe\b/gi, '')
    .replace(/\.zip\b/gi, '');
}

const OS_SVG = {
  client_win: '<svg viewBox="0 0 24 24"><path d="M0 3.449L9.75 2.1v9.451H0m10.949-9.602L24 0v11.4H10.949M0 12.6h9.75v9.451L0 20.699M10.949 12.6H24V24l-12.9-1.801"/></svg>',
  game_full: '<svg viewBox="0 0 24 24"><path d="M12 2L4 5v6.09c0 5.05 3.41 9.76 8 10.91 4.59-1.15 8-5.86 8-10.91V5l-8-3zm0 4.5l4.5 1.75v4.2c0 3.1-2.02 5.95-4.5 6.85-2.48-.9-4.5-3.75-4.5-6.85v-4.2L12 6.5z"/></svg>'
};

const SLOT_BULLETS = {
  client_win: [
    'Windows 7, 8, 8.1, 10, 11 (32-bit & 64-bit) бүрэн дэмжинэ',
    'Warcraft III хавтсыг өөрөө олж Reconnect Patch суулгана',
    '3 минутын Crash Reconnect + Anti-MapHack + WarKey'
  ],
  game_full: [
    'Суулгах шаардлагагүй Warcraft III 1.26a бүрэн тоглоом',
    'Албан ёсны 5 үндсэн DotA Allstars & LoD газрын зургууд',
    'MongolRanger програм автоматаар таньж ажиллана'
  ]
};

async function loadOverview() {
  try {
    const res = await fetch('/api/public/overview');
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById('statRooms').textContent = data.active_rooms || 0;

    if (data.downloads && data.downloads.length) {
      const grid = document.getElementById('downloadsGrid');
      const visibleDls = data.downloads.filter(d => d.slot !== 'client_mac');
      grid.innerHTML = visibleDls.map(d => {
        const isWin = d.slot === 'client_win';
        const href = isWin ? '/api/downloads/client_win/file' : (d.download_url || ('/api/downloads/' + d.slot + '/file'));
        const btnText = isWin ? 'Програм Татах (Installer)' : 'Warcraft III 1.26a Татах';
        const cleanTitle = isWin ? 'MongolRanger Тоглоомын Програм (Windows)' : cleanLabel(d.title);
        const cleanPlatform = isWin ? 'Windows 7 / 8 / 8.1 / 10 / 11 (32-bit & 64-bit — Бүх хувилбарт ажиллана)' : cleanLabel(d.platform);
        const cleanVer = isWin ? 'v4.8 Installer' : cleanLabel(d.version || 'v4.8');
        const cleanDesc = cleanLabel(d.description);
        if (isWin) {
          document.getElementById('heroWinBtn').href = href;
          document.getElementById('navQuickDl').href = href;
          document.getElementById('heroWinText').textContent = btnText;
        }
        if (d.slot === 'game_full') {
          document.getElementById('heroGameBtn').href = href;
        }
        const bullets = SLOT_BULLETS[d.slot] || [];
        return `
          <div class="dl-card ${isWin ? 'featured' : ''}">
            <div>
              <div class="dl-card-top">
                <div class="dl-os-icon">${OS_SVG[d.slot] || OS_SVG.game_full}</div>
                <span class="dl-ver-badge">${esc(cleanVer)} ${d.size_label ? '• ' + esc(d.size_label) : ''}</span>
              </div>
              <h3>${esc(cleanTitle)}</h3>
              <div class="dl-platform">${esc(cleanPlatform)}</div>
              <p class="dl-desc">${esc(cleanDesc)}</p>
              <ul class="dl-check-list">
                ${bullets.map(b => `<li>${esc(b)}</li>`).join('')}
              </ul>
            </div>
            <a href="${esc(href)}" class="btn-dl-action ${isWin ? 'primary' : 'secondary'}" ${d.external_url && !isWin ? 'target="_blank" rel="noopener"' : ''}>
              ⬇️ ${esc(btnText)}
            </a>
          </div>
        `;
      }).join('');
    }

    const mapsGrid = document.getElementById('mapsGrid');
    if (data.maps && data.maps.length) {
      mapsGrid.innerHTML = data.maps.map(m => {
        const mb = ((m.file_size || 0) / (1024 * 1024)).toFixed(2) + ' MB';
        return `
          <div class="map-card">
            <div>
              <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
                <div>
                  <h3 style="font-size:17px;font-weight:800;color:#fff">${esc(m.title)}</h3>
                  <div class="mono" style="font-size:12px;color:#94a3b8;margin-top:3px">🗺️ Хэмжээ: ${mb}</div>
                </div>
                ${m.is_default ? '<span class="m-tag emerald">Үндсэн Map</span>' : ''}
              </div>
              <div class="map-tags">
                ${m.has_cam ? '<span class="m-tag emerald">🎥 -cam 1.0–2.0</span>' : ''}
                ${m.has_reconnect ? '<span class="m-tag violet">🔄 3 мин Reconnect</span>' : ''}
              </div>
            </div>
            <div class="map-footer">
              <span class="mono" style="font-size:11px;color:#64748b">Албан ёсны хувилбар</span>
              <a href="/api/maps/${encodeURIComponent(m.id)}/download" class="btn-map-dl">⬇️ Газрын Зураг Татах</a>
            </div>
          </div>
        `;
      }).join('');
    }

    const rBody = document.getElementById('liveRoomsBody');
    if (data.rooms && data.rooms.length) {
      rBody.innerHTML = data.rooms.map(r => `
        <tr>
          <td style="font-weight:800;color:#fff">${esc(r.name)}</td>
          <td style="color:#a78bfa;font-weight:600">${esc(r.map_name || 'DotA v6.85m LoD')}</td>
          <td style="font-weight:700">${r.players || 0} / 10 тоглогч</td>
          <td><span class="m-tag emerald">${r.phase === 'RUNNING' ? '🔥 Тоглож байна' : '🟢 Хүлээж байна'}</span></td>
        </tr>
      `).join('');
    } else {
      rBody.innerHTML = `
        <tr>
          <td colspan="4" class="lobby-empty">
            Одоогоор нээлттэй өрөө алга байна. <strong>MongolRanger</strong> програмаа нээгээд анхны өрөөг үүсгээрэй!
          </td>
        </tr>
      `;
    }
  } catch (e) {
    console.error(e);
  }
}

loadOverview();
setInterval(loadOverview, 5000);
</script>
</body>
</html>
"""
