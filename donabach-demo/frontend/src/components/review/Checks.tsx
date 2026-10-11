"use client";

import { Disclosure, Icon } from "@/components/ui";
import type { CrossCheck } from "@/lib/types";
import { checkSummary } from "./fields";
import styles from "./Checks.module.css";

interface Props {
  checks: CrossCheck[];
  /** The keys of the check shown on the document right now, if any. */
  selectedKeys: string[];
  onShow: (check: CrossCheck) => void;
}

/** "What we checked": each cross-check with its result; choosing one shows the numbers it used. */
export function Checks({ checks, selectedKeys, onShow }: Props) {
  if (checks.length === 0) return null;
  const { failed, text } = checkSummary(checks);
  const picked = (check: CrossCheck) =>
    selectedKeys.length > 0 &&
    check.keys.length === selectedKeys.length &&
    check.keys.every((k) => selectedKeys.includes(k));

  return (
    <Disclosure title="What we checked" aside={text} defaultOpen={failed > 0}>
      <p className={styles.hint}>Choose a check to see the numbers it used.</p>
      <ul className={styles.list}>
        {checks.map((check) => (
          <li key={check.name}>
            <button
              type="button"
              className={styles.check}
              data-passed={check.passed}
              data-selected={picked(check)}
              onClick={() => onShow(check)}
            >
              <Icon name={check.passed ? "check" : "cross"} size={20} strokeWidth={2.6} className={styles.icon} />
              <span className={styles.name}>{check.name}</span>
              <span className={styles.result}>{check.passed ? "Passed" : "Did not pass"}</span>
              <span className={styles.detail}>{check.detail}</span>
            </button>
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
