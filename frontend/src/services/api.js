import axios from "axios";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

export async function createAnalysis(repoUrl) {
  const response = await api.post("/analyze", {
    repo_url: repoUrl.trim(),
    max_commits: 300,
    use_github: true,
    enable_penalties: true,
    force: false,
  });
  return response.data;
}

export async function getAnalysisStatus(analysisId) {
  const response = await api.get(`/analyses/${encodeURIComponent(analysisId)}`);
  return response.data;
}

export async function getAnalysisResults(analysisId) {
  const id = encodeURIComponent(analysisId);
  const [scores, anomalies, timeline, ownership] = await Promise.all([
    api.get(`/scores/${id}`),
    api.get(`/anomalies/${id}`),
    api.get(`/timeline/${id}`),
    api.get(`/ownership/${id}`),
  ]);
  return {
    scores: scores.data,
    anomalies: anomalies.data,
    timeline: timeline.data,
    ownership: ownership.data,
  };
}

export async function getAnalysisHistory() {
  const response = await api.get("/analyses", {
    params: { limit: 8, offset: 0 },
  });
  return response.data.analyses;
}

export async function getReportPdf(analysisId) {
  const response = await api.get(
    `/reports/${encodeURIComponent(analysisId)}/pdf`,
    { responseType: "blob" },
  );
  return response.data;
}

export function getErrorMessage(error) {
  return (
    error.response?.data?.error?.message ||
    error.response?.data?.detail ||
    error.message ||
    "Something went wrong. Please try again."
  );
}
