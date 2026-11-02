import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { amountOrDash } from "@/lib/invest-format";
import styles from "./Retirement.module.css";
import t from "./invest.module.css";

type Retirement = Plan["portfolio"]["retirement"];

export function RetirementTab({ retirement }: { retirement: Retirement }) {
  const head = (label: string, right = true) => (
    <th scope="col" className={right ? t.right : undefined}>
      {label}
    </th>
  );
  return (
    <div>
      <section className={t.section} aria-labelledby="ret-income">
        <h2 id="ret-income" className={t.heading}>
          Where your income comes from
        </h2>
        <div
          className={`${t.tableWrap} ${styles.scroll}`}
          tabIndex={0}
          role="region"
          aria-label="Where your income comes from"
        >
          <table className={`${t.table} ${styles.table}`} data-testid="income-table">
            <caption>Where your income comes from</caption>
            <thead>
              <tr>
                {head("Age", false)}
                {head("Year", false)}
                {head("Social Security")}
                {head("401(k)/IRA")}
                {head("Brokerage")}
                {head("Roth IRA")}
                {head("Total income")}
                {head("Spending")}
                {head("Tax")}
                {head("Total used")}
              </tr>
            </thead>
            <tbody>
              {retirement.rows.map((row) => (
                <tr key={row.age}>
                  <th scope="row">{row.age}</th>
                  <td>{row.year}</td>
                  <td className={t.right}>{amountOrDash(row.social_security)}</td>
                  <td className={t.right}>{amountOrDash(row.from_pretax)}</td>
                  <td className={t.right}>{amountOrDash(row.from_taxable)}</td>
                  <td className={t.right}>{amountOrDash(row.from_roth)}</td>
                  <td className={`${t.right} ${styles.total}`}>{dollarsWhole(row.total_sources)}</td>
                  <td className={t.right}>{dollarsWhole(row.spending)}</td>
                  <td className={t.right}>{amountOrDash(row.tax)}</td>
                  <td className={`${t.right} ${styles.total}`}>{dollarsWhole(row.total_uses)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className={t.section} aria-labelledby="ret-order">
        <h2 id="ret-order" className={t.heading}>
          Withdrawal order
        </h2>
        <ol className={styles.order} data-testid="withdrawal-order">
          {retirement.withdrawal_order.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      </section>

      <section className={t.section} aria-labelledby="ret-required">
        <h2 id="ret-required" className={t.heading}>
          Required withdrawals
        </h2>
        <dl className={t.lines} data-testid="required">
          <dt>Starting age</dt>
          <dd className="num">{retirement.required.start_age}</dd>
          <dt>First required amount</dt>
          <dd className="num">{dollarsWhole(retirement.required.first_amount)}</dd>
        </dl>
        <p className={styles.note}>{retirement.required.note}</p>
      </section>
    </div>
  );
}
