"""The year-by-year adaptive planner (spec part B): lookahead search with rollouts.

Each simulated year, on each evaluation path, the planner

1. observes the state after that year's returns have happened (balances by account and asset class, basis,
   loss carryforward, any loan, age, this year's income and goals): everything the household could know;
2. lists candidate actions for the year: stock share, Roth conversion, private credit sleeve, 401(k)
   type, goal funding (sell or borrow) and realizing gains up to the 0% bracket;
3. scores each by simulating `k` fresh futures from the current state: the candidate is applied for the
   rest of this year, then the CONTINUATION policy (the best fixed strategy) is followed to the horizon,
   and the score is the certainty-equivalent after-tax wealth at the horizon (the same objective);
4. takes the best candidate, and advances the real path one year.

Search. Scoring every combination of the six dimensions (about 2,500) every year is far too slow, so
the planner uses COORDINATE SEARCH, the spec's first choice: start from the continuation policy's action,
then improve one dimension at a time holding the others fixed, for two passes. That is at most about 35
candidates a year instead of thousands, and it needs no second, cheaper scoring model (the spec's second
choice, pruning with a cheap first score, would). A candidate replaces the incumbent only if its advantage over
it is at least `z_min` standard errors across the `k` rollouts (paired: every candidate sees the same futures).
Stock-share candidates are the menu's shares with the strategy's glide path applied, so "60% stocks" means
what it means in a fixed strategy at every age.

Why the search is not the plain one. Judged on independent futures (`app/study/decision_quality.py`,
`reports/adaptive_decision_quality.md`) the plain search LOWERS the planner's own objective on average: the best
of a dozen candidates scored on the same 32 rollouts is flattered by luck, and 32 rollouts almost never contain
the futures in which money runs out, which dominate a certainty equivalent. Two measures, both measured to help:

* IMPORTANCE SAMPLING (`tilt`): half the rollout pairs draw their equity shocks from a market `tilt` standard
  deviations a year worse, and every rollout carries the likelihood ratio against the 50/50 mixture of the two (a
  weight between 0 and 2), so weighted averages are still estimates under the market's own distribution but the
  bad stretches are in the sample about as often as the good ones.
* CONFIRMATION (`confirm_k`, `confirm_z`): a change the search proposes is re-tested, one change at a time, on
  `confirm_k` fresh futures it was not chosen on, and kept only if it wins by `confirm_z` standard errors there.

(Stratifying the first imagined year's draws was tried and gave no measurable benefit, so it is not here.)

No look-ahead. The futures a decision is scored on are drawn from a counter-based random stream keyed by
(rollout seed, path, year, rollout), where the rollout seed comes from a `SeedSequence` child disjoint from
the ones that generate the evaluation returns and incomes, and the rollout wage process restarts from the
path's wage level in the decision year, never from its later wages. A decision in year t reads the
evaluation path's inputs only up to and including year t. `tests/test_adaptive.py` checks both: changing the
path's later returns and wages changes nothing about the decisions already taken, and the two random
streams do not overlap.

Everything runs through `_run_years`, the same function the fixed strategies use, so forcing the
continuation action every year reproduces the fixed strategy exactly.

Shadow mode (`AdaptiveSettings.shadow`) searches and records what the planner would choose while the path follows the
continuation; `probe_candidates` then re-scores every candidate and the chosen action on futures the planner never
used. Together they measure a search design's decisions on the same states, which is how the design above was chosen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from app.jit import jit, prange
from app.sim import income, markets
from app.sim.simulate import (
    _KERNEL_LOCK,
    A_BORROW,
    A_CONV_TOP,
    A_K401_ROTH,
    A_PC,
    A_REALIZE,
    A_STOCK,
    HC_SS,
    NACT,
    NGATE,
    NLOG,
    NSTATE,
    NY,
    RUN_BEGIN,
    RUN_REST,
    S_BB,
    S_BBASIS,
    S_BE,
    S_BP,
    S_PB,
    S_PE,
    S_PP,
    S_UNFUNDED,
    SP_GLIDE_DROP,
    SP_GLIDE_START,
    SP_RESERVE,
    TV_AGE,
    TV_AGED,
    TV_DEPS,
    TV_GOAL,
    TV_KIDS,
    TV_NEARN,
    Policy,
    SimInputs,
    _run_years,
    _stock_share,
)
from app.tax import params_2026 as P
from app.tax.engine import pretax_withdrawal_rate, tax_core

# --------------------------------------------------------------------------------------------
# The action space (spec B3)
# --------------------------------------------------------------------------------------------

# The decisions the planner chooses among, in the order coordinate search visits them: tax timing first
# (conversion, realizing gains, how a goal is paid, 401(k) type), then the portfolio (private credit, stocks).
DIMS = np.array([A_CONV_TOP, A_REALIZE, A_BORROW, A_K401_ROTH, A_PC, A_STOCK])
ND = len(DIMS)
DIM_NAMES = ("conversion", "realize_gains", "goal_funding", "k401", "private_credit", "stock_share")

STOCK_GRID = np.array([0.50, 0.60, 0.70, 0.80, 0.90, 1.00])
CONV_GRID = np.array([0.0, P.TOP_OF_12, P.TOP_OF_22, P.TOP_OF_24])  # none, fill the 12%, 22%, 24% bracket
PC_GRID = np.array([0.0, 0.05, 0.10, 0.15])
MAX_CANDIDATES = 48

# Settings vector.
CFG_K, CFG_ZMIN, CFG_GAMMA, CFG_FLOOR, CFG_PASSES, CFG_DIMS, CFG_CONFIRM_K, CFG_CONFIRM_Z, CFG_APPLY, CFG_TILT = range(10)
NCFG = 10
MAX_MOVES = 16  # decisions the search can change in one year (two passes over six dimensions, with room to spare)
NEXTRA = 4  # per decision: moves proposed, moves confirmed, certainty equivalent of the final action and of the continuation on the fresh futures


# --------------------------------------------------------------------------------------------
# Counter-based random numbers: the same draws whatever the thread schedule
# --------------------------------------------------------------------------------------------

_GOLDEN = 0x9E3779B97F4A7C15
_M1 = 0xBF58476D1CE4E5B9
_M2 = 0x94D049BB133111EB
_TWO_POW_NEG53 = 1.1102230246251565e-16
N_DRAWS = 10  # uniforms per (rollout pair, future year): 4 Box-Muller pairs of normals + 2 job-loss uniforms


@jit
def _mix64(x):
    x = (x ^ (x >> np.uint64(30))) * np.uint64(_M1)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(_M2)
    return x ^ (x >> np.uint64(31))


@jit
def _uniform(base, n):
    """The n-th uniform in (0, 1) of the stream `base`."""
    h = _mix64(base + (np.uint64(n) + np.uint64(1)) * np.uint64(_GOLDEN))
    return (float(h >> np.uint64(11)) + 0.5) * _TWO_POW_NEG53


@jit
def _decision_stream(seed, path, year):
    """The base of the stream for one decision: distinct for every (path, year), disjoint across seeds."""
    a = _mix64(np.uint64(seed) ^ np.uint64(0xD1B54A32D192ED03))
    a = _mix64(a ^ (np.uint64(path) * np.uint64(_GOLDEN) + np.uint64(1)))
    return _mix64(a ^ (np.uint64(year) * np.uint64(_M2) + np.uint64(7)))


@jit
def _confirmation_stream(stream):
    """The stream of the fresh futures a proposed change is confirmed on: independent of the one it was proposed on."""
    return _mix64(stream ^ np.uint64(0xC2B2AE3D27D4EB4F))



# --------------------------------------------------------------------------------------------
# The futures a decision is scored on
# --------------------------------------------------------------------------------------------


@jit
def _mixture_weight(total_shock, n_future, tilt):
    """Importance weight of a rollout whose equity shocks (standard-normal units) summed to `total_shock` over
    `n_future` years, when half the rollouts come from the market and half from the market shifted down by
    `tilt` a year: market density / (0.5 market + 0.5 shifted) = 1 / (0.5 + 0.5 L), L = shifted / market."""
    log_ratio = -tilt * total_shock - 0.5 * n_future * tilt * tilt
    return 1.0 / (0.5 + 0.5 * np.exp(min(log_ratio, 700.0)))


@jit
def _make_futures(
    stream, t, k_roll, tv, mk_means, mk_sds, mk_chol, inc_base, inc_growth, inc_working, n_earn, lp0,
    rets_p, wages_p, k401_p, wt_p, fut_rets, fut_wages, fut_k, fut_wt, fut_w, tilt,
):
    """Fill the rollout arrays for decision year `t`: index t holds the real year (already seen), every later
    year is a fresh draw. Rollouts come in antithetic pairs (the second mirrors the first's normals), so the
    average of the rollouts' returns is exactly the expected return: no sampling error in the first moment.

    With `tilt` > 0 every other pair is drawn from a proposal whose equity shocks are shifted down by `tilt`
    standard deviations a year, and each rollout carries an importance weight `fut_w` (the likelihood ratio of
    the market against the 50/50 mixture of market and proposal, so the weights stay between 0 and 2). The
    weighted average of any outcome is still an unbiased estimate under the market's own distribution, but the
    bad stretches that decide a certainty equivalent (it is dominated by the few futures in which money runs
    out) are in the sample about as often as the good ones instead of once in several hundred rollouts.
    """
    n_years = tv.shape[0]
    for k in range(k_roll):
        fut_w[k] = 1.0
    for k in range(k_roll):
        fut_rets[k, t, :] = rets_p[t, :]
        fut_wages[k, t] = wages_p[t]
        fut_k[k, t] = k401_p[t]
        fut_wt[k, t, 0] = wt_p[t, 0]
        fut_wt[k, t, 1] = wt_p[t, 1]
    lp_a = np.zeros(2)
    lp_b = np.zeros(2)
    z = np.zeros(8)
    for q in range(k_roll // 2):
        a = 2 * q
        b = a + 1
        lp_a[0], lp_a[1] = lp0[0], lp0[1]
        lp_b[0], lp_b[1] = lp0[0], lp0[1]
        shift = -tilt if (tilt > 0.0 and q % 2 == 1) else 0.0
        sum_a = 0.0
        sum_b = 0.0
        for m in range(1, n_years - t):
            s = t + m
            n0 = (q * n_years + m) * N_DRAWS
            for j in range(4):  # four pairs of independent standard normals (8 normals)
                u1 = _uniform(stream, n0 + 2 * j)
                u2 = _uniform(stream, n0 + 2 * j + 1)
                radius = np.sqrt(-2.0 * np.log(u1))
                z[2 * j] = radius * np.cos(2.0 * np.pi * u2)
                z[2 * j + 1] = radius * np.sin(2.0 * np.pi * u2)
            # returns: correlated through the Cholesky factor of the correlation matrix
            za = z[0] + shift
            zb = -z[0] + shift
            sum_a += za
            sum_b += zb
            for i in range(3):
                rest = mk_chol[i, 1] * z[1] + mk_chol[i, 2] * z[2]
                fut_rets[a, s, i] = max(mk_means[i] + mk_sds[i] * (mk_chol[i, 0] * za + rest), markets.MIN_RETURN)
                fut_rets[b, s, i] = max(mk_means[i] + mk_sds[i] * (mk_chol[i, 0] * zb - rest), markets.MIN_RETURN)
            # wages: each earner's permanent level moves with growth and a shock, plus a transitory shock
            wage_a = 0.0
            wage_b = 0.0
            for e in range(n_earn):
                zp = z[3 + 2 * e]
                zt = z[4 + 2 * e]
                lp_a[e] += inc_growth[e, s - 1] + income.PERMANENT_SD * zp
                lp_b[e] += inc_growth[e, s - 1] - income.PERMANENT_SD * zp
                u_loss = _uniform(stream, n0 + 8 + e)
                loss_a = income.JOB_LOSS_SHARE if u_loss < income.JOB_LOSS_PROBABILITY else 0.0
                loss_b = income.JOB_LOSS_SHARE if (1.0 - u_loss) < income.JOB_LOSS_PROBABILITY else 0.0
                wage_a += inc_base[e] * np.exp(lp_a[e] + income.TRANSITORY_SD * zt) * (1.0 - loss_a)
                wage_b += inc_base[e] * np.exp(lp_b[e] - income.TRANSITORY_SD * zt) * (1.0 - loss_b)
            wage_a *= inc_working[s]
            wage_b *= inc_working[s]
            for which in range(2):
                k = a if which == 0 else b
                w = wage_a if which == 0 else wage_b
                contribution = min(P.LIMIT_401K_EMPLOYEE * tv[s, TV_NEARN], 0.20 * w)
                fut_wages[k, s] = w
                fut_k[k, s] = contribution
                if w > 0.0:
                    fut_wt[k, s, 0] = tax_core(w - contribution, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[s, TV_KIDS], tv[s, TV_DEPS], 0.0, tv[s, TV_AGED]).total_tax
                    fut_wt[k, s, 1] = tax_core(w, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, tv[s, TV_KIDS], tv[s, TV_DEPS], 0.0, tv[s, TV_AGED]).total_tax
                else:
                    fut_wt[k, s, 0] = 0.0
                    fut_wt[k, s, 1] = 0.0
        if tilt > 0.0:
            n_future = n_years - t - 1
            fut_w[a] = _mixture_weight(sum_a, n_future, tilt)
            fut_w[b] = _mixture_weight(sum_b, n_future, tilt)


# --------------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------------


@jit
def _utility(wealth, gamma, floor):
    """CRRA utility of after-tax wealth, which counts as `floor` below it (the planner's objective)."""
    x = max(wealth, floor)
    if abs(gamma - 1.0) < 1e-9:
        return np.log(x)
    return x ** (1.0 - gamma) / (1.0 - gamma)


@jit
def _certainty_equivalent(mean_utility, gamma):
    if abs(gamma - 1.0) < 1e-9:
        return np.exp(mean_utility)
    return ((1.0 - gamma) * mean_utility) ** (1.0 / (1.0 - gamma))


@jit
def _score(st, ys, act_candidate, t, k_roll, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, util_out):
    """Mean utility over the rollouts (importance-weighted, self-normalized) of applying `act_candidate` in year t,
    then the continuation policy to the horizon."""
    n_years = tv.shape[0]
    total = 0.0
    weights = 0.0
    for k in range(k_roll):
        st_r[:] = st
        ys_r[:] = ys
        act_r[:] = act_candidate
        wealth, _ = _run_years(
            st_r, ys_r, act_r, tv, hhc, row, gates1, fut_rets[k], fut_wages[k], fut_k[k], fut_wt[k],
            t, n_years, RUN_REST, True, False, scratch_pw, False, scratch_log,
        )
        u = _utility(wealth, gamma, floor)
        util_out[k] = u
        total += fut_w[k] * u
        weights += fut_w[k]
    return total / weights


@jit
def _dim_values(dim, st, tv, t, k_t, row, vals):
    """The values worth trying for one decision this year (none when it cannot matter).

    Stock-share candidates are the menu's shares *with the strategy's glide path applied*, exactly as a fixed
    strategy holding that share would: late in life "60% stocks" means 60% less the glide, not a flat 60%."""
    if dim == A_CONV_TOP:
        if st[S_PE] + st[S_PB] + st[S_PP] > 1.0:
            for i in range(CONV_GRID.shape[0]):
                vals[i] = CONV_GRID[i]
            return CONV_GRID.shape[0]
        return 0
    if dim == A_REALIZE:
        if st[S_BE] - st[S_BBASIS] > 1.0:
            vals[0] = 0.0
            vals[1] = 1.0
            return 2
        return 0
    if dim == A_BORROW:
        if tv[t, TV_GOAL] > 0.0 and st[S_BE] + st[S_BB] + st[S_BP] > 1.0:
            vals[0] = 0.0
            vals[1] = 1.0
            return 2
        return 0
    if dim == A_K401_ROTH:
        if k_t > 0.0:
            vals[0] = 0.0
            vals[1] = 1.0
            return 2
        return 0
    if dim == A_PC:
        for i in range(PC_GRID.shape[0]):
            vals[i] = PC_GRID[i]
        return PC_GRID.shape[0]
    if dim == A_STOCK:
        if row[SP_RESERVE] > 0.5:  # with a spending reserve the stock share is whatever the reserve leaves: nothing to choose
            return 0
        for i in range(STOCK_GRID.shape[0]):
            vals[i] = _stock_share(tv[t, TV_AGE], STOCK_GRID[i], row[SP_GLIDE_START], row[SP_GLIDE_DROP])
        return STOCK_GRID.shape[0]
    return 0


@jit
def _find(cand_act, n, trial):
    for c in range(n):
        same = True
        for d in range(ND):
            if cand_act[c, DIMS[d]] != trial[DIMS[d]]:
                same = False
                break
        if same:
            return c
    return -1


@jit
def _significant_vec(u_a, u_b, w, k_roll, z_min):
    """Is `a` better than `b` by at least `z_min` standard errors? Paired over the first `k_roll` rollouts, with the
    importance weights `w` (all 1 without a tilt; then this is the usual paired t statistic)."""
    weights = 0.0
    mean = 0.0
    for k in range(k_roll):
        weights += w[k]
        mean += w[k] * (u_a[k] - u_b[k])
    mean /= weights
    if mean <= 0.0:
        return False
    var = 0.0
    for k in range(k_roll):
        d = u_a[k] - u_b[k] - mean
        var += w[k] * w[k] * d * d
    var = var / (weights * weights) * k_roll / max(1, k_roll - 1)
    if var <= 0.0:
        return True
    return mean / np.sqrt(var) >= z_min


@jit
def _significant(cand_k, a, b, w, k_roll, z_min):
    return _significant_vec(cand_k[a], cand_k[b], w, k_roll, z_min)


@jit
def _coordinate_search(
    st, ys, act0, t, k_t, k_roll, passes, z_min, dims_mask, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w,
    st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, cand_act, cand_u, cand_k, trial, vals, mv_dim, mv_val,
):
    """Coordinate search from the continuation action. Returns (candidates scored, index of the winner, changes made).
    The changes, in the order they were made, are left in `mv_dim` / `mv_val` (one decision, one new value each)."""
    cand_act[0, :] = act0
    cand_u[0] = _score(
        st, ys, cand_act[0], t, k_roll, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r,
        scratch_pw, scratch_log, gamma, floor, cand_k[0],
    )
    n = 1
    best = 0
    n_moves = 0
    for _ in range(passes):
        improved = False
        for di in range(ND):
            if (dims_mask >> di) & 1 == 0:
                continue  # this decision is not the planner's to make in this run
            dim = DIMS[di]
            nv = _dim_values(dim, st, tv, t, k_t, row, vals)
            best_here = -1
            for vi in range(nv):
                value = vals[vi]
                if value == cand_act[best, dim]:
                    continue
                trial[:] = cand_act[best]
                trial[dim] = value
                idx = _find(cand_act, n, trial)
                if idx < 0:
                    if n >= MAX_CANDIDATES - 1:  # one slot stays free for the action finally taken
                        continue
                    idx = n
                    cand_act[idx, :] = trial
                    cand_u[idx] = _score(
                        st, ys, cand_act[idx], t, k_roll, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w,
                        st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, cand_k[idx],
                    )
                    n += 1
                if best_here < 0 or cand_u[idx] > cand_u[best_here]:
                    best_here = idx
            if best_here >= 0 and cand_u[best_here] > cand_u[best] and _significant(cand_k, best_here, best, fut_w, k_roll, z_min):
                if n_moves < MAX_MOVES:
                    mv_dim[n_moves] = di
                    mv_val[n_moves] = cand_act[best_here, dim]
                    n_moves += 1
                best = best_here
                improved = True
        if not improved:
            break
    return n, best, n_moves


@jit
def _confirm_moves(
    st, ys, act0, t, k2, z_c, mv_dim, mv_val, n_moves, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w,
    st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, picked, trial, u_inc, u_try, means,
):
    """Re-test the changes the search proposed on FRESH futures, which the search never saw.

    The search picks the best of several dozen candidates on one sample, so the winner's advantage is partly luck
    (the optimizer's curse). Here each proposed change is applied to the action confirmed so far and kept only if
    it beats it by `z_c` standard errors on futures drawn independently of the ones it was chosen on: one test per
    change, no selection among candidates, so nothing is flattered. Returns the number of changes kept; `picked`
    holds the final action, and `means` the mean utility of the continuation and of the final action on the fresh futures.
    """
    picked[:] = act0
    mean_inc = _score(
        st, ys, picked, t, k2, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r,
        scratch_pw, scratch_log, gamma, floor, u_inc,
    )
    means[0] = mean_inc
    kept = 0
    for mi in range(n_moves):
        trial[:] = picked
        trial[DIMS[mv_dim[mi]]] = mv_val[mi]
        if trial[DIMS[mv_dim[mi]]] == picked[DIMS[mv_dim[mi]]]:
            continue
        mean_try = _score(
            st, ys, trial, t, k2, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r,
            scratch_pw, scratch_log, gamma, floor, u_try,
        )
        if mean_try > mean_inc and _significant_vec(u_try, u_inc, fut_w, k2, z_c):
            picked[:] = trial
            u_inc[:k2] = u_try[:k2]
            mean_inc = mean_try
            kept += 1
    means[1] = mean_inc
    return kept


# --------------------------------------------------------------------------------------------
# One path, and all paths
# --------------------------------------------------------------------------------------------


@jit
def _adaptive_path(
    p, p_abs, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
    inc_working, n_earn, cfg, seed, force, record, out, path_wealth, chosen, cont, ce_chosen, ce_cont, n_cand, extra,
    rec_act, rec_ce, rec_state, record_state, log, do_log,
):
    n_years = tv.shape[0]
    k_roll = int(cfg[CFG_K])
    k2 = int(cfg[CFG_CONFIRM_K])
    passes = int(cfg[CFG_PASSES])
    z_min = cfg[CFG_ZMIN]
    z_c = cfg[CFG_CONFIRM_Z]
    dims_mask = int(cfg[CFG_DIMS])
    gamma = cfg[CFG_GAMMA]
    floor = cfg[CFG_FLOOR]
    tilt = cfg[CFG_TILT]
    apply = cfg[CFG_APPLY] > 0.5
    cap2 = max(k2, 2)
    st = init.copy()
    ys = np.zeros(NY)
    act0 = np.zeros(NACT)
    act = np.zeros(NACT)
    picked = np.zeros(NACT)
    gates1 = np.ones((n_years, NGATE))
    fut_rets = np.zeros((k_roll, n_years, 3))
    fut_wages = np.zeros((k_roll, n_years))
    fut_k = np.zeros((k_roll, n_years))
    fut_wt = np.zeros((k_roll, n_years, 2))
    fut_w = np.ones(k_roll)
    fut2_w = np.ones(cap2)
    fut2_rets = np.zeros((cap2, n_years, 3))
    fut2_wages = np.zeros((cap2, n_years))
    fut2_k = np.zeros((cap2, n_years))
    fut2_wt = np.zeros((cap2, n_years, 2))
    st_r = np.zeros(NSTATE)
    ys_r = np.zeros(NY)
    act_r = np.zeros(NACT)
    cand_act = np.zeros((MAX_CANDIDATES, NACT))
    cand_u = np.zeros(MAX_CANDIDATES)
    cand_k = np.zeros((MAX_CANDIDATES, k_roll))
    trial = np.zeros(NACT)
    vals = np.zeros(8)
    mv_dim = np.zeros(MAX_MOVES, dtype=np.int64)
    mv_val = np.zeros(MAX_MOVES)
    u_inc = np.zeros(cap2)
    u_try = np.zeros(cap2)
    means = np.zeros(2)
    scratch_pw = np.zeros(n_years)
    scratch_log = np.zeros((1, NLOG))
    lp0 = np.zeros(2)
    taxes = 0.0
    wealth = 0.0
    for t in range(n_years):
        _run_years(st, ys, act0, tv, hhc, row, gates1, rets[p], wages[p], k401[p], wt[p], t, t + 1, RUN_BEGIN, False, False, scratch_pw, False, scratch_log)
        act[:] = act0
        picked[:] = act0
        if record_state:
            rec_state[p, t, :] = st
        if not force:
            lp0[0] = logperm[p, t, 0]
            lp0[1] = logperm[p, t, 1]
            stream = _decision_stream(seed, p_abs, t)
            _make_futures(
                stream, t, k_roll, tv, mk_means, mk_sds, mk_chol, inc_base, inc_growth, inc_working, n_earn, lp0,
                rets[p], wages[p], k401[p], wt[p], fut_rets, fut_wages, fut_k, fut_wt, fut_w, tilt,
            )
            n, best, n_moves = _coordinate_search(
                st, ys, act0, t, k401[p, t], k_roll, passes, z_min, dims_mask, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w,
                st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, cand_act, cand_u, cand_k, trial, vals, mv_dim, mv_val,
            )
            picked[:] = cand_act[best]
            kept = n_moves
            fresh_chosen = cand_u[best]
            fresh_cont = cand_u[0]
            if k2 > 0 and n_moves > 0:
                _make_futures(
                    _confirmation_stream(stream), t, k2, tv, mk_means, mk_sds, mk_chol, inc_base, inc_growth, inc_working, n_earn, lp0,
                    rets[p], wages[p], k401[p], wt[p], fut2_rets, fut2_wages, fut2_k, fut2_wt, fut2_w, tilt,
                )
                kept = _confirm_moves(
                    st, ys, act0, t, k2, z_c, mv_dim, mv_val, n_moves, tv, hhc, row, gates1, fut2_rets, fut2_wages, fut2_k, fut2_wt, fut2_w,
                    st_r, ys_r, act_r, scratch_pw, scratch_log, gamma, floor, picked, trial, u_inc, u_try, means,
                )
                fresh_cont = means[0]
                fresh_chosen = means[1]
                # the action finally taken may be one the search never scored (some of its changes were dropped)
                best = _find(cand_act, n, picked)
                if best < 0:
                    best = n
                    cand_act[best, :] = picked
                    cand_u[best] = _score(
                        st, ys, picked, t, k_roll, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r,
                        scratch_pw, scratch_log, gamma, floor, cand_k[best],
                    )
                    n += 1
            if apply:
                act[:] = picked
            n_cand[p, t] = n
            ce_chosen[p, t] = _certainty_equivalent(cand_u[best], gamma)
            ce_cont[p, t] = _certainty_equivalent(cand_u[0], gamma)
            extra[p, t, 0] = n_moves
            extra[p, t, 1] = kept
            extra[p, t, 2] = _certainty_equivalent(fresh_chosen, gamma)
            extra[p, t, 3] = _certainty_equivalent(fresh_cont, gamma)
            if record:
                for c in range(n):
                    for d in range(ND):
                        rec_act[p, t, c, d] = cand_act[c, DIMS[d]]
                    rec_ce[p, t, c] = _certainty_equivalent(cand_u[c], gamma)
        for d in range(ND):
            chosen[p, t, d] = picked[DIMS[d]]
            cont[p, t, d] = act0[DIMS[d]]
        w, tax = _run_years(
            st, ys, act, tv, hhc, row, gates1, rets[p], wages[p], k401[p], wt[p], t, t + 1, RUN_REST, t == n_years - 1,
            True, path_wealth[p], do_log, log,
        )
        taxes += tax
        wealth = w if t == n_years - 1 else wealth
    pretax = st[S_PE] + st[S_PB] + st[S_PP]
    owed = pretax * pretax_withdrawal_rate(pretax, hhc[HC_SS], tv[n_years - 1, TV_AGED])
    out[p, 0] = wealth
    out[p, 1] = taxes
    out[p, 2] = owed
    out[p, 3] = st[S_UNFUNDED]


@jit(parallel=True, nogil=True)
def _adaptive_batch(
    p_offset, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
    inc_working, n_earn, cfg, seed, force, record, out, path_wealth, chosen, cont, ce_chosen, ce_cont, n_cand, extra,
    rec_act, rec_ce, rec_state, record_state, log, log_path,
):
    n_paths = rets.shape[0]
    for p in prange(n_paths):
        _adaptive_path(
            p, p_offset + p, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base,
            inc_growth, inc_working, n_earn, cfg, seed, force, record, out, path_wealth, chosen, cont, ce_chosen,
            ce_cont, n_cand, extra, rec_act, rec_ce, rec_state, record_state, log, p == log_path,
        )


@jit(nogil=True)
def _adaptive_batch_serial(
    p_offset, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
    inc_working, n_earn, cfg, seed, force, record, out, path_wealth, chosen, cont, ce_chosen, ce_cont, n_cand, extra,
    rec_act, rec_ce, rec_state, record_state, log, log_path,
):
    """The same loop on the calling thread alone: for one or a few paths, where a parallel launch gains nothing.
    It never touches numba's threading layer, so it needs no kernel lock and runs beside other requests' kernels."""
    n_paths = rets.shape[0]
    for p in range(n_paths):
        _adaptive_path(
            p, p_offset + p, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base,
            inc_growth, inc_working, n_earn, cfg, seed, force, record, out, path_wealth, chosen, cont, ce_chosen,
            ce_cont, n_cand, extra, rec_act, rec_ce, rec_state, record_state, log, p == log_path,
        )


@jit
def _probe_path(
    p, p_abs, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
    inc_working, n_earn, gamma, floor, tilt, ref_seed, ref_k, cand_vals, n_cand, picked_vals, out_u,
):
    """Walk path `p` with the continuation policy (the planner's own decisions are not applied) and, in each year,
    score the candidates the planner considered (and the action it took) on `ref_k` reference futures drawn from
    a stream the planner never used. The result is an independent estimate of what each candidate was worth."""
    n_years = tv.shape[0]
    st = init.copy()
    ys = np.zeros(NY)
    act0 = np.zeros(NACT)
    act = np.zeros(NACT)
    gates1 = np.ones((n_years, NGATE))
    fut_rets = np.zeros((ref_k, n_years, 3))
    fut_wages = np.zeros((ref_k, n_years))
    fut_k = np.zeros((ref_k, n_years))
    fut_wt = np.zeros((ref_k, n_years, 2))
    fut_w = np.ones(ref_k)
    st_r = np.zeros(NSTATE)
    ys_r = np.zeros(NY)
    act_r = np.zeros(NACT)
    util = np.zeros(ref_k)
    scratch_pw = np.zeros(n_years)
    scratch_log = np.zeros((1, NLOG))
    lp0 = np.zeros(2)
    for t in range(n_years):
        _run_years(st, ys, act0, tv, hhc, row, gates1, rets[p], wages[p], k401[p], wt[p], t, t + 1, RUN_BEGIN, False, False, scratch_pw, False, scratch_log)
        lp0[0] = logperm[p, t, 0]
        lp0[1] = logperm[p, t, 1]
        _make_futures(
            _decision_stream(ref_seed, p_abs, t), t, ref_k, tv, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
            inc_working, n_earn, lp0, rets[p], wages[p], k401[p], wt[p], fut_rets, fut_wages, fut_k, fut_wt, fut_w, tilt,
        )
        for c in range(n_cand[p, t] + 1):
            act[:] = act0
            for d in range(ND):
                act[DIMS[d]] = cand_vals[p, t, c, d] if c < n_cand[p, t] else picked_vals[p, t, d]
            out_u[p, t, c] = _score(
                st, ys, act, t, ref_k, tv, hhc, row, gates1, fut_rets, fut_wages, fut_k, fut_wt, fut_w, st_r, ys_r, act_r,
                scratch_pw, scratch_log, gamma, floor, util,
            )
        _run_years(st, ys, act0, tv, hhc, row, gates1, rets[p], wages[p], k401[p], wt[p], t, t + 1, RUN_REST, False, False, scratch_pw, False, scratch_log)


@jit(parallel=True, nogil=True)
def _probe_batch(
    p_offset, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base, inc_growth,
    inc_working, n_earn, gamma, floor, tilt, ref_seed, ref_k, cand_vals, n_cand, picked_vals, out_u,
):
    for p in prange(rets.shape[0]):
        _probe_path(
            p, p_offset + p, row, tv, init, hhc, rets, wages, k401, wt, logperm, mk_means, mk_sds, mk_chol, inc_base,
            inc_growth, inc_working, n_earn, gamma, floor, tilt, ref_seed, ref_k, cand_vals, n_cand, picked_vals, out_u,
        )


# --------------------------------------------------------------------------------------------
# Python layer
# --------------------------------------------------------------------------------------------

SERIAL_PATHS = 2  # runs of this many paths or fewer use the serial kernel
DEFAULT_K = 32
DEFAULT_Z_MIN = 1.0
DEFAULT_PASSES = 2
DEFAULT_CONFIRM_K = 64
DEFAULT_CONFIRM_Z = 1.645
DEFAULT_TILT = 0.25


@dataclass(frozen=True)
class AdaptiveSettings:
    k: int = DEFAULT_K  # rollouts per candidate (rounded up to an even number: they come in antithetic pairs)
    z_min: float = DEFAULT_Z_MIN  # standard errors a candidate must beat the incumbent by
    risk_aversion: float = 3.0
    floor: float = 50_000.0
    passes: int = DEFAULT_PASSES
    force_continuation: bool = False  # skip the search and take the continuation action every year (consistency test)
    dimensions: tuple[str, ...] = DIM_NAMES  # which decisions the planner may change (the rest follow the continuation)
    confirm_k: int = DEFAULT_CONFIRM_K  # fresh futures each proposed change is re-tested on (0: no confirmation step)
    confirm_z: float = DEFAULT_CONFIRM_Z  # standard errors a change must win by on the fresh futures
    tilt: float = DEFAULT_TILT  # importance sampling: half the rollouts' equity shocks shifted down by this many SDs a year
    shadow: bool = False  # search and record, but follow the continuation policy (to study decisions on a fixed path)

    @property
    def rollouts(self) -> int:
        return self.k + (self.k % 2)

    @property
    def confirm_rollouts(self) -> int:
        return self.confirm_k + (self.confirm_k % 2)

    @property
    def dimension_mask(self) -> int:
        unknown = set(self.dimensions) - set(DIM_NAMES)
        if unknown:
            raise ValueError(f"unknown decisions {sorted(unknown)}; expected some of {DIM_NAMES}")
        return sum(1 << i for i, name in enumerate(DIM_NAMES) if name in self.dimensions)


@dataclass
class AdaptiveResult:
    wealth: np.ndarray  # (paths,) after-tax wealth at the horizon
    taxes_paid: np.ndarray
    pretax_owed: np.ndarray
    unfunded: np.ndarray
    path_wealth: np.ndarray  # (paths, years) after-tax wealth at the end of each year
    chosen: np.ndarray  # (paths, years, ND) the action taken, by `DIM_NAMES`
    continuation: np.ndarray  # (paths, years, ND) what the continuation policy would have done
    ce_chosen: np.ndarray  # (paths, years) certainty-equivalent wealth at the horizon of the action taken, from the rollouts
    ce_continuation: np.ndarray  # (paths, years) the same for the continuation action
    n_candidates: np.ndarray  # (paths, years) candidates scored
    cand_actions: np.ndarray | None  # (paths, years, MAX_CANDIDATES, ND) when recorded
    cand_ce: np.ndarray | None  # (paths, years, MAX_CANDIDATES)
    elapsed_seconds: float
    settings: AdaptiveSettings
    rollout_seed: int
    proposed: np.ndarray  # (paths, years) changes the search proposed
    kept: np.ndarray  # (paths, years) changes kept (all of them without a confirmation step)
    ce_fresh_chosen: np.ndarray  # (paths, years) CE of the final action on the fresh confirmation futures (else as `ce_chosen`)
    ce_fresh_continuation: np.ndarray  # (paths, years) the same for the continuation action
    states: np.ndarray | None = None  # (paths, years, NSTATE) the state each decision was taken in, when recorded
    log: dict[str, np.ndarray] | None = None  # the year log of path `detail_path`, if asked for


def rollout_seed(eval_seed: int) -> int:
    """The seed of the rollout random stream: a `SeedSequence` child disjoint from the ones behind the
    evaluation returns (child 0) and incomes (child 1)."""
    state = int(np.random.SeedSequence(eval_seed).spawn(3)[2].generate_state(1, dtype=np.uint64)[0])
    return state & 0x7FFF_FFFF_FFFF_FFFF  # 63 bits, so it is a plain int64 to the kernel


def _market_arrays(market: markets.Assumptions | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a = market or markets.DEFAULT_ASSUMPTIONS
    if a.pc_mode != "normal":
        raise ValueError("the adaptive planner's rollouts support normal private-credit returns only")
    return (
        np.array(a.means, dtype=np.float64),
        np.array(a.sds, dtype=np.float64),
        np.linalg.cholesky(np.array(a.correlation, dtype=np.float64)),
    )


def run_adaptive(
    inputs: SimInputs,
    policy: Policy,
    settings: AdaptiveSettings | None = None,
    record_candidates: bool = False,
    detail_path: int | None = None,
    chunk: int = 12,
    on_progress=None,
    record_states: bool = False,
) -> AdaptiveResult:
    """Run the adaptive planner on every path of `inputs`, continuing with `policy` (the best fixed strategy).

    The work is done in chunks of `chunk` paths (about half a second each on four cores), at background priority: other
    requests' simulations take the kernel lock between chunks, so a plan asked for while this runs is not stuck
    behind it. The result does not depend on the chunk size.
    """
    settings = settings or AdaptiveSettings()
    if inputs.logperm is None or inputs.inc_base is None:
        raise ValueError("these inputs carry no income model; build them with build_inputs")
    started = time.perf_counter()
    n_paths, n_years = inputs.n_paths, inputs.n_years
    row = np.ascontiguousarray(policy.row(inputs.current_age))
    cfg = np.zeros(NCFG)
    cfg[CFG_K] = settings.rollouts
    cfg[CFG_ZMIN] = settings.z_min
    cfg[CFG_GAMMA] = settings.risk_aversion
    cfg[CFG_FLOOR] = settings.floor
    cfg[CFG_PASSES] = settings.passes
    cfg[CFG_DIMS] = settings.dimension_mask
    cfg[CFG_CONFIRM_K] = settings.confirm_rollouts
    cfg[CFG_CONFIRM_Z] = settings.confirm_z
    cfg[CFG_APPLY] = 0.0 if settings.shadow else 1.0
    cfg[CFG_TILT] = settings.tilt
    means, sds, chol = _market_arrays(inputs.market)
    seed = rollout_seed(inputs.seed)

    out = np.zeros((n_paths, 4))
    path_wealth = np.zeros((n_paths, n_years))
    chosen = np.zeros((n_paths, n_years, ND))
    cont = np.zeros((n_paths, n_years, ND))
    ce_chosen = np.zeros((n_paths, n_years))
    ce_cont = np.zeros((n_paths, n_years))
    n_cand = np.zeros((n_paths, n_years), dtype=np.int64)
    extra = np.zeros((n_paths, n_years, NEXTRA))
    if record_candidates:
        rec_act = np.zeros((n_paths, n_years, MAX_CANDIDATES, ND))
        rec_ce = np.zeros((n_paths, n_years, MAX_CANDIDATES))
    else:
        rec_act = np.zeros((1, 1, 1, 1))
        rec_ce = np.zeros((1, 1, 1))
    rec_state = np.zeros((n_paths, n_years, NSTATE)) if record_states else np.zeros((1, 1, 1))
    log = np.zeros((n_years, NLOG)) if detail_path is not None else np.zeros((1, NLOG))

    for p0 in range(0, n_paths, chunk):
        p1 = min(n_paths, p0 + chunk)
        sl = slice(p0, p1)
        local_log_path = detail_path - p0 if detail_path is not None and p0 <= detail_path < p1 else -1
        part = dict(
            out=out[sl], path_wealth=path_wealth[sl], chosen=chosen[sl], cont=cont[sl], ce_chosen=ce_chosen[sl],
            ce_cont=ce_cont[sl], n_cand=n_cand[sl], extra=extra[sl],
        )
        if record_candidates:
            part["rec_act"], part["rec_ce"] = rec_act[sl], rec_ce[sl]
        else:
            part["rec_act"], part["rec_ce"] = rec_act, rec_ce
        part["rec_state"] = rec_state[sl] if record_states else rec_state
        # basic slices of C-contiguous arrays are views: the kernel writes straight into the full arrays
        args = (
            p0, row, inputs.tv, inputs.init, inputs.hhc,
            inputs.rets[sl], inputs.wages[sl], inputs.k401[sl], inputs.wage_tax[sl], inputs.logperm[sl],
            means, sds, chol, inputs.inc_base, inputs.inc_growth, inputs.inc_working, int(inputs.n_earners),
            cfg, seed, settings.force_continuation, record_candidates,
            part["out"], part["path_wealth"], part["chosen"], part["cont"], part["ce_chosen"], part["ce_cont"],
            part["n_cand"], part["extra"], part["rec_act"], part["rec_ce"], part["rec_state"], record_states, log, local_log_path,
        )
        if n_paths <= SERIAL_PATHS:
            _adaptive_batch_serial(*args)  # one path (the plan path): no parallel launch, so no lock to queue for
        else:
            with _KERNEL_LOCK.background():
                _adaptive_batch(*args)
        if on_progress is not None:
            on_progress(p1, n_paths)

    return AdaptiveResult(
        wealth=out[:, 0].copy(),
        taxes_paid=out[:, 1].copy(),
        pretax_owed=out[:, 2].copy(),
        unfunded=out[:, 3].copy(),
        path_wealth=path_wealth,
        chosen=chosen,
        continuation=cont,
        ce_chosen=ce_chosen,
        ce_continuation=ce_cont,
        n_candidates=n_cand,
        cand_actions=rec_act if record_candidates else None,
        cand_ce=rec_ce if record_candidates else None,
        elapsed_seconds=time.perf_counter() - started,
        settings=settings,
        rollout_seed=seed,
        proposed=extra[:, :, 0].astype(np.int64),
        kept=extra[:, :, 1].astype(np.int64),
        ce_fresh_chosen=extra[:, :, 2].copy(),
        ce_fresh_continuation=extra[:, :, 3].copy(),
        states=rec_state if record_states else None,
        log=None if detail_path is None else {name: log[:, i].copy() for i, name in enumerate(sorted_log_names())},
    )


def certainty_equivalent_of_utility(mean_utility: np.ndarray, risk_aversion: float) -> np.ndarray:
    """Certainty-equivalent wealth from mean CRRA utility (the inverse of the utility the rollouts average)."""
    if abs(risk_aversion - 1.0) < 1e-9:
        return np.exp(mean_utility)
    return ((1.0 - risk_aversion) * mean_utility) ** (1.0 / (1.0 - risk_aversion))


def probe_candidates(
    inputs: SimInputs,
    policy: Policy,
    result: AdaptiveResult,
    reference_k: int = 2_048,
    reference_stream: int = 1,
    chunk: int = 25,
    reference_tilt: float | None = None,
) -> np.ndarray:
    """What was each candidate the planner considered, and the action it took, really worth?

    `result` must come from a run with `record_candidates=True`. Each path is walked with the continuation policy
    (the planner's own choices are not applied, so the states are the same whatever the planner decided) and in
    every year the recorded candidates and the chosen action are re-scored on `reference_k` futures drawn from a
    stream the planner never used. Returns mean utility, shape (paths, years, MAX_CANDIDATES + 1): the candidates
    in the order recorded, and the chosen action in the slot after the last of them. Because the reference
    futures are independent of the ones the choice was made on, the differences between them are unbiased
    measures of decision quality (no winner's curse).
    """
    if result.cand_actions is None:
        raise ValueError("probe_candidates needs a result recorded with record_candidates=True")
    settings = result.settings
    row = np.ascontiguousarray(policy.row(inputs.current_age))
    means, sds, chol = _market_arrays(inputs.market)
    n_paths, n_years = inputs.n_paths, inputs.n_years
    ref_seed = (rollout_seed(inputs.seed) + 1_000_003 * int(reference_stream)) & 0x7FFF_FFFF_FFFF_FFFF
    out = np.zeros((n_paths, n_years, MAX_CANDIDATES + 1))
    for p0 in range(0, n_paths, chunk):
        p1 = min(n_paths, p0 + chunk)
        sl = slice(p0, p1)
        with _KERNEL_LOCK.background():
            _probe_batch(
                p0, row, inputs.tv, inputs.init, inputs.hhc,
                inputs.rets[sl], inputs.wages[sl], inputs.k401[sl], inputs.wage_tax[sl], inputs.logperm[sl],
                means, sds, chol, inputs.inc_base, inputs.inc_growth, inputs.inc_working, int(inputs.n_earners),
                settings.risk_aversion, settings.floor,
                settings.tilt if reference_tilt is None else reference_tilt, ref_seed, int(reference_k),
                np.ascontiguousarray(result.cand_actions[sl]), np.ascontiguousarray(result.n_candidates[sl]),
                np.ascontiguousarray(result.chosen[sl]), out[sl],
            )
    return out


def sorted_log_names() -> list[str]:
    from app.sim.simulate import LOG_COLUMNS

    return list(LOG_COLUMNS)
