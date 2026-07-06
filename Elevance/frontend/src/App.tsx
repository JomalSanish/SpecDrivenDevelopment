import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { CaseDetail } from './pages/CaseDetail';

const QueueMock: React.FC = () => (
    <div style={{ padding: '20px' }}>
        <h2>Nurse Queue</h2>
        <ul>
            <li><Link to="/case/123">Case 123 (Needs Review)</Link></li>
        </ul>
    </div>
);

const App: React.FC = () => {
    return (
        <Router>
            <div>
                <nav style={{ padding: '10px', backgroundColor: '#003366', color: 'white' }}>
                    <strong>Elevance Evidence Assistant</strong>
                </nav>
                <Routes>
                    <Route path="/" element={<QueueMock />} />
                    <Route path="/case/:id" element={<CaseDetail />} />
                </Routes>
            </div>
        </Router>
    );
};

export default App;
