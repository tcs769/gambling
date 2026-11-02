import { colorOf } from "./asset-colors";
import styles from "./MixBar.module.css";

interface Item {
  key: string;
  label: string;
  share: number;
}

interface Props {
  items: Item[];
  /** Keys of the classes that moved after a change (outlined). */
  changed?: Set<string>;
  size?: "large" | "small";
  /** The legend under the bar (large only). */
  legend?: boolean;
  label: string;
}

/** One stacked bar of the asset classes; a class with nothing in it has no segment. */
export function MixBar({ items, changed, size = "large", legend = true, label }: Props) {
  const shown = items.filter((item) => item.share >= 0.0005);
  return (
    <div>
      <div className={`${styles.bar} ${styles[size]}`} role="img" aria-label={label} data-testid="mix-bar">
        {shown.map((item) => (
          <span
            key={item.key}
            className={styles.segment}
            style={{ flexGrow: item.share, background: colorOf(item.key) }}
            data-key={item.key}
            data-changed={changed?.has(item.key) || undefined}
          />
        ))}
      </div>
      {legend && size === "large" && (
        <ul className={styles.legend}>
          {shown.map((item) => (
            <li key={item.key}>
              <span className={styles.swatch} style={{ background: colorOf(item.key) }} aria-hidden="true" />
              {item.label}
              {changed?.has(item.key) && <span className={styles.tag}>Changed</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
