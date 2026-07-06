import React from 'react';
import { GapChecklistItem } from '../services/api';

interface Props {
    checklist: GapChecklistItem[];
    onItemClick?: (item: GapChecklistItem) => void;
}

export const GapChecklist: React.FC<Props> = ({ checklist, onItemClick }) => {
    const getConfidenceColor = (level: string) => {
        switch(level) {
            case 'escalate': return 'red';
            case 'caution': return 'orange';
            case 'normal': return 'green';
            default: return 'gray';
        }
    };

    return (
        <div style={{ padding: '20px', border: '1px solid #ccc', borderRadius: '8px' }}>
            <h3>Policy Checklist</h3>
            <ul style={{ listStyleType: 'none', padding: 0 }}>
                {checklist.map((item, idx) => (
                    <li 
                        key={idx} 
                        style={{ 
                            marginBottom: '10px', 
                            padding: '10px', 
                            border: `1px solid ${getConfidenceColor(item.confidence_level)}`,
                            cursor: 'pointer'
                        }}
                        onClick={() => onItemClick && onItemClick(item)}
                    >
                        <strong>[{item.status.toUpperCase()}]</strong> {item.criterion}
                        {item.conflict_detected && <span style={{ color: 'red', marginLeft: '10px' }}>⚠️ CONFLICT</span>}
                    </li>
                ))}
            </ul>
        </div>
    );
};
