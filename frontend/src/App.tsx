import { NavLink, Route, Routes } from "react-router-dom";
import { GraphPage } from "./pages/GraphPage";
import { OntologyPage } from "./pages/OntologyPage";
import { ReviewPage } from "./pages/ReviewPage";
import { SettingsPage } from "./pages/SettingsPage";
import { UploadPage } from "./pages/UploadPage";
import { TipHost } from "./tips";

function Icon({ path }: { path: string }) {
  return (
    <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path d={path} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const links: { to: string; label: string; icon: string; end?: boolean }[] = [
  {
    to: "/",
    label: "本体",
    end: true,
    icon: "M12 3 4.5 7.5v9L12 21l7.5-4.5v-9L12 3Zm0 9 7.5-4.5M12 12v9M12 12 4.5 7.5",
  },
  {
    to: "/upload",
    label: "上传",
    icon: "M12 16V5m0 0 4 4M12 5 8 9M5 19h14",
  },
  {
    to: "/review",
    label: "审阅",
    icon: "M8 6h12M8 12h12M8 18h8M4 6h.01M4 12h.01M4 18h.01",
  },
  {
    to: "/graph",
    label: "图",
    icon: "M8 8a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm10 4a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5ZM7 20a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Zm2.2-11.2 6.6 2.4M9.1 16.2 16 12.2",
  },
  {
    to: "/settings",
    label: "设置",
    icon: "M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Zm8.2-3.7-.9-1.6 1-1.7-1.8-1.8-1.7 1-.6-.3-1.6-.9h-2.2l-1.6.9-.6.3-1.7-1-1.8 1.8 1 1.7-.9 1.6v2.2l.9 1.6-1 1.7 1.8 1.8 1.7-1 .6.3 1.6.9h2.2l1.6-.9.6-.3 1.7 1 1.8-1.8-1-1.7.9-1.6v-2.2Z",
  },
];

export function App() {
  return (
    <TipHost>
    <div className="shell">
      <aside className="rail">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            O
          </span>
          <div>
            <p className="brand-name">OntoCore</p>
            <p className="brand-sub">对象 · 属性 · 关系</p>
          </div>
        </div>
        <nav className="app-nav">
          {links.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              <Icon path={item.icon} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <p className="rail-foot">工作室</p>
      </aside>
      <div className="canvas">
        <Routes>
          <Route path="/" element={<OntologyPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/graph" element={<GraphPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </div>
    </div>
    </TipHost>
  );
}
