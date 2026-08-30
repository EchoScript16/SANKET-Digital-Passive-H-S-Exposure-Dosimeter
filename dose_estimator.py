# dose_estimator.py
"""
This is the algorithm that would actually ship inside the phone app.

Pipeline, matching the product description exactly:
1. Photograph gives distorted RGB for the strip AND the printed reference
   swatches (same frame, same light).
2. Fit a per-channel affine correction FROM the known true swatch colours
   TO the photographed swatch colours, then invert it -- this is the
   "corrects for whatever lighting the photo was taken in" step.
3. Apply the inverse correction to the photographed strip colour to
   recover an estimate of its true colour.
4. Invert the corrected colour through the calibration gradient to get
   fraction reacted (f_hat), then through the reaction kinetics to get
   effective dose.
5. Divide out the average temperature/humidity rate multiplier (from
   logged sensor data at capture time) to recover an estimated ppm*h dose.
6. Report a confidence range from the residual calibration error, not a
   bare number -- the brief explicitly asks for the estimate to be stated
   as an estimate.
"""

import numpy as np


class DoseEstimator:
    def __init__(self, color_gradient, kinetics):
        self.color_gradient = color_gradient
        self.kinetics = kinetics

    @staticmethod
    def _fit_affine_correction(true_swatch_rgb, photographed_swatch_rgb):
        """
        Per-channel least-squares fit: photographed = a*true + b
        Returns (a, b) per channel; inverting gives corrected = (photographed - b) / a
        """
        a = np.zeros(3)
        b = np.zeros(3)
        for c in range(3):
            x = true_swatch_rgb[:, c]
            y = photographed_swatch_rgb[:, c]
            A = np.vstack([x, np.ones_like(x)]).T
            coef, *_ = np.linalg.lstsq(A, y, rcond=None)
            a[c], b[c] = coef
        return a, b

    def estimate(self, photographed_strip_rgb, true_swatch_f, true_swatch_rgb,
                 photographed_swatch_rgb, mean_rate_multiplier, n_bootstrap=60):
        """
        Returns a dict with the point estimate and a 95%-style confidence range,
        expressed in the same ppm*h units the badge and app both display.
        """
        a, b = self._fit_affine_correction(true_swatch_rgb, photographed_swatch_rgb)

        corrected_strip_rgb = (photographed_strip_rgb - b) / a
        f_hat, residual = self.color_gradient.inverse(corrected_strip_rgb)

        effective_dose_hat = self.kinetics.invert_effective_dose(f_hat)
        # divide out the temperature/humidity compensation to recover ppm*h
        dose_hat = effective_dose_hat / max(mean_rate_multiplier, 1e-3) / self.kinetics.k0

        # bootstrap the swatch fit with small perturbations to get a spread,
        # standing in for propagated calibration + colour-matching uncertainty.
        # Jitter magnitude is matched to the same sensor-noise scale used when
        # the photograph itself was simulated, so the reported interval
        # reflects the real measurement noise rather than an arbitrarily
        # tight number.
        rng = np.random.default_rng(0)
        boot_doses = []
        for _ in range(n_bootstrap):
            jitter = rng.normal(0, 4.0, size=photographed_swatch_rgb.shape)
            a_b, b_b = self._fit_affine_correction(true_swatch_rgb, photographed_swatch_rgb + jitter)
            strip_jitter = rng.normal(0, 4.0, size=3)
            corrected_b = (photographed_strip_rgb + strip_jitter - b_b) / a_b
            f_b, _ = self.color_gradient.inverse(corrected_b)
            eff_b = self.kinetics.invert_effective_dose(f_b)
            boot_doses.append(eff_b / max(mean_rate_multiplier, 1e-3) / self.kinetics.k0)

        boot_doses = np.array(boot_doses)
        spread = np.std(boot_doses)
        # widen slightly beyond the raw bootstrap spread: with only 6
        # calibration swatches the bootstrap itself under-samples fit
        # uncertainty, so this keeps the stated interval honest rather
        # than optimistic.
        lo = dose_hat - 2.4 * spread
        hi = dose_hat + 2.4 * spread

        return {
            'dose_estimate_ppmh': float(dose_hat),
            'ci_low_ppmh': float(lo),
            'ci_high_ppmh': float(hi),
            'f_hat': float(f_hat),
            'color_match_residual': float(residual),
        }
