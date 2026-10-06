"""Financial goals: catalogue, automatic target calculation, at-risk assessment, CRUD and selection."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, ErrorCode, NotFoundError
from app.core.time import ensure_utc, utctoday
from app.models.enums import CreditAccountType, GoalCategory, GoalPriority, GoalStatus, GoalType
from app.models.goal import FinancialGoal
from app.models.user import User
from app.schemas.goal import GoalCreate, GoalInputs, GoalSelectionIn, GoalUpdate
from app.services import onboarding_service
from app.services.financial_service import FinancialSnapshot, build_snapshot

ZERO = Decimal("0")
CENT = Decimal("0.01")

# ---- assumptions (one place to tune them) ------------------------------------------------------
EMERGENCY_FUND_MONTHS = 6
# Upcoming vests are taxed as salary (perquisite) at vest; 30% approximates the top Indian slab.
EQUITY_TAX_RATE = Decimal("0.30")
# Without a risk profile, use this single-stock limit.
DEFAULT_SINGLE_STOCK_LIMIT = Decimal("35")
HOME_DOWN_PAYMENT_SHARE = Decimal("0.20")
HOME_REGISTRATION_STAMP_DUTY = Decimal("0.07")  # typical stamp duty + registration, varies by state
RETIREMENT_SPEND_MULTIPLE = 25
GENERAL_INFLATION = Decimal("0.06")
EDUCATION_INFLATION = Decimal("0.08")
SABBATICAL_MONTHS = 12
HIGH_INTEREST_THRESHOLD = Decimal("9")  # % effective interest; credit cards always count
TERM_COVER_INCOME_MULTIPLE = 15
FAMILY_HEALTH_COVER = Decimal("5000000")  # 50 lakh
# A dated goal is "behind schedule" if progress lags elapsed time by more than this many points.
SCHEDULE_TOLERANCE = Decimal("10")


@dataclass(frozen=True)
class GoalDefinition:
    name: str
    description: str
    category: GoalCategory
    priority: GoalPriority


# Order = order of the cards on the goals screen.
GOAL_CATALOG: dict[GoalType, GoalDefinition] = {
    GoalType.EMERGENCY_FUND: GoalDefinition(
        "Emergency fund (6 months)",
        "6 x your monthly outflow, held in cash you can reach the same day.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
    GoalType.EQUITY_TAX_RESERVE: GoalDefinition(
        "Equity tax reserve",
        "Perquisite tax estimate on your upcoming vests, set aside in cash.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
    GoalType.REDUCE_SINGLE_STOCK_CONCENTRATION: GoalDefinition(
        "Reduce single-stock concentration",
        "Move holdings toward your single-stock limit of net worth in any one ticker.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
    GoalType.HOME_DOWN_PAYMENT: GoalDefinition(
        "Home down payment",
        "20% of target property value plus registration and stamp duty.",
        GoalCategory.PROPERTY, GoalPriority.OPTIONAL,
    ),
    GoalType.RETIREMENT_CORPUS: GoalDefinition(
        "Retirement corpus",
        "25 x your expected annual spend at retirement, inflation-adjusted.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
    GoalType.CHILD_EDUCATION: GoalDefinition(
        "Children's education corpus",
        "Projected fees at 8% education inflation to the year of admission.",
        GoalCategory.FAMILY, GoalPriority.IMPORTANT,
    ),
    GoalType.SABBATICAL_RUNWAY: GoalDefinition(
        "Sabbatical / career break runway",
        "12 months of essential spend plus health cover premiums.",
        GoalCategory.FREEDOM, GoalPriority.OPTIONAL,
    ),
    GoalType.CLEAR_HIGH_INTEREST_DEBT: GoalDefinition(
        "Clear high-interest debt",
        "Outstanding balance on anything above 9% effective interest.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
    GoalType.PROTECTION_TOPUP: GoalDefinition(
        "Protection top-up (term + health)",
        "Term cover of 15 x annual income and family health cover of 50 lakh.",
        GoalCategory.ESSENTIAL, GoalPriority.ESSENTIAL,
    ),
}


@dataclass
class Calculation:
    suggested_target_amount: Decimal | None
    basis: str
    details: dict = field(default_factory=dict)
    required_inputs: list[str] = field(default_factory=list)
    default_current_amount: Decimal = ZERO

    def as_dict(self) -> dict:
        details = {k: _number(v) if isinstance(v, Decimal) else v for k, v in self.details.items()}
        return {
            "suggested_target_amount": self.suggested_target_amount,
            "basis": self.basis,
            "details": details,
            "required_inputs": self.required_inputs,
        }


def _number(v: Decimal) -> int | float:
    return int(v) if v == v.to_integral_value() else float(v)


def fmt_pct(v: Decimal | None) -> str:
    """Decimal('35.00') -> '35', Decimal('73.20') -> '73.2'."""
    return "-" if v is None else f"{v.normalize():f}"


def _dec(inputs: dict, key: str) -> Decimal | None:
    v = inputs.get(key)
    return None if v is None else Decimal(str(v))


def _needs_profile() -> Calculation:
    return Calculation(None, "Add your money details to calculate this goal")


def _needs_equity() -> Calculation:
    return Calculation(None, "Add your equity holdings to calculate this goal")


# ---- calculations (pure functions over the snapshot + goal inputs) ----------------------------

def calc_emergency_fund(s: FinancialSnapshot, _: dict) -> Calculation:
    if not s.profile:
        return _needs_profile()
    target = (s.profile.monthly_spend * EMERGENCY_FUND_MONTHS).quantize(CENT)
    return Calculation(
        target,
        f"{EMERGENCY_FUND_MONTHS} x monthly spending",
        {"monthly_spend": s.profile.monthly_spend, "months": EMERGENCY_FUND_MONTHS, "cash_reserve": s.cash},
        default_current_amount=min(s.cash, target),
    )


def calc_equity_tax_reserve(s: FinancialSnapshot, _: dict) -> Calculation:
    if not s.holdings:
        return _needs_equity()
    unvested = s.unvested_equity
    target = (unvested * EQUITY_TAX_RATE).quantize(CENT)
    return Calculation(
        target,
        f"{int(EQUITY_TAX_RATE * 100)}% estimated tax on upcoming (unvested) equity",
        {"unvested_equity": unvested, "assumed_tax_rate_percent": EQUITY_TAX_RATE * 100},
    )


def concentration_analysis(s: FinancialSnapshot) -> dict | None:
    """Largest single-stock share of net worth vs. the user's limit."""
    top = s.top_position()
    if top is None:
        return None
    limit = s.risk.single_stock_limit_percent if s.risk else DEFAULT_SINGLE_STOCK_LIMIT
    current = s.concentration_percent(top)
    nw = s.net_worth
    excess = max(ZERO, top.vested_value - nw * limit / 100).quantize(CENT) if nw > 0 else top.vested_value
    return {
        "security_name": top.security_name,
        "ticker": top.ticker,
        "value": top.vested_value,
        "net_worth": nw,
        "percent_of_net_worth": current,
        "limit_percent": limit,
        "above_limit": current is None or current > limit,
        "amount_to_diversify": excess,
    }


