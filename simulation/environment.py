# environment.py
"""
Generates a synthetic occupational environment for one worker shift:
- H2S concentration profile C(t) in ppm, with baseline drift + random spike events
- Ambient temperature T(t) in deg C
- Relative humidity RH(t) in %

This stands in for real field data / a lab gas-chamber protocol until
sensor logs are available. Every profile carries its own ground-truth
cumulative dose so the rest of the pipeline can be scored against it.
"""

import numpy as np


class ShiftEnvironment:
    def __init__(self, duration_h=8.0, dt_h=1.0 / 60, seed=None):
        """
        duration_h : shift length in hours
        dt_h       : simulation time step in hours (default = 1 minute)
        """
        self.duration_h = duration_h
        self.dt_h = dt_h
        self.n_steps = int(duration_h / dt_h) + 1
        self.t_h = np.linspace(0, duration_h, self.n_steps)
        self.rng = np.random.default_rng(seed)

    def generate_h2s_profile(self, baseline_ppm=0.5, spike_rate_per_h=0.4,
                              spike_ppm_range=(2.0, 12.0), spike_duration_min_range=(3, 20)):
        """
        Low-level chronic baseline + occasional short-duration spikes.
        This mirrors the real hazard described in the brief: workers are not
        exposed to one big leak, they accumulate dose from many small ones.
        """
        conc = np.full(self.n_steps, baseline_ppm, dtype=float)

        # slow baseline drift (wind direction / process variation)
        drift = 0.15 * np.sin(2 * np.pi * self.t_h / self.duration_h + self.rng.uniform(0, 2 * np.pi))
        conc += np.clip(drift, -baseline_ppm * 0.8, None)

        # Poisson-arrival spike events
        n_spikes = self.rng.poisson(spike_rate_per_h * self.duration_h)
        for _ in range(n_spikes):
            start_h = self.rng.uniform(0, self.duration_h)
            dur_min = self.rng.uniform(*spike_duration_min_range)
            dur_h = dur_min / 60.0
            peak = self.rng.uniform(*spike_ppm_range)

            # triangular pulse (ramp up / ramp down), not a step function
            idx = np.where((self.t_h >= start_h) & (self.t_h <= start_h + dur_h))[0]
            if len(idx) == 0:
                continue
            local_t = self.t_h[idx] - start_h
            half = dur_h / 2
            shape = 1 - np.abs(local_t - half) / half
            conc[idx] += peak * np.clip(shape, 0, 1)

        conc = np.clip(conc, 0, None)
        return conc

    def generate_temperature_profile(self, base_c=32.0, daily_amp_c=6.0):
        """Warm field/rig-site diurnal-style curve over the shift window."""
        t = base_c + daily_amp_c * np.sin(np.pi * self.t_h / self.duration_h)
        t += self.rng.normal(0, 0.4, size=self.n_steps)
        return t

    def generate_humidity_profile(self, base_rh=60.0, amp_rh=15.0):
        rh = base_rh + amp_rh * np.sin(np.pi * self.t_h / self.duration_h + 0.6)
        rh += self.rng.normal(0, 1.5, size=self.n_steps)
        return np.clip(rh, 5, 100)

    def cumulative_dose_ppmh(self, conc_ppm):
        """Ground-truth cumulative dose via trapezoidal integration of C(t)."""
        return np.trapezoid(conc_ppm, self.t_h)

    def generate_shift(self, **kwargs):
        """Convenience: returns a dict with everything the rest of the pipeline needs."""
        conc = self.generate_h2s_profile(**kwargs.get('h2s_kwargs', {}))
        temp = self.generate_temperature_profile(**kwargs.get('temp_kwargs', {}))
        rh = self.generate_humidity_profile(**kwargs.get('rh_kwargs', {}))
        dose_true = self.cumulative_dose_ppmh(conc)
        return {
            't_h': self.t_h,
            'conc_ppm': conc,
            'temp_c': temp,
            'rh_pct': rh,
            'dose_true_ppmh': dose_true,
        }
