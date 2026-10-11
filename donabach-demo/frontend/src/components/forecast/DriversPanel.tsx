import { FactorList, Panel, PanelTitle } from "@/components/ui";
import type { Factor } from "@/lib/types";
import styles from "./Forecast.module.css";

/**
 * "What drives this": the top factors the connected income model reported. Only rendered when
 * the model is connected; the placeholder process has no factors and none are shown for it.
 */
export function DriversPanel({ factors }: { factors: readonly Factor[] }) {
  return (
    <Panel>
      <PanelTitle aside="From the connected income model">What drives this</PanelTitle>
      {factors.length > 0 ? (
        <>
          <p className={styles.panelNote}>
            The inputs that moved the forecast most, with which way each pushes household income and how much it matters
            compared with the others.
          </p>
          <FactorList factors={factors} upText="Pushes income up" downText="Pushes income down" label="What drives the income forecast" />
        </>
      ) : (
        <p className={styles.panelNote}>The model did not report any factors for this forecast.</p>
      )}
    </Panel>
  );
}
