import os, json
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL']
eng = create_engine(url)
out = {}
with eng.connect() as c:
    r = c.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname='chat_staging'"))
    out['chat_staging_connections'] = r.scalar()
    r = c.execute(text("SELECT setting FROM pg_settings WHERE name='max_connections'"))
    out['pg_max_connections'] = r.scalar()
    # count stress users registered so far
    r = c.execute(text("SELECT count(*) FROM users WHERE username LIKE 'stress_%'"))
    out['stress_users_registered'] = r.scalar()
    # any orphan: users without... (basic check)
    r = c.execute(text("SELECT count(*) FROM users WHERE username LIKE 'stress_%' AND password_hash IS NULL"))
    out['stress_users_null_hash'] = r.scalar()
print(json.dumps(out, ensure_ascii=False))
