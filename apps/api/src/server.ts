import { createYoga } from "graphql-yoga";
import { createServer } from "node:http";
import "dotenv/config";
import { PrismaClient, Prisma } from "./generated/prisma/client.js";
import { PrismaPg } from "@prisma/adapter-pg";
import SchemaBuilder from "@pothos/core";
import PrismaPlugin from "@pothos/plugin-prisma";
import { GraphQLJSON } from "graphql-scalars";

import type PrismaTypes from "./generated/pothos-types.js";
import { getDatamodel } from "./generated/pothos-types.js";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL! });
const prisma = new PrismaClient({ adapter });

const builder = new SchemaBuilder<{
  PrismaTypes: PrismaTypes;
  Scalars: {
    JSON: { Input: unknown; Output: unknown };
  };
}>({
  plugins: [PrismaPlugin],
  prisma: {
    client: prisma,
    dmmf: getDatamodel(),
  },
});

builder.addScalarType("JSON", GraphQLJSON);

/* ------------------------------------------------------------------ *
 * Row shapes for raw SQL.
 *
 * $queryRaw cannot validate the shape it returns, so the casts below are
 * an assertion boundary: the SQL is the source of truth, not the type.
 * ------------------------------------------------------------------ */

interface ScoreSummaryRow {
  scorerKey: string;
  scorerKind: string;
  total: number;
  passed: number;
  avgConfidence: number;
  costUsd: number;
}

interface CalibrationPairRow {
  scorerKey: string;
  judge: boolean;
  human: boolean;
}

interface QueueStatsRow {
  pending: number;
  labeled: number;
  byReason: string;
}

/* ------------------------------------------------------------------ *
 * Object types
 * ------------------------------------------------------------------ */

builder.prismaObject("Run", {
  fields: (t) => ({
    id: t.exposeID("id"),
    model: t.exposeString("model"),
    status: t.string({ resolve: (r) => r.status }),
    totalCases: t.exposeInt("totalCases"),
    doneCases: t.exposeInt("doneCases"),
    costUsd: t.exposeFloat("costUsd"),
    startedAt: t.string({ resolve: (r) => r.startedAt.toISOString() }),
    finishedAt: t.string({
      nullable: true,
      resolve: (r) => r.finishedAt?.toISOString() ?? null,
    }),
    trajectories: t.relation("trajectories"),
    calibrations: t.relation("calibrations"),
  }),
});

builder.prismaObject("TaskCase", {
  fields: (t) => ({
    id: t.exposeID("id"),
    externalId: t.exposeString("externalId"),
    prompt: t.exposeString("prompt"),
    rubric: t.exposeString("rubric", { nullable: true }),
    tags: t.exposeStringList("tags"),
  }),
});

builder.prismaObject("Trajectory", {
  fields: (t) => ({
    id: t.exposeID("id"),
    status: t.string({ resolve: (tr) => tr.status }),
    steps: t.field({ type: "JSON", resolve: (tr) => tr.steps }),
    finalOutput: t.exposeString("finalOutput"),
    terminalState: t.exposeString("terminalState", { nullable: true }),
    latencyMs: t.exposeInt("latencyMs"),
    costUsd: t.exposeFloat("costUsd"),
    attempt: t.exposeInt("attempt"),
    error: t.exposeString("error", { nullable: true }),
    scores: t.relation("scores"),
    taskCase: t.relation("taskCase"),
    review: t.relation("review", { nullable: true }),
  }),
});

builder.prismaObject("Score", {
  fields: (t) => ({
    id: t.exposeID("id"),
    scorerKey: t.exposeString("scorerKey"),
    scorerKind: t.exposeString("scorerKind"),
    value: t.exposeFloat("value"),
    passed: t.exposeBoolean("passed"),
    confidence: t.exposeFloat("confidence"),
    rationale: t.exposeString("rationale", { nullable: true }),
    costUsd: t.exposeFloat("costUsd"),
  }),
});

builder.prismaObject("Review", {
  fields: (t) => ({
    id: t.exposeID("id"),
    reason: t.string({ resolve: (r) => r.reason }),
    humanPassed: t.exposeBoolean("humanPassed", { nullable: true }),
    reviewer: t.exposeString("reviewer", { nullable: true }),
    note: t.exposeString("note", { nullable: true }),
    blind: t.exposeBoolean("blind"),
    reviewedAt: t.string({
      nullable: true,
      resolve: (r) => r.reviewedAt?.toISOString() ?? null,
    }),
  }),
});

builder.prismaObject("Calibration", {
  fields: (t) => ({
    id: t.exposeID("id"),
    scorerKey: t.exposeString("scorerKey"),
    n: t.exposeInt("n"),
    agreement: t.exposeFloat("agreement"),
    kappa: t.exposeFloat("kappa"),
    falsePass: t.exposeInt("falsePass"),
    falseFail: t.exposeInt("falseFail"),
    computedAt: t.string({ resolve: (c) => c.computedAt.toISOString() }),
  }),
});

