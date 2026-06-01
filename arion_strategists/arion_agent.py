# ArionStrategists - SCML Standard track (CS451/551)
# Muhammad Raees Azam (S050683), Mehak Arshid (S050293)
# Extends SyncRandomStdAgent with bundle selection + partner memory.

from __future__ import annotations

import os
from itertools import combinations
from typing import Literal

from negmas import Outcome, ResponseType, SAOResponse, SAOState
from scml.oneshot.common import QUANTITY, TIME, UNIT_PRICE
from scml.std.agents.rand import SyncRandomStdAgent

StrategyName = Literal["baseline", "optimize", "search", "game", "hybrid"]

# submission default after local benchmarks
DEFAULT_STRATEGY: StrategyName = "game"


class ArionAgent(SyncRandomStdAgent):
    # tuned on our std worlds
    PRODUCTION_NORMAL = 0.42
    PRODUCTION_URGENT = 0.58
    UTIL_FLOOR_NORMAL = 0.22
    UTIL_FLOOR_URGENT = 0.12
    UTIL_FLOOR_LATE = 0.08
    MAX_SUBSET = 8
    LATE_REL = 0.78
    BEAM_WIDTH = 6
    OVERORDER_FRAC = 0.15

    def __init__(self, *args, strategy: StrategyName | None = None, **kwargs):
        kwargs.setdefault("today_target_productivity", 0.42)
        kwargs.setdefault("future_target_productivity", 0.32)
        kwargs.setdefault("today_concession_exp", 1.55)
        kwargs.setdefault("future_concession_exp", 4.0)
        kwargs.setdefault("pfuture", 0.11)
        kwargs.setdefault("prioritize_near_future", True)
        kwargs.setdefault("today_concentration", 0.32)
        super().__init__(*args, **kwargs)

        picked = strategy
        if picked is None:
            env = os.environ.get("ARION_STRATEGY", "").strip().lower()
            if env in ("baseline", "optimize", "search", "game", "hybrid"):
                picked = env  # type: ignore[assignment]
            else:
                picked = DEFAULT_STRATEGY
        self._strategy: StrategyName = picked  # type: ignore[assignment]

        self._partner_best_buy: dict[str, float] = {}
        self._partner_best_sell: dict[str, float] = {}
        self._partner_offers_seen: dict[str, int] = {}
        self._step_supplies = 0
        self._step_sales = 0
        self._urgent = False
        self._prod_anchor = self.PRODUCTION_NORMAL

    def init(self):
        self._partner_best_buy.clear()
        self._partner_best_sell.clear()
        self._partner_offers_seen.clear()

    def before_step(self):
        ufun = getattr(self, "ufun", None)
        if ufun is not None:
            try:
                ufun.find_limit(True)
                ufun.find_limit(False)
            except MemoryError:
                pass
        self._step_supplies = 0
        self._step_sales = 0
        awi = self.awi
        self._urgent = int(awi.needed_supplies) > 0 or int(awi.needed_sales) > 0
        if self._urgent:
            self._prod_anchor = self.PRODUCTION_URGENT
        else:
            self._prod_anchor = self.PRODUCTION_NORMAL
        self.today_productivity = self._prod_anchor

    def on_negotiation_success(self, contract, mechanism):
        super().on_negotiation_success(contract, mechanism)
        agr = contract.agreement
        t = agr.get("time", agr.get(TIME))
        price = agr.get("unit_price", agr.get(UNIT_PRICE))
        if t is None or price is None:
            return
        if int(t) != int(self.awi.current_step):
            return
        price = float(price)
        qty = int(agr.get("quantity", agr.get(QUANTITY, 0)))

        if contract.annotation["product"] == self.awi.my_input_product:
            seller = contract.annotation["seller"]
            old = self._partner_best_buy.get(seller, price)
            self._partner_best_buy[seller] = min(old, price)
            self._step_supplies += qty
        else:
            buyer = contract.annotation["buyer"]
            old = self._partner_best_sell.get(buyer, price)
            self._partner_best_sell[buyer] = max(old, price)
            self._step_sales += qty

    def _today_supply_need(self) -> int:
        awi = self.awi
        target = int(awi.n_lines * self._prod_anchor)
        have = int(awi.current_inventory_input) + int(awi.total_supplies_at(awi.current_step))
        return max(0, target - have, int(awi.needed_supplies))

    def _today_sales_need(self) -> int:
        awi = self.awi
        if int(awi.total_sales_at(awi.current_step)) > int(awi.n_lines):
            return 0
        target = int(awi.n_lines * self._prod_anchor)
        cap = min(int(awi.n_lines), target + int(awi.current_inventory_input))
        sold = int(awi.total_sales_at(awi.current_step))
        return max(0, cap - sold, int(awi.needed_sales))

    def _util_floor(self) -> float:
        ufun = getattr(self, "ufun", None)
        if ufun is None or ufun.max_utility <= 0:
            return 0.0
        frac = self.UTIL_FLOOR_URGENT if self._urgent else self.UTIL_FLOOR_NORMAL
        rel = float(getattr(self.awi, "relative_time", 0.0) or 0.0)
        if rel > self.LATE_REL:
            frac = min(frac, self.UTIL_FLOOR_LATE)
        return frac * float(ufun.max_utility)

    def _bundle_util(self, chosen: dict[str, Outcome], *, selling: bool) -> float:
        ufun = getattr(self, "ufun", None)
        if ufun is None or not chosen:
            return -1.0
        try:
            outs = tuple(chosen.values())
            flags = tuple(selling for _ in chosen)
            return float(ufun.from_offers(outs, flags))
        except MemoryError:
            return -1.0
        except Exception:
            return -1.0

    def _qty_cap(self, need: int) -> int:
        extra = int(self.awi.n_lines * self.OVERORDER_FRAC)
        return need + extra

    def _rank_offers(self, side_offers: dict[str, Outcome], *, selling: bool):
        if selling:
            return sorted(side_offers.items(), key=lambda kv: -int(kv[1][UNIT_PRICE]))
        return sorted(side_offers.items(), key=lambda kv: int(kv[1][UNIT_PRICE]))

    def _subset_qty(self, chosen: dict[str, Outcome]) -> int:
        return sum(int(o[QUANTITY]) for o in chosen.values())

    def _subset_score(self, chosen, need, util, floor):
        # higher tuple wins: utility, covers need, small gap, fewer units
        if util < floor:
            return (-1.0, -1, -1, -1.0)
        qty = self._subset_qty(chosen)
        if qty > self._qty_cap(need):
            return (-1.0, -1, -1, -1.0)
        gap = abs(qty - need)
        covers = 1 if qty >= need else 0
        return (util, covers, -gap, -qty)

    def _best_subset_baseline(self, side_offers, need, *, selling: bool):
        if need <= 0 or not side_offers:
            return {}
        floor = self._util_floor()
        ranked = self._rank_offers(side_offers, selling=selling)
        partners = [p for p, _ in ranked]
        offers = {p: o for p, o in ranked}

        if len(partners) <= self.MAX_SUBSET:
            best = {}
            best_u = -1.0
            for r in range(1, len(partners) + 1):
                for combo in combinations(partners, r):
                    qty = sum(int(offers[p][QUANTITY]) for p in combo)
                    if qty > self._qty_cap(need):
                        continue
                    trial = {p: offers[p] for p in combo}
                    u = self._bundle_util(trial, selling=selling)
                    if u >= floor and u > best_u:
                        best_u = u
                        best = trial
            if best:
                return best

        chosen = {}
        got = 0
        for partner, offer in ranked:
            trial = dict(chosen)
            trial[partner] = offer
            if self._bundle_util(trial, selling=selling) >= floor:
                chosen = trial
                got += int(offer[QUANTITY])
                if got >= need:
                    break
        return chosen

    def _best_subset_optimize(self, side_offers, need, *, selling: bool):
        if need <= 0 or not side_offers:
            return {}
        floor = self._util_floor()
        ranked = self._rank_offers(side_offers, selling=selling)
        partners = [p for p, _ in ranked]
        offers = {p: o for p, o in ranked}

        best = {}
        best_score = (-1.0, -1, -1, -1.0)
        limit = min(len(partners), self.MAX_SUBSET)
        for r in range(1, limit + 1):
            for combo in combinations(partners, r):
                trial = {p: offers[p] for p in combo}
                u = self._bundle_util(trial, selling=selling)
                sc = self._subset_score(trial, need, u, floor)
                if sc > best_score:
                    best_score = sc
                    best = trial
        if best:
            return best
        return self._best_subset_baseline(side_offers, need, selling=selling)

    def _best_subset_search(self, side_offers, need, *, selling: bool):
        if need <= 0 or not side_offers:
            return {}
        floor = self._util_floor()
        ranked = self._rank_offers(side_offers, selling=selling)

        beam = [{}]
        for partner, offer in ranked:
            nxt = []
            for state in beam:
                nxt.append(state)
                trial = dict(state)
                trial[partner] = offer
                if self._subset_qty(trial) <= self._qty_cap(need):
                    nxt.append(trial)
            scored = []
            for state in nxt:
                if not state:
                    scored.append(((0.0, 0, 0, 0.0), state))
                    continue
                u = self._bundle_util(state, selling=selling)
                scored.append((self._subset_score(state, need, u, floor), state))
            scored.sort(key=lambda x: x[0], reverse=True)
            beam = [s for _, s in scored[: self.BEAM_WIDTH]]

        best = {}
        best_score = (-1.0, -1, -1, -1.0)
        for state in beam:
            if not state:
                continue
            u = self._bundle_util(state, selling=selling)
            sc = self._subset_score(state, need, u, floor)
            if sc > best_score:
                best_score = sc
                best = state
        if best:
            return best
        return self._best_subset_baseline(side_offers, need, selling=selling)

    def _select_today_bundle(self, side_offers, need, *, selling: bool):
        mode = self._strategy
        if mode == "optimize":
            return self._best_subset_optimize(side_offers, need, selling=selling)
        if mode == "search":
            return self._best_subset_search(side_offers, need, selling=selling)
        if mode == "hybrid":
            return self._best_subset_search(side_offers, need, selling=selling)
        # baseline and game both use greedy/exhaustive bundles
        return self._best_subset_baseline(side_offers, need, selling=selling)

    def _nash_reservation(self, mn: int, mx: int, *, buying: bool) -> int:
        rel = float(getattr(self.awi, "relative_time", 0.0) or 0.0)
        t = min(1.0, max(0.0, rel)) ** 1.4
        mid = (mn + mx) / 2.0
        if buying:
            target = mn + (mid - mn) * (0.25 + 0.65 * t)
            return int(min(mx, max(mn, target)))
        target = mx - (mx - mid) * (0.25 + 0.65 * t)
        return int(max(mn, min(mx, target)))

    def _anchor_price_baseline(self, partner: str, *, buying: bool, mn: int, mx: int) -> int:
        rel = float(getattr(self.awi, "relative_time", 0.0) or 0.0)
        t = rel ** 1.6
        if buying:
            anchor = self._partner_best_buy.get(partner, float(mx))
            cap = int(mn + (mx - mn) * (0.35 + 0.55 * t))
            return int(min(cap, max(mn, anchor + 1)))
        anchor = self._partner_best_sell.get(partner, float(mn))
        floor = int(mx - (mx - mn) * (0.35 + 0.55 * t))
        return int(max(floor, min(mx, anchor - 1)))

    def _anchor_price_game(self, partner: str, *, buying: bool, mn: int, mx: int) -> int:
        nash = self._nash_reservation(mn, mx, buying=buying)
        if buying:
            hist = self._partner_best_buy.get(partner)
            if hist is not None:
                return int(min(nash, max(mn, hist + 1)))
            return nash
        hist = self._partner_best_sell.get(partner)
        if hist is not None:
            return int(max(nash, min(mx, hist - 1)))
        return nash

    def _anchor_price(self, partner: str, *, buying: bool, mn: int, mx: int) -> int:
        if self._strategy in ("game", "hybrid"):
            return self._anchor_price_game(partner, buying=buying, mn=mn, mx=mx)
        return self._anchor_price_baseline(partner, buying=buying, mn=mn, mx=mx)

    def _should_salvage(self, rel: float) -> bool:
        if self._strategy == "hybrid":
            return self._urgent or rel > self.LATE_REL
        return rel > self.LATE_REL

    def _salvage_today(self, responses, buy_today, sell_today, supply_need, sales_need):
        got_in = sum(int(buy_today[p][QUANTITY]) for p in responses if p in buy_today)
        got_out = sum(int(sell_today[p][QUANTITY]) for p in responses if p in sell_today)
        rem_in = max(0, supply_need - got_in)
        rem_out = max(0, sales_need - got_out)

        for p in sorted(buy_today, key=lambda x: int(buy_today[x][UNIT_PRICE])):
            if rem_in <= 0 or p in responses:
                continue
            q = int(buy_today[p][QUANTITY])
            if q <= rem_in:
                responses[p] = SAOResponse(ResponseType.ACCEPT_OFFER, buy_today[p])
                rem_in -= q

        for p in sorted(sell_today, key=lambda x: int(sell_today[x][UNIT_PRICE]), reverse=True):
            if rem_out <= 0 or p in responses:
                continue
            q = int(sell_today[p][QUANTITY])
            if q <= rem_out:
                responses[p] = SAOResponse(ResponseType.ACCEPT_OFFER, sell_today[p])
                rem_out -= q

    def counter_all(self, offers: dict[str, Outcome], states: dict[str, SAOState]):
        max_sell = self.awi.current_output_issues[UNIT_PRICE].max_value
        min_sell = max(
            self.awi.current_output_issues[UNIT_PRICE].min_value,
            self.awi.current_input_issues[UNIT_PRICE].max_value,
        )
        min_buy = self.awi.current_input_issues[UNIT_PRICE].min_value
        max_buy = min(
            self.awi.current_input_issues[UNIT_PRICE].max_value,
            self.awi.current_output_issues[UNIT_PRICE].min_value,
        )

        needed_supplies, needed_sales = self.estimate_future_needs()
        c = int(self.awi.current_step)
        supply_need = max(
            int(self.awi.needed_supplies),
            self._today_supply_need(),
            int(needed_supplies.get(c, 0)),
        )
        sales_need = max(
            int(self.awi.needed_sales),
            self._today_sales_need(),
            int(needed_sales.get(c, 0)),
        )
        if self.awi.is_middle_level:
            floor_lines = int(self.awi.n_lines * self._prod_anchor)
            supply_need = max(supply_need, floor_lines)
            sales_need = max(sales_need, floor_lines)
        needed_supplies[c] = supply_need
        needed_sales[c] = sales_need

        responses: dict[str, SAOResponse] = {}
        rel = float(getattr(self.awi, "relative_time", 0.0) or 0.0)

        buy_today = {
            p: offers[p]
            for p in offers
            if offers[p] is not None
            and self.is_supplier(p)
            and int(offers[p][TIME]) == c
            and int(offers[p][QUANTITY]) > 0
        }
        sell_today = {
            p: offers[p]
            for p in offers
            if offers[p] is not None
            and self.is_consumer(p)
            and int(offers[p][TIME]) == c
            and int(offers[p][QUANTITY]) > 0
        }

        for p, off in self._select_today_bundle(buy_today, supply_need, selling=False).items():
            responses[p] = SAOResponse(ResponseType.ACCEPT_OFFER, off)
        for p, off in self._select_today_bundle(sell_today, sales_need, selling=True).items():
            responses[p] = SAOResponse(ResponseType.ACCEPT_OFFER, off)

        if self._should_salvage(rel):
            self._salvage_today(responses, buy_today, sell_today, supply_need, sales_need)

        n = max(int(self.awi.n_steps) - c, 1)
        for is_partner, needs, is_good_price, mn, mx, buy_side in (
            (self.is_supplier, needed_supplies, self.good2buy, min_buy, max_buy, True),
            (self.is_consumer, needed_sales, self.good2sell, min_sell, max_sell, False),
        ):
            if mn > mx:
                continue
            partners = [
                p for p in offers if p not in responses and is_partner(p) and offers[p] is not None
            ]
            partners.sort(key=lambda p: int(offers[p][UNIT_PRICE]), reverse=not buy_side)
            for partner in partners:
                offer = offers[partner]
                q, t = int(offer[QUANTITY]), int(offer[TIME])
                if q <= 0:
                    continue
                today = t == c
                state = states[partner]
                r = float(state.relative_time) if today else (t - c) / n
                if not is_good_price(float(offer[UNIT_PRICE]), r, mn, mx, today):
                    continue
                need_t = int(needs.get(t, 0))
                if today:
                    if 0 < q <= need_t:
                        responses[partner] = SAOResponse(ResponseType.ACCEPT_OFFER, offer)
                        needs[t] = need_t - q
                elif 0 < q < need_t:
                    responses[partner] = SAOResponse(ResponseType.ACCEPT_OFFER, offer)
                    needs[t] = need_t - q

        remaining = {k for k in offers if k not in responses}
        distribution = self.distribute_todays_needs(partners=remaining)
        future_partners = {k for k, v in distribution.items() if v <= 0}
        unneeded = None if not self.awi.allow_zero_quantity else (0, c, 0)
        myoffers: dict[str, Outcome | None] = {}
        for partner, q in distribution.items():
            if q > 0:
                if self.is_supplier(partner):
                    mn_p, mx_p = min_buy, max_buy
                else:
                    mn_p, mx_p = min_sell, max_sell
                price = self._anchor_price(
                    partner,
                    buying=self.is_supplier(partner),
                    mn=int(mn_p),
                    mx=int(mx_p),
                )
                myoffers[partner] = (int(q), c, price)
            else:
                myoffers[partner] = unneeded
        myoffers |= self.distribute_future_offers(list(future_partners))
        for k, offer in myoffers.items():
            if k not in responses:
                responses[k] = SAOResponse(ResponseType.REJECT_OFFER, offer)
        return responses


# extra classes for local comparison only
class ArionAgentBaseline(ArionAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, strategy="baseline", **kwargs)


class ArionAgentOptimize(ArionAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, strategy="optimize", **kwargs)


class ArionAgentSearch(ArionAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, strategy="search", **kwargs)


class ArionAgentGame(ArionAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, strategy="game", **kwargs)


class ArionAgentHybrid(ArionAgent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, strategy="hybrid", **kwargs)


STRATEGY_VARIANTS: dict[str, type[ArionAgent]] = {
    "baseline": ArionAgentBaseline,
    "optimize": ArionAgentOptimize,
    "search": ArionAgentSearch,
    "game": ArionAgentGame,
    "hybrid": ArionAgentHybrid,
}


if __name__ == "__main__":
    import sys

    from .helpers.runner import run

    run([ArionAgent], sys.argv[1] if len(sys.argv) > 1 else "std")
