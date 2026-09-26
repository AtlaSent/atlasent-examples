/**
 * Behavior Conditioning Demo
 *
 * This example demonstrates how to use the @atlasent/behavior package to:
 * 1. Fetch a user's state summary (aggregated behavior patterns)
 * 2. Attach behavior context to evaluate requests
 * 3. Check category-specific aggregates for sensitive categories
 *
 * Note: Requires @atlasent/behavior package and behavior-insights service.
 * The @atlasent/behavior package reads from the pattern_entries aggregates —
 * no raw event data (trigger_text, notes, payload) is exposed via this API.
 */

import { AtlaSentClient } from '@atlasent/sdk';
// import { getStateSummary, getCategoryAggregate, attachToEvaluate } from '@atlasent/behavior';

const client = new AtlaSentClient({
  apiKey: process.env.ATLASENT_API_KEY!,
  baseUrl: process.env.ATLASENT_API_URL ?? 'https://api.atlasent.io/functions/v1',
});

const BEHAVIOR_BASE_URL = process.env.ATLASENT_BEHAVIOR_URL ?? 'http://localhost:3001';
const BEHAVIOR_API_KEY = process.env.ATLASENT_API_KEY!;

async function fetchStateSummary(userId: string) {
  const res = await fetch(
    `${BEHAVIOR_BASE_URL}/api/patterns/summary/${encodeURIComponent(userId)}`,
    { headers: { Authorization: `Bearer ${BEHAVIOR_API_KEY}` } }
  );
  if (!res.ok) throw new Error(`Failed to fetch state summary: ${res.status}`);
  return res.json();
}

async function fetchCategoryAggregate(userId: string, category: string) {
  const res = await fetch(
    `${BEHAVIOR_BASE_URL}/api/patterns/category/${encodeURIComponent(userId)}/${encodeURIComponent(category)}`,
    { headers: { Authorization: `Bearer ${BEHAVIOR_API_KEY}` } }
  );
  if (!res.ok) throw new Error(`Failed to fetch category aggregate: ${res.status}`);
  return res.json();
}

async function main() {
  const userId = process.env.DEMO_USER_ID ?? 'demo-user-001';

  console.log('AtlaSent Behavior Conditioning Demo');
  console.log(`User: ${userId}\n`);

  // 1. Fetch state summary
  console.log('1. Fetching behavior state summary (aggregates only)...');
  try {
    const summary = await fetchStateSummary(userId);
    console.log('   State summary:', JSON.stringify(summary, null, 2));
  } catch (err) {
    console.log('   (No behavior data yet for this user — run some evaluations first)');
  }

  console.log();

  // 2. Check mental health sensitive category
  console.log('2. Checking mental health category aggregate...');
  try {
    const agg = await fetchCategoryAggregate(userId, 'behavior.health.mental');
    if (agg.confidence_low) {
      console.log(`   Low confidence (only ${agg.count} events in window) — insufficient signal`);
    } else {
      console.log(`   ${agg.count} events in past ${agg.window_days} days`);
    }
  } catch (err) {
    console.log('   (No data for this category)');
  }

  console.log();

  // 3. Evaluate with behavior context attached
  console.log('3. Running evaluate with behavior context...');
  const metadata: Record<string, unknown> = {};

  try {
    const summary = await fetchStateSummary(userId);
    metadata['behavior_context'] = {
      event_count: summary.event_count,
      window_start: summary.window_start,
      window_end: summary.window_end,
    };
  } catch {
    // no behavior data — evaluate without it
  }

  const result = await client.evaluate({
    agent: userId,
    action: 'report.read_sensitive',
    context: metadata,
  });

  console.log(`   Decision: ${result.decision_canonical} (reason: ${result.reason || 'n/a'})`);
  if (result.decision === 'escalate') {
    console.log('   → Routing to human review queue (escalate decision)');
  }
}

main().catch(console.error);
