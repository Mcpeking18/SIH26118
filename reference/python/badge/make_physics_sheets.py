import cv2
import numpy as np
import os
import sys

# Import the actual physics engine
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'reference', 'python')))
from engine.dosimetry import SYNTHETIC_CALIBRATION, locus_lab_for_lightness, UNEXPOSED_PAD_LAB
from engine.colorimetry import lab_to_srgb

def draw_badge(img, x_offset_px, y_offset_px, px_per_mm, pad_color_bgr):
    width_mm = 30.0
    height_mm = 40.0
    w_px = int(width_mm * px_per_mm)
    h_px = int(height_mm * px_per_mm)
    
    cv2.rectangle(img, (x_offset_px, y_offset_px), (x_offset_px + w_px, y_offset_px + h_px), (255, 255, 255), -1)
    cv2.rectangle(img, (x_offset_px, y_offset_px), (x_offset_px + w_px, y_offset_px + h_px), (200, 200, 200), 2)
    
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    fid_size = int(10.0 * px_per_mm)
    inset = int(5.0 * px_per_mm)
    centers = [
        (inset, inset), (w_px - inset, inset),
        (w_px - inset, h_px - inset), (inset, h_px - inset)
    ]
    ids = [0, 1, 2, 3]

    for i, (cx, cy) in enumerate(centers):
        marker = cv2.aruco.generateImageMarker(aruco_dict, ids[i], fid_size)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        x0 = x_offset_px + cx - fid_size // 2
        y0 = y_offset_px + cy - fid_size // 2
        img[y0:y0+fid_size, x0:x0+fid_size] = marker_bgr

    patch_size = 4.0
    topY = 5.0
    sideGap, startY, rightX, leftX = 0.6, 11.1, 21.0, 5.0
    botY = 31.0

    patch_rects = [
        (10.5, topY, patch_size, patch_size),
        (15.5, topY, patch_size, patch_size),
        (rightX, startY, patch_size, patch_size),
        (rightX, startY + patch_size + sideGap, patch_size, patch_size),
        (rightX, startY + 2*(patch_size + sideGap), patch_size, patch_size),
        (rightX, startY + 3*(patch_size + sideGap), patch_size, patch_size),
        (15.5, botY, patch_size, patch_size),
        (10.5, botY, patch_size, patch_size),
        (leftX, startY + 3*(patch_size + sideGap), patch_size, patch_size),
        (leftX, startY + 2*(patch_size + sideGap), patch_size, patch_size),
        (leftX, startY + patch_size + sideGap, patch_size, patch_size),
        (leftX, startY, patch_size, patch_size)
    ]

    SUBSTRATE = (232, 230, 226)[::-1]
    PATCHES = [
        ('P1',       (243, 243, 242)[::-1]), ('P2',        (22, 163, 218)[::-1]), 
        ('P3', SUBSTRATE), ('P4',     (200, 24, 124)[::-1]),
        ('P5',     (119, 119, 119)[::-1]), ('P6',      (243, 214, 26)[::-1]), 
        ('P7',       (35, 35, 35)[::-1]), ('P8',         (196, 48, 43)[::-1]),
        ('P9', SUBSTRATE), ('P10',       (60, 140, 78)[::-1]), 
        ('P11',     (75, 75, 75)[::-1]), ('P12',        (46, 62, 148)[::-1])
    ]

    for i, rect in enumerate(patch_rects):
        px_x = x_offset_px + int(rect[0] * px_per_mm)
        px_y = y_offset_px + int(rect[1] * px_per_mm)
        px_w = int(rect[2] * px_per_mm)
        px_h = int(rect[3] * px_per_mm)
        cv2.rectangle(img, (px_x, px_y), (px_x + px_w, px_y + px_h), PATCHES[i][1], -1)

    sw, sh = 10.0, 20.0
    cx, cy = 15.0, 20.0
    sx = cx - sw / 2.0
    sy = cy - sh / 2.0
    px_sx = x_offset_px + int(sx * px_per_mm)
    px_sy = y_offset_px + int(sy * px_per_mm)
    px_sw = int(sw * px_per_mm)
    px_sh = int(sh * px_per_mm)
    cv2.rectangle(img, (px_sx, px_sy), (px_sx + px_sw, px_sy + px_sh), pad_color_bgr, -1)
    
# Meaningful dose levels in ppm.hr to generate test data for
DOSES = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0, 80.0, 100.0]

def generate_physics_colors():
    colors = []
    for d in DOSES:
        dl = SYNTHETIC_CALIBRATION.observable_for_dose(d)
        dl_val = dl[0] if hasattr(dl, '__len__') else dl
        L_star = UNEXPOSED_PAD_LAB[0] - dl_val
        lab = locus_lab_for_lightness(L_star)
        if len(lab.shape) > 1: lab = lab[0]
        rgb = lab_to_srgb(lab, max_value=255.0)
        c_rgb = tuple(int(round(x)) for x in rgb)
        colors.append(c_rgb[::-1]) # BGR
    return colors

px_per_mm = 40.0
colors_bgr = generate_physics_colors()

badge_w_mm = 30.0
badge_h_mm = 40.0
badge_w_px = int(badge_w_mm * px_per_mm)
badge_h_px = int(badge_h_mm * px_per_mm)

# Use test folder
out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'test_sheets'))
if not os.path.exists(out_dir):
    os.makedirs(out_dir)

print(f"Generating physical dose sheets into {out_dir}...")
for i, pad_bgr in enumerate(colors_bgr):
    single_img = np.ones((badge_h_px, badge_w_px, 3), dtype=np.uint8) * 255
    draw_badge(single_img, 0, 0, px_per_mm, pad_bgr)
    cv2.imwrite(os.path.join(out_dir, f'badge_{DOSES[i]:03.0f}ppmhr.png'), single_img)

cols = 4
rows = 4
spacing_mm = 10.0
margin_mm = 15.0
text_h_mm = 5.0

sheet_w_mm = margin_mm * 2 + (badge_w_mm * cols) + (spacing_mm * (cols - 1))
sheet_h_mm = margin_mm * 2 + ((badge_h_mm + text_h_mm) * rows) + (spacing_mm * (rows - 1))

sheet_w_px = int(sheet_w_mm * px_per_mm)
sheet_h_px = int(sheet_h_mm * px_per_mm)

sheet = np.ones((sheet_h_px, sheet_w_px, 3), dtype=np.uint8) * 255

for i, pad_bgr in enumerate(colors_bgr):
    r = i // cols
    c = i % cols
    
    x_offset = int((margin_mm + c * (badge_w_mm + spacing_mm)) * px_per_mm)
    y_offset = int((margin_mm + text_h_mm + r * (badge_h_mm + text_h_mm + spacing_mm)) * px_per_mm)
    
    draw_badge(sheet, x_offset, y_offset, px_per_mm, pad_bgr)
    
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    text = f"{DOSES[i]:.0f} ppm.hr"
    text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
    text_x = x_offset + int((badge_w_mm * px_per_mm) / 2) - text_size[0] // 2
    text_y = y_offset - int(2.0 * px_per_mm)
    cv2.putText(sheet, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness)

out_grid = os.path.join(out_dir, 'badge_v2_dosimetry_grid.png')
cv2.imwrite(out_grid, sheet)
print(f"Generated physical dosimetry 16-grid sheet at {out_grid}")
print("Done.")
