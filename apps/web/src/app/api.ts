import { createApi } from "@reduxjs/toolkit/query/react";
import { graphqlRequestBaseQuery } from "@rtk-query/graphql-request-base-query";
import { gql } from "graphql-request";

export interface SubmitReviewArgs {
  trajectoryId: string;
  humanPassed: boolean;
  reviewer: string;
  blind: boolean;
  note?: string;
}

export const api = createApi({
  reducerPath: "api",
  baseQuery: graphqlRequestBaseQuery({ url: "/graphql" }),
  tagTypes: ["Run", "Review", "Calibration"],
  endpoints: (b) => ({
    runs: b.query<{ runs: any[] }, void>({
      query: () => ({
        document: gql`
          {
            runs(limit: 20) {
              id
              model
              status
              totalCases
              doneCases
              costUsd
              startedAt
            }
          }
        `,
      }),
      providesTags: ["Run"],
    }),

    runDetail: b.query<any, string>({
      query: (runId) => ({
        document: gql`
          query RunDetail($runId: String!) {
            run(id: $runId) {
              id
              model
              status
              totalCases
              doneCases
              costUsd
            }
            scoreSummary(runId: $runId) {
              scorerKey
              scorerKind
              total
              passed
              passRate
              avgConfidence
              costUsd
            }
            calibrations(runId: $runId) {
              scorerKey
              n
              agreement
              kappa
              falsePass
              falseFail
            }
          }
        `,
        variables: { runId },
      }),
      providesTags: ["Run", "Calibration"],
    }),

    reviewQueue: b.query<{ reviewQueue: any[] }, number>({
      query: (limit) => ({
        document: gql`
          query Queue($limit: Int!) {
            reviewQueue(limit: $limit) {
              id
              finalOutput
              terminalState
              steps
              taskCase {
                externalId
                prompt
                rubric
              }
              scores {
                scorerKey
                scorerKind
                passed
                value
                confidence
                rationale
              }
            }
          }
        `,
        variables: { limit },
      }),
      providesTags: ["Review"],
    }),

    queueStats: b.query<any, string | undefined>({
      query: (runId) => ({
        document: gql`
          query Stats($runId: String) {
            queueStats(runId: $runId) {
              pending
              labeled
              byReason
            }
          }
        `,
        variables: { runId },
      }),
      providesTags: ["Review"],
    }),

    submitReview: b.mutation<any, SubmitReviewArgs>({
      query: (vars) => ({
        document: gql`
          mutation Submit(
            $trajectoryId: String!
            $humanPassed: Boolean!
            $reviewer: String!
            $blind: Boolean
            $note: String
          ) {
            submitReview(
              trajectoryId: $trajectoryId
              humanPassed: $humanPassed
              reviewer: $reviewer
              blind: $blind
              note: $note
            ) {
              id
              humanPassed
              blind
            }
          }
        `,
        variables: vars,
      }),
      // Deliberately NOT invalidating "Review" per label. Refetching the queue
      // after every keystroke destroys review throughput. The local cursor
      // advances; the component refetches only when the buffer runs low.
    }),

    recomputeCalibration: b.mutation<any, { runId: string; blindOnly?: boolean }>({
      query: ({ runId, blindOnly = false }) => ({
        document: gql`
          mutation Recompute($runId: String!, $blindOnly: Boolean) {
            recomputeCalibration(runId: $runId, blindOnly: $blindOnly) {
              scorerKey
              n
              kappa
              agreement
              falsePass
              falseFail
            }
          }
        `,
        variables: { runId, blindOnly },
      }),
      invalidatesTags: ["Calibration"],
    }),
  }),
});

export const {
  useRunsQuery,
  useRunDetailQuery,
  useReviewQueueQuery,
  useQueueStatsQuery,
  useSubmitReviewMutation,
  useRecomputeCalibrationMutation,
} = api;