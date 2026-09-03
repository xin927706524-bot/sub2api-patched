#!/usr/bin/env python3
"""Resolve the small, semantic conflicts in the display-multiplier patch.

The adaptation workflow applies the diff between the last official release and
its patched counterpart.  Most files apply cleanly; this helper merges the
usage DTO and its regression test when upstream has refactored those files.
It deliberately fails closed if any other file is conflicted.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], text=True, encoding="utf-8", errors="strict"
    )


def git_write_stage(path: str, stage: int) -> None:
    content = git("show", f":{stage}:{path}")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="")


def extract_function(source: str, name: str) -> str:
    match = re.search(rf"(?m)^func {re.escape(name)}\([^\n]*\)[^{{\n]*\{{", source)
    if not match:
        raise ValueError(f"function {name} was not found")

    opening = source.find("{", match.start())
    depth = 0
    in_string = False
    escaped = False
    for index in range(opening, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise ValueError(f"unterminated function {name}")


def merge_mapper(path: str, patched_ref: str) -> None:
    git_write_stage(path, 2)
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if "func usageLogFromServiceUser" not in source:
        raise ValueError("upstream usage mapper shape is not recognized")

    source = source.replace('"strconv"\n\t"strings"', '"math"\n\t"strconv"\n\t"strings"', 1)
    source = merge_group_mapper(source)
    source = source.replace(
        "func usageLogFromServiceUser(l *service.UsageLog) UsageLog {",
        "func usageLogFromService(l *service.UsageLog, applyDisplayTokenMultiplier bool) UsageLog {",
        1,
    )

    anchor = "\tif requestedModel == \"\" {\n\t\trequestedModel = l.Model\n\t}\n"
    helpers = """\ttokenMultiplier := 1.0
\tif applyDisplayTokenMultiplier {
\t\ttokenMultiplier = l.Group.PublicTokenMultiplier()
\t}
\tdisplayTokens := func(tokens int) int {
\t\treturn int(math.Round(float64(tokens) * tokenMultiplier))
\t}
\tdisplayCost := func(cost float64) float64 {
\t\treturn cost * tokenMultiplier
\t}
\ttokenPricePerMillion := func(cost float64, tokens int) *float64 {
\t\tif tokens <= 0 {
\t\t\treturn nil
\t\t}
\t\tprice := cost / float64(tokens) * 1_000_000
\t\treturn &price
\t}
\trateMultiplier := l.RateMultiplier
\ttotalCost := l.TotalCost
\tif applyDisplayTokenMultiplier {
\t\tif l.Group != nil {
\t\t\trateMultiplier = l.Group.PublicRateMultiplier()
\t\t}
\t\ttotalCost = l.ActualCost
\t}
"""
    if anchor not in source:
        raise ValueError("usage mapper model anchor was not found")
    source = source.replace(anchor, anchor + helpers, 1)

    replacements = {
        "InputTokens": "displayTokens(l.InputTokens)",
        "OutputTokens": "displayTokens(l.OutputTokens)",
        "CacheCreationTokens": "displayTokens(l.CacheCreationTokens)",
        "CacheReadTokens": "displayTokens(l.CacheReadTokens)",
        "CacheCreation5mTokens": "displayTokens(l.CacheCreation5mTokens)",
        "CacheCreation1hTokens": "displayTokens(l.CacheCreation1hTokens)",
        "InputCost": "displayCost(l.InputCost)",
        "OutputCost": "displayCost(l.OutputCost)",
        "CacheReadCost": "displayCost(l.CacheReadCost)",
        "TotalCost": "totalCost",
        "RateMultiplier": "rateMultiplier",
        "ImageInputTokens": "displayTokens(l.ImageInputTokens)",
        "ImageOutputTokens": "displayTokens(l.ImageOutputTokens)",
    }
    for field, value in replacements.items():
        pattern = rf"(?m)^(\s*{re.escape(field)}:\s+)l\.{re.escape(field)},$"
        source, count = re.subn(pattern, rf"\g<1>{value},", source, count=1)
        if count != 1:
            raise ValueError(f"usage mapper field anchor was not found: {field}")

    price_anchor = re.compile(
        r"(?m)^(\s*CacheReadCost:\s+displayCost\(l\.CacheReadCost\),\s*\n)"
    )
    prices = """\t\tInputTokenPricePerMillion:       tokenPricePerMillion(l.InputCost, l.InputTokens-l.ImageInputTokens),
