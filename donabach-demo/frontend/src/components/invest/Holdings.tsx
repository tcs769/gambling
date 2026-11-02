"use client";

import { useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { percent0, percentTrim } from "@/lib/invest-format";
import { Tabs } from "./Tabs";
import styles from "./Holdings.module.css";
import t from "./invest.module.css";

type Holdings = Plan["portfolio"]["holdings"];
type Account = Holdings["accounts"][number];
type Bars = Holdings["sectors"];

function gainOrYield(row: Account["holdings"][number]): string {
  if (row.gain !== null && row.gain !== undefined) return dollarsWhole(row.gain);
  if (row.yield_rate !== null && row.yield_rate !== undefined) return `${percentTrim(row.yield_rate)} yield`;
  return "—";
}

function positionsText(row: Account["holdings"][number]): string {
  return row.positions === 1 ? "1" : row.positions.toLocaleString("en-US");
}

function BarList({ rows, label }: { rows: Bars; label: string }) {
  // The longest bar is the largest share (a layout scale only: the figures shown are the API's).
  const widest = Math.max(0.0001, ...rows.map((r) => r.share));
  return (
    <ul className={styles.bars} aria-label={label} data-testid={`bars-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      {rows.map((row) => (
        <li key={row.label} className={styles.barRow}>
          <span className={styles.barLabel}>{row.label}</span>
          <span className={styles.track} aria-hidden="true">
            <span className={styles.fill} style={{ width: `${(row.share / widest) * 100}%` }} />
          </span>
          <span className={`${styles.barShare} num`}>{percentTrim(row.share)}</span>
          <span className={`${styles.barAmount} num`}>{dollarsWhole(row.amount)}</span>
        </li>
      ))}
    </ul>
  );
}

function AccountPanel({ account }: { account: Account }) {
  return (
    <div data-testid={`account-${account.key}`}>
      <dl className={t.lines}>
        <dt>Balance</dt>
        <dd className="num" data-testid="account-balance">
          {dollarsWhole(account.balance)}
        </dd>
        <dt>Taxed</dt>
        <dd>{account.taxation}</dd>
        {account.cost_basis !== null && account.cost_basis !== undefined && (
          <>
            <dt>Cost basis</dt>
            <dd className="num">{dollarsWhole(account.cost_basis)}</dd>
          </>
        )}
        {account.unrealized_gain !== null && account.unrealized_gain !== undefined && (
          <>
            <dt>Unrealized gain</dt>
            <dd className="num">{dollarsWhole(account.unrealized_gain)}</dd>
          </>
        )}
      </dl>
      <div className={`${t.tableWrap} ${styles.tableGap}`}>
        <table className={t.table} data-testid="holdings-table">
          <caption>{account.label} holdings</caption>
          <thead>
            <tr>
              <th scope="col">Holding</th>
              <th scope="col" className={t.right}>
                Positions
              </th>
              <th scope="col" className={t.right}>
                Value
              </th>
              <th scope="col" className={t.right}>
                Gain or yield
              </th>
              <th scope="col" className={t.right}>
                Share
              </th>
            </tr>
          </thead>
          <tbody>
            {account.holdings.map((row) => (
              <tr key={row.name}>
                <th scope="row">{row.name}</th>
                <td className={t.right}>{positionsText(row)}</td>
                <td className={t.right}>{dollarsWhole(row.value)}</td>
                <td className={t.right}>{gainOrYield(row)}</td>
                <td className={t.right}>{percent0(row.share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function HoldingsTab({ holdings }: { holdings: Holdings }) {
  const [key, setKey] = useState<string>(holdings.accounts[0]?.key ?? "brokerage");
  const account = holdings.accounts.find((a) => a.key === key) ?? holdings.accounts[0];
  return (
    <div>
      <Tabs
        label="Accounts"
        idPrefix="acct"
        variant="pill"
        tabs={holdings.accounts.map((a) => ({ key: a.key, label: a.label }))}
        value={account.key}
        onChange={setKey}
      >
        <AccountPanel account={account} />
      </Tabs>

      {holdings.largest_stocks && holdings.largest_stocks.length > 0 && (
        <section className={t.section} aria-labelledby="hold-largest">
          <h2 id="hold-largest" className={t.heading}>
            Largest individual stocks
            {holdings.illustrative && <span className={t.tagQuiet}>Illustrative</span>}
          </h2>
          <div className={t.tableWrap}>
            <table className={t.table} data-testid="largest-stocks">
              <caption>Largest individual stocks</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col" className={t.right}>
                    Value
                  </th>
                  <th scope="col" className={t.right}>
                    Gain
                  </th>
                </tr>
              </thead>
              <tbody>
                {holdings.largest_stocks.map((row) => (
                  <tr key={row.name}>
                    <th scope="row">{row.name}</th>
                    <td className={t.right}>{dollarsWhole(row.value)}</td>
                    <td className={t.right}>{dollarsWhole(row.gain)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className={t.section} aria-labelledby="hold-sectors">
        <h2 id="hold-sectors" className={t.heading}>
          Stocks by sector
          {holdings.illustrative && <span className={t.tagQuiet}>Illustrative</span>}
        </h2>
        <BarList rows={holdings.sectors} label="Stocks by sector" />
      </section>

      <section className={t.section} aria-labelledby="hold-regions">
        <h2 id="hold-regions" className={t.heading}>
          Stocks by region
          {holdings.illustrative && <span className={t.tagQuiet}>Illustrative</span>}
        </h2>
        <BarList rows={holdings.regions} label="Stocks by region" />
      </section>
    </div>
  );
}
