import { lazy, Suspense, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createAnalysis,
  getAnalysisHistory,
  getAnalysisResults,
  getAnalysisStatus,
  getErrorMessage,
  getReportPdf,
} from "../services/api";
const TimelineChart = lazy(() => import("../components/TimelineChart"));

const iconPaths = {
  scales: "M12 3v18m-7-3h14M5 18l-3-7h6l-3 7Zm14 0-3-7h6l-3 7ZM8 7l4-3 4 3",
  sparkle: "m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Zm7 12 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z",
  github: "M9 19c-4.3 1.4-4.3-2.5-6-3m12 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3-.3 6.1-1.5 6.1-6.7a5.2 5.2 0 0 0-1.4-3.6 4.8 4.8 0 0 0-.1-3.6s-1.2-.4-3.7 1.4a12.8 12.8 0 0 0-6.7 0C5.8 1.2 4.6 1.6 4.6 1.6a4.8 4.8 0 0 0-.1 3.6A5.2 5.2 0 0 0 3.1 8.8c0 5.2 3.1 6.4 6.1 6.7a3.4 3.4 0 0 0-.9 2.6V22",
  arrow: "M5 12h14m-6-6 6 6-6 6",
  warning: "M12 9v4m0 4h.01M10.3 3.9 1.8 18.5A1.7 1.7 0 0 0 3.3 21h17.4a1.7 1.7 0 0 0 1.5-2.5L13.7 3.9a2 2 0 0 0-3.4 0Z",
  clock: "M12 8v4l2.5 2.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  chart: "M3 3v18h18M8 15l4-4 4 4 5-7",
  code: "m8 17-5-5 5-5m8 10 5-5-5-5m-2-12-4 16",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4m4-5 5 5 5-5m-5 5V3",
  external: "M14 3h7v7m-1-6-9 9m-4-7H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2",
  shield: "M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Zm-3-11 2 2 4-4",
  check: "m5 12 4 4L19 6",
  repository: "M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21V5.5Zm0 13A2.5 2.5 0 0 1 6.5 16H20M8 7h8m-8 4h6",
  link: "M10 13a5 5 0 0 0 7.1 0l3-3A5 5 0 0 0 13 2.9l-1.7 1.7m2.7 6.4a5 5 0 0 0-7.1 0l-3 3A5 5 0 0 0 11 21.1l1.7-1.7",
};

function Icon({ name, size = 18 }) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={iconPaths[name]} />
    </svg>
  );
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString();
}

