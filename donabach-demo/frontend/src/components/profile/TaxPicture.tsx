import { Disclosure, Panel, StatCard, Tag } from "@/components/ui";
import { dollars, percent } from "@/lib/format";
import type { HouseholdProfile } from "@/lib/types";
import styles from "./Profile.module.css";

/**
 * This year's tax picture. Everything here is read from what the API computed (`tax_return`,
 * `tax_lines`); amounts are exact dollars so they can be matched against the return.
 */
export function TaxPicture({ profile }: { profile: HouseholdProfile }) {
  const t = profile.tax_return;
  return (
    <>
      <div className={styles.sectionHead}>
        <h2>
          This year&apos;s tax picture {profile.tax_estimated && <Tag tone="gold">Estimated</Tag>}
        </h2>
        <p>
          {profile.tax_estimated
            ? "Estimated from your wages and balances, because no tax return was read. 2026 rules."
            : "Computed from the income on your tax return, with 2026 rules."}
        </p>
      </div>

      <div className={styles.cards}>
        <StatCard label="Adjusted gross income" value={dollars(t.agi)} note="Total income, less adjustments" />
        <StatCard
          label="Taxable income"
          value={dollars(t.taxable_income)}
          note={`After the ${dollars(t.standard_deduction)} standard deduction`}
        />
        <StatCard
          label="Federal tax"
          value={dollars(t.federal_total)}
          note={t.child_tax_credit > 0 ? `After a ${dollars(t.child_tax_credit)} child tax credit` : undefined}
        />
        <StatCard
          label="Illinois tax"
          value={dollars(t.illinois_tax)}
          note={`After ${dollars(t.il_exemptions)} of exemptions`}
        />
        <div className={styles.wide}>
          <StatCard
            label="Total income tax"
            value={dollars(t.grand_total)}
            note="Federal and Illinois together"
            tone="accent"
          />
        </div>
        <StatCard
          label="Marginal federal rate"
          value={percent(t.marginal_federal_rate)}
          note="The rate on your next dollar of income"
        />
        <StatCard
          label="Effective rate"
          value={percent(t.effective_total_rate, 1)}
          note={`Total income tax over AGI. Federal alone: ${percent(t.effective_federal_rate, 1)}`}
        />
      </div>

      <Panel className={styles.returnPanel}>
        <Disclosure title="See the full return" aside={`${profile.tax_lines.length} lines`}>
          <table className={styles.table}>
            <caption className="sr-only">This year&apos;s federal and Illinois income tax, line by line</caption>
            <tbody>
              {profile.tax_lines.map((line, i) => (
                <tr key={i} data-kind={line.kind} data-zero={line.kind === "amount" && Math.round(line.amount) === 0}>
                  <th scope="row">
                    {line.label}
                    {line.note && <span className={styles.note}>{line.note}</span>}
                  </th>
                  <td className="num">{line.kind === "rate" ? percent(line.amount) : dollars(line.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Disclosure>
      </Panel>
    </>
  );
}
