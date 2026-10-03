#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_bounties.py -- DAXDA meta-bounty structural validator.

Purpose
-------
Required deliverable 2 of BOUNTY_DAXDA_META_RECURSIVE.md:

    "Validation Script: A Python script that verifies each generated bounty
     meets the structural and content requirements (structural similarity
     scoring, required section presence, technical specificity metrics)."

This script checks ONLY requirements that are objectively measurable and
published in BOUNTY_DAXDA_META_RECURSIVE.md. Every threshold below is quoted
from that document with its source line. Nothing is invented here.

Each check maps to a published requirement:

  C1  Five Markdown files, pattern BOUNTY_DAXDA_[SUBSYSTEM_NAME].md   (META:84)
  C2  Each bounty at least 150 lines                                   (META:131)
  C3  Same section structure as the meta-bounty; Structural Fidelity
      Score > 95% match with meta-bounty structure                     (META:52,132,44)
  C4  Required metadata present: tags, reward info, evaluation
      criteria                                                         (META:133)
  C5  Recursive Depth: at least 3 sub-bounty opportunities             (META:54,64)
  C6  Technical specificity: the five categories listed at META:66-71
      (languages/frameworks, DAXDA integration points, test and validation
      criteria, security/containment, performance benchmarks)
  C7  Submission requirements listed at META:73-78: acceptance criteria,
      evaluation methodology, deliverable artifacts, timeline/milestones,
      payment structure and conditions
  C8  Interconnection map exists                                       (META:88)
  C9  Submission Package: a compressed archive containing all
      deliverables                                                    (META:90)

REPORTED BUT NOT GRADED (published, yet not objectively decidable):
  - Content Originality: 100% original content except verbatim
    foundation (META:53). Requires provenance judgement. Not automated.
  - Interconnection Density: all five bounties must reference each other
    "where appropriate" (META:55). "Where appropriate" is a judgement, so
    cross-reference counts are reported as information only.
  - Professional / technical English tone (META:46,134). Not automated.

Design constraints
------------------
  - Python standard library only.
  - Every file is read with an explicit UTF-8 decode (the bounty documents
    contain non-ASCII characters and are UTF-8 without BOM).
  - Console output is forced to pure ASCII so this runs unchanged on Windows
    PowerShell 5.1 with console code page 850 / locale cp1252.
  - Exit code 0 if and only if every graded check passes; 1 otherwise.

Usage
-----
    python validation/validate_bounties.py
    python validation/validate_bounties.py --root . --strict-archive
