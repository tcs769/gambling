import { Icon, Pill } from "@/components/ui";
import type { RankedRow } from "@/lib/types";
import styles from "./RankedStrategy.module.css";

/** A strategy's name with its flags: the one chosen, the one the model picked, and ties. */
export function RankedStrategyCell({ row }: { row: RankedRow }) {
  const tied = row.tied_with !== null && row.tied_with !== undefined;
  return (
    <div className={styles.cell}>
      <span>{row.label}</span>
      {(row.is_chosen || row.is_model_pick || tied) && (
        <span className={styles.flags}>
          {row.is_chosen && (
            <Pill tone="good" icon={<Icon name="check" size={14} strokeWidth={2.8} />}>
              Chosen
            </Pill>
          )}
          {row.is_model_pick && (
            <Pill tone="gold" icon={<Icon name="plug" size={14} />}>
              Model&apos;s pick
            </Pill>
          )}
          {tied && <span className={styles.tied}>Same result as #{row.tied_with}</span>}
        </span>
      )}
    </div>
  );
}
