import { BrowserRouter, Routes, Route, Link } from 'react-router-dom'
import IntakeDashboard from './pages/IntakeDashboard'

function Home() {
  return (
    <main style={{ fontFamily: "'Inter', system-ui, sans-serif", padding: '2rem', background: '#0a0f1e', color: '#f1f5f9', minHeight: '100vh' }}>
      <h1 style={{ fontSize: '1.8rem', marginBottom: '1rem' }}>PA Evidence Assistant</h1>
      <p style={{ color: '#94a3b8', marginBottom: '2rem' }}>Elevance Prior Authorization Evidence Assistant — Phase 2 ready.</p>
      <nav style={{ display: 'flex', gap: '1rem' }}>
        <Link to="/intake" style={{ background: '#3b82f6', color: '#fff', padding: '0.6rem 1.2rem', borderRadius: '8px', textDecoration: 'none', fontWeight: 600 }}>
          → Intake Dashboard
        </Link>
      </nav>
    </main>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/intake" element={<IntakeDashboard />} />
      </Routes>
    </BrowserRouter>
  )
}
