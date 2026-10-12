"""The layout of one household's state vector, shared by the simulator and the direct-indexing book.

Indices 0..10 are balances that scale together when a fee is charged (the brokerage basis, a memo item, is skipped).
Account letters: P pre-tax, R Roth, B brokerage; asset letters: E equity, B bonds, P private credit (the brokerage bonds
also hold cash); GB is the goal bucket.
"""

from __future__ import annotations

(S_PE, S_PB, S_PP, S_RE, S_RB, S_RP, S_BE, S_BBASIS, S_BB, S_BP, S_GB) = range(11)
S_CF, S_DGAIN, S_DDIST, S_UNFUNDED, S_LOAN = 11, 12, 13, 14, 15
# Tax lots. The path's lot method and short-term switch (set from the policy at the start), the year being simulated,
# the short-term gains realized so far by sales that are not yet in a year's tax return, and the short-term part of
# the deferred gains (S_DGAIN is the whole of them). The brokerage stock is a number of units at a price that moves
# with the market (S_PRICE, 1 at the start; S_UNITS is the total), so a year's growth touches no lot. Lot i holds
# S_LOTU + i units bought at S_LOTC + i per unit: lot 0 is the opening position and lot 1 + t takes year t's purchases.
# The account's value S_BE is S_PRICE x S_UNITS and its basis S_BBASIS is the sum of cost x units over the lots.
# S_BEST remembers which live lot has the highest cost per unit (-1: not known), so a sale need not look for it. (A path with the
# direct-indexing book below keeps the year's harvest threshold there instead, or -1 when the year harvests nothing.)
S_LOTS, S_STCG, S_YEAR, S_STACC, S_DGAIN_ST, S_PRICE, S_UNITS, S_BEST = 16, 17, 18, 19, 20, 21, 22, 23
N_SCALARS = 24
MAX_LOTS = 64  # a household can be as young as 18, so the horizon is at most 62 years: lots 0 to 63
S_LOTU = N_SCALARS
S_LOTC = S_LOTU + MAX_LOTS
NSTATE = S_LOTC + MAX_LOTS
N_BALANCES = 11

# Lot methods (S_LOTS, SP_LOTS) and the order a sale takes lots in. LOTS_STOCK is not a policy's choice: it marks a path
# whose brokerage equity is the direct-indexing book below (100 stocks, each with its own lots, sold highest cost first).
LOTS_AVERAGE, LOTS_FIFO, LOTS_HIFO, LOTS_STOCK = 0.0, 1.0, 2.0, 3.0

# The direct-indexing book lives after the base state, in the state vector of a path that has one (NSTATE_DI long; a path
# without one has NSTATE). Stock i has a price (relative to its own start, 1 at the start), a total number of units, the
# highest cost per unit among its lots (an upper bound that sales leave stale), and lots by the year they were bought or
# last harvested: lot (i, tau) holds D_LOTU + i x MAX_LOTS + tau units at D_LOTC + i x MAX_LOTS + tau per unit.
N_STOCKS = 100
D_PRICE = NSTATE
D_UNITS = D_PRICE + N_STOCKS
D_MAXC = D_UNITS + N_STOCKS
D_LOTU = D_MAXC + N_STOCKS
D_LOTC = D_LOTU + N_STOCKS * MAX_LOTS
# Each stock also keeps a list of the lots it holds, by the year they were opened (ascending; a lot that has been sold out is
# taken off the list the next time a scan passes it): D_NLOTS + i is the length of stock i's list, D_LIST + i x MAX_LOTS + j
# its j-th entry. A stock holds a handful of lots at any time (harvesting moves most into the year's lot), so a scan that follows
# the list visits a few lots where the slots by year run to dozens.
D_NLOTS = D_LOTC + N_STOCKS * MAX_LOTS
D_LIST = D_NLOTS + N_STOCKS
NSTATE_DI = D_LIST + N_STOCKS * MAX_LOTS

# Selling the lots with the least gain per dollar first is done by sorting lots into DI_BUCKETS bins of gain per dollar,
# from DI_GMIN to 1 (a lot bought for nothing); a bin is 0.4 points wide, and within the bin where a sale stops the
# shares are sold pro rata.
DI_BUCKETS = 1024
DI_GMIN = -3.0
