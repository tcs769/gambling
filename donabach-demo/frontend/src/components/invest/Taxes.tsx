import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { percent0, percentTrim } from "@/lib/invest-format";
import styles from "./Taxes.module.css";
import t from "./invest.module.css";

type Taxes = Plan["portfolio"]["taxes"];
type Step = Taxes["bracket"]["brackets"][number];

/** How wide a bracket is drawn: the square root of its span, so the small ones stay readable; the open-ended one is as wide as the one below it. */
function drawnWidths(steps: Step[]): number[] {
  const spans = steps.map((s) => (s.ceiling === null ? null : s.ceiling - s.floor));
  return steps.map((_, i) => {
    const span = spans[i] ?? spans[i - 1] ?? 1;
    return Math.sqrt(span);
  });
}

function Bracket({ bracket }: { bracket: Taxes["bracket"] }) {
  const widths = drawnWidths(bracket.brackets);
  return (
    <div>
      <div className={styles.bar} role="img" aria-label="Federal tax brackets" data-testid="bracket-bar">
        {bracket.brackets.map((step, i) => (
          <div
            key={step.rate}
            className={styles.step}
            style={{ flexGrow: widths[i] }}
            data-filled={step.filled || undefined}
            data-rate={step.rate}
          >
            <span className={styles.rate}>{percentTrim(step.rate)}</span>
            <span className={`${styles.floor} num`}>
              {dollarsWhole(step.floor)}
              {step.ceiling === null ? " and up" : ""}
            </span>
          </div>
        ))}
      </div>
      <dl className={`${t.lines} ${styles.values}`} data-testid="bracket-values">
        <dt>Taxable income before the conversion</dt>
        <dd className="num">{dollarsWhole(bracket.taxable_before)}</dd>
        <dt>The conversion</dt>
        <dd className="num">{dollarsWhole(bracket.conversion)}</dd>
        <dt>Fills to</dt>
        <dd className="num">{dollarsWhole(bracket.fills_to)}</dd>
        <dt>Marginal rate</dt>
        <dd className="num">{percentTrim(bracket.marginal_rate)}</dd>
        <dt>Illinois tax on the conversion</dt>
        <dd className="num">{dollarsWhole(bracket.illinois_tax_on_conversion)}</dd>
      </dl>
    </div>
  );
}

export function TaxesTab({ taxes }: { taxes: Taxes }) {
  const y = taxes.this_year;
  const rows: [string, number][] = [
    ["Roth conversion", y.roth_conversion],
    ["Tax on the conversion", y.conversion_tax],
    ["Losses harvested", y.losses_harvested],
    ["Gains offset", y.gains_offset],
    ["Deducted from income", y.deducted_from_income],
  ];
  if (y.carried_forward > 0) rows.push(["Carried forward", y.carried_forward]);
  rows.push(["Interest kept out of taxable accounts", y.interest_kept_out]);

  return (
    <div>
      <section className={t.section} aria-labelledby="tax-year">
        <h2 id="tax-year" className={t.heading}>
          Taxes this year
        </h2>
        <dl className={`${t.lines} ${styles.year}`} data-testid="taxes-year">
          {rows.map(([label, value]) => (
            <div key={label} className={styles.pair}>
              <dt>{label}</dt>
              <dd className="num">{dollarsWhole(value)}</dd>
            </div>
          ))}
          <div className={`${styles.pair} ${styles.total}`}>
            <dt>Estimated tax saved</dt>
            <dd className="num" data-testid="taxes-saved">
              {dollarsWhole(y.tax_saved)}
            </dd>
          </div>
        </dl>
      </section>

      <section className={t.section} aria-labelledby="tax-bracket">
        <h2 id="tax-bracket" className={t.heading}>
          Your tax bracket
        </h2>
        <Bracket bracket={taxes.bracket} />
      </section>

      <section className={t.section} aria-labelledby="tax-harvest">
        <h2 id="tax-harvest" className={t.heading}>
          Harvesting opportunities
        </h2>
        {taxes.opportunities.length === 0 ? (
          <p className={t.quiet} data-testid="no-opportunities">
            No positions below cost
          </p>
        ) : (
          <div className={t.tableWrap}>
            <table className={t.table} data-testid="opportunities-table">
              <caption>Harvesting opportunities</caption>
              <thead>
                <tr>
                  <th scope="col">Position</th>
                  <th scope="col" className={t.right}>
                    Value
                  </th>
                  <th scope="col" className={t.right}>
                    Cost
                  </th>
                  <th scope="col" className={t.right}>
                    Loss
                  </th>
                  <th scope="col">Replaced with</th>
                </tr>
              </thead>
              <tbody>
                {taxes.opportunities.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{row.name}</th>
                    <td className={t.right}>{dollarsWhole(row.value)}</td>
                    <td className={t.right}>{dollarsWhole(row.cost)}</td>
                    <td className={t.right}>{dollarsWhole(row.loss)}</td>
                    <td>{row.replacement}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={t.section} aria-labelledby="tax-conv">
        <h2 id="tax-conv" className={t.heading}>
          Roth conversions by year
        </h2>
        <div className={t.tableWrap}>
          <table className={t.table} data-testid="conversions-table">
            <caption>Roth conversions by year</caption>
            <thead>
              <tr>
                <th scope="col">Year</th>
                <th scope="col">Age</th>
                <th scope="col" className={t.right}>
                  Amount
                </th>
                <th scope="col" className={t.right}>
                  Tax
                </th>
                <th scope="col" className={t.right}>
                  Bracket
                </th>
              </tr>
            </thead>
            <tbody>
              {taxes.conversions.map((row) => (
                <tr key={row.year}>
                  <th scope="row">{row.year}</th>
                  <td>{row.age}</td>
                  <td className={t.right}>{dollarsWhole(row.amount)}</td>
                  <td className={t.right}>{dollarsWhole(row.tax)}</td>
                  <td className={t.right}>{percent0(row.bracket_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
