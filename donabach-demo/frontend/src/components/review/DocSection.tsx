"use client";

import { useId } from "react";
import { ConfidenceBadge, Icon, Panel } from "@/components/ui";
import { KIND_LABEL, UNRECOGNISED_NOTE } from "@/components/upload/docKinds";
import type { CrossCheck, ParsedField } from "@/lib/types";
import { Checks } from "./Checks";
import { FieldRow } from "./FieldRow";
import { fieldStatus, groupFields, type Overrides } from "./fieldLogic";
import type { ReadyDoc } from "./useDocuments";
import fields from "./Fields.module.css";
import styles from "./Review.module.css";

interface Props {
  doc: ReadyDoc;
  overrides: Overrides;
  acknowledged: string[];
  /** Keys shown on the document right now (empty when the selection is in another document). */
  selectedKeys: string[];
  /** Keys whose editor the user opened on purpose. */
  editing: string[];
  onSelect: (doc: ReadyDoc, field: ParsedField) => void;
  onShowCheck: (doc: ReadyDoc, check: CrossCheck) => void;
  onEdit: (key: string) => void;
  onCancelEdit: (key: string) => void;
  onSave: (field: ParsedField, value: number | string) => void;
  onKeep: (field: ParsedField) => void;
}

/** One document: its title, its numbers by group, and what we checked. */
export function DocSection({
  doc,
  overrides,
  acknowledged,
  selectedKeys,
  editing,
  onSelect,
  onShowCheck,
  onEdit,
  onCancelEdit,
  onSave,
  onKeep,
}: Props) {
  const titleId = useId();
  const { parsed } = doc;
  const statuses = new Map(parsed.fields.map((f) => [f.key, fieldStatus(f, overrides, acknowledged)]));
  const waiting = parsed.fields.filter((f) => statuses.get(f.key)?.needsLook && !statuses.get(f.key)?.resolved).length;
  const read = parsed.fields.filter((f) => f.value !== null).length;
  const recognised = parsed.doc_kind !== "unknown";
  const failedChecks = parsed.checks.filter((c) => !c.passed);

  return (
    <Panel as="section" className={styles.docPanel} aria-labelledby={titleId} data-doc={doc.info.id}>
      <header className={styles.docHead}>
        <span className={styles.docIcon} aria-hidden="true">
          <Icon name="file" size={24} />
        </span>
        <div>
          <h2 id={titleId} className={styles.docTitle} title={doc.info.name}>
            {recognised ? KIND_LABEL[parsed.doc_kind] : doc.info.name}
          </h2>
          <p className={styles.docMeta}>
            {recognised ? `${read} ${read === 1 ? "number" : "numbers"} read` : "Not read"}
          </p>
        </div>
        {recognised && (
          <ConfidenceBadge
            confidence={waiting > 0 ? "medium" : "high"}
            label={waiting > 0 ? `${waiting} ${waiting === 1 ? "needs" : "need"} a look` : "All look right"}
          />
        )}
      </header>

      {!recognised && <p className={styles.unread}>{UNRECOGNISED_NOTE}. No numbers were read from this file.</p>}

      {groupFields(parsed.fields).map((group) => (
        <div key={group.name} className={fields.group}>
          <h3 className={fields.groupTitle}>{group.name}</h3>
          <ul className={fields.list}>
            {group.fields.map((field) => {
              const failed = failedChecks.find((c) => c.keys.includes(field.key));
              return (
                <FieldRow
                  key={field.key}
                  field={field}
                  status={statuses.get(field.key)!}
                  selected={selectedKeys.includes(field.key)}
                  editing={editing.includes(field.key)}
                  onShowEvidence={failed ? () => onShowCheck(doc, failed) : undefined}
                  onSelect={() => onSelect(doc, field)}
                  onEdit={() => onEdit(field.key)}
                  onCancelEdit={() => onCancelEdit(field.key)}
                  onSave={(value) => onSave(field, value)}
                  onKeep={() => onKeep(field)}
                />
              );
            })}
          </ul>
        </div>
      ))}

      <Checks checks={parsed.checks} selectedKeys={selectedKeys} onShow={(check) => onShowCheck(doc, check)} />
    </Panel>
  );
}
