'use strict';

const { readFileSync } = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const base = readFileSync(path.join(root, 'compose.team.yaml'), 'utf8');
const override = readFileSync(path.join(root, 'compose.team-ai-drafts.yaml'), 'utf8');

test('default team API remains on private networks with AI disabled', () => {
  assert.match(base, /networks: \[database, api, automation\]/);
  assert.doesNotMatch(base, /ai-egress|SOCIALMEI_GROQ_API_KEY/);
});

test('AI override exposes only an explicit outbound network and opt-in settings', () => {
  assert.match(override, /SOCIALMEI_AI_DRAFT_ENABLED: \$\{SOCIALMEI_AI_DRAFT_ENABLED:-false\}/);
  assert.match(override, /SOCIALMEI_AI_DRAFT_WORKSPACES: \$\{SOCIALMEI_AI_DRAFT_WORKSPACES:-\}/);
  assert.match(override, /SOCIALMEI_GROQ_API_KEY: \$\{SOCIALMEI_GROQ_API_KEY:-\}/);
  assert.match(override, /networks: \[database, api, automation, ai-egress\]/);
  assert.match(override, /ai-egress:\s*\n\s*driver: bridge/);
  assert.doesNotMatch(override, /\bports:|\bprivileged:|\bcap_add:/);
});
