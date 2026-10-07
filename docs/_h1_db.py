import os, json
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL']
eng = create_engine(url)
out = {}
with eng.connect() as c:
    # all stress users
    r = c.execute(text("SELECT username FROM users WHERE username LIKE 'stress_%' ORDER BY username"))
    allu = [row[0] for row in r]
    out['total_stress_users'] = len(allu)
    # classify by index range
    def idx(u):
        try: return int(u.split('_')[1])
        except: return -1
    seq = [u for u in allu if 1 <= idx(u) <= 60]      # expected from seq batches
    conc = [u for u in allu if 61 <= idx(u) <= 160]    # from c100_conc
    other = [u for u in allu if idx(u) not in range(1,161)]
    out['seq_range_1_60'] = len(seq)
    out['conc_range_61_160'] = len(conc)
    out['other_stress'] = len(other)
    out['conc_expected_100_got'] = len(conc)
    # orphan check: users with null password_hash
    r = c.execute(text("SELECT count(*) FROM users WHERE username LIKE 'stress_%' AND password_hash IS NULL"))
    out['null_hash'] = r.scalar()
    # duplicate username check (should be 0 by unique constraint)
    r = c.execute(text("SELECT username, count(*) FROM users WHERE username LIKE 'stress_%' GROUP BY username HAVING count(*)>1"))
    dups = [{"u": row[0], "n": row[1]} for row in r]
    out['duplicate_usernames'] = dups
    # any stress user with friendships/conversations/messages (should be none)
    r = c.execute(text("SELECT count(*) FROM friendships f JOIN users u ON u.id=f.user_id WHERE u.username LIKE 'stress_%'"))
    out['stress_friendships'] = r.scalar()
    r = c.execute(text("SELECT count(*) FROM conversations c JOIN users u ON u.id=c.user_a WHERE u.username LIKE 'stress_%'"))
    out['stress_conversations'] = r.scalar()
print(json.dumps(out, ensure_ascii=False))
