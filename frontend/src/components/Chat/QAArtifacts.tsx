import type { QAArtifact, QACitation } from "../../types/api";

export function ArtifactRenderer({ artifact }: { artifact: QAArtifact }) {
  if (artifact.type === "column_table") {
    const columns = Array.isArray(artifact.data.columns) ? artifact.data.columns as Array<Record<string, unknown>> : [];
    return (
      <section className="qa-artifact">
        <strong>{artifact.title}</strong>
        <div className="qa-table-wrap">
          <table><thead><tr><th>#</th><th>Column</th><th>Type</th><th>Nullable</th><th>Key</th><th>Default</th><th>Comment</th></tr></thead>
            <tbody>{columns.map((column, index) => <tr key={String(column.name ?? index)}><td>{String(column.ordinal ?? index + 1)}</td><td>{String(column.name ?? "")}</td><td>{String(column.data_type ?? "")}</td><td>{column.nullable ? "YES" : "NO"}</td><td>{String(column.key ?? "")}</td><td>{column.default == null ? "NULL" : String(column.default)}</td><td>{String(column.comment ?? "")}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
    );
  }
  const items = artifact.type === "relation_cards" || artifact.type === "evidence_cards" ? artifact.data.relations : artifact.type === "clarification_options" ? artifact.data.candidates : artifact.type === "index_table" ? artifact.data.indexes : undefined;
  return (
    <section className="qa-artifact">
      <strong>{artifact.title}</strong>
      {Array.isArray(items) ? <div className="qa-card-list">{items.map((item, index) => <code key={index}>{JSON.stringify(item)}</code>)}</div> : <dl>{Object.entries(artifact.data).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>}
    </section>
  );
}

export function CitationList({ citations }: { citations: QACitation[] }) {
  if (!citations.length) return null;
  return (
    <details className="qa-citations">
      <summary>Evidence citations ({citations.length})</summary>
      <ol>{citations.map((citation) => <li key={citation.citation_id}><strong>{citation.label}</strong><code>{JSON.stringify(citation.locator)}</code></li>)}</ol>
    </details>
  );
}
