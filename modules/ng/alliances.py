"""Alliance System 2.0 — create, join, treasury, betrayal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from zoneinfo import ZoneInfo

TEHRAN = ZoneInfo("Asia/Tehran")

if TYPE_CHECKING:
    from modules.ng.game import Game

BASE_CREATE_COST = 4_000_000
COST_PER_EXTRA_MEMBER = 700_000  # beyond 2
COST_PER_100M_TREASURY = 1_200_000  # beyond 100M base included
BASE_MEMBER_SLOTS = 2
BASE_TREASURY_CAP = 100_000_000
MIN_MEMBERS = 2
MAX_MEMBERS = 20
MIN_TREASURY_CAP = 50_000_000
MAX_TREASURY_CAP = 5_000_000_000
RENAME_COST = 5_000_000
BETRAYAL_WINDOW_SEC = 3 * 3600
BETRAYAL_PENALTY_SEC = 6 * 3600
DESTROY_WAIT_SEC = 30 * 60


class AllianceError(Exception):
    pass


MAX_CREATE_COST = 20_000_000


def create_cost(max_members: int, treasury_cap: float) -> int:
    max_members = max(MIN_MEMBERS, min(MAX_MEMBERS, int(max_members)))
    treasury_cap = max(MIN_TREASURY_CAP, min(MAX_TREASURY_CAP, float(treasury_cap)))
    cost = BASE_CREATE_COST
    cost += max(0, max_members - BASE_MEMBER_SLOTS) * COST_PER_EXTRA_MEMBER
    extra_cap = max(0.0, treasury_cap - BASE_TREASURY_CAP)
    cost += int((extra_cap / 100_000_000.0) * COST_PER_100M_TREASURY)
    return int(min(MAX_CREATE_COST, max(BASE_CREATE_COST, cost)))


def expand_member_cost(old: int, new: int) -> int:
    if new <= old:
        return 0
    return max(0, new - old) * COST_PER_EXTRA_MEMBER


def expand_treasury_cost(old: float, new: float) -> int:
    if new <= old:
        return 0
    return int(((new - old) / 100_000_000.0) * COST_PER_100M_TREASURY)


class AllianceService:
    def __init__(self, game: "Game"):
        self.g = game
        self.db = game.db

    async def member_of(self, country: str) -> dict | None:
        return await self.db.fetchrow(
            "SELECT m.*, a.name, a.status, a.founder_country, a.max_members, a.treasury, a.treasury_cap "
            "FROM ng_alliance_members m JOIN ng_alliances a ON a.id=m.alliance_id "
            "WHERE m.country_code=$1 AND a.status='active'",
            (country,),
        )

    async def get(self, aid: int) -> dict | None:
        return await self.db.fetchrow("SELECT * FROM ng_alliances WHERE id=$1", (aid,))

    async def members(self, aid: int) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_alliance_members WHERE alliance_id=$1 ORDER BY joined_at",
            (aid,),
        )

    async def list_active(self) -> list[dict]:
        return await self.db.fetch(
            "SELECT * FROM ng_alliances WHERE status='active' ORDER BY id"
        )

    async def create(
        self, pid: int, country: str, name: str, max_members: int, treasury_cap: float
    ) -> str:
        name = (name or "").strip()[:40]
        if len(name) < 3:
            raise AllianceError("نام اتحاد خیلی کوتاه است.")
        max_members = max(MIN_MEMBERS, min(MAX_MEMBERS, int(max_members)))
        treasury_cap = max(MIN_TREASURY_CAP, min(MAX_TREASURY_CAP, float(treasury_cap)))
        if await self.member_of(country):
            raise AllianceError("شما هم‌اکنون عضو یک اتحاد هستید.")
        cost = create_cost(max_members, treasury_cap)
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (country, pid),
        )
        if not c:
            raise AllianceError("کشور یافت نشد")
        if float(c["treasury"]) < cost:
            raise AllianceError(f"پول کافی نیست. نیاز: {cost:,}")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            if await tx.fetchrow(
                "SELECT 1 AS x FROM ng_alliance_members WHERE country_code=$1", (country,)
            ):
                raise AllianceError("عضو اتحاد دیگر هستید")
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, country),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliances")
            aid = int(nid["id"])
            await tx.execute(
                """
                INSERT INTO ng_alliances
                (id, name, founder_country, founder_player_id, max_members, treasury_cap, treasury, status, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,0,'active',$7)
                """,
                (aid, name, country, pid, max_members, treasury_cap, now),
            )
            await tx.execute(
                """
                INSERT INTO ng_alliance_members (alliance_id, country_code, player_id, role, joined_at)
                VALUES ($1,$2,$3,'founder',$4)
                """,
                (aid, country, pid, now),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                """
                INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at)
                VALUES ($1,$2,'create',$3,$4,$5,$6,$7)
                """,
                (int(tid["id"]), aid, cost, pid, country, f"تأسیس {name}", now),
            )
        await self.g.log_activity("alliance", f"تأسیس اتحاد {name}", country, pid)
        return f"✅ اتحاد «{name}» ساخته شد.\nهزینه: {cost:,}\nظرفیت اعضا: {max_members}\nظرفیت خزانه: {int(treasury_cap):,}"

    async def join(self, pid: int, country: str, aid: int) -> str:
        a = await self.get(aid)
        if not a or a["status"] != "active":
            raise AllianceError("اتحاد فعال نیست")
        if await self.member_of(country):
            raise AllianceError("شما عضو اتحاد دیگری هستید")
        mems = await self.members(aid)
        if len(mems) >= int(a["max_members"]):
            raise AllianceError("ظرفیت اتحاد پر است")
        c = await self.db.fetchrow(
            "SELECT * FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (country, pid),
        )
        if not c:
            raise AllianceError("کشور یافت نشد")
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            """
            INSERT INTO ng_alliance_members (alliance_id, country_code, player_id, role, joined_at)
            VALUES ($1,$2,$3,'member',$4)
            """,
            (aid, country, pid, now),
        )
        await self.g.log_activity("alliance", f"عضویت در {a['name']}", country, pid)
        return f"✅ به اتحاد «{a['name']}» پیوستید."

    async def leave(self, pid: int, country: str) -> str:
        m = await self.member_of(country)
        if not m:
            raise AllianceError("عضو هیچ اتحادی نیستید")
        if m["role"] == "founder":
            raise AllianceError("بنیان‌گذار نمی‌تواند خارج شود. ابتدا اتحاد را منحل کنید یا مالکیت را واگذار کنید.")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "DELETE FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
                (m["alliance_id"], country),
            )
            nid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_exits")
            await tx.execute(
                """
                INSERT INTO ng_alliance_exits (id, alliance_id, country_code, player_id, exited_at, member_snapshot)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                (int(nid["id"]), m["alliance_id"], country, pid, now, m.get("name") or ""),
            )
            # player flags
            fl = await tx.fetchrow("SELECT player_id FROM ng_player_flags WHERE player_id=$1", (pid,))
            if fl:
                await tx.execute(
                    "UPDATE ng_player_flags SET last_alliance_exit_at=$1, last_exit_alliance_id=$2 WHERE player_id=$3",
                    (now, m["alliance_id"], pid),
                )
            else:
                await tx.execute(
                    "INSERT INTO ng_player_flags (player_id, last_alliance_exit_at, last_exit_alliance_id) VALUES ($1,$2,$3)",
                    (pid, now, m["alliance_id"]),
                )
        return f"✅ از اتحاد «{m.get('name')}» خارج شدید."

    async def kick(self, founder_pid: int, target_country: str) -> str:
        m_f = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m_f:
            raise AllianceError("فقط بنیان‌گذار")
        if target_country == m_f["country_code"]:
            raise AllianceError("نمی‌توانید خود را اخراج کنید")
        t = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
            (m_f["alliance_id"], target_country),
        )
        if not t:
            raise AllianceError("عضو نیست")
        await self.db.execute(
            "DELETE FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
            (m_f["alliance_id"], target_country),
        )
        return f"✅ کشور {target_country} اخراج شد."

    async def deposit(self, pid: int, country: str, amount: float) -> str:
        amount = float(amount)
        if amount <= 0:
            raise AllianceError("مبلغ نامعتبر")
        m = await self.member_of(country)
        if not m:
            raise AllianceError("عضو اتحاد نیستید")
        a = await self.get(m["alliance_id"])
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1 AND owner_player_id=$2",
            (country, pid),
        )
        if not c or float(c["treasury"]) < amount:
            raise AllianceError("پول کافی نیست")
        if float(a["treasury"]) + amount > float(a["treasury_cap"]) + 1e-6:
            raise AllianceError("ظرفیت خزانه اتحاد پر است")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - amount, country),
            )
            await tx.execute(
                "UPDATE ng_alliances SET treasury=$1 WHERE id=$2",
                (float(a["treasury"]) + amount, a["id"]),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'deposit',$3,$4,$5,'واریز',$6)",
                (int(tid["id"]), a["id"], amount, pid, country, now),
            )
        return f"✅ {int(amount):,} به خزانه اتحاد واریز شد."

    async def withdraw(self, founder_pid: int, amount: float) -> str:
        amount = float(amount)
        if amount <= 0:
            raise AllianceError("مبلغ نامعتبر")
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        a = await self.get(m["alliance_id"])
        if float(a["treasury"]) < amount:
            raise AllianceError("خزانه کافی نیست")
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (m["country_code"],)
        )
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_alliances SET treasury=$1 WHERE id=$2",
                (float(a["treasury"]) - amount, a["id"]),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) + amount, m["country_code"]),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'withdraw',$3,$4,$5,'برداشت',$6)",
                (int(tid["id"]), a["id"], amount, founder_pid, m["country_code"], now),
            )
        return f"✅ {int(amount):,} از خزانه برداشت شد."

    async def pay_member(self, founder_pid: int, target_country: str, amount: float) -> str:
        amount = float(amount)
        if amount <= 0:
            raise AllianceError("مبلغ نامعتبر")
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        t = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
            (m["alliance_id"], target_country),
        )
        if not t:
            raise AllianceError("عضو نیست")
        a = await self.get(m["alliance_id"])
        if float(a["treasury"]) < amount:
            raise AllianceError("خزانه کافی نیست")
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (target_country,)
        )
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_alliances SET treasury=$1 WHERE id=$2",
                (float(a["treasury"]) - amount, a["id"]),
            )
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) + amount, target_country),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'pay_member',$3,$4,$5,'پرداخت به عضو',$6)",
                (int(tid["id"]), a["id"], amount, founder_pid, target_country, now),
            )
        return f"✅ {int(amount):,} به {target_country} پرداخت شد."

    async def equal_split(self, founder_pid: int) -> str:
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        a = await self.get(m["alliance_id"])
        mems = await self.members(m["alliance_id"])
        if not mems:
            raise AllianceError("عضوی نیست")
        total = float(a["treasury"])
        if total <= 0:
            raise AllianceError("خزانه خالی است")
        each = int(total // len(mems))
        if each <= 0:
            raise AllianceError("مبلغ برای تقسیم کافی نیست")
        used = each * len(mems)
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            for mem in mems:
                c = await tx.fetchrow(
                    "SELECT treasury FROM ng_countries WHERE country_code=$1",
                    (mem["country_code"],),
                )
                await tx.execute(
                    "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                    (float(c["treasury"]) + each, mem["country_code"]),
                )
            await tx.execute(
                "UPDATE ng_alliances SET treasury=$1 WHERE id=$2",
                (total - used, a["id"]),
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'equal_split',$3,$4,$5,$6,$7)",
                (int(tid["id"]), a["id"], used, founder_pid, m["country_code"], f"هر نفر {each}", now),
            )
        return f"✅ تقسیم مساوی: هر عضو {each:,} | باقی خزانه: {int(total-used):,}"

    async def rename(self, founder_pid: int, new_name: str) -> str:
        new_name = (new_name or "").strip()[:40]
        if len(new_name) < 3:
            raise AllianceError("نام کوتاه است")
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (m["country_code"],)
        )
        if float(c["treasury"]) < RENAME_COST:
            raise AllianceError(f"هزینه تغییر نام {RENAME_COST:,}")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - RENAME_COST, m["country_code"]),
            )
            await tx.execute(
                "UPDATE ng_alliances SET name=$1 WHERE id=$2", (new_name, m["alliance_id"])
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'rename',$3,$4,$5,$6,$7)",
                (int(tid["id"]), m["alliance_id"], RENAME_COST, founder_pid, m["country_code"], new_name, now),
            )
        return f"✅ نام اتحاد به «{new_name}» تغییر کرد."

    async def expand_members(self, founder_pid: int, new_max: int) -> str:
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        a = await self.get(m["alliance_id"])
        new_max = max(int(a["max_members"]) + 1, min(MAX_MEMBERS, int(new_max)))
        cost = expand_member_cost(int(a["max_members"]), new_max)
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (m["country_code"],)
        )
        if float(c["treasury"]) < cost:
            raise AllianceError(f"هزینه: {cost:,}")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, m["country_code"]),
            )
            await tx.execute(
                "UPDATE ng_alliances SET max_members=$1 WHERE id=$2", (new_max, a["id"])
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'expand_members',$3,$4,$5,$6,$7)",
                (int(tid["id"]), a["id"], cost, founder_pid, m["country_code"], str(new_max), now),
            )
        return f"✅ ظرفیت اعضا: {new_max} | هزینه: {cost:,}"

    async def expand_treasury(self, founder_pid: int, new_cap: float) -> str:
        m = await self.db.fetchrow(
            "SELECT * FROM ng_alliance_members WHERE player_id=$1 AND role='founder'",
            (founder_pid,),
        )
        if not m:
            raise AllianceError("فقط بنیان‌گذار")
        a = await self.get(m["alliance_id"])
        new_cap = float(new_cap)
        if new_cap < float(a["treasury"]):
            raise AllianceError("ظرفیت نمی‌تواند از موجودی فعلی کمتر باشد")
        if new_cap <= float(a["treasury_cap"]):
            raise AllianceError("ظرفیت باید بیشتر از فعلی باشد")
        cost = expand_treasury_cost(float(a["treasury_cap"]), new_cap)
        c = await self.db.fetchrow(
            "SELECT treasury FROM ng_countries WHERE country_code=$1", (m["country_code"],)
        )
        if float(c["treasury"]) < cost:
            raise AllianceError(f"هزینه: {cost:,}")
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            await tx.execute(
                "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                (float(c["treasury"]) - cost, m["country_code"]),
            )
            await tx.execute(
                "UPDATE ng_alliances SET treasury_cap=$1 WHERE id=$2", (new_cap, a["id"])
            )
            tid = await tx.fetchrow("SELECT COALESCE(MAX(id),0)+1 AS id FROM ng_alliance_tx")
            await tx.execute(
                "INSERT INTO ng_alliance_tx (id, alliance_id, kind, amount, actor_player_id, country_code, note, created_at) VALUES ($1,$2,'expand_treasury',$3,$4,$5,$6,$7)",
                (int(tid["id"]), a["id"], cost, founder_pid, m["country_code"], str(int(new_cap)), now),
            )
        return f"✅ ظرفیت خزانه: {int(new_cap):,} | هزینه: {cost:,}"

    async def dissolve(self, actor: int, aid: int, is_owner: bool = False) -> str:
        a = await self.get(aid)
        if not a or a["status"] != "active":
            raise AllianceError("اتحاد فعال نیست")
        if not is_owner:
            m = await self.db.fetchrow(
                "SELECT * FROM ng_alliance_members WHERE alliance_id=$1 AND player_id=$2 AND role='founder'",
                (aid, actor),
            )
            if not m:
                raise AllianceError("فقط بنیان‌گذار یا مالک بازی")
        # return treasury to founder country
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.transaction() as tx:
            if float(a["treasury"]) > 0:
                c = await tx.fetchrow(
                    "SELECT treasury FROM ng_countries WHERE country_code=$1",
                    (a["founder_country"],),
                )
                if c:
                    await tx.execute(
                        "UPDATE ng_countries SET treasury=$1 WHERE country_code=$2",
                        (float(c["treasury"]) + float(a["treasury"]), a["founder_country"]),
                    )
            await tx.execute(
                "UPDATE ng_alliances SET status='dissolved', treasury=0, dissolved_at=$1 WHERE id=$2",
                (now, aid),
            )
            await tx.execute(
                "DELETE FROM ng_alliance_members WHERE alliance_id=$1", (aid,)
            )
        return f"✅ اتحاد «{a['name']}» منحل شد. موجودی خزانه به بنیان‌گذار برگشت."

    async def on_country_destroyed(self, country: str) -> None:
        m = await self.member_of(country)
        if not m:
            return
        if m["role"] == "founder":
            await self.dissolve(int(m["player_id"]), int(m["alliance_id"]), is_owner=False)
        else:
            await self.db.execute(
                "DELETE FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
                (m["alliance_id"], country),
            )

    async def check_betrayal_on_attack(self, attacker_pid: int, attacker_code: str, defender_code: str) -> str | None:
        fl = await self.db.fetchrow(
            "SELECT * FROM ng_player_flags WHERE player_id=$1", (attacker_pid,)
        )
        if not fl or not fl.get("last_alliance_exit_at") or not fl.get("last_exit_alliance_id"):
            return None
        try:
            exited = datetime.fromisoformat(str(fl["last_alliance_exit_at"]).replace("Z", "+00:00"))
            if exited.tzinfo is None:
                exited = exited.replace(tzinfo=timezone.utc)
        except Exception:
            return None
        now = datetime.now(timezone.utc)
        if (now - exited).total_seconds() > BETRAYAL_WINDOW_SEC:
            return None
        # was defender in that alliance at exit time? check current or exit snapshot members
        still = await self.db.fetchrow(
            "SELECT 1 AS x FROM ng_alliance_members WHERE alliance_id=$1 AND country_code=$2",
            (int(fl["last_exit_alliance_id"]), defender_code),
        )
        # also if alliance dissolved, still punish if attack within window against former ally listed in members was deleted — use exits only
        if not still:
            # check if defender was in same alliance via any exit/membership history - simple: if defender still member OK; if not, check alliance members history not available — treat any attack on anyone who is/was in alliance id via remaining members
            return None
        until = (now + timedelta(seconds=BETRAYAL_PENALTY_SEC)).isoformat()
        if fl:
            await self.db.execute(
                "UPDATE ng_player_flags SET shop_penalty_until=$1 WHERE player_id=$2",
                (until, attacker_pid),
            )
        else:
            await self.db.execute(
                "INSERT INTO ng_player_flags (player_id, shop_penalty_until) VALUES ($1,$2)",
                (attacker_pid, until),
            )
        return (
            "⚠️ خیانت به اتحاد\n\n"
            "شما پس از خروج از اتحاد قبلی به یکی از اعضای آن حمله کردید.\n"
            "قیمت تمام تجهیزات فروشگاه برای شما به مدت ۶ ساعت دو برابر شده است."
        )

    async def shop_mult_for_player(self, pid: int) -> float:
        fl = await self.db.fetchrow(
            "SELECT shop_penalty_until FROM ng_player_flags WHERE player_id=$1", (pid,)
        )
        if not fl or not fl.get("shop_penalty_until"):
            return 1.0
        try:
            until = datetime.fromisoformat(str(fl["shop_penalty_until"]).replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < until:
                return 2.0
        except Exception:
            return 1.0
        return 1.0

    def card_text(self, a: dict, mems: list[dict], labels: dict[str, str]) -> str:
        founder = labels.get(a["founder_country"], a["founder_country"])
        lines = [
            f"🤝 {a['name']}",
            f"بنیان‌گذار: {founder}",
            f"اعضا: {len(mems)}/{a['max_members']}",
            f"خزانه: {int(float(a['treasury'])):,} / {int(float(a['treasury_cap'])):,}",
            "",
            "اعضا:",
        ]
        for m in mems:
            role = "👑" if m["role"] == "founder" else "•"
            lines.append(f"{role} {labels.get(m['country_code'], m['country_code'])}")
        return "\n".join(lines)
