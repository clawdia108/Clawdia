#!/usr/bin/env python3
"""
Knowledge Deduplication — Detect and merge duplicate contacts/companies
========================================================================
Scans the knowledge graph for duplicate entries using fuzzy matching.

Detection methods:
- Exact email match
- Fuzzy name matching (Levenshtein-like)
- Same company + similar title
- Similar company names / domains

Usage:
  python3 scripts/knowledge_dedup.py scan              # Report duplicates
  python3 scripts/knowledge_dedup.py merge              # Auto-merge detected dupes
  python3 scripts/knowledge_dedup.py stats              # Dedup statistics
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
DEDUP_LOG = WORKSPACE / "logs" / "dedup.log"
DEDUP_REPORT = WORKSPACE / "knowledge" / "dedup-report.json"


def dlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    DEDUP_LOG.parent.mkdir(exist_ok=True)
    with open(DEDUP_LOG, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def normalize(s):
    """Normalize string for comparison."""
    if not s:
        return ""
    return re.sub(r'\s+', ' ', s.lower().strip())


def similarity(a, b):
    """Simple similarity score between two strings (0-1)."""
    a, b = normalize(a), normalize(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    # Jaccard on character bigrams
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1)) if len(s) > 1 else {s}

    a_bi = bigrams(a)
    b_bi = bigrams(b)
    intersection = len(a_bi & b_bi)
    union = len(a_bi | b_bi)
    return intersection / union if union else 0.0


def extract_domain(email):
    """Extract domain from email."""
    if not email or "@" not in email:
        return ""
    return email.split("@")[1].lower()


class DuplicateDetector:
    """Detect duplicates in the knowledge graph."""

    def __init__(self, graph_data):
        self.contacts = []
        self.companies = []
        self.deals = []

        if not graph_data:
            return

        # Handle both list and dict node formats
        nodes_raw = graph_data.get("nodes", [])
        if isinstance(nodes_raw, dict):
            nodes_iter = nodes_raw.values()
        else:
            nodes_iter = nodes_raw

        for node in nodes_iter:
            if not isinstance(node, dict):
                continue
            # Flatten properties into node for easier access
            props = node.get("properties", {})
            flat = {**node, **props}
            flat["id"] = node.get("id", "")
            ntype = node.get("type", "").lower()
            if ntype == "contact":
                self.contacts.append(flat)
            elif ntype == "company":
                self.companies.append(flat)
            elif ntype == "deal":
                self.deals.append(flat)

        # Handle both list and dict edge formats
        edges_raw = graph_data.get("edges", [])
        if isinstance(edges_raw, dict):
            self.edges = list(edges_raw.values())
        elif isinstance(edges_raw, list):
            self.edges = edges_raw
        else:
            self.edges = []

    def find_duplicate_contacts(self, threshold=0.75):
        """Find duplicate contacts."""
        duplicates = []
        n = len(self.contacts)

        # Index by email
        by_email = defaultdict(list)
        for c in self.contacts:
            email = (c.get("email") or "").lower().strip()
            if email:
                by_email[email].append(c)

        # Exact email matches
        for email, contacts in by_email.items():
            if len(contacts) > 1:
                duplicates.append({
                    "type": "exact_email",
                    "confidence": 1.0,
                    "reason": f"Same email: {email}",
                    "nodes": [c["id"] for c in contacts],
                    "names": [c.get("name", "?") for c in contacts],
                })

        # Fuzzy name matching within same company (cheap — small groups)
        by_company = defaultdict(list)
        for c in self.contacts:
            comp = str(c.get("company_id", c.get("pipedrive_id", "none")))
            by_company[comp].append(c)

        for comp_id, contacts in by_company.items():
            if len(contacts) > 20:
                continue  # skip very large groups
            for i in range(len(contacts)):
                for j in range(i + 1, len(contacts)):
                    name_a = contacts[i].get("name", "")
                    name_b = contacts[j].get("name", "")
                    sim = similarity(name_a, name_b)
                    if sim >= threshold:
                        pair = tuple(sorted([contacts[i]["id"], contacts[j]["id"]]))
                        duplicates.append({
                            "type": "fuzzy_name_same_company",
                            "confidence": round(sim, 2),
                            "reason": f"Similar names at same company: '{name_a}' vs '{name_b}'",
                            "nodes": list(pair),
                            "names": [name_a, name_b],
                        })

        # Same name, different company (exact match only for speed)
        by_name = defaultdict(list)
        for c in self.contacts:
            norm = normalize(c.get("name", ""))
            if norm:
                by_name[norm].append(c)

        for name, contacts in by_name.items():
            if len(contacts) > 1:
                companies = set(str(c.get("company_id", "")) for c in contacts)
                if len(companies) > 1:
                    duplicates.append({
                        "type": "same_name_diff_company",
                        "confidence": 0.6,
                        "reason": f"Same name '{contacts[0].get('name', '?')}' at {len(companies)} companies (possible job change)",
                        "nodes": [c["id"] for c in contacts[:5]],
                        "names": [c.get("name", "?") for c in contacts[:5]],
                    })

        return duplicates

    def find_duplicate_companies(self, threshold=0.8):
        """Find duplicate companies."""
        duplicates = []

        # Index by domain
        by_domain = defaultdict(list)
        for c in self.companies:
            # Try to extract domain from name or website
            name = c.get("name", "")
            website = c.get("website", "")
            domain = ""
            if website:
                domain = re.sub(r'^https?://(?:www\.)?', '', website).split('/')[0].lower()
            if not domain and name:
                domain = re.sub(r'\s+', '', name.lower()) + ".com"
            if domain:
                by_domain[domain].append(c)

        for domain, companies in by_domain.items():
            if len(companies) > 1:
                duplicates.append({
                    "type": "same_domain",
                    "confidence": 0.9,
                    "reason": f"Same domain: {domain}",
                    "nodes": [c["id"] for c in companies],
                    "names": [c.get("name", "?") for c in companies],
                })

        # Fuzzy name matching — use bucket approach to avoid O(n^2)
        by_prefix = defaultdict(list)
        for c in self.companies:
            name = normalize(c.get("name", ""))
            if name:
                prefix = name[:3]  # bucket by first 3 chars
                by_prefix[prefix].append(c)

        for prefix, comps in by_prefix.items():
            if len(comps) > 20:
                continue  # skip very common prefixes
            for i in range(len(comps)):
                for j in range(i + 1, len(comps)):
                    name_a = comps[i].get("name", "")
                    name_b = comps[j].get("name", "")
                    sim = similarity(name_a, name_b)
                    if sim >= threshold:
                        pair = tuple(sorted([comps[i]["id"], comps[j]["id"]]))
                        duplicates.append({
                            "type": "fuzzy_name",
                            "confidence": round(sim, 2),
                            "reason": f"Similar names: '{name_a}' vs '{name_b}'",
                            "nodes": list(pair),
                            "names": [name_a, name_b],
                        })

        return duplicates

    def scan_all(self):
        """Run full deduplication scan."""
        contact_dupes = self.find_duplicate_contacts()
        company_dupes = self.find_duplicate_companies()

        return {
            "timestamp": datetime.now().isoformat(),
            "contact_duplicates": len(contact_dupes),
            "company_duplicates": len(company_dupes),
            "contacts": contact_dupes,
            "companies": company_dupes,
            "total_contacts": len(self.contacts),
            "total_companies": len(self.companies),
        }


class DuplicateMerger:
    """Merge duplicate nodes in the knowledge graph."""

    def __init__(self, graph_data):
        self.graph = graph_data or {"nodes": [], "edges": []}

    def merge_nodes(self, keep_id, remove_ids):
        """Merge multiple nodes into one, keeping the most data."""
        keep_node = None
        remove_nodes = []

        for node in self.graph["nodes"]:
            if node["id"] == keep_id:
                keep_node = node
            elif node["id"] in remove_ids:
                remove_nodes.append(node)

        if not keep_node:
            return False

        # Merge data: keep non-empty values from removed nodes
        for rm_node in remove_nodes:
            for key, value in rm_node.items():
                if key == "id":
                    continue
                if not keep_node.get(key) and value:
                    keep_node[key] = value

        # Re-point edges
        for edge in self.graph["edges"]:
            if edge.get("source") in remove_ids:
                edge["source"] = keep_id
            if edge.get("target") in remove_ids:
                edge["target"] = keep_id

        # Remove duplicate nodes
        self.graph["nodes"] = [n for n in self.graph["nodes"] if n["id"] not in remove_ids]

        # Remove self-referencing edges
        self.graph["edges"] = [e for e in self.graph["edges"] if e.get("source") != e.get("target")]

        # Remove duplicate edges
        seen = set()
        unique_edges = []
        for e in self.graph["edges"]:
            key = (e.get("source"), e.get("target"), e.get("type"))
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)
        self.graph["edges"] = unique_edges

        dlog(f"Merged {remove_ids} into {keep_id}")
        return True

    def auto_merge(self, report):
        """Auto-merge high-confidence duplicates."""
        merged = 0

        # Merge contact duplicates with confidence >= 0.9
        for dup in report.get("contacts", []):
            if dup["confidence"] >= 0.9 and len(dup["nodes"]) >= 2:
                keep = dup["nodes"][0]
                remove = dup["nodes"][1:]
                if self.merge_nodes(keep, remove):
                    merged += 1

        # Merge company duplicates with confidence >= 0.9
        for dup in report.get("companies", []):
            if dup["confidence"] >= 0.9 and len(dup["nodes"]) >= 2:
                keep = dup["nodes"][0]
                remove = dup["nodes"][1:]
                if self.merge_nodes(keep, remove):
                    merged += 1

        return merged

    def save(self):
        """Save the merged graph."""
        GRAPH_FILE.write_text(json.dumps(self.graph, indent=2, ensure_ascii=False))


def cmd_scan():
    """Scan for duplicates."""
    if not GRAPH_FILE.exists():
        print("  No knowledge graph found. Run: python3 scripts/knowledge_graph.py build")
        return

    graph = json.loads(GRAPH_FILE.read_text())
    detector = DuplicateDetector(graph)
    report = detector.scan_all()

    # Save report
    DEDUP_REPORT.parent.mkdir(exist_ok=True)
    DEDUP_REPORT.write_text(json.dumps(report, indent=2))

    print(f"\n{'='*50}")
    print(f"  Knowledge Deduplication Scan")
    print(f"{'='*50}\n")
    print(f"  Total Contacts: {report['total_contacts']}")
    print(f"  Total Companies: {report['total_companies']}")
    print(f"  Contact Duplicates: {report['contact_duplicates']}")
    print(f"  Company Duplicates: {report['company_duplicates']}\n")

    if report["contacts"]:
        print("  Contact Duplicates:")
        for d in report["contacts"][:15]:
            conf = d["confidence"]
            color = "\033[0;31m" if conf >= 0.9 else "\033[0;33m" if conf >= 0.7 else "\033[0;36m"
            print(f"    {color}{conf:.0%}\033[0m  {d['reason']}")

    if report["companies"]:
        print(f"\n  Company Duplicates:")
        for d in report["companies"][:10]:
            conf = d["confidence"]
            color = "\033[0;31m" if conf >= 0.9 else "\033[0;33m"
            print(f"    {color}{conf:.0%}\033[0m  {d['reason']}")

    print(f"\n  Report saved to: {DEDUP_REPORT}\n")


def cmd_merge():
    """Auto-merge high-confidence duplicates."""
    if not DEDUP_REPORT.exists():
        print("  No dedup report found. Run 'scan' first.")
        return

    report = json.loads(DEDUP_REPORT.read_text())
    graph = json.loads(GRAPH_FILE.read_text())

    nodes_before = len(graph["nodes"])
    merger = DuplicateMerger(graph)
    merged = merger.auto_merge(report)
    merger.save()
    nodes_after = len(merger.graph["nodes"])

    print(f"\n  Auto-Merge Complete")
    print(f"  Merged: {merged} duplicate groups")
    print(f"  Nodes: {nodes_before} → {nodes_after} (-{nodes_before - nodes_after})")
    print(f"  Graph saved.\n")


def cmd_stats():
    """Show dedup statistics."""
    report = None
    if DEDUP_REPORT.exists():
        try:
            report = json.loads(DEDUP_REPORT.read_text())
        except json.JSONDecodeError:
            pass

    if not report:
        print("  No dedup report. Run 'scan' first.")
        return

    print(f"\n  Dedup Statistics")
    print(f"  Last scan: {report.get('timestamp', 'unknown')}")
    print(f"  Contacts: {report['total_contacts']} total, {report['contact_duplicates']} duplicates")
    print(f"  Companies: {report['total_companies']} total, {report['company_duplicates']} duplicates")

    # Confidence distribution
    all_dupes = report.get("contacts", []) + report.get("companies", [])
    high = sum(1 for d in all_dupes if d["confidence"] >= 0.9)
    medium = sum(1 for d in all_dupes if 0.7 <= d["confidence"] < 0.9)
    low = sum(1 for d in all_dupes if d["confidence"] < 0.7)
    print(f"  High confidence (>=90%): {high}")
    print(f"  Medium (70-89%): {medium}")
    print(f"  Low (<70%): {low}\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        cmd_scan()
    elif cmd == "merge":
        cmd_merge()
    elif cmd == "stats":
        cmd_stats()
    else:
        print("Usage: knowledge_dedup.py [scan|merge|stats]")


if __name__ == "__main__":
    main()
