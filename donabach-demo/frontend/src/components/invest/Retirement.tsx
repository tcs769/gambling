import type { Plan } from "@/lib/portal-types";
import { amountOrDash } from "@/lib/invest-format";
import t from "./invest.module.css";
import styles from "./Retirement.module.css";

type Retirement = Plan["portfolio"]["retirement"];

export function RetirementTab({ retirement }: { retirement: Retirement }) {
  const head = (label: string, right = true) => (
    <th scope="col" className={right ? t.right : undefined}>
      {label}
    </th>
  );
  const cell = (value: number) => (
    <td className={`${t.right} num ${Math.abs(value) < 0.5 ? t.dash : ""}`}>{amountOrDash(value)}</td>
  );
  const { required } = retirement;
  // With nothing required there is no "covered": the API's note says why (no pre-tax balance left, or none before 80).
  const nothingRequired = required.first_amount < 0.5;
  return (
    <div>
      <section className={t.panel} aria-labelledby="ret-income">
        <div className={t.panelHead}>
          <h2 id="ret-income" className={t.sectionT}>
            Where your income comes from
          </h2>
          <span className={t.mutedS}>First years of retirement, in today&rsquo;s dollars</span>
        </div>
        <div className={t.scroll} tabIndex={0} role="region" aria-label="Where your income comes from">
          <table className={t.hold} data-testid="income-table">
            <caption>Where your income comes from</caption>
            <thead>
              <tr>
                {head("Age", false)}
                {head("Social Security")}
                {head("From 401(k) / IRA")}
                {head("From brokerage")}
                {head("From Roth")}
                {head("Tax")}
                {head("Spending")}
              </tr>
            </thead>
            <tbody>
              {retirement.rows.map((row) => (
                <tr key={row.age}>
                  <th scope="row" className="num">
                    {row.age}
                  </th>
                  {cell(row.social_security)}
                  {cell(row.from_pretax)}
                  {cell(row.from_taxable)}
                  {cell(row.from_roth)}
                  {cell(row.tax)}
                  {cell(row.spending)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className={t.twocol}>
        <section className={t.panel} aria-labelledby="ret-order">
          <div className={t.panelHead}>
            <h2 id="ret-order" className={t.sectionT}>
              Withdrawal order
            </h2>
          </div>
          <ol className={styles.order} data-testid="withdrawal-order">
            {retirement.withdrawal_order.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </section>

        <section className={t.panel} aria-labelledby="ret-required">
          <div className={t.panelHead}>
            <h2 id="ret-required" className={t.sectionT}>
              Required withdrawals
            </h2>
          </div>
          <dl className={t.kv} data-testid="required">
            <div>
              <dt>Start at age</dt>
              <dd className="num">{required.start_age}</dd>
            </div>
            <div>
              <dt>First required amount</dt>
              <dd className="num">{amountOrDash(required.first_amount)}</dd>
            </div>
            <div>
              <dt>Already covered by planned withdrawals</dt>
              <dd data-testid="required-covered">
                {nothingRequired ? required.note : required.covered ? "Yes" : "No"}
              </dd>
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
