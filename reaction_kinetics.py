# reaction_kinetics.py
"""
Chemistry model behind the badge.

Design choice, matching the problem statement directly: the strip must
respond to CUMULATIVE ppm*h dose, not just instantaneous concentration,
and must NOT be linear across the whole range (real colorimetric layers
saturate). We use a pseudo-first-order, saturating conversion model:

    f(t) = 1 - exp( -k_eff(t) * D(t) )

where D(t) is cumulative dose (ppm*h) and k_eff folds in temperature and
humidity dependence of the reaction rate. f in [0,1] is "fraction of
reactive sites converted" -- this is what actually darkens the strip.

The expiry patch uses the same functional form but is driven by TIME
alone (not H2S), so it can independently confirm shelf life.
"""

import numpy as np


class DoseStripKinetics:
    def __init__(self, k0=0.028, T_ref_c=25.0, q10=1.9, rh_ref=50.0, rh_coeff=0.006):
        """
        k0        : base rate constant at reference temperature/humidity (per ppm*h)
        T_ref_c   : reference temperature the strip was calibrated at
        q10       : rate roughly multiplies by q10 for every 10 deg C rise
                    (standard way to describe temperature sensitivity of a
                    wet-chemistry reaction without needing full Arrhenius terms)
        rh_ref    : reference relative humidity
        rh_coeff  : fractional change in rate per % RH away from reference
                    (H2S/lead-acetate-type reactions need surface moisture,
                    so higher RH modestly speeds the reaction)
        """
        self.k0 = k0
        self.T_ref_c = T_ref_c
        self.q10 = q10
        self.rh_ref = rh_ref
        self.rh_coeff = rh_coeff

    def rate_multiplier(self, temp_c, rh_pct):
        """Combined temperature x humidity compensation factor, k(T,RH)/k0."""
        temp_factor = self.q10 ** ((temp_c - self.T_ref_c) / 10.0)
        rh_factor = 1.0 + self.rh_coeff * (rh_pct - self.rh_ref)
        rh_factor = np.clip(rh_factor, 0.5, 1.8)
        return temp_factor * rh_factor

    def simulate(self, t_h, conc_ppm, temp_c, rh_pct):
        """
        Integrates the strip's state through a real, time-varying exposure.
        Returns: f_final (fraction converted), effective_dose (the
        temperature/humidity-weighted integral that actually drove the
        reaction), and true_dose (plain ppm*h for scoring/reporting).
        """
        k_t = self.rate_multiplier(temp_c, rh_pct) * self.k0
        # effective dose = integral of k(t)*C(t) dt, i.e. rate-weighted exposure
        effective_dose = np.trapezoid(k_t * conc_ppm, t_h)
        f_final = 1 - np.exp(-effective_dose)
        true_dose = np.trapezoid(conc_ppm, t_h)
        return {
            'f_final': float(np.clip(f_final, 0, 0.999)),
            'effective_dose': float(effective_dose),
            'true_dose_ppmh': float(true_dose),
            'mean_rate_multiplier': float(np.mean(k_t) / self.k0),
        }

    def invert_effective_dose(self, f):
        """f -> effective_dose, the inverse of the forward model above."""
        f = np.clip(f, 1e-4, 0.999)
        return -np.log(1 - f)


class ExpiryPatchKinetics:
    def __init__(self, target_shelf_life_days=90, k_time_per_day=None,
                 T_ref_c=25.0, q10=2.2):
        """
        A separate, slower reaction driven purely by elapsed time (and
        storage temperature), tuned so f crosses the "expired" threshold
        (0.5) at target_shelf_life_days under reference storage conditions.
        """
        self.target_days = target_shelf_life_days
        self.T_ref_c = T_ref_c
        self.q10 = q10
        # solve k so that 1 - exp(-k * target_days) = 0.5  =>  k = ln(2)/target_days
        self.k_time_per_day = k_time_per_day or (np.log(2) / target_shelf_life_days)

    def state_at(self, days_elapsed, storage_temp_c=25.0):
        temp_factor = self.q10 ** ((storage_temp_c - self.T_ref_c) / 10.0)
        f = 1 - np.exp(-self.k_time_per_day * temp_factor * days_elapsed)
        return float(np.clip(f, 0, 0.999))

    def is_expired(self, days_elapsed, storage_temp_c=25.0, threshold=0.5):
        return self.state_at(days_elapsed, storage_temp_c) >= threshold

    def validate_shelf_life(self, storage_temp_c=25.0, threshold=0.5, tol_days=3):
        """
        Scans day-by-day to find the day the patch actually crosses the
        expiry threshold under given storage, and checks it against spec.
        """
        days = np.arange(0, self.target_days * 2, 0.5)
        f_vals = np.array([self.state_at(d, storage_temp_c) for d in days])
        crossing_idx = np.argmax(f_vals >= threshold)
        crossing_day = days[crossing_idx] if f_vals[crossing_idx] >= threshold else None
        within_tol = (crossing_day is not None and
                      abs(crossing_day - self.target_days) <= tol_days)
        return {
            'spec_days': self.target_days,
            'measured_crossing_day': crossing_day,
            'within_tolerance': bool(within_tol),
        }
