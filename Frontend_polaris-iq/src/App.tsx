import { useState } from 'react';
import MainLayout from './components/layout/MainLayout';
import type { PageId } from './components/layout/Sidebar';
import HomeDashboard from './components/pages/HomeDashboard';
import QueryStudio from './components/pages/QueryStudio';
import DataWorkspace from './components/pages/DataWorkspace';
import InsightsPage from './components/pages/InsightsPage';
import PipelineMonitor from './components/pages/PipelineMonitor';

function App() {
  const [currentPage, setCurrentPage] = useState<PageId>('home');

  return (
    <MainLayout currentPage={currentPage} onNavigate={setCurrentPage}>
      <div style={{ display: currentPage === 'home' ? 'block' : 'none' }}><HomeDashboard /></div>
      <div style={{ display: currentPage === 'query' ? 'block' : 'none' }}><QueryStudio /></div>
      <div style={{ display: currentPage === 'workspace' ? 'block' : 'none' }}><DataWorkspace /></div>
      <div style={{ display: currentPage === 'insights' ? 'block' : 'none' }}><InsightsPage /></div>
      <div style={{ display: currentPage === 'pipeline' ? 'block' : 'none' }}><PipelineMonitor /></div>
    </MainLayout>
  );
}

export default App;
