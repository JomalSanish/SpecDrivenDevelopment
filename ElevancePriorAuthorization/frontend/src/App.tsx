import { BrowserRouter, Routes, Route } from 'react-router-dom'

function Home() {
  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}>
      <h1>PA Evidence Assistant</h1>
      <p>Elevance Prior Authorization Evidence Assistant — Phase 1 foundation ready.</p>
    </main>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  )
}
