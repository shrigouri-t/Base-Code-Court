import { Navigate, Route, Routes } from "react-router-dom";
import StudioPage from "./pages/StudioPage";
import "./App.css";

function App() {
  return (
    <Routes>
      <Route path="/" element={<StudioPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;
