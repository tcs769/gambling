import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { percent0, percentTrim } from "@/lib/invest-format";
import styles from "./Taxes.module.css";
import t from "./invest.module.css";

type Taxes = Plan["portfolio"]["taxes"];
type Step = Taxes["bracket"]["brackets"][number];

/** The brackets up to the one above the filled one (the higher ones are not drawn), each as wide as its span. */
function shownBrackets(steps: Step[]): Step[] {
  const filled = steps.findIndex((s) => s.filled);
  return filled < 0 ? steps.slice(0, 4) : steps.slice(0, Math.min(steps.length, filled + 2));
}

/** How wide a bracket is drawn, in proportion to its span; the open-ended one is as wide as the one below it. */
function drawnWidths(steps: Step[]): number[] {
  const spans = steps.map((s) => (s.ceiling === null ? null : s.ceiling - s.floor));
  return steps.map((_, i) => spans[i] ?? spans[i - 1] ?? 1);
}

function Bracket({ bracket }: { bracket: Taxes["bracket"] }) {
  const steps = shownBrackets(bracket.brackets);
  const widths = drawnWidths(steps);
  const rate = percentTrim(bracket.marginal_rate);
  return (
    <div>
      <div className={styles.bracket} role="img" aria-label="Federal tax brackets" data-testid="bracket-bar">
        {steps.map((step, i) => (
          <div
            key={step.rate}
            className={`${styles.seg} ${step.filled ? styles.fill : ""}`}
            style={{ flexGrow: widths[i] }}
            data-filled={step.filled || undefined}
            data-rate={step.rate}
          >
            <span>{percentTrim(step.rate)}</span>
          </div>
        ))}
      </div>
      <dl className={`${t.kv} ${styles.values}`} data-testid="bracket-values">
        <div>
          <dt>Taxable income before conversion</dt>
          <dd className="num">{dollarsWhole(bracket.taxable_before)}</dd>
        </div>
        <div>
          <dt>Conversion fills the {rate} bracket to</dt>
          <dd className="num">{dollarsWhole(bracket.fills_to)}</dd>
        </div>
        <div>
          <dt>Federal marginal rate</dt>
          <dd className="num">{rate}</dd>
        </div>
        <div>
          <dt>Illinois tax on the conversion</dt>
          <dd className="num">{dollarsWhole(bracket.illinois_tax_on_conversion)}</dd>
        </div>
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
      <div className={t.twocol}>
        <section className={t.panel} aria-labelledby="tax-year">
          <div className={t.panelHead}>
            <h2 id="tax-year" className={t.sectionT}>
              Taxes this year
            </h2>
          </div>
          <dl className={t.kv} data-testid="taxes-year">
            {rows.map(([label, value]) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd className="num">{dollarsWhole(value)}</dd>
              </div>
            ))}
            <div className={t.total}>
              <dt>Estimated tax saved</dt>
              <dd className="num" data-testid="taxes-saved">
                {dollarsWhole(y.tax_saved)}
              </dd>
            </div>
          </dl>
        </section>

        <section className={t.panel} aria-labelledby="tax-bracket">
          <div className={t.panelHead}>
            <h2 id="tax-bracket" className={t.sectionT}>
              Your tax bracket
            </h2>
          </div>
          <Bracket bracket={taxes.bracket} />
        </section>
      </div>

      <section className={t.panel} aria-labelledby="tax-harvest">
        <div className={t.panelHead}>
          <h2 id="tax-harvest" className={t.sectionT}>
            Harvesting opportunities
          </h2>
          <span className={t.mutedS}>Brokerage positions below cost</span>
        </div>
        {taxes.opportunities.length === 0 ? (
          <p data-testid="no-opportunities">No positions below cost</p>
        ) : (
          <div className={t.scroll}>
            <table className={t.hold} data-testid="opportunities-table">
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
                  <th scope="col">Replace with</th>
                </tr>
              </thead>
              <tbody>
                {taxes.opportunities.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{row.name}</th>
                    <td className={`${t.right} num`}>{dollarsWhole(row.value)}</td>
                    <td className={`${t.right} num`}>{dollarsWhole(row.cost)}</td>
                    <td className={`${t.right} num`}>{dollarsWhole(row.loss)}</td>
                    <td>{row.replacement}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className={t.panel} aria-labelledby="tax-conv">
        <div className={t.panelHead}>
          <h2 id="tax-conv" className={t.sectionT}>
            Roth conversions by year
          </h2>
        </div>
        <div className={t.scroll}>
          <table className={t.hold} data-testid="conversions-table">
            <caption>Roth conversions by year</caption>
            <thead>
              <tr>
                <th scope="col">Year</th>
                <th scope="col">Age</th>
                <th scope="col" className={t.right}>
                  Convert
                </th>
                <th scope="col" className={t.right}>
                  Tax
                </th>
                <th scope="col">Fills</th>
              </tr>
            </thead>
            <tbody>
              {taxes.conversions.map((row) => (
                <tr key={row.year}>
                  <th scope="row" className="num">
                    {row.year}
                  </th>
                  <td className="num">{row.age}</td>
                  <td className={`${t.right} num`}>{dollarsWhole(row.amount)}</td>
                  <td className={`${t.right} num`}>{dollarsWhole(row.tax)}</td>
                  <td>{percent0(row.bracket_rate)} bracket</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
