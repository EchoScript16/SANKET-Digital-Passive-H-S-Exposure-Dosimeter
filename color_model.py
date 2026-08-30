# color_model.py
"""
Maps the chemical state of the strip (fraction reacted, f in [0,1]) to a
colour, and back again. This is the shared curve printed on the physical
reference scale AND used by the app to interpret a photograph -- exactly
the "sealed reference cell" concept from the brief.

Stops chosen to mimic a real lead-sulfide-type darkening: pale
straw/cream -> ochre -> umber -> near-black, rather than an arbitrary
warning-light gradient.
"""

import numpy as np

# (f, R, G, B) calibration stops, 0-255 scale
_STOPS = [
    (0.00, 234, 223, 184),   # unreacted strip
    (0.30, 201, 162, 39),
    (0.62, 122, 75, 36),
    (1.00, 36, 26, 20),      # fully saturated / near-black
]


class ColorGradient:
    def __init__(self, stops=None):
        self.stops = stops or _STOPS
        self._f = np.array([s[0] for s in self.stops])
        self._rgb = np.array([s[1:] for s in self.stops], dtype=float)

    def forward(self, f):
        """f (0..1) -> RGB colour, piecewise-linear interpolation over stops."""
        f = np.clip(f, 0.0, 1.0)
        r = np.interp(f, self._f, self._rgb[:, 0])
        g = np.interp(f, self._f, self._rgb[:, 1])
        b = np.interp(f, self._f, self._rgb[:, 2])
        return np.array([r, g, b])

    def reference_swatches(self, n=6):
        """Fixed swatches printed on the badge's reference scale."""
        f_vals = np.linspace(0, 1, n)
        return f_vals, np.array([self.forward(f) for f in f_vals])

    def inverse(self, rgb, n_search=400):
        """
        RGB -> f, by finding the nearest point on the calibration curve
        (dense search along the piecewise-linear path). Simple and robust
        for a 1-D physical curve living in 3-D colour space.
        """
        f_grid = np.linspace(0, 1, n_search)
        curve = np.array([self.forward(f) for f in f_grid])
        d2 = np.sum((curve - np.asarray(rgb)) ** 2, axis=1)
        best = np.argmin(d2)
        return float(f_grid[best]), float(np.sqrt(d2[best]))
