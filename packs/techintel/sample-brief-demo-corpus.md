# Signal brief: AI technology intelligence

> Source: a local Signal instance running its built-in **demo corpus** (synthetic articles on
> example.org), read live through the techintel MCP server. The numbers are real platform output
> for that corpus, not for the live web.

## Headline
**Agent Harness** is the fastest-rising concept on the platform: trend 92.9, impact 86.0, and
5× mention growth in 30 days. Foundation Models is the strongest category shift, with all 7
concepts rising, and Signal recommends a **trial** of Agent Harness and Durable Execution.

## Rising and falling
| Concept | Stage | Trend | 30-day growth | Impact | Maturity |
|---|---|---|---|---|---|
| Agent Harness | trending | 92.9 | +500% | 86.0 | 57.2 |
| Durable Execution | trending | 84.7 | +250% | 77.0 | 68.0 |
| Context Engineering | established | 80.9 | +54% | 81.3 | 83.2 |
| Neuro-Symbolic AI | established | 78.8 | +180% | 71.8 | 73.7 |
| LLM-as-a-Judge | established | 77.1 | +59% | 78.4 | 74.7 |
| Agent Evaluation | trending | 76.7 | +62% | 78.2 | 64.5 |
| Small Language Models | trending | 68.3 | +56% | 70.1 | 64.4 |
| Knowledge Distillation | trending | 68.3 | +56% | 70.1 | 64.4 |

**Falling:**
- Agentic RAG (adopting): trend 60.5, −29%
- Knowledge Graph Embeddings (declining): trend 0, −100%

**Category shifts:**
- Foundation Models: 7 of 7 rising
- Agentic AI: 4 of 9 rising, and the highest average trend (77.5)
- Security, Governance & Responsible AI: 2 of 2 rising
- Context Engineering: 2 of 3 rising

## Radar
- **Trending:** Agent Harness, Durable Execution, Agent Evaluation, Test-Time Compute Scaling, Vibe Coding, Small Language Models, Knowledge Distillation
- **Adopting:** Agent Memory, Agent-to-Agent Protocol, Agentic Coding, GraphRAG
- **Established:** Context Engineering, Neuro-Symbolic AI, Model Context Protocol, LLM-as-a-Judge, Retrieval-Augmented Generation, Reasoning Models, Speculative Decoding, Mixture of Experts, Tool Calling

## Recommendations
| Action | Concept | Priority | Why |
|---|---|---|---|
| **Trial** | Agent Harness | 88.8 | Growing practical adoption (trend 93, rising); validate in a pilot |
| **Adopt** | Retrieval-Augmented Generation | 81.2 | Mature (83), demonstrated implementations, impact 84 |
| **Adopt** | Context Engineering | 81.2 | Mature (83), demonstrated implementations, impact 81 |
| **Adopt** | Model Context Protocol | 80.1 | Mature (78), demonstrated implementations, impact 82 |
| **Trial** | Durable Execution | 80.1 | Growing practical adoption (trend 85, rising) |
| **Adopt** | Agent-to-Agent Protocol | 79.5 | Mature (66), demonstrated implementations, impact 81 |

The suggested experiment for each one is a time-boxed proof of concept on one internal workflow,
with explicit quality, latency and cost metrics.

## Deep dive: Agent Harness
- **Definition:** the runtime scaffolding around a model that manages the tool loop, permissions,
  context compaction, sandboxing and checkpoints for an autonomous agent.
- **Scores:** trend 92.9, impact 86.0, maturity 57.2. It's new (novelty: new): popular, but
  implementation evidence is still building.
- **Signals (7-day window):**
  - mentions: 22 (previously 15, +47%)
  - research signal: 7
  - GitHub signal: 5
  - source credibility: 0.72
  - mentions overall: 71, from 5 sources
- **Origin:** *Revisiting Agent Harness for Long-Horizon Tasks* (18 Oct 2026); popularised on 22 Oct 2026.
- **Key technical claims** from the research report (v1, confidence 0.88, review pending):
  - **Why it exists:** raw model APIs don't provide durable, safe execution for multi-step agent work [S5, S7].
  - **Architecture:** a tool loop, permissions, context compaction, sandboxing and checkpoints; practitioners often combine it with Context Engineering [S1, S5].
  - **Evidence:** studies across 10–27 tasks report gains in cost efficiency, but robustness on out-of-distribution inputs remains a challenge [S1, S2, S4].
  - **In production:** it needs careful observability, cost controls and human review for high-risk actions; reported latency fell 16–37% [S9, S11].
  - **Ecosystem:** toolkit v0.3 releases, reference implementations, and minimal implementations with 26–35 integrations [S5–S8].
- **Related (co-occurring):**
  - Durable Execution (0.88)
  - Context Engineering (0.84)
  - Agent Evaluation (0.60)
  - Agentic Coding (0.44)

## Latest reports
- Research Breakthrough Report: 20 Nov 2026
- Enterprise Technology Impact Report: 20 Nov 2026
- Monthly Technology Radar: 20 Nov 2026 (18 concepts)

## Data as of
2026-11-20 19:20 UTC