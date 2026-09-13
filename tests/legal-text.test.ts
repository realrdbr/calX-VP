import assert from 'node:assert/strict';
import test from 'node:test';
import { renderLegalText } from '../server/legalText';

test('environment values receive one sentence ending without duplicate punctuation', () => {
  for (const value of ['Text', 'Text.', 'Text. ', 'Text!', 'Text?', 'Text…']) {
    const expected = value.trim() + (value === 'Text' ? '.' : '');
    assert.equal(renderLegalText('{VALUE}. Danach.', { VALUE: value }), expected + ' Danach.');
  }
  assert.equal(renderLegalText('{VALUE}.', {}), 'Vom Betreiber noch zu ergänzen.');
});
