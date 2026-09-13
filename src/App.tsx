import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Legal from './pages/Legal';
import Home from './pages/Home';
import UserDashboard from './pages/UserDashboard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/datenschutz" element={<Legal />} />
        <Route path="/impressum" element={<Legal imprint />} />
        <Route path="/info" element={<Navigate to="/" replace />} />
        <Route path="/" element={<Home />} />
        <Route path="/:username" element={<UserDashboard />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
