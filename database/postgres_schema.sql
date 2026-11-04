-- Gli istanti restano testo ISO UTC per mantenere lo stesso contratto di SQLite.
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS draws (
    id BIGSERIAL PRIMARY KEY,
    game TEXT NOT NULL, variant TEXT NOT NULL, wheel TEXT NOT NULL,
    draw_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
    numbers TEXT NOT NULL, extras TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)), source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(game, variant, wheel, draw_id, synthetic)
);
CREATE INDEX IF NOT EXISTS draws_chronological ON draws(game,variant,wheel,synthetic,occurred_at);
ALTER TABLE draws ADD COLUMN IF NOT EXISTS date_precision TEXT NOT NULL DEFAULT 'instant';
CREATE TABLE IF NOT EXISTS source_updates (
    source_key TEXT PRIMARY KEY, checked_at TEXT NOT NULL, details TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY, operation TEXT NOT NULL, status TEXT NOT NULL,
    created_at TEXT NOT NULL, finished_at TEXT NOT NULL, parameters TEXT NOT NULL,
    result TEXT, error TEXT
);
CREATE INDEX IF NOT EXISTS experiments_created ON experiments(created_at,id);
CREATE TABLE IF NOT EXISTS update_log (
    id BIGSERIAL PRIMARY KEY, created_at TEXT NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL,
    game TEXT NOT NULL, variant TEXT NOT NULL, wheel TEXT NOT NULL,
    synthetic INTEGER NOT NULL CHECK(synthetic IN (0,1)),
    target_id TEXT NOT NULL, target_date TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS prediction_results (
    prediction_id TEXT PRIMARY KEY REFERENCES predictions(id),
    draw_row_id BIGINT NOT NULL REFERENCES draws(id), evaluated_at TEXT NOT NULL, matches TEXT NOT NULL
);
CREATE OR REPLACE FUNCTION reject_prediction_change() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Previsioni e risultati sono immutabili';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS predictions_immutable ON predictions;
CREATE TRIGGER predictions_immutable BEFORE UPDATE OR DELETE ON predictions
FOR EACH ROW EXECUTE FUNCTION reject_prediction_change();
DROP TRIGGER IF EXISTS results_immutable ON prediction_results;
CREATE TRIGGER results_immutable BEFORE UPDATE OR DELETE ON prediction_results
FOR EACH ROW EXECUTE FUNCTION reject_prediction_change();
DELETE FROM schema_version WHERE version=2;
INSERT INTO schema_version(version) VALUES(3) ON CONFLICT DO NOTHING;
