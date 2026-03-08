#!/usr/bin/env python3
"""
Referral Network Analyzer — Find warm introduction paths
==========================================================
Uses the knowledge graph to find warm introduction paths between contacts.
BFS pathfinding with relationship strength scoring.

Identifies:
- Mutual connections between contacts
- Company alumni networks
- Industry peer connections
- Multi-hop introduction chains

Usage:
  python3 scripts/referral_network.py find <target_company>    # Find paths to company
  python3 scripts/referral_network.py suggest <deal_id>        # Suggest referrals for deal
  python3 scripts/referral_network.py network                  # Show full network stats
  python3 scripts/referral_network.py strongest                # Show strongest connections
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path
from collections import defaultdict, deque

WORKSPACE = Path(__file__).resolve().parents[1]
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
LOG_FILE = WORKSPACE / "logs" / "referral-network.log"
REFERRALS_FILE = WORKSPACE / "knowledge" / "referral-suggestions.json"
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"


def rlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def load_graph():
    """Load knowledge graph."""
    try:
        if GRAPH_FILE.exists():
            return json.loads(GRAPH_FILE.read_text())
    except (json.JSONDecodeError, OSError) as e:
        rlog(f"Failed to load graph: {e}", "ERROR")
    return None


class ReferralNetwork:
    """Analyze and find referral paths in the knowledge graph."""

    def __init__(self, graph_data):
        self.nodes = {}
        self.edges = defaultdict(list)
        self.contacts_by_company = defaultdict(list)
        self.companies_by_industry = defaultdict(list)

        if graph_data:
            nodes_raw = graph_data.get("nodes", [])
            if isinstance(nodes_raw, dict):
                for nid, node in nodes_raw.items():
                    if isinstance(node, dict):
                        node.setdefault("id", nid)
                        self.nodes[nid] = node
            else:
                for node in nodes_raw:
                    self.nodes[node["id"]] = node

            for edge in graph_data.get("edges", []):
                src, tgt = edge.get("source"), edge.get("target")
                etype = edge.get("type", "related")
                weight = edge.get("weight", 1.0)
                self.edges[src].append({"target": tgt, "type": etype, "weight": weight})
                self.edges[tgt].append({"target": src, "type": etype, "weight": weight})

            # Index contacts by company
            for nid, node in self.nodes.items():
                if node.get("type") == "contact":
                    comp_id = node.get("company_id")
                    if comp_id:
                        self.contacts_by_company[str(comp_id)].append(nid)

                if node.get("type") == "company":
                    industry = node.get("industry", "unknown")
                    self.companies_by_industry[industry].append(nid)

    def bfs_paths(self, start_id, end_id, max_depth=4):
        """Find all paths between two nodes using BFS."""
        if start_id not in self.nodes or end_id not in self.nodes:
            return []

        queue = deque([(start_id, [start_id])])
        visited_paths = []

        while queue:
            current, path = queue.popleft()

            if len(path) > max_depth:
                continue

            if current == end_id and len(path) > 1:
                visited_paths.append(path)
                continue

            for edge in self.edges.get(current, []):
                next_node = edge["target"]
                if next_node not in path:  # avoid cycles
                    queue.append((next_node, path + [next_node]))

        return visited_paths

    def score_path(self, path):
        """Score a referral path based on relationship strength."""
        if len(path) < 2:
            return 0

        score = 100.0
        # Penalty for each hop
        score -= (len(path) - 2) * 15

        # Bonus/penalty based on edge types
        for i in range(len(path) - 1):
            edges = self.edges.get(path[i], [])
            for e in edges:
                if e["target"] == path[i + 1]:
                    weight = e.get("weight", 1.0)
                    etype = e.get("type", "related")

                    # Strong connections
                    if etype in ("works_at", "manages"):
                        score += 10
                    elif etype in ("contacted", "met"):
                        score += 5 * weight
                    elif etype == "deal":
                        score += 8
                    break

        # Bonus if intermediaries are contacts (not just companies)
        for nid in path[1:-1]:
            node = self.nodes.get(nid, {})
            if node.get("type") == "contact":
                score += 5
                # Extra bonus for senior titles
                title = node.get("title", "").lower()
                if any(t in title for t in ["ceo", "cto", "vp", "director", "head"]):
                    score += 10

        return max(0, min(100, score))

    def find_paths_to_company(self, target_company_name, max_results=10):
        """Find referral paths to a target company."""
        # Find target company node
        target_ids = []
        for nid, node in self.nodes.items():
            if node.get("type") == "company":
                name = node.get("name", "").lower()
                if target_company_name.lower() in name:
                    target_ids.append(nid)

        if not target_ids:
            return []

        # Find contacts at target company
        target_contacts = []
        for tid in target_ids:
            target_contacts.extend(self.contacts_by_company.get(str(tid), []))
            # Also check edges
            for edge in self.edges.get(tid, []):
                tgt_node = self.nodes.get(edge["target"], {})
                if tgt_node.get("type") == "contact":
                    target_contacts.append(edge["target"])

        # Find all our "known" contacts (those with activity history)
        our_contacts = []
        for nid, node in self.nodes.items():
            if node.get("type") == "contact":
                # Has activity edges or is in our deals
                edges = self.edges.get(nid, [])
                if any(e.get("type") in ("activity", "deal", "contacted") for e in edges):
                    our_contacts.append(nid)

        if not our_contacts:
            # Fallback: use all contacts not at target company
            our_contacts = [nid for nid, n in self.nodes.items()
                          if n.get("type") == "contact" and nid not in target_contacts]

        # Find paths
        all_paths = []
        seen_pairs = set()

        for start in our_contacts[:50]:  # limit search space
            for end in (target_contacts or target_ids)[:10]:
                pair = (start, end)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                paths = self.bfs_paths(start, end, max_depth=4)
                for p in paths:
                    score = self.score_path(p)
                    all_paths.append({"path": p, "score": score})

        # Sort by score and deduplicate
        all_paths.sort(key=lambda x: x["score"], reverse=True)
        return all_paths[:max_results]

    def suggest_for_deal(self, deal_id):
        """Suggest referral paths for a specific deal."""
        # Find deal node
        deal_node_id = None
        for nid, node in self.nodes.items():
            if node.get("type") == "deal" and str(node.get("deal_id", "")) == str(deal_id):
                deal_node_id = nid
                break

        if not deal_node_id:
            # Try to find company from deal edges
            return []

        # Get company connected to this deal
        company_name = None
        for edge in self.edges.get(deal_node_id, []):
            target = self.nodes.get(edge["target"], {})
            if target.get("type") == "company":
                company_name = target.get("name")
                break

        if not company_name:
            return []

        return self.find_paths_to_company(company_name)

    def get_industry_peers(self, company_name):
        """Find companies in the same industry."""
        # Find company
        target = None
        for nid, node in self.nodes.items():
            if node.get("type") == "company" and company_name.lower() in node.get("name", "").lower():
                target = node
                break

        if not target:
            return []

        industry = target.get("industry", "unknown")
        peers = []
        for nid in self.companies_by_industry.get(industry, []):
            node = self.nodes[nid]
            if node.get("name") != target.get("name"):
                peers.append({
                    "id": nid,
                    "name": node.get("name"),
                    "industry": industry,
                    "contacts": len(self.contacts_by_company.get(str(nid), [])),
                })

        return sorted(peers, key=lambda x: x["contacts"], reverse=True)

    def network_stats(self):
        """Get network statistics."""
        type_counts = defaultdict(int)
        for node in self.nodes.values():
            type_counts[node.get("type", "unknown")] += 1

        edge_type_counts = defaultdict(int)
        total_edges = 0
        for src, edges in self.edges.items():
            for e in edges:
                edge_type_counts[e.get("type", "unknown")] += 1
                total_edges += 1

        # Connectivity
        connected_contacts = sum(1 for nid, node in self.nodes.items()
                                if node.get("type") == "contact" and len(self.edges.get(nid, [])) > 0)
        total_contacts = type_counts.get("contact", 0)

        # Hub detection (nodes with most connections)
        hubs = []
        for nid in self.nodes:
            degree = len(self.edges.get(nid, []))
            if degree > 5:
                hubs.append({"id": nid, "name": self.nodes[nid].get("name", "?"), "degree": degree,
                            "type": self.nodes[nid].get("type", "?")})
        hubs.sort(key=lambda x: x["degree"], reverse=True)

        return {
            "total_nodes": len(self.nodes),
            "total_edges": total_edges // 2,  # undirected
            "node_types": dict(type_counts),
            "edge_types": {k: v // 2 for k, v in edge_type_counts.items()},
            "contact_connectivity": f"{connected_contacts}/{total_contacts}",
            "industries": len(self.companies_by_industry),
            "top_hubs": hubs[:10],
        }

    def strongest_connections(self, top_n=20):
        """Find the strongest connections in the network."""
        connections = []
        seen = set()

        for src, edges in self.edges.items():
            for e in edges:
                pair = tuple(sorted([src, e["target"]]))
                if pair in seen:
                    continue
                seen.add(pair)

                src_node = self.nodes.get(src, {})
                tgt_node = self.nodes.get(e["target"], {})

                strength = e.get("weight", 1.0)
                # Boost for contact-to-company (employment)
                if e.get("type") == "works_at":
                    strength += 2
                elif e.get("type") == "deal":
                    strength += 1.5

                connections.append({
                    "from": src_node.get("name", src),
                    "from_type": src_node.get("type", "?"),
                    "to": tgt_node.get("name", e["target"]),
                    "to_type": tgt_node.get("type", "?"),
                    "type": e.get("type", "related"),
                    "strength": strength,
                })

        connections.sort(key=lambda x: x["strength"], reverse=True)
        return connections[:top_n]


def format_path(network, path):
    """Format a path for display."""
    parts = []
    for nid in path:
        node = network.nodes.get(nid, {})
        name = node.get("name", nid)
        ntype = node.get("type", "?")
        title = node.get("title", "")
        if title:
            parts.append(f"{name} ({title}, {ntype})")
        else:
            parts.append(f"{name} ({ntype})")
    return " → ".join(parts)


def cmd_find(target):
    """Find referral paths to a company."""
    graph = load_graph()
    if not graph:
        print("  No knowledge graph found. Run: python3 scripts/knowledge_graph.py build")
        return

    network = ReferralNetwork(graph)
    paths = network.find_paths_to_company(target)

    print(f"\n  Referral Paths to '{target}'")
    print(f"  {'='*50}\n")

    if not paths:
        print(f"  No paths found to '{target}'")
        print(f"  Try building the graph first: python3 scripts/knowledge_graph.py build\n")
        return

    for i, p in enumerate(paths, 1):
        score = p["score"]
        color = "\033[0;32m" if score >= 70 else "\033[0;33m" if score >= 40 else "\033[0;31m"
        path_str = format_path(network, p["path"])
        print(f"  {color}{score:3.0f}\033[0m  {path_str}")

    # Also show industry peers
    peers = network.get_industry_peers(target)
    if peers:
        print(f"\n  Industry Peers ({len(peers)}):")
        for p in peers[:5]:
            print(f"    {p['name']} — {p['contacts']} contacts")

    # Save suggestions
    suggestions = {
        "target": target,
        "generated": datetime.now().isoformat(),
        "paths": [{"nodes": p["path"], "score": p["score"]} for p in paths],
    }
    saved = json.loads(REFERRALS_FILE.read_text()) if REFERRALS_FILE.exists() else {"suggestions": []}
    saved["suggestions"].append(suggestions)
    saved["suggestions"] = saved["suggestions"][-50:]  # keep last 50
    REFERRALS_FILE.write_text(json.dumps(saved, indent=2))

    print()


def cmd_suggest(deal_id):
    """Suggest referrals for a deal."""
    graph = load_graph()
    if not graph:
        print("  No knowledge graph found.")
        return

    network = ReferralNetwork(graph)
    paths = network.suggest_for_deal(deal_id)

    print(f"\n  Referral Suggestions for Deal #{deal_id}")
    print(f"  {'='*50}\n")

    if not paths:
        print(f"  No referral paths found for deal #{deal_id}")
        return

    for i, p in enumerate(paths, 1):
        score = p["score"]
        path_str = format_path(network, p["path"])
        print(f"  {score:3.0f}  {path_str}")
    print()


def cmd_network():
    """Show network stats."""
    graph = load_graph()
    if not graph:
        print("  No knowledge graph found.")
        return

    network = ReferralNetwork(graph)
    stats = network.network_stats()

    print(f"\n{'='*50}")
    print(f"  Referral Network Statistics")
    print(f"{'='*50}\n")

    print(f"  Nodes: {stats['total_nodes']}")
    print(f"  Edges: {stats['total_edges']}")
    print(f"  Contact Connectivity: {stats['contact_connectivity']}")
    print(f"  Industries: {stats['industries']}")

    print(f"\n  Node Types:")
    for t, c in sorted(stats["node_types"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {t}: {c}")

    print(f"\n  Edge Types:")
    for t, c in sorted(stats["edge_types"].items(), key=lambda x: x[1], reverse=True):
        print(f"    {t}: {c}")

    if stats["top_hubs"]:
        print(f"\n  Top Hubs (most connected):")
        for h in stats["top_hubs"][:10]:
            print(f"    {h['name']} ({h['type']}) — {h['degree']} connections")

    print()


def cmd_strongest():
    """Show strongest connections."""
    graph = load_graph()
    if not graph:
        print("  No knowledge graph found.")
        return

    network = ReferralNetwork(graph)
    connections = network.strongest_connections(20)

    print(f"\n  Strongest Network Connections")
    print(f"  {'='*50}\n")

    for c in connections:
        strength_bar = "#" * int(c["strength"] * 3)
        print(f"  {strength_bar:15s}  {c['from']} ({c['from_type']}) —[{c['type']}]→ {c['to']} ({c['to_type']})")

    print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "network"

    if cmd == "find" and len(sys.argv) > 2:
        cmd_find(" ".join(sys.argv[2:]))
    elif cmd == "suggest" and len(sys.argv) > 2:
        cmd_suggest(sys.argv[2])
    elif cmd == "network":
        cmd_network()
    elif cmd == "strongest":
        cmd_strongest()
    else:
        print("Usage: referral_network.py [find <company>|suggest <deal_id>|network|strongest]")


if __name__ == "__main__":
    main()
