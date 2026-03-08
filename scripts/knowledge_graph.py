#!/usr/bin/env python3
"""
Knowledge Graph — links deals, contacts, companies, interactions, and insights.

Builds a graph data structure from Pipedrive data, persists to knowledge/graph.json,
and provides analytics (industry clusters, warm intros, contact networks, deal similarity).

Usage:
  python3 scripts/knowledge_graph.py build               # Build from Pipedrive
  python3 scripts/knowledge_graph.py stats               # Graph statistics
  python3 scripts/knowledge_graph.py node <id>           # Show node details
  python3 scripts/knowledge_graph.py related <company>   # Related deals/contacts
  python3 scripts/knowledge_graph.py path <from> <to>    # Find path
  python3 scripts/knowledge_graph.py clusters            # Industry clusters
  python3 scripts/knowledge_graph.py warm-intro <company> # Warm introductions
  python3 scripts/knowledge_graph.py export              # Export to markdown
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import deque, defaultdict
from datetime import datetime, date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
EXPORT_FILE = WORKSPACE / "knowledge" / "GRAPH_EXPORT.md"
LOG_FILE = WORKSPACE / "logs" / "knowledge-graph.log"

TODAY = date.today()
NOW = datetime.now()

NODE_TYPES = {"DEAL", "CONTACT", "COMPANY", "INTERACTION", "INSIGHT", "TEMPLATE"}
EDGE_TYPES = {
    "BELONGS_TO", "CONTACTED_BY", "HAS_DEAL", "MENTIONED_IN",
    "RELATED_TO", "COMPETED_WITH", "REFERRED_BY", "USED_TEMPLATE",
}

SALES_STAGES = {
    7: ("Interested/Qualified", 1),
    8: ("Demo Scheduled", 2),
    28: ("Ongoing Discussion", 3),
    9: ("Proposal made", 4),
    10: ("Negotiation", 5),
    12: ("Pilot", 6),
    29: ("Contract Sent", 7),
    11: ("Invoice sent", 8),
}

ONBOARDING_STAGES = {
    16: ("Sales Action Needed", 1),
    15: ("Waiting for Customer", 2),
    17: ("1. Pulse Planned", 3),
    18: ("Probation Period", 4),
    19: ("Customers", 5),
    20: ("Test Only", 6),
    32: ("Not Converted", 7),
}


# ── ENV & API (same pattern as existing scripts) ─────

def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base, token, method, path, params=None, data=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < retry - 1:
                time.sleep(2 * (i + 1))
                continue
            raise
    return None


def paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        j = api_request(base, token, "GET", path, params=p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def glog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    try:
        if LOG_FILE.stat().st_size > 200_000:
            lines = LOG_FILE.read_text().splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    except OSError:
        pass


def days_ago(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (TODAY - d).days
    except (ValueError, TypeError):
        return 999


def get_stage_name(stage_id):
    if stage_id in SALES_STAGES:
        return SALES_STAGES[stage_id][0]
    if stage_id in ONBOARDING_STAGES:
        return ONBOARDING_STAGES[stage_id][0]
    return f"Stage {stage_id}"


def get_pipeline_name(stage_id):
    if stage_id in SALES_STAGES:
        return "Sales"
    if stage_id in ONBOARDING_STAGES:
        return "Onboarding"
    return "Other"


# ── KNOWLEDGE GRAPH ──────────────────────────────────

class KnowledgeGraph:
    """Graph stored as JSON adjacency list with typed edges."""

    def __init__(self, graph_path=None):
        self.path = graph_path or GRAPH_FILE
        self.nodes = {}   # {node_id: {type, id, properties, updated_at}}
        self.edges = []    # [{from_id, to_id, edge_type, properties}]
        self._adjacency = defaultdict(list)  # node_id -> [edge_index, ...]
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.nodes = data.get("nodes", {})
                self.edges = data.get("edges", [])
                self._rebuild_adjacency()
                return
            except (json.JSONDecodeError, OSError):
                pass
        self.nodes = {}
        self.edges = []
        self._adjacency = defaultdict(list)

    def _rebuild_adjacency(self):
        self._adjacency = defaultdict(list)
        for i, edge in enumerate(self.edges):
            self._adjacency[edge["from_id"]].append(i)
            self._adjacency[edge["to_id"]].append(i)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "nodes": self.nodes,
            "edges": self.edges,
            "meta": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "updated_at": NOW.isoformat(),
            },
        }
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def add_node(self, node_type, node_id, properties=None):
        node_id = str(node_id)
        self.nodes[node_id] = {
            "type": node_type,
            "id": node_id,
            "properties": properties or {},
            "updated_at": NOW.isoformat(),
        }

    def add_edge(self, from_id, to_id, edge_type, properties=None):
        from_id = str(from_id)
        to_id = str(to_id)
        # Deduplicate: don't add same edge twice
        for edge in self.edges:
            if (edge["from_id"] == from_id and edge["to_id"] == to_id
                    and edge["edge_type"] == edge_type):
                edge["properties"] = properties or edge.get("properties", {})
                return
        idx = len(self.edges)
        self.edges.append({
            "from_id": from_id,
            "to_id": to_id,
            "edge_type": edge_type,
            "properties": properties or {},
        })
        self._adjacency[from_id].append(idx)
        self._adjacency[to_id].append(idx)

    def get_node(self, node_id):
        node_id = str(node_id)
        node = self.nodes.get(node_id)
        if not node:
            return None
        edges = []
        for idx in self._adjacency.get(node_id, []):
            edges.append(self.edges[idx])
        return {**node, "edges": edges}

    def get_neighbors(self, node_id, edge_type=None):
        node_id = str(node_id)
        neighbors = []
        for idx in self._adjacency.get(node_id, []):
            edge = self.edges[idx]
            if edge_type and edge["edge_type"] != edge_type:
                continue
            other_id = edge["to_id"] if edge["from_id"] == node_id else edge["from_id"]
            other_node = self.nodes.get(other_id)
            if other_node:
                neighbors.append({**other_node, "edge": edge})
        return neighbors

    def query(self, node_type=None, properties=None):
        """Find nodes matching type and/or property criteria."""
        properties = properties or {}
        results = []
        for node in self.nodes.values():
            if node_type and node["type"] != node_type:
                continue
            match = True
            for k, v in properties.items():
                node_val = node.get("properties", {}).get(k, "")
                if isinstance(v, str) and isinstance(node_val, str):
                    if v.lower() not in node_val.lower():
                        match = False
                        break
                elif node_val != v:
                    match = False
                    break
            if match:
                results.append(node)
        return results

    def path_between(self, from_id, to_id):
        """BFS shortest path between two nodes. Returns list of node IDs."""
        from_id = str(from_id)
        to_id = str(to_id)
        if from_id not in self.nodes or to_id not in self.nodes:
            return None
        if from_id == to_id:
            return [from_id]

        visited = {from_id}
        queue = deque([(from_id, [from_id])])

        while queue:
            current, path = queue.popleft()
            for idx in self._adjacency.get(current, []):
                edge = self.edges[idx]
                neighbor = edge["to_id"] if edge["from_id"] == current else edge["from_id"]
                if neighbor in visited:
                    continue
                new_path = path + [neighbor]
                if neighbor == to_id:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))

        return None  # no path found

    def related_deals(self, company_id):
        """All deals for a company (via BELONGS_TO / HAS_DEAL edges)."""
        company_id = str(company_id)
        deals = []
        for n in self.get_neighbors(company_id):
            if n["type"] == "DEAL":
                deals.append(n)
            # Also check transitive: contact -> deal
            if n["type"] == "CONTACT":
                for cn in self.get_neighbors(n["id"]):
                    if cn["type"] == "DEAL" and cn["id"] not in [d["id"] for d in deals]:
                        deals.append(cn)
        return deals

    def contact_network(self, contact_id):
        """All people/companies connected to a contact."""
        contact_id = str(contact_id)
        network = {"companies": [], "deals": [], "contacts": []}
        seen = set()

        for n in self.get_neighbors(contact_id):
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            if n["type"] == "COMPANY":
                network["companies"].append(n)
                # Also get other contacts at this company
                for cn in self.get_neighbors(n["id"]):
                    if cn["type"] == "CONTACT" and cn["id"] != contact_id and cn["id"] not in seen:
                        seen.add(cn["id"])
                        network["contacts"].append(cn)
            elif n["type"] == "DEAL":
                network["deals"].append(n)
            elif n["type"] == "CONTACT":
                network["contacts"].append(n)

        return network

    def node_count_by_type(self):
        counts = defaultdict(int)
        for node in self.nodes.values():
            counts[node["type"]] += 1
        return dict(counts)

    def edge_count_by_type(self):
        counts = defaultdict(int)
        for edge in self.edges:
            counts[edge["edge_type"]] += 1
        return dict(counts)

    def density(self):
        n = len(self.nodes)
        if n < 2:
            return 0.0
        max_edges = n * (n - 1)  # directed graph max
        return len(self.edges) / max_edges if max_edges > 0 else 0.0


# ── PIPEDRIVE GRAPH BUILDER ──────────────────────────

class PipedriveGraphBuilder:
    """Pull data from Pipedrive API to populate graph."""

    def __init__(self, base_url, api_token, graph=None):
        self.base = base_url
        self.token = api_token
        self.graph = graph or KnowledgeGraph()

    def build(self):
        """Full build: orgs, persons, deals, then wire edges."""
        print("Building knowledge graph from Pipedrive...")

        orgs = self._fetch_organizations()
        persons = self._fetch_persons()
        deals = self._fetch_deals()
        activities = self._fetch_activities()

        self._build_org_nodes(orgs)
        self._build_contact_nodes(persons)
        self._build_deal_nodes(deals)
        self._build_activity_nodes(activities)

        self._wire_deal_org_edges(deals)
        self._wire_deal_contact_edges(deals)
        self._wire_contact_org_edges(persons)
        self._wire_activity_edges(activities)

        self.graph.save()
        glog(f"Graph built: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
        print(f"Graph built: {len(self.graph.nodes)} nodes, {len(self.graph.edges)} edges")
        print(f"Saved to {self.graph.path}")
        return self.graph

    def _fetch_organizations(self):
        print("  Fetching organizations...")
        orgs = paged_get(self.base, self.token, "/api/v1/organizations")
        print(f"  -> {len(orgs)} organizations")
        glog(f"Fetched {len(orgs)} organizations")
        return orgs

    def _fetch_persons(self):
        print("  Fetching contacts (persons)...")
        persons = paged_get(self.base, self.token, "/api/v1/persons")
        print(f"  -> {len(persons)} contacts")
        glog(f"Fetched {len(persons)} persons")
        return persons

    def _fetch_deals(self):
        print("  Fetching deals (all statuses)...")
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "all_not_deleted"})
        print(f"  -> {len(deals)} deals")
        glog(f"Fetched {len(deals)} deals")
        return deals

    def _fetch_activities(self):
        print("  Fetching activities...")
        activities = paged_get(self.base, self.token, "/api/v1/activities")
        print(f"  -> {len(activities)} activities")
        glog(f"Fetched {len(activities)} activities")
        return activities

    def _build_org_nodes(self, orgs):
        for org in orgs:
            org_id = org.get("id")
            if not org_id:
                continue
            address = org.get("address", "") or ""
            self.graph.add_node("COMPANY", f"org_{org_id}", {
                "name": org.get("name", ""),
                "pipedrive_id": org_id,
                "address": address,
                "people_count": org.get("people_count", 0),
                "open_deals_count": org.get("open_deals_count", 0),
                "won_deals_count": org.get("won_deals_count", 0),
                "lost_deals_count": org.get("lost_deals_count", 0),
                "closed_deals_count": org.get("closed_deals_count", 0),
                "activities_count": org.get("activities_count", 0),
                "add_time": (org.get("add_time") or "")[:10],
                "label": org.get("label") or "",
                "country": org.get("country_code", "") or "",
            })

    def _build_contact_nodes(self, persons):
        for person in persons:
            pid = person.get("id")
            if not pid:
                continue
            phones = person.get("phone", [])
            phone_list = [p.get("value", "") for p in phones if isinstance(p, dict) and p.get("value")]
            emails = person.get("email", [])
            email_list = [e.get("value", "") for e in emails if isinstance(e, dict) and e.get("value")]

            org = person.get("org_id")
            org_name = ""
            org_id = None
            if isinstance(org, dict):
                org_name = org.get("name", "")
                org_id = org.get("value") or org.get("id")
            elif org:
                org_id = org

            self.graph.add_node("CONTACT", f"person_{pid}", {
                "name": person.get("name", ""),
                "pipedrive_id": pid,
                "phones": phone_list,
                "emails": email_list,
                "org_name": org_name,
                "org_id": org_id,
                "open_deals_count": person.get("open_deals_count", 0),
                "won_deals_count": person.get("won_deals_count", 0),
                "activities_count": person.get("activities_count", 0),
                "add_time": (person.get("add_time") or "")[:10],
                "label": person.get("label") or "",
            })

    def _build_deal_nodes(self, deals):
        for deal in deals:
            did = deal.get("id")
            if not did:
                continue
            stage_id = deal.get("stage_id")
            owner = deal.get("user_id")
            owner_name = ""
            if isinstance(owner, dict):
                owner_name = owner.get("name", "")

            self.graph.add_node("DEAL", f"deal_{did}", {
                "title": deal.get("title", ""),
                "pipedrive_id": did,
                "value": deal.get("value") or 0,
                "currency": deal.get("currency", "CZK"),
                "status": deal.get("status", ""),
                "stage_id": stage_id,
                "stage_name": get_stage_name(stage_id) if stage_id else "",
                "pipeline": get_pipeline_name(stage_id) if stage_id else "",
                "owner": owner_name,
                "org_name": deal.get("org_name") or "",
                "person_name": deal.get("person_name") or "",
                "add_time": (deal.get("add_time") or "")[:10],
                "won_time": (deal.get("won_time") or "")[:10] if deal.get("won_time") else "",
                "lost_time": (deal.get("lost_time") or "")[:10] if deal.get("lost_time") else "",
                "close_time": (deal.get("close_time") or "")[:10] if deal.get("close_time") else "",
                "last_activity_date": deal.get("last_activity_date") or "",
                "next_activity_date": deal.get("next_activity_date") or "",
                "activities_count": deal.get("activities_count") or 0,
                "email_messages_count": deal.get("email_messages_count") or 0,
                "expected_close_date": deal.get("expected_close_date") or "",
                "lost_reason": deal.get("lost_reason") or "",
            })

    def _build_activity_nodes(self, activities):
        for act in activities:
            aid = act.get("id")
            if not aid:
                continue
            self.graph.add_node("INTERACTION", f"activity_{aid}", {
                "pipedrive_id": aid,
                "type": act.get("type", ""),
                "subject": act.get("subject", ""),
                "done": act.get("done", False),
                "due_date": act.get("due_date", ""),
                "deal_id": act.get("deal_id"),
                "person_id": act.get("person_id"),
                "org_id": act.get("org_id"),
                "add_time": (act.get("add_time") or "")[:10],
                "note": (act.get("note") or "")[:200],
            })

    def _wire_deal_org_edges(self, deals):
        for deal in deals:
            did = deal.get("id")
            org_id = deal.get("org_id")
            if isinstance(org_id, dict):
                org_id = org_id.get("value") or org_id.get("id")
            if did and org_id:
                self.graph.add_edge(f"deal_{did}", f"org_{org_id}", "BELONGS_TO", {
                    "relationship": "deal_at_company",
                })
                self.graph.add_edge(f"org_{org_id}", f"deal_{did}", "HAS_DEAL", {
                    "status": deal.get("status", ""),
                })

    def _wire_deal_contact_edges(self, deals):
        for deal in deals:
            did = deal.get("id")
            person_id = deal.get("person_id")
            if isinstance(person_id, dict):
                person_id = person_id.get("value") or person_id.get("id")
            if did and person_id:
                self.graph.add_edge(f"deal_{did}", f"person_{person_id}", "CONTACTED_BY", {
                    "relationship": "deal_contact",
                })

    def _wire_contact_org_edges(self, persons):
        for person in persons:
            pid = person.get("id")
            org = person.get("org_id")
            org_id = None
            if isinstance(org, dict):
                org_id = org.get("value") or org.get("id")
            elif org:
                org_id = org
            if pid and org_id:
                self.graph.add_edge(f"person_{pid}", f"org_{org_id}", "BELONGS_TO", {
                    "relationship": "works_at",
                })

    def _wire_activity_edges(self, activities):
        for act in activities:
            aid = act.get("id")
            if not aid:
                continue
            deal_id = act.get("deal_id")
            person_id = act.get("person_id")
            org_id = act.get("org_id")

            if deal_id:
                self.graph.add_edge(f"activity_{aid}", f"deal_{deal_id}", "MENTIONED_IN", {
                    "type": act.get("type", ""),
                })
            if person_id:
                self.graph.add_edge(f"activity_{aid}", f"person_{person_id}", "RELATED_TO", {
                    "type": act.get("type", ""),
                })
            if org_id:
                self.graph.add_edge(f"activity_{aid}", f"org_{org_id}", "RELATED_TO", {
                    "type": act.get("type", ""),
                })


# ── GRAPH ANALYTICS ──────────────────────────────────

class GraphAnalytics:
    """Analytical queries over the knowledge graph."""

    def __init__(self, graph):
        self.graph = graph

    def industry_clusters(self):
        """Group companies by label/country, show deal stats per cluster."""
        companies = self.graph.query(node_type="COMPANY")
        clusters = defaultdict(lambda: {
            "companies": [], "total_deals": 0, "open_deals": 0,
            "won_deals": 0, "lost_deals": 0, "total_value": 0,
        })

        for company in companies:
            props = company.get("properties", {})
            label = props.get("label") or "Unlabeled"
            country = props.get("country") or "Unknown"
            cluster_key = f"{label}"
            if country and country != "Unknown":
                cluster_key = f"{label} ({country})"

            c = clusters[cluster_key]
            c["companies"].append(props.get("name", "?"))
            c["open_deals"] += props.get("open_deals_count", 0)
            c["won_deals"] += props.get("won_deals_count", 0)
            c["lost_deals"] += props.get("lost_deals_count", 0)
            c["total_deals"] += (
                props.get("open_deals_count", 0) +
                props.get("won_deals_count", 0) +
                props.get("lost_deals_count", 0) +
                props.get("closed_deals_count", 0)
            )

            # Sum deal values via graph edges
            deals = self.graph.related_deals(company["id"])
            for d in deals:
                c["total_value"] += d.get("properties", {}).get("value", 0)

        return dict(clusters)

    def warm_introductions(self, target_company):
        """Find people who might introduce you to target_company.

        Looks for contacts connected to target AND to companies you already have deals with.
        """
        target_id = self._find_company_id(target_company)
        if not target_id:
            return {"error": f"Company not found: {target_company}", "intros": []}

        # Get contacts at target company
        target_contacts = self.graph.get_neighbors(target_id, edge_type="BELONGS_TO")
        target_contact_ids = set()
        for n in target_contacts:
            if n["type"] == "CONTACT":
                target_contact_ids.add(n["id"])

        # Find any contacts who are connected to both target and another company with deals
        intros = []
        won_companies = set()
        for node in self.graph.nodes.values():
            if node["type"] == "COMPANY" and node["id"] != target_id:
                props = node.get("properties", {})
                if props.get("won_deals_count", 0) > 0 or props.get("open_deals_count", 0) > 0:
                    won_companies.add(node["id"])

        # For each contact at the target, check if they also connect to a won company
        for contact_id in target_contact_ids:
            contact_network = self.graph.get_neighbors(contact_id)
            for neighbor in contact_network:
                if neighbor["type"] == "COMPANY" and neighbor["id"] in won_companies:
                    contact_node = self.graph.nodes.get(contact_id, {})
                    intros.append({
                        "contact": contact_node.get("properties", {}).get("name", "?"),
                        "contact_id": contact_id,
                        "via_company": neighbor.get("properties", {}).get("name", "?"),
                        "via_company_id": neighbor["id"],
                        "target_company": target_company,
                    })

        # Also check: contacts at won companies who might know people at target
        # (reverse lookup: shared contacts between companies)
        for won_cid in won_companies:
            won_contacts = self.graph.get_neighbors(won_cid, edge_type="BELONGS_TO")
            for wc in won_contacts:
                if wc["type"] != "CONTACT":
                    continue
                # Check if this contact has any path to target
                path = self.graph.path_between(wc["id"], target_id)
                if path and len(path) <= 4:  # Within 3 hops
                    wc_props = wc.get("properties", {})
                    won_props = self.graph.nodes.get(won_cid, {}).get("properties", {})
                    already = any(i["contact_id"] == wc["id"] for i in intros)
                    if not already:
                        intros.append({
                            "contact": wc_props.get("name", "?"),
                            "contact_id": wc["id"],
                            "via_company": won_props.get("name", "?"),
                            "via_company_id": won_cid,
                            "target_company": target_company,
                            "path_length": len(path),
                        })

        intros.sort(key=lambda x: x.get("path_length", 2))
        return {"target": target_company, "target_id": target_id, "intros": intros}

    def most_connected_contacts(self, top_n=20):
        """Contacts with the most relationships."""
        contacts = self.graph.query(node_type="CONTACT")
        scored = []
        for contact in contacts:
            neighbors = self.graph.get_neighbors(contact["id"])
            companies = [n for n in neighbors if n["type"] == "COMPANY"]
            deals = [n for n in neighbors if n["type"] == "DEAL"]
            interactions = [n for n in neighbors if n["type"] == "INTERACTION"]
            scored.append({
                "id": contact["id"],
                "name": contact.get("properties", {}).get("name", "?"),
                "org": contact.get("properties", {}).get("org_name", ""),
                "total_connections": len(neighbors),
                "companies": len(companies),
                "deals": len(deals),
                "interactions": len(interactions),
                "emails": contact.get("properties", {}).get("emails", []),
            })
        scored.sort(key=lambda x: x["total_connections"], reverse=True)
        return scored[:top_n]

    def deal_similarity(self, deal_id):
        """Find similar past deals based on: same company, same stage progression,
        similar value, same pipeline."""
        deal_id = str(deal_id)
        # Normalize deal_id to include prefix if needed
        if not deal_id.startswith("deal_"):
            deal_id = f"deal_{deal_id}"

        target = self.graph.get_node(deal_id)
        if not target:
            return {"error": f"Deal not found: {deal_id}", "similar": []}

        target_props = target.get("properties", {})
        target_value = target_props.get("value", 0)
        target_pipeline = target_props.get("pipeline", "")
        target_org = target_props.get("org_name", "")

        all_deals = self.graph.query(node_type="DEAL")
        scored = []

        for deal in all_deals:
            if deal["id"] == deal_id:
                continue
            props = deal.get("properties", {})
            score = 0
            reasons = []

            # Same organization
            if props.get("org_name") and props["org_name"] == target_org:
                score += 30
                reasons.append("same_org")

            # Same pipeline
            if props.get("pipeline") == target_pipeline:
                score += 15
                reasons.append("same_pipeline")

            # Similar value (within 50%)
            deal_value = props.get("value", 0)
            if target_value > 0 and deal_value > 0:
                ratio = min(deal_value, target_value) / max(deal_value, target_value)
                if ratio >= 0.5:
                    score += int(20 * ratio)
                    reasons.append(f"similar_value({ratio:.0%})")

            # Has outcome data (won/lost) -> more useful for learning
            if props.get("status") in ("won", "lost"):
                score += 10
                reasons.append(f"outcome:{props['status']}")

            # Connected via shared contacts
            target_contacts = set(
                n["id"] for n in self.graph.get_neighbors(deal_id) if n["type"] == "CONTACT"
            )
            deal_contacts = set(
                n["id"] for n in self.graph.get_neighbors(deal["id"]) if n["type"] == "CONTACT"
            )
            shared = target_contacts & deal_contacts
            if shared:
                score += 15 * len(shared)
                reasons.append(f"shared_contacts:{len(shared)}")

            if score > 0:
                scored.append({
                    "id": deal["id"],
                    "title": props.get("title", ""),
                    "org": props.get("org_name", ""),
                    "value": deal_value,
                    "status": props.get("status", ""),
                    "similarity_score": score,
                    "reasons": reasons,
                })

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        return {
            "deal": target_props.get("title", ""),
            "deal_id": deal_id,
            "similar": scored[:15],
        }

    def revenue_by_cluster(self):
        """Total revenue/pipeline per industry cluster."""
        clusters = self.industry_clusters()
        revenue = {}
        for cluster_name, data in clusters.items():
            revenue[cluster_name] = {
                "company_count": len(data["companies"]),
                "total_deals": data["total_deals"],
                "open_deals": data["open_deals"],
                "won_deals": data["won_deals"],
                "total_value": data["total_value"],
                "companies": data["companies"][:10],  # cap list for display
            }
        # Sort by total value descending
        return dict(sorted(revenue.items(), key=lambda x: x[1]["total_value"], reverse=True))

    def _find_company_id(self, name_or_id):
        """Find company node ID by name (fuzzy) or by ID."""
        name_or_id = str(name_or_id)
        # Direct ID match
        if name_or_id.startswith("org_") and name_or_id in self.graph.nodes:
            return name_or_id
        if f"org_{name_or_id}" in self.graph.nodes:
            return f"org_{name_or_id}"
        # Name search
        for node_id, node in self.graph.nodes.items():
            if node["type"] == "COMPANY":
                node_name = node.get("properties", {}).get("name", "")
                if name_or_id.lower() in node_name.lower():
                    return node_id
        return None


# ── GRAPH VISUALIZATION ──────────────────────────────

class GraphVisualization:
    """Terminal-printable and markdown export."""

    def __init__(self, graph, analytics=None):
        self.graph = graph
        self.analytics = analytics or GraphAnalytics(graph)

    def terminal_stats(self):
        lines = []
        lines.append("=" * 60)
        lines.append("  KNOWLEDGE GRAPH STATISTICS")
        lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 60)

        lines.append(f"\n  Total nodes: {len(self.graph.nodes)}")
        lines.append(f"  Total edges: {len(self.graph.edges)}")
        lines.append(f"  Graph density: {self.graph.density():.6f}")

        lines.append("\n  NODES BY TYPE")
        lines.append("  " + "-" * 40)
        for ntype, count in sorted(self.graph.node_count_by_type().items(), key=lambda x: -x[1]):
            bar = "#" * min(count, 40)
            lines.append(f"  {ntype:<15} {count:>6}  {bar}")

        lines.append("\n  EDGES BY TYPE")
        lines.append("  " + "-" * 40)
        for etype, count in sorted(self.graph.edge_count_by_type().items(), key=lambda x: -x[1]):
            bar = "#" * min(count // 2, 40)
            lines.append(f"  {etype:<15} {count:>6}  {bar}")

        # Top connected contacts
        top_contacts = self.analytics.most_connected_contacts(10)
        if top_contacts:
            lines.append("\n  TOP CONNECTED CONTACTS")
            lines.append("  " + "-" * 55)
            lines.append(f"  {'Name':<25} {'Org':<20} {'Conn':>5} {'Deals':>5}")
            lines.append("  " + "-" * 55)
            for c in top_contacts:
                lines.append(
                    f"  {c['name'][:24]:<25} {c['org'][:19]:<20} "
                    f"{c['total_connections']:>5} {c['deals']:>5}"
                )

        lines.append("\n" + "=" * 60)
        return "\n".join(lines)

    def node_detail(self, node_id):
        """Pretty-print node details and connections."""
        node = self.graph.get_node(node_id)
        if not node:
            # Try with common prefixes
            for prefix in ["deal_", "org_", "person_", "activity_"]:
                node = self.graph.get_node(f"{prefix}{node_id}")
                if node:
                    break
        if not node:
            return f"Node not found: {node_id}"

        lines = []
        lines.append(f"\n  NODE: {node['id']}")
        lines.append(f"  Type: {node['type']}")
        lines.append("  " + "-" * 50)

        props = node.get("properties", {})
        for k, v in sorted(props.items()):
            if v and v != "" and v != 0 and v != []:
                val_str = str(v)[:60]
                lines.append(f"  {k:<25} {val_str}")

        edges = node.get("edges", [])
        if edges:
            lines.append(f"\n  CONNECTIONS ({len(edges)})")
            lines.append("  " + "-" * 50)
            for edge in edges:
                other_id = edge["to_id"] if edge["from_id"] == node["id"] else edge["from_id"]
                other = self.graph.nodes.get(other_id, {})
                other_name = other.get("properties", {}).get("name", "") or \
                             other.get("properties", {}).get("title", "") or \
                             other.get("properties", {}).get("subject", "") or other_id
                direction = "->" if edge["from_id"] == node["id"] else "<-"
                lines.append(
                    f"  {direction} [{edge['edge_type']}] {other.get('type', '?')}: "
                    f"{str(other_name)[:40]}"
                )

        return "\n".join(lines)

    def export_markdown(self):
        """Export full graph to markdown."""
        lines = []
        lines.append("# Knowledge Graph Export")
        lines.append(f"\n> Generated: {NOW.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"> Nodes: {len(self.graph.nodes)} | Edges: {len(self.graph.edges)}")
        lines.append(f"> Density: {self.graph.density():.6f}")
        lines.append("")

        # Stats summary
        lines.append("## Node Summary")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for ntype, count in sorted(self.graph.node_count_by_type().items(), key=lambda x: -x[1]):
            lines.append(f"| {ntype} | {count} |")
        lines.append("")

        lines.append("## Edge Summary")
        lines.append("")
        lines.append("| Type | Count |")
        lines.append("|------|-------|")
        for etype, count in sorted(self.graph.edge_count_by_type().items(), key=lambda x: -x[1]):
            lines.append(f"| {etype} | {count} |")
        lines.append("")

        # Companies with deals
        companies = self.graph.query(node_type="COMPANY")
        companies_with_deals = [
            c for c in companies
            if c.get("properties", {}).get("open_deals_count", 0) > 0
               or c.get("properties", {}).get("won_deals_count", 0) > 0
        ]
        companies_with_deals.sort(
            key=lambda x: x.get("properties", {}).get("open_deals_count", 0), reverse=True
        )

        if companies_with_deals:
            lines.append("## Companies with Deals")
            lines.append("")
            lines.append("| Company | Open | Won | Lost | Contacts |")
            lines.append("|---------|------|-----|------|----------|")
            for c in companies_with_deals[:30]:
                p = c.get("properties", {})
                lines.append(
                    f"| {p.get('name', '?')[:30]} | {p.get('open_deals_count', 0)} "
                    f"| {p.get('won_deals_count', 0)} | {p.get('lost_deals_count', 0)} "
                    f"| {p.get('people_count', 0)} |"
                )
            lines.append("")

        # Open deals
        open_deals = [
            d for d in self.graph.query(node_type="DEAL")
            if d.get("properties", {}).get("status") == "open"
        ]
        open_deals.sort(key=lambda x: x.get("properties", {}).get("value", 0), reverse=True)

        if open_deals:
            lines.append("## Open Deals")
            lines.append("")
            lines.append("| Deal | Company | Value | Stage | Pipeline |")
            lines.append("|------|---------|-------|-------|----------|")
            for d in open_deals[:30]:
                p = d.get("properties", {})
                val = f"{p.get('value', 0):,.0f} {p.get('currency', '')}" if p.get("value") else "-"
                lines.append(
                    f"| {p.get('title', '?')[:30]} | {p.get('org_name', '')[:20]} "
                    f"| {val} | {p.get('stage_name', '')} | {p.get('pipeline', '')} |"
                )
            lines.append("")

        # Top contacts
        top = self.analytics.most_connected_contacts(15)
        if top:
            lines.append("## Most Connected Contacts")
            lines.append("")
            lines.append("| Name | Organization | Connections | Deals |")
            lines.append("|------|-------------|-------------|-------|")
            for c in top:
                lines.append(
                    f"| {c['name'][:25]} | {c['org'][:20]} "
                    f"| {c['total_connections']} | {c['deals']} |"
                )
            lines.append("")

        # Revenue clusters
        rev = self.analytics.revenue_by_cluster()
        if rev:
            lines.append("## Revenue by Cluster")
            lines.append("")
            lines.append("| Cluster | Companies | Deals | Open | Won | Value |")
            lines.append("|---------|-----------|-------|------|-----|-------|")
            for cluster_name, data in list(rev.items())[:20]:
                val = f"{data['total_value']:,.0f}" if data["total_value"] else "-"
                lines.append(
                    f"| {cluster_name[:25]} | {data['company_count']} "
                    f"| {data['total_deals']} | {data['open_deals']} "
                    f"| {data['won_deals']} | {val} |"
                )
            lines.append("")

        report = "\n".join(lines)
        EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXPORT_FILE.write_text(report)
        return report


# ── CLI ──────────────────────────────────────────────

def main():
    try:
        env = load_env(ENV_PATH)
    except FileNotFoundError:
        print(f"ERROR: Env file not found: {ENV_PATH}")
        sys.exit(1)

    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "build":
        graph = KnowledgeGraph()
        builder = PipedriveGraphBuilder(base, token, graph)
        builder.build()

    elif cmd == "stats":
        graph = KnowledgeGraph()
        analytics = GraphAnalytics(graph)
        viz = GraphVisualization(graph, analytics)
        print(viz.terminal_stats())

    elif cmd == "node":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py node <id>")
            print("Examples: knowledge_graph.py node deal_123  |  node org_456  |  node person_789")
            sys.exit(1)
        graph = KnowledgeGraph()
        viz = GraphVisualization(graph)
        print(viz.node_detail(sys.argv[2]))

    elif cmd == "related":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py related <company_name_or_id>")
            sys.exit(1)
        graph = KnowledgeGraph()
        analytics = GraphAnalytics(graph)
        company_name = " ".join(sys.argv[2:])
        company_id = analytics._find_company_id(company_name)
        if not company_id:
            print(f"Company not found: {company_name}")
            # Show available companies
            companies = graph.query(node_type="COMPANY")
            if companies:
                print("\nAvailable companies:")
                for c in sorted(companies, key=lambda x: x.get("properties", {}).get("name", ""))[:20]:
                    print(f"  {c['id']}: {c.get('properties', {}).get('name', '?')}")
            sys.exit(1)

        company_node = graph.get_node(company_id)
        company_name = company_node.get("properties", {}).get("name", "?") if company_node else "?"
        deals = graph.related_deals(company_id)
        contacts = graph.get_neighbors(company_id, edge_type="BELONGS_TO")
        contact_list = [n for n in contacts if n["type"] == "CONTACT"]

        print(f"\n  RELATED TO: {company_name} ({company_id})")
        print("  " + "=" * 50)

        if deals:
            print(f"\n  DEALS ({len(deals)})")
            print("  " + "-" * 50)
            for d in deals:
                p = d.get("properties", {})
                val = f"{p.get('value', 0):,.0f}" if p.get("value") else "-"
                print(f"  [{d['id']}] {p.get('title', '?')[:35]} | {p.get('status', '?')} | {val} {p.get('currency', '')}")
        else:
            print("\n  No deals found for this company.")

        if contact_list:
            print(f"\n  CONTACTS ({len(contact_list)})")
            print("  " + "-" * 50)
            for c in contact_list:
                p = c.get("properties", {})
                emails = ", ".join(p.get("emails", [])[:2])
                print(f"  [{c['id']}] {p.get('name', '?')[:30]} | {emails[:40]}")
        else:
            print("\n  No contacts found for this company.")

    elif cmd == "path":
        if len(sys.argv) < 4:
            print("Usage: knowledge_graph.py path <from_id> <to_id>")
            sys.exit(1)
        graph = KnowledgeGraph()
        viz = GraphVisualization(graph)
        from_id = sys.argv[2]
        to_id = sys.argv[3]

        # Try to resolve IDs with common prefixes
        def resolve_id(raw):
            if raw in graph.nodes:
                return raw
            for prefix in ["deal_", "org_", "person_", "activity_"]:
                if f"{prefix}{raw}" in graph.nodes:
                    return f"{prefix}{raw}"
            # Try name search for companies
            analytics = GraphAnalytics(graph)
            cid = analytics._find_company_id(raw)
            if cid:
                return cid
            return raw

        from_id = resolve_id(from_id)
        to_id = resolve_id(to_id)

        path = graph.path_between(from_id, to_id)
        if path is None:
            print(f"No path found between {from_id} and {to_id}")
            sys.exit(0)

        print(f"\n  PATH: {from_id} -> {to_id} ({len(path) - 1} hops)")
        print("  " + "=" * 50)
        for i, node_id in enumerate(path):
            node = graph.nodes.get(node_id, {})
            props = node.get("properties", {})
            name = props.get("name", "") or props.get("title", "") or props.get("subject", "") or node_id
            ntype = node.get("type", "?")
            prefix = "  " if i == 0 else "  -> "

            # Find edge type to next node
            edge_label = ""
            if i < len(path) - 1:
                next_id = path[i + 1]
                for edge in graph.edges:
                    if ((edge["from_id"] == node_id and edge["to_id"] == next_id) or
                            (edge["from_id"] == next_id and edge["to_id"] == node_id)):
                        edge_label = f" --[{edge['edge_type']}]--"
                        break

            print(f"{prefix}[{ntype}] {name}{edge_label}")

    elif cmd == "clusters":
        graph = KnowledgeGraph()
        analytics = GraphAnalytics(graph)
        clusters = analytics.industry_clusters()

        if not clusters:
            print("No clusters found. Run 'build' first.")
            sys.exit(0)

        print(f"\n  INDUSTRY CLUSTERS ({len(clusters)})")
        print("  " + "=" * 60)

        sorted_clusters = sorted(clusters.items(), key=lambda x: x[1]["total_deals"], reverse=True)
        for name, data in sorted_clusters:
            if data["total_deals"] == 0 and len(data["companies"]) < 2:
                continue
            print(f"\n  {name}")
            print(f"  Companies: {len(data['companies'])} | Deals: {data['total_deals']} "
                  f"(Open: {data['open_deals']}, Won: {data['won_deals']})")
            if data["total_value"]:
                print(f"  Pipeline value: {data['total_value']:,.0f}")
            if data["companies"]:
                print(f"  -> {', '.join(data['companies'][:8])}")

    elif cmd == "warm-intro":
        if len(sys.argv) < 3:
            print("Usage: knowledge_graph.py warm-intro <company_name>")
            sys.exit(1)
        graph = KnowledgeGraph()
        analytics = GraphAnalytics(graph)
        target = " ".join(sys.argv[2:])
        result = analytics.warm_introductions(target)

        if result.get("error"):
            print(f"ERROR: {result['error']}")
            # Show available companies
            companies = graph.query(node_type="COMPANY")
            if companies:
                print("\nAvailable companies:")
                for c in sorted(companies, key=lambda x: x.get("properties", {}).get("name", ""))[:20]:
                    print(f"  {c.get('properties', {}).get('name', '?')}")
            sys.exit(1)

        intros = result.get("intros", [])
        print(f"\n  WARM INTRODUCTIONS TO: {target}")
        print("  " + "=" * 55)

        if not intros:
            print("\n  No warm introduction paths found.")
            print("  This company may not share contacts with your existing network.")
        else:
            print(f"\n  Found {len(intros)} potential introduction paths:")
            print("  " + "-" * 55)
            for intro in intros:
                hops = intro.get("path_length", 2)
                print(f"  {intro['contact']}")
                print(f"    via: {intro['via_company']} ({hops - 1} hop{'s' if hops > 2 else ''})")
                print()

    elif cmd == "export":
        graph = KnowledgeGraph()
        analytics = GraphAnalytics(graph)
        viz = GraphVisualization(graph, analytics)
        report = viz.export_markdown()
        print(f"Exported to {EXPORT_FILE}")
        print(f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
