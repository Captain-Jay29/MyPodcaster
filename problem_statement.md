# Take-Home Project: Generating Accurate, Engaging Audio Summaries

This README captures the take-home project brief shared ahead of the technical interview.

---

## Context

Many people enjoy *Google NotebookLM*-style “podcast” summaries, and short audio briefings can make commute time more productive.

The idea: **pre-create short audio summaries (one per article / document)** that can be queued up and listened to during a commute to get briefed for the day.

---

## Product Goal

Build something **useful** that requires:
- creativity
- experimentation
- more sophisticated use of AI than typical “getting started” tutorials

There isn’t a single “right answer.” The **journey and process** matter—feel free to question the assumptions in the brief.

---

## Inputs (Assumed Available)

Assume that **all documents are already extracted** and available as text/content to your system.

Example sources to prioritize:
1. **Documents associated with meetings on my calendar today**
2. **Documents shared with me in the last 24 hours**, especially those highlighted in email
3. **Articles emailed to me by people I trust**
4. **Highly ranked industry news articles** (e.g., *Hacker News*)

---

## Output Requirements

For each selected article/doc, generate **one short audio summary** that is:

- **Informative**: captures key points, decisions, and “what to do with this”
- **Engaging**: pleasant to listen to, well-structured, not monotone
- **Accurate**: faithful to the source; avoids hallucinations and over-claims

> Note: The end result **probably shouldn’t be a two-host podcast**, but the starter repo is a helpful jump-off point.

---

## Starting Point Codebase

Use the open-source podcast generator below as the starting point:

- https://github.com/knowsuchagency/pdf-to-podcast

You’re free to refactor/replace components as needed to better fit the single-summary-per-doc experience.

---

## Suggested Approach (Non-Prescriptive)

You can treat this as a mini “product + applied AI” exercise:

### 1) Selection & Ranking
- Define a ranking strategy for which documents to summarize first (calendar relevance, recency, trusted senders, HN rank, etc.).
- Consider a “daily queue” that produces a small set of summaries.

### 2) Summarization Strategy
- Determine the target format (e.g., 60–180 seconds per doc).
- Consider structure like:
  - headline + why it matters
  - 3–5 key takeaways
  - actions / decisions / open questions
  - caveats and uncertainties

### 3) Accuracy Controls
- Encourage groundedness: cite sections, verify claims, avoid adding facts.
- Consider “self-check” passes, constrained generation, or retrieval snippets.

### 4) Audio Generation
- Convert the final summary text into audio.
- Optimize for listenability: pacing, emphasis, short sentences.

### 5) Evaluation
Define how you’ll measure:
- **Accuracy** (faithfulness to source)
- **Coverage** (did it include the most important points?)
- **Engagement** (does it sound good / flow well?)
- **Usefulness** (would someone actually listen daily?)

You can use lightweight human evaluation, rubrics, or small automated checks.

---

## What to Prepare for Pairing

Please spend as much time as you like understanding the codebase and thinking through how you’d build and evaluate the product (expected to be **≤ 1 hour** for prep).

### High-Level Log (Requested)
Keep a brief log of what you did ahead of time so we can quickly align when pairing.

You can use this template:

```text
## Prep Log

- Date/Time:
- Repo exploration:
  - Notes on architecture / flow:
  - Key files/modules:
- Proposed product changes:
  - Summary format:
  - Doc selection/ranking:
  - Accuracy approach:
  - Audio approach:
- Experiments run (if any):
  - Inputs:
  - Outputs:
  - Observations:
- Open questions / tradeoffs:
```

---

## Interview Notes

- Two technical interviews on Friday.
- Both are project-style, and you may use your IDE and AI tools of choice.
- Most candidates use their own computer; a provided machine is possible if needed.
- Interview 1: new project (no prep needed).
- Interview 2: this take-home project brief (pairing + discussion).

---
