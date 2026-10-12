"""Mortality: the Social Security Administration's period life table for 2023.

`MALE_Q[a]` and `FEMALE_Q[a]` are the probability of dying between exact ages a and a + 1, for a = 0 to 119. They are copied from
third-party transcriptions of SSA's table (a JSON export, a TypeScript table in an open-source retirement calculator and a
spreadsheet), and the life expectancies worked out from these probabilities match the life-expectancy column of the same table to within 0.005
years at every age from 0 to 99 (at 65: 18.12 more years for men, 20.66 for women). SSA's own page (ssa.gov/oact/STATS/table4c6.html) could not be
fetched from this environment, so it was not read directly.

The households of this app do not record sex, so the model uses the average of the two (`UNISEX_Q`) for every spouse.
"""

from __future__ import annotations

import numpy as np

MALE_Q = np.array([
    0.006015, 0.000479, 0.000320, 0.000249, 0.000194, 0.000159, 0.000137, 0.000125,
    0.000120, 0.000120, 0.000125, 0.000140, 0.000173, 0.000233, 0.000327, 0.000463,
    0.000634, 0.000819, 0.000999, 0.001138, 0.001235, 0.001315, 0.001378, 0.001439,
    0.001509, 0.001595, 0.001685, 0.001783, 0.001876, 0.001970, 0.002085, 0.002202,
    0.002308, 0.002407, 0.002490, 0.002577, 0.002665, 0.002764, 0.002864, 0.002987,
    0.003115, 0.003253, 0.003419, 0.003600, 0.003777, 0.003931, 0.004073, 0.004245,
    0.004477, 0.004795, 0.005126, 0.005496, 0.005917, 0.006404, 0.006923, 0.007491,
    0.008173, 0.008938, 0.009714, 0.010494, 0.011337, 0.012232, 0.013196, 0.014229,
    0.015316, 0.016455, 0.017574, 0.018735, 0.019981, 0.021366, 0.022903, 0.024615,
    0.026504, 0.028648, 0.031071, 0.033802, 0.037010, 0.041158, 0.045461, 0.050346,
    0.055633, 0.061757, 0.068358, 0.075420, 0.083364, 0.092680, 0.103459, 0.115502,
    0.129018, 0.143810, 0.159458, 0.176551, 0.195360, 0.216286, 0.238799, 0.262268,
    0.286291, 0.310944, 0.332325, 0.349036, 0.366568, 0.384960, 0.404252, 0.424488,
    0.445712, 0.467998, 0.491398, 0.515968, 0.541766, 0.568854, 0.597297, 0.627162,
    0.658520, 0.691446, 0.726018, 0.762319, 0.800435, 0.840457, 0.882480, 0.926604,
])

FEMALE_Q = np.array([
    0.005125, 0.000392, 0.000229, 0.000188, 0.000155, 0.000133, 0.000115, 0.000105,
    0.000100, 0.000098, 0.000101, 0.000111, 0.000126, 0.000152, 0.000188, 0.000229,
    0.000273, 0.000323, 0.000372, 0.000410, 0.000441, 0.000476, 0.000513, 0.000546,
    0.000582, 0.000609, 0.000641, 0.000683, 0.000740, 0.000808, 0.000878, 0.000947,
    0.001018, 0.001089, 0.001154, 0.001209, 0.001263, 0.001347, 0.001438, 0.001533,
    0.001643, 0.001742, 0.001845, 0.001954, 0.002075, 0.002187, 0.002306, 0.002438,
    0.002595, 0.002791, 0.003030, 0.003288, 0.003554, 0.003847, 0.004172, 0.004532,
    0.004923, 0.005365, 0.005815, 0.006333, 0.006923, 0.007555, 0.008220, 0.008881,
    0.009514, 0.010188, 0.010880, 0.011659, 0.012543, 0.013581, 0.014769, 0.016153,
    0.017705, 0.019495, 0.021533, 0.023846, 0.026458, 0.029700, 0.033135, 0.036982,
    0.041183, 0.045959, 0.051282, 0.057262, 0.064107, 0.071752, 0.080490, 0.090566,
    0.102204, 0.115178, 0.129176, 0.144229, 0.160353, 0.177635, 0.196502, 0.216846,
    0.238750, 0.261359, 0.283899, 0.306491, 0.329680, 0.353333, 0.377300, 0.401416,
    0.425501, 0.451031, 0.478092, 0.506778, 0.537185, 0.568854, 0.597297, 0.627162,
    0.658520, 0.691446, 0.726018, 0.762319, 0.800435, 0.840457, 0.882480, 0.926604,
])

UNISEX_Q = 0.5 * (MALE_Q + FEMALE_Q)



def death_years(ages, n_years: int, uniforms: np.ndarray) -> np.ndarray:
    """For each draw and each spouse, the index of the simulated year in which they die (`n_years` or more when they outlive the horizon).

    `ages` are the spouses' ages now; `uniforms` has shape (draws, spouses). A spouse of age a is alive at the start of year t with
    probability prod(1 - q) over ages a .. a + t - 1 and dies in the first year at whose end the survival probability has fallen below the draw.
    """
    out = np.full(uniforms.shape, n_years + 1, dtype=np.int64)
    for j, age in enumerate(ages):
        q = UNISEX_Q[age : age + n_years]
        survival = np.cumprod(1.0 - q)  # survival to the end of year t
        out[:, j] = np.searchsorted(-survival, -uniforms[:, j], side="left")
    return out
