import { skippedRequests } from './render-page';

describe('skippedRequests', () => {
  it('keeps only the lines about skipped prompt requests', () => {
    expect(
      skippedRequests([
        "Prompt request 'add drone shots' skipped: no matching footage",
        'Used 12 shots',
      ]),
    ).toEqual(["Prompt request 'add drone shots' skipped: no matching footage"]);
  });

  it('copes with a missing log', () => {
    expect(skippedRequests(undefined)).toEqual([]);
  });
});