def calc_concentration(s: FinancialSnapshot, _: dict) -> Calculation:
    a = concentration_analysis(s)
    if a is None:
        return _needs_equity()
    return Calculation(
        a["amount_to_diversify"],
        "Value to diversify so the largest stock is within your single-stock limit",
        {
            "security_name": a["security_name"],
            "position_value": a["value"],
            "net_worth": a["net_worth"],
            "current_concentration_percent": a["percent_of_net_worth"],
            "limit_percent": a["limit_percent"],
            "status": "ABOVE_TARGET" if a["above_limit"] else "WITHIN_TARGET",
        },
    )


def calc_home_down_payment(s: FinancialSnapshot, inputs: dict) -> Calculation:
    value = _dec(inputs, "property_value")
    if value is None:
        return Calculation(None, "Enter the target property value", required_inputs=["property_value"])
    share = HOME_DOWN_PAYMENT_SHARE + HOME_REGISTRATION_STAMP_DUTY
    return Calculation(
        (value * share).quantize(CENT),
        "20% down payment + about 7% registration and stamp duty",
        {
            "property_value": value,
            "down_payment_percent": HOME_DOWN_PAYMENT_SHARE * 100,
            "registration_stamp_duty_percent": HOME_REGISTRATION_STAMP_DUTY * 100,
        },
    )