/* ------------------------------------------------------------------ *
 * Plain object refs (aggregates, not Prisma models)
 * ------------------------------------------------------------------ */

const ScoreSummary = builder
  .objectRef<ScoreSummaryRow>("ScoreSummary")
  .implement({
    fields: (t) => ({
      scorerKey: t.exposeString("scorerKey"),
      scorerKind: t.exposeString("scorerKind"),
      total: t.exposeInt("total"),
      passed: t.exposeInt("passed"),
      passRate: t.float({ resolve: (s) => (s.total ? s.passed / s.total : 0) }),
      avgConfidence: t.exposeFloat("avgConfidence"),
      costUsd: t.exposeFloat("costUsd"),
    }),
  });

const QueueStats = builder.objectRef<QueueStatsRow>("QueueStats").implement({
  fields: (t) => ({
    pending: t.exposeInt("pending"),
    labeled: t.exposeInt("labeled"),
    byReason: t.exposeString("byReason"),
  }),
});

/* ------------------------------------------------------------------ *
 * Queries
 * ------------------------------------------------------------------ */

builder.queryType({
  fields: (t) => ({
    runs: t.prismaField({
      type: ["Run"],
      args: { limit: t.arg.int({ defaultValue: 20 }) },
      resolve: (q, _root, args) =>
        prisma.run.findMany({
          ...q,
          orderBy: { startedAt: "desc" },
          take: args.limit ?? 20,
        }),
    }),

    run: t.prismaField({
      type: "Run",
      args: { id: t.arg.string({ required: true }) },
      resolve: (q, _root, args) =>
        prisma.run.findUniqueOrThrow({ ...q, where: { id: args.id } }),
    }),

    trajectory: t.prismaField({
      type: "Trajectory",
      args: { id: t.arg.string({ required: true }) },
      resolve: (q, _root, args) =>
        prisma.trajectory.findUniqueOrThrow({ ...q, where: { id: args.id } }),
    }),

    // Stable ordering matters: the reviewer holds a local cursor into this
    // list, and an unordered refetch would shuffle rows under them.
    reviewQueue: t.prismaField({
      type: ["Trajectory"],
      args: {
        limit: t.arg.int({ defaultValue: 50 }),
        runId: t.arg.string(),
      },
      resolve: (q, _root, args) =>
        prisma.trajectory.findMany({
          ...q,
          where: {
            review: { is: { humanPassed: null } },
            ...(args.runId ? { runId: args.runId } : {}),
          },
          orderBy: { id: "asc" },
          take: args.limit ?? 50,
        }),
    }),

    scoreSummary: t.field({
      type: [ScoreSummary],
      args: { runId: t.arg.string({ required: true }) },
      resolve: async (_root, args) =>
        (await prisma.$queryRaw(Prisma.sql`
          SELECT s."scorerKey",
                 MIN(s."scorerKind")                              AS "scorerKind",
                 COUNT(*)::int                                    AS total,
                 SUM(CASE WHEN s.passed THEN 1 ELSE 0 END)::int   AS passed,
                 COALESCE(AVG(s.confidence), 0)::float            AS "avgConfidence",
                 COALESCE(SUM(s."costUsd"), 0)::float             AS "costUsd"
          FROM "Score" s
          JOIN "Trajectory" t ON t.id = s."trajectoryId"
          WHERE t."runId" = ${args.runId}
          GROUP BY s."scorerKey"
          ORDER BY s."scorerKey"
        `)) as ScoreSummaryRow[],
    }),

    calibrations: t.prismaField({
      type: ["Calibration"],
      args: { runId: t.arg.string({ required: true }) },
      resolve: (q, _root, args) =>
        prisma.calibration.findMany({
          ...q,
          where: { runId: args.runId },
          orderBy: { kappa: "asc" },
        }),
    }),

    queueStats: t.field({
      type: QueueStats,
      args: { runId: t.arg.string() },
      resolve: async (_root, args) => {
        const where = args.runId ? { trajectory: { runId: args.runId } } : {};
        const [pending, labeled, grouped] = await Promise.all([
          prisma.review.count({ where: { ...where, humanPassed: null } }),
          prisma.review.count({
            where: { ...where, NOT: { humanPassed: null } },
          }),
          prisma.review.groupBy({
            by: ["reason"],
            where: { ...where, humanPassed: null },
            _count: { _all: true },
          }),
        ]);
        return {
          pending,
          labeled,
          byReason: grouped
            .map((g) => `${g.reason}:${g._count._all}`)
            .join(" "),
        };
      },
    }),
  }),
});

/* ------------------------------------------------------------------ *
 * Mutations
 * ------------------------------------------------------------------ */

