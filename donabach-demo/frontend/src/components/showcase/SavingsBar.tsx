"use client";

import { dollars, percent } from "@/lib/format";
import type { CardAccount } from "@/lib/types";
import { useElementWidth } from "./useElementWidth";
import styles from "./SavingsBar.module.css";

/** A share label sits above its segment only when the segment is at least this wide: room for "65%" and a little air. */
const LABEL_ROOM_PX = 52;

/**
 * Where the savings are: one stacked bar (a segment per account, as wide as its share of everything saved) with a legend
 * that carries each account's dollars and share, and the taxable account's cost basis and unrealized gain called out.
 * The bar only shows the proportions; every number is also written in the legend, so the bar is hidden from screen readers.
 */
export function SavingsBar({ accounts, total }: { accounts: readonly CardAccount[]; total: number }) {
  const [measure, width] = useElementWidth<HTMLDivElement>();
  const taxable = accounts.find((a) => a.key === "taxable");
  const gain = taxable?.unrealized_gain;
  return (
    <div className={styles.wrap}>
      <div className={styles.bar} ref={measure} aria-hidden="true">
        <div className={styles.labels}>
          {accounts.map((account, i) => {
            const before = accounts.slice(0, i).reduce((sum, a) => sum + a.share, 0);
            const fits = account.share * width >= LABEL_ROOM_PX;
            return (
              fits && (
                <span
                  key={account.key}
                  className={styles.share}
                  style={{ left: `${(before + account.share / 2) * 100}%` }}
                >
                  {percent(account.share)}
                </span>
              )
            );
          })}
        </div>
        <div className={styles.segments}>
          {accounts.map((account) => (
            <span
              key={account.key}
              className={styles.segment}
              data-account={account.key}
              style={{ flexGrow: Math.max(account.share, 0), flexBasis: 0 }}
            />
          ))}
        </div>
      </div>

      <ul className={styles.legend} aria-label={`Savings by account, ${dollars(total)} in all`}>
        {accounts.map((account) => (
          <li key={account.key} className={styles.item}>
            <span className={styles.swatch} data-account={account.key} aria-hidden="true" />
            <span className={styles.name}>{account.label}</span>
            <span className={`${styles.value} num`}>{dollars(account.value)}</span>
            <span className={styles.pct}>{percent(account.share)} of savings</span>
          </li>
        ))}
      </ul>

      {taxable && typeof taxable.basis === "number" && (
        <p className={styles.callout} data-account="taxable">
          <span className={styles.calloutTitle}>{taxable.label}</span>
          <span>
            Cost basis <strong className="num">{dollars(taxable.basis)}</strong>
          </span>
          <span>
            {typeof gain === "number" && gain > 0 ? (
              <>
                Unrealized gain <strong className="num">{dollars(gain)}</strong>
              </>
            ) : (
              "No unrealized gain"
            )}
          </span>
        </p>
      )}
    </div>
  );
}
