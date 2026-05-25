"""
Poker equity engine: hand evaluation, range parsing, Monte Carlo & full enumeration.
"""

from itertools import combinations
from collections import Counter
import random

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
SUIT_SYMBOLS = {'c': '♣', 'd': '♦', 'h': '♥', 's': '♠'}
SUIT_COLORS  = {'c': 'black', 'd': 'red', 'h': 'red', 's': 'black'}

_CARD_RANKS = [c // 4 for c in range(52)]
_CARD_SUITS = [c % 4 for c in range(52)]
_C75 = list(combinations(range(7), 5))
_C65 = list(combinations(range(6), 5))
_C55 = [(0, 1, 2, 3, 4)]


# ---------------------------------------------------------------------------
# Card helpers
# ---------------------------------------------------------------------------

def card_to_int(s: str) -> int:
    s = s.strip()
    if len(s) != 2:
        raise ValueError(f"Invalid card '{s}'")
    r = s[0].upper()
    su = s[1].lower()
    if r not in RANKS:
        raise ValueError(f"Invalid rank '{r}'")
    if su not in SUITS:
        raise ValueError(f"Invalid suit '{su}'")
    return RANKS.index(r) * 4 + SUITS.index(su)


def int_to_card(n: int) -> str:
    return RANKS[n // 4] + SUITS[n % 4]


def card_info(n: int) -> dict:
    rank = RANKS[n // 4]
    suit = SUITS[n % 4]
    return {
        'int': n,
        'str': rank + suit,
        'rank': rank,
        'suit': suit,
        'symbol': SUIT_SYMBOLS[suit],
        'color': SUIT_COLORS[suit],
        'rank_idx': n // 4,
    }


# ---------------------------------------------------------------------------
# Hand evaluator (5-card → tuple, higher = better)
# ---------------------------------------------------------------------------

def eval5(cards) -> tuple:
    r = [_CARD_RANKS[c] for c in cards]
    s = [_CARD_SUITS[c] for c in cards]

    is_flush = s[0] == s[1] == s[2] == s[3] == s[4]
    sr = sorted(r, reverse=True)

    is_straight = False
    straight_top = -1
    if len(set(r)) == 5:
        if sr[0] - sr[4] == 4:
            is_straight = True
            straight_top = sr[0]
        elif sr == [12, 3, 2, 1, 0]:
            is_straight = True
            straight_top = 3

    cnt = [0] * 13
    for ri in r:
        cnt[ri] += 1

    quad_r = trip_r = -1
    pairs = []
    kickers = []
    for ri in range(12, -1, -1):
        c = cnt[ri]
        if c == 4:
            quad_r = ri
        elif c == 3:
            trip_r = ri
        elif c == 2:
            pairs.append(ri)
        elif c == 1:
            kickers.append(ri)

    if is_straight and is_flush:
        return (8, straight_top)
    if quad_r >= 0:
        k = kickers[0] if kickers else (pairs[0] if pairs else trip_r)
        return (7, quad_r, k)
    if trip_r >= 0 and pairs:
        return (6, trip_r, pairs[0])
    if is_flush:
        return (5, sr[0], sr[1], sr[2], sr[3], sr[4])
    if is_straight:
        return (4, straight_top)
    if trip_r >= 0:
        return (3, trip_r, kickers[0], kickers[1])
    if len(pairs) >= 2:
        return (2, pairs[0], pairs[1], kickers[0])
    if pairs:
        return (1, pairs[0], kickers[0], kickers[1], kickers[2])
    return (0, sr[0], sr[1], sr[2], sr[3], sr[4])


def best_hand(hole: list, board: list) -> tuple:
    all_cards = hole + board
    n = len(all_cards)
    idx_combos = _C75 if n == 7 else (_C65 if n == 6 else _C55)
    best = None
    for idxs in idx_combos:
        five = [all_cards[i] for i in idxs]
        score = eval5(five)
        if best is None or score > best:
            best = score
    return best


HAND_NAMES = {
    8: 'Quinte Flush',
    7: 'Carré',
    6: 'Full',
    5: 'Couleur',
    4: 'Suite',
    3: 'Brelan',
    2: 'Double Paire',
    1: 'Paire',
    0: 'Carte Haute',
}


# ---------------------------------------------------------------------------
# Range parsing
# ---------------------------------------------------------------------------

def expand_hand(i1: int, i2: int, suited=False, offsuit=False) -> list:
    """Return all (card1, card2) tuples for a hand category."""
    combos = []
    if i1 == i2:
        for s1, s2 in combinations(range(4), 2):
            combos.append((i1 * 4 + s1, i1 * 4 + s2))
    else:
        hi, lo = max(i1, i2), min(i1, i2)
        for s1 in range(4):
            for s2 in range(4):
                if suited and s1 != s2:
                    continue
                if offsuit and s1 == s2:
                    continue
                c1, c2 = hi * 4 + s1, lo * 4 + s2
                combos.append((min(c1, c2), max(c1, c2)))
    return list(set(combos))


def _strip_suitedness(part: str):
    suited = part.endswith('s')
    offsuit = part.endswith('o')
    if suited or offsuit:
        part = part[:-1]
    return part, suited, offsuit


def parse_plain(part: str) -> list:
    part, suited, offsuit = _strip_suitedness(part)
    if len(part) != 2:
        return []
    r1, r2 = part[0].upper(), part[1].upper()
    if r1 not in RANKS or r2 not in RANKS:
        return []
    return expand_hand(RANKS.index(r1), RANKS.index(r2), suited, offsuit)


def parse_plus(part: str) -> list:
    part, suited, offsuit = _strip_suitedness(part)
    if len(part) != 2:
        return []
    r1, r2 = part[0].upper(), part[1].upper()
    if r1 not in RANKS or r2 not in RANKS:
        return []
    i1, i2 = RANKS.index(r1), RANKS.index(r2)
    if i1 < i2:
        i1, i2 = i2, i1
    combos = []
    if i1 == i2:
        for i in range(i1, 13):
            combos.extend(expand_hand(i, i, False, False))
    else:
        for i in range(i2, i1):
            combos.extend(expand_hand(i1, i, suited, offsuit))
    return combos


def parse_dash(left: str, right: str) -> list:
    left, sl, ol = _strip_suitedness(left)
    right, sr, or_ = _strip_suitedness(right)
    suited = sl or sr
    offsuit = ol or or_

    if len(left) != 2 or len(right) != 2:
        return []
    r1l, r2l = left[0].upper(), left[1].upper()
    r1r, r2r = right[0].upper(), right[1].upper()
    for c in (r1l, r2l, r1r, r2r):
        if c not in RANKS:
            return []

    il1, il2 = RANKS.index(r1l), RANKS.index(r2l)
    ir1, ir2 = RANKS.index(r1r), RANKS.index(r2r)
    if il1 < il2:
        il1, il2 = il2, il1
    if ir1 < ir2:
        ir1, ir2 = ir2, ir1

    combos = []
    if il1 == il2 and ir1 == ir2:
        lo, hi = min(il1, ir1), max(il1, ir1)
        for i in range(lo, hi + 1):
            combos.extend(expand_hand(i, i, False, False))
    elif il1 == ir1:
        lo, hi = min(il2, ir2), max(il2, ir2)
        for i in range(lo, hi + 1):
            combos.extend(expand_hand(il1, i, suited, offsuit))
    elif il2 == ir2:
        lo, hi = min(il1, ir1), max(il1, ir1)
        for i in range(lo, hi + 1):
            combos.extend(expand_hand(i, il2, suited, offsuit))
    return combos


def parse_token(part: str) -> list:
    part = part.strip()
    if not part:
        return []
    if len(part) == 4 and part[1].lower() in 'cdhs' and part[3].lower() in 'cdhs':
        try:
            c1 = card_to_int(part[:2])
            c2 = card_to_int(part[2:])
            if c1 != c2:
                return [(min(c1, c2), max(c1, c2))]
        except ValueError:
            pass
        return []
    if '-' in part:
        lhs, rhs = part.split('-', 1)
        return parse_dash(lhs.strip(), rhs.strip())
    if part.endswith('+'):
        return parse_plus(part[:-1])
    return parse_plain(part)


def parse_range(range_str: str, blocked=None) -> list:
    blocked = set(blocked or [])
    seen = set()
    combos = []
    for token in range_str.replace(' ', '').split(','):
        for combo in parse_token(token):
            c1, c2 = combo
            if combo not in seen and c1 not in blocked and c2 not in blocked:
                seen.add(combo)
                combos.append(combo)
    return combos


def count_range(range_str: str) -> int:
    try:
        return len(parse_range(range_str))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Equity: full enumeration (specific hands only)
# ---------------------------------------------------------------------------

def equity_enum(hands: list, board: list) -> list:
    """Exact equity via full enumeration. hands = list of [c1,c2]."""
    n = len(hands)
    dead = set(board)
    for h in hands:
        dead.update(h)
    remaining = [c for c in range(52) if c not in dead]
    needed = 5 - len(board)

    wins = [0] * n
    tie_eq = [0.0] * n
    total = 0

    for extra in combinations(remaining, needed):
        full_board = board + list(extra)
        scores = [best_hand(h, full_board) for h in hands]
        best_score = max(scores)
        winners = [i for i, s in enumerate(scores) if s == best_score]
        total += 1
        if len(winners) == 1:
            wins[winners[0]] += 1
        else:
            share = 1.0 / len(winners)
            for w in winners:
                tie_eq[w] += share

    if total == 0:
        return None

    return [
        {
            'equity': round((wins[i] + tie_eq[i]) / total * 100, 2),
            'wins': round(wins[i] / total * 100, 2),
            'ties': round(tie_eq[i] / total * 100, 2),
            'combos': 1,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Equity: Monte Carlo (ranges)
# ---------------------------------------------------------------------------

def equity_mc(player_ranges: list, board: list, iterations: int = 20000) -> list:
    n = len(player_ranges)
    wins = [0] * n
    tie_eq = [0.0] * n
    total = 0

    board = list(board)
    dead_base = set(board)

    for _ in range(iterations):
        used = set(dead_base)
        hands = []
        ok = True
        for ranges in player_ranges:
            avail = [(c1, c2) for c1, c2 in ranges if c1 not in used and c2 not in used]
            if not avail:
                ok = False
                break
            h = random.choice(avail)
            used.add(h[0])
            used.add(h[1])
            hands.append(list(h))
        if not ok:
            continue

        remaining = [c for c in range(52) if c not in used]
        needed = 5 - len(board)
        if len(remaining) < needed:
            continue

        extra = random.sample(remaining, needed)
        full_board = board + extra
        scores = [best_hand(h, full_board) for h in hands]
        best_score = max(scores)
        winners = [i for i, s in enumerate(scores) if s == best_score]
        total += 1
        if len(winners) == 1:
            wins[winners[0]] += 1
        else:
            share = 1.0 / len(winners)
            for w in winners:
                tie_eq[w] += share

    if total == 0:
        return None

    return [
        {
            'equity': round((wins[i] + tie_eq[i]) / total * 100, 2),
            'wins': round(wins[i] / total * 100, 2),
            'ties': round(tie_eq[i] / total * 100, 2),
            'combos': len(player_ranges[i]),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Scenario analyzer
# ---------------------------------------------------------------------------

def _scenario_equity(hands_or_ranges, board, specific, iters):
    if specific:
        hand1, hand2 = hands_or_ranges
        full_board = board
        s1 = best_hand(list(hand1), full_board)
        s2 = best_hand(list(hand2), full_board)
        if s1 > s2:
            return 100.0
        elif s2 > s1:
            return 0.0
        return 50.0
    else:
        res = equity_mc(hands_or_ranges, board, iters)
        return res[0]['equity'] if res else 50.0


def scenario_turn(hands_or_ranges, flop: list, specific=True, iters_per_card=400) -> list:
    dead = set(flop)
    if specific:
        for h in hands_or_ranges:
            dead.update(h)

    results = []
    for turn_card in range(52):
        if turn_card in dead:
            continue
        board_with_turn = flop + [turn_card]

        if specific:
            hand1, hand2 = hands_or_ranges
            all_dead = set(hand1 + hand2 + board_with_turn)
            rivers = [c for c in range(52) if c not in all_dead]
            w1 = w2 = ties = 0
            for rv in rivers:
                fb = board_with_turn + [rv]
                s1 = best_hand(list(hand1), fb)
                s2 = best_hand(list(hand2), fb)
                if s1 > s2:
                    w1 += 1
                elif s2 > s1:
                    w2 += 1
                else:
                    ties += 1
            tot = w1 + w2 + ties
            eq1 = round((w1 + ties / 2) / tot * 100, 2) if tot else 50.0
        else:
            res = equity_mc(hands_or_ranges, board_with_turn, iters_per_card)
            eq1 = res[0]['equity'] if res else 50.0

        info = card_info(turn_card)
        info['equity_p1'] = eq1
        results.append(info)

    return sorted(results, key=lambda x: x['int'])


def scenario_river(hands_or_ranges, flop: list, turn: int, specific=True, iters_per_card=400) -> list:
    board = flop + [turn]
    dead = set(board)
    if specific:
        for h in hands_or_ranges:
            dead.update(h)

    results = []
    for river_card in range(52):
        if river_card in dead:
            continue
        full_board = board + [river_card]

        if specific:
            hand1, hand2 = hands_or_ranges
            s1 = best_hand(list(hand1), full_board)
            s2 = best_hand(list(hand2), full_board)
            eq1 = 100.0 if s1 > s2 else (0.0 if s2 > s1 else 50.0)
        else:
            res = equity_mc(hands_or_ranges, full_board, iters_per_card)
            eq1 = res[0]['equity'] if res else 50.0

        info = card_info(river_card)
        info['equity_p1'] = eq1
        results.append(info)

    return sorted(results, key=lambda x: x['int'])
