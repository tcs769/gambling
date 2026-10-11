"use client";

import { Button, Icon } from "@/components/ui";
import { useShowcase } from "@/lib/showcase";
import styles from "./ChangeError.module.css";

/**
 * The API refused a change of strategies. The switches have already gone back to what the numbers on screen are for,
 * so this says what happened, in the API's words, and that the numbers are unchanged.
 */
export function ChangeError() {
  const { changeError, actions } = useShowcase();
  if (!changeError) return null;
  return (
    <div className={styles.error} role="alert">
      <Icon name="alert" size={20} className={styles.icon} />
      <div className={styles.text}>
        <strong>That change could not be applied.</strong> {changeError} The strategies and numbers below are as they were.
      </div>
      <Button variant="ghost" onClick={actions.dismissError}>
        Dismiss
      </Button>
    </div>
  );
}
