import styles from "./ResultsFooter.module.css";

/**
 * The disclaimer every results screen carries. A screen can put one line of its own ahead of it (`note`: the showcase's
 * "Results for this household…", which the API words and this writes as it is).
 */
export function ResultsFooter({ note }: { note?: string }) {
  return (
    <footer className={styles.footer}>
      {note && <p className={styles.note}>{note}</p>}
      <p>
        Prototype for illustration only, not investment or tax advice. Tax rules from IRS Rev. Proc. 2025-32 and
        Illinois 2026 guidance, simplified (income tax only, standard deduction). Market returns simulated and
        illustrative.
      </p>
      <p>
        Simplifications: income tax only (no payroll taxes), the standard deduction (itemizing only for charitable
        gifts), no AMT, no state tax credits. All amounts are in 2026 dollars.
      </p>
      <p>
        Not modeled: the years after the first spouse dies (a surviving spouse files as a single taxpayer, with narrower
        brackets) and taxes paid by heirs on inherited accounts. Both generally favor Roth conversions, so this tool, if
        anything, understates their value.
      </p>
    </footer>
  );
}
