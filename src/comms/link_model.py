"""
CARES — RF Link Model
Log-distance path loss for UAV-to-UAV / UAV-to-GCS links.

Design targets (derived from actual map geometry):
  Hard scenario diagonal ≈ 3606m, 2-3 relays available.
  Each hop must bridge ~800-1000m. Target:
    full quality (1.0) to ~330m
    degrading from 330m → ~774m
    dead beyond ~774m

  Hardware spec: 23dBm TX, -95dBm sensitivity, n=2.7 (light-urban rubble).
  Link budget = 23 - (-95) = 118 dB.
  Full quality threshold: 118-10 = 108 dB  → d = 10^((108-40)/(27)) ≈ 330m
  Dead threshold: 118 dB → d = 10^((118-40)/(27)) ≈ 774m

NLOS penalty: +25 dB applied in dB-space (not as a probability multiplier).
  At 300m blocked: mean prx = 23 - (40+27*log10(300)+25) ≈ -97.5 dBm < -95 → dead.
  Forces relays around obstacles rather than hoping packets sneak through.
"""

import math
import random


class LinkModel:
    def __init__(self,
                 frequency_ghz: float = 2.4,
                 tx_power_dbm: float = 23.0,
                 rx_sensitivity_dbm: float = -95.0,
                 path_loss_exp: float = 2.7,
                 shadow_std_db: float = 4.0,
                 nlos_penalty_db: float = 25.0):
        self.frequency_ghz = frequency_ghz
        self.tx_power_dbm = tx_power_dbm
        self.rx_sensitivity_dbm = rx_sensitivity_dbm
        self.n = path_loss_exp
        self.shadow_std_db = shadow_std_db   # log-normal fading: drives MC variance
        self.nlos_penalty_db = nlos_penalty_db
        # Reference path loss at d=1m for 2.4 GHz
        self._L0 = 40.0 + 20.0 * math.log10(frequency_ghz / 2.4)

    def path_loss_db(self, distance: float, nlos: bool = False) -> float:
        """
        Mean log-distance path loss + log-normal shadow fading.
        PL(d) = L0 + 10·n·log10(d) + X_σ  [+ nlos_penalty_db if blocked]
        """
        if distance <= 1.0:
            return 0.0
        pl = self._L0 + 10.0 * self.n * math.log10(distance)
        # Stochastic shadow fading — this is what makes each Monte Carlo seed differ
        pl += random.gauss(0.0, self.shadow_std_db)
        if nlos:
            pl += self.nlos_penalty_db
        return pl

    def link_quality_from_prx(self, prx_dbm: float) -> float:
        """
        Normalize received power to [0,1] link quality.
        Transition band: [sensitivity, sensitivity+10 dB].
        Factored out so both LOS and NLOS paths use identical thresholding.
        """
        if prx_dbm >= self.rx_sensitivity_dbm + 10.0:
            return 1.0
        elif prx_dbm <= self.rx_sensitivity_dbm:
            return 0.0
        return (prx_dbm - self.rx_sensitivity_dbm) / 10.0

    def link_quality(self, distance: float, nlos: bool = False) -> float:
        prx = self.tx_power_dbm - self.path_loss_db(distance, nlos=nlos)
        return self.link_quality_from_prx(prx)

    def packet_success_probability(self, distance: float, nlos: bool = False) -> float:
        return self.link_quality(distance, nlos=nlos)