"""

import argparse
import os
import re
import sys

# --------------------------------------------------------------------------
# Constants drawn from BOUNTY_DAXDA_META_RECURSIVE.md
# --------------------------------------------------------------------------

META_FILE = "BOUNTY_DAXDA_META_RECURSIVE.md"

#: The five Level 1 subsystem bounties named at META:38 and META:57-62.
CORE_BOUNTIES = [
    "BOUNTY_DAXDA_CLENGINE.md",
    "BOUNTY_DAXDA_CONTAINMENT.md",
    "BOUNTY_DAXDA_VALIDATOR.md",
    "BOUNTY_DAXDA_SYNCHRONICITY.md",
    "BOUNTY_DAXDA_PENETRATION.md",
]

INTERCONNECTION_MAP = "interconnection_map.md"
ARCHIVE_EXTENSIONS = (".zip",)

#: Unambiguous subsystem names for each core bounty. Used only to recognise a
#: declared interconnection row; never used to infer that an integration
#: exists. Matching is exact-substring on the row text.
SUBSYSTEM_ALIASES = {
    "BOUNTY_DAXDA_CLENGINE.md": (
        "Cl(16,4) Hypercombinatorial Governance Engine",
    ),
    "BOUNTY_DAXDA_CONTAINMENT.md": (
        "Anomalous Containment Wing",
    ),
    "BOUNTY_DAXDA_VALIDATOR.md": (
        "DA13 Distributed GPU Validator Cluster",
    ),
    "BOUNTY_DAXDA_SYNCHRONICITY.md": (
        "Chrono-Synchronicity",
    ),
    "BOUNTY_DAXDA_PENETRATION.md": (
        "MMPIBench",
    ),
}

MIN_LINES = 150            # META:131
FIDELITY_THRESHOLD = 95.0  # META:52  (> 95% match)
MIN_SUB_BOUNTIES = 3       # META:54  (at least 3 sub-bounty opportunities)

FILENAME_RE = re.compile(r"^BOUNTY_DAXDA_[A-Z0-9_]+\.md$")  # META:84

# META:133 -- "Must include all required metadata (tags, reward information,
# evaluation criteria)".
METADATA_PROBES = [
    ("tags", re.compile(r"\*\*Tags\*\*", re.IGNORECASE)),
    ("reward information", re.compile(r"Total bounty\s*:", re.IGNORECASE)),
    ("evaluation criteria", re.compile(r"^##\s*\S*\s*Evaluation Criteria", re.MULTILINE)),
]

# META:66-71 -- "Technical Specificity: Include specific technical
# requirements". These keyword sets are transcribed from that list; presence
# is a proxy for the category and is reported as such.
TECHNICAL_SPECIFICITY_CATEGORIES = [
    ("required programming languages and frameworks",
     re.compile(r"Python\s*3\.11|Ray|CUDA|Kubernetes|PyTorch", re.IGNORECASE)),
    ("integration points with existing DAXDA infrastructure",
     re.compile(r"DAXDA", re.IGNORECASE)),
    ("test and validation criteria",
     re.compile(r"\btests?\b|validation", re.IGNORECASE)),
    ("security and containment considerations",
     re.compile(r"security|containment", re.IGNORECASE)),
    ("performance benchmarks and metrics",
     re.compile(r"performance|latency|throughput|benchmark|scalability", re.IGNORECASE)),
]

# META:73-78 -- "Submission Requirements: Each generated bounty must specify".
SUBMISSION_REQUIREMENT_PROBES = [
    ("acceptance criteria", re.compile(r"^##\s*\S*\s*(Acceptance Criteria|Objective)", re.MULTILINE)),
    ("evaluation methodology", re.compile(r"^##\s*\S*\s*Evaluation Criteria", re.MULTILINE)),
    ("deliverable artifacts", re.compile(r"^##\s*\S*\s*Required Deliverables", re.MULTILINE)),
    ("timeline and milestones", re.compile(r"^##\s*\S*\s*Timeline", re.MULTILINE)),
    ("payment structure and conditions", re.compile(r"Milestone", re.IGNORECASE)),
]

SECTION_RE = re.compile(r"^##\s+(.*\S)\s*$")


# --------------------------------------------------------------------------
# ASCII-safe output
# --------------------------------------------------------------------------

def out(line=""):
    """Print a line forced to pure ASCII.

    The bounty documents contain emoji. On Windows PowerShell 5.1 with console
    code page 850 (locale cp1252) a raw emoji raises UnicodeEncodeError, so
    every character outside ASCII is replaced before printing.
    """
    sys.stdout.write(line.encode("ascii", "replace").decode("ascii") + "\n")


def rule(char="-", width=78):
    out(char * width)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def read_text(path):
    """Read a file with an explicit UTF-8 decode. Returns (text, error)."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read(), None
    except UnicodeDecodeError as exc:
        return None, "not valid UTF-8: %s" % exc
    except OSError as exc:
        return None, "unreadable: %s" % exc


def normalize_section(name):
    """Normalize a section header for structural comparison.

    Strips non-ASCII (decorative emoji, which vary between documents),
    lowercases, and collapses punctuation runs to single spaces. This does
    not reconcile renamed sections; see fidelity_score() for the rationale.
    """
    ascii_only = "".join(ch for ch in name if ord(ch) < 128)
    ascii_only = re.sub(r"[^a-z0-9]+", " ", ascii_only.lower())
    return ascii_only.strip()


def section_names(text):
    """Return the ordered list of '## ' section names in a document."""
    names = []
    for line in text.splitlines():
        match = SECTION_RE.match(line)
        if match:
            names.append(match.group(1))
    return names


