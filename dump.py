import sys
import os
import json
import numpy as np

sys.path.insert(0, os.path.abspath('reference/python'))
from engine.badge_spec import BADGE, REFERENCE_LAB, PAD_STAGE_SRGB

def ndarray_to_list(arr):
    if isinstance(arr, np.ndarray):
        return arr.tolist()
    return arr

data = {
    'marker_centres_mm': ndarray_to_list(BADGE.marker_centres_mm()),
    'marker_outer_corners_mm': ndarray_to_list(BADGE.marker_outer_corners_mm()),
    'patch_centres_mm': ndarray_to_list(BADGE.patch_centres_mm()),
    'white_field_probes_mm': ndarray_to_list(BADGE.white_field_probes_mm()),
    'REFERENCE_LAB': ndarray_to_list(REFERENCE_LAB),
    'PAD_STAGE_SRGB': ndarray_to_list(PAD_STAGE_SRGB)
}
with open('badge_constants_dump.json', 'w') as f:
    json.dump(data, f, indent=2)
print('DUMPED')