def calc_retirement(s: FinancialSnapshot, inputs: dict) -> Calculation:
    if not s.profile:
        return _needs_profile()
    annual_spend = s.profile.monthly_spend * 12
    years = inputs.get("years_to_retirement")
    factor = (1 + GENERAL_INFLATION) ** int(years) if years else Decimal("1")
    target = (annual_spend * factor * RETIREMENT_SPEND_MULTIPLE).quantize(CENT)
    basis = f"{RETIREMENT_SPEND_MULTIPLE} x annual spend"
    if years:
        basis += f", grown at {fmt_pct(GENERAL_INFLATION * 100)}% inflation for {years} years"
    return Calculation(
        target,
        basis,
        {"annual_spend_today": annual_spend, "multiple": RETIREMENT_SPEND_MULTIPLE, "years_to_retirement": years},
    )


def calc_child_education(s: FinancialSnapshot, inputs: dict) -> Calculation:
    cost, years = _dec(inputs, "education_cost_today"), inputs.get("years_to_admission")
    missing = [k for k, v in (("education_cost_today", cost), ("years_to_admission", years)) if v is None]
    if missing:
        return Calculation(None, "Enter today's course fees and years until admission", required_inputs=missing)
    target = (cost * (1 + EDUCATION_INFLATION) ** int(years)).quantize(CENT)
    return Calculation(
        target,
        f"Today's fees grown at {fmt_pct(EDUCATION_INFLATION * 100)}% education inflation for {years} years",
        {"education_cost_today": cost, "years_to_admission": years,
         "education_inflation_percent": EDUCATION_INFLATION * 100},
    )


def calc_sabbatical(s: FinancialSnapshot, inputs: dict) -> Calculation:
    if not s.profile:
        return _needs_profile()
    premium = _dec(inputs, "health_premium_annual") or ZERO
    target = (s.profile.monthly_spend * SABBATICAL_MONTHS + premium).quantize(CENT)
    return Calculation(
        target,
        f"{SABBATICAL_MONTHS} months of spending + a year of health premiums",
        {"monthly_spend": s.profile.monthly_spend, "months": SABBATICAL_MONTHS, "health_premium_annual": premium},
    )


def calc_high_interest_debt(s: FinancialSnapshot, _: dict) -> Calculation:
    report = s.credit_report
    if report is None:
        return Calculation(None, "Needs your credit report to find high-interest balances")
    accounts = [
        a for a in report.accounts
        if a.is_active and a.current_balance > 0 and (
            a.account_type == CreditAccountType.CREDIT_CARD
            or (a.interest_rate is not None and a.interest_rate > HIGH_INTEREST_THRESHOLD)
        )
    ]
    target = sum((a.current_balance for a in accounts), ZERO)
    return Calculation(
        target,
        f"Outstanding balance on credit cards and loans above {fmt_pct(HIGH_INTEREST_THRESHOLD)}% interest",
        {"accounts_counted": len(accounts), "interest_threshold_percent": HIGH_INTEREST_THRESHOLD},
    )


def calc_protection(s: FinancialSnapshot, _: dict) -> Calculation:
    if not s.profile:
        return _needs_profile()
    term = (s.profile.annual_income * TERM_COVER_INCOME_MULTIPLE).quantize(CENT)
    existing = s.profile.insurance_cover or ZERO
    return Calculation(
        term,
        f"Term cover of {TERM_COVER_INCOME_MULTIPLE} x annual income (plus a separate family health cover)",
        {"term_cover_needed": term, "family_health_cover": FAMILY_HEALTH_COVER, "existing_cover": existing},
        default_current_amount=min(existing, term),
    )


CALCULATORS = {
    GoalType.EMERGENCY_FUND: calc_emergency_fund,
    GoalType.EQUITY_TAX_RESERVE: calc_equity_tax_reserve,
    GoalType.REDUCE_SINGLE_STOCK_CONCENTRATION: calc_concentration,
    GoalType.HOME_DOWN_PAYMENT: calc_home_down_payment,
    GoalType.RETIREMENT_CORPUS: calc_retirement,
    GoalType.CHILD_EDUCATION: calc_child_education,
    GoalType.SABBATICAL_RUNWAY: calc_sabbatical,
    GoalType.CLEAR_HIGH_INTEREST_DEBT: calc_high_interest_debt,
    GoalType.PROTECTION_TOPUP: calc_protection,
}


def calculate(goal_type: GoalType, s: FinancialSnapshot, inputs: dict | None = None) -> Calculation:
    return CALCULATORS[goal_type](s, inputs or {})


