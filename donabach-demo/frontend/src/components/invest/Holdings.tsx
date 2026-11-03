"use client";

import { useState } from "react";
import type { Plan } from "@/lib/portal-types";
import { dollarsWhole } from "@/lib/portal-format";
import { percent0, percentTrim } from "@/lib/invest-format";
import { TabList, TabPanel } from "./Tabs";
import styles from "./Holdings.module.css";
import t from "./invest.module.css";

type Holdings = Plan["portfolio"]["holdings"];
type Account = Holdings["accounts"][number];
type Row = Account["holdings"][number];
type Bars = Holdings["sectors"];

/** The account names the way the mockup writes them. */
const ACCOUNT_LABEL: Record<string, string> = { pretax: "401(k) and IRA" };
const accountLabel = (a: Account) => ACCOUNT_LABEL[a.key] ?? a.label;

function gainOrYield(row: Row): string {
  if (row.gain !== null && row.gain !== undefined) return dollarsWhole(row.gain);
  if (row.yield_rate !== null && row.yield_rate !== undefined) return percentTrim(row.yield_rate);
  return "–";
}

function positionsText(row: Row): string {
  return row.positions > 0 ? row.positions.toLocaleString("en-US") : "–";
}

function BarList({ rows, label }: { rows: Bars; label: string }) {
  // The longest bar is the largest share (a layout scale only: the figures shown are the API's).
  const widest = Math.max(0.0001, ...rows.map((r) => r.share));
  return (
    <ul className={styles.bars} aria-label={label} data-testid={`bars-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      {rows.map((row) => (
        <li key={row.label}>
          <span>{row.label}</span>
          <span className={styles.track} aria-hidden="true">
            <i style={{ width: `${(row.share / widest) * 100}%` }} />
          </span>
          <span className={`${styles.share} num`}>{percent0(row.share)}</span>
        </li>
      ))}
    </ul>
  );
}

function AccountPanel({ account }: { account: Account }) {
  const hasGain = account.cost_basis !== null && account.cost_basis !== undefined;
  return (
    <div data-testid={`account-${account.key}`}>
      <div className={styles.acctmeta} data-testid="account-meta">
        <span>
          <b className="num" data-testid="account-balance">
            {dollarsWhole(account.balance)}
          </b>{" "}
          balance
        </span>
        {hasGain && (
          <span>
            <b className="num">{dollarsWhole(account.cost_basis ?? 0)}</b> cost basis
          </span>
        )}
        {account.unrealized_gain !== null && account.unrealized_gain !== undefined && (
          <span>
            <b className="num">{dollarsWhole(account.unrealized_gain)}</b> unrealized gain
          </span>
        )}
        <span>{account.taxation}</span>
      </div>
      <div className={t.scroll}>
        <table className={t.hold} data-testid="holdings-table">
          <caption>{accountLabel(account)} holdings</caption>
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
                {hasGain ? "Gain" : "Yield"}
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
                <td className={`${t.right} num`}>{positionsText(row)}</td>
                <td className={`${t.right} num`}>{dollarsWhole(row.value)}</td>
                <td className={`${t.right} num`}>{gainOrYield(row)}</td>
                <td className={`${t.right} num`}>{percent0(row.share)}</td>
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
  const brokerage = holdings.accounts.find((a) => a.key === "brokerage");
  const illustrative = holdings.illustrative ? <span className={t.tagQuiet}>Illustrative</span> : null;
  const largest = holdings.largest_stocks ?? [];
  return (
    <div>
      <section className={t.panel} aria-labelledby="hold-accounts">
        <div className={t.panelHead}>
          <h2 id="hold-accounts" className={t.sectionT}>
            Holdings by account
          </h2>
          <TabList
            label="Accounts"
            idPrefix="acct"
            variant="pill"
            tabs={holdings.accounts.map((a) => ({ key: a.key, label: accountLabel(a) }))}
            value={account.key}
            onChange={setKey}
          />
        </div>
        <TabPanel idPrefix="acct" value={account.key}>
          <AccountPanel account={account} />
        </TabPanel>
      </section>

      <div className={t.twocol}>
        {largest.length > 0 ? (
          <section className={t.panel} aria-labelledby="hold-largest">
            <div className={t.panelHead}>
              <h2 id="hold-largest" className={t.sectionT}>
                Largest individual stocks
                {illustrative}
              </h2>
              {brokerage && (
                <span className={t.mutedS}>
                  Brokerage, {Math.max(0, ...brokerage.holdings.map((r) => r.positions)).toLocaleString("en-US")} held
                </span>
              )}
            </div>
            <div className={t.scroll}>
              <table className={t.hold} data-testid="largest-stocks">
                <caption>Largest individual stocks</caption>
                <thead>
                  <tr>
                    <th scope="col">Company</th>
                    <th scope="col" className={t.right}>
                      Value
                    </th>
                    <th scope="col" className={t.right}>
                      Gain
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {largest.map((row) => (
                    <tr key={row.name}>
                      <th scope="row">{row.name}</th>
                      <td className={`${t.right} num`}>{dollarsWhole(row.value)}</td>
                      <td className={`${t.right} num`}>{dollarsWhole(row.gain)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        ) : (
          <div />
        )}
        <section className={t.panel} aria-labelledby="hold-sectors">
          <div className={t.panelHead}>
            <h2 id="hold-sectors" className={t.sectionT}>
              Stocks by sector
              {illustrative}
            </h2>
          </div>
          <BarList rows={holdings.sectors} label="Stocks by sector" />
          <div className={`${t.panelHead} ${styles.second}`}>
            <h2 id="hold-regions" className={t.sectionT}>
              Stocks by region
              {illustrative}
            </h2>
          </div>
          <BarList rows={holdings.regions} label="Stocks by region" />
        </section>
      </div>
    </div>
  );
}
