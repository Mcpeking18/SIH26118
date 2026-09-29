import cv2
import numpy as np

width_mm = 40.0
height_mm = 30.0
px_per_mm = 40.0

w_px = int(width_mm * px_per_mm)
h_px = int(height_mm * px_per_mm)
img = np.ones((h_px, w_px, 3), dtype=np.uint8) * 255

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
fid_size = int(6.0 * px_per_mm)
inset = int(4.0 * px_per_mm)
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
    x0 = cx - fid_size // 2
    y0 = cy - fid_size // 2
    img[y0:y0+fid_size, x0:x0+fid_size] = marker_bgr

cols, rows, w, h = 4, 3, 8.0, 4.5
start_x = (width_mm - (cols * w)) / 2.0
start_y = 8.0
SUBSTRATE = (232, 230, 226)[::-1]
PATCHES = [
    ('WHITE',       (243, 243, 242)[::-1]), ('CYAN',        (22, 163, 218)[::-1]), ('SUBSTRATE_A', SUBSTRATE), ('MAGENTA',     (200, 24, 124)[::-1]),
    ('GREY_50',     (119, 119, 119)[::-1]), ('YELLOW',      (243, 214, 26)[::-1]), ('BLACK',       (35, 35, 35)[::-1]), ('RED',         (196, 48, 43)[::-1]),
    ('SUBSTRATE_B', SUBSTRATE), ('GREEN',       (60, 140, 78)[::-1]), ('GREY_20',     (75, 75, 75)[::-1]), ('BLUE',        (46, 62, 148)[::-1])
]

k = 0
for r in range(rows):
    for c in range(cols):
        px_x = int((start_x + c * w) * px_per_mm)
        px_y = int((start_y + r * h) * px_per_mm)
        px_w = int(w * px_per_mm)
        px_h = int(h * px_per_mm)
        cv2.rectangle(img, (px_x, px_y), (px_x + px_w, px_y + px_h), PATCHES[k][1], -1)
        k += 1

sw, sh = 12.0, 6.0
px_sx = int((width_mm / 2.0 - sw/2.0) * px_per_mm)
px_sy = int((height_mm - 4.0 - sh/2.0 - sh/2.0) * px_per_mm)
px_sw = int(sw * px_per_mm)
px_sh = int(sh * px_per_mm)
cv2.rectangle(img, (px_sx, px_sy), (px_sx + px_sw, px_sy + px_sh), (200, 232, 232), -1)

cv2.putText(img, 'SIMULATED DATA', (int(w_px/2)-120, int(h_px/2)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
out_path = 'badge_v2_reference.png'
cv2.imwrite(out_path, img)
print('Generated', out_path)
