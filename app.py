from flask import Flask, render_template, request, redirect, url_for, session
import psycopg2
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def to_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

@app.route('/select_tour', methods=['GET', 'POST'])
def select_tour():
    with get_db() as conn:
        with conn.cursor() as cur:
            if request.method == 'POST':
                tour_name = request.form['tour_name']
                cur.execute("INSERT INTO tours (name) VALUES (%s)", (tour_name,))
                conn.commit()
            cur.execute("SELECT id, name FROM tours ORDER BY created_at DESC")
            tours = cur.fetchall()
    return render_template("select_tour.html", tours=tours)

@app.route('/setup', methods=['GET', 'POST'])
def setup():
    tour_id = request.args.get("tour_id") or session.get("tour_id")
    if not tour_id:
        return redirect(url_for("select_tour"))
    session["tour_id"] = tour_id

    with get_db() as conn:
        with conn.cursor() as cur:
            if request.method == 'POST':
                name = request.form['player_name']
                hcp = to_int(request.form['handicap'])
                cur.execute("INSERT INTO players (name, handicap, tour_id) VALUES (%s, %s, %s)", (name, hcp, tour_id))
                conn.commit()

            cur.execute("SELECT name, handicap FROM players WHERE tour_id = %s", (tour_id,))
            players = cur.fetchall()
    return render_template("setup.html", players=players)

@app.route('/', methods=['GET', 'POST'])
def index():
    tour_id = session.get('tour_id')
    if not tour_id:
        return redirect(url_for("select_tour"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, handicap, points, total_c2, total_ctp, total_ace FROM players WHERE tour_id = %s ORDER BY id", (tour_id,))
    players = cur.fetchall()

    if request.method == 'POST':
        cur.execute("INSERT INTO rounds (tour_id) VALUES (%s) RETURNING id", (tour_id,))
        round_id = cur.fetchone()[0]

        scores = {}
        for pid, name, hcap, *_ in players:
            score = to_int(request.form.get(name))
            c2 = to_int(request.form.get(f'c2_{name}'))
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

        cur.execute("""
            UPDATE players
            SET points = points + CASE
                WHEN s.placement = 1 THEN 3
                WHEN s.placement = 2 THEN 2
                WHEN s.placement = 3 THEN 1
                ELSE 0
            END,
            handicap = handicap + CASE
                WHEN s.placement = 1 THEN -1
                WHEN s.placement = 3 THEN 1
                ELSE 0
            END,
            total_c2 = total_c2 + s.c2,
            total_ctp = total_ctp + CASE WHEN s.ctp THEN 1 ELSE 0 END,
            total_ace = total_ace + CASE WHEN s.ace THEN 1 ELSE 0 END
            FROM round_scores s
            WHERE s.round_id = %s AND players.id = s.player_id
        """, (round_id,))
        conn.commit()
        return redirect(url_for('index'))

    cur.execute("SELECT id FROM rounds WHERE tour_id = %s ORDER BY id DESC", (tour_id,))
    round_ids = cur.fetchall()
    rounds = []
    for (rid,) in round_ids:
        cur.execute("""
            SELECT r.*, p.name as player_name FROM round_scores r
            JOIN players p ON r.player_id = p.id
            WHERE round_id = %s
        """, (rid,))
        scores = cur.fetchall()
        rounds.append({'id': rid, 'scores': scores})

    return render_template('index.html', players=players, rounds=rounds)

@app.route('/delete_round/<int:round_id>')
def delete_round(round_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM round_scores WHERE round_id = %s", (round_id,))
            cur.execute("DELETE FROM rounds WHERE id = %s", (round_id,))
        conn.commit()
    return redirect(url_for('index'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
