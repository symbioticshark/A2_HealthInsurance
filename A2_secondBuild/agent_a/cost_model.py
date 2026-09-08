"""
D6 -- the three-layer cost model, straight from the brief's formulas.

Two different uses, kept clearly separate:
  * estimate_tokens_for_run() -- a MODEL of tokens, used only to give the
    scripted backend something to check the budget ceiling against and to
    let you sanity-check turn-count trade-offs before spending a live cent.
  * cost_from_measured() -- takes REAL numbers (your D4 success rate, your
    D5 measured token counts from the API's own usage field) and turns them
    into the report's cost-to-serve figures. This is the one that belongs
    in your report; the estimate above never should.
"""
from dataclasses import dataclass
from . import config


def estimate_tokens_for_run(turns: int, base_prefix: int = 1200, growth_per_turn: int = 400):
    """input ~= B*T + D*T*(T-1)/2 -- Class 5's exact sum (D2c). Used ONLY
    for the scripted backend's own budget-ceiling bookkeeping; not a
    substitute for measured tokens in the report."""
    b, d, t = base_prefix, growth_per_turn, turns
    input_tokens = b * t + d * t * (t - 1) // 2
    output_tokens = 60 * t   # a short Thought+Action per turn, roughly
    return input_tokens, output_tokens


def price_run(input_tokens: int, output_tokens: int, tier: str = "cheap"):
    price_in, price_out = config.PRICE_TABLE[tier]
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


@dataclass
class CostToServe:
    layer1_variable: float          # per-task tokens/tools, this model, this success
    layer2_expected_fallback: float  # (1 - success_rate) * failure_cost
    layer3_fixed_monthly: float
    volume_per_month: int

    @property
    def cost_per_successful_task(self):
        return self.layer1_variable + self.layer2_expected_fallback

    @property
    def monthly_cost(self):
        return self.cost_per_successful_task * self.volume_per_month + self.layer3_fixed_monthly


def cost_from_measured(mean_input_tokens: float, mean_output_tokens: float, tier: str,
                        success_rate: float, failure_cost_usd: float,
                        volume_per_month: int, fixed_monthly_usd: float,
                        retrieval_and_tool_fees_usd: float = 0.0) -> CostToServe:
    """Builds the three-layer model from MEASURED quantities (D4 success
    rate, D5 mean tokens per run from the API usage field)."""
    layer1 = price_run(mean_input_tokens, mean_output_tokens, tier) + retrieval_and_tool_fees_usd
    layer2 = (1 - success_rate) * failure_cost_usd
    return CostToServe(layer1, layer2, fixed_monthly_usd, volume_per_month)


def sensitivity_table(mean_input_tokens: float, mean_output_tokens: float, tier: str,
                       measured_success_rate: float, failure_cost_usd: float,
                       volume_per_month: int, fixed_monthly_usd: float, delta_pp: float = 0.10):
    """Cost per successful task across success_rate +/- delta_pp, per D6's
    'a sensitivity table, not a point estimate.'"""
    rows = []
    for offset in (-delta_pp, -delta_pp / 2, 0.0, delta_pp / 2, delta_pp):
        sr = min(1.0, max(0.0, measured_success_rate + offset))
        c = cost_from_measured(mean_input_tokens, mean_output_tokens, tier, sr,
                                failure_cost_usd, volume_per_month, fixed_monthly_usd)
        rows.append({"success_rate": round(sr, 3), "cost_per_successful_task": round(c.cost_per_successful_task, 4)})
    return rows


def break_even_success_rate(cheap_run_cost: float, expensive_cost_per_success: float, failure_cost_usd: float):
    """failures you can afford = (E - C) / F ; break-even p = 1 - that.
    E includes the expensive model's own failures (already folded into
    expensive_cost_per_success); C does not, because the cheap model's
    success rate is the unknown being solved for."""
    e, c, f = expensive_cost_per_success, cheap_run_cost, failure_cost_usd
    affordable_failure_rate = (e - c) / f
    return 1 - affordable_failure_rate, affordable_failure_rate


# Problem A defaults from Appendix A, section 7 and D6.
PROBLEM_A_VOLUME_PER_MONTH = 8000
PROBLEM_A_FAILURE_COST_USD = 7.60   # US$38/hr assessor x 12 min / 60
