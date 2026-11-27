import { useState } from "react";
import {
  Info,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

function formatImpact(value) {
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}`;
}

function ImpactBadge({ impact }) {
  const isPositive = impact.impact >= 0;
  const isAnomaly = impact.feature === "penalty_multiplier" || impact.feature === "anomaly_flag";
  const Icon = isAnomaly ? ShieldAlert : isPositive ? TrendingUp : TrendingDown;

  return (
    <span className={`feature-impact-badge ${isPositive ? "positive" : "negative"}`}>
      <Icon aria-hidden="true" size={13} />
      {formatImpact(impact.impact)} {impact.label}
    </span>
  );
}

function FeatureImpactBreakdown({ featureImpacts, score, baseScore }) {
  const [selectedFeature, setSelectedFeature] = useState(null);
  const impacts = Array.isArray(featureImpacts)
    ? featureImpacts
      .filter((item) => item && item.impact != null && Number.isFinite(Number(item.impact)) && item.label)
      .map((item) => ({ ...item, impact: Number(item.impact) }))
      .sort((left, right) => Math.abs(right.impact) - Math.abs(left.impact))
    : [];

  if (!impacts.length) {
    return (
      <div className="feature-impact-fallback">
        <Info aria-hidden="true" size={15} />
        <span>Rule-based score weighting applied.</span>
      </div>
    );
  }

  const maxMagnitude = Math.max(...impacts.map((item) => Math.abs(item.impact)), 0.01);
  const scoreDifference = Number(score) - Number(baseScore);
  const hasScoreDifference = Number.isFinite(scoreDifference);
  const summaryFeatures = impacts.slice(0, 2).map((item) => item.label).join(" and ");
  const positives = impacts.filter((item) => item.impact > 0).slice(0, 3);
  const negatives = impacts.filter((item) => item.impact < 0).slice(0, 3);
  const selectedImpact = impacts.find((item) => item.feature === selectedFeature);

  return (
    <section className="feature-impact-breakdown" aria-label="Feature impact explanation">
      <div className="feature-impact-heading">
        <div>
          <h4>What influenced this score?</h4>
          <p>Largest model attributions, shown in score points</p>
        </div>
        <Info aria-hidden="true" size={16} />
      </div>

      <div className="feature-impact-badges" aria-label="Largest positive and negative impacts">
        {positives.map((impact) => (
          <ImpactBadge key={impact.feature} impact={impact} />
        ))}
        {negatives.map((impact) => (
          <ImpactBadge key={impact.feature} impact={impact} />
        ))}
      </div>

      <div className="feature-impact-chart">
        <div className="feature-impact-chart-heading">
          <span />
          <span className="feature-impact-scale-labels">
            <span>Negative pull</span>
            <span className="feature-impact-zero-label">0.0</span>
            <span>Positive pull</span>
          </span>
          <span />
        </div>
        {impacts.map((impact) => {
          const magnitude = impact.impact === 0
            ? "0%"
            : `${Math.max(3, (Math.abs(impact.impact) / maxMagnitude) * 100)}%`;
          const isPositive = impact.impact > 0;
          const isNegative = impact.impact < 0;
          const isSelected = selectedFeature === impact.feature;
          return (
            <button
              type="button"
              className={`feature-impact-row ${isSelected ? "selected" : ""}`}
              key={impact.feature}
              onClick={() => setSelectedFeature(isSelected ? null : impact.feature)}
              aria-pressed={isSelected}
              title={`${impact.label}: ${formatImpact(impact.impact)} points`}
            >
              <span className="feature-impact-label">{impact.label}</span>
              <span className="feature-impact-track" aria-hidden="true">
                <span className="feature-impact-negative-zone">
                  {isNegative && (
                    <span className="feature-impact-bar negative" style={{ width: magnitude }} />
                  )}
                </span>
                <span className="feature-impact-zero-axis" />
                <span className="feature-impact-positive-zone">
                  {isPositive && (
                    <span className="feature-impact-bar positive" style={{ width: magnitude }} />
                  )}
                </span>
              </span>
              <span className={`feature-impact-value ${isPositive ? "positive" : isNegative ? "negative" : ""}`}>
                {formatImpact(impact.impact)}
              </span>
            </button>
          );
        })}
      </div>

      {selectedImpact && (
        <p className="feature-impact-selected" role="status">
          {selectedImpact.label} contributed {formatImpact(selectedImpact.impact)} points
          relative to the model&apos;s expected output.
        </p>
      )}

      <div className="feature-impact-summary">
        <Info aria-hidden="true" size={15} />
        <p>
          {hasScoreDifference
            ? `The model adjusted the base score by ${formatImpact(scoreDifference)} points.`
            : "The model score includes the feature contributions shown above."}
          {summaryFeatures ? ` Largest attributions: ${summaryFeatures}.` : ""}
        </p>
      </div>
      <p className="feature-impact-note">
        Attributions are relative to the model&apos;s expected output; the rules-based base score
        is also an input to the model.
      </p>
    </section>
  );
}

export default FeatureImpactBreakdown;
