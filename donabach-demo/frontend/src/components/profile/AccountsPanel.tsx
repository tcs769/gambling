import { Panel, PanelTitle, Tag } from "@/components/ui";
import { dollars } from "@/lib/format";
import type { HouseholdProfile } from "@/lib/types";
import styles from "./Profile.module.css";

/** Balances by account, with a total. Amounts are exact so they match the documents. */
export function AccountsPanel({ profile }: { profile: HouseholdProfile }) {
  return (
    <Panel as="section" aria-label="Balances by account">
      <PanelTitle>Balances by account</PanelTitle>
      <ul className={styles.list}>
        {profile.accounts.map((account) => (
          <li key={account.label} className={styles.item}>
            <span className={styles.name}>
              {account.label}
              {account.estimated && <Tag tone="gold">Estimated</Tag>}
            </span>
            <span className={`${styles.amount} num`}>{dollars(account.amount)}</span>
            {/* The API says just "Estimated" for estimated lines; the tag already does. */}
            {account.detail && account.detail !== "Estimated" && (
              <span className={styles.detail}>{account.detail}</span>
            )}
          </li>
        ))}
      </ul>
      <div className={styles.total}>
        <span>Total</span>
        <span className={`${styles.amount} num`}>{dollars(profile.total_assets)}</span>
      </div>
      {profile.accounts.some((account) => account.estimated) && (
        <p className={styles.totalNote}>Includes estimated balances</p>
      )}
    </Panel>
  );
}