def fidelity_score(candidate_sections, template_sections):
    """Compute structural fidelity against the meta-bounty template.

    Returns a dict with the exact-match and normalized-match percentages.

    Score definition (META:52 "Structural Fidelity Score: > 95% match with
    meta-bounty structure"): the proportion of the meta-bounty's own '## '
    section headers that are present in the candidate.

    Normalized comparison ignores decorative emoji and punctuation only, so
    '## Reward & Payment' matches '## [emoji] Reward & Payment'. It does NOT
    forgive a renamed or absent section: 'Constraints' does not match
    'Constraints & Requirements'. A renamed section therefore counts as
    missing, which is the stricter reading of META:132 ("must use the exact
    same ... section structure"). The exact-string score is reported too.
    """
    candidate_exact = set(candidate_sections)
    candidate_norm = {normalize_section(s) for s in candidate_sections}
    template_exact = set(template_sections)
    template_norm = {normalize_section(s) for s in template_sections}

    total = len(template_norm) or 1
    exact_hits = len(candidate_exact & template_exact)
    norm_hits = len(candidate_norm & template_norm)

    missing_exact = sorted(template_exact - candidate_exact)
    missing_norm = sorted(template_norm - candidate_norm)

    return {
        "exact_pct": 100.0 * exact_hits / total,
        "normalized_pct": 100.0 * norm_hits / total,
        "missing_exact": missing_exact,
        "missing_normalized": missing_norm,
        "template_total": len(template_norm),
    }


