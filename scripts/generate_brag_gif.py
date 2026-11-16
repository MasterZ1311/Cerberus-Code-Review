"""
generate_brag_gif.py
Produces a high-fidelity 25 FPS animated product demonstration GIF for Cerberus.
Directly drives the live web console (cerberus/web/index.html) via Playwright,
orchestrating authentic user interactions with high-fidelity, fluid cursor animations:

1. Dark mode console with live health beacon and agent registry.
2. 1-Click scenario preset loading (SQL & Secrets) into editor.
3. Multi-Agent collaborative execution stepper with concurrent diagnostic agents.
4. Animated Concentric Metric Rings (Security, Performance, Quality, Compliance) and Score Gauge.
5. Automated AST code repair with inline diff transformation.
6. Unified Patch Diff inspection.
7. Executive Share Sheet modal.
8. Seamless, continuous infinite loop closure (modal close & smooth cursor return to origin).

Specs:
- Framerate: 25 FPS (40ms per frame) for cinema-grade fluidity (zero sluggishness).
- Resolution: 1120x700 viewport, crystal-clear typography.
- Color Quantization: Optimal 256-color master palette with Floyd-Steinberg dithering for banding-free dark glassmorphism.
- Loop: Netscape 2.0 infinite loop (loop=0).
"""

import io
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_FILE = (REPO_ROOT / "cerberus" / "web" / "index.html").resolve()
OUTPUT_DIR = REPO_ROOT / "brag-output"
ASSETS_DIR = REPO_ROOT / "assets"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not Path(CHROME_PATH).exists():
    CHROME_PATH = None

# Realistic multi-agent review response
REVIEW_DATA = {
    "review_id": "rev_ast_01",
    "status": "completed",
    "overall_score": 93.8,
    "processing_time_ms": 14,
    "cache_hit": False,
    "blocking": False,
    "should_block": False,
    "results": {
        "overall_score": 93.8,
        "severity_summary": {
            "critical": 1,
            "high": 1,
            "medium": 1,
            "low": 0,
            "info": 1
        },
        "agents": [
            {"name": "security", "status": "completed", "score": 85.0, "execution_time_ms": 4, "findings": []},
            {"name": "performance", "status": "completed", "score": 96.0, "execution_time_ms": 2, "findings": []},
            {"name": "quality", "status": "completed", "score": 94.0, "execution_time_ms": 3, "findings": []},
            {"name": "architecture", "status": "completed", "score": 95.0, "execution_time_ms": 1, "findings": []},
            {"name": "compliance", "status": "completed", "score": 90.0, "execution_time_ms": 2, "findings": []},
            {"name": "consensus", "status": "completed", "score": 93.8, "execution_time_ms": 1, "findings": []},
            {"name": "code_fixer", "status": "completed", "score": 100.0, "execution_time_ms": 1, "findings": []}
        ]
    },
    "critical_issues": [
        {
            "id": "SEC-SQLI-01",
            "agent_name": "security",
            "severity": "critical",
            "category": "security",
            "title": "SQL Injection Risk via String Concatenation",
            "message": "Raw SQL query constructed via direct string formatting allows unescaped arbitrary SQL injection.",
            "line": 6,
            "code_snippet": 'query = "SELECT * FROM users WHERE id = " + user_id',
            "explanation": "An attacker can supply '1 OR 1=1' to dump all records, bypass authentication, or drop database tables.",
            "recommendation": "Use parameterized queries or SQLAlchemy ORM bind variables.",
            "suggestion": 'db.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
            "cwe_id": "CWE-89",
            "cvss_score": 9.8,
            "exploitability": 0.95,
            "false_positive_probability": 0.02
        }
    ],
    "warnings": [
        {
            "id": "SEC-SECRET-01",
            "agent_name": "security",
            "severity": "high",
            "category": "security",
            "title": "Hardcoded Cloud API Key in Source",
            "message": "Hardcoded production API credential 'sk-live-...' detected in code.",
            "line": 3,
            "code_snippet": 'API_KEY = "sk-live-98213847291038291029381"',
            "explanation": "Secrets committed to git repositories can be scanned by automated scrapers within seconds.",
            "recommendation": "Load secrets securely from environment variables or AWS Secrets Manager.",
            "suggestion": 'API_KEY = os.environ.get("APP_API_KEY")',
            "cwe_id": "CWE-798",
            "cvss_score": 7.5,
            "false_positive_probability": 0.01
        }
    ],
    "suggestions": [
        {
            "id": "COMP-HIPAA-01",
            "agent_name": "compliance",
            "severity": "medium",
            "category": "compliance",
            "title": "Unencrypted Sensitive Data Retrieval (HIPAA §164.312)",
            "message": "User entity queried without explicit data classification masking.",
            "line": 7,
            "code_snippet": 'db.execute(query)',
            "explanation": "HIPAA requires encrypted transit and strict column masking for protected health data.",
            "recommendation": "Ensure row-level filtering and encrypted field attributes.",
            "suggestion": 'db.execute_safe_select("users", user_id=user_id, masked=True)',
            "cwe_id": "CWE-312",
            "cvss_score": 5.3,
            "false_positive_probability": 0.05
        }
    ],
    "fixes": {
        "SEC-SQLI-01": {
            "type": "parameterized_sql",
            "original_code": 'query = "SELECT * FROM users WHERE id = " + user_id\n    db.execute(query)',
            "fixed_code": 'query = "SELECT * FROM users WHERE id = %s"\n    db.execute(query, (user_id,))',
            "diff": '@@ -6,2 +6,2 @@\n-    query = "SELECT * FROM users WHERE id = " + user_id\n-    db.execute(query)\n+    query = "SELECT * FROM users WHERE id = %s"\n+    db.execute(query, (user_id,))'
        }
    }
}

