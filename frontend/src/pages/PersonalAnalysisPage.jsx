import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowUpRight,
  CircleAlert,
  Code2,
  Scale,
} from "lucide-react";
import FeatureImpactBreakdown from "../components/FeatureImpactBreakdown";
import WorkSignalDetails from "../components/WorkSignalDetails";
import {
  getAnalysisResults,
  getAnalysisStatus,
  getErrorMessage,
} from "../services/api";

const signalLabels = {
  work: "Work signal",
  survival: "Code survival",
  ownership: "Code ownership",
  consistency: "Consistency",
  review: "Review activity",
  issues: "Issue activity",
};

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function formatMetric(value, digits = 1) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString(undefined, { maximumFractionDigits: digits })
    : "—";
}

function getRepositoryName(status, scores) {
  const name = scores?.meta?.repo
    || status?.params?.github_repo
    || status?.params?.repo_url
    || "Repository analysis";
  const match = name.match(/github\.com\/([^/?#]+\/[^/?#]+)/i);
  return match?.[1]?.replace(/\.git$/i, "") || name;
}

function ScoreStat({ label, value, detail }) {
  return (
    <div className="personal-analysis-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}

function SignalBreakdown({ signals }) {
  const entries = Object.entries(signals || {})
    .filter(([key, signal]) => key !== "work_metadata" && signal && typeof signal === "object");

  if (!entries.length) {
    return <p className="personal-analysis-empty">No individual signal breakdown is available.</p>;
  }

  return (
    <div className="personal-signal-grid">
      {entries.map(([key, signal]) => (
        <article className="personal-signal-card" key={key}>
          <div className="personal-signal-card-top">
            <h3>{signalLabels[key] || signal.name || key}</h3>
            <span className={signal.available ? "available" : "unavailable"}>
              {signal.available ? "Included" : "Unavailable"}
            </span>
          </div>
          <strong className="personal-signal-points">
            {formatMetric(signal.points, 2)}
            <small> points</small>
          </strong>
          <div className="personal-signal-meta">
            <span>Signal score <strong>{formatMetric(signal.score == null ? null : signal.score * 100)}%</strong></span>
            <span>Weight <strong>{formatMetric(signal.effective_weight == null ? null : signal.effective_weight * 100)}%</strong></span>
            <span>Raw value <strong>{formatMetric(signal.raw_value, 2)}</strong></span>
          </div>
          {signal.note && <p>{signal.note}</p>}
        </article>
      ))}
    </div>
  );
}

function PersonalAnalysisPage() {
  const { analysisId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const authorKey = searchParams.get("contributor") || "";
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function loadReport() {
      setLoading(true);
      setError("");
      setReport(null);
      try {
        const status = await getAnalysisStatus(analysisId);
        if (status.status !== "succeeded") {
          if (active) {
            setError(status.status === "failed"
              ? status.error?.message || "This analysis failed."
              : "This analysis is not complete yet. Return to the repository report and try again when it finishes.");
          }
          return;
        }

        const results = await getAnalysisResults(analysisId);
        const contributor = results.scores.ranking?.find(
          (item) => item.author_key === authorKey,
        );
        if (!contributor) {
          if (active) setError("This contributor was not found in the selected analysis.");
          return;
        }
        if (active) setReport({ status, results, contributor });
      } catch (loadError) {
        if (active) setError(getErrorMessage(loadError));
      } finally {
        if (active) setLoading(false);
      }
    }

    loadReport();
    return () => {
      active = false;
    };
  }, [analysisId, authorKey]);

  const contributor = report?.contributor;
  const results = report?.results;
  const scoreChange = contributor
    ? Number(contributor.score) - Number(contributor.base_score)
    : 0;
  const personalAnomalies = (results?.anomalies?.anomalies || [])
    .filter((item) => item.author_key === authorKey);
  const contributorNotes = Array.isArray(contributor?.notes) ? contributor.notes : [];
  const notes = [...contributorNotes, ...personalAnomalies.map((item) => item.message)]
    .filter(Boolean);
  const repositoryName = getRepositoryName(report?.status, results?.scores);
  const reportUrl = `/?analysis=${encodeURIComponent(analysisId)}`;

  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to={reportUrl} aria-label="Back to CodeCourt report">
          <span className="brand-mark"><Scale aria-hidden="true" size={20} /></span>
          <span>CodeCourt</span>
        </Link>
        <div className="topbar-note"><span className="status-dot" /> Personal contribution report</div>
      </header>

      <main className="main-content personal-analysis-content">
        <Link className="personal-analysis-back" to={reportUrl}>
          <ArrowLeft aria-hidden="true" size={15} />
          Back to repository report
        </Link>

        {loading && (
          <section className="panel personal-analysis-message" aria-live="polite">
            <span className="spinner" />
            <p>Loading this contributor&apos;s analysis…</p>
          </section>
        )}

        {!loading && error && (
          <section className="panel personal-analysis-message" role="alert">
            <CircleAlert aria-hidden="true" size={19} />
            <p>{error}</p>
          </section>
        )}

        {!loading && contributor && (
          <>
            <section className="personal-analysis-hero">
              <div>
                <span className="personal-analysis-eyebrow"><Code2 aria-hidden="true" size={15} /> PERSONAL CONTRIBUTION ANALYSIS</span>
                <h1>{contributor.display_name || contributor.author_key}</h1>
                <p>{contributor.display_email || contributor.author_key} <span>·</span> {repositoryName}</p>
              </div>
              <div className="personal-rank-card">
                <span>Leaderboard rank</span>
                <strong>#{contributor.rank}</strong>
                <small>of {formatNumber(results.scores.ranking?.length)} contributors</small>
              </div>
            </section>

            <section className="personal-analysis-stats" aria-label="Contribution summary">
              <ScoreStat label="Final score" value={formatMetric(contributor.score)} detail="out of 100" />
              <ScoreStat
                label="Model adjustment"
                value={`${scoreChange >= 0 ? "+" : ""}${formatMetric(scoreChange)}`}
                detail={`Base score ${formatMetric(contributor.base_score)}`}
              />
              <ScoreStat label="Team share" value={`${formatMetric(contributor.share_of_team)}%`} />
              <ScoreStat label="Commits" value={formatNumber(contributor.commits)} />
              <ScoreStat label="Credited lines" value={formatNumber(contributor.credited_lines)} />
              <ScoreStat label="Surviving lines" value={formatNumber(contributor.surviving_lines)} />
            </section>

            <section className="panel personal-analysis-section" aria-label="Model score explanation">
              <FeatureImpactBreakdown
                featureImpacts={contributor.feature_impacts}
                score={contributor.score}
                baseScore={contributor.base_score}
              />
            </section>

            <section className="panel personal-analysis-section">
              <div className="personal-section-heading">
                <div>
                  <h2>Contribution signal breakdown</h2>
                  <p>How each available signal contributed to the rules-based base score.</p>
                </div>
                <Scale aria-hidden="true" size={19} />
              </div>
              <SignalBreakdown signals={contributor.signals} />
            </section>

            <section className="panel personal-analysis-section">
              <div className="personal-section-heading">
                <div>
                  <h2>Work signal details</h2>
                  <p>AST complexity, language weighting, and refactoring diagnostics.</p>
                </div>
                <Code2 aria-hidden="true" size={19} />
              </div>
              <WorkSignalDetails metadata={contributor.work_metadata} />
            </section>

            <section className="panel personal-analysis-section">
              <div className="personal-section-heading">
                <div>
                  <h2>Review notes</h2>
                  <p>Contributor-specific observations from this repository analysis.</p>
                </div>
                <CircleAlert aria-hidden="true" size={19} />
              </div>
              {notes.length
                ? <ul className="personal-notes">{notes.map((note, index) => <li key={`${note}-${index}`}>{note}</li>)}</ul>
                : <p className="personal-analysis-empty">No contributor-specific review notes were recorded.</p>}
            </section>

            <footer className="footer">
              Scores are evidence-based signals to support review — not a substitute for human judgment.
            </footer>
          </>
        )}

        {!loading && !error && !contributor && (
          <section className="panel personal-analysis-message">
            <CircleAlert aria-hidden="true" size={19} />
            <p>No contributor was selected. Return to the report and choose a contributor.</p>
            <Link to={reportUrl}>Open repository report <ArrowUpRight aria-hidden="true" size={14} /></Link>
          </section>
        )}
      </main>
    </div>
  );
}

export default PersonalAnalysisPage;
