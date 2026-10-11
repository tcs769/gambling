"use client";

import { useId } from "react";
import { ButtonLink, Icon, NumberInput, Panel } from "@/components/ui";
import styles from "./Review.module.css";

export interface MissingItem {
  key: string;
  label: string;
  kind: "money" | "integer";
  /** A parsed field with this key is in the list below, where it is filled in. */
  inList: boolean;
}

interface Props {
  items: MissingItem[];
  onSet: (key: string, value: number) => void;
}

/** ["A", "B", "C"] -> "A, B and C". */
const joinList = (items: string[]): string =>
  items.length < 2 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

/**
 * Shown when the household could not be built because numbers were missing. Values that belong
 * to a document row are fixed on that row; the rest (their document was not added) can be typed here.
 */
export function MissingValues({ items, onSet }: Props) {
  const prefix = useId();
  const typed = items.filter((item) => !item.inList);
  return (
    <Panel className={styles.banner} role="alert" aria-labelledby={`${prefix}-title`}>
      <div className={styles.bannerHead}>
        <Icon name="alert" size={22} />
        <div>
          <h2 id={`${prefix}-title`}>We could not build your profile yet</h2>
          <p>
            These numbers were not found on your documents: {joinList(items.map((item) => item.label))}.
            {typed.length > 0
              ? " Type them in below, or add the document that has them."
              : " Fill them in on their rows below."}
          </p>
        </div>
      </div>
      {typed.length > 0 && (
        <ul className={styles.missingList}>
          {typed.map((item) => (
            <li key={item.key}>
              <label>
                {item.label}
                <NumberInput
                  value={null}
                  prefixText={item.kind === "money" ? "$" : undefined}
                  integer={item.kind === "integer"}
                  min={0}
                  placeholder="Enter a value"
                  onCommit={(value) => onSet(item.key, value)}
                />
              </label>
            </li>
          ))}
        </ul>
      )}
      <div className={styles.bannerActions}>
        <ButtonLink href="/" variant="secondary">
          Add another document
        </ButtonLink>
      </div>
    </Panel>
  );
}
