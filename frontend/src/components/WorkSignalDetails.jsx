import { Code2 } from "lucide-react";

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function WorkSignalDetails({ metadata }) {
  if (!metadata) {
    return (
      <div className="work-signal-details">
        <p>AST diagnostics are unavailable for this analysis.</p>
      </div>
    );
  }

  const languages = Object.entries(metadata.language_distribution || {});
  const parsedFiles = Number(metadata.ast_files_parsed || 0);
  const totalFiles = Number(metadata.ast_files_total || 0);

  return (
    <section className="work-signal-details" aria-label="Work Signal diagnostics">
      <div className="work-signal-heading">
        <Code2 aria-hidden="true" size={15} />
        <h4>Work Signal diagnostics</h4>
      </div>
      <div className="work-signal-metrics">
        <span><strong>{formatNumber(metadata.ast_nodes_count)}</strong> AST nodes</span>
        <span><strong>{Number(metadata.ast_weighted_volume || 0).toFixed(2)}</strong> weighted volume</span>
        <span className="work-signal-bonus">
          <strong>+{Number(metadata.refactoring_bonus || 0).toFixed(2)}</strong> refactoring bonus
        </span>
        <span><strong>{Number(metadata.language_weight || 1).toFixed(2)}x</strong> language weight</span>
      </div>
      {languages.length > 0 && (
        <p className="work-signal-languages">
          Languages: {languages.map(([language, count]) => `${language} (${count})`).join(", ")}
        </p>
      )}
      {!parsedFiles && (
        <p className="work-signal-fallback">
          Tree-Sitter was unavailable for these files ({parsedFiles}/{totalFiles} parsed); clean
          line-count fallback was used.
        </p>
      )}
    </section>
  );
}

export default WorkSignalDetails;
