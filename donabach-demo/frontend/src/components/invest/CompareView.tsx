import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { feeLine, moreAtHorizon, signedPercent2, wealth } from "@/lib/invest-format";
import { MixBar } from "./MixBar";
import styles from "./CompareView.module.css";

type Card = Plan["comparison"]["advisor"];

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function CompareCard({ card, side, horizon }: { card: Card; side: "advisor" | "waramoug"; horizon: number }) {
  const harvested = card.harvested_so_far !== null && card.harvested_so_far !== undefined ? card.harvested_so_far : 0;
  return (
    <article
      className={`${styles.side} ${side === "waramoug" ? styles.can : ""}`}
      data-side={side}
      data-testid={`card-${side}`}
      aria-labelledby={`card-${side}-title`}
    >
      <h2 className={styles.sidehead} id={`card-${side}-title`}>
        {card.title}
      </h2>
      <div className={styles.sidebig}>
        <span>Projected at {horizon}</span>
        <b className="num" data-testid={`wealth-${side}`}>
          {wealth(card.wealth_80)}
        </b>
      </div>
      <div className={styles.sidebar} aria-hidden="true">
        <i data-side={side} style={{ width: `${card.bar * 100}%` }} />
      </div>
      <dl className={styles.sidelist}>
        <Row label="Mix">
          <MixBar items={card.mix} size="small" label={`${card.title} mix`} legend={false} />
          <span data-testid={`mix-${side}`}>{card.mix_text}</span>
        </Row>
        <Row label="Accounts">
          {card.accounts.map((line) => (
            <span key={line} className={styles.line}>
              {line}
            </span>
          ))}
        </Row>
        <Row label="Harvesting losses">
          {card.harvesting}
          {harvested > 0.5 && <span className="num">: {dollarsWhole(harvested)} so far</span>}
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
      <section className={styles.gap} aria-label="With Waramoug" data-testid="compare-strip">
        <span className={styles.gapk}>With Waramoug</span>
        <b className="num" data-testid="dollars-more">
          {moreAtHorizon(comparison.dollars_more, horizon)}
        </b>
        <span className={styles.gapsep} aria-hidden="true" />
        <b className="num" data-testid="rate-per-year">
          {signedPercent2(comparison.rate_per_year)} a year
        </b>
      </section>
      <div className={styles.duo}>
        <CompareCard card={comparison.advisor} side="advisor" horizon={horizon} />
        <CompareCard card={comparison.waramoug} side="waramoug" horizon={horizon} />
      </div>
    </div>
  );
}
