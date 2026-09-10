import { NavLink, Route, Routes } from "react-router-dom";
import { GraphPage } from "./pages/GraphPage";
import { OntologyPage } from "./pages/OntologyPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";

export function App() {
  return (
    <>
      <nav className="app-nav">
        <NavLink to="/" end>
          本体
        </NavLink>
        <NavLink to="/upload">上传</NavLink>
        <NavLink to="/review">审阅</NavLink>
        <NavLink to="/graph">图</NavLink>
        <NavLink to="/settings">设置</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<OntologyPage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </>
  );
}