# ---- assessment ------------------------------------------------------------------------------

def progress_percent(goal: FinancialGoal) -> Decimal:
    if goal.target_amount <= 0:
        return Decimal("100.00")
    return min(Decimal("100"), goal.current_amount / goal.target_amount * 100).quantize(CENT)


def assess_risk(goal: FinancialGoal, s: FinancialSnapshot, today: date | None = None) -> str | None:
    """Return a reason string if the goal is at risk, else None."""
    if goal.status != GoalStatus.ACTIVE:
        return None
    today = today or utctoday()
    progress = progress_percent(goal)
    if progress >= 100:
        return None

    if goal.goal_type == GoalType.REDUCE_SINGLE_STOCK_CONCENTRATION:
        a = concentration_analysis(s)
        if a and a["above_limit"]:
            return (
                f"{a['security_name']} is {fmt_pct(a['percent_of_net_worth'])}% of net worth "
                f"(limit {fmt_pct(a['limit_percent'])}%)"
            )

    if goal.target_date:
        if goal.target_date < today:
            return "Target date has passed"
        start = ensure_utc(goal.created_at).date()
        total_days = (goal.target_date - start).days
        if total_days > 0:
            expected = Decimal((today - start).days) / total_days * 100
            if progress + SCHEDULE_TOLERANCE < expected:
                return f"Behind schedule: {progress}% saved vs {expected.quantize(CENT)}% of time elapsed"

    if goal.goal_type == GoalType.EMERGENCY_FUND and s.profile and s.profile.monthly_spend > 0:
        if s.cash < s.profile.monthly_spend * 3:
            return "Cash reserve covers less than 3 months of spending"
    return None


def to_response(goal: FinancialGoal, s: FinancialSnapshot) -> dict:
    reason = assess_risk(goal, s)
    return {
        "id": goal.id,
        "goal_type": goal.goal_type,
        "category": GOAL_CATALOG[goal.goal_type].category,
        "name": goal.name,
        "description": goal.description,
        "priority": goal.priority,
        "target_amount": goal.target_amount,
        "current_amount": goal.current_amount,
        "remaining_amount": max(ZERO, goal.target_amount - goal.current_amount),
        "progress_percent": progress_percent(goal),
        "target_date": goal.target_date,
        "status": goal.status,
        "is_at_risk": reason is not None,
        "at_risk_reason": reason,
        "inputs": goal.inputs,
        "calculation": calculate(goal.goal_type, s, goal.inputs).as_dict(),
        "created_at": goal.created_at,
        "updated_at": goal.updated_at,
    }


# ---- CRUD ------------------------------------------------------------------------------------

def _inputs_json(inputs: GoalInputs | None) -> dict | None:
    if inputs is None:
        return None
    data = inputs.model_dump(mode="json", exclude_none=True)
    return data or None


def _resolve_target(goal_type: GoalType, s: FinancialSnapshot, target: Decimal | None, inputs: dict | None):
    calc = calculate(goal_type, s, inputs)
    resolved = target if target is not None else calc.suggested_target_amount
    if resolved is None:
        need = f" Required inputs: {', '.join(calc.required_inputs)}." if calc.required_inputs else ""
        raise AppError(
            422, f"target_amount is required for {goal_type.value}. {calc.basis}.{need}", ErrorCode.GOAL_TARGET_REQUIRED
        )
    return resolved, calc


async def _list(db: AsyncSession, user: User) -> list[FinancialGoal]:
    stmt = select(FinancialGoal).where(FinancialGoal.user_id == user.id).order_by(FinancialGoal.id)
    return list((await db.execute(stmt)).scalars())


async def list_goals(db: AsyncSession, user: User) -> list[dict]:
    snapshot = await build_snapshot(db, user)
    return [to_response(g, snapshot) for g in await _list(db, user)]


async def get_owned(db: AsyncSession, user: User, goal_id: int) -> FinancialGoal:
    goal = (
        await db.execute(select(FinancialGoal).where(FinancialGoal.id == goal_id, FinancialGoal.user_id == user.id))
    ).scalar_one_or_none()
    if goal is None:
        raise NotFoundError("Goal not found", ErrorCode.GOAL_NOT_FOUND)
    return goal