function initials(name = "") {
  return name
    .split(/[\s@._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function formatDate(value) {
  if (!value) return "Just now";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Recent";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function getRepositoryName(status, scores) {
  const fullName = scores?.meta?.repo || status?.params?.github_repo || status?.params?.repo_url || "";
  if (fullName.includes("/")) return fullName;
  const repoUrl = status?.params?.repo_url || "";
  const match = repoUrl.match(/github\.com\/([^/]+\/[^/?#]+)/i);
  return match?.[1]?.replace(/\.git$/i, "") || fullName || "Repository analysis";
}

function getGithubUrl(repositoryName) {
  const parts = repositoryName.split("/");
  return parts.length === 2
    ? `https://github.com/${parts.map(encodeURIComponent).join("/")}`
    : null;
}

function Stat({ label, value }) {
  return (
    <div className="stat-box">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
    </div>
  );
}

function EmptyResults() {
  return (
    <section className="panel empty-results">
      <div>
        <div className="empty-graphic"><Icon name="chart" size={30} /></div>
        <h2>Your contribution picture, at a glance.</h2>
        <p>Enter a public GitHub repository above. CodeCourt will score contributors and prepare a shareable report.</p>
      </div>
    </section>
  );
}

function ProgressCard({ status }) {
  const progress = Math.max(0, Math.min(100, Math.round((status?.progress || 0) * 100)));
  return (
    <div className="progress-card" aria-live="polite">
      <div className="progress-top">
        <div>
          <div className="progress-title">
            {status?.status === "queued" ? "Waiting in the analysis queue" : "Analyzing repository"}
          </div>
          <div className="progress-message">{status?.message || "Preparing your analysis…"}</div>
        </div>
        <span className="progress-percent">{progress}%</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={progress}
      >
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-meta">
        <span>{status?.stage ? `Stage: ${status.stage.replaceAll("_", " ")}` : "Starting analysis"}</span>
        <span>{status?.commit_count ? `${formatNumber(status.commit_count)} commits inspected` : "This can take a few minutes"}</span>
      </div>
    </div>
  );
}

function RankingTable({ ranking = [] }) {
  if (!ranking.length) {
    return <div className="chart-empty">No contributor ranking was returned for this analysis.</div>;
  }
  return (
    <div className="table-wrap">
      <table className="ranking-table">
        <thead>
          <tr>
            <th>Rank</th>
            <th>Contributor</th>
            <th>Score</th>
            <th>Commits</th>
            <th>Lines kept</th>
            <th>Team share</th>
          </tr>
        </thead>
        <tbody>
          {ranking.map((contributor, index) => (
            <tr key={contributor.author_key}>
              <td><span className={`rank-badge ${index === 0 ? "rank-first" : ""}`}>{contributor.rank || index + 1}</span></td>
              <td>
                <div className="contributor-cell">
                  <span className="contributor-avatar">{initials(contributor.display_name || contributor.author_key)}</span>
                  <span>
                    {contributor.display_name || contributor.author_key}
                    <span className="contributor-sub">{contributor.display_email || contributor.author_key}</span>
                  </span>
                </div>
              </td>
              <td className="score-cell">
                <span className="score-meter">
                  {Number(contributor.score || 0).toFixed(1)}
                  <span className="score-meter-track">
                    <span className="score-meter-fill" style={{ width: `${Math.min(100, Math.max(0, contributor.score || 0))}%` }} />
                  </span>
                </span>
              </td>
              <td>{formatNumber(contributor.commits)}</td>
              <td>{formatNumber(contributor.surviving_lines)}</td>
              <td>{`${Number(contributor.share_of_team || 0).toFixed(1)}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OwnershipList({ ownership }) {
  const directories = ownership?.directories || [];
  const maxLines = Math.max(1, ...directories.map((directory) => directory.total_lines || 0));
  if (!directories.length) return <div className="chart-empty">No directory ownership data was returned.</div>;
  return (
    <div className="ownership-list">
      {directories.slice(0, 8).map((directory) => (
        <div className="ownership-row" key={directory.path}>
          <span className="ownership-name" title={directory.path}>{directory.path || "(root)"}</span>
          <span className="ownership-count">{formatNumber(directory.total_lines)}</span>
          <span className="ownership-bar">
            <span style={{ width: `${Math.max(3, (directory.total_lines / maxLines) * 100)}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

function AnomalyList({ anomalies }) {
  const items = anomalies?.anomalies || [];
  if (!items.length) return <div className="anomaly-empty">No notable anomalies found.</div>;
  return (
    <div className="anomaly-list">
      {items.slice(0, 5).map((item, index) => (
        <div className="anomaly-item" key={`${item.author_key}-${item.kind}-${index}`}>
          <span className={`anomaly-icon ${item.severity === "info" ? "info" : ""}`}>
            <Icon name={item.severity === "info" ? "shield" : "warning"} size={14} />
          </span>
          <div className="anomaly-copy">
            <strong>{item.display_name || item.kind}</strong>
            <p>{item.message}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function ResultsPanel({ status, results, onDownload, downloading }) {
  const { scores, anomalies, timeline, ownership } = results;
  const ranking = scores.ranking || [];
  const meta = scores.meta || {};
  const repositoryName = getRepositoryName(status, scores);
  const githubUrl = getGithubUrl(repositoryName);

  return (
    <>
      <section className="panel section-card">
        <div className="panel-heading results-heading">
          <div>
            <div className="repo-title">
              <Icon name="repository" />
              <h2>
                {githubUrl ? <a href={githubUrl} target="_blank" rel="noreferrer">{repositoryName}</a> : repositoryName}
              </h2>
              {githubUrl && <a href={githubUrl} target="_blank" rel="noreferrer" aria-label="Open repository on GitHub"><Icon name="external" size={14} /></a>}
            </div>
            <p className="results-subtitle">
              {meta.head_sha ? `Analyzed at ${meta.head_sha.slice(0, 7)}` : "Contribution analysis"}{meta.generated_at ? ` · ${formatDate(meta.generated_at)}` : ""}
            </p>
          </div>
          <div className="results-actions">
            <span className="status-pill"><Icon name="check" size={12} /> Analysis complete</span>
            <button type="button" className="secondary-button" onClick={onDownload} disabled={downloading}>
              {downloading ? <span className="spinner" /> : <Icon name="download" size={14} />}
              {downloading ? "Preparing…" : "Download PDF"}
            </button>
          </div>
        </div>

        <div className="stats-grid">
          <Stat label="CONTRIBUTORS" value={formatNumber(ranking.length)} />
          <Stat label="COMMITS ANALYZED" value={formatNumber(meta.commits_analyzed || status.commit_count)} />
          <Stat label="TOP SCORE" value={ranking.length ? Number(ranking[0].score || 0).toFixed(1) : "—"} />
          <Stat label="ANOMALIES" value={formatNumber(anomalies?.counts?.warning || 0)} />
        </div>

        <div className="section-heading">
          <h3>Contributor leaderboard</h3>
          <span>Ranked by contribution score</span>
        </div>
        <RankingTable ranking={ranking} />

        <div className="detail-grid">
          <div className="detail-panel">
            <div className="section-heading">
              <h3>Contribution over time</h3>
              <span>Meaningful lines · weekly</span>
            </div>
            <Suspense fallback={<div className="chart-empty">Loading weekly chart…</div>}>
              <TimelineChart timeline={timeline} />
            </Suspense>
          </div>
          <div className="detail-panel">
            <div className="section-heading">
              <h3>Directory ownership</h3>
              <span>Lines by directory</span>
            </div>
            <OwnershipList ownership={ownership} />
          </div>
        </div>

        <div className="detail-panel" style={{ marginTop: 16 }}>
          <div className="section-heading">
            <h3>Analysis notes</h3>
            <span>{anomalies?.anomalies?.length || 0} signals</span>
          </div>
          <AnomalyList anomalies={anomalies} />
        </div>
      </section>
      <div className="footer">Scores are evidence-based signals to support review — not a substitute for human judgment.</div>
    </>
  );
}

function HistoryPanel({ history, activeId, loading, error, onSelect }) {
  return (
    <section className="panel sidebar-panel">
      <div className="panel-heading">
        <div>
          <h3>Recent analyses</h3>
          <p>Pick up where you left off</p>
        </div>
        <Icon name="clock" size={17} />
      </div>
      <div className="history-list">
        {loading && <div className="history-loading">Loading your latest reports…</div>}
        {!loading && error && <div className="history-empty">{error}</div>}
        {!loading && !error && !history.length && (
          <div className="history-empty">Your recent repository analyses will show up here.</div>
        )}
        {history.map((item) => {
          const label = item.params?.repo_url || item.params?.repo || `Analysis ${item.analysis_id.slice(0, 8)}`;
          return (
            <button
              type="button"
              className={`history-item ${activeId === item.analysis_id ? "active" : ""}`}
              key={item.analysis_id}
              onClick={() => onSelect(item.analysis_id)}
            >
              <span className="history-icon"><Icon name="repository" size={15} /></span>
              <span className="history-copy">
                <span className="history-name">{label}</span>
                <span className="history-date">{formatDate(item.created_at)}</span>
              </span>
              <span className={`history-status ${item.status}`} title={item.status} />
            </button>
          );
        })}
      </div>
    </section>
  );
}

function SidebarInfo({ availableSignals = [] }) {
  const signals = [
    ["Work", "work"],
    ["Code survival", "survival"],
    ["Ownership", "ownership"],
    ["Consistency", "consistency"],
    ["Review activity", "review"],
    ["Issue activity", "issues"],
  ];
  return (
    <section className="panel info-panel">
      <div className="info-banner">
        <h3>Fair contribution signals</h3>
        <p>Multiple signals help put activity in context. Some signals need enough repository history to be available.</p>
      </div>
      <div className="signal-list">
        {signals.map(([label, key]) => (
          <div className="signal-row" key={key}>
            <span>{label}</span>
            <span className={`signal-check ${availableSignals.includes(key) ? "" : "off"}`}>
              {availableSignals.includes(key) ? "Included" : "—"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function StudioPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const analysisId = searchParams.get("analysis") || "";
  const [repoUrl, setRepoUrl] = useState("");
  const [status, setStatus] = useState(null);
  const [results, setResults] = useState(null);
  const [downloadError, setDownloadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");

  useEffect(() => {
    let active = true;
    getAnalysisHistory()
      .then((items) => {
        if (active) setHistory(items);
      })
      .catch((error) => {
        if (active) setHistoryError(`Could not load previous analyses: ${getErrorMessage(error)}`);
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!analysisId) return undefined;

    let active = true;
    let timer;

    async function poll() {
      try {
        const nextStatus = await getAnalysisStatus(analysisId);
        if (!active) return;
        setStatus(nextStatus);
        setHistory((previous) => previous.map((item) => (
          item.analysis_id === analysisId ? { ...item, status: nextStatus.status, progress: nextStatus.progress } : item
        )));
        if (nextStatus.status === "succeeded") {
          const nextResults = await getAnalysisResults(analysisId);
          if (active) setResults({ analysisId, data: nextResults });
          return;
        }
        if (nextStatus.status === "failed") {
          return;
        }
        timer = window.setTimeout(poll, 1800);
      } catch (error) {
        if (active) setResults({ analysisId, error: getErrorMessage(error) });
      }
    }

    poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [analysisId]);

  async function handleSubmit(event) {
    event.preventDefault();
    const value = repoUrl.trim();
    if (!value) {
      setSubmitError("Enter a public GitHub repository URL or owner/repository.");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      const ticket = await createAnalysis(value);
      setSearchParams({ analysis: ticket.analysis_id });
      setHistory((previous) => [
        {
          analysis_id: ticket.analysis_id,
          status: ticket.status,
          created_at: new Date().toISOString(),
          params: { repo_url: value },
        },
        ...previous.filter((item) => item.analysis_id !== ticket.analysis_id),
      ].slice(0, 8));
    } catch (error) {
      setSubmitError(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  }

  function selectAnalysis(id) {
    setSubmitError("");
    setSearchParams({ analysis: id });
  }

  async function handleDownload() {
    if (!analysisId) return;
    setDownloading(true);
    setDownloadError("");
    try {
      const pdf = await getReportPdf(analysisId);
      const url = URL.createObjectURL(pdf);
      const link = document.createElement("a");
      link.href = url;
      link.download = `codecourt-${analysisId}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setDownloadError(`PDF download failed: ${getErrorMessage(error)}`);
    } finally {
      setDownloading(false);
    }
  }

  const currentStatus = status?.analysis_id === analysisId ? status : null;
  const currentResults = results?.analysisId === analysisId ? results : null;
  const availableSignals = currentResults?.data?.scores?.available_signals || [];
  const isRunning = currentStatus?.status === "queued" || currentStatus?.status === "running";
  const showResults = currentStatus?.status === "succeeded" && currentResults?.data;
  const showEmpty = !analysisId;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="CodeCourt home">
          <span className="brand-mark"><Icon name="scales" size={20} /></span>
          <span>CodeCourt</span>
        </a>
        <div className="topbar-note"><span className="status-dot" /> Open-source contribution intelligence</div>
      </header>

      <main className="main-content">
        <section className="hero-panel">
          <div className="hero-copy">
            <div className="eyebrow"><Icon name="sparkle" size={15} /> CONTRIBUTION ANALYSIS, MADE CLEAR</div>
            <h1>Give every contribution <span>its due.</span></h1>
            <p>Understand the work behind your code. Analyze a public GitHub repository and see a thoughtful, transparent view of how your team contributes.</p>
          </div>
          <div className="hero-visual" aria-hidden="true">
            <span className="orbit" />
            <span className="orbit orbit-two" />
            <span className="orbit orbit-three" />
            <span className="hero-spark spark-one" />
            <span className="hero-spark spark-two" />
            <div className="hero-score-card">
              <div className="score-card-top"><span>TEAM CONTRIBUTION</span><span>+12.8%</span></div>
              <div className="score-card-title">A clearer picture.</div>
              <div className="score-card-person"><span className="avatar">AM</span><span className="score-person-name">A. Morgan</span><span className="score-person-value">94.8</span></div>
              <div className="score-card-person"><span className="avatar avatar-lilac">JL</span><span className="score-person-name">J. Lee</span><span className="score-person-value">86.2</span></div>
              <div className="score-card-person"><span className="avatar avatar-gold">SK</span><span className="score-person-name">S. Khan</span><span className="score-person-value">79.4</span></div>
            </div>
          </div>
        </section>

        <div className="analysis-grid">
          <div className="primary-column">
            <section className="panel form-panel">
              <div className="panel-heading">
                <div>
                  <h2>Start a repository analysis</h2>
                  <p>Public GitHub repositories only. No account connection needed.</p>
                </div>
                <span className="beta-pill"><Icon name="shield" size={12} /> Free analysis</span>
              </div>
              <form className="repo-form" onSubmit={handleSubmit}>
                <label className="input-label" htmlFor="repository-url">GitHub repository</label>
                <div className="input-row">
                  <span className="repo-input-wrap">
                    <Icon name="github" size={17} />
                    <input
                      className="repo-input"
                      id="repository-url"
                      type="text"
                      value={repoUrl}
                      onChange={(event) => setRepoUrl(event.target.value)}
                      placeholder="https://github.com/owner/repository"
                      autoComplete="url"
                      disabled={isRunning || submitting}
                    />
                  </span>
                  <button className="primary-button" type="submit" disabled={isRunning || submitting}>
                    {submitting || isRunning ? <span className="spinner" /> : <Icon name="arrow" size={15} />}
                    {submitting ? "Starting…" : isRunning ? "Analyzing…" : "Analyze repository"}
                  </button>
                </div>
                <p className="form-hint">You can also enter a short name like <code>owner/repository</code></p>
                {submitError && <div className="alert" role="alert"><Icon name="warning" size={15} />{submitError}</div>}
                {isRunning && <ProgressCard status={currentStatus} />}
                {currentResults?.error && (
                  <div className="alert" role="alert"><Icon name="warning" size={15} />{currentResults.error}</div>
                )}
                {downloadError && (
                  <div className="alert" role="alert"><Icon name="warning" size={15} />{downloadError}</div>
                )}
                {currentStatus?.status === "failed" && (
                  <div className="alert" role="alert"><Icon name="warning" size={15} />{currentStatus.error?.message || "The analysis failed. Please try again."}</div>
                )}
              </form>
            </section>

            {showResults ? (
              <ResultsPanel
                status={currentStatus}
                results={currentResults.data}
                onDownload={handleDownload}
                downloading={downloading}
              />
            ) : showEmpty ? <EmptyResults /> : null}
          </div>

          <aside className="sidebar-column">
            <HistoryPanel
              history={history}
              activeId={analysisId}
              loading={historyLoading}
              error={historyError}
              onSelect={selectAnalysis}
            />
            <SidebarInfo availableSignals={availableSignals} />
          </aside>
        </div>
      </main>
    </div>
  );
}

export default StudioPage;
