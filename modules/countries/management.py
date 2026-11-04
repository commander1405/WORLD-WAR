"""Country dashboard, cabinet, budget and policies — persisted state changes."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from database.interface import Database
from engine.world_engine import WorldEngine
from engine.economy_engine import EconomyEngine
from engine.event_engine import EventEngine


PORTFOLIOS = [
    "finance",
    "defense",
    "foreign",
    "interior",
    "economy",
]


class CountryManagement:
    def __init__(self, db: Database, world: WorldEngine, economy: EconomyEngine):
        self.db = db
        self.world = world
        self.economy = economy
        self.events = EventEngine(db)

    async def ensure_schema(self) -> None:
        # migrations should create tables; init economy rows for existing countries
        countries = await self.db.fetch("SELECT country_code, treasury, stability FROM countries")
        for c in countries:
            code = c["country_code"]
            row = await self.db.fetchrow(
                "SELECT country_code FROM country_economy WHERE country_code = $1", (code,)
            )
            if not row:
                baseline = await self.db.fetchrow(
                    "SELECT gdp_ref FROM country_baselines WHERE country_code = $1", (code,)
                )
                gdp = float(baseline["gdp_ref"] or 0) if baseline else 0.0
                # scale treasury seed as small fraction of GDP units (abstract)
                treasury = float(c.get("treasury") or 0) or max(gdp * 0.01, 0)
                now = datetime.now(timezone.utc).isoformat()
                await self.db.execute(
                    """
                    INSERT INTO country_economy (
                        country_code, treasury, tax_rate, public_spending_rate, gdp,
                        public_satisfaction, stability, updated_at
                    ) VALUES ($1,$2,0.15,0.12,$3,50,$4,$5)
                    """,
                    (code, treasury, gdp, float(c.get("stability") or 50), now),
                )
            # default sectors
            for sector in ("agriculture", "industry", "services", "energy"):
                exists = await self.db.fetchrow(
                    "SELECT sector_code FROM production_sectors WHERE country_code=$1 AND sector_code=$2",
                    (code, sector),
                )
                if not exists:
                    await self.db.execute(
                        "INSERT INTO production_sectors (country_code, sector_code, output_level, investment) VALUES ($1,$2,50,0)",
                        (code, sector),
                    )

    async def dashboard(self, country_code: str) -> str:
        code = country_code.upper()
        c = await self.db.fetchrow("SELECT * FROM countries WHERE country_code=$1", (code,))
        b = await self.db.fetchrow("SELECT * FROM country_baselines WHERE country_code=$1", (code,))
        e = await self.db.fetchrow("SELECT * FROM country_economy WHERE country_code=$1", (code,))
        if not c or not e:
            return "کشور یافت نشد."
        gdate = await self.world.current_game_date()
        sectors = await self.db.fetch(
            "SELECT * FROM production_sectors WHERE country_code=$1 ORDER BY sector_code", (code,)
        )
        cabinet = await self.db.fetch(
            "SELECT * FROM cabinet_members WHERE country_code=$1 ORDER BY portfolio", (code,)
        )
        resources = await self.economy.get_resources(code)
        flag = (b or {}).get("flag") or c.get("flag") or ""
        lines = [
            f"📊 داشبورد {flag} {c.get('name_fa') or c.get('name_en')} ({code})",
            f"📅 تاریخ بازی: {gdate.isoformat()}",
            f"🏛 حکومت (پایه تاریخی): {(b or {}).get('government_type') or 'نامشخص'}",
            f"👤 رهبر پایه ۲۰۲۰: {(b or {}).get('leader_name') or 'نامشخص'}",
            f"👥 جمعیت: {c.get('population')}",
            f"💰 GDP (شبیه‌سازی): {e.get('gdp'):,.0f}",
            f"🏦 خزانه: {e.get('treasury'):,.0f}",
            f"📈 مالیات: {float(e.get('tax_rate') or 0)*100:.1f}%",
            f"📉 مخارج عمومی: {float(e.get('public_spending_rate') or 0)*100:.1f}%",
            f"😊 رضایت عمومی: {e.get('public_satisfaction')}",
            f"⚖ ثبات: {e.get('stability')}",
            "",
            "🏭 تولید:",
        ]
        for s in sectors:
            lines.append(f"  • {s['sector_code']}: سطح {s['output_level']} | سرمایه‌گذاری {s['investment']}")
        lines.append("")
        lines.append("📦 منابع:")
        if resources:
            for r in resources:
                lines.append(f"  • {r['resource_code']}: {r['quantity']} {r.get('unit') or ''}")
        else:
            lines.append("  • هنوز منبع پویایی ثبت نشده")
        lines.append("")
        lines.append("🧑‍💼 کابینه:")
        if cabinet:
            for m in cabinet:
                lines.append(f"  • {m['portfolio']}: {m['minister_name']} (توانایی {m['competence']})")
        else:
            lines.append("  • خالی — با «انتصاب وزارت …» وزیر بگذارید")
        lines.append("")
        lines.append("دستورات: مالیات X | مخارج X | سرمایه‌گذاری SECTOR AMT | انتصاب PORTFOLIO NAME | برکناری PORTFOLIO")
        lines.append("بازگشت: منو")
        return "\n".join(lines)

    async def set_tax_rate(self, country_code: str, rate: float, player_id: int | None = None) -> str:
        code = country_code.upper()
        rate = max(0.0, min(0.5, rate))
        e = await self._eco(code)
        old = float(e["tax_rate"])
        # higher tax raises treasury growth potential but lowers satisfaction
        sat = float(e["public_satisfaction"]) - (rate - old) * 40
        sat = max(0, min(100, sat))
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE country_economy SET tax_rate=$1, public_satisfaction=$2, updated_at=$3 WHERE country_code=$4",
            (rate, sat, now, code),
        )
        await self.events.record(
            "policy_tax",
            summary=f"{code} tax_rate {old:.2f}->{rate:.2f}",
            actor_player_id=player_id,
            country_code=code,
            payload={"old": old, "new": rate},
        )
        await self.db.execute(
            """
            INSERT INTO news_items (game_date, real_time, headline, body, country_code, importance)
            VALUES ($1,$2,$3,$4,$5,2)
            """,
            (
                (await self.world.current_game_date()).isoformat(),
                now,
                f"تغییر نرخ مالیات در {code}",
                f"نرخ مالیات از {old*100:.1f}% به {rate*100:.1f}% تغییر کرد.",
                code,
            ),
        )
        return f"✅ نرخ مالیات {code}: {rate*100:.1f}% | رضایت عمومی: {sat:.1f}"

    async def set_spending_rate(self, country_code: str, rate: float, player_id: int | None = None) -> str:
        code = country_code.upper()
        rate = max(0.0, min(0.5, rate))
        e = await self._eco(code)
        old = float(e["public_spending_rate"])
        sat = float(e["public_satisfaction"]) + (rate - old) * 30
        sat = max(0, min(100, sat))
        stab = float(e["stability"]) + (rate - old) * 10
        stab = max(0, min(100, stab))
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE country_economy SET public_spending_rate=$1, public_satisfaction=$2, stability=$3, updated_at=$4 WHERE country_code=$5",
            (rate, sat, stab, now, code),
        )
        # mirror stability on countries table
        await self.db.execute(
            "UPDATE countries SET stability=$1, updated_at=$2 WHERE country_code=$3",
            (stab, now, code),
        )
        await self.events.record(
            "policy_spending",
            summary=f"{code} spending {old:.2f}->{rate:.2f}",
            actor_player_id=player_id,
            country_code=code,
            payload={"old": old, "new": rate},
        )
        return f"✅ مخارج عمومی {code}: {rate*100:.1f}% | رضایت {sat:.1f} | ثبات {stab:.1f}"

    async def invest(self, country_code: str, sector: str, amount: float, player_id: int | None = None) -> str:
        code = country_code.upper()
        sector = sector.lower().strip()
        amount = max(0.0, amount)
        e = await self._eco(code)
        if amount > float(e["treasury"]):
            return "❌ موجودی خزانه کافی نیست."
        sec = await self.db.fetchrow(
            "SELECT * FROM production_sectors WHERE country_code=$1 AND sector_code=$2",
            (code, sector),
        )
        if not sec:
            return f"❌ بخش نامعتبر. بخش‌ها: agriculture, industry, services, energy"
        now = datetime.now(timezone.utc).isoformat()
        new_treas = float(e["treasury"]) - amount
        new_inv = float(sec["investment"]) + amount
        new_out = min(100.0, float(sec["output_level"]) + amount / max(float(e["gdp"]) * 0.001, 1) * 0.5)
        new_gdp = float(e["gdp"]) * (1 + amount / max(float(e["gdp"]), 1) * 0.02)
        await self.db.execute(
            "UPDATE country_economy SET treasury=$1, gdp=$2, updated_at=$3 WHERE country_code=$4",
            (new_treas, new_gdp, now, code),
        )
        await self.db.execute(
            "UPDATE production_sectors SET investment=$1, output_level=$2 WHERE country_code=$3 AND sector_code=$4",
            (new_inv, new_out, code, sector),
        )
        await self.events.record(
            "invest_sector",
            summary=f"{code} invest {amount} in {sector}",
            actor_player_id=player_id,
            country_code=code,
            payload={"sector": sector, "amount": amount},
        )
        return f"✅ سرمایه‌گذاری {amount:,.0f} در {sector} | خزانه {new_treas:,.0f} | تولید {new_out:.1f}"

    async def appoint_minister(
        self, country_code: str, portfolio: str, name: str, player_id: int | None = None
    ) -> str:
        code = country_code.upper()
        portfolio = portfolio.lower().strip()
        if portfolio not in PORTFOLIOS:
            return f"❌ سمت نامعتبر. موارد: {', '.join(PORTFOLIOS)}"
        name = name.strip()[:80]
        if len(name) < 2:
            return "❌ نام وزیر نامعتبر است."
        competence = 45 + (sum(ord(ch) for ch in name) % 40)
        now = datetime.now(timezone.utc).isoformat()
        existing = await self.db.fetchrow(
            "SELECT portfolio FROM cabinet_members WHERE country_code=$1 AND portfolio=$2",
            (code, portfolio),
        )
        if existing:
            await self.db.execute(
                "UPDATE cabinet_members SET minister_name=$1, competence=$2, appointed_at=$3 WHERE country_code=$4 AND portfolio=$5",
                (name, competence, now, code, portfolio),
            )
        else:
            await self.db.execute(
                "INSERT INTO cabinet_members (country_code, portfolio, minister_name, competence, appointed_at) VALUES ($1,$2,$3,$4,$5)",
                (code, portfolio, name, competence, now),
            )
        # competent finance minister slightly improves satisfaction
        if portfolio == "finance":
            e = await self._eco(code)
            sat = min(100, float(e["public_satisfaction"]) + competence * 0.02)
            await self.db.execute(
                "UPDATE country_economy SET public_satisfaction=$1, updated_at=$2 WHERE country_code=$3",
                (sat, now, code),
            )
        await self.events.record(
            "cabinet_appoint",
            summary=f"{code} appoint {name} as {portfolio}",
            actor_player_id=player_id,
            country_code=code,
            payload={"portfolio": portfolio, "name": name, "competence": competence},
        )
        return f"✅ {name} به وزارت {portfolio} منصوب شد (توانایی {competence})."

    async def dismiss_minister(self, country_code: str, portfolio: str, player_id: int | None = None) -> str:
        code = country_code.upper()
        portfolio = portfolio.lower().strip()
        res = await self.db.execute(
            "DELETE FROM cabinet_members WHERE country_code=$1 AND portfolio=$2",
            (code, portfolio),
        )
        await self.events.record(
            "cabinet_dismiss",
            summary=f"{code} dismiss {portfolio}",
            actor_player_id=player_id,
            country_code=code,
            payload={"portfolio": portfolio},
        )
        return f"✅ برکناری {portfolio} انجام شد."

    async def apply_budget_tick(self, country_code: str) -> dict:
        """One economic tick: tax income vs spending, update treasury/satisfaction."""
        code = country_code.upper()
        e = await self._eco(code)
        gdp = float(e["gdp"] or 0)
        tax = float(e["tax_rate"] or 0)
        spend = float(e["public_spending_rate"] or 0)
        income = gdp * tax * 0.01  # abstract annualized fraction per tick
        expense = gdp * spend * 0.01
        treasury = float(e["treasury"]) + income - expense
        sat = float(e["public_satisfaction"])
        if expense > income:
            sat = max(0, sat - 0.5)
        else:
            sat = min(100, sat + 0.2)
        stab = float(e["stability"])
        if treasury < 0:
            stab = max(0, stab - 1)
            treasury = treasury * 0.99
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE country_economy SET treasury=$1, public_satisfaction=$2, stability=$3, updated_at=$4 WHERE country_code=$5",
            (treasury, sat, stab, now, code),
        )
        await self.db.execute(
            "UPDATE countries SET treasury=$1, stability=$2, updated_at=$3 WHERE country_code=$4",
            (treasury, stab, now, code),
        )
        return {"treasury": treasury, "income": income, "expense": expense, "satisfaction": sat}

    async def _eco(self, code: str) -> dict:
        row = await self.db.fetchrow(
            "SELECT * FROM country_economy WHERE country_code=$1", (code,)
        )
        if not row:
            await self.ensure_schema()
            row = await self.db.fetchrow(
                "SELECT * FROM country_economy WHERE country_code=$1", (code,)
            )
        assert row
        return row
