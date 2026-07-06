export interface EvidenceItem {
    evidence_id?: string;
    criterion: string;
    status: 'present' | 'absent' | 'unclear';
    matched_text: string;
    source_name: string;
    confidence: number;
}

export interface GapChecklistItem {
    criterion: string;
    status: 'present' | 'absent' | 'unclear';
    rationale: string;
    evidence_refs: string[];
    conflict_detected: boolean;
    confidence_level: 'normal' | 'caution' | 'escalate';
}

export interface CaseSummary {
    summary_text: string;
    evidence_refs: string[];
}

export const fetchCaseEvidence = async (caseId: string): Promise<{evidence_items: EvidenceItem[]}> => {
    // In reality, this calls the orchestration API
    // return fetch(`/api/cases/${caseId}/evidence`).then(res => res.json());
    return {
        evidence_items: [
            { criterion: "Test", status: "present", matched_text: "Sample", source_name: "test.pdf", confidence: 0.95 }
        ]
    };
};

export const fetchCaseGapAnalysis = async (caseId: string): Promise<{checklist: GapChecklistItem[]}> => {
    // return fetch(`/api/cases/${caseId}/gap-analysis`).then(res => res.json());
    return {
        checklist: [
            {
                criterion: "Patient has documented condition X.",
                status: "present",
                rationale: "Found in notes.",
                evidence_refs: ["123"],
                conflict_detected: false,
                confidence_level: "normal"
            },
            {
                criterion: "Patient tried alternative Y.",
                status: "unclear",
                rationale: "Contradictory evidence detected.",
                evidence_refs: ["124", "125"],
                conflict_detected: true,
                confidence_level: "escalate"
            }
        ]
    };
};
