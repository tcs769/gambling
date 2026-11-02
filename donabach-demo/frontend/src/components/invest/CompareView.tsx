import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { feeLine, moreAtHorizon, percent0, signedPercent2, wealth } from "@/lib/invest-format";
import { MixBar } from "./MixBar";
import styles from "./CompareView.module.css";

type Card = Plan["comparison"]["advisor"];

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <dt className={styles.rowLabel}>{label}</dt>
      <dd className={styles.rowValue}>{children}</dd>
    </div>
  );
}

function CompareCard({ card, side, horizon }: { card: Card; side: "advisor" | "waramoug"; horizon: number }) {
  const shown = card.mix.filter((m) => Math.round(m.share * 100) > 0);
  return (
    <article
      className={styles.card}
      data-side={side}
      data-testid={`card-${side}`}
      aria-labelledby={`card-${side}-title`}
    >
      <h2 className={styles.cardHead} id={`card-${side}-title`}>
        {card.title}
      </h2>
      <dl className={styles.rows}>
        <Row label={`Projected wealth at ${horizon}`}>
          <span className={`${styles.wealth} num`} data-testid={`wealth-${side}`}>
            {wealth(card.wealth_80)}
          </span>
          <span className={styles.barTrack} aria-hidden="true">
            <span className={styles.barFill} data-side={side} style={{ width: `${card.bar * 100}%` }} />
          </span>
        </Row>
        <Row label="Mix">
          <MixBar items={card.mix} size="small" label={`${card.title} mix`} legend={false} />
          <span className={styles.mixText} data-testid={`mix-${side}`}>
            {shown.map((m) => `${m.label} ${percent0(m.share)}`).join(" · ")}
          </span>
        </Row>
        <Row label="Accounts">
          <ul className={styles.accounts}>
            {card.accounts.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </Row>
        <Row label="Harvesting losses">
          {card.harvesting}
          {card.harvested_so_far !== null && card.harvested_so_far !== undefined && card.harvested_so_far > 0 && (
            <span className={`${styles.extra} num`}>this year {dollarsWhole(card.harvested_so_far)}</span>
          )}
        </Row>
        <Row label="Roth conversion this year">
          <span className="num">{card.roth_conversion > 0.5 ? dollarsWhole(card.roth_conversion) : "None"}</span>
        </Row>
        <Row label="Yearly fee">
          <span className="num" data-testid={`fee-${side}`}>
            {feeLine(card.fee_dollars, card.fee_rate, side === "advisor" ? "two" : "trim")}
          </span>
        </Row>
      </dl>
    </article>
  );
}

export function CompareView({ plan }: { plan: Plan }) {
  const { comparison, portfolio } = plan;
  const horizon = portfolio.summary.horizon_age;
  return (
    <div data-plan-id={plan.plan_id}>
      <section className={styles.strip} aria-label="With Waramoug" data-testid="compare-strip">
        <p className={styles.stripLead}>With Waramoug</p>
        <p className={`${styles.stripBig} num`} data-testid="dollars-more">
          {moreAtHorizon(comparison.dollars_more, horizon)}
        </p>
        <p className={`${styles.stripRate} num`} data-testid="rate-per-year">
          {signedPercent2(comparison.rate_per_year)} a year
        </p>
      </section>
      <div className={styles.cards}>
        <CompareCard card={comparison.advisor} side="advisor" horizon={horizon} />
        <CompareCard card={comparison.waramoug} side="waramoug" horizon={horizon} />
      </div>
    </div>
  );
}
