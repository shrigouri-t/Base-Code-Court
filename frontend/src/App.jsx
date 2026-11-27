import { Navigate, Route, Routes } from "react-router-dom";
import PersonalAnalysisPage from "./pages/PersonalAnalysisPage";
import StudioPage from "./pages/StudioPage";
import "./App.css";

function App() {
  return (
    <Routes>
      <Route path="/" element={<StudioPage />} />
      <Route path="/personal-analysis/:analysisId" element={<PersonalAnalysisPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
