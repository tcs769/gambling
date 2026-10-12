"use client";

import { Disclosure, Tag } from "@/components/ui";
import type { AltStyle, StyleSlot } from "@/lib/state";
import type { PlanResponse, PlanningStyle } from "@/lib/types";
import { StylePending } from "./StylePending";
import { ChoiceChips } from "./StrategyCard";
import { StyleFigures } from "./StyleFigures";
import { STYLE_BLURB, STYLE_NAME } from "./styles";
import styles from "./StyleComparison.module.css";

/** The two choices a style is told apart by, as the plan's own chips say them: the stock share and the spending reserve. */
function reserveAndStocks(plan: PlanResponse): Record<string, string> {
  const choices = plan.strategy.choices;
  return Object.fromEntries(
    ["stock_share", "reserve"].filter((key) => key in choices).map((key) => [key, choices[key]]),
  );
}

/**
 * One planning style's plan in the side-by-side view: what the plan is (its label, its reserve and stock choices in words and
 * the whole sentence behind a fold), then what it comes to (see StyleFigures). While the plan is being searched for, or if
 * the API refused, the column says so by itself and the other columns are unaffected.
 */
export function StyleColumn({
  style,
  slot,
  isDefault,
  onRetry,
}: {
  style: PlanningStyle;
  slot: StyleSlot;
  /** The style the rest of the demo (the Comparison screen) uses. */
  isDefault: boolean;
  onRetry: (style: AltStyle) => void;
}) {
  const id = `style-${style}`;
  const name = STYLE_NAME[style];
  const plan = slot.status === "ready" ? slot.plan : undefined;
  return (
    <article
      className={styles.column}
      aria-labelledby={`${id}-name`}
      aria-busy={slot.status === "loading" || undefined}
      data-style={style}
      data-status={slot.status}
    >
      <header className={styles.head}>
        <div className={styles.nameRow}>
          <h3 id={`${id}-name`}>{name}</h3>
          {isDefault && <Tag tone="gold">Used on the Comparison screen</Tag>}
        </div>
        <p className={styles.blurb}>{STYLE_BLURB[style]}</p>
      </header>
      {slot.status !== "ready" && style !== "equity_first" && (
        <div className={styles.pending}>
          <StylePending style={style} slot={slot} onRetry={() => onRetry(style)} />
        </div>
      )}
      {plan && (
        <>
          <section className={styles.plan} aria-labelledby={`${id}-plan`}>
            <h4 id={`${id}-plan`} className={styles.planTitle}>
              The plan
            </h4>
            <p className={styles.label}>{plan.strategy.label}</p>
            <ChoiceChips
              choices={reserveAndStocks(plan)}
              label={`The reserve and stock choices in the ${name} plan`}
              compact
            />
            <Disclosure title="The plan in words" className={styles.fold} level={5}>
              <p className={styles.sentence}>{plan.strategy.sentence}</p>
            </Disclosure>
          </section>
          <StyleFigures plan={plan} id={id} />
        </>
      )}
    </article>
  );
}
