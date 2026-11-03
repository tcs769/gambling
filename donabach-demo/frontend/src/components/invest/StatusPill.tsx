import type { Plan } from "@/lib/portal-types";
import styles from "./StatusPill.module.css";

type Status = Plan["portfolio"]["overview"]["moves"][number]["status"];

const TEXT: Record<Status, string> = {
  done: "Done",
  ongoing: "Ongoing",
  scheduled: "Scheduled",
  needs_ok: "Needs your OK",
  your_step: "Your step",
};

/** The mockup's status pill: the words carry the meaning, the colour is a second cue. */
export function StatusPill({ status }: { status: Status }) {
  return (
    <span className={`${styles.st} ${styles[status]}`} data-status={status}>
      {TEXT[status]}
    </span>
  );
}
