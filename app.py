
from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS tours (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS players (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        handicap INTEGER NOT NULL DEFAULT 0,
        points INTEGER NOT NULL DEFAULT 0,
        total_c2 INTEGER NOT NULL DEFAULT 0,
        total_ctp INTEGER NOT NULL DEFAULT 0,
        total_ace INTEGER NOT NULL DEFAULT 0,
        tour_id INTEGER REFERENCES tours(id)
    );
    CREATE TABLE IF NOT EXISTS rounds (
        id SERIAL PRIMARY KEY,
        tour_id INTEGER REFERENCES tours(id)
    );
    CREATE TABLE IF NOT EXISTS round_scores (
        id SERIAL PRIMARY KEY,
        round_id INTEGER REFERENCES rounds(id),
        player_id INTEGER REFERENCES players(id),
        raw_score INTEGER,
        adjusted_score INTEGER,
        placement INTEGER,
        handicap_used INTEGER,
        c2 INTEGER DEFAULT 0,
        ctp BOOLEAN DEFAULT FALSE,
        ace BOOLEAN DEFAULT FALSE
    );
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
        conn.commit()

@app.route('/', methods=['GET', 'POST'])
def index():
    init_db()
    tour_id = session.get('tour_id', 1)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, handicap, points, total_c2, total_ctp, total_ace FROM players WHERE tour_id = %s ORDER BY id", (tour_id,))
    players = cur.fetchall()

    if request.method == 'POST':
        cur.execute("INSERT INTO rounds (tour_id) VALUES (%s) RETURNING id", (tour_id,))
        round_id = cur.fetchone()[0]

        scores = {}
        for pid, name, hcap, *_ in players:
            score = int(request.form[name])
            c2 = int(request.form.get(f'c2_{name}', 0))
            ctp = f'ctp_{name}' in request.form
            ace = f'ace_{name}' in request.form
            scores[name] = {
                'id': pid,
                'raw': score,
                'handicap': hcap,
                'c2': c2,
                'ctp': ctp,
                'ace': ace
            }

        adjusted = {name: s['raw'] - s['handicap'] for name, s in scores.items()}
        placements = sorted(adjusted.items(), key=lambda x: x[1])
        for idx, (name, _) in enumerate(placements):
            info = scores[name]
            place = idx + 1
            cur.execute(
                "INSERT INTO round_scores (round_id, player_id, raw_score, adjusted_score, placement, handicap_used, c2, ctp, ace) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (round_id, info['id'], info['raw'], adjusted[name], place, info['handicap'], info['c2'], info['ctp'], info['ace'])
            )
        conn.commit()
        return redirect(url_for('index'))

    cur.execute("SELECT id FROM rounds WHERE tour_id = %s ORDER BY id DESC", (tour_id,))
    round_ids = cur.fetchall()
    rounds = []
    for (rid,) in round_ids:
        cur.execute("SELECT * FROM round_scores WHERE round_id = %s", (rid,))
        scores = cur.fetchall()
        rounds.append({'id': rid, 'scores': scores})

    return render_template('index.html', players=players, rounds=rounds)
