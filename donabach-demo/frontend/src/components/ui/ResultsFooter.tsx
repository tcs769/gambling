import styles from "./ResultsFooter.module.css";

/** The disclaimer every results screen carries. */
export function ResultsFooter() {
  return (
    <footer className={styles.footer}>
      <p>
        Prototype for illustration only, not investment or tax advice. Tax rules from IRS Rev. Proc. 2025-32 and
        Illinois 2026 guidance, simplified (income tax only, standard deduction). Market returns simulated and
        illustrative.
      </p>
      <p>
        Simplifications: income tax only (no payroll taxes), standard deduction only (no itemizing), no AMT, no state
        tax credits. All amounts are in 2026 dollars.
      </p>
      <p>
        Not modeled: the years after the first spouse dies (a surviving spouse files as a single taxpayer, with
        narrower brackets) and taxes paid by heirs on inherited accounts. Both generally favor Roth conversions, so
        this tool, if anything, understates their value.
      </p>
    </footer>
  );
}
