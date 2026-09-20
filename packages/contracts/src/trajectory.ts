import { z } from "zod";

export const ToolCall = z.object({
  id: z.string(),
  name: z.string(),
  args: z.record(z.string(), z.unknown()),
});

export const Step = z.object({
  index: z.number().int().nonnegative(),
  role: z.enum(["user", "assistant", "tool", "system"]),
  content: z.string().default(""),
  toolCalls: z.array(ToolCall).default([]),
  toolResult: z.string().nullable().default(null),
  latencyMs: z.number().int().nonnegative().default(0),
  inputTokens: z.number().int().default(0),
  outputTokens: z.number().int().default(0),
});

export const Trajectory = z.object({
  taskCaseId: z.string(),
  runId: z.string(),
  steps: z.array(Step),
  finalOutput: z.string(),
  terminalState: z.enum(["completed", "max_steps", "error", "refused"]),
});

export const ScoreResult = z.object({
  trajectoryId: z.string(),
  scorerKey: z.string(),
  scorerKind: z.enum(["deterministic", "programmatic", "llm_judge"]),
  value: z.number().min(0).max(1),
  passed: z.boolean(),
  confidence: z.number().min(0).max(1),
  rationale: z.string().nullable(),
  costUsd: z.number().default(0),
  latencyMs: z.number().int().default(0),
});

export type ToolCall = z.infer<typeof ToolCall>;
export type Step = z.infer<typeof Step>;
export type Trajectory = z.infer<typeof Trajectory>;
export type ScoreResult = z.infer<typeof ScoreResult>;