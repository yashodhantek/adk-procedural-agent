# Signal (techintel) procedure pack

Procedure and term cards for the Signal AI technology intelligence platform, read through
the techintel MCP server (`techintel_mcp.py`). Ingest with:

    python scripts/ingest.py packs/techintel/procedures.md --apply --approve all

## Term: Signal
Kind: concept
Aliases: techintel, tech intel, intel platform, intelligence platform, tech radar platform
Definition: YashodhanTek's AI technology intelligence platform: it discovers emerging AI concepts, scores trend, impact and maturity (0-100), keeps a technology radar and writes research reports with evidence.
Related: techintel_brief, techintel_trends

## Term: hot topics
Kind: concept
Aliases: what's hot, what is hot, trending tech, emerging tech, rising technologies, latest ai trends, ai trends
Definition: Concepts whose trend score and 30-day mention growth are rising.
Related: techintel_trends, techintel_radar, techintel_brief

## Procedure: techintel_trends
Description: Live AI technology trends from Signal: top, rising and falling concepts with 30-day growth, category averages and category shifts.
Domain: techintel
Outputs: top, rising, falling, by_category, shifts, as_of
MCP: techintel.get_trends limit=8
Required: rising

## Procedure: techintel_radar
Description: Signal's live technology radar: which concepts sit in which ring and quadrant, with scores and direction.
Domain: techintel
Outputs: rings, entries
MCP: techintel.get_radar limit=20
Required: rings

## Procedure: techintel_recommendations
Description: Signal's adopt / trial / assess / hold recommendations with rationale and a suggested experiment.
Domain: techintel
Outputs: recommendations, generated_at
MCP: techintel.get_recommendations limit=6
Extract: recommendations = items; generated_at = generated_at
Required: recommendations

## Procedure: techintel_top_concepts
Description: The highest-trending AI concepts on Signal right now.
Domain: techintel
Outputs: concepts, top_slug
MCP: techintel.list_concepts sort=-trend_score limit=5
Extract: concepts = items; top_slug = top_slug
Required: top_slug

## Procedure: techintel_concept_details
Description: Technical detail on one AI concept from Signal: definition, scores and signals, origin, related concepts, research claims and evidence.
Domain: techintel
Inputs: slug
Outputs: concept
MCP: techintel.get_concept slug={slug}
Extract: concept = .
Required: concept

## Procedure: techintel_top_concept_details
Description: Technical deep-dive on the top trending concept right now (definition, signals, research claims, evidence).
Domain: techintel
Inputs: slug
Outputs: concept
Needs: techintel_top_concepts (slug->top_slug)
MCP: techintel.get_concept slug={slug}
Extract: concept = .
Required: concept

## Procedure: techintel_reports
Description: Signal's latest generated reports (research breakthroughs, enterprise impact, comparisons).
Domain: techintel
Outputs: reports
MCP: techintel.list_reports limit=3
Extract: reports = items

## Procedure: techintel_brief
Description: Summary of the latest AI technology intelligence from Signal with the important technical details: what is rising or falling, radar positions, recommendations, latest reports and a technical deep-dive on the top concept.
Domain: techintel
Outputs: brief_md
Needs: techintel_trends; techintel_radar; techintel_recommendations; techintel_top_concept_details; techintel_reports
LLM: You are writing a technology intelligence brief for an AI architect. Using ONLY the data below, write Markdown with these sections: "## Headline" (2 sentences), "## Rising and falling" (bullets with trend score and 30-day growth as %), "## Radar" (concepts per ring), "## Recommendations" (action, concept, one-line rationale), "## Deep dive: <top concept>" (definition, scores, signals, 3-5 key technical claims with their citation keys, origin, related concepts), "## Latest reports" (titles), and "## Data as of" ({as_of}). Never invent numbers. DATA: rising={rising} falling={falling} shifts={shifts} radar={rings} recommendations={recommendations} top_concept={concept} reports={reports}
Steps:
1. Fetch trends, radar, recommendations, reports and the top concept's details in parallel (the details need the top concept first).
2. Summarise them into a Markdown brief with the technical details.

## Procedure: techintel_save_brief
Description: Save today's Signal brief as a Markdown file on this machine (asks for approval first).
Domain: techintel
Inputs: brief_md
Outputs: saved
Needs: techintel_brief (brief_md->brief_md)
MCP: techintel.save_brief markdown={brief_md} title="Signal brief"
Side effect: write

## Procedure: techintel_email_brief
Description: Email today's Signal brief. Used by the daily schedule; unattended runs need a standing approval for the exact recipients.
Domain: techintel
Inputs: brief_md, to
Outputs: sent
Needs: techintel_brief (brief_md->brief_md)
MCP: mail.send_email to={to} subject="Signal brief" markdown={brief_md}
Side effect: write
