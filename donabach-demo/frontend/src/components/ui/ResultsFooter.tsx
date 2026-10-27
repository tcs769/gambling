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
        {note ? "Not investment or tax advice." : "Prototype for illustration only, not investment or tax advice."} Tax
        rules from IRS Rev. Proc. 2025-32 and Illinois 2026 guidance, simplified (income tax only, standard deduction).
        Market returns simulated and illustrative.
      </p>
      <p>
        Simplifications: income tax only (no payroll taxes), the standard deduction (itemizing only for charitable
        gifts), no AMT, no state tax credits. All amounts are in 2026 dollars.
      </p>
      <p>
        After the first of two spouses dies the household files as a single taxpayer, with spending and Social Security
        reduced; a household with one person on file is taxed as married filing jointly. Taxes paid by heirs are an
        assumption (a flat rate on pre-tax accounts, shown as a separate valuation), not a simulation.
      </p>
    </footer>
  );
}
