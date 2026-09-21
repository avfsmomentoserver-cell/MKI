import { Routes, Route } from 'react-router-dom'
import { Shell } from './components/Shell'
import { OverviewPage } from './pages/OverviewPage'
import { KnowledgePage } from './pages/KnowledgePage'
import { ResearchPage } from './pages/ResearchPage'
import { ExperimentsPage } from './pages/ExperimentsPage'
import { DecisionsPage } from './pages/DecisionsPage'
import { DocumentationPage } from './pages/DocumentationPage'

function App() {
  return (
    <Shell>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/research" element={<ResearchPage />} />
        <Route path="/experiments" element={<ExperimentsPage />} />
        <Route path="/decisions" element={<DecisionsPage />} />
        <Route path="/documentation" element={<DocumentationPage />} />
        <Route path="/insights" element={<div className="p-4">Insights page coming soon</div>} />
        <Route path="/reports" element={<div className="p-4">Reports page coming soon</div>} />
        <Route path="/search" element={<div className="p-4">Search page coming soon</div>} />
        <Route path="/system" element={<div className="p-4">System page coming soon</div>} />
      </Routes>
    </Shell>
  )
}

export default App
