# Security Requirements Checklist

**Feature**: `001-pa-evidence-assistant`
**Created**: 2026-07-20
**Checklist Type**: Security — Requirements Quality Validation
**Purpose**: Validate that security requirements in the spec, data model, and API contracts are complete, unambiguous, consistent, and measurable before implementation begins. These items test the *requirements*, not the implementation.
**Source documents**: spec.md (FR-001–006, FR-031–032, FR-058), data-model.md (users, refresh_tokens, audit_logs), contracts/auth.md, contracts/admin.md, contracts/nurse-review.md

---

## Requirement Completeness

- [ ] CHK001 - Are the JWT access-token expiry duration and the refresh-token validity window explicitly specified in the spec or contracts, not left as implementation-time decisions? [Completeness, Spec §FR-002, contracts/auth.md]
- [ ] CHK002 - Is the refresh-token rotation policy (old token revoked on use, new token issued) explicitly documented as a requirement — not just implied by the logout revocation rule? [Completeness, research.md §6]
- [ ] CHK003 - Are requirements defined for what happens when a refresh token is presented after it has already been rotated (i.e., replay of a consumed token) — is this treated as a security event requiring all tokens for that user to be revoked? [Gap, Spec §FR-006]
- [ ] CHK004 - Is a maximum session lifetime (i.e., total chained refresh window) specified, or is refresh permitted indefinitely as long as each individual token is used within 7 days? [Gap, research.md §6]
- [ ] CHK005 - Are requirements defined for the `argon2` password-hashing configuration parameters (time cost, memory cost, parallelism factor) — or is implementation left to pick defaults without a minimum standard? [Completeness, Spec §FR-005]
- [ ] CHK006 - Are requirements specified for how the argon2 configuration is surfaced to the secrets abstraction module so it can be changed centrally without editing multiple service files? [Completeness, Spec §FR-005, Constitution Principle XIII]
- [ ] CHK007 - Are requirements defined for the behavior of `/api/v1/auth/token` when a deactivated user (`is_active = FALSE`) attempts to log in — specifically, is the error response required to be indistinguishable from an invalid-credentials response (to avoid user-enumeration)? [Clarity, Spec §FR-056, contracts/auth.md]
- [ ] CHK008 - Is a requirement specified for rate-limiting or account-lockout on the `/api/v1/auth/token` endpoint to prevent brute-force attacks, or is this explicitly out of scope for v2? [Gap]
- [ ] CHK009 - Are requirements defined for logging failed authentication attempts (`user_login_failed` event) including the username supplied, timestamp, and source IP — and is the maximum retention or access pattern for this data specified? [Completeness, data-model.md §audit_logs]

---

## Requirement Clarity

