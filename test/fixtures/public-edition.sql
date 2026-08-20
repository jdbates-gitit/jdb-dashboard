INSERT OR REPLACE INTO briefings
  (id, briefing_date, title, subtitle, one_line_signal, content_json, model, generated_at)
VALUES
  (
    '00000000-0000-4000-8000-000000000001',
    '2026-08-19',
    'Fixture Daily Briefing',
    'A local boundary test',
    'Public information should remain separate from private project decisions.',
    '{"sections":[{"key":"ai_technology","title":"AI + Technology","headline":"A public test signal","body":"This section is safe to publish.","why_it_matters":"It proves the public edition works.","takeaway":"Only deliberately public content should cross the boundary.","sources":[]},{"key":"project_vote","title":"Project Vote","headline":"A private project decision","body":"This section must never appear publicly.","why_it_matters":"Project data stays private.","takeaway":"Exclude this entire section.","sources":[]}]}',
    'fixture-model',
    '2026-08-19T13:00:00.000Z'
  );
