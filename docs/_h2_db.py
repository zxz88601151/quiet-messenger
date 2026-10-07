import os, json
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL']
eng = create_engine(url)
out = {}
with eng.connect() as c:
    r = c.execute(text("SELECT count(*) FROM users WHERE username LIKE 'stress_%' OR username LIKE 'staging_e2e_%'"))
    out['test_users'] = r.scalar()
    r = c.execute(text("SELECT count(*) FROM users WHERE username LIKE 'stress_%' AND password_hash IS NULL"))
    out['null_hash_stress'] = r.scalar()
    r = c.execute(text("SELECT username, count(*) FROM users WHERE username LIKE 'stress_%' OR username LIKE 'staging_e2e_%' GROUP BY username HAVING count(*)>1"))
    out['duplicate_usernames'] = [{"u": row[0], "n": row[1]} for row in r]
    # devices created by H2 logins (device_identifier like h2-%)
    r = c.execute(text("SELECT count(*) FROM devices WHERE device_identifier LIKE 'h2-%'"))
    out['h2_devices'] = r.scalar()
    # orphan devices (no user)
    r = c.execute(text("SELECT count(*) FROM devices d LEFT JOIN users u ON u.id=d.user_id WHERE u.id IS NULL"))
    out['orphan_devices'] = r.scalar()
    # refresh tokens / sessions table if exists
    r = c.execute(text("SELECT to_regclass('public.refresh_tokens')"))
    tbl = r.scalar()
    out['refresh_tokens_table'] = tbl
    if tbl:
        r = c.execute(text("SELECT count(*) FROM refresh_tokens"))
        out['refresh_tokens_count'] = r.scalar()
print(json.dumps(out, ensure_ascii=False))