\t\tOutputTokenPricePerMillion:      tokenPricePerMillion(l.OutputCost, l.OutputTokens-l.ImageOutputTokens),
\t\tImageInputTokenPricePerMillion:  tokenPricePerMillion(l.ImageInputCost, l.ImageInputTokens),
\t\tImageOutputTokenPricePerMillion: tokenPricePerMillion(l.ImageOutputCost, l.ImageOutputTokens),
"""
    if not price_anchor.search(source):
        raise ValueError("usage mapper cost anchor was not found")
    source = price_anchor.sub(r"\g<1>" + prices, source, count=1)
    source = source.replace("u := usageLogFromServiceUser(l)", "u := usageLogFromService(l, true)", 1)
    source = source.replace("usageLog := usageLogFromServiceUser(l)", "usageLog := usageLogFromService(l, false)", 1)
    target.write_text(source, encoding="utf-8", newline="")
    subprocess.check_call(["git", "add", path])


def merge_group_mapper(source: str) -> str:
    """Reapply the group display-rate fields that share this mapper file."""
    admin = extract_function(source, "GroupFromServiceAdmin")
    if "DisplayRateMultiplier:" not in admin:
        group_anchor = re.compile(
            r"(?m)^(\s*Group:\s+groupFromServiceBase\(g\),\s*\n)"
        )
        match = group_anchor.search(admin)
        if not match:
            raise ValueError("admin group mapper anchor was not found")
        indent = re.match(r"\s*", match.group(1)).group(0)
        addition = (
            f"{indent}DisplayRateMultiplier:       g.DisplayRateMultiplier,\n"
            f"{indent}DisplayTokenMultiplier:      g.DisplayTokenMultiplier,\n"
        )
        admin = admin[: match.end()] + addition + admin[match.end() :]
        admin_anchor = "\n\t}\n\tif len(g.AccountGroups) > 0 {"
        if admin_anchor not in admin:
            raise ValueError("admin group mapper return anchor was not found")
        admin = admin.replace(
            admin_anchor,
            "\n\t}\n\t// Admin responses retain the real billing multiplier and expose the\n"
            "\t// optional display override separately.\n"
            "\tout.RateMultiplier = g.RateMultiplier\n"
            "\tif len(g.AccountGroups) > 0 {",
            1,
        )
        source = source.replace(
            extract_function(source, "GroupFromServiceAdmin"), admin, 1
        )

    base = extract_function(source, "groupFromServiceBase")
    if "out.RateMultiplier = g.PublicRateMultiplier()" not in base:
        if "return Group{" not in base:
            raise ValueError("group mapper return anchor was not found")
        base = base.replace("return Group{", "out := Group{", 1)
        if not base.endswith("\n}"):
            raise ValueError("group mapper function boundary was not found")
        base = (
            base[:-1]
            + "\tout.RateMultiplier = g.PublicRateMultiplier()\n"
            + "\treturn out\n}"
        )
        source = source.replace(
            extract_function(source, "groupFromServiceBase"), base, 1
        )
    return source


def merge_usage_test(path: str, patched_ref: str) -> None:
    git_write_stage(path, 2)
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if "TestUsageLogFromService_AppliesDisplayTokenMultiplierOnlyForUser" in source:
        subprocess.check_call(["git", "add", path])
        return
    patched = git("show", f"{patched_ref}:{path}")
    function = extract_function(
        patched, "TestUsageLogFromService_AppliesDisplayTokenMultiplierOnlyForUser"
    )
    insertion = re.search(r"(?m)^func TestUsageLogFromService_", source)
    if not insertion:
        raise ValueError("usage DTO test insertion point was not found")
    source = source[: insertion.start()] + function + "\n\n" + source[insertion.start() :]
    target.write_text(source, encoding="utf-8", newline="")
    subprocess.check_call(["git", "add", path])


def resolve_markers(source: str, path: str, include_theirs: bool) -> str:
    """Resolve git conflict markers while preserving already-merged surrounding edits."""
    lines = source.splitlines(keepends=True)
    merged: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("<<<<<<< ours"):
            merged.append(lines[index])
            index += 1
            continue
        index += 1
        ours: list[str] = []
        while index < len(lines) and not lines[index].startswith("======="):
            ours.append(lines[index])
            index += 1
        if index >= len(lines):
            raise ValueError(f"unterminated conflict in {path}")
        index += 1
        theirs: list[str] = []
        while index < len(lines) and not lines[index].startswith(">>>>>>> theirs"):
            theirs.append(lines[index])
            index += 1
        if index >= len(lines):
            raise ValueError(f"unterminated conflict in {path}")
        index += 1
        merged.extend(ours)
        if include_theirs:
            ours_normalized = {line.strip() for line in ours if line.strip()}
            merged.extend(
                line for line in theirs if not line.strip() or line.strip() not in ours_normalized
            )
    return "".join(merged)


def keep_upstream_generated(path: str) -> None:
    """Resolve generated-file hunks in favor of upstream while keeping non-overlapping patch additions."""
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if "<<<<<<< ours" not in source:
        git_write_stage(path, 2)
    else:
        target.write_text(
            resolve_markers(source, path, include_theirs=False),
            encoding="utf-8",
            newline="",
        )
    subprocess.check_call(["git", "add", path])


def merge_admin_dto_types(path: str) -> None:
    """Keep upstream admin fields while retaining the patched display overrides."""
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if "<<<<<<< ours" in source:
        source = resolve_markers(source, path, include_theirs=True)
    else:
        git_write_stage(path, 2)
        source = target.read_text(encoding="utf-8")
    if "DisplayRateMultiplier" not in source:
        anchor = "type AdminGroup struct {\n\tGroup\n"
        if anchor not in source:
            raise ValueError("admin DTO group anchor was not found")
        source = source.replace(
            anchor,
            anchor
            + '\tDisplayRateMultiplier  *float64 `json:"display_rate_multiplier"`\n'
            + '\tDisplayTokenMultiplier *float64 `json:"display_token_multiplier"`\n',
            1,
        )
    target.write_text(source, encoding="utf-8", newline="")
    subprocess.check_call(["git", "add", path])


def merge_frontend_types(path: str) -> None:
    """Keep upstream admin type additions while retaining patched display fields."""
    target = Path(path)
    source = target.read_text(encoding="utf-8")
    if "<<<<<<< ours" in source:
        source = resolve_markers(source, path, include_theirs=True)
    else:
        git_write_stage(path, 2)
        source = target.read_text(encoding="utf-8")
    if "display_rate_multiplier" not in source:
        anchor = "export interface AdminGroup extends Group {\n"
        if anchor not in source:
            raise ValueError("frontend admin group anchor was not found")
        source = source.replace(
            anchor,
            anchor
            + "  display_rate_multiplier: number | null\n"
            + "  display_token_multiplier: number | null\n",
            1,
        )
    target.write_text(source, encoding="utf-8", newline="")
    subprocess.check_call(["git", "add", path])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-ref", required=True)
    args = parser.parse_args()

    conflicted = [line for line in git("diff", "--name-only", "--diff-filter=U").splitlines() if line]
    allowed = {
        "backend/cmd/server/VERSION",
        "backend/ent/mutation.go",
        "backend/ent/runtime/runtime.go",
        "backend/internal/handler/dto/mappers.go",
        "backend/internal/handler/dto/mappers_usage_test.go",
        "backend/internal/handler/dto/types.go",
        "frontend/src/types/index.ts",
    }
    unexpected = sorted(set(conflicted) - allowed)
    if unexpected:
        print("Unexpected merge conflicts:", file=sys.stderr)
        print("\n".join(unexpected), file=sys.stderr)
        return 1
    if not conflicted:
        return 0

    if "backend/cmd/server/VERSION" in conflicted:
        git_write_stage("backend/cmd/server/VERSION", 2)
        subprocess.check_call(["git", "add", "backend/cmd/server/VERSION"])
    for path in ("backend/ent/mutation.go", "backend/ent/runtime/runtime.go"):
        if path in conflicted:
            keep_upstream_generated(path)
    if "backend/internal/handler/dto/mappers.go" in conflicted:
        merge_mapper("backend/internal/handler/dto/mappers.go", args.patched_ref)
    if "backend/internal/handler/dto/mappers_usage_test.go" in conflicted:
        merge_usage_test("backend/internal/handler/dto/mappers_usage_test.go", args.patched_ref)
    if "backend/internal/handler/dto/types.go" in conflicted:
        merge_admin_dto_types("backend/internal/handler/dto/types.go")
    if "frontend/src/types/index.ts" in conflicted:
        merge_frontend_types("frontend/src/types/index.ts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