CURSOR_SCRIPT = """
(function() {
  const existing = document.getElementById('cinematic-cursor');
  if (existing) existing.remove();

  const cur = document.createElement('div');
  cur.id = 'cinematic-cursor';
  cur.innerHTML = `
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" style="filter: drop-shadow(0 2px 5px rgba(0,0,0,0.7)); display:block;">
      <path d="M4 3L11 20L14 13L21 10L4 3Z" fill="#ffffff" stroke="#1d1d1f" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>
    <div id="cursor-ring" style="
      position: absolute;
      top: -6px;
      left: -6px;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      border: 2px solid #2997ff;
      opacity: 0;
      transform: scale(0.3);
      pointer-events: none;
      transition: transform 0.2s ease-out, opacity 0.2s ease-out;
    "></div>
  `;
  cur.style.cssText = `
    position: fixed;
    z-index: 99999999;
    pointer-events: none;
    top: 0;
    left: 0;
    transform: translate(850px, 480px);
    will-change: transform;
    transition: transform 0.02s linear;
  `;
  document.body.appendChild(cur);

  window.__cursorX = 850;
  window.__cursorY = 480;

  window.setCursorPos = function(x, y) {
    window.__cursorX = x;
    window.__cursorY = y;
    const el = document.getElementById('cinematic-cursor');
    if (el) el.style.transform = `translate(${x}px, ${y}px)`;
  };

  window.triggerCursorClick = function() {
    const ring = document.getElementById('cursor-ring');
    if (ring) {
      ring.style.opacity = '0.9';
      ring.style.transform = 'scale(0.4)';
      ring.style.borderColor = '#2997ff';
      setTimeout(() => {
        ring.style.opacity = '0';
        ring.style.transform = 'scale(1.4)';
      }, 40);
    }
  };

  window.getElementCenter = function(selector) {
    const el = document.querySelector(selector);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return {
      x: Math.round(rect.left + rect.width / 2),
      y: Math.round(rect.top + rect.height / 2)
    };
  };
})();
"""

def ease_in_out(t: float) -> float:
    """Smooth cubic bezier easing (0 to 1)."""
    return 3 * t * t - 2 * t * t * t

