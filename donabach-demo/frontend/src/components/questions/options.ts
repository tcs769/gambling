// The choices the questions offer. These are the screen's options, not results: the answers they
// produce go to the API, which builds the household from them.

/** `null` is "None": no home purchase, no college. */
export const HOME_IN_YEARS = [null, 1, 3, 5, 8] as const;
export const HOME_DOWN_PAYMENT = [60_000, 120_000, 200_000] as const;

export const COLLEGE_IN_YEARS = [null, 5, 10, 15] as const;
export const COLLEGE_COST_A_YEAR = [25_000, 35_000, 50_000] as const;

export const RETIREMENT_AGES = [57, 60, 62, 65, 67] as const;
export const RETIREMENT_SPENDING = [90_000, 110_000, 130_000, 150_000] as const;

// Not on any document: estimated.
export const ROTH_BALANCES = [0, 30_000, 60_000] as const;
export const CASH_BALANCES = [20_000, 40_000, 80_000] as const;
export const SOCIAL_SECURITY_A_YEAR = [40_000, 50_000, 60_000] as const;
