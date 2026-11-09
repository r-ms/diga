"""CTC word spotting: find where glossary terms were *said*, from frame-level CTC log-probs.

An exact dynamic programme over a token trie of all term spellings, in the style of NeMo's
CTC word spotter (Andrusenko et al., 2024). Each hypothesis is scored *relative* to the best
path at every frame (so acoustic scores are ≤ 0) plus a per-token bonus ``ctc_weight``; a
term is spotted where its score stays above ``theta``. Overlapping detections are resolved
greedily by score (non-maximum suppression).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

NEG = np.float32(-1e9)


@dataclass(frozen=True)
class Spot:
    frame_start: int
    frame_end: int  # inclusive
    n_tokens: int
    score: float
    entry: int  # index into the entries the trie was built from


class Trie:
    """Flat, BFS-ordered trie over token ids of every spelling of every entry.

    ``spellings[i]`` lists the spellings of entry ``i``; ``encode`` maps a string to token ids
    in the CTC model's vocabulary; ``blank_id`` is the CTC blank.
    """

    def __init__(
        self, spellings: Sequence[Sequence[str]], encode: Callable[[str], list[int]], blank_id: int
    ) -> None:
        children: dict[tuple[int, int], int] = {}
        parent, token, depth = [0], [-1], [0]  # node 0 is the root sentinel
        is_end, entry_of = [False], [-1]
        for entry, variants in enumerate(spellings):
            for variant in variants:
                ids = encode(variant)
                if not ids:
                    continue
                node = 0
                for tok in ids:
                    key = (node, tok)
                    if key not in children:
                        children[key] = len(parent)
                        parent.append(node)
                        token.append(tok)
                        depth.append(depth[node] + 1)
                        is_end.append(False)
                        entry_of.append(-1)
                    node = children[key]
                is_end[node] = True
                entry_of[node] = entry
        self.blank_id = blank_id
        self.parent = np.array(parent, dtype=np.int32)
        self.token = np.array(token, dtype=np.int32)
        self.depth = np.array(depth, dtype=np.int32)
        self.is_end = np.array(is_end)
        self.entry_of = np.array(entry_of, dtype=np.int32)
        self.n = len(parent)
        self.root_child = self.parent == 0
        self.same_as_parent = self.token == self.token[self.parent]
        self.same_as_parent[0] = False
        self.gather_token = self.token.copy()
        self.gather_token[0] = blank_id

    def __len__(self) -> int:
        return self.n


def spot(
    log_probs: np.ndarray,
    trie: Trie,
    ctc_weight: float = 0.5,
    theta: float = 0.0,
    max_frames_per_token: int = 15,
) -> list[Spot]:
    """Run the DP over ``log_probs`` [T, vocab+1]; return non-overlapping spots by start."""
    if trie.n <= 1:
        return []
    n_frames = log_probs.shape[0]
    n = trie.n
    weight = np.float32(ctc_weight)
    blank = trie.blank_id

    dp_tok = np.full(n, NEG, dtype=np.float32)
    dp_blank = np.full(n, NEG, dtype=np.float32)
    start_tok = np.zeros(n, dtype=np.int32)
    start_blank = np.zeros(n, dtype=np.int32)
    best = log_probs.max(axis=1)
    candidates: list[tuple[float, int, int, int, int]] = []
    budget = np.maximum(trie.depth, 1) * max_frames_per_token

    for t in range(n_frames):
        logp_t = log_probs[t]
        tok_lp = logp_t[trie.gather_token] - best[t]
        blank_lp = np.float32(logp_t[blank] - best[t])

        par = trie.parent
        par_best = np.maximum(dp_tok[par], dp_blank[par])
        par_best_start = np.where(dp_tok[par] >= dp_blank[par], start_tok[par], start_blank[par])
        # a repeated token must be separated by a blank
        from_par = np.where(trie.same_as_parent, dp_blank[par], par_best)
        from_par_start = np.where(trie.same_as_parent, start_blank[par], par_best_start)
        fresh = trie.root_child & (from_par < 0.0)  # a term may start at any frame
        from_par = np.where(fresh, np.float32(0.0), from_par)
        from_par_start = np.where(fresh, t, from_par_start)

        advance = from_par + weight
        new_tok = tok_lp + np.maximum(dp_tok, advance)
        new_start_tok = np.where(advance >= dp_tok, from_par_start, start_tok)
        keep_blank = dp_blank >= dp_tok
        new_blank = blank_lp + np.maximum(dp_tok, dp_blank)
        new_start_blank = np.where(keep_blank, start_blank, start_tok)

        dp_tok, dp_blank = new_tok, new_blank
        start_tok, start_blank = new_start_tok, new_start_blank
        dp_tok[0] = dp_blank[0] = NEG
        # a term may not stretch over too many frames per token
        dp_tok = np.where(t - start_tok + 1 > budget, NEG, dp_tok)
        dp_blank = np.where(t - start_blank + 1 > budget, NEG, dp_blank)

        for e in np.flatnonzero(trie.is_end & (dp_tok >= theta)):
            candidates.append((float(dp_tok[e]), int(trie.depth[e]), int(start_tok[e]), t, int(e)))

    candidates.sort(key=lambda c: (-c[0], -c[1], c[2]))
    accepted: list[tuple[float, int, int, int, int]] = []
    for c in candidates:
        _, _, s, e, _ = c
        if all(e < a_s or s > a_e for _, _, a_s, a_e, _ in accepted):
            accepted.append(c)
    return [
        Spot(
            frame_start=s,
            frame_end=e,
            n_tokens=k,
            score=round(score, 3),
            entry=int(trie.entry_of[node]),
        )
        for score, k, s, e, node in sorted(accepted, key=lambda c: c[2])
    ]
