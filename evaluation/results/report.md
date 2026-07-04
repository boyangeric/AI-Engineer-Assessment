# Evaluation Report

| Query | Grounded | Citations valid | Token overlap | Judge: relevance | Judge: groundedness |
|---|---|---|---|---|---|
| What controls apply to API security? | True | True | 0.762 | 5/5 | 5/5 |
| How should sensitive data be protected in cloud systems? | True | True | 0.78 | 4/5 | 5/5 |
| Summarise the requirements for access control | True | True | 0.784 | 5/5 | 5/5 |
| What policies relate to logging and monitoring? | True | True | 0.828 | 5/5 | 5/5 |
| What is the best recipe for chocolate chip cookies? | False | True | 0.0 | 1/5 | 5/5 |

## Judge justifications

- **What controls apply to API security?** — All retrieved controls directly address core API security concerns (authentication/attribution, information-flow separation and filtering, allowed unauthenticated actions, and wireless access protections), and the final answer maps each claim to the corresponding control with only reasonable, supported examples.
- **How should sensitive data be protected in cloud systems?** — The retrieved controls directly support key protections (encryption at rest, media/data sanitization, dual authorization, separation of duties and sanitization on domain transfers) though they do not cover every aspect of cloud security (e.g., encryption in transit, key management, access logging), and every claim in the answer is traceable to one of the provided controls.
- **Summarise the requirements for access control** — All retrieved AC-3 control enhancements (MAC, DAC, RBAC, ABAC, and combined enforcement) directly address access-control requirements and each claim in the summary can be traced to the corresponding cited controls (AC-3(3), AC-3(4), AC-3(7), AC-3(13), AC-3(15)).
- **What policies relate to logging and monitoring?** — The retrieved controls (AU-6, AU-6(4), AU-6(5), AU-4, SI-4) directly address audit logging, centralized/integrated analysis, storage capacity, and system monitoring, and the final answer accurately paraphrases those controls with clear citations.
- **What is the best recipe for chocolate chip cookies?** — The retrieved NIST SP 800-53 security controls about rules of behavior and external system use are unrelated to baking, so declining to provide a recipe due to lack of relevant policy material was the correct response.