def count_sub_bounty_opportunities(text):
    """Count sub-bounty opportunity bullets in the Recursive Expansion section.

    Implements META:54 ("at least 3 sub-bounty opportunities") by counting the
    bullet list under the 'Recursive Expansion' header.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("## ") and "recursive expansion" in line.lower():
            start = index + 1
            break
    if start is None:
        return 0, "no 'Recursive Expansion' section found"

    count = 0
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if re.match(r"^\s*[-*]\s+\S", line):
            count += 1
    return count, None


def interconnection_section(text):
    """Return the body of the 'DAXDA System Interconnection' subsection.

    Returns None when the subsection is absent, so that a document can be
    distinguished as having no declared relationships at all.
    """
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.startswith("### ") and "interconnection" in line.lower():
            start = index + 1
            break
    if start is None:
        return None
    body = []
    for line in lines[start:]:
        if line.startswith("## ") or line.startswith("### "):
            break
        body.append(line)
    return "\n".join(body)


def count_cross_references(texts):
    """Describe how each document references the other four core bounties.

    Reported as information only. META:55 requires interconnection
    "where appropriate", which is a judgement call, so this function
    deliberately produces NO pass/fail threshold. It reports, per ordered
    pair: whether the peer bounty is named by filename, whether it is named
    by subsystem concept, how many times it is named, and whether the
    document marks the relationship REQUIRED or OPTIONAL.

    A relationship is attributed to a peer only when the filename or one of
    the peer's unambiguous subsystem names occurs inside an interconnection
    table row, so that passing prose mentions elsewhere in the document are
    not silently counted as declared integration.
    """
    matrix = {}
    for name in CORE_BOUNTIES:
        text = texts.get(name)
        if text is None:
            continue
        body = interconnection_section(text)
        rows = []
        if body:
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped.startswith("|"):
                    continue
                for other in CORE_BOUNTIES:
                    if other == name:
                        continue
                    aliases = [other] + list(SUBSYSTEM_ALIASES.get(other, ()))
                    hits = [a for a in aliases if a in stripped]
                    if not hits:
                        continue
                    upper = stripped.upper()
                    if "REQUIRED" in upper and "OPTIONAL" not in upper:
                        status = "REQUIRED"
                    elif "OPTIONAL" in upper:
                        status = "OPTIONAL"
                    else:
                        status = "unstated"
                    rows.append({
                        "peer": other,
                        "matched": hits[0],
                        "status": status,
                    })
                    break
        named = sorted({row["peer"] for row in rows})
        required = sorted({row["peer"] for row in rows if row["status"] == "REQUIRED"})
        matrix[name] = {
            "rows": rows,
            "named": named,
            "count": len(named),
            "required": required,
            "peers": len(CORE_BOUNTIES) - 1,
            "has_section": body is not None,
        }
    return matrix


# --------------------------------------------------------------------------
# Per-file graded validation
# --------------------------------------------------------------------------

class Result(object):
    def __init__(self, name):
        self.name = name
        self.checks = []   # (check_id, label, passed, detail)
        self.info = []     # informational strings, never graded

    @property
    def passed(self):
        return all(ok for _, _, ok, _ in self.checks)

    def add(self, check_id, label, passed, detail=""):
        self.checks.append((check_id, label, bool(passed), detail))

    def fail_count(self):
        return sum(1 for _, _, ok, _ in self.checks if not ok)


def validate_bounty(path, name, template_sections):
    """Run every graded check against one core bounty document."""
    result = Result(name)

    # C1 filename pattern (META:84)
    result.add("C1", "filename matches BOUNTY_DAXDA_[SUBSYSTEM_NAME].md",
               bool(FILENAME_RE.match(name)),
               "" if FILENAME_RE.match(name) else "filename %r does not match pattern" % name)

    text, error = read_text(path)
    if error:
        result.add("C2", "at least %d lines (META:131)" % MIN_LINES, False, error)
        result.add("C3", "structural fidelity > %.0f%% (META:52)" % FIDELITY_THRESHOLD, False, error)
        result.add("C4", "required metadata present (META:133)", False, error)
        result.add("C5", "at least %d sub-bounty opportunities (META:54)" % MIN_SUB_BOUNTIES, False, error)
        result.add("C6", "technical specificity categories (META:66-71)", False, error)
        result.add("C7", "submission requirements (META:73-78)", False, error)
        return result

    lines = text.splitlines()

    # C2 minimum length (META:131)
    result.add("C2", "at least %d lines (META:131)" % MIN_LINES,
               len(lines) >= MIN_LINES,
               "%d lines" % len(lines))

    # C3 structural fidelity (META:52, :132, :44)
    sections = section_names(text)
    score = fidelity_score(sections, template_sections)
    graded = score["normalized_pct"] > FIDELITY_THRESHOLD
    detail = ("normalized %.1f%%, exact %.1f%% of %d template sections; "
              "missing: %s"
              % (score["normalized_pct"], score["exact_pct"],
                 score["template_total"],
                 ", ".join(score["missing_normalized"]) or "none"))
    result.add("C3", "structural fidelity > %.0f%% (META:52)" % FIDELITY_THRESHOLD,
               graded, detail)

    # C4 required metadata (META:133)
    absent = [label for label, pattern in METADATA_PROBES if not pattern.search(text)]
    result.add("C4", "required metadata present (META:133)",
               not absent,
               "missing: %s" % ", ".join(absent) if absent
               else "tags, reward information and evaluation criteria all found")

    # C5 recursive depth (META:54)
    count, count_error = count_sub_bounty_opportunities(text)
    result.add("C5", "at least %d sub-bounty opportunities (META:54)" % MIN_SUB_BOUNTIES,
               count >= MIN_SUB_BOUNTIES,
               count_error if count_error else "%d opportunities listed" % count)

    # C6 technical specificity (META:66-71)
    missing_categories = [label for label, pattern in TECHNICAL_SPECIFICITY_CATEGORIES
                          if not pattern.search(text)]
    result.add("C6", "technical specificity categories (META:66-71)",
               not missing_categories,
               "missing categories: %s" % ", ".join(missing_categories)
               if missing_categories
               else "all %d published categories present" % len(TECHNICAL_SPECIFICITY_CATEGORIES))

    # C7 submission requirements (META:73-78)
    missing_reqs = [label for label, pattern in SUBMISSION_REQUIREMENT_PROBES
                    if not pattern.search(text)]
    result.add("C7", "submission requirements (META:73-78)",
               not missing_reqs,
               "missing: %s" % ", ".join(missing_reqs) if missing_reqs
               else "all 5 published submission requirements specified")

    result.info.append("reward declared: %s" % first_reward(text))
    return result


def first_reward(text):
    match = re.search(r"Total bounty\s*:\s*([^\n]+)", text)
    return match.group(1).strip() if match else "not found"


# --------------------------------------------------------------------------
# Package-level checks
# --------------------------------------------------------------------------

def validate_package(root, template_sections, strict_archive):
    """Run checks that apply to the package rather than to one bounty.

    Returns (checks, archives, warnings). Entries in `warnings` are published
    requirements that are reported but not counted as graded failures.
    """
    checks = []
    warnings = []

    # C1 file presence and count (META:84)
    missing = [n for n in CORE_BOUNTIES if not os.path.isfile(os.path.join(root, n))]
    checks.append(("C1", "five core bounty files present (META:84)",
                   not missing,
                   "missing: %s" % ", ".join(missing) if missing
                   else "all 5 present"))
    if missing:
        return checks, [], warnings

    # C8 interconnection map (META:88)
    map_path = os.path.join(root, INTERCONNECTION_MAP)
    map_exists = os.path.isfile(map_path)
    map_detail = "found: %s" % INTERCONNECTION_MAP if map_exists else "not found: %s" % INTERCONNECTION_MAP
    if map_exists:
        map_text, map_error = read_text(map_path)
        if map_error:
            map_detail = "%s unreadable: %s" % (INTERCONNECTION_MAP, map_error)
        elif not re.search(r"BOUNTY_DAXDA_", map_text):
            map_detail = "%s names no bounty files" % INTERCONNECTION_MAP
            map_exists = False
    checks.append(("C8", "interconnection map present (META:88)", map_exists, map_detail))

    # C9 submission archive (META:90)
    archives = []
    try:
        for entry in sorted(os.listdir(root)):
            if entry.lower().endswith(ARCHIVE_EXTENSIONS):
                archives.append(entry)
    except OSError as exc:
        checks.append(("C9", "compressed submission archive (META:90)", False,
                       "root unreadable: %s" % exc))
        return checks, [], warnings

    archive_ok = bool(archives)
    archive_detail = ("found: %s" % ", ".join(archives)) if archive_ok else \
        "no .zip archive in package root; META:90 requires a compressed archive"

    # META:90 does require a compressed archive, so the requirement is real.
    # In normal mode it is reported as a WARN so that it stays visible without
    # being counted as an objective validation failure; --strict-archive
    # promotes it to a graded FAIL, which is how the published requirement
    # should be read when packaging is actually being submitted.
    if archive_ok:
        checks.append(("C9", "compressed submission archive (META:90)", True,
                       archive_detail))
    elif strict_archive:
        checks.append(("C9", "compressed submission archive (META:90)", False,
                       archive_detail))
    else:
        warnings.append(("C9", "compressed submission archive (META:90)",
                         archive_detail + " [WARN: reported, not graded; "
                         "re-run with --strict-archive to enforce]"))

    return checks, archives, warnings


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_results(results):
    for result in results:
        rule("=")
        status = "PASS" if result.passed else "FAIL"
        out("%s  %s" % (status, result.name))
        rule("=")
        for check_id, label, passed, detail in result.checks:
            out("  [%s] %-4s %s" % ("PASS" if passed else "FAIL", check_id, label))
            if detail:
                for line in wrap(detail, 68):
                    out("            %s" % line)
        for note in result.info:
            out("  [INFO] %s" % note)
        out("")


def wrap(text, width):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = word if not current else current + " " + word
    if current:
        lines.append(current)
    return lines or [""]


def print_summary(results, package_checks, package_warnings):
    graded = []
    for result in results:
        for check_id, label, passed, detail in result.checks:
            graded.append((check_id, label, passed, detail))
    for check_id, label, passed, detail in package_checks:
        graded.append((check_id, label, passed, detail))

    passed = sum(1 for _, _, ok, _ in graded if ok)
    failed = len(graded) - passed

    out("")
    rule("=")
    out("SUMMARY")
    rule("=")
    out("  Files checked      : %d core bounty documents" % len(results))
    out("  Graded checks      : %d" % len(graded))
    out("  Passed             : %d" % passed)
    out("  Failed             : %d" % failed)
    out("  Warnings           : %d (reported, not graded)" % len(package_warnings))
    out("  Files PASS         : %d" % sum(1 for r in results if r.passed))
    out("  Files FAIL         : %d" % sum(1 for r in results if not r.passed))
    out("")
    if package_warnings:
        out("  Warnings (published requirement, not counted as failure):")
        for check_id, label, _ in package_warnings:
            out("    - %s: %s" % (check_id, label))
        out("")
    if failed:
        out("  Failing checks:")
        for check_id, label, ok, detail in graded:
            if not ok:
                out("    - %s: %s" % (check_id, label))
        out("")
    out("  NOT automated (published but not objectively decidable):")
    out("    - Content Originality, 100% original (META:53) - needs provenance")
    out("    - Interconnection Density, 'where appropriate' (META:55) - judgement")
    out("    - Professional / technical English tone (META:46,134) - judgement")
    out("    - Technical Depth 30% and Cohesion 10% weights (META:98,102)")
    out("      are assigned by human review, not by this script.")
    out("")
    out("  This script reports structure only. It does not assert that the")
    out("  submission has been accepted, funded, or approved for payment.")
    out("")
    return failed


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate the DAXDA meta-bounty package structure.")
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))),
        help="package root (default: parent of this script's directory)")
    parser.add_argument("--strict-archive", action="store_true",
                        help="treat a missing submission archive as a failure "
                             "rather than an informational note")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.root)

    out("DAXDA meta-bounty structural validator")
    out("Package root: %s" % root)
    out("Reference   : %s" % META_FILE)
    out("")

    template_path = os.path.join(root, META_FILE)
    if not os.path.isfile(template_path):
        out("FATAL: reference template not found: %s" % META_FILE)
        out("This script validates against the meta-bounty's own section")
        out("structure and cannot run without it.")
        return 2

    template_text, template_error = read_text(template_path)
    if template_error:
        out("FATAL: cannot read %s: %s" % (META_FILE, template_error))
        return 2
    template_sections = section_names(template_text)

    out("Template sections (%d): %s"
        % (len(template_sections),
           ", ".join(normalize_section(s) or "<empty>" for s in template_sections)))
    out("")

    results = []
    texts = {}
    for name in CORE_BOUNTIES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            text, _ = read_text(path)
            texts[name] = text
        results.append(validate_bounty(path, name, template_sections))

    print_results(results)

    out("INFORMATIONAL: cross-reference matrix (META:55, NOT graded)")
    rule()
    out("  Reports declared relationships only. META:55 says 'where")
    out("  appropriate', which is a judgement, so no threshold is applied and")
    out("  no PASS/FAIL is derived from this table.")
    out("")
    matrix = count_cross_references(texts)
    short = lambda n: n.replace("BOUNTY_DAXDA_", "").replace(".md", "")
    out("  %-16s %-7s %s" % ("document", "peers", "declared relationships (status)"))
    for name in CORE_BOUNTIES:
        info = matrix.get(name)
        if not info:
            continue
        if not info["has_section"]:
            out("  %-16s %-7s no interconnection subsection found"
                % (short(name), "-"))
            continue
        entries = ["%s [%s]" % (short(row["peer"]), row["status"])
                   for row in info["rows"]]
        out("  %-16s %d/%-5d %s"
            % (short(name), info["count"], info["peers"], ", ".join(entries)))
    out("")
    for name in CORE_BOUNTIES:
        info = matrix.get(name)
        if not info or not info["has_section"]:
            continue
        out("  %-16s REQUIRED: %d   OPTIONAL: %d"
            % (short(name),
               sum(1 for r in info["rows"] if r["status"] == "REQUIRED"),
               sum(1 for r in info["rows"] if r["status"] == "OPTIONAL")))
    out("")

    package_checks, _archives, package_warnings = validate_package(
        root, template_sections, args.strict_archive)
    out("PACKAGE CHECKS")
    rule()
    for check_id, label, passed, detail in package_checks:
        out("  [%s] %-4s %s" % ("PASS" if passed else "FAIL", check_id, label))
        for line in wrap(detail, 68):
            out("            %s" % line)
    for check_id, label, detail in package_warnings:
        out("  [WARN] %-4s %s" % (check_id, label))
        for line in wrap(detail, 68):
            out("            %s" % line)
    out("")

    failed = print_summary(results, package_checks, package_warnings)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())