builder.mutationType({
  fields: (t) => ({
    startRun: t.prismaField({
      type: "Run",
      args: {
        suiteSlug: t.arg.string({ required: true }),
        model: t.arg.string({ required: true }),
        concurrency: t.arg.int({ defaultValue: 8 }),
      },
      resolve: async (q, _root, args) => {
        const suite = await prisma.suite.findUniqueOrThrow({
          where: { slug: args.suiteSlug },
          include: { cases: { select: { id: true } } },
        });

        // Creating the Trajectory rows IS the enqueue. Workers claim
        // status=QUEUED rows with FOR UPDATE SKIP LOCKED.
        const run = await prisma.run.create({
          data: {
            suiteId: suite.id,
            model: args.model,
            config: { concurrency: args.concurrency ?? 8 },
            totalCases: suite.cases.length,
            status: "RUNNING",
            trajectories: {
              create: suite.cases.map((c: { id: string }) => ({
                taskCaseId: c.id,
              })),
            },
          },
        });

        return prisma.run.findUniqueOrThrow({ ...q, where: { id: run.id } });
      },
    }),

    // upsert, not update: once you sample passing trajectories for
    // calibration, you will label rows that have no Review yet.
    submitReview: t.prismaField({
      type: "Review",
      args: {
        trajectoryId: t.arg.string({ required: true }),
        humanPassed: t.arg.boolean({ required: true }),
        reviewer: t.arg.string({ required: true }),
        note: t.arg.string(),
        blind: t.arg.boolean({ defaultValue: false }),
      },
      resolve: (q, _root, args) =>
        prisma.review.upsert({
          ...q,
          where: { trajectoryId: args.trajectoryId },
          create: {
            trajectoryId: args.trajectoryId,
            reason: "SAMPLED",
            humanPassed: args.humanPassed,
            reviewer: args.reviewer,
            note: args.note ?? null,
            blind: args.blind ?? false,
            reviewedAt: new Date(),
          },
          update: {
            humanPassed: args.humanPassed,
            reviewer: args.reviewer,
            note: args.note ?? null,
            blind: args.blind ?? false,
            reviewedAt: new Date(),
          },
        }),
    }),

    // Derived read model, recomputed on demand. n is in the hundreds and the
    // query is one join, so incremental maintenance would buy nothing but bugs.
    recomputeCalibration: t.prismaField({
      type: ["Calibration"],
      args: {
        runId: t.arg.string({ required: true }),
        blindOnly: t.arg.boolean({ defaultValue: false }),
      },
      resolve: async (q, _root, args) => {
        // Compose the optional predicate as SQL rather than binding a bare
        // boolean, which Postgres cannot type-infer in this position.
        const blindFilter = args.blindOnly
          ? Prisma.sql`AND r.blind = true`
          : Prisma.empty;

        const rows = (await prisma.$queryRaw(Prisma.sql`
          SELECT s."scorerKey", s.passed AS judge, r."humanPassed" AS human
          FROM "Score" s
          JOIN "Trajectory" t ON t.id = s."trajectoryId"
          JOIN "Review" r     ON r."trajectoryId" = t.id
          WHERE t."runId" = ${args.runId}
            AND r."humanPassed" IS NOT NULL
            ${blindFilter}
        `)) as CalibrationPairRow[];

        const byScorer = new Map<string, CalibrationPairRow[]>();
        for (const r of rows) {
          const bucket = byScorer.get(r.scorerKey) ?? [];
          bucket.push(r);
          byScorer.set(r.scorerKey, bucket);
        }

        const out = [];
        for (const [scorerKey, pairs] of byScorer) {
          const n = pairs.length;
          const po = pairs.filter((p) => p.judge === p.human).length / n;
          const pj = pairs.filter((p) => p.judge).length / n;
          const ph = pairs.filter((p) => p.human).length / n;
          const pe = pj * ph + (1 - pj) * (1 - ph);
          const kappa = pe === 1 ? 0 : (po - pe) / (1 - pe);
          const falsePass = pairs.filter((p) => p.judge && !p.human).length;
          const falseFail = pairs.filter((p) => !p.judge && p.human).length;

          out.push(
            await prisma.calibration.upsert({
              ...q,
              where: { runId_scorerKey: { runId: args.runId, scorerKey } },
              create: {
                runId: args.runId,
                scorerKey,
                n,
                agreement: po,
                kappa,
                falsePass,
                falseFail,
              },
              update: {
                n,
                agreement: po,
                kappa,
                falsePass,
                falseFail,
                computedAt: new Date(),
              },
            }),
          );
        }
        return out;
      },
    }),
  }),
});

const yoga = createYoga({ schema: builder.toSchema() });
createServer(yoga).listen(4000, () =>
  console.log("api on http://localhost:4000/graphql"),
);