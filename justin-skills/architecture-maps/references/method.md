# Architecture mapping method (reference)

Source: "Architecture Mapping Method" (Microsoft-style method, made vendor-neutral here).
Read the section you need. Section numbers match the source.

## Contents
1. Architecture question and inputs
2. The ten views (what each answers and shows)
3. Diagram conventions
4. Architecture decision records
5. Well-Architected review → see frameworks.md
6. Register: risks, assumptions, dependencies, open questions
7. Validation (14 questions, reviewer roles)
8. Maintenance (metadata, statuses, update triggers)
9. Package order

---

## 1. Architecture question and inputs

Start from the stakeholder question, not from product icons. Fill in:

> For **[audience]**, this architecture map explains **[system or decision]** so they can
> determine **[question the map must answer]**, within **[scope and constraints]**.

Inputs to record (spec `inputs`):
- **Business outcome** – what the solution must enable.
- **Actors** – who or what starts each interaction.
- **Scope** – in and out.
- **Constraints** – security, network, data, cost, latency, platform.
- **Quality targets** – availability, recovery (RTO/RPO), performance, scale.
- **Decisions** – choices that need approval.
- **Unknowns** – what still needs investigation.

## 2. The ten views

Each view answers one question. Make only the views that the architecture question needs.

| # | View (`type`) | Question it answers | Show |
|---|---|---|---|
| 2.1 | Executive outcome (`executive_outcome`) | What business outcome does it support? | Problem, users, outcome, major capabilities, value, key constraints, success measures. **No technical detail.** |
| 2.2 | System context (`system_context`) | What is the system, who uses it, what does it connect to? | Users, external actors, the solution as **one bounded box**, external apps/platforms, major inputs/outputs, organizational or trust boundaries, systems of record. Simple enough for business and technical readers together. |
| 2.3 | Logical capability (`logical_capability`) | What capabilities must it contain? | Layers: experience; identity and access; API and integration; orchestration and business logic; AI/agents/automation; data and knowledge; security and governance; monitoring and operations. **Functional names, not products** (e.g. "User authentication", "Knowledge retrieval", "Policy enforcement", "Audit logging"). |
| 2.4 | Technology (`technology`) | Which technologies implement each capability? | Map every capability to a selected service. **Every service ties to a requirement or ADR** – never pick a service only because it is familiar. |
| 2.5 | Network and deployment (`network_deployment`) | Where does everything run; what are the network and security boundaries? | Tenant/org, management groups/folders, subscriptions/accounts/projects, resource groups, regions, zones, VNets/VPCs, subnets, NSGs/security groups, firewalls, gateways, public and private endpoints, private DNS, PaaS resources, on-prem links, external systems, prod/test/dev, primary and recovery regions. **Draw each service where it really is.** A PaaS service reached by private endpoint sits **outside** the subnet; only the private endpoint sits in the subnet. |
| 2.6 | Identity and security (`identity_security`) | How is access controlled and the system protected? | Human, application and managed identities; authentication flow; where authorization is enforced; roles; privileged access; secrets and keys; trust boundaries; public vs private access; encryption boundaries; security monitoring; audit records; data-classification boundaries; admin access paths. **Label each trust boundary and each authorization enforcement point.** |
| 2.7 | Data and knowledge flow (`data_flow`) | Where does information start, move, get processed and stay? | Sources, systems of record, ingestion, processing, transformation, storage, retrieval, search indexes, AI grounding sources, outputs, logging, archive, retention, deletion. For each flow record: data type, direction, protocol, classification, owner, storage location, retention, encryption (spec `data_flows`). |
| 2.8 | Sequence (`sequence`) | What happens in one critical end-to-end scenario? | One map per critical scenario. Number every interaction; label direction and protocol. Typical: authenticate → token → request → validate identity and authorization → orchestrate → call internal service with managed identity → retrieve authorized data → process / ground AI → filter by policy → respond → telemetry → audit record. |
| 2.9 | Observability and operations (`operations`) | How is it deployed, monitored, supported and recovered? | Repos, build and deploy pipelines, IaC, config management, app telemetry, platform metrics, logs, tracing, dashboards, alerts, incident management, backup, restore, DR, admin tools, support ownership. **Say which component makes telemetry, where it is stored, and who responds to an alert.** |
| 2.10 | Resilience and recovery (`resilience`) | What happens when a component, zone, region or dependency fails? | Redundancy, zone and region distribution, load balancing, health probes, retries, circuit breakers, queues, replication, backup locations, failover paths, recovery sequence, external dependencies, single points of failure. Record (spec `targets`): RTO, RPO, expected availability, failover trigger, failover owner, restore procedure, failure-test method. |

