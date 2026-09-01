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
    match = re.search(rf"(?m)^func {re.escape(name)}\([^\n]*\) \{{", source)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-ref", required=True)
    args = parser.parse_args()

    conflicted = [line for line in git("diff", "--name-only", "--diff-filter=U").splitlines() if line]
    allowed = {
        "backend/cmd/server/VERSION",
        "backend/internal/handler/dto/mappers.go",
        "backend/internal/handler/dto/mappers_usage_test.go",
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
    if "backend/internal/handler/dto/mappers.go" in conflicted:
        merge_mapper("backend/internal/handler/dto/mappers.go", args.patched_ref)
    if "backend/internal/handler/dto/mappers_usage_test.go" in conflicted:
        merge_usage_test("backend/internal/handler/dto/mappers_usage_test.go", args.patched_ref)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
