-- CreateEnum
CREATE TYPE "RunStatus" AS ENUM ('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED');

-- CreateEnum
CREATE TYPE "TrajStatus" AS ENUM ('QUEUED', 'RUNNING', 'SCORED', 'FAILED');

-- CreateEnum
CREATE TYPE "ReviewReason" AS ENUM ('LOW_CONFIDENCE', 'SCORER_DISAGREEMENT', 'SAMPLED');

-- CreateTable
CREATE TABLE "Suite" (
    "id" TEXT NOT NULL,
    "slug" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "version" INTEGER NOT NULL DEFAULT 1,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Suite_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "TaskCase" (
    "id" TEXT NOT NULL,
    "suiteId" TEXT NOT NULL,
    "externalId" TEXT NOT NULL,
    "prompt" TEXT NOT NULL,
    "expected" JSONB,
    "rubric" TEXT,
    "tags" TEXT[],

    CONSTRAINT "TaskCase_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Run" (
    "id" TEXT NOT NULL,
    "suiteId" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "config" JSONB NOT NULL,
    "status" "RunStatus" NOT NULL DEFAULT 'QUEUED',
    "totalCases" INTEGER NOT NULL DEFAULT 0,
    "doneCases" INTEGER NOT NULL DEFAULT 0,
    "costUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "startedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" TIMESTAMP(3),

    CONSTRAINT "Run_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Trajectory" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "taskCaseId" TEXT NOT NULL,
    "status" "TrajStatus" NOT NULL DEFAULT 'QUEUED',
    "steps" JSONB NOT NULL DEFAULT '[]',
    "finalOutput" TEXT NOT NULL DEFAULT '',
    "terminalState" TEXT,
    "latencyMs" INTEGER NOT NULL DEFAULT 0,
    "inputTokens" INTEGER NOT NULL DEFAULT 0,
    "outputTokens" INTEGER NOT NULL DEFAULT 0,
    "costUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "attempt" INTEGER NOT NULL DEFAULT 0,
    "error" TEXT,

    CONSTRAINT "Trajectory_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Score" (
    "id" TEXT NOT NULL,
    "trajectoryId" TEXT NOT NULL,
    "scorerKey" TEXT NOT NULL,
    "scorerKind" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "passed" BOOLEAN NOT NULL,
    "confidence" DOUBLE PRECISION NOT NULL,
    "rationale" TEXT,
    "costUsd" DOUBLE PRECISION NOT NULL DEFAULT 0,

    CONSTRAINT "Score_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Review" (
    "id" TEXT NOT NULL,
    "trajectoryId" TEXT NOT NULL,
    "reason" "ReviewReason" NOT NULL,
    "humanPassed" BOOLEAN,
    "reviewer" TEXT,
    "note" TEXT,
    "reviewedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Review_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Calibration" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "scorerKey" TEXT NOT NULL,
    "n" INTEGER NOT NULL,
    "agreement" DOUBLE PRECISION NOT NULL,
    "kappa" DOUBLE PRECISION NOT NULL,
    "falsePass" INTEGER NOT NULL,
    "falseFail" INTEGER NOT NULL,
    "computedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Calibration_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "Suite_slug_key" ON "Suite"("slug");

-- CreateIndex
CREATE UNIQUE INDEX "TaskCase_suiteId_externalId_key" ON "TaskCase"("suiteId", "externalId");

-- CreateIndex
CREATE INDEX "Run_suiteId_startedAt_idx" ON "Run"("suiteId", "startedAt");

-- CreateIndex
CREATE INDEX "Trajectory_runId_status_idx" ON "Trajectory"("runId", "status");

-- CreateIndex
CREATE UNIQUE INDEX "Trajectory_runId_taskCaseId_key" ON "Trajectory"("runId", "taskCaseId");

-- CreateIndex
CREATE INDEX "Score_scorerKey_passed_idx" ON "Score"("scorerKey", "passed");

-- CreateIndex
CREATE UNIQUE INDEX "Score_trajectoryId_scorerKey_key" ON "Score"("trajectoryId", "scorerKey");

-- CreateIndex
CREATE UNIQUE INDEX "Review_trajectoryId_key" ON "Review"("trajectoryId");

-- CreateIndex
CREATE INDEX "Review_humanPassed_createdAt_idx" ON "Review"("humanPassed", "createdAt");

-- CreateIndex
CREATE UNIQUE INDEX "Calibration_runId_scorerKey_key" ON "Calibration"("runId", "scorerKey");

-- AddForeignKey
ALTER TABLE "TaskCase" ADD CONSTRAINT "TaskCase_suiteId_fkey" FOREIGN KEY ("suiteId") REFERENCES "Suite"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Run" ADD CONSTRAINT "Run_suiteId_fkey" FOREIGN KEY ("suiteId") REFERENCES "Suite"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Trajectory" ADD CONSTRAINT "Trajectory_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Trajectory" ADD CONSTRAINT "Trajectory_taskCaseId_fkey" FOREIGN KEY ("taskCaseId") REFERENCES "TaskCase"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Score" ADD CONSTRAINT "Score_trajectoryId_fkey" FOREIGN KEY ("trajectoryId") REFERENCES "Trajectory"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Review" ADD CONSTRAINT "Review_trajectoryId_fkey" FOREIGN KEY ("trajectoryId") REFERENCES "Trajectory"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Calibration" ADD CONSTRAINT "Calibration_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
