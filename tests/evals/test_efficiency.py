"""Surface 2: Operational efficiency evals — tool calls, tokens, latency."""

import pytest

# ──────────────────────────────────────────────
# Tool call metrics
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_search_call_count(agent_trace):
    """Agent should make 1-5 search_hn calls."""
    search_calls = [tc for tc in agent_trace.tool_calls if tc.name == "search_hn"]
    count = len(search_calls)
    assert 1 <= count <= 5, f"Agent made {count} search_hn calls (expected 1-5)"
    if count > 3:
        pytest.warns(UserWarning, match="")  # noqa: PT023
        print(f"  WARNING: {count} search calls is above recommended 3")


@pytest.mark.eval
def test_read_call_count(agent_trace):
    """Agent should read at least 3 articles."""
    read_calls = [tc for tc in agent_trace.tool_calls if tc.name == "read_url"]
    count = len(read_calls)
    assert count >= 3, f"Agent only read {count} URLs (expected >= 3)"


@pytest.mark.eval
def test_no_duplicate_reads(agent_trace):
    """Agent should not read the same URL twice."""
    read_urls = [tc.args["url"] for tc in agent_trace.tool_calls if tc.name == "read_url"]
    duplicates = [url for url in read_urls if read_urls.count(url) > 1]
    assert not duplicates, f"Duplicate read_url calls: {set(duplicates)}"


# ──────────────────────────────────────────────
# Turn metrics
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_turn_count(agent_trace):
    """Agent should finish within 10 turns."""
    count = len(agent_trace.turns)
    assert count <= 10, f"Agent used {count} turns (limit: 10)"


@pytest.mark.eval
def test_articles_produced(agent_trace):
    """Agent should produce at least 3 articles."""
    count = len(agent_trace.script.articles)
    assert count >= 3, f"Agent produced only {count} articles (expected >= 3)"


# ──────────────────────────────────────────────
# Token metrics
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_total_token_budget(agent_trace):
    """Total tokens should stay under 80K."""
    total = agent_trace.total_tokens
    assert total <= 80_000, f"Total tokens {total:,} exceeds 80K budget"


@pytest.mark.eval
def test_token_growth_curve(agent_trace, capsys):
    """Report cumulative token growth per turn to identify bottlenecks."""
    turns = agent_trace.turns

    # Build the report table
    lines = [
        "",
        "=" * 78,
        "CUMULATIVE TOKEN GROWTH",
        "=" * 78,
        f"{'Turn':>4} | {'Prompt':>8} | {'Completion':>10} | {'Turn Total':>10} | "
        f"{'Cumulative':>10} | {'Tool Calls':>10}",
        "-" * 78,
    ]

    for t in turns:
        # Describe tool calls for this turn
        tool_desc = f"{t.tool_call_count} call(s)" if t.tool_call_count > 0 else "(finalize)"

        lines.append(
            f"{t.turn_num:>4} | {t.prompt_tokens:>8,} | {t.completion_tokens:>10,} | "
            f"{t.total_tokens:>10,} | {t.cumulative_tokens:>10,} | {tool_desc:>10}"
        )

    # Identify the biggest token jump
    if len(turns) >= 2:
        biggest_jump = max(
            turns[1:],
            key=lambda t: t.total_tokens,
        )
        lines.append("-" * 78)
        lines.append(
            f"Bottleneck: Turn {biggest_jump.turn_num} "
            f"({biggest_jump.total_tokens:,} tokens, "
            f"{biggest_jump.prompt_tokens:,} prompt + "
            f"{biggest_jump.completion_tokens:,} completion)"
        )

    lines.append(f"Total: {agent_trace.total_tokens:,} tokens across {len(turns)} turns")
    lines.append("=" * 78)

    report = "\n".join(lines)
    print(report)

    # Also check input/output ratio — if completion tokens are > 50% of total,
    # the agent is generating too much text relative to what it reads
    total_prompt = sum(t.prompt_tokens for t in turns)
    total_completion = sum(t.completion_tokens for t in turns)
    if total_prompt > 0:
        ratio = total_completion / total_prompt
        print(f"\nCompletion/Prompt ratio: {ratio:.2f} "
              f"({total_completion:,} completion / {total_prompt:,} prompt)")

    # This test always passes — it's a reporting test
    assert len(turns) > 0, "No turns recorded"


# ──────────────────────────────────────────────
# Latency metrics (report only)
# ──────────────────────────────────────────────


@pytest.mark.eval
def test_latency_report(agent_trace, capsys):
    """Report latency breakdown. No assertions — API latency is too variable."""
    lines = [
        "",
        "=" * 78,
        "LATENCY REPORT",
        "=" * 78,
        f"Wall clock: {agent_trace.wall_clock_s:.1f}s",
        "",
        "Per-turn latency:",
    ]

    for t in agent_trace.turns:
        lines.append(f"  Turn {t.turn_num}: {t.latency_ms:,.0f}ms")

    lines.append("")
    lines.append("Per-tool-call latency:")
    for tc in agent_trace.tool_calls:
        url_snippet = ""
        if tc.name == "read_url":
            url = tc.args.get("url", "")
            url_snippet = f" ({url[:50]}...)" if len(url) > 50 else f" ({url})"
        lines.append(
            f"  {tc.name}{url_snippet}: {tc.latency_ms:.0f}ms, {tc.result_chars:,} chars"
        )

    lines.append("=" * 78)

    print("\n".join(lines))

    # Always passes — purely informational
    assert agent_trace.wall_clock_s > 0
