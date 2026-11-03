/** The five asset classes in the mockup's series colours (the same on Overview and Compare). */
export const ASSET_COLORS: Record<string, string> = {
  us_stocks: "var(--seg1)",
  intl_stocks: "var(--seg5)",
  bonds: "var(--seg2)",
  private_credit: "var(--seg3)",
  cash: "var(--seg4)",
};
export const colorOf = (key: string): string => ASSET_COLORS[key] ?? "var(--advisor)";
