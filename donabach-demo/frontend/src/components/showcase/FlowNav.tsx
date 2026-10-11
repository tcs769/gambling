import Link from "next/link";
import { ButtonLink, Icon } from "@/components/ui";
import styles from "./FlowNav.module.css";

interface Step {
  href: string;
  label: string;
}

/** The way on and the way back, at the foot of a showcase screen: a back link and the primary "next" button. */
export function FlowNav({ back, next }: { back: Step; next: Step }) {
  return (
    <div className={styles.flow}>
      <Link href={back.href} className={styles.back}>
        <Icon name="arrow" size={18} className={styles.backArrow} />
        {back.label}
      </Link>
      <ButtonLink href={next.href} arrow>
        {next.label}
      </ButtonLink>
    </div>
  );
}
