# camera_model.py
"""
Simulates "whatever lighting the photo was taken in": an unknown
per-channel gain/offset (colour cast + exposure) plus sensor noise,
applied to every colour patch captured in one photograph.

Critically, the SAME distortion is applied to the strip and to the
printed reference swatches, because they are photographed in the same
frame under the same light -- that shared distortion is exactly what
lets the app calibrate itself out in dose_estimator.py.
"""

import numpy as np


class PhotographSimulator:
    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)

    def sample_lighting_distortion(self, severity='normal'):
        """
        Returns a per-channel affine transform (gain, offset) representing
        one lighting condition: warm/cool cast, under/over-exposure.
        """
        severity_scale = {'mild': 0.5, 'normal': 1.0, 'harsh': 1.8}[severity]

        gain = 1.0 + self.rng.normal(0, 0.12 * severity_scale, size=3)
        gain = np.clip(gain, 0.55, 1.6)

        offset = self.rng.normal(0, 10 * severity_scale, size=3)

        return gain, offset

    def photograph(self, true_rgb_list, severity='normal', sensor_noise_std=4.0):
        """
        true_rgb_list : list/array of true RGB colours (strip + swatches)
        Returns the same colours as they would appear in one captured photo.
        """
        gain, offset = self.sample_lighting_distortion(severity)
        out = []
        for rgb in true_rgb_list:
            distorted = np.asarray(rgb) * gain + offset
            distorted += self.rng.normal(0, sensor_noise_std, size=3)
            out.append(np.clip(distorted, 0, 255))
        return np.array(out), {'gain': gain, 'offset': offset}
