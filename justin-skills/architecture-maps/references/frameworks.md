# Well-Architected review: pick the framework by platform

Put the framework name in `waf.framework`; one key per pillar, each a list of `{q, a, status}` with status `met | gap | unknown`.
Answer from the design and the user's inputs. If the design cannot answer, status `unknown` and add a register item. Never mark `met` without evidence in the design.

| Platform | Framework (`waf.framework`) | Pillar keys |
|---|---|---|
| Azure / Microsoft cloud | Azure Well-Architected Framework | reliability, security, cost_optimization, operational_excellence, performance_efficiency |
| AWS | AWS Well-Architected Framework | operational_excellence, security, reliability, performance_efficiency, cost_optimization, sustainability |
| Google Cloud | Google Cloud Well-Architected Framework | operational_excellence, security_privacy_compliance, reliability, cost_optimization, performance_optimization, sustainability |
| Mixed, on-prem, SaaS-only | Method default (5 pillars) | reliability, security, cost_optimization, operational_excellence, performance_efficiency |

For multi-cloud, use the framework of the platform that hosts most of the workload and say so in `waf.framework`; note cross-cloud gaps under security and reliability.

## Core questions (from the method; use for every framework, map to the matching pillar)

**Reliability** – What happens when each dependency fails? Single points of failure? RTO and RPO? Spread across zones? Needs multiple regions? How is data backed up and restored? Has failure behavior been tested? What if an external dependency is down? Can it degrade gracefully?

**Security** (Google: security, privacy and compliance) – Where are the trust boundaries? How does every actor authenticate? Where is authorization enforced? Can managed/workload identities replace stored credentials? Which endpoints are public? How are secrets protected? How is data encrypted? How is privileged access controlled? Which security events are audited? How are vulnerabilities found and fixed? How is access revoked?

**Cost optimization** – Which components drive cost? How does cost grow with use? Can resources scale down or to zero? Are premium features tied to real requirements? Is redundancy right for the workload's criticality? Are non-prod environments optimized? Are data-retention costs understood? Who owns ongoing cost management?

**Operational excellence** – Who owns each component? What telemetry is produced? How are deployments automated? How are config changes managed? Which alerts need action? What is the rollback process? Are runbooks available? How are incidents escalated? How are architecture changes documented? How is health communicated?

**Performance efficiency** (Google: performance optimization) – Latency targets? Throughput targets? Where are the synchronous dependencies? What should be cached? Which parts scale independently? What are the tested limits? Where could back pressure occur? How are regressions detected? What happens at peak? What should run asynchronously?

**Sustainability** (AWS, Google only) – Is capacity sized to real demand (scale to zero, right-sizing)? Is the region choice informed by carbon data where allowed? Are data retention and replication no larger than needed? Are batch jobs scheduled to flexible times?

Keep each pillar to the questions that matter for this workload (typically 3–6). A review with 40 "unknown" rows helps no one; a review with 15 sharp rows and register items does.
