"""Structured outputs exchanged between workflow nodes."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StepInput(BaseModel):
  name: str = Field(description="Input parameter name declared by the procedure.")
  value: str = Field(description="Literal value taken from the user's question.")


class PlanStep(BaseModel):
  id: str = Field(description="Short unique step id, e.g. s1, s2.")
  procedure: str = Field(
      description="Exact procedure name from the catalog, or 'adhoc' when no procedure fits."
  )
  inputs: list[StepInput] = Field(default_factory=list)
  depends_on: list[str] = Field(
      default_factory=list, description="Step ids whose outputs this step needs."
  )
  purpose: str = Field(default="", description="Why this step is needed (one line).")


class Plan(BaseModel):
  intent: str = Field(description="The user's goal in a few words.")
  domain: str = Field(default="general")
  steps: list[PlanStep] = Field(default_factory=list)
  answer_strategy: str = Field(
      default="", description="How the final answer should combine the step results."
  )


class Verdict(BaseModel):
  ok: bool = Field(description="True when the draft fully and correctly answers the question.")
  score: float = Field(description="Quality from 0.0 to 1.0.")
  issues: list[str] = Field(default_factory=list)
  missing_data: bool = Field(
      default=False,
      description="True when the plan failed to fetch data the answer needs (re-plan).",
  )
