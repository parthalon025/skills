# Spec format (architecture.json)

One JSON file drives every output. `assets/example_spec.json` is a complete small example – copy it and edit.

```jsonc
{
  "meta": {
    "workload": "Name",              // used in file names
    "version": "0.1",                // semver; new version = new files
    "status": "Draft",               // Draft|Proposed|Under review|Approved|Implemented|Superseded|Retired
    "date": "YYYY-MM-DD", "owner": "...", "reviewers": ["..."], "environment": "Production",
    "question": {"audience": "...", "system": "...", "determine": "...", "scope": "..."}
  },
  "inputs": {"business_outcome": "", "actors": [], "scope_in": [], "scope_out": [],
             "constraints": [], "quality_targets": [], "decisions": [], "unknowns": []},
  "views": [ /* see below */ ],
  "data_flows": [{"flow","data_type","from","to","protocol","classification","owner","storage","retention","encryption"}],
  "decisions":  [{"id","decision","requirement","options":[],"selected","reason","tradeoffs","risks",
                  "assumptions","evidence","owner","date","review_date"}],
  "waf": {"framework": "...", "<pillar_key>": [{"q","a","status":"met|gap|unknown"}]},   // frameworks.md
  "register":   [{"id","type","description","impact","owner","target_date","validation","status"}],
  "validation": [{"n":1,"question":"...","result":"yes|partial|no","evidence":"..."}],
  "review":     {"source":"file or description reviewed","summary":"...",
                 "findings":[{"id","severity":"high|medium|low","rule","location","finding","fix"}]},
  "related":    ["links to implementation docs"],
  "changelog":  [{"version","date","change"}]
}
```

Unknown values: write `"TBD"` and add a register item. Do not invent owners, dates or targets.

## Box-and-arrow views (all types except `sequence`)

```jsonc
{
  "id": "network", "type": "network_deployment", "title": "Network and deployment",
  "question": "Where does everything run ...?",
  "boundaries": [
    {"id": "sub", "label": "sub-prod", "kind": "subscription"},
    {"id": "vnet", "label": "vnet-prod 10.0.0.0/16", "kind": "vnet", "parent": "sub"}
  ],
  "nodes": [
    {"id": "api", "label": "Orders API", "icon": "azure:container-apps", "kind": "compute",
     "in": "vnet", "col": 1, "row": 0,
     "detail": "optional 2nd line", "requirement": "R3 / ADR-01",   // requirement: mandatory in technology views
     "assumption": false, "vnet_injected": false}
  ],
  "edges": [
    {"from": "api", "to": "db", "label": "Read orders", "type": "request", "protocol": "SQL/TLS", "step": 3}
  ],
  "notes": ["short facts that do not fit on the canvas"],
  "targets": {"rto": "4 h", "rpo": "15 min", ...}   // resilience view only
}
```

**Boundary kinds:** tenant, organization, management_group, account, subscription, project, resource_group, region, availability_zone, vnet (also VPC), subnet, trust, application, environment, external, on_premises, layer (capability-map layers only).
Nest with `parent`. A boundary is sized automatically to fit its members.

**Node kinds:** actor, service, paas, compute, data, external, capability, outcome, network, security, endpoint, note.
`kind: paas` inside a subnet is an error unless `vnet_injected: true` (method 2.5).

**Edge types:** request, response, data, event, command, admin, replication, telemetry. One direction per edge. `step` adds a number.

**Icons:** `python3 scripts/archmap.py icons aws:` lists keys. Prefixes: `azure:` (Azure, Entra, Power Platform), `aws:`, `gcp:`, `generic:` (user, users, database, storage, queue, server, browser, mobile, document, cloud, external-saas, service, function, llm, agent, gateway, firewall, key-store, monitoring, identity-provider, on-prem).
No icon for a product (e.g. SharePoint, Salesforce, Okta)? Omit `icon` or use a `generic:` shape and name the product in `label`. Never borrow another product's icon.

## Layout

Grid placement: `col`, `row` (cell 240 × 170 px). Nodes may also take explicit `x`, `y`.
- Leave **one empty column or row** between sibling boundaries, more for deep nesting (each nesting level adds ~38 px of padding + header). `check` reports overlaps.
- Put request/response pairs between nodes at least **two columns apart** when labels are long. `check` warns when a label is longer than its edge.
- Flow left → right (actors on the left, systems of record on the right); control/admin top, data bottom.
- Keep a view to about 15 nodes. Split a bigger picture into two views with different questions.

## Sequence views

```jsonc
{
  "id": "seq-login", "type": "sequence", "title": "Sequence: user signs in and asks",
  "question": "What happens end to end when ...?",
  "participants": [{"id": "user", "label": "User browser"}, {"id": "api", "label": "API"}],
  "steps": [
    {"from": "user", "to": "api", "label": "POST /ask", "protocol": "HTTPS/REST"},
    {"from": "api", "to": "user", "label": "Answer", "protocol": "HTTPS", "type": "response"}
  ]
}
```
Steps are numbered in order. `protocol` is mandatory. Default `type` is request.

## Commands

```bash
python3 scripts/archmap.py check  spec.json             # rules; exit 1 on errors
python3 scripts/archmap.py build  spec.json --out DIR   # .drawio + .html + previews/*.png + spec copy
python3 scripts/archmap.py import diagram.drawio --out imported.json   # review / update mode
python3 scripts/archmap.py icons  gcp:
```
Output names: `<workload-slug>_architecture_<version>.drawio|.html|.spec.json|_previews/`. `build` refuses to overwrite: bump `meta.version` to publish a change.
