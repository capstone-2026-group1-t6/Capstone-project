import { BrowserRouter, Routes, Route } from 'react-router-dom';
import SiteLayout from './components/layout/SiteLayout.jsx';
import Index from './pages/index.jsx';
import Upload from './pages/upload.jsx';
import NotFound from './pages/not-found.jsx';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route path="/" element={<Index />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}