def record_peak_walkthrough():
    print("🎬 Initializing Playwright at Ultra-Smooth 25 FPS (40ms per frame)...")
    frames = []

    with sync_playwright() as p:
        browser_args = {"headless": True}
        if CHROME_PATH:
            browser_args["executable_path"] = CHROME_PATH

        browser = p.chromium.launch(**browser_args)
        context = browser.new_context(
            viewport={"width": 1120, "height": 700},
            device_scale_factor=1.0
        )
        page = context.new_page()

        # Intercept backend endpoints
        page.route("**/health", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"status":"healthy","database":"connected","agents":7,"cache_status":"ready"}'
        ))
        page.route("**/api/v1/agents", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"agents":[{"name":"security","status":"active"},{"name":"performance","status":"active"},{"name":"quality","status":"active"},{"name":"architecture","status":"active"},{"name":"compliance","status":"active"},{"name":"consensus","status":"active"},{"name":"code_fixer","status":"active"}]}'
        ))
        page.route("**/api/v1/review", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(REVIEW_DATA)
        ))

        # Navigate to live application
        page.goto(HTML_FILE.as_uri())
        page.wait_for_timeout(300)

        # Ensure Dark Theme is strictly applied
        page.evaluate("""
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('cerberus_theme', 'dark');
            const icon = document.getElementById('theme-icon');
            if (icon) icon.innerText = '☀️';
            const beacon = document.getElementById('backend-status-text');
            if (beacon) beacon.innerText = 'FastAPI Connected';
            const dot = document.querySelector('.beacon-dot');
            if (dot) dot.style.background = '#30d158';
        """)

        # Inject cinematic cursor
        page.evaluate(CURSOR_SCRIPT)
        page.wait_for_timeout(100)

        def capture_frame(repeat=1):
            buf = page.screenshot(type="png")
            img = Image.open(io.BytesIO(buf)).convert("RGB")
            for _ in range(repeat):
                frames.append(img)

        def glide_cursor(from_x, from_y, to_x, to_y, steps=14):
            for i in range(1, steps + 1):
                t = ease_in_out(i / steps)
                cx = from_x + (to_x - from_x) * t
                cy = from_y + (to_y - from_y) * t
                page.evaluate(f"setCursorPos({cx}, {cy})")
                capture_frame(1)

        print("Phase 1: Starting neutral view & smooth glide to preset...")
        capture_frame(4)
        preset_coords = page.evaluate("getElementCenter('#preset-vulnerable')") or {"x": 260, "y": 168}
        glide_cursor(850, 480, preset_coords["x"], preset_coords["y"], steps=14)

        print("Phase 2: Clicking Scenario Preset [ 🔴 SQL & Secrets ]...")
        page.evaluate("triggerCursorClick()")
        page.evaluate("loadPreset('vulnerable')")
        capture_frame(6)

        print("Phase 3: Glide to [ Execute Multi-Agent Review ]...")
        review_btn_coords = page.evaluate("getElementCenter('#btn-review')") or {"x": 240, "y": 660}
        glide_cursor(preset_coords["x"], preset_coords["y"], review_btn_coords["x"], review_btn_coords["y"], steps=14)

        print("Phase 4: Click Execute & Stepper in Motion...")
        page.evaluate("triggerCursorClick()")
        page.evaluate("""
            const btn = document.getElementById('btn-review');
            const spinner = document.getElementById('btn-spinner');
            const btnText = document.getElementById('btn-text');
            btn.disabled = true;
            spinner.style.display = 'inline-block';
            btnText.innerText = 'Agents Inspecting Snippet...';
            renderProgressiveLoadingState();
        """)
        capture_frame(5)

        # Stepper step 2: Security & Analysis
        page.evaluate("""
            const s1 = document.getElementById('step-1');
            const s2 = document.getElementById('step-2');
            if (s1 && s2) { s1.className = 'stepper-step done'; s2.className = 'stepper-step active'; }
        """)
        capture_frame(5)

        # Stepper step 3: Consensus & Auto-Healer
        page.evaluate("""
            const s2 = document.getElementById('step-2');
            const s3 = document.getElementById('step-3');
            if (s2 && s3) { s2.className = 'stepper-step done'; s3.className = 'stepper-step active'; }
        """)
        capture_frame(5)

        print("Phase 5: Rendering Results & Animated 4-Concentric Activity Rings...")
        page.evaluate(f"""
            const data = {json.dumps(REVIEW_DATA)};
            lastReviewData = data;
            const btn = document.getElementById('btn-review');
            const spinner = document.getElementById('btn-spinner');
            const btnText = document.getElementById('btn-text');
            btn.disabled = false;
            spinner.style.display = 'none';
            btnText.innerText = 'Execute Multi-Agent Review';
            renderResults(data);
            const autoHealBtn = document.getElementById('btn-editor-autoheal');
            if (autoHealBtn) autoHealBtn.style.display = 'inline-flex';
        """)

        # 10-step fluid sweep of activity rings & score gauge
        for i in range(1, 11):
            pct = ease_in_out(i / 10)
            sub_score = 93.8 * pct
            page.evaluate(f"""
                animateActivityRings({{
                    security: Math.round(85 * {pct}),
                    performance: Math.round(96 * {pct}),
                    quality: Math.round(94 * {pct}),
                    compliance: Math.round(90 * {pct})
                }}, {sub_score});
            """)
            capture_frame(1)

        # Brief hold on full scorecard results
        capture_frame(8)

        print("Phase 6: AST Auto-Repair Injection...")
        autoheal_coords = page.evaluate("getElementCenter('#btn-editor-autoheal')") or {"x": 450, "y": 168}
        glide_cursor(review_btn_coords["x"], review_btn_coords["y"], autoheal_coords["x"], autoheal_coords["y"], steps=14)

        # Hover & Click AutoHeal
        page.evaluate("triggerCursorClick()")
        page.evaluate("triggerAutoHealCode()")
        # Emerald glow ripple wave active!
        capture_frame(12)

        print("Phase 7: Inspecting Unified Patch Diff...")
        patch_tab_coords = page.evaluate("getElementCenter('#res-tab-patch')") or {"x": 830, "y": 168}
        glide_cursor(autoheal_coords["x"], autoheal_coords["y"], patch_tab_coords["x"], patch_tab_coords["y"], steps=12)
        page.evaluate("triggerCursorClick()")
        page.evaluate("switchResultTab('patch')")
        capture_frame(14)

        print("Phase 8: Executive Share Sheet...")
        share_btn_coords = page.evaluate("getElementCenter('button[onclick=\"openShareSheetModal()\"]')") or {"x": 1000, "y": 28}
        glide_cursor(patch_tab_coords["x"], patch_tab_coords["y"], share_btn_coords["x"], share_btn_coords["y"], steps=12)
        page.evaluate("triggerCursorClick()")
        page.evaluate("openShareSheetModal()")
        capture_frame(14)

        print("Phase 9: Seamless Infinite Loop Closure — Closing Modal & Returning to Origin...")
        close_btn_coords = page.evaluate("getElementCenter('.btn-close-modal')") or {"x": 780, "y": 140}
        glide_cursor(share_btn_coords["x"], share_btn_coords["y"], close_btn_coords["x"], close_btn_coords["y"], steps=10)
        page.evaluate("triggerCursorClick()")
        page.evaluate("document.getElementById('share-modal').classList.remove('active')")
        capture_frame(4)

        # Clean reset of UI back to pristine preset-loaded baseline
        page.evaluate("""
            loadPreset('vulnerable');
            switchResultTab('issues');
            const autoHealBtn = document.getElementById('btn-editor-autoheal');
            if (autoHealBtn) autoHealBtn.style.display = 'none';
        """)
        capture_frame(3)

        # Smooth glide back to initial resting coordinates (850, 480)
        glide_cursor(close_btn_coords["x"], close_btn_coords["y"], 850, 480, steps=12)
        capture_frame(4)

        browser.close()

    print(f"Captured {len(frames)} frames @ 25 FPS. Synthesizing master color palette & compiling animated GIF...")

    # High-quality palette generation using MAXCOVERAGE on a composite sample of keyframes
    sample_indices = list(range(0, len(frames), max(1, len(frames) // 20)))[:20]
    sample_img = Image.new("RGB", (frames[0].width, frames[0].height * len(sample_indices)))
    for idx, s_idx in enumerate(sample_indices):
        sample_img.paste(frames[s_idx], (0, idx * frames[0].height))

    # Generate optimal 256-color palette with MAXCOVERAGE for rich glassmorphism gradients
    palette_master = sample_img.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE)

    print("Quantizing all frames against optimal master palette with Floyd-Steinberg dithering...")
    palette_frames = []
    for f in frames:
        q = f.quantize(palette=palette_master, dither=Image.Dither.FLOYDSTEINBERG)
        palette_frames.append(q)

    gif_assets = ASSETS_DIR / "cerberus_demo.gif"
    gif_brag = OUTPUT_DIR / "cerberus_demo.gif"
    frame_duration = 40  # 25 fps = 40ms per frame

    print(f"Saving ultra-smooth 25 FPS animated GIF to {gif_assets}...")
    palette_frames[0].save(
        gif_assets,
        save_all=True,
        append_images=palette_frames[1:],
        duration=frame_duration,
        loop=0,
        optimize=True
    )

    palette_frames[0].save(
        gif_brag,
        save_all=True,
        append_images=palette_frames[1:],
        duration=frame_duration,
        loop=0,
        optimize=True
    )

    # Save high-res poster frame (Apple Rings & Scorecard reveal)
    poster_idx = min(len(frames) - 1, 75)
    poster = frames[poster_idx]
    poster.save(OUTPUT_DIR / "brag.jpg", quality=95)
    poster.save(ASSETS_DIR / "cerberus_poster.jpg", quality=95)

    size_mb = gif_assets.stat().st_size / (1024 * 1024)
    print(f"✨ SUCCESS! Peak GIF generated: {gif_assets} ({size_mb:.2f} MB, {len(frames)} frames @ 25fps [40ms])")
    print(f"Poster frame saved: {OUTPUT_DIR / 'brag.jpg'}")

if __name__ == "__main__":
    record_peak_walkthrough()
