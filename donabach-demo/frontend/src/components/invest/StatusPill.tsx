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

/** Text and an icon, never colour alone. */
export function StatusPill({ status }: { status: Status }) {
  return (
    <span className={`${styles.pill} ${styles[status]}`} data-status={status}>
      <svg className={styles.icon} viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        {status === "done" && <path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="currentColor" strokeWidth="2" />}
        {status === "ongoing" && (
          <path
            d="M13 8a5 5 0 1 1-1.6-3.7M13 2.5v3h-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
        )}
        {status === "scheduled" && (
          <path
            d="M8 2.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11zM8 5v3.3l2.2 1.4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
          />
        )}
        {status === "needs_ok" && (
          <path d="M8 3v6M8 11.2v1.6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
        )}
        {status === "your_step" && (
          <path d="M3 8h9M8.5 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        )}
      </svg>
      {TEXT[status]}
    </span>
  );
}
