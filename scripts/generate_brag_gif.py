"""
Generates an ultra-cinematic 20-second animated product demonstration GIF for cerberus</>.
Showcases the Steve Jobs / Apple Human Interface Design transformation:
- Cupertino Frosted Glass Vibrancy & SF Pro Typography
- Magic Dropzone & One-Click Input
- Parallel Multi-Agent Stepper (7 Specialized Agents)
- Iconic Apple 4-Concentric Activity Health Rings (Security, Performance, Quality, Compliance)
- "✨ Auto-Heal Code" Magical Emerald Ripple Code Repair
- Cupertino Executive Share Sheet & Outro

Uses Google Chrome via Playwright and Pillow for deterministic, high-resolution rendering.
"""

import os
import io
from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    width: 1080px;
    height: 608px;
    background: #000000;
    color: #f5f5f7;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", system-ui, sans-serif;
    overflow: hidden;
    position: relative;
    user-select: none;
    -webkit-font-smoothing: antialiased;
  }

  /* Ambient Colored Glow Orbs in Background */
  .ambient-orb {
    position: absolute;
    border-radius: 50%;
    filter: blur(80px);
    pointer-events: none;
    opacity: 0.35;
  }
  .orb-1 { width: 420px; height: 420px; background: #0071e3; top: -100px; left: -80px; }
  .orb-2 { width: 450px; height: 450px; background: #af52de; bottom: -120px; right: -80px; }
  .orb-3 { width: 350px; height: 350px; background: #34c759; top: 180px; left: 45%; opacity: 0.2; }

  /* Cupertino Glass Header */
  .header {
    height: 54px;
    background: rgba(20, 20, 24, 0.82);
    backdrop-filter: blur(28px) saturate(190%);
    -webkit-backdrop-filter: blur(28px) saturate(190%);
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    position: relative;
    z-index: 50;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .logo-badge {
    width: 32px;
    height: 32px;
    border-radius: 9px;
    background: linear-gradient(135deg, #ffffff, #d1d1d6);
    color: #000000;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: "JetBrains Mono", monospace;
    font-weight: 800;
    font-size: 13px;
    box-shadow: 0 2px 10px rgba(255, 255, 255, 0.25);
  }
  .brand-title {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: -0.4px;
    color: #f5f5f7;
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .badge-pro {
    font-size: 10px;
    font-weight: 600;
    padding: 2px 7px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.15);
    color: #8e8e93;
    letter-spacing: 0.5px;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 9px;
  }
  .beacon-pill {
    display: flex;
    align-items: center;
    gap: 7px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 4px 11px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    color: #30d158;
  }
  .beacon-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #30d158;
    box-shadow: 0 0 8px #30d158;
  }
  .btn-pill {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #f5f5f7;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 5px;
  }

  /* Main Viewport Stage */
  .stage {
    position: absolute;
    top: 54px;
    left: 0;
    width: 1080px;
    height: 554px;
  }

  /* Scenes */
  .scene {
    position: absolute;
    inset: 0;
    display: none;
    opacity: 0;
    transition: opacity 0.35s ease;
  }
  .scene.active {
    display: flex;
    opacity: 1;
  }

  /* SCENE 1: The Cold Open / Hook */
  .s1-wrap {
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    text-align: center;
    padding: 0 40px;
  }
  .s1-pill {
    background: rgba(0, 113, 227, 0.15);
    border: 1px solid rgba(41, 151, 255, 0.35);
    color: #2997ff;
    padding: 5px 15px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 16px;
    box-shadow: 0 0 16px rgba(41, 151, 255, 0.25);
  }
  .s1-title {
    font-size: 46px;
    font-weight: 800;
    letter-spacing: -1.5px;
    color: #ffffff;
    line-height: 1.1;
    margin-bottom: 14px;
  }
  .s1-gradient {
    background: linear-gradient(135deg, #ffffff 30%, #a1a1a6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .s1-sub {
    font-size: 18px;
    color: #8e8e93;
    max-width: 640px;
    line-height: 1.45;
    margin-bottom: 28px;
    letter-spacing: -0.2px;
  }
  .s1-agent-strip {
    display: flex;
    gap: 8px;
    justify-content: center;
    flex-wrap: wrap;
  }
  .s1-agent-pill {
    background: rgba(28, 28, 30, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.12);
    padding: 7px 14px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    color: #f5f5f7;
    display: flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }

  /* SCENE 2: The Magic Dropzone */
  .s2-drop-wrap {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    padding: 30px;
  }
  .magic-drop-box {
    width: 580px;
    background: rgba(28, 28, 30, 0.85);
    backdrop-filter: blur(30px);
    border: 2px dashed #2997ff;
    border-radius: 24px;
    padding: 40px;
    text-align: center;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 12px;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.7), 0 0 50px rgba(41, 151, 255, 0.2);
    position: relative;
  }
  .drop-file-chip {
    position: absolute;
    background: #1c1c1e;
    border: 1.5px solid #30d158;
    padding: 10px 18px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 700;
    color: #ffffff;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6);
    top: -24px;
    transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  }

  /* SPLIT WORKSPACE LAYOUT (Used in Scenes 3, 4, 5) */
  .workspace {
    display: grid;
    grid-template-columns: 1.15fr 0.85fr;
    gap: 18px;
    width: 100%;
    height: 100%;
    padding: 18px 24px;
  }

  /* Left Panel: VS Code Dark+ Code Editor */
  .editor-panel {
    background: #1e1e1e;
    border: 1px solid #2d2d2d;
    border-radius: 16px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    position: relative;
  }
  .editor-header {
    background: #252526;
    padding: 8px 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #2d2d2d;
    font-size: 11px;
    color: #9cdcfe;
    font-family: monospace;
  }
  .dots { display: flex; gap: 6px; }
  .dot { width: 9px; height: 9px; border-radius: 50%; }
  .dot-r { background: #ff5f56; }
  .dot-y { background: #ffbd2e; }
  .dot-g { background: #27c93f; }

  .editor-scenarios {
    background: #18181b;
    padding: 6px 12px;
    display: flex;
    gap: 6px;
    border-bottom: 1px solid #27272a;
    align-items: center;
  }
  .sc-pill {
    font-size: 10px;
    padding: 3px 9px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: #a1a1aa;
    font-weight: 500;
  }
  .sc-pill.active {
    background: #ffffff;
    color: #000000;
    font-weight: 700;
  }

  .editor-content {
    padding: 14px;
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 12.5px;
    line-height: 1.6;
    color: #d4d4d4;
    flex: 1;
    background: #1e1e1e;
    overflow: hidden;
    position: relative;
  }
  .ln { color: #5a5a5a; width: 22px; display: inline-block; user-select: none; }
  .kw { color: #569cd6; font-weight: 600; }
  .fn { color: #dcdcaa; }
  .str { color: #ce9178; }
  .vulnerable-line {
    background: rgba(255, 69, 58, 0.22);
    border-left: 3px solid #ff453a;
    padding: 0 4px;
    display: block;
    margin: 2px 0;
  }
  .healed-line {
    background: rgba(48, 209, 88, 0.22);
    border-left: 3px solid #30d158;
    padding: 0 4px;
    display: block;
    margin: 2px 0;
  }

  .editor-ripple-overlay {
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at center, rgba(48, 209, 88, 0.35), transparent 70%);
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.4s ease;
  }
  .editor-ripple-overlay.active { opacity: 1; }

  .editor-footer {
    background: #252526;
    padding: 6px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 10px;
    color: #858585;
    border-top: 1px solid #2d2d2d;
    font-family: monospace;
  }
  .btn-submit-scan {
    background: #f5f5f7;
    color: #000000;
    border: none;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 2px 8px rgba(255, 255, 255, 0.3);
  }
  .btn-autoheal-tag {
    background: linear-gradient(135deg, #30d158, #10b981);
    color: #ffffff;
    border: none;
    padding: 5px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    box-shadow: 0 0 16px rgba(48, 209, 88, 0.5);
  }

  /* Right Panel: Synthesis Workspace */
  .synth-panel {
    background: rgba(28, 28, 30, 0.85);
    backdrop-filter: blur(28px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    overflow: hidden;
  }
  .synth-title {
    font-size: 13px;
    font-weight: 700;
    color: #f5f5f7;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  /* Stepper Cards in Scene 3 */
  .stepper-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 6px;
  }
  .step-row {
    background: rgba(44, 44, 46, 0.8);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 10px 12px;
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 11.5px;
    color: #d1d1d6;
  }
  .step-check {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #30d158;
    color: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 800;
    flex-shrink: 0;
  }
  .step-spin {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.2);
    border-top-color: #2997ff;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Apple 4-Concentric Activity Rings in Scene 4 */
  .rings-card {
    background: rgba(44, 44, 46, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 14px;
    padding: 14px;
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .rings-svg-wrap {
    position: relative;
    width: 120px;
    height: 120px;
    flex-shrink: 0;
  }
  .rings-svg {
    transform: rotate(-90deg);
    width: 120px;
    height: 120px;
  }
  .r-track { fill: none; opacity: 0.18; }
  .r-track.t1 { stroke: #ff453a; }
  .r-track.t2 { stroke: #0a84ff; }
  .r-track.t3 { stroke: #30d158; }
  .r-track.t4 { stroke: #bf5af2; }

  .r-meter { fill: none; stroke-linecap: round; }
  .r-meter.m1 { stroke: #ff453a; stroke-dasharray: 263.89; }
  .r-meter.m2 { stroke: #0a84ff; stroke-dasharray: 213.62; }
  .r-meter.m3 { stroke: #30d158; stroke-dasharray: 163.36; }
  .r-meter.m4 { stroke: #bf5af2; stroke-dasharray: 113.09; }

  .rings-score-box {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
  .rings-val {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -1px;
    color: #ffffff;
    line-height: 1;
  }
  .rings-lbl {
    font-size: 8px;
    font-weight: 700;
    color: #8e8e93;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
  }

  .rings-legend {
    display: flex;
    flex-direction: column;
    gap: 5px;
    flex: 1;
  }
  .leg-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 11px;
    color: #d1d1d6;
  }
  .leg-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 5px;
  }
  .leg-dot.d1 { background: #ff453a; }
  .leg-dot.d2 { background: #0a84ff; }
  .leg-dot.d3 { background: #30d158; }
  .leg-dot.d4 { background: #bf5af2; }

  .finding-alert-card {
    background: rgba(255, 69, 58, 0.12);
    border: 1px solid rgba(255, 69, 58, 0.35);
    border-radius: 12px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .alert-title {
    font-size: 12px;
    font-weight: 700;
    color: #ff453a;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .alert-desc {
    font-size: 11px;
    color: #d1d1d6;
    line-height: 1.4;
  }

  /* SCENE 6: Apple Share Sheet Modal Overlay */
  .share-modal-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(24px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 90;
  }
  .share-card {
    width: 440px;
    background: rgba(30, 30, 32, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 20px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 14px;
    box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8);
  }
  .share-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 15px;
    font-weight: 700;
    color: #ffffff;
  }
  .share-row {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 10px;
    padding: 10px 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
    font-weight: 500;
    color: #f5f5f7;
  }

  /* Outro Card */
  .outro-card {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    width: 100%;
    height: 100%;
    text-align: center;
    padding: 0 40px;
  }
  .outro-logo {
    width: 60px;
    height: 60px;
    border-radius: 16px;
    background: linear-gradient(135deg, #ffffff, #d1d1d6);
    color: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    font-weight: 800;
    margin-bottom: 18px;
    box-shadow: 0 8px 30px rgba(255, 255, 255, 0.3);
  }
</style>
</head>
<body>

  <!-- Background Glow Orbs -->
  <div class="ambient-orb orb-1"></div>
  <div class="ambient-orb orb-2"></div>
  <div class="ambient-orb orb-3"></div>

  <!-- Header -->
  <header class="header">
    <div class="brand">
      <div class="logo-badge">&lt;/&gt;</div>
      <div class="brand-title">
        <span>cerberus&lt;/&gt;</span>
        <span class="badge-pro">v1.0.0 Pro</span>
      </div>
    </div>
    <div class="header-actions">
      <div class="beacon-pill">
        <div class="beacon-dot"></div>
        <span>FastAPI Connected</span>
      </div>
      <div class="btn-pill"><span>🔊 Sound</span></div>
      <div class="btn-pill"><span>↗ Share</span></div>
      <div class="btn-pill"><span>🛡️ 7 Agents</span></div>
    </div>
  </header>

  <!-- Stage -->
  <div class="stage">

    <!-- SCENE 1: The Cold Open / Hook (0.0s - 3.2s) -->
    <div class="scene" id="scene-1">
      <div class="s1-wrap">
        <div class="s1-pill">✦ APPLE HUMAN INTERFACE DESIGN • CERBERUS v1.0.0</div>
        <h1 class="s1-title">Code Review <span class="s1-gradient">Reimagined.</span></h1>
        <p class="s1-sub">Seven specialized AI detectives. Zero drama. One unified mind.</p>
        <div class="s1-agent-strip">
          <div class="s1-agent-pill">🔴 Security (CWE)</div>
          <div class="s1-agent-pill">🔵 Performance (O(n²))</div>
          <div class="s1-agent-pill">🟢 Quality (PEP 257)</div>
          <div class="s1-agent-pill">🏗️ Architecture (SRP)</div>
          <div class="s1-agent-pill">🟣 Compliance (HIPAA/GDPR)</div>
          <div class="s1-agent-pill">🤝 Consensus</div>
          <div class="s1-agent-pill">✨ CodeFixer</div>
        </div>
      </div>
    </div>

    <!-- SCENE 2: Magic Dropzone (3.2s - 6.5s) -->
    <div class="scene" id="scene-2">
      <div class="s2-drop-wrap">
        <div class="magic-drop-box" id="s2-dropbox">
          <div class="drop-file-chip" id="s2-filechip" style="transform: translateY(-60px); opacity: 0;">
            <span>📄</span>
            <span>user_service.py</span>
          </div>
          <div style="font-size: 54px; filter: drop-shadow(0 4px 16px rgba(41, 151, 255, 0.4));">✨</div>
          <div style="font-size: 22px; font-weight: 700; color: #ffffff;">Magic Code Dropzone</div>
          <div style="font-size: 13px; color: #8e8e93; max-width: 420px; line-height: 1.5;">
            Drop any code file or .zip repository archive to analyze immediately.
          </div>
          <div class="badge-pro" style="margin-top: 6px;">Steve Jobs Philosophy • "It Just Works"</div>
        </div>
      </div>
    </div>

    <!-- SCENE 3: Code Editor & Multi-Agent Deliberation (6.5s - 9.8s) -->
    <div class="scene" id="scene-3">
      <div class="workspace">
        <div class="editor-panel">
          <div class="editor-header">
            <div class="dots"><div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div></div>
            <span>user_service.py</span>
            <span>Python 3.11</span>
          </div>
          <div class="editor-scenarios">
            <div class="sc-pill active">🔴 SQL &amp; Secrets</div>
            <div class="sc-pill">⚡ O(n²) Complexity</div>
            <div class="sc-pill">🛡️ HIPAA &amp; GDPR</div>
            <div class="sc-pill">✨ Clean Code</div>
          </div>
          <div class="editor-content">
            <div><span class="ln">1</span><span class="kw">import</span> os</div>
            <div><span class="ln">2</span><span class="kw">from</span> cerberus.db <span class="kw">import</span> get_db</div>
            <div><span class="ln">3</span></div>
            <div><span class="ln">4</span><span class="kw">def</span> <span class="fn">get_user</span>(user_id: str):</div>
            <div class="vulnerable-line"><span class="ln">5</span>    <span class="kw">return</span> db.execute(<span class="str">"SELECT * FROM users WHERE id = "</span> + user_id)</div>
            <div><span class="ln">6</span></div>
            <div><span class="ln">7</span><span class="kw">def</span> <span class="fn">export_phi</span>(patient_name, ssn):</div>
            <div class="vulnerable-line"><span class="ln">8</span>    logger.info(<span class="str">f"Export: {patient_name}, SSN: {ssn}"</span>)</div>
          </div>
          <div class="editor-footer">
            <span>UTF-8 • 8 lines • 248 chars</span>
            <button class="btn-submit-scan" id="s3-scan-btn">Scanning...</button>
          </div>
        </div>

        <div class="synth-panel">
          <div class="synth-title">
            <span>Autonomous Agent Stepper</span>
            <span style="color:#2997ff; font-size:11px;">14ms Engine</span>
          </div>
          <div class="stepper-list">
            <div class="step-row" id="s3-step-1">
              <div class="step-check">✓</div>
              <span>Parsing Code &amp; Building AST Cache</span>
            </div>
            <div class="step-row" id="s3-step-2">
              <div class="step-check" id="s3-icon-2">✓</div>
              <span>Running 5 Diagnostic Agents Concurrently</span>
            </div>
            <div class="step-row" id="s3-step-3">
              <div class="step-spin" id="s3-icon-3"></div>
              <span>Reconciling Conflicts via Consensus Agent</span>
            </div>
            <div class="step-row" id="s3-step-4">
              <div class="step-spin" id="s3-icon-4"></div>
              <span>Synthesizing AST-Verified Git Diff Patch</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- SCENE 4: Iconic Apple 4-Concentric Activity Rings (9.8s - 13.8s) -->
    <div class="scene" id="scene-4">
      <div class="workspace">
        <div class="editor-panel">
          <div class="editor-header">
            <div class="dots"><div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div></div>
            <span>user_service.py</span>
            <span>Python 3.11</span>
          </div>
          <div class="editor-content">
            <div><span class="ln">1</span><span class="kw">import</span> os</div>
            <div><span class="ln">2</span><span class="kw">from</span> cerberus.db <span class="kw">import</span> get_db</div>
            <div><span class="ln">3</span></div>
            <div><span class="ln">4</span><span class="kw">def</span> <span class="fn">get_user</span>(user_id: str):</div>
            <div class="vulnerable-line"><span class="ln">5</span>    <span class="kw">return</span> db.execute(<span class="str">"SELECT * FROM users WHERE id = "</span> + user_id)</div>
            <div><span class="ln">6</span></div>
            <div><span class="ln">7</span><span class="kw">def</span> <span class="fn">export_phi</span>(patient_name, ssn):</div>
            <div class="vulnerable-line"><span class="ln">8</span>    logger.info(<span class="str">f"Export: {patient_name}, SSN: {ssn}"</span>)</div>
          </div>
          <div class="editor-footer">
            <span>2 Actionable Remediations Detected</span>
            <div class="btn-autoheal-tag">✨ Auto-Heal Ready</div>
          </div>
        </div>

        <div class="synth-panel">
          <div class="synth-title">
            <span>Review Health Scorecard</span>
            <span class="badge-pro" style="color:#30d158; border-color:rgba(48,209,88,0.3);">Grade A • Enterprise Ready</span>
          </div>

          <div class="rings-card">
            <div class="rings-svg-wrap">
              <svg class="rings-svg" viewBox="0 0 120 120">
                <!-- Outer Ring (Security - Red) -->
                <circle class="r-track t1" cx="60" cy="60" r="42" stroke-width="6" />
                <circle class="r-meter m1" id="s4-ring-1" cx="60" cy="60" r="42" stroke-width="6" />

                <!-- 2nd Ring (Performance - Blue) -->
                <circle class="r-track t2" cx="60" cy="60" r="34" stroke-width="6" />
                <circle class="r-meter m2" id="s4-ring-2" cx="60" cy="60" r="34" stroke-width="6" />

                <!-- 3rd Ring (Quality - Green) -->
                <circle class="r-track t3" cx="60" cy="60" r="26" stroke-width="6" />
                <circle class="r-meter m3" id="s4-ring-3" cx="60" cy="60" r="26" stroke-width="6" />

                <!-- 4th Ring (Compliance - Purple) -->
                <circle class="r-track t4" cx="60" cy="60" r="18" stroke-width="6" />
                <circle class="r-meter m4" id="s4-ring-4" cx="60" cy="60" r="18" stroke-width="6" />
              </svg>
              <div class="rings-score-box">
                <div class="rings-val" id="s4-score-text">94</div>
                <div class="rings-lbl">Score</div>
              </div>
            </div>

            <div class="rings-legend">
              <div class="leg-item"><span><span class="leg-dot d1"></span>Security</span><strong>100%</strong></div>
              <div class="leg-item"><span><span class="leg-dot d2"></span>Performance</span><strong>95%</strong></div>
              <div class="leg-item"><span><span class="leg-dot d3"></span>Quality</span><strong>90%</strong></div>
              <div class="leg-item"><span><span class="leg-dot d4"></span>Compliance</span><strong>100%</strong></div>
            </div>
          </div>

          <div class="finding-alert-card">
            <div class="alert-title">
              <span>🔴 SQL Injection (CWE-89)</span>
              <span class="badge-pro" style="color:#ff453a;">CVSS 9.8</span>
            </div>
            <div class="alert-desc">Raw user string concatenated directly into SQL statement. Parameterization required.</div>
          </div>
        </div>
      </div>
    </div>

    <!-- SCENE 5: ✨ Auto-Heal Code Magical Repair (13.8s - 17.2s) -->
    <div class="scene" id="scene-5">
      <div class="workspace">
        <div class="editor-panel">
          <div class="editor-ripple-overlay" id="s5-ripple"></div>
          <div class="editor-header">
            <div class="dots"><div class="dot dot-r"></div><div class="dot dot-y"></div><div class="dot dot-g"></div></div>
            <span id="s5-filename">healed_user_service.py</span>
            <span style="color:#30d158;">✓ AST Verified</span>
          </div>
          <div class="editor-content" id="s5-editor-code">
            <div><span class="ln">1</span><span class="kw">import</span> os</div>
            <div><span class="ln">2</span><span class="kw">from</span> cerberus.db <span class="kw">import</span> get_db</div>
            <div><span class="ln">3</span></div>
            <div><span class="ln">4</span><span class="kw">def</span> <span class="fn">get_user</span>(user_id: str):</div>
            <div class="healed-line"><span class="ln">5</span>    <span class="kw">return</span> db.execute(<span class="str">"SELECT * FROM users WHERE id = %s"</span>, (user_id,))</div>
            <div><span class="ln">6</span></div>
            <div><span class="ln">7</span><span class="kw">def</span> <span class="fn">export_phi</span>(patient_name, ssn):</div>
            <div class="healed-line"><span class="ln">8</span>    logger.info(<span class="str">"Export record authorized for patient"</span>)</div>
          </div>
          <div class="editor-footer">
            <span style="color:#30d158; font-weight:700;">✨ Remediations Auto-Applied via AST</span>
            <div class="btn-pill" style="background:#30d158; color:#000; font-weight:700;">Merge Ready</div>
          </div>
        </div>

        <div class="synth-panel">
          <div class="synth-title">
            <span>Governance Arbitrator</span>
            <span class="badge-pro" style="color:#30d158;">APPROVED</span>
          </div>
          <div style="background:rgba(48,209,88,0.12); border:1px solid rgba(48,209,88,0.3); border-radius:12px; padding:14px; display:flex; flex-direction:column; gap:8px;">
            <div style="display:flex; align-items:center; gap:8px; font-weight:700; color:#30d158;">
              <span style="font-size:18px;">✓</span>
              <span>All Security &amp; Compliance Checks Passed</span>
            </div>
            <div style="font-size:11.5px; color:#d1d1d6; line-height:1.5;">
              Automated Git diff patch verified safe. Zero runtime exceptions. PR authorized for merge.
            </div>
          </div>
          <div style="margin-top:auto;">
            <div class="btn-submit-scan" style="width:100%; text-align:center; padding:10px; font-size:12px;">
              Authorize Instant Production Merge
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- SCENE 6: Apple Share Sheet & Outro (17.2s - 20.0s) -->
    <div class="scene" id="scene-6">
      <div class="outro-card">
        <div class="outro-logo">&lt;/&gt;</div>
        <h1 style="font-size:38px; font-weight:800; letter-spacing:-1.2px; margin-bottom:8px;">cerberus&lt;/&gt;</h1>
        <p style="font-size:19px; color:#8e8e93; font-weight:500; margin-bottom:20px;">
          <em>"It just works."</em>
        </p>
        <div style="display:flex; gap:10px; justify-content:center; flex-wrap:wrap; margin-bottom:20px;">
          <div class="btn-pill" style="padding:6px 14px;">✓ 412/412 Tests Verified</div>
          <div class="btn-pill" style="padding:6px 14px;">⚡ Sub-15ms Latency</div>
          <div class="btn-pill" style="padding:6px 14px;">🛡️ HIPAA / GDPR / PCI-DSS Gated</div>
          <div class="btn-pill" style="padding:6px 14px;">100% Offline AST or Any Cloud LLM</div>
        </div>
        <div class="s1-pill" style="font-size:13px; padding:6px 20px;">Ship With Fearless Confidence.</div>
      </div>
    </div>

  </div>

  <script>
    function renderTime(t) {
      // Hide all scenes
      for (let s = 1; s <= 6; s++) {
        const sc = document.getElementById(`scene-${s}`);
        if (sc) {
          sc.classList.remove('active');
          sc.style.display = 'none';
        }
      }

      if (t < 3.2) {
        // SCENE 1: Cold Open
        const sc = document.getElementById('scene-1');
        sc.style.display = 'flex';
        sc.classList.add('active');
      } else if (t < 6.5) {
        // SCENE 2: Magic Dropzone
        const sc = document.getElementById('scene-2');
        sc.style.display = 'flex';
        sc.classList.add('active');
        const chip = document.getElementById('s2-filechip');
        const progress = (t - 3.2) / 3.3;
        if (chip) {
          if (progress > 0.2) {
            chip.style.opacity = '1';
            chip.style.transform = `translateY(${Math.min(10, -60 + progress * 70)}px)`;
          }
        }
      } else if (t < 9.8) {
        // SCENE 3: Stepper
        const sc = document.getElementById('scene-3');
        sc.style.display = 'flex';
        sc.classList.add('active');
        const p = (t - 6.5) / 3.3;
        if (p > 0.4) {
          const s3_icon = document.getElementById('s3-icon-3');
          if (s3_icon) {
            s3_icon.className = 'step-check';
            s3_icon.innerText = '✓';
          }
        }
        if (p > 0.7) {
          const s4_icon = document.getElementById('s3-icon-4');
          if (s4_icon) {
            s4_icon.className = 'step-check';
            s4_icon.innerText = '✓';
          }
        }
      } else if (t < 13.8) {
        // SCENE 4: 4 Concentric Activity Rings
        const sc = document.getElementById('scene-4');
        sc.style.display = 'flex';
        sc.classList.add('active');
        const p = Math.min(1.0, (t - 9.8) / 2.5);
        // Animate Rings
        const r1 = document.getElementById('s4-ring-1');
        const r2 = document.getElementById('s4-ring-2');
        const r3 = document.getElementById('s4-ring-3');
        const r4 = document.getElementById('s4-ring-4');

        if (r1) r1.style.strokeDashoffset = 263.89 * (1.0 - p * 1.0);
        if (r2) r2.style.strokeDashoffset = 213.62 * (1.0 - p * 0.95);
        if (r3) r3.style.strokeDashoffset = 163.36 * (1.0 - p * 0.90);
        if (r4) r4.style.strokeDashoffset = 113.09 * (1.0 - p * 1.0);

        const scoreText = document.getElementById('s4-score-text');
        if (scoreText) scoreText.innerText = Math.round(p * 94);
      } else if (t < 17.2) {
        // SCENE 5: Auto-Heal Ripple
        const sc = document.getElementById('scene-5');
        sc.style.display = 'flex';
        sc.classList.add('active');
        const ripple = document.getElementById('s5-ripple');
        const p = (t - 13.8) / 3.4;
        if (ripple) {
          if (p < 0.5) ripple.classList.add('active');
          else ripple.classList.remove('active');
        }
      } else {
        // SCENE 6: Outro
        const sc = document.getElementById('scene-6');
        sc.style.display = 'flex';
        sc.classList.add('active');
      }
    }
  </script>
</body>
</html>
"""

def generate_gif():
    repo_root = Path(__file__).parent.parent
    output_dir = repo_root / "brag-output"
    assets_dir = repo_root / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    temp_html = output_dir / "storyboard.html"
    temp_html.write_text(HTML_CONTENT, encoding="utf-8")

    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not Path(chrome_path).exists():
        chrome_path = None

    print("Launching Chromium to capture 20-second cinematic storyboard frames...")
    frames = []

    with sync_playwright() as p:
        browser_args = {"headless": True}
        if chrome_path:
            browser_args["executable_path"] = chrome_path

        browser = p.chromium.launch(**browser_args)
        page = browser.new_page(viewport={"width": 1080, "height": 608})
        page.goto(temp_html.resolve().as_uri())

        total_duration = 20.0
        fps = 4.0  # 4 fps * 20 seconds = 80 crisp frames
        total_frames = int(total_duration * fps)

        for i in range(total_frames):
            t = i / fps
            page.evaluate(f"renderTime({t})")
            img_bytes = page.screenshot(type="png")
            img = Image.open(io.BytesIO(img_bytes))
            frames.append(img.convert("RGB"))

        browser.close()

    print(f"Captured {len(frames)} frames. Compiling cinematic animated GIF...")

    gif_path_assets = assets_dir / "cerberus_demo.gif"
    gif_path_brag = output_dir / "cerberus_demo.gif"

    frame_duration_ms = int(1000 / fps)

    # High-quality adaptive palette quantization with lanczos resampling
    palette_frames = [f.quantize(colors=128, method=Image.Resampling.LANCZOS) for f in frames]

    palette_frames[0].save(
        gif_path_assets,
        save_all=True,
        append_images=palette_frames[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True
    )

    palette_frames[0].save(
        gif_path_brag,
        save_all=True,
        append_images=palette_frames[1:],
        duration=frame_duration_ms,
        loop=0,
        optimize=True
    )

    # Save poster frame brag.jpg (Apple Concentric Activity Rings scene at t=11.5s)
    poster_idx = int(11.5 * fps)
    poster_frame = frames[poster_idx]
    poster_frame.save(output_dir / "brag.jpg", quality=95)
    poster_frame.save(assets_dir / "cerberus_poster.jpg", quality=95)

    size_mb = os.path.getsize(gif_path_assets) / (1024 * 1024)
    print(f"Successfully generated cinematic GIF: {gif_path_assets} ({size_mb:.2f} MB)")
    print(f"Saved poster frame: {output_dir / 'brag.jpg'}")

if __name__ == "__main__":
    generate_gif()
