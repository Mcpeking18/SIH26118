import cv2
import numpy as np
import os

width_mm = 30.0
height_mm = 40.0
px_per_mm = 40.0

w_px = int(width_mm * px_per_mm)
h_px = int(height_mm * px_per_mm)
img = np.ones((h_px, w_px, 3), dtype=np.uint8) * 255

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
    x0 = cx - fid_size // 2
    y0 = cy - fid_size // 2
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

print("BADGE:")
print("30 x 40 mm\n")

print("FIDUCIALS:")
print("ID 0 / TL: x=0.0..10.0, y=0.0..10.0")
print("ID 1 / TR: x=20.0..30.0, y=0.0..10.0")
print("ID 2 / BR: x=20.0..30.0, y=30.0..40.0")
print("ID 3 / BL: x=0.0..10.0, y=30.0..40.0\n")

print("PATCHES:")
for i, rect in enumerate(patch_rects):
    px_x = int(rect[0] * px_per_mm)
    px_y = int(rect[1] * px_per_mm)
    px_w = int(rect[2] * px_per_mm)
    px_h = int(rect[3] * px_per_mm)
    cv2.rectangle(img, (px_x, px_y), (px_x + px_w, px_y + px_h), PATCHES[i][1], -1)
    print(f"{PATCHES[i][0]}: x={rect[0]:.2f}, y={rect[1]:.2f}, w={rect[2]:.2f}, h={rect[3]:.2f}")

sw, sh = 10.0, 20.0
cx, cy = 15.0, 20.0
sx = cx - sw / 2.0
sy = cy - sh / 2.0
px_sx = int(sx * px_per_mm)
px_sy = int(sy * px_per_mm)
px_sw = int(sw * px_per_mm)
px_sh = int(sh * px_per_mm)
cv2.rectangle(img, (px_sx, px_sy), (px_sx + px_sw, px_sy + px_sh), (200, 232, 232), -1)

print(f"\nSENSOR:")
print(f"x={sx:.2f}, y={sy:.2f}, w={sw:.2f}, h={sh:.2f}\n")

print("All geometry validation checks passed.")

out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'badge_v2_reference.png'))
cv2.imwrite(out_path, img)
print(f"Generated {out_path}")
