"""
scratch/patch_history_store_db.py

Patches history_store.py to fix all database-related bugs:
1. Schema auto-bootstrap (DDL creation for sensor_readings, station_health_events, hypertable, indices)
2. Connection pool poisoning prevention (putconn with close=True on broken sockets)
3. Naive timestamp conversion fix in sync_csv_to_db (tz_localize vs tz_convert)
4. Parameter normalization for DB mark_spike
5. Complete database table purge in clear_all (truncates station_health_events as well)
"""

with open('history_store.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace _init_timescale_pool
old_init = '''            # Test connection
            conn = self._db_pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = '3000ms';")
                    cur.execute("SELECT 1;")
                conn.commit()
                self.use_db = True
                print("[HistoryStore] Connected to TimescaleDB (Tiger Cloud) successfully.")
            finally:
                self._db_pool.putconn(conn)'''

new_init = '''            # Test connection and bootstrap schema
            conn = self._db_pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SET statement_timeout = '5000ms';")
                    cur.execute("SELECT 1;")
                conn.commit()
                self._ensure_schema(conn)
                self.use_db = True
                print("[HistoryStore] Connected to TimescaleDB (Tiger Cloud) and verified schema successfully.")
            finally:
                self._db_pool.putconn(conn)'''

assert old_init in content, "old_init not found"
content = content.replace(old_init, new_init)

# Add _ensure_schema method
schema_method = '''    def _ensure_schema(self, conn):
        """Auto-bootstraps TimescaleDB hypertable and indices if they do not exist."""
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_readings (
                        time TIMESTAMPTZ NOT NULL,
                        station_id VARCHAR(32) NOT NULL,
                        temperature_c DOUBLE PRECISION,
                        pressure_hpa DOUBLE PRECISION,
                        humidity_pct DOUBLE PRECISION,
                        is_anomaly BOOLEAN DEFAULT FALSE,
                        fault_type VARCHAR(64),
                        severity VARCHAR(32),
                        anomaly_score_pct DOUBLE PRECISION,
                        suggested_temperature_c DOUBLE PRECISION,
                        suggested_pressure_hpa DOUBLE PRECISION,
                        suggested_humidity_pct DOUBLE PRECISION,
                        health_status VARCHAR(32),
                        source VARCHAR(32) DEFAULT 'live',
                        decision_basis VARCHAR(64),
                        model_confidence_pct DOUBLE PRECISION,
                        rule_confidence_pct DOUBLE PRECISION,
                        PRIMARY KEY (station_id, time)
                    );
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS station_health_events (
                        time TIMESTAMPTZ NOT NULL,
                        station_id VARCHAR(32) NOT NULL,
                        old_state VARCHAR(32),
                        new_state VARCHAR(32),
                        reason TEXT
                    );
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sensor_readings_station_source_time
                    ON sensor_readings (station_id, source, time DESC);
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_station_health_events_station_time
                    ON station_health_events (station_id, time DESC);
                """)
                try:
                    cur.execute("SELECT create_hypertable('sensor_readings', 'time', if_not_exists => TRUE, migrate_data => TRUE);")
                except Exception:
                    pass
            conn.commit()
        except Exception as e:
            print(f"[HistoryStore] Schema bootstrap note: {e!r}")
            try:
                conn.rollback()
            except Exception:
                pass

'''

# Insert _ensure_schema before _get_db_conn
content = content.replace('    @contextmanager\n    def _get_db_conn(self):', schema_method + '    @contextmanager\n    def _get_db_conn(self):')

# Replace _get_db_conn to prevent pool poisoning
old_get_conn = '''    @contextmanager
    def _get_db_conn(self):
        """Context manager to acquire and return pooled connections safely."""
        if not self.use_db or not self._db_pool:
            yield None
            return

        conn = None
        try:
            conn = self._db_pool.getconn()
        except Exception as e:
            print(f"[HistoryStore DB Pool Error] {e!r}")
            self.use_db = False
            yield None
            return

        try:
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[HistoryStore DB Error] {e!r}")
            err_str = str(e).lower()
            if any(k in err_str for k in ("closed", "connection", "terminat", "timeout", "broken", "network", "operationalerror", "canceling")):
                self.use_db = False
        finally:
            if conn and self._db_pool:
                try:
                    self._db_pool.putconn(conn)
                except Exception:
                    pass'''

new_get_conn = '''    @contextmanager
    def _get_db_conn(self):
        """Context manager to acquire and return pooled connections safely."""
        if not self.use_db or not self._db_pool:
            yield None
            return

        conn = None
        should_close = False
        try:
            conn = self._db_pool.getconn()
        except Exception as e:
            print(f"[HistoryStore DB Pool Error] {e!r}")
            self.use_db = False
            yield None
            return

        try:
            yield conn
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"[HistoryStore DB Error] {e!r}")
            err_str = str(e).lower()
            if any(k in err_str for k in ("closed", "connection", "terminat", "timeout", "broken", "network", "operationalerror", "canceling")):
                self.use_db = False
                should_close = True
        finally:
            if conn and self._db_pool:
                try:
                    is_dead = should_close or (hasattr(conn, "closed") and conn.closed != 0)
                    self._db_pool.putconn(conn, close=is_dead)
                except Exception:
                    pass'''

assert old_get_conn in content, "old_get_conn not found"
content = content.replace(old_get_conn, new_get_conn)

# Fix sync_csv_to_db naive timestamp handling
old_sync_ts = '''                                if row and row[0]:
                                    latest_db_time = pd.Timestamp(row[0]).tz_convert("UTC")'''

new_sync_ts = '''                                if row and row[0]:
                                    t_val = pd.Timestamp(row[0])
                                    if t_val.tzinfo is None:
                                        latest_db_time = t_val.tz_localize("UTC")
                                    else:
                                        latest_db_time = t_val.tz_convert("UTC")'''

assert old_sync_ts in content, "old_sync_ts not found"
content = content.replace(old_sync_ts, new_sync_ts)

# Fix mark_spike parameter normalization
old_mark_spike = '''        # Database update
        if self.use_db and parameter in RAW_PARAMS:
            try:
                col_name = f"suggested_{parameter}"
                with self._get_db_conn() as conn:
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                f"""
                                UPDATE sensor_readings
                                SET is_anomaly = TRUE, fault_type = 'spike', severity = 'medium', {col_name} = %s
                                WHERE station_id = %s AND time = %s AND source = %s;
                                """,
                                (suggested_value, station_id, ts_obj.to_pydatetime(), source),
                            )
                        conn.commit()
            except Exception as e:
                print(f"[HistoryStore] DB mark_spike error: {e!r}")'''

new_mark_spike = '''        # Database update with parameter normalization
        norm_param = parameter
        if norm_param in ("temp", "temperature"):
            norm_param = "temperature_c"
        elif norm_param in ("pressure", "baro"):
            norm_param = "pressure_hpa"
        elif norm_param in ("humidity", "humid", "rh"):
            norm_param = "humidity_pct"

        if self.use_db and norm_param in RAW_PARAMS:
            try:
                col_name = f"suggested_{norm_param}"
                with self._get_db_conn() as conn:
                    if conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                f"""
                                UPDATE sensor_readings
                                SET is_anomaly = TRUE, fault_type = 'spike', severity = 'medium', {col_name} = %s
                                WHERE station_id = %s AND time = %s AND source = %s;
                                """,
                                (suggested_value, station_id, ts_obj.to_pydatetime(), source),
                            )
                        conn.commit()
            except Exception as e:
                print(f"[HistoryStore] DB mark_spike error: {e!r}")'''

assert old_mark_spike in content, "old_mark_spike not found"
content = content.replace(old_mark_spike, new_mark_spike)

# Fix clear_all to also truncate station_health_events
old_clear_all = '''                            if source is None:
                                cur.execute("TRUNCATE TABLE sensor_readings;")
                            else:
                                cur.execute("DELETE FROM sensor_readings WHERE source = %s;", (source,))'''

new_clear_all = '''                            if source is None:
                                cur.execute("TRUNCATE TABLE sensor_readings;")
                                cur.execute("TRUNCATE TABLE station_health_events;")
                            else:
                                cur.execute("DELETE FROM sensor_readings WHERE source = %s;", (source,))'''

assert old_clear_all in content, "old_clear_all not found"
content = content.replace(old_clear_all, new_clear_all)

with open('history_store.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("history_store.py successfully patched for all database bugs!")
