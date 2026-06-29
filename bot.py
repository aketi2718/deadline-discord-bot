import os
import discord
import aiosqlite
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "deadlines.db")
JST = timezone(timedelta(hours=9))

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

REMINDER_LABELS = {
    "40320": "4週間前",
    "20160": "2週間前",
    "10080": "1週間前",
    "4320": "3日前",
    "1440": "1日前",
    "180": "3時間前",
}

REMINDER_VALUES_BY_LABEL = {
    label: value for value, label in REMINDER_LABELS.items()
}


def parse_due(text: str) -> datetime:
    text = text.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%m/%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            if "%Y" not in fmt:
                dt = dt.replace(year=datetime.now(JST).year)
            return dt.replace(tzinfo=JST)
        except ValueError:
            pass
    raise ValueError("日時の形式が違います")


def format_dt(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y-%m-%d %H:%M")


async def replace_notifications(db, deadline_id, due_dt, reminder_values):
    await db.execute(
        """
        DELETE FROM deadline_notifications
        WHERE deadline_id = ?
        """,
        (deadline_id,)
    )

    for value in reminder_values:
        minutes = int(value)
        notify_at = due_dt - timedelta(minutes=minutes)

        await db.execute(
            """
            INSERT INTO deadline_notifications
            (deadline_id, label, notify_at)
            VALUES (?, ?, ?)
            """,
            (
                deadline_id,
                REMINDER_LABELS[value],
                notify_at.isoformat(),
            )
        )


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                subject TEXT,
                due_at TEXT NOT NULL,
                memo TEXT,
                done INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS deadline_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deadline_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                notify_at TEXT NOT NULL,
                notified INTEGER DEFAULT 0,
                FOREIGN KEY(deadline_id) REFERENCES deadlines(id)
            )
        """)

        await db.commit()


class DeadlineModal(discord.ui.Modal, title="課題・テストを登録"):
    task_title = discord.ui.TextInput(
        label="課題名・テスト名",
        placeholder="例: 化学レポート",
        max_length=100
    )

    due = discord.ui.TextInput(
        label="期限",
        placeholder="例: 2026-07-10 23:59",
        max_length=30
    )

    subject = discord.ui.TextInput(
        label="科目",
        placeholder="例: 有機化学",
        required=False,
        max_length=50
    )

    memo = discord.ui.TextInput(
        label="メモ",
        placeholder="例: 実験1の考察まで",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=300
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            due_dt = parse_due(str(self.due))
        except ValueError:
            await interaction.response.send_message(
                "期限は `2026-07-10 23:59` のように入力してください。",
                ephemeral=True
            )
            return

        data = {
            "title": str(self.task_title),
            "due_at": due_dt.isoformat(),
            "subject": str(self.subject),
            "memo": str(self.memo),
        }

        embed = discord.Embed(
            title="通知タイミングを選んでください",
            description="複数選べます。選んだら「確認へ」を押してください。",
            color=discord.Color.blue()
        )
        embed.add_field(name="課題", value=data["title"], inline=False)
        embed.add_field(name="期限", value=format_dt(due_dt), inline=False)

        await interaction.response.send_message(
            embed=embed,
            view=ReminderView(data),
            ephemeral=True
        )


class EditDeadlineModal(discord.ui.Modal, title="課題・テストを編集"):
    task_title = discord.ui.TextInput(
        label="課題名・テスト名",
        placeholder="例: 化学レポート",
        max_length=100
    )

    due = discord.ui.TextInput(
        label="期限",
        placeholder="例: 2026-07-10 23:59",
        max_length=30
    )

    subject = discord.ui.TextInput(
        label="科目",
        placeholder="例: 有機化学",
        required=False,
        max_length=50
    )

    memo = discord.ui.TextInput(
        label="メモ",
        placeholder="例: 実験1の考察まで",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=300
    )

    def __init__(self, deadline_id, title, subject, due_at, memo):
        super().__init__()
        self.deadline_id = deadline_id
        due_dt = datetime.fromisoformat(due_at)
        self.task_title.default = title
        self.due.default = format_dt(due_dt)
        self.subject.default = subject or ""
        self.memo.default = memo or ""

    async def on_submit(self, interaction: discord.Interaction):
        try:
            due_dt = parse_due(str(self.due))
        except ValueError:
            await interaction.response.send_message(
                "期限は `2026-07-10 23:59` のように入力してください。",
                ephemeral=True
            )
            return

        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall(
                """
                SELECT label
                FROM deadline_notifications
                WHERE deadline_id = ?
                """,
                (self.deadline_id,)
            )
            reminder_values = [
                REMINDER_VALUES_BY_LABEL[label]
                for (label,) in rows
                if label in REMINDER_VALUES_BY_LABEL
            ]

            cursor = await db.execute(
                """
                UPDATE deadlines
                SET title = ?, subject = ?, due_at = ?, memo = ?
                WHERE id = ? AND guild_id = ? AND done = 0
                """,
                (
                    str(self.task_title),
                    str(self.subject),
                    due_dt.isoformat(),
                    str(self.memo),
                    self.deadline_id,
                    interaction.guild_id,
                )
            )

            if cursor.rowcount == 0:
                await interaction.response.send_message(
                    f"`{self.deadline_id}` は見つからないか、完了済みです。",
                    ephemeral=True
                )
                return

            await replace_notifications(db, self.deadline_id, due_dt, reminder_values)
            await db.commit()

        await interaction.response.send_message(
            f"編集しました: **{str(self.task_title)}** / 期限: `{format_dt(due_dt)}`",
            ephemeral=True
        )


class ReminderView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=300)
        self.data = data
        self.selected = []

    @discord.ui.select(
        placeholder="通知タイミングを選ぶ",
        min_values=1,
        max_values=6,
        options=[
            discord.SelectOption(label=REMINDER_LABELS["40320"], value="40320"),
            discord.SelectOption(label=REMINDER_LABELS["20160"], value="20160"),
            discord.SelectOption(label=REMINDER_LABELS["10080"], value="10080"),
            discord.SelectOption(label=REMINDER_LABELS["4320"], value="4320"),
            discord.SelectOption(label=REMINDER_LABELS["1440"], value="1440"),
            discord.SelectOption(label=REMINDER_LABELS["180"], value="180"),
        ]
    )
    async def select_reminders(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected = select.values
        labels = [option.label for option in select.options if option.value in self.selected]
        await interaction.response.send_message(
            "選択中: " + "、".join(labels),
            ephemeral=True
        )

    @discord.ui.button(label="確認へ", style=discord.ButtonStyle.primary)
    async def confirm_step(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected:
            await interaction.response.send_message(
                "通知タイミングを1つ以上選んでください。",
                ephemeral=True
            )
            return

        due_dt = datetime.fromisoformat(self.data["due_at"])
        selected_labels = [REMINDER_LABELS[value] for value in self.selected]

        embed = discord.Embed(
            title="この内容で登録しますか？",
            color=discord.Color.green()
        )
        embed.add_field(name="課題", value=self.data["title"], inline=False)
        embed.add_field(name="科目", value=self.data["subject"] or "未設定", inline=False)
        embed.add_field(name="期限", value=format_dt(due_dt), inline=False)
        embed.add_field(name="通知", value="、".join(selected_labels), inline=False)
        embed.add_field(name="メモ", value=self.data["memo"] or "なし", inline=False)

        self.data["reminders"] = self.selected

        await interaction.response.send_message(
            embed=embed,
            view=FinalConfirmView(self.data),
            ephemeral=True
        )


class FinalConfirmView(discord.ui.View):
    def __init__(self, data):
        super().__init__(timeout=300)
        self.data = data

    @discord.ui.button(label="登録する", style=discord.ButtonStyle.success)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        due_dt = datetime.fromisoformat(self.data["due_at"])

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                INSERT INTO deadlines
                (guild_id, channel_id, user_id, title, subject, due_at, memo)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    self.data["title"],
                    self.data["subject"],
                    due_dt.isoformat(),
                    self.data["memo"],
                )
            )

            deadline_id = cursor.lastrowid

            await replace_notifications(db, deadline_id, due_dt, self.data["reminders"])
            await db.commit()

        selected_labels = [REMINDER_LABELS[value] for value in self.data["reminders"]]
        registered_embed = discord.Embed(
            title="課題・テストが登録されました",
            color=discord.Color.green()
        )
        registered_embed.add_field(name="課題", value=self.data["title"], inline=False)
        registered_embed.add_field(name="科目", value=self.data["subject"] or "未設定", inline=False)
        registered_embed.add_field(name="期限", value=format_dt(due_dt), inline=False)
        registered_embed.add_field(name="通知", value="、".join(selected_labels), inline=False)
        registered_embed.add_field(name="登録者", value=interaction.user.mention, inline=False)
        if self.data["memo"]:
            registered_embed.add_field(name="メモ", value=self.data["memo"], inline=False)

        if interaction.channel:
            await interaction.channel.send(embed=registered_embed)

        await interaction.response.send_message(
            f"登録しました: **{self.data['title']}** / 期限: `{format_dt(due_dt)}`",
            ephemeral=True
        )

    @discord.ui.button(label="キャンセル", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("キャンセルしました。", ephemeral=True)


@tree.command(name="add", description="課題・テストの期限を登録します")
async def add(interaction: discord.Interaction):
    await interaction.response.send_modal(DeadlineModal())


@tree.command(name="list", description="登録されている課題・テストを表示します")
async def list_deadlines(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT id, title, subject, due_at, memo
            FROM deadlines
            WHERE guild_id = ? AND done = 0
            ORDER BY due_at ASC
            """,
            (interaction.guild_id,)
        )

    if not rows:
        await interaction.response.send_message(
            "登録されている課題・テストはありません。",
            ephemeral=True,
        )
        return

    lines = []
    for row_id, title, subject, due_at, memo in rows:
        dt = datetime.fromisoformat(due_at)
        subject_text = f" / {subject}" if subject else ""
        lines.append(f"`{row_id}` **{title}**{subject_text} - {format_dt(dt)}")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@tree.command(name="edit", description="課題・テストの内容を編集します")