## 3. Diagram conventions

**Arrows.** Every connection states one relationship: request, response, data, event, command, admin action, replication, telemetry. Use one-way arrows. Not `App ↔ DB`; instead `App → DB: SQL query` and `DB → App: query result`. This shows who starts the interaction.

**Labels.** Label every non-obvious relationship with protocol or interaction type: HTTPS/REST, OAuth 2.0, OpenID Connect, SQL/TLS, Private Link, managed identity, AMQP, events, logs and metrics, replication.

**Boundaries.** A box is a boundary only when it means one: tenant, subscription/account/project, resource group, region, zone, VNet/VPC, subnet, trust boundary, application boundary, environment, external system. No decorative containers that a reader could take for a technical boundary.

**Icons.** Use the vendor's official architecture icons. Put the product name next to the icon. Do not crop, flip, rotate, distort or reshape. **Never use one product's icon for a different product** – use a plain labelled box. Keep icon sizes the same. Icons show chosen technology; they are not decoration.

**Consistency.** Same colors, fonts, icon sizes, line weights and types, arrowheads, border styles, naming and capitalization, and boundary styles across the whole set. (archmap.py enforces this; do not hand-style.)

## 4. Architecture decision records

The diagram shows what connects; the ADR explains why. For every major decision record:
decision, requirement, options considered, selected option, reason, tradeoffs, risks, assumptions, evidence required, decision owner, decision date, review date.

Example rows:

| Decision | Requirement | Options | Selected | Tradeoff |
|---|---|---|---|---|
| Compute model | Variable demand, low ops overhead | VMs, Kubernetes, PaaS web, serverless containers | Serverless containers | Less infra control for simpler ops |
| Connectivity | No public access to data services | Public firewall rules, service endpoints, private endpoints | Private endpoints | More DNS and network complexity |
| App identity | No stored credentials | Secrets, certificates, managed/workload identity | Managed identity | Needs compatible services |
| Integration | Decouple long-running work | Direct calls, queues, events | Queue-based messaging | Eventual consistency |

## 6. Register

Keep a separate register. Per item: item, type, description, architecture impact, owner, target resolution date, validation method, status.
Types: Risk, Assumption, Dependency, Constraint, Open question, Decision required, Proof of concept, Security review, Compliance review.
**Never show an assumption as a confirmed fact.** Mark the node `assumption: true` (drawn dashed, "(assumed)") and add a register item.

## 7. Validation

Reviewer roles: business stakeholders, solution architects, application engineers, data engineers, identity specialists, network engineers, security reviewers, governance, operations, support owners, compliance, cost owners.

The 14 questions (spec `validation`; answer each yes / partial / no with evidence):
1. Does the architecture answer the intended stakeholder question?
2. Is the scope clear?
3. Are all users, systems, and dependencies represented?
4. Are the arrows directional and labeled?
5. Are trust boundaries visible?
6. Is the deployment model technically accurate?
7. Are identity and authorization flows clear?
8. Are data flows and classifications documented?
9. Are failure paths represented?
10. Are monitoring and support responsibilities clear?
11. Are major decisions supported by requirements?
12. Are risks, assumptions, and unknowns visible?
13. Does the architecture reflect the actual implementation?
14. What evidence is still needed before approval?

## 8. Maintenance

Every map carries: title, workload name, diagram type, environment, version, date updated, owner, reviewers, status, assumptions, related decisions, related implementation docs. (archmap.py prints the title block on each page from `meta`.)

Statuses: Draft, Proposed, Under review, Approved, Implemented, Superseded, Retired.

Update when: a major service changes; security boundaries change; data flows change; a new integration appears; deployment topology changes; availability requirements change; the implementation differs from the approved design. Retire maps that no longer match the solution or answer a live question.

## 9. Package order

1 Executive outcome · 2 System context · 3 Logical capabilities · 4 Technology · 5 Identity and security · 6 Network and deployment · 7 Data and knowledge flows · 8 Critical sequences · 9 Observability and operations · 10 Resilience and recovery · 11 Decisions · 12 Register.

The maps communicate the design. The decisions explain the choices. The Well-Architected review tests whether those choices are defensible.
