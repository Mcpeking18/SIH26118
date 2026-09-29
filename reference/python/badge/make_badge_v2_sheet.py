import cv2
import numpy as np
import os

def draw_badge(img, x_offset_px, y_offset_px, px_per_mm, pad_color_bgr):
    width_mm = 30.0
    height_mm = 40.0
    
    # Draw badge background (white)
    w_px = int(width_mm * px_per_mm)
    h_px = int(height_mm * px_per_mm)
    cv2.rectangle(img, (x_offset_px, y_offset_px), (x_offset_px + w_px, y_offset_px + h_px), (255, 255, 255), -1)
    
    # Draw border (light gray) to cut it out
    cv2.rectangle(img, (x_offset_px, y_offset_px), (x_offset_px + w_px, y_offset_px + h_px), (200, 200, 200), 2)
    
    # Fiducials
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    fid_size = int(10.0 * px_per_mm)
    inset = int(5.0 * px_per_mm)
    centers = [
        (inset, inset),
        (w_px - inset, inset),
        (w_px - inset, h_px - inset),
        (inset, h_px - inset)
    ]
    ids = [0, 1, 2, 3]

    for i, (cx, cy) in enumerate(centers):
        marker = cv2.aruco.generateImageMarker(aruco_dict, ids[i], fid_size)
        marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
        x0 = x_offset_px + cx - fid_size // 2
        y0 = y_offset_px + cy - fid_size // 2
        img[y0:y0+fid_size, x0:x0+fid_size] = marker_bgr

    # Patches
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
        ('P1',       (243, 243, 242)[::-1]), 
        ('P2',        (22, 163, 218)[::-1]), 
        ('P3', SUBSTRATE), 
        ('P4',     (200, 24, 124)[::-1]),
        ('P5',     (119, 119, 119)[::-1]), 
        ('P6',      (243, 214, 26)[::-1]), 
        ('P7',       (35, 35, 35)[::-1]), 
        ('P8',         (196, 48, 43)[::-1]),
        ('P9', SUBSTRATE), 
        ('P10',       (60, 140, 78)[::-1]), 
        ('P11',     (75, 75, 75)[::-1]), 
        ('P12',        (46, 62, 148)[::-1])
    ]

    for i, rect in enumerate(patch_rects):
        px_x = x_offset_px + int(rect[0] * px_per_mm)
        px_y = y_offset_px + int(rect[1] * px_per_mm)
        px_w = int(rect[2] * px_per_mm)
        px_h = int(rect[3] * px_per_mm)
        cv2.rectangle(img, (px_x, px_y), (px_x + px_w, px_y + px_h), PATCHES[i][1], -1)

    # Sensor
    sw, sh = 10.0, 20.0
    cx, cy = 15.0, 20.0
    sx = cx - sw / 2.0
    sy = cy - sh / 2.0
    px_sx = x_offset_px + int(sx * px_per_mm)
    px_sy = y_offset_px + int(sy * px_per_mm)
    px_sw = int(sw * px_per_mm)
    px_sh = int(sh * px_per_mm)
    cv2.rectangle(img, (px_sx, px_sy), (px_sx + px_sw, px_sy + px_sh), pad_color_bgr, -1)


px_per_mm = 40.0
# 5 badges across, with margins
pad_stages = [
    (220, 232, 232)[::-1], # 0
    (184, 184, 160)[::-1], # 1
    (122, 88, 50)[::-1],   # 2
    (56, 35, 21)[::-1],    # 3
    (13, 12, 12)[::-1]     # 4
]

labels = [
    "Stage 0 (Pristine - 0 ppm.hr)",
    "Stage 1 (~10 ppm.hr)",
    "Stage 2 (~25 ppm.hr)",
    "Stage 3 (~50 ppm.hr)",
    "Stage 4 (Saturated)"
]

badge_w_mm = 30.0
badge_h_mm = 40.0
spacing_mm = 10.0
margin_mm = 15.0

sheet_w_mm = margin_mm * 2 + (badge_w_mm * len(pad_stages)) + (spacing_mm * (len(pad_stages) - 1))
sheet_h_mm = margin_mm * 3 + badge_h_mm

sheet_w_px = int(sheet_w_mm * px_per_mm)
sheet_h_px = int(sheet_h_mm * px_per_mm)

# Create white sheet
sheet = np.ones((sheet_h_px, sheet_w_px, 3), dtype=np.uint8) * 255

y_offset = int(margin_mm * px_per_mm)

for i, pad_bgr in enumerate(pad_stages):
    x_offset = int(margin_mm * px_per_mm + i * (badge_w_mm + spacing_mm) * px_per_mm)
    draw_badge(sheet, x_offset, y_offset, px_per_mm, pad_bgr)
    
    # Draw label above
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.0
    thickness = 2
    text = labels[i]
    text_size, _ = cv2.getTextSize(text, font, font_scale, thickness)
    text_x = x_offset + int((badge_w_mm * px_per_mm) / 2) - text_size[0] // 2
    text_y = y_offset - int(3.0 * px_per_mm)
    cv2.putText(sheet, text, (text_x, text_y), font, font_scale, (0, 0, 0), thickness)

out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'badge_v2_sheet.png'))
cv2.imwrite(out_path, sheet)
print(f"Generated {out_path}")
