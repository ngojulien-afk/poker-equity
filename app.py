from flask import Flask, render_template, request, jsonify
from math import comb
import os
import json
import hashlib
import poker_engine as pe

# psycopg2 is only needed for cloud sync (Neon). Keep it optional so the app
# still runs locally without a database configured.
try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None

# Absolute template folder so Flask finds templates regardless of the working
# directory (important on Vercel's serverless runtime).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# Neon / Postgres connection string (set in Vercel env vars). Use the *pooled*
# connection string from Neon for serverless.
DATABASE_URL = os.environ.get('DATABASE_URL')


# ---------------------------------------------------------------------------
# Cloud sync helpers (Neon Postgres)
# ---------------------------------------------------------------------------

def _db_conn():
    """Open a short-lived Postgres connection. Raises RuntimeError if sync
    is not configured (no DATABASE_URL) or the driver is missing."""
    if not DATABASE_URL:
        raise RuntimeError('Cloud sync is not configured on the server.')
    if psycopg2 is None:
        raise RuntimeError('Database driver (psycopg2) is not installed.')
    return psycopg2.connect(DATABASE_URL)


def _ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ranges (
            user_key   TEXT PRIMARY KEY,
            data       JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def _user_key(passphrase):
    """Derive a storage key from the passphrase. The raw passphrase is never
    stored — only this hash is used as the row key."""
    return hashlib.sha256(('pkr-sync:' + passphrase).encode('utf-8')).hexdigest()


def _parse_board(board_strs):
    cards = []
    for c in board_strs:
        if c and c.strip():
            cards.append(pe.card_to_int(c.strip()))
    return cards


def _is_specific(range_str):
    """True only if the string is a single concrete hand like 'AhKs'."""
    r = range_str.strip()
    return (len(r) == 4
            and r[1].lower() in 'cdhs'
            and r[3].lower() in 'cdhs')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/equity', methods=['POST'])
def calculate_equity():
    data = request.json or {}
    players = data.get('players', [])
    board_strs = data.get('board', [])

    try:
        board = _parse_board(board_strs)
    except ValueError as e:
        return jsonify({'error': f'Invalid board card: {e}'}), 400

    if len(players) < 2:
        return jsonify({'error': 'At least 2 players required'}), 400

    player_ranges = []
    player_meta = []
    all_specific = True

    for p in players:
        rstr = p.get('range', '').strip()
        if not rstr:
            return jsonify({'error': 'Each player must have a range'}), 400

        # Only block board cards when parsing — inter-player conflicts are
        # resolved inside the Monte Carlo sampler, not at parse time.
        combos = pe.parse_range(rstr, board)
        if not combos:
            return jsonify({'error': f'No valid combos for: {rstr}'}), 400

        is_spec = _is_specific(rstr) and len(combos) == 1
        all_specific = all_specific and is_spec

        player_ranges.append(combos)
        player_meta.append({'range': rstr, 'combos': len(combos)})

    iters = int(data.get('iterations', 20000))

    # Full enumeration only when board is on flop+ (few remaining cards needed).
    # Preflop: C(48,5)=1.7M → too slow. Flop: C(45,2)=990. Turn: 44. Fast enough.
    board_needed = 5 - len(board)
    remaining_approx = 52 - 4 - len(board)
    enum_size = comb(max(remaining_approx, 0), board_needed) if board_needed >= 0 else 0

    if all_specific and len(player_ranges) == 2 and enum_size <= 50000:
        hand1 = list(player_ranges[0][0])
        hand2 = list(player_ranges[1][0])
        results = pe.equity_enum([hand1, hand2], board)
    else:
        results = pe.equity_mc(player_ranges, board, iters)

    if results is None:
        return jsonify({'error': 'Cannot calculate — ranges too constrained or incompatible'}), 400

    for i, r in enumerate(results):
        r['range'] = player_meta[i]['range']
        r['combos'] = player_meta[i]['combos']

    return jsonify({'results': results})


@app.route('/api/validate_range', methods=['POST'])
def validate_range():
    data = request.json or {}
    rstr = data.get('range', '')
    board_strs = data.get('board', [])
    try:
        board = _parse_board(board_strs)
        total_combos = pe.count_range(rstr)
        available = len(pe.parse_range(rstr, board))
        return jsonify({'combos': total_combos, 'available': available, 'valid': True})
    except Exception as e:
        return jsonify({'combos': 0, 'available': 0, 'valid': False, 'error': str(e)})


@app.route('/api/scenario/turn', methods=['POST'])
def analyze_turn():
    data = request.json or {}
    range1 = data.get('range1', '').strip()
    range2 = data.get('range2', '').strip()
    flop_strs = data.get('flop', [])

    try:
        flop = _parse_board(flop_strs)
    except ValueError as e:
        return jsonify({'error': f'Invalid card: {e}'}), 400

    if len(flop) != 3:
        return jsonify({'error': 'Flop must have exactly 3 cards'}), 400

    spec1 = _is_specific(range1)
    spec2 = _is_specific(range2)

    try:
        if spec1 and spec2:
            hand1 = [pe.card_to_int(range1[:2]), pe.card_to_int(range1[2:])]
            hand2 = [pe.card_to_int(range2[:2]), pe.card_to_int(range2[2:])]
            # Check for card collision
            if set(hand1) & set(hand2) or set(hand1+hand2) & set(flop):
                return jsonify({'error': 'Card conflict between hands and board'}), 400
            results = pe.scenario_turn((hand1, hand2), flop, specific=True)
        else:
            r1 = pe.parse_range(range1, flop)
            r2 = pe.parse_range(range2, flop)
            if not r1:
                return jsonify({'error': f'Invalid or empty range: {range1}'}), 400
            if not r2:
                return jsonify({'error': f'Invalid or empty range: {range2}'}), 400
            results = pe.scenario_turn((r1, r2), flop, specific=False, iters_per_card=600)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

    return jsonify({'results': results})


@app.route('/api/scenario/river', methods=['POST'])
def analyze_river():
    data = request.json or {}
    range1 = data.get('range1', '').strip()
    range2 = data.get('range2', '').strip()
    flop_strs = data.get('flop', [])
    turn_str = data.get('turn', '').strip()

    try:
        flop = _parse_board(flop_strs)
        turn = pe.card_to_int(turn_str)
    except ValueError as e:
        return jsonify({'error': f'Invalid card: {e}'}), 400

    spec1 = _is_specific(range1)
    spec2 = _is_specific(range2)

    try:
        if spec1 and spec2:
            hand1 = [pe.card_to_int(range1[:2]), pe.card_to_int(range1[2:])]
            hand2 = [pe.card_to_int(range2[:2]), pe.card_to_int(range2[2:])]
            if set(hand1) & set(hand2) or set(hand1+hand2) & set(flop+[turn]):
                return jsonify({'error': 'Card conflict between hands and board'}), 400
            results = pe.scenario_river((hand1, hand2), flop, turn, specific=True)
        else:
            blocked = flop + [turn]
            r1 = pe.parse_range(range1, blocked)
            r2 = pe.parse_range(range2, blocked)
            if not r1:
                return jsonify({'error': f'Invalid or empty range: {range1}'}), 400
            if not r2:
                return jsonify({'error': f'Invalid or empty range: {range2}'}), 400
            results = pe.scenario_river((r1, r2), flop, turn, specific=False, iters_per_card=600)
    except Exception as e:
        import traceback
        return jsonify({'error': str(e), 'detail': traceback.format_exc()}), 500

    return jsonify({'results': results})


@app.route('/api/sync/pull', methods=['POST'])
def sync_pull():
    """Return the whole saved-ranges blob for a passphrase."""
    data = request.json or {}
    pw = (data.get('passphrase') or '').strip()
    if len(pw) < 4:
        return jsonify({'error': 'Passphrase too short (min 4 characters).'}), 400
    try:
        conn = _db_conn()
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    try:
        with conn:
            with conn.cursor() as cur:
                _ensure_table(cur)
                cur.execute(
                    "SELECT data, updated_at FROM ranges WHERE user_key = %s",
                    (_user_key(pw),))
                row = cur.fetchone()
        if not row:
            return jsonify({'found': False, 'data': {}, 'updated_at': None})
        blob = row[0]
        if isinstance(blob, str):
            blob = json.loads(blob)
        return jsonify({'found': True, 'data': blob,
                        'updated_at': row[1].isoformat()})
    except Exception as e:
        return jsonify({'error': f'Sync failed: {e}'}), 500
    finally:
        conn.close()


@app.route('/api/sync/push', methods=['POST'])
def sync_push():
    """Upsert the whole saved-ranges blob for a passphrase."""
    data = request.json or {}
    pw = (data.get('passphrase') or '').strip()
    ranges = data.get('data')
    if len(pw) < 4:
        return jsonify({'error': 'Passphrase too short (min 4 characters).'}), 400
    if not isinstance(ranges, dict):
        return jsonify({'error': 'Invalid ranges payload.'}), 400
    try:
        conn = _db_conn()
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    try:
        with conn:
            with conn.cursor() as cur:
                _ensure_table(cur)
                cur.execute("""
                    INSERT INTO ranges (user_key, data, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (user_key)
                    DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    RETURNING updated_at
                """, (_user_key(pw), json.dumps(ranges)))
                ts = cur.fetchone()[0]
        return jsonify({'ok': True, 'updated_at': ts.isoformat()})
    except Exception as e:
        return jsonify({'error': f'Sync failed: {e}'}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    print("PokerEquity running at http://localhost:8080")
    app.run(debug=True, port=8080)
