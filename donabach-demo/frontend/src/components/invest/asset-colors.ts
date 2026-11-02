/** The five asset classes in a restrained navy / blue / brown palette (the same on Overview and Compare). */
export const ASSET_COLORS: Record<string, string> = {
  us_stocks: "#1f3a5f",
  intl_stocks: "#5b84b1",
  bonds: "#a9b8c9",
  private_credit: "#b8946a",
  cash: "#6b4a2e",
};
export const colorOf = (key: string): string => ASSET_COLORS[key] ?? "#8592a3";
