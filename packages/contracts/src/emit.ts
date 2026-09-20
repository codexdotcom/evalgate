import { writeFileSync, mkdirSync } from "node:fs";
import { z } from "zod";
import { Trajectory, ScoreResult } from "./trajectory.js";

const schemas: Record<string, z.ZodType> = { Trajectory, ScoreResult };

mkdirSync("dist/schema", { recursive: true });

for (const [name, schema] of Object.entries(schemas)) {
  const json = z.toJSONSchema(schema, { io: "input" });
  writeFileSync(`dist/schema/${name}.json`, JSON.stringify(json, null, 2));
  console.log(`wrote dist/schema/${name}.json`);
}