async def edit(interaction: discord.Interaction, id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            SELECT title, subject, due_at, memo
            FROM deadlines
            WHERE id = ? AND guild_id = ? AND done = 0
            """,
            (id, interaction.guild_id)
        )
        row = await cursor.fetchone()

    if row is None:
        await interaction.response.send_message(
            f"`{id}` は見つからないか、完了済みです。",
            ephemeral=True
        )
        return

    await interaction.response.send_modal(EditDeadlineModal(id, *row))


@tree.command(name="done", description="課題・テストを完了にします")
async def done(interaction: discord.Interaction, id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE deadlines
            SET done = 1
            WHERE id = ? AND guild_id = ?
            """,
            (id, interaction.guild_id)
        )
        await db.commit()

    await interaction.response.send_message(f"`{id}` を完了にしました。")


@tree.command(name="delete", description="課題・テストを削除します")
async def delete(interaction: discord.Interaction, id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            DELETE FROM deadline_notifications
            WHERE deadline_id = ?
            """,
            (id,)
        )

        await db.execute(
            """
            DELETE FROM deadlines
            WHERE id = ? AND guild_id = ?
            """,
            (id, interaction.guild_id)
        )

        await db.commit()

    await interaction.response.send_message(f"`{id}` を削除しました。")


@tasks.loop(minutes=1)
async def check_notifications():
    now = datetime.now(JST)

    async with aiosqlite.connect(DB_PATH) as db:
        rows = await db.execute_fetchall(
            """
            SELECT
                deadline_notifications.id,
                deadlines.channel_id,
                deadlines.title,
                deadlines.subject,
                deadlines.due_at,
                deadlines.memo,
                deadline_notifications.label
            FROM deadline_notifications
            JOIN deadlines ON deadline_notifications.deadline_id = deadlines.id
            WHERE deadline_notifications.notified = 0
              AND deadlines.done = 0
              AND deadline_notifications.notify_at <= ?
            """,
            (now.isoformat(),)
        )

        for notification_id, channel_id, title, subject, due_at, memo, label in rows:
            channel = client.get_channel(channel_id)
            due_dt = datetime.fromisoformat(due_at)

            if channel:
                embed = discord.Embed(
                    title="期限が近いです",
                    color=discord.Color.orange()
                )
                embed.add_field(name="課題", value=title, inline=False)
                embed.add_field(name="科目", value=subject or "未設定", inline=False)
                embed.add_field(name="期限", value=format_dt(due_dt), inline=False)
                embed.add_field(name="通知", value=label, inline=False)
                if memo:
                    embed.add_field(name="メモ", value=memo, inline=False)

                await channel.send(embed=embed)

            await db.execute(
                """
                UPDATE deadline_notifications
                SET notified = 1
                WHERE id = ?
                """,
                (notification_id,)
            )

        await db.commit()


@client.event
async def on_ready():
    await init_db()
    await tree.sync()

    if not check_notifications.is_running():
        check_notifications.start()

    print(f"{client.user} としてログインしました")


if not TOKEN:
    raise RuntimeError(".env に DISCORD_TOKEN を設定してください")

client.run(TOKEN)
