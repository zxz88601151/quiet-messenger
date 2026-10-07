import os, json
from sqlalchemy import create_engine, text

url = os.environ['DATABASE_URL']
eng = create_engine(url)
out = {}
with eng.connect() as c:
    r = c.execute(text("SELECT id, username, nickname FROM users WHERE username IN ('staging_e2e_a_7f3c','staging_e2e_b_7f3c') ORDER BY username"))
    out['users'] = [dict(zip(['id','username','nickname'], row)) for row in r]
    ids = [u['id'] for u in out['users']]
    if len(ids) == 2:
        a, b = ids
        r = c.execute(text("SELECT id, user_id, friend_id, created_at FROM friendships WHERE (user_id=:a AND friend_id=:b) OR (user_id=:b AND friend_id=:a)"), {'a':a,'b':b})
        out['friendships'] = [dict(zip(['id','user_id','friend_id','created_at'], row)) for row in r]
        r = c.execute(text("SELECT id, user_a, user_b, created_at, updated_at FROM conversations WHERE (user_a=:a AND user_b=:b) OR (user_a=:b AND user_b=:a)"), {'a':a,'b':b})
        out['conversations'] = [dict(zip(['id','user_a','user_b','created_at','updated_at'], row)) for row in r]
        conv_ids = [x['id'] for x in out['conversations']]
        if conv_ids:
            r = c.execute(text("SELECT id, conversation_id, sender_id, client_message_id, content, created_at, read_at FROM messages WHERE conversation_id = ANY(:ids) ORDER BY created_at"), {'ids':conv_ids})
            out['messages'] = [dict(zip(['id','conversation_id','sender_id','client_message_id','content','created_at','read_at'], row)) for row in r]
print(json.dumps(out, ensure_ascii=False, default=str))