- [ ] CHK010 - Is "short-lived access token" in FR-002 now consistently expressed as the concrete "15-minute expiry" value that was resolved in the clarification session — or does the spec still use the vague adjective in the normative FR text, creating an ambiguity between the Clarifications section and the requirement? [Clarity, Spec §FR-002, Spec §Clarifications]
- [ ] CHK011 - Is the phrase "memory-hard algorithm" in FR-005 sufficiently specific, or should the normative requirement name argon2 explicitly so that an implementer cannot substitute bcrypt or scrypt and still claim compliance? [Clarity, Spec §FR-005]
- [ ] CHK012 - Is "explicit role check" in FR-003 defined precisely enough to distinguish between (a) checking the role claim in the JWT locally and (b) re-querying the database for current role — given that a user whose role is changed after token issuance would retain their old role until token expiry? [Clarity, Spec §FR-003]
- [ ] CHK013 - Does the spec or contracts clearly state which HTTP status code is returned for an authenticated but insufficiently-privileged request — currently FR-003 says "403 Forbidden," but does this align with the 401/403 distinction consistently across all contract files? [Consistency, Spec §FR-003, contracts/*]

---

## Requirement Consistency

- [ ] CHK014 - Are the RBAC role-permission mappings in FR-004 consistent with every route's `Auth` line in the API contracts — specifically: does the policy upload route in contracts/policies.md explicitly document that intake and nurse roles receive 403, and does the admin.md contract enforce that all its endpoints are admin-only? [Consistency, Spec §FR-004, contracts/policies.md, contracts/admin.md]
- [ ] CHK015 - Is the nurse-review lock endpoint in contracts/nurse-review.md consistent with the spec's statement that "admin override" of a nurse lock is permitted — specifically, does FR-031 or the contract describe how an admin acquires or breaks a nurse's lock, or is this behavior only mentioned in the Edge Cases section without a corresponding FR? [Consistency, Spec §FR-031, Spec §Edge Cases]
- [ ] CHK016 - Are the `is_active = FALSE` deactivation requirements in FR-056 consistent with the `refresh_tokens` lifecycle — specifically, does the spec require that all refresh tokens for a deactivated user be revoked immediately on deactivation, or only that new logins are blocked? [Consistency, Spec §FR-056, data-model.md §refresh_tokens]
- [ ] CHK017 - Is the audit log's immutability requirement in FR-058 consistently reflected in all contract files — specifically, does the admin audit-log endpoint in contracts/admin.md explicitly note that no DELETE or PATCH endpoint exists, making the prohibition visible to API consumers? [Consistency, Spec §FR-058, contracts/admin.md]

---

## Acceptance Criteria Quality

- [ ] CHK018 - Is SC-010 ("unauthenticated request returns 401 within 200ms") measurable as stated — does it specify which clock (wall clock, service processing time) and whether the 200ms includes network round-trip or is a server-side processing budget? [Measurability, Spec §SC-010]
- [ ] CHK019 - Is there a measurable acceptance criterion covering RBAC correctness — for example, a statement that every protected route returns 403 to a correctly authenticated but wrong-role request within a defined latency bound — or is role enforcement only validated narratively? [Gap, Spec §SC-010]
- [ ] CHK020 - Is the 30-minute nurse lock auto-release criterion in SC-006 ("becomes claimable within 5 seconds") measurable end-to-end — does the spec define the mechanism (background sweep frequency) that must fire within those 5 seconds, so the tolerance window can be validated without ambiguity? [Measurability, Spec §SC-006, research.md §5]

---

## Scenario Coverage

- [ ] CHK021 - Are requirements defined for role change scenarios — if a nurse is promoted to admin between JWT issuance and token expiry, does the system rely on expiry-only for the role to take effect, or is there a requirement to revoke active tokens on role change? [Coverage, Gap]
- [ ] CHK022 - Is a requirement specified for the behavior when the same user logs in from two concurrent browser sessions — should both refresh tokens remain valid simultaneously, or should a new login invalidate prior sessions? [Coverage, Gap]
- [ ] CHK023 - Are requirements defined for the admin case-edit endpoint's behavior when the admin's own JWT expires mid-form — specifically, does the required comment prevent a partial save without a valid token, or is this left to generic session expiry handling? [Coverage, Spec §FR-053]
- [ ] CHK024 - Are security requirements specified for PDF upload — specifically, are there requirements that: (a) only files with a PDF MIME type and magic bytes are accepted, (b) file size is bounded, and (c) filenames are sanitized before being stored in the database? [Coverage, Gap, Spec §FR-010]

---

## Edge Case Coverage

- [ ] CHK025 - Does the spec define the behavior when a refresh token is presented after its `expires_at` has passed — is this treated identically to a revoked token (401) or does it return a distinct error distinguishing expiry from revocation? [Edge Case, Spec §FR-006, contracts/auth.md]
- [ ] CHK026 - Is there a requirement covering what happens when the `refresh_tokens` table has accumulated a large number of expired or revoked rows — is periodic cleanup (TTL sweep) in scope or is table growth unbounded? [Edge Case, Gap, data-model.md §refresh_tokens]
- [ ] CHK027 - Are requirements defined for the nurse heartbeat endpoint's behavior when the nurse's access token has expired mid-session — does the frontend's token-refresh interceptor guarantee the heartbeat reaches the server before the 30-minute lock window lapses? [Edge Case, Spec §FR-032, research.md §11]

---

## Dependencies & Assumptions

- [ ] CHK028 - Is the assumption that "15-minute blast radius on a leaked access token is acceptable for an internal tool" documented as an explicit architectural decision in the spec (it currently appears only in the Clarifications section and research.md) — should it be promoted to a normative constraint in FR-002 or FR-006 so it is visible to future reviewers? [Assumption, Spec §Clarifications, research.md §6]
- [ ] CHK029 - Are the secrets that the `src/core/secrets.py` abstraction module is responsible for protecting explicitly enumerated in the spec or plan — DB credentials, JWT signing key, Ollama endpoint, Qdrant host — so that an audit of the module's coverage is unambiguous? [Dependency, Constitution Principle XIII, plan.md §Technical Context]
