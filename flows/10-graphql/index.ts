import { graphql, type V2Transport } from '@atlasent/sdk';

const transport: V2Transport = {
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
  apiKey: process.env.ATLASENT_API_KEY!,
};

// POST /v1/graphql (V2-D2 + V2-D8) — Wave A schema is read-only:
// `recentEvaluations(limit: Int!)` and `activeBundle`. There is no
// `auditLog` field, no `userId`/`decision`/`since` filter arguments, and no
// per-record `confidence` field — see @atlasent/sdk's GraphQLRequest /
// graphql() docs. Field selections below use only the two documented root
// fields; confirm sub-field availability against the live schema before
// extending this query.
const RECENT_EVALUATIONS_QUERY = `
  query RecentEvaluations($limit: Int!) {
    recentEvaluations(limit: $limit) {
      id
      decision
      actorId
      timestamp
    }
  }
`;

interface RecentEvaluationsData {
  recentEvaluations: Array<{
    id: string;
    decision: string;
    actorId: string;
    timestamp: string;
  }>;
}

async function main() {
  console.log('AtlaSent GraphQL API Demo\n');

  console.log('1. Fetching recent evaluations (last 5)...');
  const result = await graphql<RecentEvaluationsData>(transport, {
    query: RECENT_EVALUATIONS_QUERY,
    variables: { limit: 5 },
  });

  if (result.errors?.length) {
    console.error('   GraphQL errors:', result.errors);
  }

  if (result.data?.recentEvaluations) {
    console.log(`   Found ${result.data.recentEvaluations.length} entries:`);
    for (const entry of result.data.recentEvaluations) {
      console.log(`   - [${entry.timestamp}] actor=${entry.actorId} decision=${entry.decision}`);
    }
  }
}

main().catch(console.error);
