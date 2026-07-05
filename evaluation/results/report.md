# Evaluation Report

**Outcome checks passed: 5/5**

| Query | Semantic ranker exercised | Outcome correct | Grounded | Citations valid | Token overlap | Faithfulness | Judge: relevance | Judge: groundedness |
|---|---|---|---|---|---|---|---|---|
| What controls apply to API security? | True | True | True | True | 0.643 | 1.00 | 4/5 | 5/5 |
| How should sensitive data be protected in cloud systems? | True | True | True | True | 0.654 | 0.95 | 4/5 | 5/5 |
| Summarise the requirements for access control | True | True | True | True | 0.721 | 1.00 | 5/5 | 5/5 |
| What policies relate to logging and monitoring? | True | True | True | True | 0.757 | 1.00 | 5/5 | 5/5 |
| What is the best recipe for chocolate chip cookies? | False | True | False | N/A | 0.0 | - | 1/5 | 5/5 |

## Judge justifications

- **What controls apply to API security?** — The retrieved controls (encryption/TLS, auditing, and least-privilege design) are directly applicable to API security but are not comprehensive for all API-specific topics (e.g., auth/token management, rate limiting), so relevance is 4; the final answer sticks closely to and cites only those retrieved controls, so groundedness is 5.
- **How should sensitive data be protected in cloud systems?** — The retrieved controls (encryption at rest, least privilege, developer design for least privilege, separation of duties, plus an audit-related control) are directly relevant to protecting sensitive cloud data though they omit other important areas (e.g., encryption in transit, key management, tenant isolation), and the final answer sticks closely to and cites only the provided controls.
- **Summarise the requirements for access control** — The final answer directly reflects and cites the retrieved AC controls (least privilege, privileged account restriction, separation of duties, account usage conditions, and session termination) with no unsupported claims beyond those controls.
- **What policies relate to logging and monitoring?** — The retrieved controls (AU-6 and its enhancements, SI-4, and IR-4(14)) directly address audit/log review, centralized and integrated analysis, active system monitoring, and SOC responsibilities, and the final answer accurately summarizes those controls with claims traceable to the retrieved excerpts.
- **What is the best recipe for chocolate chip cookies?** — No security-policy controls were retrieved and the user’s question about a cooking recipe is unrelated to the indexed security policy corpus, so declining and redirecting to appropriate security topics was the correct behavior.
