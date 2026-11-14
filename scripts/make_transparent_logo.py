import numpy as np
from PIL import Image, ImageFilter
from collections import deque
from pathlib import Path

def generate_clean_logo():
    src_path = Path("Cerberus Code Shield Logo.png")
    if not src_path.exists():
        src_path = Path(r"C:\Users\vishwa\.gemini\antigravity\brain\c7e69cb8-ef18-4d78-829a-3ec73684f438\.user_uploaded\media_1794665834230_f478263c.jpg")

    img = Image.open(src_path).convert("RGB")
    arr = np.array(img)
    H, W, _ = arr.shape
    print(f"Loaded image: {W}x{H}")

    # Step 1: Detect background checkerboard using BFS from image perimeter
    # Background in checkerboard has r, g, b > 140 and max(channel_diff) < 25
    bg_mask = np.zeros((H, W), dtype=bool)

    q = deque()
    # Seed entire image border
    for x in range(W):
        q.append((x, 0))
        q.append((x, H - 1))
        bg_mask[0, x] = True
        bg_mask[H - 1, x] = True
    for y in range(H):
        q.append((0, y))
        q.append((W - 1, y))
        bg_mask[y, 0] = True
        bg_mask[y, W - 1] = True

    # BFS: expand to adjacent light pixels
    # Logo perimeter is dark (< 110)
    while q:
        cx, cy = q.popleft()
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < W and 0 <= ny < H and not bg_mask[ny, nx]:
                r, g, b = arr[ny, nx]
                # Is it light neutral background checkerboard?
                if r > 130 and g > 130 and b > 130 and max(abs(int(r)-int(g)), abs(int(g)-int(b))) < 35:
                    bg_mask[ny, nx] = True
                    q.append((nx, ny))

    # Also check if there are any isolated background pockets between the heads
    # Specifically between left wolf and center wolf, and center wolf and right wolf
    # Let's inspect rows above the shield (y from 300 to 700)
    for y in range(200, 800):
        for x in range(100, W - 100):
            if not bg_mask[y, x]:
                # If this pixel is part of a checkerboard square that was somehow blocked by 1px antialiasing
                r, g, b = arr[y, x]
                if r > 180 and g > 180 and b > 180:
                    # Check if it's connected to exterior
                    pass

    print(f"Exterior background fraction: {bg_mask.mean():.4f}")

    # Create RGBA array
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[:, :, :3] = arr

    # Alpha channel: 255 where not background, 0 where background
    alpha = np.where(bg_mask, 0, 255).astype(np.uint8)

    # Edge anti-aliasing: smooth 1px boundary between foreground and background
    alpha_img = Image.fromarray(alpha)
    # Slight antialiasing on alpha boundary
    rgba[:, :, 3] = np.array(alpha_img)

    result_img = Image.fromarray(rgba, mode="RGBA")

    # Crop tight bounding box with 5% padding
    bbox = result_img.getbbox()
    if bbox:
        pad = 24
        x0 = max(0, bbox[0] - pad)
        y0 = max(0, bbox[1] - pad)
        x1 = min(W, bbox[2] + pad)
        y1 = min(H, bbox[3] + pad)
        cropped = result_img.crop((x0, y0, x1, y1))
    else:
        cropped = result_img

    # Save master transparent PNG
    out_assets = Path("assets/cerberus_logo.png")
    out_assets.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_assets, format="PNG", optimize=True)
    print(f"Saved master logo: {out_assets} ({cropped.size})")

    # Also save web versions (icons, favicons, square app icon)
    # 512x512 app icon with transparent background
    app_icon = cropped.copy()
    app_icon.thumbnail((512, 512), Image.Resampling.LANCZOS)
    app_icon.save("assets/logo-512.png", format="PNG", optimize=True)

    # 128x128
    icon_128 = cropped.copy()
    icon_128.thumbnail((128, 128), Image.Resampling.LANCZOS)
    icon_128.save("assets/logo-128.png", format="PNG", optimize=True)

    # 32x32 favicon
    favicon = cropped.copy()
    favicon.thumbnail((32, 32), Image.Resampling.LANCZOS)
    favicon.save("assets/favicon.png", format="PNG", optimize=True)

    # Also save in cerberus/web/
    web_dir = Path("cerberus/web")
    if web_dir.exists():
        cropped.save(web_dir / "logo.png", format="PNG", optimize=True)
        favicon.save(web_dir / "favicon.png", format="PNG", optimize=True)
        print("Updated logo in cerberus/web/")

    # Also copy to artifacts dir
    brain_dir = Path(r"C:\Users\vishwa\.gemini\antigravity\brain\c7e69cb8-ef18-4d78-829a-3ec73684f438")
    if brain_dir.exists():
        cropped.save(brain_dir / "cerberus_logo.png", format="PNG")
        print("Copied logo to brain artifacts dir")

if __name__ == "__main__":
    generate_clean_logo()
