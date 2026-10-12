"use client";

import { useId, useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import styles from "./Disclosure.module.css";

interface Props {
  title: ReactNode;
  /** Right-aligned summary in the header, e.g. "4 checks, all passed". */
  aside?: ReactNode;
  defaultOpen?: boolean;
  /** Pass `open` (with `onOpenChange`) to control it from outside. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
  className?: string;
  /** The heading level the button sits in (3 unless it is inside a section of its own that has a heading of level 4). */
  level?: 3 | 4 | 5;
}

/** A collapsible section: a real button with aria-expanded, and content that animates open. */
export function Disclosure({
  title,
  aside,
  defaultOpen = false,
  open,
  onOpenChange,
  children,
  className = "",
  level = 3,
}: Props) {
  const Heading = `h${level}` as const;
  const regionId = useId();
  const [innerOpen, setInnerOpen] = useState(defaultOpen);
  const isOpen = open ?? innerOpen;

  const toggle = () => {
    const next = !isOpen;
    if (open === undefined) setInnerOpen(next);
    onOpenChange?.(next);
  };

  return (
    <div className={`${styles.root} ${className}`} data-open={isOpen}>
      <Heading className={styles.heading}>
        <button
          type="button"
          className={styles.trigger}
          aria-expanded={isOpen}
          aria-controls={regionId}
          onClick={toggle}
        >
          <Icon name="chevron" size={18} className={styles.chevron} />
          <span className={styles.title}>{title}</span>
          {aside && <span className={styles.aside}>{aside}</span>}
        </button>
      </Heading>
      <div id={regionId} className={styles.region}>
        <div className={styles.inner}>{children}</div>
      </div>
    </div>
  );
}
