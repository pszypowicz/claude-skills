---
name: house-style
description: Audit prose written in the user's voice for the patterns that mark text as machine-generated. Use when drafting or revising a pull request description, a pull request or issue comment, a review reply, a release note, a README section, a commit message body, or a blog post. Covers sentence shape and structure, which a pattern matcher cannot judge. The house-style hook already covers single characters and single words, so this skill does not repeat them.
---

# house-style

Six patterns give away machine-written prose. Each one has a plain rewrite.

## 1. Counter-factual contrast

Bad: "It is not a cache, it is an index."
Good: "It is an index."

State the thing. The reader never proposed the alternative.

## 2. The larger-goal construction

Bad: "The ambition is larger: one pipeline for every region."
Good: "The goal is one pipeline for every region."

## 3. The dramatic pause

Bad: "The retry exists in the client; in practice it never fires."
Good: "The client has a retry, but it never fires."

## 4. Punchy fragments

Bad: "Keep the signal. Govern the response."
Good: "Keep the signal and govern the response."

Write full sentences, joined by ordinary conjunctions.

## 5. Clever section headers

Bad: "The plot thickens", "Enter the dragon".
Good: "What I measured", "Root cause".

## 6. Decorative colons and semicolons

Bad: "The build failed; the cache was stale."
Good: "The build failed because the cache was stale."

Use "and", "but", "because", "although", or "so".

## Prefer plain words

In running prose, "for example" reads better than the abbreviation.

## How to run the audit

Read the draft once for each pattern. Rewrite every hit. Then read the draft aloud in your head. A sentence you cannot say in one breath needs a split.
