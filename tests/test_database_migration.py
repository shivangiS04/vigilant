import unittest

from sqlalchemy import create_engine

from backend.database.session import _make_event_confidence_nullable


class DatabaseMigrationTests(unittest.TestCase):
    def test_existing_sqlite_events_survive_nullable_confidence_migration(self):
        engine = create_engine("sqlite:///:memory:")
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql("CREATE TABLE homes (id VARCHAR PRIMARY KEY)")
                connection.exec_driver_sql("CREATE TABLE cameras (id VARCHAR PRIMARY KEY)")
                connection.exec_driver_sql(
                    "CREATE TABLE ring_events ("
                    "id VARCHAR NOT NULL PRIMARY KEY, home_id VARCHAR NOT NULL, "
                    "camera_id VARCHAR NOT NULL, type VARCHAR NOT NULL, "
                    "confidence FLOAT NOT NULL, timestamp DATETIME NOT NULL, "
                    "raw_payload JSON, created_at DATETIME)"
                )
                connection.exec_driver_sql(
                    "INSERT INTO ring_events "
                    "(id, home_id, camera_id, type, confidence, timestamp) "
                    "VALUES ('event-1', 'home-1', 'device-1', 'motion_detected', "
                    "0.8, '2026-09-29 12:00:00')"
                )

            _make_event_confidence_nullable(engine)

            with engine.connect() as connection:
                columns = connection.exec_driver_sql("PRAGMA table_info(ring_events)").fetchall()
                confidence_column = next(column for column in columns if column[1] == "confidence")
                event = connection.exec_driver_sql(
                    "SELECT id, confidence FROM ring_events WHERE id='event-1'"
                ).one()
            self.assertEqual(confidence_column[3], 0)
            self.assertEqual(tuple(event), ("event-1", 0.8))
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()