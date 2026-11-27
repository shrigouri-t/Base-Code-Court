# Contribution scoring

CodeCourt keeps the configured signal calculation as `base_score`, and uses it
as one of the inputs to the bundled Random Forest Regressor. The regressor's
prediction is the contributor's final `score`; CodeCourt does not derive that
score by multiplying `base_score` by the anomaly penalty.

The model artifact is `backend/models/code_court_v1.1.pkl`. Its ordered input
contract is defined in `app/core/ml_scoring.py`. `lines_added` uses meaningful
credited lines, `adjusted_work` applies the quality modifier to those lines,
and `issues_handled` sums issues opened and issue comments by the contributor.
Signal-score features are passed on a 0-to-100 scale; `survival_rate` remains
a 0-to-1 ratio. `anomaly_flag` is set for any reported contributor anomaly,
including anomalies that do not apply a penalty. GitHub counts are zero when
unavailable, and `github_data_available` is 1 only when both review and issue
signals are available.

The model predicts a normalized value from 0 to 1, which CodeCourt converts to
the report's 0-to-100 scale. The bundled estimator was serialized with
scikit-learn 1.9.0; the backend requirements pin that version. If the artifact
cannot be loaded or inference fails, CodeCourt logs the error and uses the
rules-based `base_score` for that analysis. The affected contributor records
have no feature impacts and include a note that the rules-based score was used.

When available, SHAP's `TreeExplainer` attributes each prediction; if SHAP is
missing or fails, CodeCourt decomposes the Random Forest's tree paths instead.
The API returns the six largest signed feature impacts in score points. If both
attribution methods fail, the score is still returned with `feature_impacts`
set to `null`.

The default signal weights used to produce `base_score` are:

| Signal | Weight |
| --- | ---: |
| work | 0.45 |
| survival | 0.25 |
| ownership | 0.05 |
| review | 0.12 |
| issues | 0.06 |
| consistency | 0.07 |

Unavailable signals are removed and the remaining configured weights are
renormalized when calculating `base_score`. Scores support logarithmic,
square-root, and linear scaling.