async def suggestions(db: AsyncSession, user: User) -> list[dict]:
    snapshot = await build_snapshot(db, user)
    existing = {g.goal_type: g for g in await _list(db, user)}
    out = []
    for gt, d in GOAL_CATALOG.items():
        saved = existing.get(gt)
        out.append({
            "goal_type": gt,
            "category": d.category,
            "name": d.name,
            "description": d.description,
            "priority": d.priority,
            "calculation": calculate(gt, snapshot, saved.inputs if saved else None).as_dict(),
            "already_added": saved is not None,
        })
    return out


def _new_goal(user: User, goal_type: GoalType, target: Decimal, calc: Calculation, inputs: dict | None, **over):
    d = GOAL_CATALOG[goal_type]
    return FinancialGoal(
        user_id=user.id,
        goal_type=goal_type,
        name=over.get("name") or d.name,
        description=over["description"] if over.get("description") is not None else d.description,
        priority=over.get("priority") or d.priority,
        target_amount=target,
        current_amount=over["current_amount"] if over.get("current_amount") is not None else calc.default_current_amount,
        target_date=over.get("target_date"),
        status=GoalStatus.ACTIVE,
        inputs=inputs,
    )


async def create(db: AsyncSession, user: User, payload: GoalCreate) -> dict:
    snapshot = await build_snapshot(db, user)
    inputs = _inputs_json(payload.inputs)
    target, calc = _resolve_target(payload.goal_type, snapshot, payload.target_amount, inputs)
    goal = _new_goal(
        user, payload.goal_type, target, calc, inputs,
        name=payload.name, description=payload.description, priority=payload.priority,
        current_amount=payload.current_amount, target_date=payload.target_date,
    )
    db.add(goal)
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    await db.refresh(goal)
    return to_response(goal, snapshot)


async def update(db: AsyncSession, user: User, goal_id: int, payload: GoalUpdate) -> dict:
    goal = await get_owned(db, user, goal_id)
    data = payload.model_dump(exclude_unset=True)
    if "inputs" in data:
        goal.inputs = _inputs_json(payload.inputs)
        data.pop("inputs")
    for k, v in data.items():
        if v is None and k not in ("description", "target_date"):
            continue
        setattr(goal, k, v)
    await db.commit()
    await db.refresh(goal)
    return to_response(goal, await build_snapshot(db, user))


async def delete(db: AsyncSession, user: User, goal_id: int) -> None:
    goal = await get_owned(db, user, goal_id)
    await db.delete(goal)
    await db.commit()


async def save_selection(db: AsyncSession, user: User, payload: GoalSelectionIn) -> list[dict]:
    """Make the user's goals exactly the ticked set (one goal per type).

    Ticked + already saved -> kept (target/inputs updated if sent); ticked + new -> created with
    the calculated target; saved but not ticked -> deleted. All or nothing.
    """
    snapshot = await build_snapshot(db, user)
    existing: dict[GoalType, list[FinancialGoal]] = {}
    for g in await _list(db, user):
        existing.setdefault(g.goal_type, []).append(g)

    # Validate everything before changing anything.
    plan = []
    for item in payload.goals:
        current = existing.get(item.goal_type, [None])[0]
        inputs = _inputs_json(item.inputs) if item.inputs is not None else (current.inputs if current else None)
        if current is None or item.target_amount is not None or item.inputs is not None:
            target, calc = _resolve_target(item.goal_type, snapshot, item.target_amount, inputs)
        else:
            target, calc = current.target_amount, None
        plan.append((item, current, inputs, target, calc))

    selected = {item.goal_type for item in payload.goals}
    removed = [gt for gt in existing if gt not in selected]
    if removed:
        await db.execute(
            sa_delete(FinancialGoal).where(FinancialGoal.user_id == user.id, FinancialGoal.goal_type.in_(removed))
        )
    for item, current, inputs, target, calc in plan:
        if current is None:
            db.add(_new_goal(user, item.goal_type, target, calc, inputs))
        else:
            current.target_amount = target
            current.inputs = inputs
    await db.flush()
    await onboarding_service.refresh(db, user)
    await db.commit()
    return await list_goals(db, user)


async def assess_all(db: AsyncSession, user: User, snapshot: FinancialSnapshot) -> list[tuple[FinancialGoal, str | None]]:
    return [(g, assess_risk(g, snapshot)) for g in await _list(db, user)]
