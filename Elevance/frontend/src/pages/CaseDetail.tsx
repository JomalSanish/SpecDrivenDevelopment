import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { fetchCaseGapAnalysis, GapChecklistItem } from '../services/api';
import { GapChecklist } from '../components/GapChecklist';

export const CaseDetail: React.FC = () => {
    const { id } = useParams<{id: string}>();
    const [checklist, setChecklist] = useState<GapChecklistItem[]>([]);
    const [selectedItem, setSelectedItem] = useState<GapChecklistItem | null>(null);

    useEffect(() => {
        if (id) {
            fetchCaseGapAnalysis(id).then(data => setChecklist(data.checklist));
        }
    }, [id]);

    return (
        <div style={{ display: 'flex', height: '100vh' }}>
            <div style={{ flex: 1, padding: '20px', borderRight: '1px solid #ddd' }}>
                <h2>Case Summary</h2>
                <p>Mock summary text from Reviewer Summary Agent would go here.</p>
                <div style={{ marginTop: '20px', padding: '10px', backgroundColor: '#f9f9f9' }}>
                    <strong>Routing Status:</strong> Mock Routing Queue (Nurse)
                </div>
            </div>
            
            <div style={{ flex: 1, padding: '20px', borderRight: '1px solid #ddd' }}>
                <GapChecklist checklist={checklist} onItemClick={setSelectedItem} />
                
                {selectedItem && (
                    <div style={{ marginTop: '20px', padding: '10px', border: '1px dashed #aaa' }}>
                        <h4>Evidence Drill-down</h4>
                        <p>Rationale: {selectedItem.rationale}</p>
                        <p>Refs: {selectedItem.evidence_refs.join(', ')}</p>
                    </div>
                )}
            </div>
            
            <div style={{ flex: 1, padding: '20px' }}>
                <h2>Document Viewer</h2>
                <div style={{ height: '400px', backgroundColor: '#eaeaea', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    PDF Mock Viewer
                </div>
            </div>
        </div>
    );
};
