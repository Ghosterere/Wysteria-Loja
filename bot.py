import io
import os
import re
import sqlite3
import unicodedata
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional
import json

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger("lojadc.bot")


def parse_optional_env_id(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    normalized = value.strip()
    if not normalized.isdigit():
        raise RuntimeError(f"Variavel {name} precisa ser um ID numerico do Discord. Valor recebido: {normalized!r}.")
    return int(normalized)


DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "lojas.db"))
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = parse_optional_env_id("GUILD_ID")
TICKET_CATEGORY_ID = parse_optional_env_id("TICKET_CATEGORY_ID")
TICKET_ARCHIVE_CATEGORY_ID = parse_optional_env_id("TICKET_ARCHIVE_CATEGORY_ID")
FEEDBACK_CHANNEL_ID = parse_optional_env_id("FEEDBACK_CHANNEL_ID")
SERVICE_DESK_CHANNEL_ID = parse_optional_env_id("SERVICE_DESK_CHANNEL_ID")
TICKET_LOG_CHANNEL_ID = parse_optional_env_id("TICKET_LOG_CHANNEL_ID")
BOOST_THANK_CHANNEL_ID = parse_optional_env_id("BOOST_THANK_CHANNEL_ID")
SELLER_APPLICATION_CHANNEL_ID = parse_optional_env_id("SELLER_APPLICATION_CHANNEL_ID")
ADMIN_TESTER_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_TESTER_IDS", "").split(",")
    if value.strip().isdigit()
}
LOJISTA_ROLE_NAME = os.getenv("LOJISTA_ROLE_NAME", "Lojista").strip() or "Lojista"
SHOP_AVAILABILITY_META = {
    "disponivel": {"label": "Disponivel", "emoji": "🟢"},
    "ocupado": {"label": "Ocupado", "emoji": "🟠"},
    "ausente": {"label": "Ausente", "emoji": "🟡"},
    "fechado": {"label": "Fechado", "emoji": "🔴"},
}


EMBED_COLORS = {
    "panel": discord.Color.from_rgb(20, 24, 33),
    "primary": discord.Color.from_rgb(88, 166, 255),
    "success": discord.Color.from_rgb(63, 185, 80),
    "warning": discord.Color.from_rgb(210, 153, 34),
    "danger": discord.Color.from_rgb(248, 81, 73),
}

ORDER_STATUS_META = {
    "pendente": {"label": "Pendente", "emoji": "🟡", "color": EMBED_COLORS["warning"]},
    "em_andamento": {"label": "Em andamento", "emoji": "🔵", "color": EMBED_COLORS["primary"]},
    "concluido": {"label": "Concluido", "emoji": "🟢", "color": EMBED_COLORS["success"]},
    "fechado": {"label": "Fechado", "emoji": "⚫", "color": EMBED_COLORS["danger"]},
}

THEME_PRESETS = {
    "booster": {
        "label": "Booster",
        "color": "#5865F2",
        "emoji": "🚀",
        "headline": "Visual premium para quem quer destaque",
        "subtitle": "Tema vibrante com cara de produto especial.",
    },
    "dark_red": {
        "label": "Dark Red",
        "color": "#7A1E2C",
        "emoji": "🌹",
        "headline": "Estilo intenso e sofisticado",
        "subtitle": "Perfeito para vitrines mais fortes e dramáticas.",
    },
    "gold": {
        "label": "Gold",
        "color": "#D4A017",
        "emoji": "👑",
        "headline": "Acabamento de vitrine premium",
        "subtitle": "Um visual dourado para transmitir valor e exclusividade.",
    },
    "neon_blue": {
        "label": "Neon Blue",
        "color": "#00C8FF",
        "emoji": "⚡",
        "headline": "Energia visual e brilho moderno",
        "subtitle": "Ideal para lojas com pegada tech, booster ou gaming.",
    },
}


@dataclass
class Shop:
    db_id: int
    id: int
    guild_id: int
    owner_id: int
    name: str
    description: str
    shop_emoji: Optional[str]
    theme_name: Optional[str]
    buy_button_text: Optional[str]
    headline: Optional[str]
    subtitle: Optional[str]
    highlights: Optional[str]
    terms_text: Optional[str]
    is_open: bool
    availability_status: str
    accent_color: Optional[str]
    image_url: Optional[str]
    banner_url: Optional[str]


class StoreDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._setup()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_column(self, db: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
        columns = db.execute(f"PRAGMA table_info({table_name})").fetchall()
        names = {str(column["name"]) for column in columns}
        if column_name not in names:
            db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    def _next_shop_public_id(self, db: sqlite3.Connection, guild_id: int) -> int:
        row = db.execute("SELECT COALESCE(MAX(public_id), 0) + 1 AS next_id FROM shops WHERE guild_id = ?", (guild_id,)).fetchone()
        return int(row["next_id"])

    def _next_order_public_id(self, db: sqlite3.Connection, guild_id: int) -> int:
        row = db.execute("SELECT COALESCE(MAX(public_id), 0) + 1 AS next_id FROM orders WHERE guild_id = ?", (guild_id,)).fetchone()
        return int(row["next_id"])

    def _resequence_shop_public_ids(self, db: sqlite3.Connection) -> None:
        guild_rows = db.execute("SELECT DISTINCT guild_id FROM shops ORDER BY guild_id").fetchall()
        for guild_row in guild_rows:
            guild_id = int(guild_row["guild_id"])
            rows = db.execute(
                "SELECT id FROM shops WHERE guild_id = ? ORDER BY created_at, id",
                (guild_id,),
            ).fetchall()
            for index, row in enumerate(rows, start=1):
                db.execute("UPDATE shops SET public_id = ? WHERE id = ?", (index, int(row["id"])))

    def _resequence_order_public_ids(self, db: sqlite3.Connection) -> None:
        guild_rows = db.execute("SELECT DISTINCT guild_id FROM orders ORDER BY guild_id").fetchall()
        for guild_row in guild_rows:
            guild_id = int(guild_row["guild_id"])
            rows = db.execute(
                "SELECT id FROM orders WHERE guild_id = ? ORDER BY created_at, id",
                (guild_id,),
            ).fetchall()
            for index, row in enumerate(rows, start=1):
                db.execute("UPDATE orders SET public_id = ? WHERE id = ?", (index, int(row["id"])))

    def _foreign_key_delete_action(self, db: sqlite3.Connection, table_name: str, from_column: str) -> Optional[str]:
        rows = db.execute(f"PRAGMA foreign_key_list({table_name})").fetchall()
        for row in rows:
            if str(row["from"]) == from_column:
                return str(row["on_delete"]).upper()
        return None

    def _migrate_order_history_tables(self, db: sqlite3.Connection) -> None:
        order_product_action = self._foreign_key_delete_action(db, "orders", "product_id")
        order_shop_action = self._foreign_key_delete_action(db, "orders", "shop_id")
        order_item_product_action = self._foreign_key_delete_action(db, "order_items", "product_id")
        if (
            order_product_action == "SET NULL"
            and order_shop_action in {"NO ACTION", "RESTRICT"}
            and order_item_product_action == "SET NULL"
        ):
            return

        db.commit()
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("DROP TABLE IF EXISTS order_items_new")
            db.execute("DROP TABLE IF EXISTS orders_new")
            db.execute(
                """
                CREATE TABLE orders_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    public_id INTEGER,
                    shop_id INTEGER NOT NULL,
                    product_id INTEGER,
                    buyer_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    total_price_cents INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    assigned_editor_id INTEGER,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    ticket_channel_id INTEGER,
                    service_message_id INTEGER,
                    service_kind TEXT NOT NULL DEFAULT 'channel',
                    transcript_text TEXT,
                    accepted_terms_text TEXT,
                    accepted_terms_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE RESTRICT,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
                )
                """
            )
            db.execute(
                """
                INSERT INTO orders_new (
                    id, guild_id, public_id, shop_id, product_id, buyer_id, quantity, details, total_price_cents,
                    status, assigned_editor_id, started_at, completed_at, closed_at, ticket_channel_id,
                    service_message_id, service_kind, transcript_text, accepted_terms_text, accepted_terms_at, created_at
                )
                SELECT
                    id, guild_id, public_id, shop_id, product_id, buyer_id, quantity, details, total_price_cents,
                    status, assigned_editor_id, started_at, completed_at, closed_at, ticket_channel_id,
                    service_message_id, service_kind, transcript_text, accepted_terms_text, accepted_terms_at, created_at
                FROM orders
                """
            )
            db.execute(
                """
                CREATE TABLE order_items_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    unit_price_cents INTEGER NOT NULL,
                    line_total_cents INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders_new(id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
                )
                """
            )
            db.execute(
                """
                INSERT INTO order_items_new (id, order_id, product_id, quantity, unit_price_cents, line_total_cents, created_at)
                SELECT id, order_id, product_id, quantity, unit_price_cents, line_total_cents, created_at
                FROM order_items
                """
            )
            db.execute("DROP TABLE order_items")
            db.execute("DROP TABLE orders")
            db.execute("ALTER TABLE orders_new RENAME TO orders")
            db.execute("ALTER TABLE order_items_new RENAME TO order_items")
            db.commit()
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    def _setup(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS shops (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    public_id INTEGER,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    shop_emoji TEXT,
                    theme_name TEXT,
                    buy_button_text TEXT,
                    headline TEXT,
                    subtitle TEXT,
                    highlights TEXT,
                    terms_text TEXT,
                    is_open INTEGER NOT NULL DEFAULT 1,
                    availability_status TEXT NOT NULL DEFAULT 'disponivel',
                    accent_color TEXT,
                    image_url TEXT,
                    banner_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, owner_id, name)
                )
                """
            )
            self._ensure_column(db, "shops", "public_id", "INTEGER")
            self._ensure_column(db, "shops", "shop_emoji", "TEXT")
            self._ensure_column(db, "shops", "theme_name", "TEXT")
            self._ensure_column(db, "shops", "buy_button_text", "TEXT")
            self._ensure_column(db, "shops", "headline", "TEXT")
            self._ensure_column(db, "shops", "subtitle", "TEXT")
            self._ensure_column(db, "shops", "highlights", "TEXT")
            self._ensure_column(db, "shops", "terms_text", "TEXT")
            self._ensure_column(db, "shops", "is_open", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(db, "shops", "availability_status", "TEXT NOT NULL DEFAULT 'disponivel'")
            self._ensure_column(db, "shops", "accent_color", "TEXT")
            self._ensure_column(db, "shops", "image_url", "TEXT")
            self._ensure_column(db, "shops", "banner_url", "TEXT")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'Geral',
                    price_cents INTEGER NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
                    UNIQUE (shop_id, name)
                )
                """
            )
            self._ensure_column(db, "products", "category", "TEXT NOT NULL DEFAULT 'Geral'")
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    public_id INTEGER,
                    shop_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    buyer_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    total_price_cents INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente',
                    assigned_editor_id INTEGER,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    closed_at TIMESTAMP,
                    ticket_channel_id INTEGER,
                    service_message_id INTEGER,
                    service_kind TEXT NOT NULL DEFAULT 'channel',
                    transcript_text TEXT,
                    accepted_terms_text TEXT,
                    accepted_terms_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_column(db, "orders", "public_id", "INTEGER")
            self._ensure_column(db, "orders", "status", "TEXT NOT NULL DEFAULT 'pendente'")
            self._ensure_column(db, "orders", "assigned_editor_id", "INTEGER")
            self._ensure_column(db, "orders", "started_at", "TIMESTAMP")
            self._ensure_column(db, "orders", "completed_at", "TIMESTAMP")
            self._ensure_column(db, "orders", "closed_at", "TIMESTAMP")
            self._ensure_column(db, "orders", "ticket_channel_id", "INTEGER")
            self._ensure_column(db, "orders", "service_message_id", "INTEGER")
            self._ensure_column(db, "orders", "service_kind", "TEXT NOT NULL DEFAULT 'channel'")
            self._ensure_column(db, "orders", "transcript_text", "TEXT")
            self._ensure_column(db, "orders", "accepted_terms_text", "TEXT")
            self._ensure_column(db, "orders", "accepted_terms_at", "TIMESTAMP")
            db.execute(
                """
                UPDATE orders
                SET assigned_editor_id = COALESCE(assigned_editor_id, (SELECT owner_id FROM shops WHERE shops.id = orders.shop_id))
                WHERE assigned_editor_id IS NULL
                """
            )
            db.execute(
                """
                UPDATE orders
                SET started_at = COALESCE(started_at, created_at)
                WHERE status = 'em_andamento' AND started_at IS NULL
                """
            )
            db.execute(
                """
                UPDATE orders
                SET completed_at = COALESCE(completed_at, created_at)
                WHERE status IN ('concluido', 'fechado') AND completed_at IS NULL
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL UNIQUE,
                    guild_id INTEGER NOT NULL,
                    shop_id INTEGER NOT NULL,
                    buyer_id INTEGER NOT NULL,
                    seller_id INTEGER NOT NULL,
                    stars INTEGER NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS term_acceptances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    shop_id INTEGER NOT NULL,
                    buyer_id INTEGER NOT NULL,
                    terms_text TEXT NOT NULL,
                    accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (guild_id, shop_id, buyer_id, terms_text)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS order_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    unit_price_cents INTEGER NOT NULL,
                    line_total_cents INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS order_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    actor_id INTEGER,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS seller_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    applicant_id INTEGER NOT NULL,
                    portfolio_text TEXT NOT NULL DEFAULT '',
                    specialty_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pendente',
                    admin_id INTEGER,
                    review_note TEXT NOT NULL DEFAULT '',
                    message_channel_id INTEGER,
                    message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP,
                    UNIQUE (guild_id, applicant_id, status)
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS shop_publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    shop_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (shop_id, channel_id),
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS boost_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    thanked_message_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            self._migrate_order_history_tables(db)
            db.execute("CREATE INDEX IF NOT EXISTS idx_orders_guild_buyer_id ON orders(guild_id, buyer_id, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_orders_shop_status_id ON orders(shop_id, status, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_orders_guild_status_id ON orders(guild_id, status, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_products_shop_active_category_name ON products(shop_id, active, category, name)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_shops_guild_owner_id ON shops(guild_id, owner_id, id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ratings_shop_id_desc ON ratings(shop_id, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ratings_seller_id_desc ON ratings(seller_id, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_order_logs_order_id_desc ON order_logs(order_id, id DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_shop_publications_shop_id ON shop_publications(shop_id)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_seller_applications_status_created ON seller_applications(status, created_at DESC)")
            db.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents, line_total_cents)
                SELECT o.id, o.product_id, o.quantity, CAST(o.total_price_cents / CASE WHEN o.quantity <= 0 THEN 1 ELSE o.quantity END AS INTEGER), o.total_price_cents
                FROM orders o
                WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.id)
                """
            )

    def create_shop(
        self,
        guild_id: int,
        owner_id: int,
        name: str,
        description: str,
        shop_emoji: Optional[str] = None,
        theme_name: Optional[str] = None,
        buy_button_text: Optional[str] = None,
        headline: Optional[str] = None,
        subtitle: Optional[str] = None,
        highlights: Optional[str] = None,
        terms_text: Optional[str] = None,
        is_open: bool = True,
        availability_status: str = "disponivel",
        accent_color: Optional[str] = None,
        image_url: Optional[str] = None,
        banner_url: Optional[str] = None,
    ) -> int:
        with self.connect() as db:
            public_id = self._next_shop_public_id(db, guild_id)
            db.execute(
                """
                INSERT INTO shops (
                    guild_id, public_id, owner_id, name, description, shop_emoji, theme_name, buy_button_text,
                    headline, subtitle, highlights, terms_text, is_open, availability_status,
                    accent_color, image_url, banner_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    public_id,
                    owner_id,
                    name,
                    description,
                    shop_emoji,
                    theme_name,
                    buy_button_text,
                    headline,
                    subtitle,
                    highlights,
                    terms_text,
                    1 if is_open else 0,
                    availability_status,
                    accent_color,
                    image_url,
                    banner_url,
                ),
            )
            return public_id

    def get_shop(self, guild_id: int, shop_id: int) -> Optional[Shop]:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT id AS db_id, public_id, guild_id, owner_id, name, description, shop_emoji, theme_name, buy_button_text,
                       headline, subtitle, highlights, terms_text, is_open, availability_status, accent_color, image_url, banner_url
                FROM shops
                WHERE guild_id = ? AND public_id = ?
                """,
                (guild_id, shop_id),
            ).fetchone()
        if row is None:
            return None
        return Shop(
            db_id=int(row["db_id"]),
            id=int(row["public_id"]),
            guild_id=int(row["guild_id"]),
            owner_id=int(row["owner_id"]),
            name=str(row["name"]),
            description=str(row["description"]),
            shop_emoji=str(row["shop_emoji"]) if row["shop_emoji"] else None,
            theme_name=str(row["theme_name"]) if row["theme_name"] else None,
            buy_button_text=str(row["buy_button_text"]) if row["buy_button_text"] else None,
            headline=str(row["headline"]) if row["headline"] else None,
            subtitle=str(row["subtitle"]) if row["subtitle"] else None,
            highlights=str(row["highlights"]) if row["highlights"] else None,
            terms_text=str(row["terms_text"]) if row["terms_text"] else None,
            is_open=bool(row["is_open"]),
            availability_status=str(row["availability_status"] or "disponivel"),
            accent_color=str(row["accent_color"]) if row["accent_color"] else None,
            image_url=str(row["image_url"]) if row["image_url"] else None,
            banner_url=str(row["banner_url"]) if row["banner_url"] else None,
        )

    def list_shops(self, guild_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT s.id AS db_id, s.public_id AS id, s.name, s.description, s.owner_id, s.shop_emoji, s.theme_name, s.buy_button_text,
                       s.headline, s.subtitle, s.highlights, s.terms_text, s.is_open, s.availability_status,
                       s.accent_color, s.image_url, s.banner_url,
                       COUNT(DISTINCT p.id) AS product_count,
                       COUNT(DISTINCT CASE WHEN o.status NOT IN ('concluido', 'fechado') THEN o.id END) AS active_order_count
                FROM shops s
                LEFT JOIN products p ON p.shop_id = s.id AND p.active = 1
                LEFT JOIN orders o ON o.shop_id = s.id
                WHERE s.guild_id = ?
                GROUP BY s.id
                ORDER BY s.name COLLATE NOCASE
                """,
                (guild_id,),
            ).fetchall()

    def update_shop_style(
        self,
        guild_id: int,
        shop_id: int,
        owner_id: int,
        description: Optional[str],
        shop_emoji: Optional[str],
        theme_name: Optional[str],
        buy_button_text: Optional[str],
        headline: Optional[str],
        subtitle: Optional[str],
        highlights: Optional[str],
        terms_text: Optional[str],
        is_open: Optional[bool],
        availability_status: Optional[str],
        accent_color: Optional[str],
        image_url: Optional[str],
        banner_url: Optional[str],
    ) -> bool:
        assignments: list[str] = []
        values: list[object] = []
        if description is not None:
            assignments.append("description = ?")
            values.append(description)
        if shop_emoji is not None:
            assignments.append("shop_emoji = ?")
            values.append(shop_emoji)
        if theme_name is not None:
            assignments.append("theme_name = ?")
            values.append(theme_name)
        if buy_button_text is not None:
            assignments.append("buy_button_text = ?")
            values.append(buy_button_text)
        if headline is not None:
            assignments.append("headline = ?")
            values.append(headline)
        if subtitle is not None:
            assignments.append("subtitle = ?")
            values.append(subtitle)
        if highlights is not None:
            assignments.append("highlights = ?")
            values.append(highlights)
        if terms_text is not None:
            assignments.append("terms_text = ?")
            values.append(terms_text)
        if is_open is not None:
            assignments.append("is_open = ?")
            values.append(1 if is_open else 0)
        if availability_status is not None:
            assignments.append("availability_status = ?")
            values.append(availability_status)
        if accent_color is not None:
            assignments.append("accent_color = ?")
            values.append(accent_color)
        if image_url is not None:
            assignments.append("image_url = ?")
            values.append(image_url)
        if banner_url is not None:
            assignments.append("banner_url = ?")
            values.append(banner_url)
        if not assignments:
            return False

        values.extend([guild_id, shop_id, owner_id])
        with self.connect() as db:
            cursor = db.execute(
                f"""
                UPDATE shops
                SET {", ".join(assignments)}
                WHERE guild_id = ? AND public_id = ? AND owner_id = ?
                """,
                values,
            )
            return cursor.rowcount > 0

    def add_product(self, shop_id: int, name: str, category: str, price_cents: int, description: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO products (shop_id, name, category, price_cents, description) VALUES (?, ?, ?, ?, ?)",
                (shop_id, name, category, price_cents, description),
            )
            return int(cursor.lastrowid)

    def update_product_price(self, product_id: int, price_cents: int) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE products SET price_cents = ? WHERE id = ?",
                (price_cents, product_id),
            )
            return cursor.rowcount > 0

    def update_product(
        self,
        guild_id: int,
        product_id: int,
        owner_id: int,
        name: str,
        category: str,
        price_cents: int,
        description: str,
    ) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                """
                UPDATE products
                SET name = ?, category = ?, price_cents = ?, description = ?
                WHERE id = ?
                  AND shop_id IN (
                      SELECT id FROM shops WHERE guild_id = ? AND owner_id = ?
                  )
                """,
                (name, category, price_cents, description, product_id, guild_id, owner_id),
            )
            return cursor.rowcount > 0

    def delete_product(self, guild_id: int, product_id: int, owner_id: int) -> bool:
        with self.connect() as db:
            linked_order = db.execute(
                """
                SELECT 1
                FROM shops s
                WHERE s.guild_id = ? AND s.owner_id = ?
                  AND (
                      EXISTS (
                          SELECT 1 FROM orders o
                          WHERE o.shop_id = s.id AND o.product_id = ?
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM orders o
                          JOIN order_items oi ON oi.order_id = o.id
                          WHERE o.shop_id = s.id AND oi.product_id = ?
                      )
                  )
                LIMIT 1
                """,
                (guild_id, owner_id, product_id, product_id),
            ).fetchone()
            if linked_order is not None:
                cursor = db.execute(
                    """
                    UPDATE products
                    SET active = 0
                    WHERE id = ?
                      AND shop_id IN (
                          SELECT id FROM shops WHERE guild_id = ? AND owner_id = ?
                      )
                    """,
                    (product_id, guild_id, owner_id),
                )
                return cursor.rowcount > 0
            cursor = db.execute(
                """
                DELETE FROM products
                WHERE id = ?
                  AND shop_id IN (
                      SELECT id FROM shops WHERE guild_id = ? AND owner_id = ?
                  )
                """,
                (product_id, guild_id, owner_id),
            )
            return cursor.rowcount > 0

    def product_belongs_to_owner(self, guild_id: int, product_id: int, owner_id: int) -> bool:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT p.id
                FROM products p
                JOIN shops s ON s.id = p.shop_id
                WHERE s.guild_id = ? AND s.owner_id = ? AND p.id = ?
                """,
                (guild_id, owner_id, product_id),
            ).fetchone()
        return row is not None

    def product_has_orders(self, guild_id: int, product_id: int, owner_id: int) -> bool:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT 1
                FROM shops s
                WHERE s.guild_id = ? AND s.owner_id = ?
                  AND (
                      EXISTS (
                          SELECT 1 FROM orders o
                          WHERE o.shop_id = s.id AND o.product_id = ?
                      )
                      OR EXISTS (
                          SELECT 1
                          FROM orders o
                          JOIN order_items oi ON oi.order_id = o.id
                          WHERE o.shop_id = s.id AND oi.product_id = ?
                      )
                  )
                LIMIT 1
                """,
                (guild_id, owner_id, product_id, product_id),
            ).fetchone()
        return row is not None

    def list_products(self, guild_id: int, shop_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT p.id, p.shop_id, p.name, p.category, p.price_cents, p.description
                FROM products p
                JOIN shops s ON s.id = p.shop_id
                WHERE s.guild_id = ? AND s.public_id = ? AND p.active = 1
                ORDER BY p.category COLLATE NOCASE, p.name COLLATE NOCASE
                """,
                (guild_id, shop_id),
            ).fetchall()

    def get_product(self, guild_id: int, product_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT p.id, p.shop_id, p.name, p.category, p.price_cents, p.description,
                       s.public_id AS store_id, s.id AS store_db_id, s.name AS store_name, s.owner_id, s.guild_id
                FROM products p
                JOIN shops s ON s.id = p.shop_id
                WHERE s.guild_id = ? AND p.id = ? AND p.active = 1
                """,
                (guild_id, product_id),
            ).fetchone()

    def list_shop_categories(self, guild_id: int, shop_id: int) -> list[str]:
        with self.connect() as db:
            rows = db.execute(
                """
                SELECT DISTINCT p.category
                FROM products p
                JOIN shops s ON s.id = p.shop_id
                WHERE s.guild_id = ? AND s.public_id = ? AND p.active = 1
                ORDER BY p.category COLLATE NOCASE
                """,
                (guild_id, shop_id),
            ).fetchall()
        return [str(row["category"]) for row in rows]

    def delete_shop(self, guild_id: int, shop_id: int, owner_id: int) -> bool:
        with self.connect() as db:
            existing_orders = db.execute(
                """
                SELECT 1
                FROM orders o
                JOIN shops s ON s.id = o.shop_id
                WHERE s.guild_id = ? AND s.public_id = ? AND s.owner_id = ?
                LIMIT 1
                """,
                (guild_id, shop_id, owner_id),
            ).fetchone()
            if existing_orders is not None:
                return False
            cursor = db.execute(
                "DELETE FROM shops WHERE guild_id = ? AND public_id = ? AND owner_id = ?",
                (guild_id, shop_id, owner_id),
            )
            return cursor.rowcount > 0

    def list_shop_orders_for_owner(self, guild_id: int, shop_id: int, owner_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.quantity, o.details, o.total_price_cents, o.status, o.created_at, o.started_at, o.completed_at, o.closed_at,
                       o.ticket_channel_id, o.buyer_id, o.transcript_text,
                       COALESCE(p.name, '[produto removido]') AS product_name, s.name AS shop_name,
                       COALESCE((
                           SELECT GROUP_CONCAT(COALESCE(p2.name, '[produto removido]') || ' x' || oi.quantity, ' | ')
                           FROM order_items oi
                           LEFT JOIN products p2 ON p2.id = oi.product_id
                           WHERE oi.order_id = o.id
                       ), COALESCE(p.name, '[produto removido]') || ' x' || o.quantity) AS item_summary,
                       CASE WHEN o.transcript_text IS NOT NULL AND o.transcript_text != '' THEN 1 ELSE 0 END AS has_transcript
                FROM orders o
                LEFT JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.guild_id = ? AND s.public_id = ? AND s.owner_id = ?
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (guild_id, shop_id, owner_id, limit),
            ).fetchall()

    def shop_has_orders(self, guild_id: int, shop_id: int, owner_id: int) -> bool:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT 1
                FROM orders o
                JOIN shops s ON s.id = o.shop_id
                WHERE s.guild_id = ? AND s.public_id = ? AND s.owner_id = ?
                LIMIT 1
                """,
                (guild_id, shop_id, owner_id),
            ).fetchone()
        return row is not None

    def list_shops_for_owner(self, guild_id: int, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT s.id AS db_id, s.public_id AS id, s.name, s.description, s.owner_id, s.shop_emoji, s.theme_name, s.buy_button_text,
                       s.headline, s.subtitle, s.highlights, s.terms_text, s.is_open, s.availability_status,
                       s.accent_color, s.image_url, s.banner_url,
                       COUNT(DISTINCT p.id) AS product_count,
                       COUNT(DISTINCT CASE WHEN o.status NOT IN ('concluido', 'fechado') THEN o.id END) AS active_order_count
                FROM shops s
                LEFT JOIN products p ON p.shop_id = s.id AND p.active = 1
                LEFT JOIN orders o ON o.shop_id = s.id
                WHERE s.guild_id = ? AND s.owner_id = ?
                GROUP BY s.id
                ORDER BY s.name COLLATE NOCASE
                """,
                (guild_id, owner_id),
            ).fetchall()

    def create_order(
        self,
        guild_id: int,
        shop_id: int,
        product_id: int,
        buyer_id: int,
        quantity: int,
        details: str,
        total_price_cents: int,
        assigned_editor_id: Optional[int] = None,
        accepted_terms_text: Optional[str] = None,
        accepted_terms_at: Optional[str] = None,
        service_kind: str = "channel",
        items: Optional[list[dict[str, int]]] = None,
    ) -> int:
        with self.connect() as db:
            public_id = self._next_order_public_id(db, guild_id)
            cursor = db.execute(
                """
                INSERT INTO orders (
                    guild_id, public_id, shop_id, product_id, buyer_id, quantity, details, total_price_cents,
                    assigned_editor_id, accepted_terms_text, accepted_terms_at, service_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    public_id,
                    shop_id,
                    product_id,
                    buyer_id,
                    quantity,
                    details,
                    total_price_cents,
                    assigned_editor_id,
                    accepted_terms_text,
                    accepted_terms_at,
                    service_kind,
                ),
            )
            order_id = int(cursor.lastrowid)
            normalized_items = items or [
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit_price_cents": total_price_cents // max(quantity, 1),
                    "line_total_cents": total_price_cents,
                }
            ]
            for item in normalized_items:
                db.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents, line_total_cents)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        int(item["product_id"]),
                        int(item["quantity"]),
                        int(item["unit_price_cents"]),
                        int(item["line_total_cents"]),
                    ),
                )
            return order_id

    def update_order_ticket_channel(self, order_id: int, channel_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (channel_id, order_id))

    def update_order_service_kind(self, order_id: int, service_kind: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE orders SET service_kind = ? WHERE id = ?", (service_kind, order_id))

    def update_order_service_message(self, order_id: int, message_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE orders SET service_message_id = ? WHERE id = ?", (message_id, order_id))

    def save_order_transcript(self, order_id: int, transcript_text: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE orders SET transcript_text = ? WHERE id = ?", (transcript_text, order_id))

    def create_order_log(
        self,
        order_id: int,
        guild_id: int,
        actor_id: Optional[int],
        event_type: str,
        message: str,
        metadata: Optional[dict[str, object]] = None,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO order_logs (order_id, guild_id, actor_id, event_type, message, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, guild_id, actor_id, event_type, message, json.dumps(metadata or {}, ensure_ascii=True)),
            )

    def update_order_status(self, order_id: int, status: str) -> None:
        with self.connect() as db:
            if status == "em_andamento":
                db.execute(
                    """
                    UPDATE orders
                    SET status = ?, started_at = COALESCE(started_at, CURRENT_TIMESTAMP), completed_at = NULL
                    WHERE id = ?
                    """,
                    (status, order_id),
                )
            elif status in {"concluido", "fechado"}:
                db.execute(
                    """
                    UPDATE orders
                    SET status = ?,
                        completed_at = CASE WHEN ? = 'concluido' THEN COALESCE(completed_at, CURRENT_TIMESTAMP) ELSE completed_at END,
                        closed_at = CASE WHEN ? = 'fechado' THEN CURRENT_TIMESTAMP ELSE closed_at END
                    WHERE id = ?
                    """,
                    (status, status, status, order_id),
                )
            else:
                db.execute(
                    """
                    UPDATE orders
                    SET status = ?,
                        completed_at = CASE WHEN ? = 'pendente' THEN NULL ELSE completed_at END,
                        closed_at = CASE WHEN ? = 'pendente' THEN NULL ELSE closed_at END
                    WHERE id = ?
                    """,
                    (status, status, status, order_id),
                )

    def list_order_items(self, order_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT oi.product_id, oi.quantity, oi.unit_price_cents, oi.line_total_cents, p.name AS product_name, p.category
                FROM order_items oi
                LEFT JOIN products p ON p.id = oi.product_id
                WHERE oi.order_id = ?
                ORDER BY oi.id
                """,
                (order_id,),
            ).fetchall()

    def list_order_logs(self, order_id: int, limit: int = 15) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT actor_id, event_type, message, created_at
                FROM order_logs
                WHERE order_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (order_id, limit),
            ).fetchall()

    def create_rating(
        self,
        order_id: int,
        guild_id: int,
        shop_db_id: int,
        buyer_id: int,
        seller_id: int,
        stars: int,
        comment: str,
    ) -> bool:
        with self.connect() as db:
            try:
                db.execute(
                    """
                    INSERT INTO ratings (order_id, guild_id, shop_id, buyer_id, seller_id, stars, comment)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (order_id, guild_id, shop_db_id, buyer_id, seller_id, stars, comment),
                )
            except sqlite3.IntegrityError:
                return False
            return True

    def has_rating_for_order(self, order_id: int) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT 1 FROM ratings WHERE order_id = ?", (order_id,)).fetchone()
        return row is not None

    def get_shop_rating_summary(self, shop_db_id: int) -> tuple[float, int]:
        with self.connect() as db:
            row = db.execute(
                "SELECT COALESCE(AVG(stars), 0) AS avg_stars, COUNT(*) AS total FROM ratings WHERE shop_id = ?",
                (shop_db_id,),
            ).fetchone()
        return float(row["avg_stars"]), int(row["total"])

    def list_recent_shop_ratings(self, shop_db_id: int, limit: int = 3) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT stars, comment, buyer_id, created_at
                FROM ratings
                WHERE shop_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (shop_db_id, limit),
            ).fetchall()

    def record_term_acceptance(self, guild_id: int, shop_db_id: int, buyer_id: int, terms_text: str) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO term_acceptances (guild_id, shop_id, buyer_id, terms_text)
                VALUES (?, ?, ?, ?)
                """,
                (guild_id, shop_db_id, buyer_id, terms_text),
            )

    def get_order_details(self, order_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.guild_id, o.shop_id, o.product_id, o.buyer_id, o.quantity, o.details,
                       o.total_price_cents, o.status, o.ticket_channel_id, o.service_message_id, o.service_kind,
                       o.created_at, o.started_at, o.completed_at, o.closed_at, o.transcript_text,
                       o.accepted_terms_text, o.accepted_terms_at, o.assigned_editor_id,
                       COALESCE(p.name, '[produto removido]') AS product_name,
                       s.name AS shop_name, s.public_id AS shop_public_id, s.owner_id AS shop_owner_id,
                       COALESCE((
                           SELECT GROUP_CONCAT(COALESCE(p2.name, '[produto removido]') || ' x' || oi.quantity, ' | ')
                           FROM order_items oi
                           LEFT JOIN products p2 ON p2.id = oi.product_id
                           WHERE oi.order_id = o.id
                       ), COALESCE(p.name, '[produto removido]') || ' x' || o.quantity) AS item_summary
                FROM orders o
                LEFT JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.id = ?
                """,
                (order_id,),
            ).fetchone()

    def list_orders_for_buyer(self, guild_id: int, buyer_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.quantity, o.details, o.total_price_cents, o.status, o.created_at, o.started_at, o.completed_at, o.closed_at, o.ticket_channel_id,
                       COALESCE(p.name, '[produto removido]') AS product_name, s.name AS shop_name,
                       COALESCE((
                           SELECT GROUP_CONCAT(COALESCE(p2.name, '[produto removido]') || ' x' || oi.quantity, ' | ')
                           FROM order_items oi
                           LEFT JOIN products p2 ON p2.id = oi.product_id
                           WHERE oi.order_id = o.id
                       ), COALESCE(p.name, '[produto removido]') || ' x' || o.quantity) AS item_summary,
                       CASE WHEN o.transcript_text IS NOT NULL AND o.transcript_text != '' THEN 1 ELSE 0 END AS has_transcript
                FROM orders o
                LEFT JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.guild_id = ? AND o.buyer_id = ?
                ORDER BY o.id DESC
                LIMIT 15
                """,
                (guild_id, buyer_id),
            ).fetchall()

    def list_orders_for_owner(self, guild_id: int, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.quantity, o.details, o.total_price_cents, o.status, o.created_at, o.started_at, o.completed_at, o.closed_at, o.ticket_channel_id,
                       COALESCE(p.name, '[produto removido]') AS product_name, s.name AS shop_name, o.buyer_id,
                       COALESCE((
                           SELECT GROUP_CONCAT(COALESCE(p2.name, '[produto removido]') || ' x' || oi.quantity, ' | ')
                           FROM order_items oi
                           LEFT JOIN products p2 ON p2.id = oi.product_id
                           WHERE oi.order_id = o.id
                       ), COALESCE(p.name, '[produto removido]') || ' x' || o.quantity) AS item_summary,
                       CASE WHEN o.transcript_text IS NOT NULL AND o.transcript_text != '' THEN 1 ELSE 0 END AS has_transcript
                FROM orders o
                LEFT JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.guild_id = ? AND s.owner_id = ?
                ORDER BY o.id DESC
                LIMIT 15
                """,
                (guild_id, owner_id),
            ).fetchall()

    def list_ticket_orders(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.buyer_id, o.status, o.ticket_channel_id, o.service_message_id, s.owner_id AS shop_owner_id
                FROM orders o
                JOIN shops s ON s.id = o.shop_id
                WHERE o.ticket_channel_id IS NOT NULL
                """
            ).fetchall()

    def get_editor_stats(self, guild_id: int, editor_id: int) -> sqlite3.Row:
        with self.connect() as db:
            row = db.execute(
                """
                SELECT COUNT(*) AS total_orders,
                       SUM(CASE WHEN status IN ('concluido', 'fechado') THEN 1 ELSE 0 END) AS completed_orders,
                       AVG(CASE
                            WHEN started_at IS NOT NULL AND completed_at IS NOT NULL
                            THEN (julianday(completed_at) - julianday(started_at)) * 24 * 60
                           END) AS avg_minutes
                FROM orders
                WHERE guild_id = ? AND assigned_editor_id = ?
                """,
                (guild_id, editor_id),
            ).fetchone()
        return row

    def list_recent_editor_ratings(self, seller_id: int, limit: int = 3) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT stars, comment, buyer_id, created_at
                FROM ratings
                WHERE seller_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (seller_id, limit),
            ).fetchall()

    def create_seller_application(self, guild_id: int, applicant_id: int, portfolio_text: str, specialty_text: str) -> int:
        with self.connect() as db:
            existing = db.execute(
                "SELECT id FROM seller_applications WHERE guild_id = ? AND applicant_id = ? AND status = 'pendente'",
                (guild_id, applicant_id),
            ).fetchone()
            if existing is not None:
                return int(existing["id"])
            cursor = db.execute(
                """
                INSERT INTO seller_applications (guild_id, applicant_id, portfolio_text, specialty_text)
                VALUES (?, ?, ?, ?)
                """,
                (guild_id, applicant_id, portfolio_text, specialty_text),
            )
            return int(cursor.lastrowid)

    def set_seller_application_message(self, application_id: int, channel_id: int, message_id: int) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE seller_applications SET message_channel_id = ?, message_id = ? WHERE id = ?",
                (channel_id, message_id, application_id),
            )

    def get_seller_application(self, application_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM seller_applications WHERE id = ?", (application_id,)).fetchone()

    def list_pending_seller_applications(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT id FROM seller_applications WHERE status = 'pendente'").fetchall()

    def review_seller_application(self, application_id: int, status: str, admin_id: int, note: str) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                """
                UPDATE seller_applications
                SET status = ?, admin_id = ?, review_note = ?, reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pendente'
                """,
                (status, admin_id, note[:300], application_id),
            )
            return cursor.rowcount > 0

    def upsert_shop_publication(self, guild_id: int, shop_db_id: int, channel_id: int, message_id: int) -> None:
        with self.connect() as db:
            db.execute(
                """
                INSERT INTO shop_publications (guild_id, shop_id, channel_id, message_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(shop_id, channel_id) DO UPDATE SET message_id = excluded.message_id
                """,
                (guild_id, shop_db_id, channel_id, message_id),
            )

    def list_shop_publications(self, shop_db_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                "SELECT guild_id, shop_id, channel_id, message_id FROM shop_publications WHERE shop_id = ?",
                (shop_db_id,),
            ).fetchall()

    def list_published_shops(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT DISTINCT sp.guild_id, s.public_id AS shop_public_id
                FROM shop_publications sp
                JOIN shops s ON s.id = sp.shop_id
                ORDER BY sp.guild_id, s.public_id
                """
            ).fetchall()

    def record_boost_event(self, guild_id: int, user_id: int, thanked_message_id: Optional[int]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO boost_events (guild_id, user_id, thanked_message_id) VALUES (?, ?, ?)",
                (guild_id, user_id, thanked_message_id),
            )


store_db = StoreDatabase(DATABASE_PATH)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)


def guild_only_interaction(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise app_commands.AppCommandError("Use este comando dentro de um servidor.")
    return interaction.guild_id


def is_admin_tester(user_id: int) -> bool:
    return user_id in ADMIN_TESTER_IDS


def parse_price_to_cents(value: str) -> int:
    normalized = value.strip().replace("R$", "").replace(" ", "").replace(",", ".")
    try:
        amount = float(normalized)
    except ValueError as exc:
        raise app_commands.AppCommandError("Preco invalido. Use algo como `25`, `25.50` ou `25,50`.") from exc
    if amount <= 0:
        raise app_commands.AppCommandError("O preco precisa ser maior que zero.")
    return round(amount * 100)


def format_price(price_cents: int) -> str:
    return f"R$ {price_cents / 100:.2f}".replace(".", ",")


def truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def parse_hex_color(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized.startswith("#"):
        normalized = f"#{normalized}"
    if not re.fullmatch(r"#[0-9A-F]{6}", normalized):
        raise app_commands.AppCommandError("Use uma cor em formato HEX, por exemplo `#2B2D31`.")
    return normalized


def parse_optional_image_url(value: str) -> str:
    normalized = value.strip()
    if normalized.lower() in {"remover", "none", "nenhum"}:
        return ""
    if not re.match(r"^https?://", normalized, flags=re.IGNORECASE):
        raise app_commands.AppCommandError("A imagem precisa ser uma URL `http` ou `https`.")
    return normalized


def parse_optional_shop_emoji(value: str) -> str:
    normalized = value.strip()
    if normalized.lower() in {"remover", "none", "nenhum"}:
        return ""
    if len(normalized) > 40:
        raise app_commands.AppCommandError("O emoji/enfeite da loja precisa ter no maximo 40 caracteres.")
    return normalized


def parse_optional_short_text(value: str, limit: int, field_name: str) -> str:
    normalized = value.strip()
    if normalized.lower() in {"remover", "none", "nenhum"}:
        return ""
    if len(normalized) > limit:
        raise app_commands.AppCommandError(f"{field_name} precisa ter no maximo {limit} caracteres.")
    return normalized


def parse_optional_multiline_text(value: str, limit: int, field_name: str) -> str:
    normalized = value.strip()
    if normalized.lower() in {"remover", "none", "nenhum"}:
        return ""
    if len(normalized) > limit:
        raise app_commands.AppCommandError(f"{field_name} precisa ter no maximo {limit} caracteres.")
    return normalized


def normalize_availability_status(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "disponivel": "disponivel",
        "aberta": "disponivel",
        "livre": "disponivel",
        "ocupado": "ocupado",
        "busy": "ocupado",
        "ausente": "ausente",
        "away": "ausente",
        "fechado": "fechado",
        "closed": "fechado",
    }
    if normalized in aliases:
        return aliases[normalized]
    raise app_commands.AppCommandError("Status invalido. Use `disponivel`, `ocupado`, `ausente` ou `fechado`.")


def find_lojista_role(guild: discord.Guild) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=LOJISTA_ROLE_NAME)


def member_is_lojista(member: discord.abc.User | discord.Member) -> bool:
    return isinstance(member, discord.Member) and any(role.name == LOJISTA_ROLE_NAME for role in member.roles)


def ensure_lojista_member(interaction: discord.Interaction) -> discord.Member:
    if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
        raise app_commands.AppCommandError("Use este comando dentro do servidor.")
    if not member_is_lojista(interaction.user):
        raise app_commands.AppCommandError(f"Apenas usuarios com o cargo `{LOJISTA_ROLE_NAME}` podem usar esta funcao.")
    return interaction.user


def shop_color_value(shop: Shop) -> discord.Color:
    if shop.accent_color:
        try:
            return discord.Color(int(shop.accent_color.replace("#", ""), 16))
        except ValueError:
            pass
    return EMBED_COLORS["panel"]


def shop_title(name: str, emoji: Optional[str]) -> str:
    prefix = f"{emoji} " if emoji else ""
    return f"{prefix}{name}"


def row_shop_title(shop: sqlite3.Row) -> str:
    return shop_title(str(shop["name"]), str(shop["shop_emoji"]) if shop["shop_emoji"] else None)


def shop_theme_label(shop: Shop) -> str:
    if shop.theme_name:
        return shop.theme_name
    if shop.accent_color:
        return shop.accent_color
    return "Padrao"


def row_theme_label(shop: sqlite3.Row) -> str:
    if shop["theme_name"]:
        return str(shop["theme_name"])
    if shop["accent_color"]:
        return str(shop["accent_color"])
    return "Padrao"


def shop_buy_button_text(shop: Shop) -> str:
    return truncate_text(shop.buy_button_text or "🛒 Abrir pedido", 80)


def build_shop_intro_text(shop: Shop) -> str:
    parts: list[str] = []
    if shop.headline:
        parts.append(f"**{shop.headline}**")
    if shop.subtitle:
        parts.append(shop.subtitle)
    if shop.description:
        parts.append(shop.description)
    return "\n\n".join(parts) if parts else "Sem descricao cadastrada."


def build_row_shop_intro_text(shop: sqlite3.Row) -> str:
    parts: list[str] = []
    if shop["headline"]:
        parts.append(f"**{shop['headline']}**")
    if shop["subtitle"]:
        parts.append(str(shop["subtitle"]))
    if shop["description"]:
        parts.append(str(shop["description"]))
    return "\n\n".join(parts) if parts else "Sem descricao cadastrada."


def apply_theme_preset_to_shop(shop: Shop, preset_key: str) -> dict[str, str]:
    preset = THEME_PRESETS[preset_key]
    updates = {
        "theme_name": str(preset["label"]),
        "accent_color": str(preset["color"]),
    }
    if not shop.shop_emoji:
        updates["shop_emoji"] = str(preset["emoji"])
    if not shop.headline:
        updates["headline"] = str(preset["headline"])
    if not shop.subtitle:
        updates["subtitle"] = str(preset["subtitle"])
    return updates


def shop_status_text(shop: Shop) -> str:
    effective_status = "fechado" if not shop.is_open else shop.availability_status
    meta = SHOP_AVAILABILITY_META.get(effective_status, SHOP_AVAILABILITY_META["disponivel"])
    return f"{meta['emoji']} {meta['label']}"


def row_shop_status_text(shop: sqlite3.Row) -> str:
    effective_status = "fechado" if not bool(shop["is_open"]) else str(shop["availability_status"] or "disponivel")
    meta = SHOP_AVAILABILITY_META.get(effective_status, SHOP_AVAILABILITY_META["disponivel"])
    active_orders = int(shop["active_order_count"]) if "active_order_count" in shop.keys() else 0
    return f"{meta['emoji']} {meta['label']} â€¢ {active_orders} ativo(s)"


def slugify_channel_name(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value.lower()).strip("-")
    return normalized or "pedido"


def shorten_channel_slug(value: str, limit: int) -> str:
    cleaned = slugify_channel_name(value)
    return cleaned[:limit].strip("-") or "pedido"


def build_ticket_channel_name(buyer_name: str, buyer_id: int, product_name: str, order_public_id: int) -> str:
    buyer_slug = shorten_channel_slug(buyer_name, 20)
    product_slug = shorten_channel_slug(product_name, 24)
    channel_name = f"{buyer_slug}-{product_slug}-{order_public_id:03d}"
    return channel_name[:95].strip("-") or f"pedido-{order_public_id:03d}"


def get_status_meta(status: str) -> dict[str, object]:
    return ORDER_STATUS_META.get(status, ORDER_STATUS_META["pendente"])


def format_status(status: str) -> str:
    meta = get_status_meta(status)
    return f"{meta['emoji']} {meta['label']}"


def format_rating_summary(average: float, total: int) -> str:
    if total == 0:
        return "Sem avaliacoes ainda"
    return f"{average:.1f}/5 ⭐ ({total})"


def format_star_rating(stars: int) -> str:
    safe_stars = max(1, min(stars, 5))
    return "★" * safe_stars + "☆" * (5 - safe_stars)


def build_recent_rating_lines(ratings: list[sqlite3.Row]) -> str:
    if not ratings:
        return "Nenhuma avaliacao publicada ainda."
    lines = []
    for rating in ratings[:3]:
        comment = truncate_text(str(rating["comment"] or "Sem comentario."), 100)
        lines.append(
            f"{format_star_rating(int(rating['stars']))} • <@{rating['buyer_id']}>\n"
            f"{comment}"
        )
    return "\n\n".join(lines)


def format_delivery_duration(started_at: Optional[str], completed_at: Optional[str]) -> str:
    if not started_at or not completed_at:
        return "Em aberto"
    try:
        start = datetime.fromisoformat(str(started_at).replace(" ", "T"))
        end = datetime.fromisoformat(str(completed_at).replace(" ", "T"))
    except ValueError:
        return "Indisponivel"
    delta = end - start
    total_minutes = int(delta.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    days, hours = divmod(hours, 24)
    if days > 0:
        return f"{days}d {hours}h"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def build_ticket_reference(channel_id: Optional[int]) -> str:
    if channel_id:
        return f"<#{channel_id}>"
    return "`nao criado`"


def build_ticket_creation_notice(ticket_channel: Optional[discord.abc.GuildChannel]) -> str:
    if ticket_channel is not None:
        return ticket_channel.mention
    return (
        "`nao foi possivel criar o ticket`\n"
        "Verifique se o bot tem permissao para criar, ver e gerenciar canais/categorias."
    )


def build_stat_block(label: str, value: str) -> str:
    return f"**{label}**\n`{value}`"


def build_section_title(icon: str, title: str) -> str:
    return f"{icon} **{title}**"


def format_shop_highlights(value: Optional[str]) -> str:
    if not value:
        return "• Atendimento organizado\n• Fluxo guiado dentro do Discord"
    parts = [part.strip() for part in str(value).replace("\n", "|").split("|") if part.strip()]
    if not parts:
        return "• Atendimento organizado\n• Fluxo guiado dentro do Discord"
    return "\n".join(f"• {truncate_text(part, 80)}" for part in parts[:4])


def short_order_details(value: str) -> str:
    return truncate_text(value or "Sem observacoes.", 120)


def format_order_items_inline(order: sqlite3.Row) -> str:
    return truncate_text(str(order["item_summary"] if "item_summary" in order.keys() else order["product_name"]), 120)


def format_transcript_state(order: sqlite3.Row) -> str:
    has_transcript = bool(order["has_transcript"]) if "has_transcript" in order.keys() else bool(order["transcript_text"])
    return "Disponivel" if has_transcript else "Pendente"


def normalize_category(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    return cleaned[:40] if cleaned else "Geral"


def filter_products_by_category(products: list[sqlite3.Row], category: Optional[str]) -> list[sqlite3.Row]:
    if not category or category == "Todos":
        return products
    return [product for product in products if str(product["category"]) == category]


def paginate_products(products: list[sqlite3.Row], page: int, page_size: int = 5) -> tuple[list[sqlite3.Row], int]:
    total_pages = max(1, (len(products) + page_size - 1) // page_size)
    safe_page = max(0, min(page, total_pages - 1))
    start = safe_page * page_size
    return products[start : start + page_size], total_pages


def build_home_panel_embed(guild_id: int, viewer_id: int) -> discord.Embed:
    shops = store_db.list_shops(guild_id)
    my_orders = store_db.list_orders_for_buyer(guild_id, viewer_id)
    received_orders = store_db.list_orders_for_owner(guild_id, viewer_id)

    embed = discord.Embed(
        title="Central de Lojas",
        description="Uma visao rapida das vitrines, dos seus pedidos e do atendimento das suas lojas.",
        color=EMBED_COLORS["panel"],
    )
    embed.add_field(name="Resumo", value=build_stat_block("Lojas ativas", str(len(shops))), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Seus pedidos", str(len(my_orders))), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Pedidos recebidos", str(len(received_orders))), inline=True)

    if shops:
        preview = []
        for shop in shops[:4]:
            preview.append(
                f"`#{shop['id']}` **{row_shop_title(shop)}**\n"
                f"{shop['product_count']} produto(s) • {row_theme_label(shop)}"
            )
        embed.add_field(name="Lojas em destaque", value="\n\n".join(preview), inline=False)
    else:
        embed.add_field(name="Lojas em destaque", value="Ainda nao existe nenhuma loja cadastrada.", inline=False)

    embed.add_field(
        name="Atalhos",
        value=(
            "`Explorar lojas` para navegar nas vitrines.\n"
            "`Meus pedidos` para acompanhar compras.\n"
            "`Gerenciar lojas` para cuidar do visual e do catalogo.\n"
            "`Solicitar lojista` para pedir acesso ao modo vendedor."
        ),
        inline=False,
    )
    embed.set_footer(text="Painel privado • cliente e vendedor em fluxos separados")
    return embed


def build_shop_browser_embed(shops: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title="Explorar Vitrines",
        description="Descubra lojas com estilo próprio, compare propostas e abra a vitrine que mais combina com o seu pedido.",
        color=EMBED_COLORS["panel"],
    )
    if not shops:
        embed.add_field(name="Lojas", value="Nenhuma loja cadastrada ainda.", inline=False)
        return embed

    lines = []
    for shop in shops[:8]:
        lines.append(
            f"`#{shop['id']}` **{row_shop_title(shop)}**\n"
            f"Dono: <@{shop['owner_id']}> • Produtos: {shop['product_count']} • Tema: {row_theme_label(shop)}"
        )
    embed.add_field(name="Disponiveis agora", value="\n\n".join(lines), inline=False)
    embed.set_footer(text="Ao comprar, um ticket privado e criado automaticamente")
    return embed


def build_shop_card_embed(
    shops: list[sqlite3.Row],
    index: int,
) -> discord.Embed:
    if not shops:
        return build_shop_browser_embed(shops)

    safe_index = max(0, min(index, len(shops) - 1))
    shop = shops[safe_index]
    color_value = EMBED_COLORS["panel"]
    if shop["accent_color"]:
        try:
            color_value = discord.Color(int(str(shop["accent_color"]).replace("#", ""), 16))
        except ValueError:
            pass

    embed = discord.Embed(
        title=f"{row_shop_title(shop)} • vitrine {safe_index + 1}/{len(shops)}",
        description=build_row_shop_intro_text(shop),
        color=color_value,
    )
    embed.add_field(name="Identificacao", value=build_stat_block("Loja", f"#{shop['id']}"), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Produtos", str(shop["product_count"])), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Tema", row_theme_label(shop)), inline=True)
    embed.add_field(name="Vendedor", value=f"<@{shop['owner_id']}>", inline=False)
    if shop["highlights"]:
        embed.add_field(name="Vantagens", value=str(shop["highlights"]), inline=False)
    if shop["image_url"]:
        embed.set_thumbnail(url=str(shop["image_url"]))
    if shop["banner_url"]:
        embed.set_image(url=str(shop["banner_url"]))

    preview_lines = []
    for row in shops[:5]:
        marker = "➤" if int(row["id"]) == int(shop["id"]) else "•"
        preview_lines.append(f"{marker} `#{row['id']}` {row_shop_title(row)}")
    embed.add_field(name=build_section_title("🧭", "Outras vitrines"), value="\n".join(preview_lines), inline=False)
    embed.set_footer(text="Abra o catálogo completo pelo seletor abaixo")
    return embed


def build_shop_panel_embed(shop: Shop, products: list[sqlite3.Row]) -> discord.Embed:
    average_rating, total_ratings = store_db.get_shop_rating_summary(shop.db_id)
    recent_ratings = store_db.list_recent_editor_ratings(shop.owner_id, limit=3)
    embed = discord.Embed(
        title=f"{shop_title(shop.name, shop.shop_emoji)} • painel da loja",
        description=build_shop_intro_text(shop),
        color=shop_color_value(shop),
    )
    embed.add_field(name="Resumo", value=build_stat_block("Loja", f"#{shop.id}"), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Itens", str(len(products))), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Tema", shop_theme_label(shop)), inline=True)
    embed.add_field(name="Avaliacoes", value=build_stat_block("Media", format_rating_summary(average_rating, total_ratings)), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Quantidade", str(total_ratings)), inline=True)
    embed.add_field(name="Vendedor", value=f"<@{shop.owner_id}>", inline=False)
    embed.add_field(name="Acao principal", value=shop_buy_button_text(shop), inline=False)
    if shop.highlights:
        embed.add_field(name="Vantagens", value=shop.highlights, inline=False)
    embed.add_field(name="Feedback recente", value=build_recent_rating_lines(recent_ratings), inline=False)
    if shop.image_url:
        embed.set_thumbnail(url=shop.image_url)
    if shop.banner_url:
        embed.set_image(url=shop.banner_url)

    if not products:
        embed.add_field(name="Catalogo", value="Esta loja ainda nao tem itens ativos.", inline=False)
        embed.set_footer(text="Use /personalizar_loja para deixar a vitrine mais bonita")
        return embed

    lines = []
    for product in products[:10]:
        lines.append(
            f"`#{product['id']}` **{product['name']}**\n"
            f"{product['category']} • {format_price(int(product['price_cents']))}\n"
            f"{truncate_text(product['description'] or 'Sem descricao.', 70)}"
        )
    embed.add_field(name="Produtos em destaque", value="\n\n".join(lines), inline=False)
    embed.set_footer(text="O pedido abre um ticket privado com controles de atendimento")
    return embed


def build_shop_catalog_embed(
    shop: Shop,
    products: list[sqlite3.Row],
    page: int,
    current_category: str,
) -> discord.Embed:
    average_rating, total_ratings = store_db.get_shop_rating_summary(shop.db_id)
    filtered_products = filter_products_by_category(products, current_category if current_category != "Todos" else None)
    current_page_products, total_pages = paginate_products(filtered_products, page)
    embed = discord.Embed(
        title=f"{shop_title(shop.name, shop.shop_emoji)} • catalogo",
        description=build_shop_intro_text(shop),
        color=shop_color_value(shop),
    )
    embed.add_field(name="Categoria", value=f"`{current_category}`", inline=True)
    embed.add_field(name="Pagina", value=f"`{min(page + 1, total_pages)}/{total_pages}`", inline=True)
    embed.add_field(name="Itens", value=f"`{len(filtered_products)}`", inline=True)
    embed.add_field(name="Avaliacoes", value=f"`{format_rating_summary(average_rating, total_ratings)}`", inline=False)
    if shop.highlights:
        embed.add_field(name="Vantagens", value=shop.highlights, inline=False)
    if shop.image_url:
        embed.set_thumbnail(url=shop.image_url)
    if shop.banner_url:
        embed.set_image(url=shop.banner_url)

    if not current_page_products:
        embed.add_field(name="Catalogo", value="Nenhum item nessa categoria ainda.", inline=False)
        embed.set_footer(text="Use o seletor para trocar de categoria")
        return embed

    lines = []
    for product in current_page_products:
        lines.append(
            f"`#{product['id']}` **{product['name']}**\n"
            f"{product['category']} • **{format_price(int(product['price_cents']))}**\n"
            f"{truncate_text(product['description'] or 'Sem descricao.', 90)}"
        )
    embed.add_field(name="Produtos desta pagina", value="\n\n".join(lines), inline=False)
    embed.set_footer(text="Selecione um produto abaixo para abrir o pedido")
    return embed


def build_product_preview_embed(shop: Shop, products: list[sqlite3.Row]) -> discord.Embed:
    average_rating, total_ratings = store_db.get_shop_rating_summary(shop.db_id)
    recent_ratings = store_db.list_recent_editor_ratings(shop.owner_id, limit=3)
    lead_product = products[0]
    embed = discord.Embed(
        title=f"Prévia da compra • {shop_title(shop.name, shop.shop_emoji)}",
        description=build_shop_intro_text(shop),
        color=shop_color_value(shop),
    )
    embed.add_field(name="Loja", value=f"`#{shop.id}`", inline=True)
    embed.add_field(name="Selecionados", value=f"`{len(products)}` item(ns)", inline=True)
    embed.add_field(name="Avaliacoes", value=f"`{format_rating_summary(average_rating, total_ratings)}`", inline=True)
    selected_lines = []
    for product in products[:5]:
        selected_lines.append(
            f"`#{product['id']}` **{product['name']}** • {product['category']} • {format_price(int(product['price_cents']))}"
        )
    embed.add_field(name="Itens escolhidos", value="\n".join(selected_lines), inline=False)
    embed.add_field(
        name="Produto principal",
        value=(
            f"**{lead_product['name']}**\n"
            f"{lead_product['category']} • {format_price(int(lead_product['price_cents']))}\n"
            f"{truncate_text(str(lead_product['description'] or 'Sem descricao.'), 160)}"
        ),
        inline=False,
    )
    embed.add_field(name="Feedback recente", value=build_recent_rating_lines(recent_ratings), inline=False)
    if shop.terms_text:
        embed.add_field(name="Termos", value="A compra desta loja exige aceite antes da abertura do pedido.", inline=False)
    embed.set_footer(text="Defina as quantidades e envie o briefing no próximo passo")
    return embed


def build_shop_history_embed(shop: Shop, orders: list[sqlite3.Row], selected_order_id: Optional[int] = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"Historico • {shop_title(shop.name, shop.shop_emoji)}",
        description="Pedidos concluidos e em andamento da loja com acesso a ticket, transcript e eventos.",
        color=shop_color_value(shop),
    )
    embed.add_field(name="Total", value=f"`{len(orders)}`", inline=True)
    embed.add_field(
        name="Em aberto",
        value=f"`{sum(1 for order in orders if str(order['status']) not in {'concluido', 'fechado'})}`",
        inline=True,
    )
    embed.add_field(
        name="Finalizados",
        value=f"`{sum(1 for order in orders if str(order['status']) in {'concluido', 'fechado'})}`",
        inline=True,
    )
    if not orders:
        embed.add_field(name="Pedidos", value="Nenhum pedido encontrado para esta loja ainda.", inline=False)
        return embed

    selected = next((order for order in orders if int(order["db_id"]) == selected_order_id), None) if selected_order_id is not None else None
    if selected is None:
        selected = orders[0]

    embed.add_field(
        name="Pedido selecionado",
        value=(
            f"Pedido `#{selected['id']}` • {format_status(str(selected['status']))}\n"
            f"Cliente: <@{selected['buyer_id']}>\n"
            f"Itens: {format_order_items_inline(selected)}\n"
            f"Tempo: {format_delivery_duration(selected['started_at'], selected['completed_at'])}\n"
            f"Ticket: {build_ticket_reference(selected['ticket_channel_id'])}"
        ),
        inline=False,
    )

    preview_lines = []
    for order in orders[:8]:
        marker = "➤" if int(order["db_id"]) == int(selected["db_id"]) else "•"
        preview_lines.append(
            f"{marker} `#{order['id']}` {format_status(str(order['status']))} • <@{order['buyer_id']}> • {truncate_text(str(order['item_summary']), 60)}"
        )
    embed.add_field(name="Pedidos recentes", value="\n".join(preview_lines), inline=False)
    embed.set_footer(text="Use o seletor para trocar o pedido e o botão para abrir os logs")
    return embed


def build_editor_stats_embed(shop: Shop, stats: sqlite3.Row, recent_ratings: list[sqlite3.Row]) -> discord.Embed:
    total_orders = int(stats["total_orders"] or 0)
    completed_orders = int(stats["completed_orders"] or 0)
    avg_minutes = stats["avg_minutes"]
    avg_text = f"{float(avg_minutes):.1f} min" if avg_minutes is not None else "Sem media ainda"
    embed = discord.Embed(
        title=f"Estatisticas do editor • {shop_title(shop.name, shop.shop_emoji)}",
        description="Resumo do desempenho do editor principal desta loja.",
        color=shop_color_value(shop),
    )
    embed.add_field(name="Editor", value=f"<@{shop.owner_id}>", inline=False)
    embed.add_field(name="Pedidos totais", value=f"`{total_orders}`", inline=True)
    embed.add_field(name="Concluidos", value=f"`{completed_orders}`", inline=True)
    embed.add_field(name="Tempo medio", value=f"`{avg_text}`", inline=True)
    embed.add_field(name="Feedback recente", value=build_recent_rating_lines(recent_ratings), inline=False)
    embed.set_footer(text="Baseado no historico registrado para o editor responsavel")
    return embed


def build_order_logs_embed(order: sqlite3.Row, logs: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title=f"Logs do pedido #{order['id']}",
        description=f"{order['shop_name']} • {truncate_text(str(order['item_summary']), 120)}",
        color=get_status_meta(str(order["status"]))["color"],
    )
    embed.add_field(name="Cliente", value=f"<@{order['buyer_id']}>", inline=True)
    embed.add_field(name="Status", value=format_status(str(order["status"])), inline=True)
    embed.add_field(name="Ticket", value=build_ticket_reference(order["ticket_channel_id"]), inline=True)
    if not logs:
        embed.add_field(name="Eventos", value="Nenhum log encontrado para este pedido.", inline=False)
        return embed
    lines = []
    for log in logs:
        actor = f"<@{log['actor_id']}>" if log["actor_id"] else "Sistema"
        lines.append(f"[{log['created_at']}] {actor} • `{log['event_type']}`\n{truncate_text(str(log['message']), 180)}")
    embed.add_field(name="Eventos", value="\n\n".join(lines[:10]), inline=False)
    embed.set_footer(text="Os logs sao registrados automaticamente em criacao, status e encerramento")
    return embed


def build_seller_application_embed(
    application_id: int,
    user_id: int,
    portfolio_text: str,
    specialty_text: str,
    status: str = "pendente",
    review_note: str = "",
    admin_id: Optional[int] = None,
) -> discord.Embed:
    color = EMBED_COLORS["panel"]
    status_label = "Pendente"
    if status == "aprovado":
        color = EMBED_COLORS["success"]
        status_label = "Aprovado"
    elif status == "recusado":
        color = EMBED_COLORS["danger"]
        status_label = "Recusado"
    embed = discord.Embed(title=f"Solicitacao de lojista #{application_id}", color=color)
    embed.add_field(name="Usuario", value=f"<@{user_id}> (`{user_id}`)", inline=False)
    embed.add_field(name="Portfolio", value=truncate_text(portfolio_text or "Nao informado.", 1000), inline=False)
    embed.add_field(name="Especialidades", value=truncate_text(specialty_text or "Nao informado.", 1000), inline=False)
    embed.add_field(name="Status", value=status_label, inline=True)
    if admin_id:
        embed.add_field(name="Revisado por", value=f"<@{admin_id}>", inline=True)
    if review_note:
        embed.add_field(name="Motivo / observacao", value=truncate_text(review_note, 1000), inline=False)
    return embed


def build_owner_shop_embed(shops: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title="Painel do Vendedor",
        description="Sua área de gestão para manter vitrines, catálogo e identidade visual com aparência profissional.",
        color=EMBED_COLORS["panel"],
    )
    if not shops:
        embed.add_field(name="Lojas", value="Voce ainda nao criou nenhuma loja. Use o botao **Criar loja** abaixo para comecar.", inline=False)
        return embed
    embed.add_field(name="Resumo", value=build_stat_block("Suas lojas", str(len(shops))), inline=True)
    total_products = sum(int(shop["product_count"]) for shop in shops)
    embed.add_field(name=" ", value=build_stat_block("Produtos ativos", str(total_products)), inline=True)
    themed = sum(1 for shop in shops if shop["accent_color"] or shop["image_url"] or shop["banner_url"])
    embed.add_field(name="  ", value=build_stat_block("Vitrines personalizadas", str(themed)), inline=True)
    lines = []
    for shop in shops[:8]:
        lines.append(
            f"`#{shop['id']}` **{row_shop_title(shop)}**\n"
            f"Produtos: {shop['product_count']} • Tema: {row_theme_label(shop)} • {row_shop_status_text(shop)}"
        )
    embed.add_field(name=build_section_title("🧾", "Selecione uma vitrine"), value="\n\n".join(lines), inline=False)
    embed.set_footer(text="Tudo aqui foi pensado para gestão rápida, visual e sem comandos longos")
    return embed


def build_owner_product_embed(shop: Shop, products: list[sqlite3.Row], selected_product_id: Optional[int] = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"Produtos • {shop_title(shop.name, shop.shop_emoji)}",
        description="Edite, revise ou remova serviços da sua vitrine em um painel direto e visual.",
        color=shop_color_value(shop),
    )
    embed.add_field(name=build_section_title("🏷️", "Loja"), value=f"`#{shop.id}`", inline=True)
    embed.add_field(name=build_section_title("📦", "Itens ativos"), value=f"`{len(products)}`", inline=True)
    embed.add_field(name=build_section_title("🎨", "Cor"), value=f"`{shop.accent_color or 'Padrão'}`", inline=True)
    if shop.image_url:
        embed.set_thumbnail(url=shop.image_url)

    if not products:
        embed.add_field(
            name=build_section_title("🗂️", "Catálogo"),
            value="Nenhum produto cadastrado ainda.",
            inline=False
        )
        embed.set_footer(text="Use “Novo serviço” para adicionar o primeiro item")
        return embed

    selected = None
    if selected_product_id is not None:
        selected = next((product for product in products if int(product["id"]) == selected_product_id), None)
    if selected is None:
        selected = products[0]

    embed.add_field(
        name=build_section_title("🔎", "Serviço selecionado"),
        value=(
            f"`#{selected['id']}` **{selected['name']}**\n"
            f"Categoria: `{selected['category']}`\n"
            f"Preço: **{format_price(int(selected['price_cents']))}**\n"
            f"{truncate_text(selected['description'] or 'Sem descrição.', 180)}"
        ),
        inline=False,
    )

    preview = []
    for product in products[:8]:
        marker = "➤" if int(product["id"]) == int(selected["id"]) else "•"
        preview.append(f"{marker} `#{product['id']}` {product['name']} • {product['category']}")

    embed.add_field(
        name=build_section_title("🧾", "Itens da loja"),
        value="\n".join(preview),
        inline=False
    )

    embed.set_footer(text="Selecione um serviço abaixo para editar, excluir ou revisar")
    return embed

def resolve_ticket_category(
    guild: discord.Guild,
    current_channel: Optional[discord.abc.GuildChannel],
) -> Optional[discord.CategoryChannel]:
    if TICKET_CATEGORY_ID:
        configured = guild.get_channel(TICKET_CATEGORY_ID)
        if isinstance(configured, discord.CategoryChannel):
            return configured
    if isinstance(current_channel, discord.TextChannel):
        return current_channel.category
    return None


def resolve_ticket_archive_category(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    if TICKET_ARCHIVE_CATEGORY_ID:
        configured = guild.get_channel(TICKET_ARCHIVE_CATEGORY_ID)
        if isinstance(configured, discord.CategoryChannel):
            return configured
    return None


def build_owner_ticket_category_name(owner_member: discord.Member) -> str:
    base_name = owner_member.display_name or owner_member.name
    return truncate_text(f"atendimento-{slugify_channel_name(base_name)}-{owner_member.id}", 95)


async def get_or_create_owner_ticket_category(
    guild: discord.Guild,
    owner_member: discord.Member,
    bot_member: discord.Member,
    fallback_channel: Optional[discord.abc.GuildChannel],
) -> Optional[discord.CategoryChannel]:
    expected_name = build_owner_ticket_category_name(owner_member)
    existing = discord.utils.get(guild.categories, name=expected_name)
    if existing is not None:
        return existing

    if TICKET_CATEGORY_ID:
        configured = guild.get_channel(TICKET_CATEGORY_ID)
        if isinstance(configured, discord.CategoryChannel):
            return configured

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        owner_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    position = None
    if isinstance(fallback_channel, discord.TextChannel) and fallback_channel.category is not None:
        position = fallback_channel.category.position + 1

    try:
        return await guild.create_category(
            name=expected_name,
            overwrites=overwrites,
            position=position,
            reason=f"Categoria de atendimento criada para o vendedor {owner_member.id}",
        )
    except (discord.Forbidden, discord.HTTPException):
        return resolve_ticket_category(guild, fallback_channel)


async def set_ticket_participants_visibility(
    channel: discord.TextChannel,
    buyer: discord.abc.Snowflake,
    owner: discord.abc.Snowflake,
    buyer_visible: bool,
    buyer_can_send: bool,
    owner_can_send: bool,
) -> None:
    buyer_overwrite = discord.PermissionOverwrite(
        view_channel=buyer_visible,
        send_messages=buyer_can_send if buyer_visible else False,
        read_message_history=buyer_visible,
        attach_files=buyer_can_send if buyer_visible else False,
        embed_links=buyer_visible,
    )
    owner_overwrite = discord.PermissionOverwrite(
        view_channel=True,
        send_messages=owner_can_send,
        read_message_history=True,
        attach_files=owner_can_send,
        embed_links=True,
        manage_messages=True,
    )
    await channel.set_permissions(buyer, overwrite=buyer_overwrite)
    await channel.set_permissions(owner, overwrite=owner_overwrite)


async def send_owner_notification(
    guild: Optional[discord.Guild],
    owner_id: int,
    embed: discord.Embed,
    ticket_channel: Optional[discord.abc.GuildChannel],
) -> None:
    if guild is None:
        return

    owner = guild.get_member(owner_id)
    if owner is None:
        return

    ticket_line = f"\nTicket: {ticket_channel.mention}" if ticket_channel else ""
    try:
        await owner.send(content=f"Novo pedido recebido.{ticket_line}", embed=embed)
    except discord.Forbidden:
        logger.warning("Nao foi possivel enviar notificacao privada para o lojista %s.", owner_id)


def resolve_service_desk_channel(guild: discord.Guild) -> Optional[discord.abc.GuildChannel]:
    if SERVICE_DESK_CHANNEL_ID:
        configured = guild.get_channel(SERVICE_DESK_CHANNEL_ID)
        if isinstance(configured, (discord.TextChannel, discord.ForumChannel)):
            return configured
    return None


async def build_transcript_text(channel: discord.abc.Messageable, order_id: int) -> str:
    lines = [f"Transcript do pedido #{order_id}"]
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            created_at = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
            content = message.clean_content or "[sem texto]"
            attachment_text = ""
            if message.attachments:
                attachment_text = " | anexos: " + ", ".join(attachment.url for attachment in message.attachments)
            lines.append(f"[{created_at}] {message.author} ({message.author.id}): {content}{attachment_text}")
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        lines.append("Nao foi possivel coletar o historico completo deste atendimento.")
    return "\n".join(lines)


async def persist_transcript_and_logs(
    guild: Optional[discord.Guild],
    channel: Optional[discord.abc.GuildChannel],
    order: sqlite3.Row,
    actor_id: Optional[int],
    event_type: str,
    message: str,
) -> None:
    store_db.create_order_log(int(order["db_id"]), int(order["guild_id"]), actor_id, event_type, message)
    if channel is None or not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return
    transcript_text = await build_transcript_text(channel, int(order["id"]))
    store_db.save_order_transcript(int(order["db_id"]), transcript_text)
    if guild is None or TICKET_LOG_CHANNEL_ID is None:
        return
    log_channel = guild.get_channel(TICKET_LOG_CHANNEL_ID)
    if not isinstance(log_channel, discord.TextChannel):
        return
    embed = discord.Embed(
        title=f"Log do pedido #{order['id']}",
        description=message,
        color=EMBED_COLORS["panel"],
    )
    embed.add_field(name="Cliente", value=f"<@{order['buyer_id']}>", inline=True)
    embed.add_field(name="Loja", value=order["shop_name"], inline=True)
    embed.add_field(name="Status", value=format_status(str(order["status"])), inline=True)
    embed.add_field(name="Itens", value=truncate_text(str(order["item_summary"]), 900), inline=False)
    embed.add_field(name="Transcript", value=truncate_text(transcript_text, 900), inline=False)
    await log_channel.send(embed=embed)


async def create_ticket_channel(
    interaction: discord.Interaction,
    shop: Shop,
    order_public_id: int,
    product_name: str,
) -> Optional[discord.abc.GuildChannel]:
    guild = interaction.guild
    if guild is None or bot.user is None:
        return None

    owner_member = guild.get_member(shop.owner_id)
    if owner_member is None:
        try:
            owner_member = await guild.fetch_member(shop.owner_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    bot_member = guild.me or guild.get_member(bot.user.id)
    if bot_member is None:
        return None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
        owner_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            manage_messages=True,
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        ),
    }

    buyer_name = interaction.user.display_name if isinstance(interaction.user, discord.Member) else interaction.user.name
    channel_name = build_ticket_channel_name(
        buyer_name=buyer_name,
        buyer_id=interaction.user.id,
        product_name=product_name,
        order_public_id=order_public_id,
    )

    service_desk = resolve_service_desk_channel(guild)
    if isinstance(service_desk, discord.TextChannel):
        try:
            thread = await service_desk.create_thread(
                name=channel_name,
                auto_archive_duration=10080,
                type=discord.ChannelType.private_thread,
                invitable=False,
            )
            await thread.add_user(interaction.user)
            await thread.add_user(owner_member)
            return thread
        except TypeError:
            logger.warning(
                "A versao atual da API nao suportou thread privada para o pedido #%s; usando fallback privado por canal.",
                order_public_id,
            )
        except (discord.Forbidden, discord.HTTPException):
            logger.warning("Falha ao criar thread privada para o pedido #%s; usando fallback por canal.", order_public_id)

    category = await get_or_create_owner_ticket_category(guild, owner_member, bot_member, interaction.channel)

    try:
        return await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Pedido #{order_public_id} | Loja #{shop.id} | Cliente {interaction.user.id}",
            reason=f"Ticket criado para o pedido #{order_public_id}",
        )
    except (discord.Forbidden, discord.HTTPException):
        return None


async def sync_ticket_message(message: discord.Message, order_id: int) -> None:
    order = store_db.get_order_details(order_id)
    if order is None:
        return
    await message.edit(embed=build_order_embed_from_row(order), view=TicketControlsView.from_order(order))


async def create_order_and_ticket(
    interaction: discord.Interaction,
    shop: Shop,
    product: sqlite3.Row,
    quantity: int,
    details: str,
    items: Optional[list[dict[str, int]]] = None,
    accepted_terms_text: Optional[str] = None,
) -> tuple[int, int, Optional[discord.abc.GuildChannel]]:
    guild_id = guild_only_interaction(interaction)
    if interaction.user.id == shop.owner_id and not is_admin_tester(interaction.user.id):
        raise app_commands.AppCommandError(
            "Voce nao pode comprar um produto da sua propria loja. "
            "Se este perfil for de teste, adicione seu ID em `ADMIN_TESTER_IDS` no arquivo `.env`."
        )
    if not shop.is_open:
        raise app_commands.AppCommandError("Esta loja esta fechada no momento.")

    normalized_items = items or [
        {
            "product_id": int(product["id"]),
            "quantity": quantity,
            "unit_price_cents": int(product["price_cents"]),
            "line_total_cents": int(product["price_cents"]) * quantity,
        }
    ]
    total_price_cents = sum(int(item["line_total_cents"]) for item in normalized_items)
    total_quantity = sum(int(item["quantity"]) for item in normalized_items)
    order_id = store_db.create_order(
        guild_id=guild_id,
        shop_id=shop.db_id,
        product_id=int(product["id"]),
        buyer_id=interaction.user.id,
        quantity=total_quantity,
        details=details[:400],
        total_price_cents=total_price_cents,
        assigned_editor_id=shop.owner_id,
        accepted_terms_text=accepted_terms_text,
        accepted_terms_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if accepted_terms_text else None,
        service_kind="thread" if SERVICE_DESK_CHANNEL_ID else "channel",
        items=normalized_items,
    )

    order = store_db.get_order_details(order_id)
    if order is None:
        raise app_commands.AppCommandError("Nao foi possivel finalizar o pedido.")

    primary_name = str(product["name"]) if len(normalized_items) == 1 else f"{len(normalized_items)} itens"
    ticket_channel = await create_ticket_channel(interaction, shop, int(order["id"]), primary_name)
    if ticket_channel is not None:
        store_db.update_order_ticket_channel(order_id, ticket_channel.id)
        store_db.update_order_service_kind(order_id, "thread" if isinstance(ticket_channel, discord.Thread) else "channel")
        order = store_db.get_order_details(order_id)
        if order is None:
            raise app_commands.AppCommandError("Nao foi possivel recarregar o pedido.")

    if ticket_channel is not None:
        ticket_message = await ticket_channel.send(
            content=(
                f"{interaction.user.mention} <@{shop.owner_id}>\n"
                f"Pedido **#{order['id']}** aberto com sucesso.\n"
                "Use este canal para alinhar detalhes, prazo e entrega do pedido."
            ),
            embed=build_order_embed_from_row(order),
            view=TicketControlsView.from_order(order),
        )
        store_db.update_order_service_message(order_id, ticket_message.id)
        await sync_ticket_message(ticket_message, order_id)

    store_db.create_order_log(
        order_id,
        guild_id,
        interaction.user.id,
        "order_created",
        f"Pedido criado com {len(normalized_items)} item(ns).",
        {"items": normalized_items},
    )
    await send_owner_notification(interaction.guild, shop.owner_id, build_order_embed_from_row(order), ticket_channel)
    return order_id, total_price_cents, ticket_channel


class HeaderButton(discord.ui.Button):
    def __init__(self, label: str) -> None:
        super().__init__(label=truncate_text(label, 30), style=discord.ButtonStyle.secondary, disabled=True, row=0)


class BasePanelView(discord.ui.View):
    def __init__(self, viewer_id: Optional[int], timeout: Optional[float] = 600) -> None:
        super().__init__(timeout=timeout)
        self.viewer_id = viewer_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.viewer_id is None:
            return True
        if interaction.user.id != self.viewer_id:
            await interaction.response.send_message("Esse painel pertence a outra pessoa.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[discord.ui.View]) -> None:
        logger.exception("Erro na view %s item=%s", self.__class__.__name__, item.__class__.__name__, exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send("Erro ao processar a acao. Tente novamente em instantes.", ephemeral=True)
        else:
            await interaction.response.send_message("Erro ao processar a acao. Tente novamente em instantes.", ephemeral=True)


class HomeActionSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="🛍 Explorar lojas", description="Abrir vitrines e selecionar produtos", value="shops"),
            discord.SelectOption(label="📦 Meus pedidos", description="Ver tickets e pedidos que voce abriu", value="my_orders"),
            discord.SelectOption(label="🎨 Gerenciar lojas", description="Personalizar e administrar suas vitrines", value="manage_shops"),
            discord.SelectOption(label="🧾 Pedidos recebidos", description="Ver pedidos feitos nas suas lojas", value="owner_orders"),
            discord.SelectOption(label="🪪 Solicitar lojista", description="Enviar formulario para virar lojista", value="seller_apply"),
        ]
        super().__init__(placeholder="Escolha o que voce quer abrir...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        choice = self.values[0]
        if choice == "shops":
            shops = store_db.list_shops(guild_id)
            await interaction.response.edit_message(embed=build_shop_browser_embed(shops), view=ShopBrowserView(interaction.user.id, shops))
            return
        if choice == "my_orders":
            orders = store_db.list_orders_for_buyer(guild_id, interaction.user.id)
            await interaction.response.edit_message(
                embed=build_orders_embed("Minhas compras", "Acompanhe seus pedidos, tickets e próximos passos em um só lugar.", orders, False),
                view=OrdersView(interaction.user.id, owner_view=False),
            )
            return
        if choice == "manage_shops":
            shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
            await interaction.response.edit_message(
                embed=build_owner_shop_embed(shops),
                view=OwnerShopBrowserView(interaction.user.id, shops),
            )
            return
        if choice == "seller_apply":
            if isinstance(interaction.user, discord.Member) and member_is_lojista(interaction.user):
                await interaction.response.send_message(f"Voce ja possui o cargo `{LOJISTA_ROLE_NAME}`.", ephemeral=True)
                return
            await interaction.response.send_modal(SellerApplicationModal())
            return
        orders = store_db.list_orders_for_owner(guild_id, interaction.user.id)
        await interaction.response.edit_message(
            embed=build_orders_embed("Pedidos recebidos", "Veja os atendimentos que chegaram nas suas lojas.", orders, True),
            view=OrdersView(interaction.user.id, owner_view=True),
        )


class HomeRefreshButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Atualizar visão", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=build_home_panel_embed(guild_only_interaction(interaction), interaction.user.id),
            view=HomePanelView(interaction.user.id),
        )


class HomePanelView(BasePanelView):
    def __init__(self, viewer_id: int) -> None:
        super().__init__(viewer_id)
        self.add_item(discord.ui.Button(label="<-", style=discord.ButtonStyle.secondary, disabled=True, row=0))
        self.add_item(HeaderButton("Marketplace"))
        self.add_item(HomeActionSelect())
        self.add_item(HomeRefreshButton())


class BackToHomeButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Voltar", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=build_home_panel_embed(guild_only_interaction(interaction), interaction.user.id),
            view=HomePanelView(interaction.user.id),
        )


class ShopSelect(discord.ui.Select):
    def __init__(self, shops: list[sqlite3.Row]) -> None:
        options = [
            discord.SelectOption(
                label=truncate_text(row_shop_title(shop), 100),
                description=truncate_text(f"{shop['product_count']} produto(s) | {shop['description'] or 'Sem descricao'}", 100),
                value=str(shop["id"]),
            )
            for shop in shops[:25]
        ] or [discord.SelectOption(label="Nenhuma loja", description="Cadastre uma loja primeiro", value="0")]
        super().__init__(placeholder="Escolha a vitrine que voce quer abrir...", min_values=1, max_values=1, options=options, disabled=not shops, row=1)

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shop = store_db.get_shop(guild_id, int(self.values[0]))
        if shop is None:
            await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.edit_message(
            embed=build_shop_catalog_embed(shop, products, 0, "Todos"),
            view=ShopDetailView(interaction.user.id, shop, products, "Todos", 0),
        )


class ShopBrowserRefreshButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Atualizar vitrines", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        shops = store_db.list_shops(guild_only_interaction(interaction))
        await interaction.response.edit_message(embed=build_shop_card_embed(shops, 0), view=ShopBrowserView(interaction.user.id, shops, 0))


class ShopBrowserView(BasePanelView):
    def __init__(self, viewer_id: int, shops: list[sqlite3.Row], index: int = 0) -> None:
        super().__init__(viewer_id)
        self.index = index
        self.shops = shops
        self.add_item(BackToHomeButton())
        self.add_item(HeaderButton("Explorar vitrines"))
        self.add_item(ShopSelect(shops))
        self.add_item(ShopPageButton("prev", disabled=index <= 0))
        self.add_item(ShopPageButton("next", disabled=index >= len(shops) - 1))
        self.add_item(ShopBrowserRefreshButton())


class ShopPageButton(discord.ui.Button):
    def __init__(self, direction: str, disabled: bool) -> None:
        label = "Loja anterior" if direction == "prev" else "Próxima loja"
        super().__init__(label=label, style=discord.ButtonStyle.secondary, row=2, disabled=disabled)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shops = store_db.list_shops(guild_id)
        if not shops:
            await interaction.response.edit_message(embed=build_shop_browser_embed([]), view=ShopBrowserView(interaction.user.id, [], 0))
            return
        current_view = interaction.message.components
        del current_view
        current_index = 0
        if isinstance(self.view, ShopBrowserView):
            current_index = self.view.index
        next_index = max(0, current_index - 1) if self.direction == "prev" else min(len(shops) - 1, current_index + 1)
        await interaction.response.edit_message(
            embed=build_shop_card_embed(shops, next_index),
            view=ShopBrowserView(interaction.user.id, shops, next_index),
        )


class ProductSelect(discord.ui.Select):
    def __init__(self, shop: Shop, products: list[sqlite3.Row], category: str, page: int) -> None:
        filtered_products = filter_products_by_category(products, category if category != "Todos" else None)
        page_products, _ = paginate_products(filtered_products, page)
        options = [
            discord.SelectOption(
                label=truncate_text(str(product["name"]), 100),
                description=truncate_text(f"{product['category']} | {format_price(int(product['price_cents']))}", 100),
                value=str(product["id"]),
            )
            for product in page_products[:25]
        ] or [discord.SelectOption(label="Sem produtos", description="Nada para comprar aqui", value="0")]
        max_values = min(5, len(options)) if page_products else 1
        super().__init__(placeholder="Escolha um ou mais produtos para abrir o pedido...", min_values=1, max_values=max_values, options=options, disabled=not products, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        selected_products: list[sqlite3.Row] = []
        for value in self.values:
            product = store_db.get_product(guild_id, int(value))
            if product is None:
                await interaction.response.send_message("Um dos produtos nao esta mais disponivel.", ephemeral=True)
                return
            selected_products.append(product)
        if not selected_products:
            await interaction.response.send_message("Nenhum produto valido foi selecionado.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=build_product_preview_embed(self.shop, selected_products),
            view=ProductPurchaseView(interaction.user.id, self.shop, selected_products),
            ephemeral=True,
        )


class OpenPurchaseButton(discord.ui.Button):
    def __init__(self, shop: Shop, products: list[sqlite3.Row]) -> None:
        super().__init__(
            label=shop_buy_button_text(shop),
            style=discord.ButtonStyle.success,
            disabled=not shop.is_open,
        )
        self.shop = shop
        self.products = products

    async def callback(self, interaction: discord.Interaction) -> None:
        if not self.shop.is_open:
            await interaction.response.send_message("Esta loja esta fechada no momento.", ephemeral=True)
            return
        if self.shop.terms_text:
            await interaction.response.send_message(
                f"**Termos da loja**\n\n{self.shop.terms_text}",
                ephemeral=True,
                view=TermsAcceptanceView(self.shop, self.products, interaction.user.id),
            )
            return
        await interaction.response.send_modal(PurchaseModal(self.shop, self.products, accepted_terms_text=None))


class ViewTermsButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Ver termos", style=discord.ButtonStyle.secondary, disabled=not bool(shop.terms_text))
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"**Termos da loja {shop_title(self.shop.name, self.shop.shop_emoji)}**\n\n{self.shop.terms_text}",
            ephemeral=True,
        )


class ProductPurchaseView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, products: list[sqlite3.Row]) -> None:
        super().__init__(viewer_id)
        self.products = products
        self.add_item(ViewTermsButton(shop))
        self.add_item(OpenPurchaseButton(shop, products))


class ShopDetailRefreshButton(discord.ui.Button):
    def __init__(self, shop_id: int, category: str, page: int) -> None:
        super().__init__(label="Atualizar catálogo", style=discord.ButtonStyle.secondary, row=4)
        self.shop_id = shop_id
        self.category = category
        self.page = page

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shop = store_db.get_shop(guild_id, self.shop_id)
        if shop is None:
            shops = store_db.list_shops(guild_id)
            await interaction.response.edit_message(embed=build_shop_browser_embed(shops), view=ShopBrowserView(interaction.user.id, shops))
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.edit_message(
            embed=build_shop_catalog_embed(shop, products, self.page, self.category),
            view=ShopDetailView(interaction.user.id, shop, products, self.category, self.page),
        )


class ShopDetailView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, products: list[sqlite3.Row], category: str = "Todos", page: int = 0) -> None:
        super().__init__(viewer_id)
        self.shop = shop
        self.products = products
        self.category = category
        self.page = page
        self.add_item(BackToHomeButton())
        self.add_item(HeaderButton("Catálogo da loja"))
        self.add_item(ProductCategorySelect(shop, products, category))
        self.add_item(ProductSelect(shop, products, category, page))
        self.add_item(ProductPageButton("prev", shop, products, category, page))
        self.add_item(ProductPageButton("next", shop, products, category, page))
        self.add_item(ShopDetailRefreshButton(shop.id, category, page))


class ProductCategorySelect(discord.ui.Select):
    def __init__(self, shop: Shop, products: list[sqlite3.Row], current_category: str) -> None:
        categories = sorted({str(product["category"]) for product in products}, key=str.lower)
        options = [discord.SelectOption(label="Todos", value="Todos", default=current_category == "Todos")]
        for category in categories[:24]:
            options.append(discord.SelectOption(label=truncate_text(category, 100), value=category, default=current_category == category))
        super().__init__(placeholder="Filtrar catálogo por categoria...", min_values=1, max_values=1, options=options, row=2)
        self.shop = shop
        self.products = products

    async def callback(self, interaction: discord.Interaction) -> None:
        category = self.values[0]
        await interaction.response.edit_message(
            embed=build_shop_catalog_embed(self.shop, self.products, 0, category),
            view=ShopDetailView(interaction.user.id, self.shop, self.products, category, 0),
        )


class ProductPageButton(discord.ui.Button):
    def __init__(self, direction: str, shop: Shop, products: list[sqlite3.Row], category: str, page: int) -> None:
        filtered_products = filter_products_by_category(products, category if category != "Todos" else None)
        _, total_pages = paginate_products(filtered_products, page)
        disabled = page <= 0 if direction == "prev" else page >= total_pages - 1
        super().__init__(
            label="Página anterior" if direction == "prev" else "Próxima página",
            style=discord.ButtonStyle.secondary,
            row=3,
            disabled=disabled,
        )
        self.direction = direction
        self.shop = shop
        self.products = products
        self.category = category
        self.page = page

    async def callback(self, interaction: discord.Interaction) -> None:
        next_page = max(0, self.page - 1) if self.direction == "prev" else self.page + 1
        await interaction.response.edit_message(
            embed=build_shop_catalog_embed(self.shop, self.products, next_page, self.category),
            view=ShopDetailView(interaction.user.id, self.shop, self.products, self.category, next_page),
        )


class OrdersRefreshButton(discord.ui.Button):
    def __init__(self, owner_view: bool) -> None:
        super().__init__(label="Atualizar pedidos", style=discord.ButtonStyle.secondary, row=2)
        self.owner_view = owner_view

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        orders = store_db.list_orders_for_owner(guild_id, interaction.user.id) if self.owner_view else store_db.list_orders_for_buyer(guild_id, interaction.user.id)
        await interaction.response.edit_message(
            embed=build_orders_embed(
                "Pedidos recebidos" if self.owner_view else "Minhas compras",
                "Veja os atendimentos que chegaram nas suas lojas." if self.owner_view else "Acompanhe seus tickets, status e pedidos feitos.",
                orders,
                self.owner_view,
            ),
            view=OrdersView(interaction.user.id, owner_view=self.owner_view),
        )


class OrdersView(BasePanelView):
    def __init__(self, viewer_id: int, owner_view: bool) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToHomeButton())
        self.add_item(HeaderButton("Pedidos recebidos" if owner_view else "Minhas compras"))
        self.add_item(OrdersRefreshButton(owner_view))


class OwnerShopSelect(discord.ui.Select):
    def __init__(self, shops: list[sqlite3.Row]) -> None:
        options = [
            discord.SelectOption(
                label=truncate_text(row_shop_title(shop), 100),
                description=truncate_text(f"{shop['product_count']} produto(s) | {row_theme_label(shop)}", 100),
                value=str(shop["id"]),
            )
            for shop in shops[:25]
        ] or [discord.SelectOption(label="Nenhuma loja", description="Crie sua primeira loja", value="0")]
        super().__init__(placeholder="Escolha a loja que voce quer editar...", min_values=1, max_values=1, options=options, disabled=not shops, row=1)
        self.shops = shops

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shop = store_db.get_shop(guild_id, int(self.values[0]))
        if shop is None:
            await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.edit_message(
            embed=build_shop_panel_embed(shop, products),
            view=OwnerShopManageView(interaction.user.id, shop, products),
        )


class OwnerShopRefreshButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Atualizar vitrines", style=discord.ButtonStyle.secondary, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
        await interaction.response.edit_message(
            embed=build_owner_shop_embed(shops),
            view=OwnerShopBrowserView(interaction.user.id, shops),
        )


class CreateShopButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Criar loja", style=discord.ButtonStyle.success, row=2)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(CreateShopModal())


class OwnerShopBrowserView(BasePanelView):
    def __init__(self, viewer_id: int, shops: list[sqlite3.Row]) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToHomeButton())
        self.add_item(HeaderButton("Gerenciar Lojas"))
        self.add_item(OwnerShopSelect(shops))
        self.add_item(CreateShopButton())
        self.add_item(OwnerShopRefreshButton())


class CreateShopModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Criar nova loja")
        self.name_input = discord.ui.TextInput(label="Nome da loja", max_length=80)
        self.description_input = discord.ui.TextInput(label="Descricao", required=False, max_length=500)
        self.emoji_input = discord.ui.TextInput(label="Emoji da loja", required=False, max_length=40)
        self.headline_input = discord.ui.TextInput(label="Headline", required=False, max_length=80)
        self.color_input = discord.ui.TextInput(label="Cor HEX", required=False, max_length=7, placeholder="#58A6FF")
        self.add_item(self.name_input)
        self.add_item(self.description_input)
        self.add_item(self.emoji_input)
        self.add_item(self.headline_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        ensure_lojista_member(interaction)
        name = str(self.name_input).strip()[:80]
        if not name:
            await interaction.response.send_message("Informe o nome da loja.", ephemeral=True)
            return
        try:
            shop_public_id = store_db.add_shop(
                guild_id=guild_id,
                owner_id=interaction.user.id,
                name=name,
                description=str(self.description_input).strip()[:500],
                shop_emoji=parse_optional_shop_emoji(str(self.emoji_input)) if str(self.emoji_input).strip() else None,
                headline=parse_optional_short_text(str(self.headline_input), 80, "Headline") if str(self.headline_input).strip() else None,
                subtitle=None,
                accent_color=parse_hex_color(str(self.color_input)) if str(self.color_input).strip() else None,
            )
        except app_commands.AppCommandError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        except sqlite3.IntegrityError:
            await interaction.response.send_message("Ja existe uma loja sua com esse nome.", ephemeral=True)
            return
        shop = store_db.get_shop(guild_id, shop_public_id)
        if shop is None:
            await interaction.response.send_message("A loja foi criada, mas nao consegui recarrega-la.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Loja **{shop.name}** criada com sucesso.",
            embed=build_shop_panel_embed(shop, []),
            view=OwnerShopManageView(interaction.user.id, shop, []),
            ephemeral=True,
        )


class ShopTermsModal(discord.ui.Modal):
    def __init__(self, shop: Shop) -> None:
        super().__init__(title=f"Termos • {truncate_text(shop.name, 28)}")
        self.shop = shop
        self.terms_input = discord.ui.TextInput(
            label="Termos da loja",
            default=shop.terms_text or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=900,
            placeholder="Escreva os termos. Digite 'remover' para limpar.",
        )
        self.add_item(self.terms_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        try:
            updated = store_db.update_shop_style(
                guild_id=guild_id,
                shop_id=self.shop.id,
                owner_id=interaction.user.id,
                description=None,
                shop_emoji=None,
                theme_name=None,
                buy_button_text=None,
                headline=None,
                subtitle=None,
                highlights=None,
                terms_text=parse_optional_multiline_text(str(self.terms_input), 900, "Termos"),
                is_open=None,
                availability_status=None,
                accent_color=None,
                image_url=None,
                banner_url=None,
            )
        except app_commands.AppCommandError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        if not updated:
            await interaction.response.send_message("Nao consegui atualizar os termos.", ephemeral=True)
            return
        shop = store_db.get_shop(guild_id, self.shop.id)
        if shop is None:
            await interaction.response.send_message("Os termos foram atualizados, mas a loja nao foi recarregada.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await sync_shop_public_panels(shop)
        await interaction.response.send_message(
            "Termos atualizados com sucesso.",
            embed=build_shop_panel_embed(shop, products),
            view=OwnerShopManageView(interaction.user.id, shop, products),
            ephemeral=True,
        )


class ShopStatusModal(discord.ui.Modal):
    def __init__(self, shop: Shop) -> None:
        super().__init__(title=f"Status • {truncate_text(shop.name, 28)}")
        self.shop = shop
        self.open_input = discord.ui.TextInput(
            label="Loja aberta?",
            default="sim" if shop.is_open else "nao",
            placeholder="sim ou nao",
            max_length=3,
        )
        self.status_input = discord.ui.TextInput(
            label="Disponibilidade",
            default=shop.availability_status,
            placeholder="disponivel, ocupado, ausente ou fechado",
            max_length=15,
        )
        self.add_item(self.open_input)
        self.add_item(self.status_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        open_value = str(self.open_input).strip().lower()
        if open_value not in {"sim", "nao"}:
            await interaction.response.send_message("Use `sim` ou `nao` no campo de loja aberta.", ephemeral=True)
            return
        try:
            updated = store_db.update_shop_style(
                guild_id=guild_id,
                shop_id=self.shop.id,
                owner_id=interaction.user.id,
                description=None,
                shop_emoji=None,
                theme_name=None,
                buy_button_text=None,
                headline=None,
                subtitle=None,
                highlights=None,
                terms_text=None,
                is_open=open_value == "sim",
                availability_status=normalize_availability_status(str(self.status_input)),
                accent_color=None,
                image_url=None,
                banner_url=None,
            )
        except app_commands.AppCommandError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        if not updated:
            await interaction.response.send_message("Nao consegui atualizar o status da loja.", ephemeral=True)
            return
        shop = store_db.get_shop(guild_id, self.shop.id)
        if shop is None:
            await interaction.response.send_message("O status foi atualizado, mas a loja nao foi recarregada.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await sync_shop_public_panels(shop)
        await interaction.response.send_message(
            f"Status atualizado para **{shop_status_text(shop)}**.",
            embed=build_shop_panel_embed(shop, products),
            view=OwnerShopManageView(interaction.user.id, shop, products),
            ephemeral=True,
        )


class ThemePresetSelect(discord.ui.Select):
    def __init__(self, shop: Shop) -> None:
        options = [
            discord.SelectOption(label="Booster", value="booster"),
            discord.SelectOption(label="Dark Red", value="dark_red"),
            discord.SelectOption(label="Gold", value="gold"),
            discord.SelectOption(label="Neon Blue", value="neon_blue"),
        ]
        super().__init__(placeholder="Escolha um tema visual", min_values=1, max_values=1, options=options)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        preset_key = self.values[0]
        updates = apply_theme_preset_to_shop(self.shop, preset_key)
        store_db.update_shop_style(
            guild_id=guild_id,
            shop_id=self.shop.id,
            owner_id=interaction.user.id,
            description=None,
            shop_emoji=updates.get("shop_emoji"),
            theme_name=updates["theme_name"],
            buy_button_text=None,
            headline=updates.get("headline"),
            subtitle=updates.get("subtitle"),
            highlights=None,
            terms_text=None,
            is_open=None,
            availability_status=None,
            accent_color=updates["accent_color"],
            image_url=None,
            banner_url=None,
        )
        shop = store_db.get_shop(guild_id, self.shop.id)
        if shop is None:
            await interaction.response.send_message("Tema aplicado, mas nao consegui recarregar a loja.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await sync_shop_public_panels(shop)
        await interaction.response.edit_message(
            content=f"Tema **{updates['theme_name']}** aplicado com sucesso.",
            embed=build_shop_panel_embed(shop, products),
            view=OwnerShopManageView(interaction.user.id, shop, products),
        )


class ThemePresetView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop) -> None:
        super().__init__(viewer_id)
        self.add_item(ThemePresetSelect(shop))


class ShopHistoryOrderSelect(discord.ui.Select):
    def __init__(self, shop: Shop, orders: list[sqlite3.Row], selected_order_id: Optional[int]) -> None:
        options = []
        for order in orders[:25]:
            options.append(
                discord.SelectOption(
                    label=truncate_text(f"Pedido #{order['id']} • {order['buyer_id']}", 100),
                    description=truncate_text(f"{format_status(str(order['status']))} • {order['item_summary']}", 100),
                    value=str(order["db_id"]),
                    default=selected_order_id is not None and int(order["db_id"]) == selected_order_id,
                )
            )
        if not options:
            options = [discord.SelectOption(label="Sem pedidos", description="Nenhum pedido para listar", value="0")]
        super().__init__(placeholder="Selecione um pedido da loja", min_values=1, max_values=1, options=options, disabled=not orders, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        orders = store_db.list_shop_orders_for_owner(guild_id, self.shop.id, interaction.user.id)
        selected_order_id = int(self.values[0])
        await interaction.response.edit_message(
            embed=build_shop_history_embed(self.shop, orders, selected_order_id),
            view=OwnerShopHistoryView(interaction.user.id, self.shop, orders, selected_order_id),
        )


class OpenOrderLogsButton(discord.ui.Button):
    def __init__(self, selected_order_id: Optional[int]) -> None:
        super().__init__(label="Ver logs", style=discord.ButtonStyle.secondary, row=2, disabled=selected_order_id is None)
        self.selected_order_id = selected_order_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.selected_order_id is None:
            await interaction.response.send_message("Selecione um pedido primeiro.", ephemeral=True)
            return
        order = store_db.get_order_details(self.selected_order_id)
        if order is None:
            await interaction.response.send_message("Pedido nao encontrado.", ephemeral=True)
            return
        logs = store_db.list_order_logs(self.selected_order_id, limit=25)
        await interaction.response.send_message(embed=build_order_logs_embed(order, logs), ephemeral=True)


class ShopHistoryRefreshButton(discord.ui.Button):
    def __init__(self, shop: Shop, selected_order_id: Optional[int]) -> None:
        super().__init__(label="Atualizar historico", style=discord.ButtonStyle.secondary, row=2)
        self.shop = shop
        self.selected_order_id = selected_order_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        orders = store_db.list_shop_orders_for_owner(guild_id, self.shop.id, interaction.user.id)
        await interaction.response.edit_message(
            embed=build_shop_history_embed(self.shop, orders, self.selected_order_id),
            view=OwnerShopHistoryView(interaction.user.id, self.shop, orders, self.selected_order_id),
        )


class OwnerShopHistoryView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, orders: list[sqlite3.Row], selected_order_id: Optional[int] = None) -> None:
        super().__init__(viewer_id)
        self.shop = shop
        self.orders = orders
        if selected_order_id is None and orders:
            selected_order_id = int(orders[0]["db_id"])
        self.selected_order_id = selected_order_id
        self.add_item(BackToOwnerShopManageButton(shop))
        self.add_item(HeaderButton("Historico da loja"))
        self.add_item(ShopHistoryOrderSelect(shop, orders, self.selected_order_id))
        self.add_item(OpenOrderLogsButton(self.selected_order_id))
        self.add_item(ShopHistoryRefreshButton(shop, self.selected_order_id))


class EditorStatsRefreshButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Atualizar estatisticas", style=discord.ButtonStyle.secondary, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        stats = store_db.get_editor_stats(guild_id, self.shop.owner_id)
        recent_ratings = store_db.list_recent_editor_ratings(self.shop.owner_id, limit=3)
        await interaction.response.edit_message(
            embed=build_editor_stats_embed(self.shop, stats, recent_ratings),
            view=EditorStatsView(interaction.user.id, self.shop),
        )


class EditorStatsView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToOwnerShopManageButton(shop))
        self.add_item(HeaderButton("Estatisticas"))
        self.add_item(EditorStatsRefreshButton(shop))


class ShopStyleModal(discord.ui.Modal):
    def __init__(self, shop: Shop) -> None:
        super().__init__(title=f"Personalizar {truncate_text(shop.name, 28)}")
        self.shop = shop
        self.emoji_input = discord.ui.TextInput(
            label="Emoji ou enfeite",
            default=shop.shop_emoji or "",
            required=False,
            placeholder="Ex: ✨, 🛍️, <:booster:1234567890> ou remover",
            max_length=40,
        )
        self.description_input = discord.ui.TextInput(
            label="Descricao",
            default=shop.description or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.color_input = discord.ui.TextInput(
            label="Cor HEX",
            default=shop.accent_color or "",
            required=False,
            placeholder="#58A6FF ou remover",
            max_length=20,
        )
        self.logo_input = discord.ui.TextInput(
            label="Logo URL",
            default=shop.image_url or "",
            required=False,
            placeholder="https://... ou remover",
            max_length=300,
        )
        self.banner_input = discord.ui.TextInput(
            label="Banner URL",
            default=shop.banner_url or "",
            required=False,
            placeholder="https://... ou remover",
            max_length=300,
        )
        self.add_item(self.emoji_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.logo_input)
        self.add_item(self.banner_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        emoji_raw = str(self.emoji_input).strip()
        color_raw = str(self.color_input).strip()
        logo_raw = str(self.logo_input).strip()
        banner_raw = str(self.banner_input).strip()
        description_raw = str(self.description_input).strip()

        emoji_value = None if emoji_raw == "" else parse_optional_shop_emoji(emoji_raw)
        theme_name_value = None
        color_value = None if color_raw == "" else ("" if color_raw.lower() in {"remover", "none", "nenhum"} else parse_hex_color(color_raw))
        if color_raw != "":
            theme_name_value = ""
        image_value = None if logo_raw == "" else parse_optional_image_url(logo_raw)
        banner_value = None if banner_raw == "" else parse_optional_image_url(banner_raw)
        description_value = description_raw[:500]

        store_db.update_shop_style(
            guild_id=guild_id,
            shop_id=self.shop.id,
            owner_id=interaction.user.id,
            description=description_value,
            shop_emoji=emoji_value,
            theme_name=theme_name_value,
            buy_button_text=None,
            headline=None,
            subtitle=None,
            highlights=None,
            terms_text=None,
            is_open=None,
            availability_status=None,
            accent_color=color_value,
            image_url=image_value,
            banner_url=banner_value,
        )
        updated_shop = store_db.get_shop(guild_id, self.shop.id)
        if updated_shop is None:
            await interaction.response.send_message("Nao consegui atualizar a vitrine.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, updated_shop.id)
        await interaction.response.send_message(
            "Visual da loja atualizado.",
            embed=build_shop_panel_embed(updated_shop, products),
            ephemeral=True,
        )
        await sync_shop_public_panels(updated_shop)


class ShopBioModal(discord.ui.Modal):
    def __init__(self, shop: Shop) -> None:
        super().__init__(title=f"Bio visual • {truncate_text(shop.name, 24)}")
        self.shop = shop
        self.headline_input = discord.ui.TextInput(
            label="Headline",
            default=shop.headline or "",
            required=False,
            placeholder="Frase principal da sua vitrine",
            max_length=80,
        )
        self.subtitle_input = discord.ui.TextInput(
            label="Subtitulo",
            default=shop.subtitle or "",
            required=False,
            placeholder="Complemento curto para reforcar a proposta",
            max_length=120,
        )
        self.highlights_input = discord.ui.TextInput(
            label="Vantagens",
            default=shop.highlights or "",
            required=False,
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Entrega rapida | Revisao inclusa | Atendimento no ticket",
            max_length=300,
        )
        self.button_text_input = discord.ui.TextInput(
            label="Texto do botao de compra",
            default=shop.buy_button_text or "",
            required=False,
            placeholder="Ex: 🚀 Quero esse agora ou remover",
            max_length=80,
        )
        self.add_item(self.headline_input)
        self.add_item(self.subtitle_input)
        self.add_item(self.highlights_input)
        self.add_item(self.button_text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        updated = store_db.update_shop_style(
            guild_id=guild_id,
            shop_id=self.shop.id,
            owner_id=interaction.user.id,
            description=None,
            shop_emoji=None,
            theme_name=None,
            buy_button_text=None if str(self.button_text_input).strip() == "" else parse_optional_short_text(str(self.button_text_input), 80, "Texto do botao"),
            headline=None if str(self.headline_input).strip() == "" else parse_optional_short_text(str(self.headline_input), 80, "Headline"),
            subtitle=None if str(self.subtitle_input).strip() == "" else parse_optional_short_text(str(self.subtitle_input), 120, "Subtitulo"),
            highlights=None if str(self.highlights_input).strip() == "" else parse_optional_multiline_text(str(self.highlights_input), 300, "Vantagens"),
            terms_text=None,
            is_open=None,
            availability_status=None,
            accent_color=None,
            image_url=None,
            banner_url=None,
        )
        if not updated:
            await interaction.response.send_message("Nada foi alterado na bio visual.", ephemeral=True)
            return
        updated_shop = store_db.get_shop(guild_id, self.shop.id)
        if updated_shop is None:
            await interaction.response.send_message("Nao consegui recarregar a loja.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, updated_shop.id)
        await interaction.response.send_message(
            "Bio visual atualizada.",
            embed=build_shop_panel_embed(updated_shop, products),
            ephemeral=True,
        )
        await sync_shop_public_panels(updated_shop)


class ProductCreateModal(discord.ui.Modal):
    def __init__(self, shop: Shop) -> None:
        super().__init__(title=f"Novo produto • {truncate_text(shop.name, 25)}")
        self.shop = shop
        self.name_input = discord.ui.TextInput(label="Nome", max_length=80)
        self.category_input = discord.ui.TextInput(label="Categoria", default="Geral", max_length=40, required=False)
        self.price_input = discord.ui.TextInput(label="Preco", placeholder="25,50", max_length=20)
        self.description_input = discord.ui.TextInput(label="Descricao", required=False, style=discord.TextStyle.paragraph, max_length=500)
        self.add_item(self.name_input)
        self.add_item(self.category_input)
        self.add_item(self.price_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shop = store_db.get_shop(guild_id, self.shop.id)
        if shop is None or shop.owner_id != interaction.user.id:
            await interaction.response.send_message("Voce nao pode adicionar produtos nessa loja.", ephemeral=True)
            return
        category = normalize_category(str(self.category_input))
        price_cents = parse_price_to_cents(str(self.price_input))
        try:
            product_id = store_db.add_product(
                shop_id=shop.db_id,
                name=str(self.name_input)[:80],
                category=category,
                price_cents=price_cents,
                description=str(self.description_input)[:500],
            )
        except sqlite3.IntegrityError:
            await interaction.response.send_message("Ja existe um produto com esse nome nessa loja.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.send_message(
            f"Produto criado com sucesso. ID: `{product_id}`.",
            embed=build_shop_catalog_embed(shop, products, 0, "Todos"),
            ephemeral=True,
        )
        await sync_shop_public_panels(shop)


class ProductEditModal(discord.ui.Modal):
    def __init__(self, shop: Shop, product: sqlite3.Row) -> None:
        super().__init__(title=f"Editar • {truncate_text(str(product['name']), 28)}")
        self.shop = shop
        self.product = product
        self.name_input = discord.ui.TextInput(label="Nome", default=str(product["name"]), max_length=80)
        self.category_input = discord.ui.TextInput(label="Categoria", default=str(product["category"]), max_length=40, required=False)
        self.price_input = discord.ui.TextInput(
            label="Preco",
            default=format_price(int(product["price_cents"])).replace("R$ ", ""),
            max_length=20,
        )
        self.description_input = discord.ui.TextInput(
            label="Descricao",
            default=str(product["description"] or ""),
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.add_item(self.name_input)
        self.add_item(self.category_input)
        self.add_item(self.price_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        updated = store_db.update_product(
            guild_id=guild_id,
            product_id=int(self.product["id"]),
            owner_id=interaction.user.id,
            name=str(self.name_input)[:80],
            category=normalize_category(str(self.category_input)),
            price_cents=parse_price_to_cents(str(self.price_input)),
            description=str(self.description_input)[:500],
        )
        if not updated:
            await interaction.response.send_message("Nao consegui atualizar esse produto.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, self.shop.id)
        refreshed = store_db.get_product(guild_id, int(self.product["id"]))
        selected_id = int(refreshed["id"]) if refreshed is not None else None
        await interaction.response.send_message(
            "Produto atualizado com sucesso.",
            embed=build_owner_product_embed(self.shop, products, selected_id),
            view=OwnerProductManageView(interaction.user.id, self.shop, products, selected_id),
            ephemeral=True,
        )
        await sync_shop_public_panels(self.shop)


class DeleteProductConfirmView(discord.ui.View):
    def __init__(self, owner_id: int, shop: Shop, product_id: int) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.shop = shop
        self.product_id = product_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente o dono pode confirmar essa exclusao.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar exclusao", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        guild_id = guild_only_interaction(interaction)
        product_has_history = store_db.product_has_orders(guild_id, self.product_id, interaction.user.id)
        deleted = store_db.delete_product(guild_id, self.product_id, interaction.user.id)
        if not deleted:
            await interaction.response.send_message("Nao consegui excluir esse produto.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, self.shop.id)
        await interaction.response.edit_message(
            content="Produto ocultado do catalogo para preservar o historico dos pedidos." if product_has_history else "Produto excluido com sucesso.",
            embed=build_owner_product_embed(self.shop, products),
            view=OwnerProductManageView(interaction.user.id, self.shop, products),
        )
        await sync_shop_public_panels(self.shop)


class DeleteShopConfirmView(discord.ui.View):
    def __init__(self, owner_id: int, shop: Shop) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.shop = shop

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente o dono pode confirmar essa exclusao.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar exclusao", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        guild_id = guild_only_interaction(interaction)
        publications = store_db.list_shop_publications(self.shop.db_id)
        deleted = store_db.delete_shop(guild_id, self.shop.id, interaction.user.id)
        if not deleted:
            if store_db.shop_has_orders(guild_id, self.shop.id, interaction.user.id):
                await interaction.response.send_message("Nao e possivel excluir a loja porque ela possui historico de pedidos.", ephemeral=True)
            else:
                await interaction.response.send_message("Nao consegui excluir a loja.", ephemeral=True)
            return
        await delete_shop_public_messages(publications)
        shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
        await interaction.response.edit_message(
            content="Loja excluida com sucesso.",
            embed=build_owner_shop_embed(shops),
            view=OwnerShopBrowserView(interaction.user.id, shops),
        )


class OpenCustomizeButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Personalizar visual", style=discord.ButtonStyle.primary, row=2)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ShopStyleModal(self.shop))


class OpenBioButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Ajustar vitrine", style=discord.ButtonStyle.primary, row=3)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ShopBioModal(self.shop))


class OpenStatusModalButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Status da loja", style=discord.ButtonStyle.secondary, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ShopStatusModal(self.shop))


class OpenTermsModalButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Termos da loja", style=discord.ButtonStyle.secondary, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ShopTermsModal(self.shop))


class OpenThemePickerButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Tema visual", style=discord.ButtonStyle.secondary, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Escolha um preset visual para a sua loja.",
            embed=build_shop_panel_embed(self.shop, store_db.list_products(guild_only_interaction(interaction), self.shop.id)),
            view=ThemePresetView(interaction.user.id, self.shop),
            ephemeral=True,
        )


class OpenProductModalButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Novo serviço", style=discord.ButtonStyle.success, row=2)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(ProductCreateModal(self.shop))


class OpenManageProductsButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Gerenciar catálogo", style=discord.ButtonStyle.secondary, row=2)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        products = store_db.list_products(guild_id, self.shop.id)
        await interaction.response.edit_message(
            embed=build_owner_product_embed(self.shop, products),
            view=OwnerProductManageView(interaction.user.id, self.shop, products),
        )


class DeleteShopButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Excluir vitrine", style=discord.ButtonStyle.danger, row=3)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Tem certeza que deseja excluir **{self.shop.name}**? Lojas com historico de pedidos nao podem ser excluidas.",
            view=DeleteShopConfirmView(interaction.user.id, self.shop),
            ephemeral=True,
        )


class BackToOwnerShopsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Voltar", style=discord.ButtonStyle.secondary, row=0)

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
        await interaction.response.edit_message(
            embed=build_owner_shop_embed(shops),
            view=OwnerShopBrowserView(interaction.user.id, shops),
        )


class BackToOwnerShopManageButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Voltar", style=discord.ButtonStyle.secondary, row=0)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        shop = store_db.get_shop(guild_id, self.shop.id)
        if shop is None:
            await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.edit_message(
            embed=build_shop_panel_embed(shop, products),
            view=OwnerShopManageView(interaction.user.id, shop, products),
        )


class OwnerProductSelect(discord.ui.Select):
    def __init__(self, products: list[sqlite3.Row], selected_product_id: Optional[int]) -> None:
        options = []
        for product in products[:25]:
            options.append(
                discord.SelectOption(
                    label=truncate_text(str(product["name"]), 100),
                    description=truncate_text(f"{product['category']} • {format_price(int(product['price_cents']))}", 100),
                    value=str(product["id"]),
                    default=selected_product_id is not None and int(product["id"]) == selected_product_id,
                )
            )
        if not options:
            options = [discord.SelectOption(label="Sem produtos", description="Adicione um item primeiro", value="0")]
        super().__init__(placeholder="Selecione um serviço da vitrine...", min_values=1, max_values=1, options=options, disabled=not products, row=1)
        self.products = products

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, OwnerProductManageView):
            await interaction.response.send_message("Painel de itens indisponivel.", ephemeral=True)
            return
        selected_id = int(self.values[0])
        await interaction.response.edit_message(
            embed=build_owner_product_embed(self.view.shop, self.view.products, selected_id),
            view=OwnerProductManageView(interaction.user.id, self.view.shop, self.view.products, selected_id),
        )


class EditSelectedProductButton(discord.ui.Button):
    def __init__(self, shop: Shop, products: list[sqlite3.Row], selected_product_id: Optional[int]) -> None:
        super().__init__(label="Editar serviço", style=discord.ButtonStyle.primary, row=2, disabled=selected_product_id is None)
        self.shop = shop
        self.products = products
        self.selected_product_id = selected_product_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.selected_product_id is None:
            await interaction.response.send_message("Selecione um produto primeiro.", ephemeral=True)
            return
        product = next((row for row in self.products if int(row["id"]) == self.selected_product_id), None)
        if product is None:
            await interaction.response.send_message("Produto nao encontrado.", ephemeral=True)
            return
        await interaction.response.send_modal(ProductEditModal(self.shop, product))


class DeleteSelectedProductButton(discord.ui.Button):
    def __init__(self, shop: Shop, selected_product_id: Optional[int]) -> None:
        super().__init__(label="Excluir serviço", style=discord.ButtonStyle.danger, row=2, disabled=selected_product_id is None)
        self.shop = shop
        self.selected_product_id = selected_product_id

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.selected_product_id is None:
            await interaction.response.send_message("Selecione um produto primeiro.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Confirma a exclusao desse item da loja?",
            view=DeleteProductConfirmView(interaction.user.id, self.shop, self.selected_product_id),
            ephemeral=True,
        )


class OwnerProductRefreshButton(discord.ui.Button):
    def __init__(self, shop: Shop, selected_product_id: Optional[int]) -> None:
        super().__init__(label="Atualizar painel", style=discord.ButtonStyle.secondary, row=3)
        self.shop = shop
        self.selected_product_id = selected_product_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        products = store_db.list_products(guild_id, self.shop.id)
        await interaction.response.edit_message(
            embed=build_owner_product_embed(self.shop, products, self.selected_product_id),
            view=OwnerProductManageView(interaction.user.id, self.shop, products, self.selected_product_id),
        )


class OwnerProductManageView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, products: list[sqlite3.Row], selected_product_id: Optional[int] = None) -> None:
        super().__init__(viewer_id)
        self.shop = shop
        self.products = products
        if selected_product_id is None and products:
            selected_product_id = int(products[0]["id"])
        self.selected_product_id = selected_product_id
        self.add_item(BackToOwnerShopManageButton(shop))
        self.add_item(HeaderButton("Catálogo"))
        self.add_item(OwnerProductSelect(products, self.selected_product_id))
        self.add_item(EditSelectedProductButton(shop, products, self.selected_product_id))
        self.add_item(DeleteSelectedProductButton(shop, self.selected_product_id))
        self.add_item(OpenProductModalButton(shop))
        self.add_item(OwnerProductRefreshButton(shop, self.selected_product_id))


class PublishShopButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Divulgar loja", style=discord.ButtonStyle.secondary, row=3)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Escolha o canal para publicar o painel publico da loja.",
            ephemeral=True,
            view=PublishShopView(interaction.user.id, self.shop),
        )


class OpenShopHistoryButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Historico", style=discord.ButtonStyle.secondary, row=3)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        orders = store_db.list_shop_orders_for_owner(guild_id, self.shop.id, interaction.user.id)
        await interaction.response.send_message(
            embed=build_shop_history_embed(self.shop, orders),
            view=OwnerShopHistoryView(interaction.user.id, self.shop, orders),
            ephemeral=True,
        )


class OpenEditorStatsButton(discord.ui.Button):
    def __init__(self, shop: Shop) -> None:
        super().__init__(label="Estatisticas", style=discord.ButtonStyle.secondary, row=3)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        stats = store_db.get_editor_stats(guild_id, self.shop.owner_id)
        recent_ratings = store_db.list_recent_editor_ratings(self.shop.owner_id, limit=3)
        await interaction.response.send_message(
            embed=build_editor_stats_embed(self.shop, stats, recent_ratings),
            view=EditorStatsView(interaction.user.id, self.shop),
            ephemeral=True,
        )


class OwnerShopManageView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, products: list[sqlite3.Row]) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToOwnerShopsButton())
        self.add_item(HeaderButton("Gestao da loja"))
        self.add_item(OpenStatusModalButton(shop))
        self.add_item(OpenTermsModalButton(shop))
        self.add_item(OpenThemePickerButton(shop))
        self.add_item(OpenCustomizeButton(shop))
        self.add_item(OpenProductModalButton(shop))
        self.add_item(OpenManageProductsButton(shop))
        self.add_item(OpenBioButton(shop))
        self.add_item(OpenShopHistoryButton(shop))
        self.add_item(OpenEditorStatsButton(shop))
        self.add_item(PublishShopButton(shop))
        self.add_item(DeleteShopButton(shop))
        self.add_item(ShopDetailRefreshButton(shop.id, "Todos", 0))


class TermsAcceptanceButton(discord.ui.Button):
    def __init__(self, shop: Shop, products: list[sqlite3.Row]) -> None:
        super().__init__(label="Aceitar e continuar", style=discord.ButtonStyle.success)
        self.shop = shop
        self.products = products

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        if self.shop.terms_text:
            store_db.record_term_acceptance(guild_id, self.shop.db_id, interaction.user.id, self.shop.terms_text)
        await interaction.response.send_modal(PurchaseModal(self.shop, self.products, accepted_terms_text=self.shop.terms_text))


class TermsAcceptanceView(BasePanelView):
    def __init__(self, shop: Shop, products: list[sqlite3.Row], viewer_id: int) -> None:
        super().__init__(viewer_id)
        self.add_item(TermsAcceptanceButton(shop, products))


class PurchaseModal(discord.ui.Modal):
    def __init__(self, shop: Shop, products: list[sqlite3.Row], accepted_terms_text: Optional[str]) -> None:
        title_target = str(products[0]["name"]) if len(products) == 1 else f"{len(products)} itens"
        super().__init__(title=f"Comprar {truncate_text(title_target, 35)}")
        self.shop = shop
        self.products = products
        self.accepted_terms_text = accepted_terms_text

        default_quantity = "1" if len(products) == 1 else ", ".join(f"{int(product['id'])}=1" for product in products)
        quantity_label = "Quantidade" if len(products) == 1 else "Quantidades por item"
        quantity_placeholder = "Ex: 1" if len(products) == 1 else "Ex: 12=1, 14=2, 18=1"
        self.quantity = discord.ui.TextInput(label=quantity_label, placeholder=quantity_placeholder, default=default_quantity, max_length=120)
        self.details = discord.ui.TextInput(
            label="Briefing do pedido",
            placeholder="Explique o que voce precisa, prazo, referencias e observacoes...",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=400,
        )
        self.add_item(self.quantity)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        item_map = {int(product["id"]): product for product in self.products}
        items: list[dict[str, int]] = []
        if len(self.products) == 1:
            try:
                quantity = int(str(self.quantity).strip())
            except ValueError:
                await interaction.response.send_message("Digite uma quantidade valida.", ephemeral=True)
                return
            if quantity <= 0 or quantity > 99:
                await interaction.response.send_message("A quantidade precisa ficar entre 1 e 99.", ephemeral=True)
                return
            product = self.products[0]
            items.append(
                {
                    "product_id": int(product["id"]),
                    "quantity": quantity,
                    "unit_price_cents": int(product["price_cents"]),
                    "line_total_cents": int(product["price_cents"]) * quantity,
                }
            )
        else:
            raw_pairs = [part.strip() for part in str(self.quantity).split(",") if part.strip()]
            if not raw_pairs:
                await interaction.response.send_message("Informe as quantidades no formato `ID=quantidade`.", ephemeral=True)
                return
            seen_ids: set[int] = set()
            for pair in raw_pairs:
                if "=" not in pair:
                    await interaction.response.send_message("Use o formato `ID=quantidade`, separado por virgulas.", ephemeral=True)
                    return
                product_id_raw, quantity_raw = pair.split("=", 1)
                try:
                    product_id = int(product_id_raw.strip())
                    quantity = int(quantity_raw.strip())
                except ValueError:
                    await interaction.response.send_message("Use IDs e quantidades numericos.", ephemeral=True)
                    return
                if product_id not in item_map or quantity <= 0 or quantity > 99 or product_id in seen_ids:
                    await interaction.response.send_message("Revise os IDs e quantidades informados.", ephemeral=True)
                    return
                seen_ids.add(product_id)
                product = item_map[product_id]
                items.append(
                    {
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit_price_cents": int(product["price_cents"]),
                        "line_total_cents": int(product["price_cents"]) * quantity,
                    }
                )
            if len(items) != len(self.products):
                await interaction.response.send_message("Informe uma quantidade para cada item selecionado.", ephemeral=True)
                return

        _, total_price_cents, ticket_channel = await create_order_and_ticket(
            interaction=interaction,
            shop=self.shop,
            product=self.products[0],
            quantity=items[0]["quantity"],
            details=str(self.details).strip(),
            items=items,
            accepted_terms_text=self.accepted_terms_text,
        )
        ticket_text = build_ticket_creation_notice(ticket_channel)
        await interaction.response.send_message(
            f"Atendimento aberto com sucesso por {format_price(total_price_cents)}.\nTicket: {ticket_text}",
            ephemeral=True,
        )


class RateOrderModal(discord.ui.Modal):
    def __init__(self, order: sqlite3.Row) -> None:
        super().__init__(title=f"Avaliar pedido #{order['id']}")
        self.order = order

        self.stars_input = discord.ui.TextInput(
            label="Nota de 1 a 5",
            placeholder="Ex: 5",
            max_length=1
        )

        self.comment_input = discord.ui.TextInput(
            label="Comentário",
            required=False,
            style=discord.TextStyle.paragraph,
            placeholder="Conte como foi sua experiência...",
            max_length=300,
        )

        self.add_item(self.stars_input)
        self.add_item(self.comment_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            stars = int(self.stars_input.value.strip())  # 🔥 corrigido aqui
        except ValueError:
            await interaction.response.send_message("Digite uma nota válida de 1 a 5.", ephemeral=True)
            return

        if stars < 1 or stars > 5:
            await interaction.response.send_message("A nota precisa ficar entre 1 e 5.", ephemeral=True)
            return

        comment = self.comment_input.value.strip()[:300] if self.comment_input.value else ""

        created = store_db.create_rating(
            order_id=int(self.order["db_id"]),
            guild_id=int(self.order["guild_id"]),
            shop_db_id=int(self.order["shop_id"]),
            buyer_id=int(self.order["buyer_id"]),
            seller_id=int(self.order["shop_owner_id"]),
            stars=stars,
            comment=comment,
        )

        if not created:
            await interaction.response.send_message("Esse pedido já foi avaliado.", ephemeral=True)
            return

        if FEEDBACK_CHANNEL_ID and interaction.guild:
            feedback_channel = interaction.guild.get_channel(FEEDBACK_CHANNEL_ID)
            if isinstance(feedback_channel, discord.TextChannel):
                await feedback_channel.send(
                    f"⭐ Nova avaliação para **{self.order['shop_name']}**\n"
                    f"Pedido #{self.order['id']} • {stars}/5\n"
                    f"Cliente: <@{self.order['buyer_id']}>\n"
                    f"{comment or 'Sem comentário.'}"
                )

        await interaction.response.send_message("Avaliação registrada com sucesso.", ephemeral=True)


class RateOrderButton(discord.ui.Button):
    def __init__(self, order: sqlite3.Row) -> None:
        disabled = str(order["status"]) not in {"concluido", "fechado"} or store_db.has_rating_for_order(int(order["db_id"]))
        super().__init__(label="Avaliar atendimento", style=discord.ButtonStyle.success, custom_id=f"ticket:rate:{int(order['db_id'])}", disabled=disabled)
        self.order_db_id = int(order["db_id"])

    async def callback(self, interaction: discord.Interaction) -> None:
        order = store_db.get_order_details(self.order_db_id)
        if order is None:
            await interaction.response.send_message("Pedido nao encontrado.", ephemeral=True)
            return
        if interaction.user.id != int(order["buyer_id"]):
            await interaction.response.send_message("Somente o comprador pode avaliar este pedido.", ephemeral=True)
            return
        await interaction.response.send_modal(RateOrderModal(order))


class CallCustomerButton(discord.ui.Button):
    def __init__(self, buyer_id: int) -> None:
        super().__init__(label="Chamar cliente", style=discord.ButtonStyle.secondary)
        self.buyer_id = buyer_id

    async def callback(self, interaction: discord.Interaction) -> None:
        order = store_db.get_order_details(self.view.order_id) if isinstance(self.view, TicketControlsView) else None
        if order is None or interaction.user.id != int(order["shop_owner_id"]):
            await interaction.response.send_message("Somente o lojista responsavel pode chamar o cliente.", ephemeral=True)
            return
        await interaction.response.send_message(f"<@{self.buyer_id}> sua atencao foi solicitada neste pedido.", allowed_mentions=discord.AllowedMentions(users=True))


class TranscriptButton(discord.ui.Button):
    def __init__(self, order_db_id: int) -> None:
        super().__init__(label="Ver transcript", style=discord.ButtonStyle.secondary)
        self.order_db_id = order_db_id

    async def callback(self, interaction: discord.Interaction) -> None:
        order = store_db.get_order_details(self.order_db_id)
        if order is None:
            await interaction.response.send_message("Pedido nao encontrado.", ephemeral=True)
            return
        allowed_ids = {int(order["buyer_id"]), int(order["shop_owner_id"])}
        if interaction.user.id not in allowed_ids:
            await interaction.response.send_message("Voce nao pode acessar o transcript deste pedido.", ephemeral=True)
            return
        transcript = str(order["transcript_text"] or "Nenhum transcript foi salvo ainda para este pedido.")
        if len(transcript) <= 3800:
            await interaction.response.send_message(f"```text\n{transcript}\n```", ephemeral=True)
            return
        transcript_file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"transcript-pedido-{order['id']}.txt")
        await interaction.response.send_message("Transcript completo em anexo.", file=transcript_file, ephemeral=True)


class TicketActionButton(discord.ui.Button):
    def __init__(self, order_db_id: int, action: str, label: str, style: discord.ButtonStyle, disabled: bool = False) -> None:
        custom_id = f"ticket:{action}:{order_db_id}"
        super().__init__(label=label, style=style, custom_id=custom_id, disabled=disabled)
        self.custom_id = custom_id
        self.order_id = order_db_id
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        order = store_db.get_order_details(self.order_id)
        if order is None:
            await interaction.response.send_message("Pedido nao encontrado.", ephemeral=True)
            return

        user_id = interaction.user.id
        owner_id = int(order["shop_owner_id"])
        buyer_id = int(order["buyer_id"])
        if user_id not in {owner_id, buyer_id}:
            await interaction.response.send_message("Somente cliente e vendedor podem usar estes botoes.", ephemeral=True)
            return

        if self.action in {"start", "complete", "close", "reopen"} and user_id != owner_id:
            await interaction.response.send_message("Somente o vendedor pode alterar essa etapa do atendimento.", ephemeral=True)
            return

        next_status = str(order["status"])
        notice = ""
        if self.action == "start":
            next_status = "em_andamento"
            notice = "Atendimento marcado como em andamento."
        elif self.action == "complete":
            next_status = "concluido"
            notice = "Pedido marcado como concluido. O comprador continua com acesso somente leitura ao historico."
        elif self.action == "close":
            next_status = "fechado"
            notice = "Ticket fechado. O historico continua visivel em modo leitura."
        elif self.action == "reopen":
            next_status = "pendente"
            notice = "Ticket reaberto e comprador notificado novamente."

        store_db.update_order_status(self.order_id, next_status)
        updated = store_db.get_order_details(self.order_id)
        if updated is None:
            await interaction.response.send_message("Nao foi possivel atualizar o ticket.", ephemeral=True)
            return

        if interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            channel = interaction.channel
            buyer = interaction.guild.get_member(buyer_id) if interaction.guild else None
            owner = interaction.guild.get_member(owner_id) if interaction.guild else None
            if buyer is not None and owner is not None and isinstance(channel, discord.TextChannel):
                try:
                    if next_status in {"concluido", "fechado"}:
                        await set_ticket_participants_visibility(channel, buyer, owner, buyer_visible=True, buyer_can_send=False, owner_can_send=True)
                    else:
                        await set_ticket_participants_visibility(channel, buyer, owner, buyer_visible=True, buyer_can_send=True, owner_can_send=True)
                except discord.Forbidden:
                    logger.warning("Falha ao ajustar permissoes do ticket do pedido #%s.", updated["id"])
            if next_status in {"concluido", "fechado"} and interaction.guild and isinstance(channel, discord.TextChannel):
                archive_category = resolve_ticket_archive_category(interaction.guild)
                if archive_category is not None:
                    try:
                        await channel.edit(category=archive_category, reason=f"Ticket #{updated['id']} arquivado")
                    except discord.Forbidden:
                        logger.warning("Falha ao arquivar o ticket do pedido #%s.", updated["id"])
            if next_status in {"concluido", "fechado"}:
                await persist_transcript_and_logs(interaction.guild, channel, updated, interaction.user.id, f"status_{next_status}", notice)
            else:
                store_db.create_order_log(int(updated["db_id"]), int(updated["guild_id"]), interaction.user.id, f"status_{next_status}", notice)

        await interaction.response.edit_message(
            embed=build_order_embed_from_row(updated),
            view=TicketControlsView.from_order(updated),
        )
        if self.action == "reopen" and interaction.channel and isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.channel.send(f"<@{buyer_id}> seu pedido foi reaberto e precisa da sua atencao novamente.")
        await interaction.followup.send(notice, ephemeral=True)


class TicketControlsView(discord.ui.View):
    def __init__(self, order_db_id: int, buyer_id: int, owner_id: int, status: str, order: sqlite3.Row) -> None:
        super().__init__(timeout=None)
        self.order_id = order_db_id
        self.buyer_id = buyer_id
        self.owner_id = owner_id
        self.status = status
        self.add_item(TicketActionButton(order_db_id, "start", "Em atendimento", discord.ButtonStyle.primary, disabled=status in {"em_andamento", "concluido", "fechado"}))
        self.add_item(TicketActionButton(order_db_id, "complete", "Concluir", discord.ButtonStyle.success, disabled=status in {"concluido", "fechado"}))
        self.add_item(TicketActionButton(order_db_id, "close", "Fechar ticket", discord.ButtonStyle.danger, disabled=status == "fechado"))
        self.add_item(TicketActionButton(order_db_id, "reopen", "Reabrir", discord.ButtonStyle.secondary, disabled=status != "fechado"))
        self.add_item(CallCustomerButton(buyer_id))
        self.add_item(TranscriptButton(order_db_id))
        self.add_item(RateOrderButton(order))

    @classmethod
    def from_order(cls, order: sqlite3.Row) -> "TicketControlsView":
        return cls(
            order_db_id=int(order["db_id"]),
            buyer_id=int(order["buyer_id"]),
            owner_id=int(order["shop_owner_id"]),
            status=str(order["status"]),
            order=order,
        )


def render_order_card(order: sqlite3.Row, owner_view: bool) -> str:
    lines = [
        f"• Status: {format_status(str(order['status']))}",
        f"• Total: **{format_price(int(order['total_price_cents']))}**",
        f"• Itens: {format_order_items_inline(order)}",
        f"• Ticket: {build_ticket_reference(order['ticket_channel_id'])}",
        f"• Tempo: {format_delivery_duration(order['started_at'], order['completed_at'])}",
        f"• Transcript: `{format_transcript_state(order)}`",
    ]
    if owner_view:
        lines.insert(1, f"• Cliente: <@{order['buyer_id']}>")
    else:
        lines.insert(1, f"• Loja: **{order['shop_name']}**")
    lines.append("")
    lines.append(f"Resumo: {short_order_details(str(order['details'] or ''))}")
    return "\n".join(lines)


def build_order_embed_from_row(order: sqlite3.Row) -> discord.Embed:
    meta = get_status_meta(str(order["status"]))
    embed = discord.Embed(
        title=f"Pedido #{order['id']}",
        description=f"{meta['emoji']} **{meta['label']}** • **{order['shop_name']}**",
        color=meta["color"],
    )
    embed.add_field(name="Cliente", value=f"<@{order['buyer_id']}>", inline=True)
    embed.add_field(name="Editor", value=f"<@{order['assigned_editor_id'] or order['shop_owner_id']}>", inline=True)
    embed.add_field(name="Ticket", value=build_ticket_reference(order["ticket_channel_id"]), inline=True)
    embed.add_field(name="Itens", value=truncate_text(str(order["item_summary"]), 900), inline=False)
    embed.add_field(name="Total", value=f"**{format_price(int(order['total_price_cents']))}**", inline=True)
    embed.add_field(name="Tempo", value=format_delivery_duration(order["started_at"], order["completed_at"]), inline=True)
    embed.add_field(name="Transcript", value=format_transcript_state(order), inline=True)
    embed.add_field(name="Detalhes do cliente", value=order["details"] or "Nenhuma observacao enviada.", inline=False)
    embed.set_footer(text="Use os botoes abaixo para controlar o atendimento")
    return embed


def build_orders_embed(title: str, description: str, orders: list[sqlite3.Row], owner_view: bool) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=EMBED_COLORS["panel"])
    if not orders:
        embed.add_field(name="Pedidos", value="Nenhum pedido encontrado.", inline=False)
        return embed
    pending_count = sum(1 for order in orders if str(order["status"]) == "pendente")
    in_progress_count = sum(1 for order in orders if str(order["status"]) == "em_andamento")
    closed_count = sum(1 for order in orders if str(order["status"]) in {"concluido", "fechado"})
    transcript_count = sum(1 for order in orders if bool(order["has_transcript"]))
    embed.add_field(name="Resumo", value=build_stat_block("Total", str(len(orders))), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Pendentes", str(pending_count)), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Finalizados", str(closed_count)), inline=True)
    embed.add_field(name="Atendimento", value=build_stat_block("Em andamento", str(in_progress_count)), inline=True)
    embed.add_field(name="Transcript", value=build_stat_block("Disponiveis", str(transcript_count)), inline=True)
    for order in orders[:10]:
        embed.add_field(
            name=f"Pedido #{order['id']} | {truncate_text(str(order['product_name']), 40)}",
            value=render_order_card(order, owner_view),
            inline=False,
        )
    embed.set_footer(text="Pedidos concluidos continuam visiveis sem reabrir ticket")
    return embed


@bot.event
async def on_ready() -> None:
    logger.info("Bot conectado como %s.", bot.user)


@bot.event
async def setup_hook() -> None:
    for order in store_db.list_ticket_orders():
        view = TicketControlsView.from_order(order)
        if not view.is_persistent():
            logger.warning("Ticket #%s nao foi registrado como view persistente.", order["id"])
            continue
        bot.add_view(view)
    for application in store_db.list_pending_seller_applications():
        bot.add_view(SellerApplicationReviewView(int(application["id"])))
    for publication in store_db.list_published_shops():
        bot.add_view(PublicPublishedShopView(int(publication["guild_id"]), int(publication["shop_public_id"])))

    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info("Comandos sincronizados no servidor %s.", GUILD_ID)
        else:
            logger.info("GUILD_ID nao configurado. Comandos globais podem demorar para aparecer no Discord.")
            await bot.tree.sync()
            logger.info("Comandos globais sincronizados.")
    except discord.Forbidden:
        logger.exception("Falha ao sincronizar comandos: Missing Access para o GUILD_ID configurado.")
    except discord.HTTPException:
        logger.exception("Falha HTTP ao sincronizar comandos.")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    if before.premium_since is not None or after.premium_since is None:
        return
    if BOOST_THANK_CHANNEL_ID is None:
        return
    channel = after.guild.get_channel(BOOST_THANK_CHANNEL_ID)
    if not isinstance(channel, discord.TextChannel):
        return
    message = await channel.send(
        f"Obrigado pelo boost, {after.mention}! Sua ajuda fortalece a comunidade e a estrutura da loja."
    )
    store_db.record_boost_event(after.guild.id, after.id, message.id)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
    logger.exception("Erro em comando", exc_info=error)
    message = str(error) if isinstance(error, app_commands.AppCommandError) else "Ocorreu um erro ao executar o comando."
    if interaction.response.is_done():
        await interaction.followup.send(f"Erro: {message}", ephemeral=True)
    else:
        await interaction.response.send_message(f"Erro: {message}", ephemeral=True)


async def send_main_panel(interaction: discord.Interaction) -> None:
    guild_id = guild_only_interaction(interaction)
    await interaction.response.send_message(
        embed=build_home_panel_embed(guild_id, interaction.user.id),
        view=HomePanelView(interaction.user.id),
        ephemeral=True,
    )


async def send_owner_panel(interaction: discord.Interaction) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_owner_shop_embed(shops),
        view=OwnerShopBrowserView(interaction.user.id, shops),
        ephemeral=True,
    )


class PublicOpenShopButton(discord.ui.Button):
    def __init__(self, guild_id: int, shop_public_id: int) -> None:
        super().__init__(
            label="Abrir loja",
            style=discord.ButtonStyle.primary,
            custom_id=f"public_shop:open:{guild_id}:{shop_public_id}",
        )
        self.guild_id = guild_id
        self.shop_public_id = shop_public_id

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        if guild_id != self.guild_id:
            await interaction.response.send_message("Esse painel publico pertence a outro servidor.", ephemeral=True)
            return
        shop = store_db.get_shop(guild_id, self.shop_public_id)
        if shop is None:
            await interaction.response.send_message("Essa loja nao esta mais disponivel.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, shop.id)
        await interaction.response.send_message(
            embed=build_shop_catalog_embed(shop, products, 0, "Todos"),
            view=ShopDetailView(interaction.user.id, shop, products, "Todos", 0),
            ephemeral=True,
        )


class PublicPublishedShopView(discord.ui.View):
    def __init__(self, guild_id: int, shop_public_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(PublicOpenShopButton(guild_id, shop_public_id))


async def sync_shop_public_panels(shop: Shop) -> None:
    products = store_db.list_products(shop.guild_id, shop.id)
    embed = build_shop_panel_embed(shop, products)
    for publication in store_db.list_shop_publications(shop.db_id):
        guild = bot.get_guild(int(publication["guild_id"]))
        if guild is None:
            continue
        channel = guild.get_channel(int(publication["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            message = await channel.fetch_message(int(publication["message_id"]))
            await message.edit(embed=embed, view=PublicPublishedShopView(shop.guild_id, shop.id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning("Falha ao sincronizar painel publico da loja #%s no canal %s.", shop.id, publication["channel_id"])
            continue


async def delete_shop_public_messages(publications: list[sqlite3.Row]) -> None:
    for publication in publications:
        guild = bot.get_guild(int(publication["guild_id"]))
        if guild is None:
            continue
        channel = guild.get_channel(int(publication["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            message = await channel.fetch_message(int(publication["message_id"]))
            await message.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.warning(
                "Falha ao remover painel publico antigo da loja no canal %s mensagem %s.",
                publication["channel_id"],
                publication["message_id"],
            )
            continue


class SellerApplicationModal(discord.ui.Modal):
    def __init__(self) -> None:
        super().__init__(title="Solicitar cargo de lojista")
        self.portfolio = discord.ui.TextInput(label="Portfolio ou exemplos", style=discord.TextStyle.paragraph, max_length=400)
        self.specialty = discord.ui.TextInput(label="Servicos e experiencia", style=discord.TextStyle.paragraph, max_length=300)
        self.add_item(self.portfolio)
        self.add_item(self.specialty)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        application_id = store_db.create_seller_application(guild_id, interaction.user.id, str(self.portfolio).strip(), str(self.specialty).strip())
        if interaction.guild is None or SELLER_APPLICATION_CHANNEL_ID is None:
            await interaction.response.send_message("Configure `SELLER_APPLICATION_CHANNEL_ID` antes de usar este formulario.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(SELLER_APPLICATION_CHANNEL_ID)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Nao encontrei um canal valido para enviar a solicitacao.", ephemeral=True)
            return
        embed = build_seller_application_embed(
            application_id=application_id,
            user_id=interaction.user.id,
            portfolio_text=str(self.portfolio).strip(),
            specialty_text=str(self.specialty).strip(),
        )
        message = await channel.send(embed=embed, view=SellerApplicationReviewView(application_id))
        store_db.set_seller_application_message(application_id, channel.id, message.id)
        await interaction.response.send_message("Solicitacao enviada para analise da administracao.", ephemeral=True)


class SellerApplicationRejectModal(discord.ui.Modal):
    def __init__(self, application_id: int) -> None:
        super().__init__(title=f"Recusar solicitacao #{application_id}")
        self.application_id = application_id
        self.reason_input = discord.ui.TextInput(
            label="Motivo da recusa",
            style=discord.TextStyle.paragraph,
            max_length=300,
            placeholder="Explique de forma objetiva o motivo da recusa.",
        )
        self.add_item(self.reason_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Apenas administradores podem revisar solicitacoes.", ephemeral=True)
            return
        application = store_db.get_seller_application(self.application_id)
        if application is None or interaction.guild is None:
            await interaction.response.send_message("Solicitacao nao encontrada.", ephemeral=True)
            return
        if str(application["status"]) != "pendente":
            await interaction.response.send_message("Essa solicitacao ja foi revisada anteriormente.", ephemeral=True)
            return
        note = str(self.reason_input).strip()[:300]
        updated = store_db.review_seller_application(self.application_id, "recusado", interaction.user.id, note)
        if not updated:
            await interaction.response.send_message("Essa solicitacao ja nao esta mais pendente.", ephemeral=True)
            return
        embed = build_seller_application_embed(
            application_id=int(application["id"]),
            user_id=int(application["applicant_id"]),
            portfolio_text=str(application["portfolio_text"]),
            specialty_text=str(application["specialty_text"]),
            status="recusado",
            review_note=note,
            admin_id=interaction.user.id,
        )
        channel = interaction.guild.get_channel(int(application["message_channel_id"])) if application["message_channel_id"] else None
        if isinstance(channel, discord.TextChannel) and application["message_id"]:
            try:
                message = await channel.fetch_message(int(application["message_id"]))
                await message.edit(embed=embed, view=None)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning("Falha ao atualizar a mensagem da solicitacao de lojista #%s.", self.application_id)
        await interaction.response.send_message("Solicitacao recusada com motivo registrado.", ephemeral=True)


class SellerApplicationActionButton(discord.ui.Button):
    def __init__(self, application_id: int, action: str, label: str, style: discord.ButtonStyle) -> None:
        super().__init__(label=label, style=style, custom_id=f"seller_app:{action}:{application_id}")
        self.application_id = application_id
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Apenas administradores podem revisar solicitacoes.", ephemeral=True)
            return
        application = store_db.get_seller_application(self.application_id)
        if application is None or interaction.guild is None:
            await interaction.response.send_message("Solicitacao nao encontrada.", ephemeral=True)
            return
        if str(application["status"]) != "pendente":
            await interaction.response.send_message("Essa solicitacao ja foi revisada anteriormente.", ephemeral=True)
            return
        applicant = interaction.guild.get_member(int(application["applicant_id"]))
        if self.action == "approve":
            role = find_lojista_role(interaction.guild)
            if role is None:
                await interaction.response.send_message(f"O cargo `{LOJISTA_ROLE_NAME}` nao foi encontrado no servidor.", ephemeral=True)
                return
            if applicant is not None:
                await applicant.add_roles(role, reason=f"Solicitacao de lojista aprovada por {interaction.user.id}")
            updated = store_db.review_seller_application(self.application_id, "aprovado", interaction.user.id, "")
            if not updated:
                await interaction.response.send_message("Essa solicitacao ja nao esta mais pendente.", ephemeral=True)
                return
            embed = build_seller_application_embed(
                application_id=int(application["id"]),
                user_id=int(application["applicant_id"]),
                portfolio_text=str(application["portfolio_text"]),
                specialty_text=str(application["specialty_text"]),
                status="aprovado",
                admin_id=interaction.user.id,
            )
            await interaction.response.edit_message(embed=embed, view=None)
            return
        await interaction.response.send_modal(SellerApplicationRejectModal(self.application_id))


class SellerApplicationReviewView(discord.ui.View):
    def __init__(self, application_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(SellerApplicationActionButton(application_id, "approve", "Aprovar", discord.ButtonStyle.success))
        self.add_item(SellerApplicationActionButton(application_id, "reject", "Recusar", discord.ButtonStyle.danger))


class PublishShopChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, shop: Shop) -> None:
        super().__init__(channel_types=[discord.ChannelType.text], placeholder="Escolha o canal da divulgacao")
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Use dentro do servidor.", ephemeral=True)
            return
        channel = self.values[0]
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Selecione um canal de texto.", ephemeral=True)
            return
        products = store_db.list_products(self.shop.guild_id, self.shop.id)
        message = await channel.send(
            embed=build_shop_panel_embed(self.shop, products),
            view=PublicPublishedShopView(interaction.guild.id, self.shop.id),
        )
        store_db.upsert_shop_publication(interaction.guild.id, self.shop.db_id, channel.id, message.id)
        await interaction.response.send_message(f"Painel publico publicado em {channel.mention}.", ephemeral=True)


class PublishShopView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop) -> None:
        super().__init__(viewer_id)
        self.add_item(PublishShopChannelSelect(shop))


@bot.tree.command(name="criar_loja", description="Cria sua loja base.")
@app_commands.describe(
    nome="Nome da loja",
    descricao="Descricao curta do que sua loja vende",
    emoji_loja="Emoji, simbolo ou emoji custom para dar identidade a loja",
    headline="Frase principal da vitrine",
    subtitulo="Linha complementar para a bio visual",
    cor="Cor principal da loja em HEX, ex: #2B2D31",
)
async def create_shop(
    interaction: discord.Interaction,
    nome: str,
    descricao: str = "",
    emoji_loja: str = "",
    headline: str = "",
    subtitulo: str = "",
    cor: str = "",
) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop_emoji = parse_optional_shop_emoji(emoji_loja) if emoji_loja.strip() else None
    accent_color = parse_hex_color(cor) if cor.strip() else None
    try:
        shop_id = store_db.create_shop(
            guild_id,
            interaction.user.id,
            nome[:80],
            descricao[:500],
            shop_emoji=shop_emoji,
            headline=parse_optional_short_text(headline, 80, "Headline") if headline.strip() else None,
            subtitle=parse_optional_short_text(subtitulo, 120, "Subtitulo") if subtitulo.strip() else None,
            accent_color=accent_color,
        )
    except sqlite3.IntegrityError:
        await interaction.response.send_message("Voce ja tem uma loja com esse nome neste servidor.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"Loja **{nome}** criada com sucesso. ID: `{shop_id}`.\n"
        f"Depois use `/personalizar_loja` para colocar logo, banner e ajustar o visual.",
        ephemeral=True,
    )


@bot.tree.command(name="lojas", description="Mostra todas as lojas cadastradas neste servidor.")
async def list_shops(interaction: discord.Interaction) -> None:
    guild_id = guild_only_interaction(interaction)
    shops = store_db.list_shops(guild_id)
    if not shops:
        await interaction.response.send_message("Ainda nao existe nenhuma loja cadastrada.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=build_shop_card_embed(shops, 0),
        view=ShopBrowserView(interaction.user.id, shops, 0),
        ephemeral=True,
    )


@bot.tree.command(name="painel_loja", description="Abre o painel universal de lojas, pedidos e tickets.")
async def store_panel(interaction: discord.Interaction) -> None:
    await send_main_panel(interaction)


@bot.tree.command(name="painel", description="Abre o painel principal do sistema.")
async def main_panel_alias(interaction: discord.Interaction) -> None:
    await send_main_panel(interaction)


@bot.tree.command(name="gerenciar_lojas", description="Abre a area administrativa das suas lojas.")
async def manage_shops_command(interaction: discord.Interaction) -> None:
    await send_owner_panel(interaction)


@bot.tree.command(name="loja", description="Abre o gerenciamento central da sua loja e do catalogo.")
async def manage_store_alias(interaction: discord.Interaction) -> None:
    await send_owner_panel(interaction)


@bot.tree.command(name="solicitar_lojista", description="Envia um formulario para solicitar o cargo de lojista.")
async def request_seller_role(interaction: discord.Interaction) -> None:
    if member_is_lojista(interaction.user):
        await interaction.response.send_message(f"Voce ja possui o cargo `{LOJISTA_ROLE_NAME}`.", ephemeral=True)
        return
    await interaction.response.send_modal(SellerApplicationModal())


@bot.tree.command(name="ver_loja", description="Abre a vitrine de uma loja.")
@app_commands.describe(id_loja="ID da loja que aparece no comando /lojas")
async def view_shop(interaction: discord.Interaction, id_loja: int) -> None:
    guild_id = guild_only_interaction(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    products = store_db.list_products(guild_id, id_loja)
    await interaction.response.send_message(
        embed=build_shop_catalog_embed(shop, products, 0, "Todos"),
        view=ShopDetailView(interaction.user.id, shop, products, "Todos", 0),
        ephemeral=True,
    )


@bot.tree.command(name="criar_produto", description="Adiciona um produto na sua loja.")
@app_commands.describe(
    id_loja="ID da sua loja",
    nome="Nome do produto, ex: Banner animado",
    categoria="Categoria do produto, ex: Banner, Avatar, Booster",
    preco="Preco, ex: 25,50",
    descricao="Descricao do produto",
)
async def create_product(
    interaction: discord.Interaction,
    id_loja: int,
    nome: str,
    categoria: str,
    preco: str,
    descricao: str = "",
) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono da loja pode criar produtos nela.", ephemeral=True)
        return

    price_cents = parse_price_to_cents(preco)
    category_value = normalize_category(categoria)
    try:
        product_id = store_db.add_product(shop.db_id, nome[:80], category_value, price_cents, descricao[:500])
    except sqlite3.IntegrityError:
        await interaction.response.send_message("Ja existe um produto com esse nome nessa loja.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"Produto **{nome}** criado na categoria **{category_value}** por {format_price(price_cents)}. ID: `{product_id}`.",
        ephemeral=True,
    )
    await sync_shop_public_panels(shop)


@bot.tree.command(name="personalizar_loja", description="Edita o visual e a apresentacao da sua loja.")
@app_commands.describe(
    id_loja="ID da sua loja",
    descricao="Nova descricao da loja",
    emoji_loja="Emoji, simbolo ou emoji custom. Use 'remover' para limpar",
    headline="Frase principal da vitrine. Use 'remover' para limpar",
    subtitulo="Linha complementar da bio visual. Use 'remover' para limpar",
    vantagens="Bloco de vantagens da loja. Use 'remover' para limpar",
    texto_botao="Texto do botao de compra. Use 'remover' para limpar",
    cor="Nova cor em HEX, ex: #58A6FF, ou 'remover'",
    foto="Logo da loja por URL, ou 'remover'",
    banner="Banner/capa da loja por URL, ou 'remover'",
)
async def customize_shop(
    interaction: discord.Interaction,
    id_loja: int,
    descricao: str = "",
    emoji_loja: str = "",
    headline: str = "",
    subtitulo: str = "",
    vantagens: str = "",
    texto_botao: str = "",
    cor: str = "",
    foto: str = "",
    banner: str = "",
) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono da loja pode personalizar essa vitrine.", ephemeral=True)
        return

    description_value = descricao[:500] if descricao else None
    emoji_value: Optional[str] = None
    theme_name_value: Optional[str] = None
    buy_button_text_value: Optional[str] = None
    headline_value: Optional[str] = None
    subtitle_value: Optional[str] = None
    highlights_value: Optional[str] = None
    color_value: Optional[str] = None
    image_value: Optional[str] = None
    banner_value: Optional[str] = None

    if emoji_loja:
        emoji_value = parse_optional_shop_emoji(emoji_loja)
    if headline:
        headline_value = parse_optional_short_text(headline, 80, "Headline")
    if subtitulo:
        subtitle_value = parse_optional_short_text(subtitulo, 120, "Subtitulo")
    if vantagens:
        highlights_value = parse_optional_multiline_text(vantagens, 300, "Vantagens")
    if texto_botao:
        buy_button_text_value = parse_optional_short_text(texto_botao, 80, "Texto do botao")
    if cor:
        theme_name_value = ""
        color_value = "" if cor.strip().lower() in {"remover", "none", "nenhum"} else parse_hex_color(cor)
    if foto:
        image_value = parse_optional_image_url(foto)
    if banner:
        banner_value = parse_optional_image_url(banner)

    updated = store_db.update_shop_style(
        guild_id=guild_id,
        shop_id=id_loja,
        owner_id=interaction.user.id,
        description=description_value,
        shop_emoji=emoji_value,
        theme_name=theme_name_value,
        buy_button_text=buy_button_text_value,
        headline=headline_value,
        subtitle=subtitle_value,
        highlights=highlights_value,
        terms_text=None,
        is_open=None,
        availability_status=None,
        accent_color=color_value,
        image_url=image_value,
        banner_url=banner_value,
    )
    if not updated:
        await interaction.response.send_message(
            "Nada foi alterado. Envie ao menos um campo para atualizar a loja.",
            ephemeral=True,
        )
        return

    refreshed_shop = store_db.get_shop(guild_id, id_loja)
    if refreshed_shop is None:
        await interaction.response.send_message("A loja foi atualizada, mas nao consegui recarrega-la.", ephemeral=True)
        return
    products = store_db.list_products(guild_id, id_loja)
    await interaction.response.send_message(
        "Vitrine atualizada com sucesso.",
        embed=build_shop_panel_embed(refreshed_shop, products),
        ephemeral=True,
    )
    await sync_shop_public_panels(refreshed_shop)


@bot.tree.command(name="status_loja", description="Abre, fecha ou ajusta a disponibilidade da sua loja.")
@app_commands.describe(
    id_loja="ID da sua loja",
    aberta="Defina se a loja esta aberta para novos pedidos",
    disponibilidade="Use disponivel ou ocupado",
)
async def set_shop_status(
    interaction: discord.Interaction,
    id_loja: int,
    aberta: bool,
    disponibilidade: str,
) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono pode alterar o status da loja.", ephemeral=True)
        return

    updated = store_db.update_shop_style(
        guild_id=guild_id,
        shop_id=id_loja,
        owner_id=interaction.user.id,
        description=None,
        shop_emoji=None,
        theme_name=None,
        buy_button_text=None,
        headline=None,
        subtitle=None,
        highlights=None,
        terms_text=None,
        is_open=aberta,
        availability_status=normalize_availability_status(disponibilidade),
        accent_color=None,
        image_url=None,
        banner_url=None,
    )
    if not updated:
        await interaction.response.send_message("Nao consegui atualizar o status da loja.", ephemeral=True)
        return
    refreshed_shop = store_db.get_shop(guild_id, id_loja)
    if refreshed_shop is None:
        await interaction.response.send_message("Status atualizado, mas nao consegui recarregar a loja.", ephemeral=True)
        return
    products = store_db.list_products(guild_id, id_loja)
    await interaction.response.send_message(
        f"Status da loja atualizado para **{shop_status_text(refreshed_shop)}**.",
        embed=build_shop_panel_embed(refreshed_shop, products),
        ephemeral=True,
    )
    await sync_shop_public_panels(refreshed_shop)


@bot.tree.command(name="termos_loja", description="Configura os termos que o cliente deve ler antes da compra.")
@app_commands.describe(id_loja="ID da sua loja", termos="Texto dos termos. Use 'remover' para limpar")
async def set_shop_terms(interaction: discord.Interaction, id_loja: int, termos: str) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono pode alterar os termos.", ephemeral=True)
        return

    updated = store_db.update_shop_style(
        guild_id=guild_id,
        shop_id=id_loja,
        owner_id=interaction.user.id,
        description=None,
        shop_emoji=None,
        theme_name=None,
        buy_button_text=None,
        headline=None,
        subtitle=None,
        highlights=None,
        terms_text=parse_optional_multiline_text(termos, 900, "Termos"),
        is_open=None,
        availability_status=None,
        accent_color=None,
        image_url=None,
        banner_url=None,
    )
    if not updated:
        await interaction.response.send_message("Nao consegui atualizar os termos.", ephemeral=True)
        return
    refreshed_shop = store_db.get_shop(guild_id, id_loja)
    if refreshed_shop is None:
        await interaction.response.send_message("Termos atualizados, mas nao consegui recarregar a loja.", ephemeral=True)
        return
    products = store_db.list_products(guild_id, id_loja)
    await interaction.response.send_message(
        "Termos da loja atualizados.",
        embed=build_shop_panel_embed(refreshed_shop, products),
        ephemeral=True,
    )
    await sync_shop_public_panels(refreshed_shop)


@bot.tree.command(name="tema_loja", description="Aplica um preset visual pronto na sua loja.")
@app_commands.describe(id_loja="ID da sua loja", preset="Tema visual pronto")
@app_commands.choices(
    preset=[
        app_commands.Choice(name="Booster", value="booster"),
        app_commands.Choice(name="Dark Red", value="dark_red"),
        app_commands.Choice(name="Gold", value="gold"),
        app_commands.Choice(name="Neon Blue", value="neon_blue"),
    ]
)
async def set_shop_theme(
    interaction: discord.Interaction,
    id_loja: int,
    preset: app_commands.Choice[str],
) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono da loja pode aplicar um tema.", ephemeral=True)
        return

    updates = apply_theme_preset_to_shop(shop, preset.value)
    store_db.update_shop_style(
        guild_id=guild_id,
        shop_id=id_loja,
        owner_id=interaction.user.id,
        description=None,
        shop_emoji=updates.get("shop_emoji"),
        theme_name=updates["theme_name"],
        buy_button_text=None,
        headline=updates.get("headline"),
        subtitle=updates.get("subtitle"),
        highlights=None,
        terms_text=None,
        is_open=None,
        availability_status=None,
        accent_color=updates["accent_color"],
        image_url=None,
        banner_url=None,
    )
    refreshed_shop = store_db.get_shop(guild_id, id_loja)
    if refreshed_shop is None:
        await interaction.response.send_message("Tema aplicado, mas nao consegui recarregar a loja.", ephemeral=True)
        return
    products = store_db.list_products(guild_id, id_loja)
    await interaction.response.send_message(
        f"Tema **{preset.name}** aplicado com sucesso.",
        embed=build_shop_panel_embed(refreshed_shop, products),
        ephemeral=True,
    )
    await sync_shop_public_panels(refreshed_shop)


@bot.tree.command(name="excluir_loja", description="Remove uma loja sua e tudo ligado a ela.")
@app_commands.describe(id_loja="ID da loja que voce deseja excluir")
async def delete_shop_command(interaction: discord.Interaction, id_loja: int) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono da loja pode exclui-la.", ephemeral=True)
        return
    publications = store_db.list_shop_publications(shop.db_id)
    deleted = store_db.delete_shop(guild_id, id_loja, interaction.user.id)
    if not deleted:
        if store_db.shop_has_orders(guild_id, id_loja, interaction.user.id):
            await interaction.response.send_message("Nao e possivel excluir essa loja porque ela possui pedidos no historico.", ephemeral=True)
        else:
            await interaction.response.send_message("Nao consegui excluir a loja.", ephemeral=True)
        return
    await delete_shop_public_messages(publications)
    await interaction.response.send_message(f"Loja **{shop.name}** excluida com sucesso.", ephemeral=True)


@bot.tree.command(name="alterar_preco", description="Altera o preco de um produto da sua loja.")
@app_commands.describe(id_produto="ID do produto", novo_preco="Novo preco, ex: 40,00")
async def update_price(interaction: discord.Interaction, id_produto: int, novo_preco: str) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    if not store_db.product_belongs_to_owner(guild_id, id_produto, interaction.user.id):
        await interaction.response.send_message("Produto nao encontrado ou voce nao e o dono da loja desse produto.", ephemeral=True)
        return

    price_cents = parse_price_to_cents(novo_preco)
    store_db.update_product_price(id_produto, price_cents)
    await interaction.response.send_message(f"Preco do produto `#{id_produto}` alterado para {format_price(price_cents)}.", ephemeral=True)
    product = store_db.get_product(guild_id, id_produto)
    if product is not None:
        shop = store_db.get_shop(guild_id, int(product["store_id"]))
        if shop is not None:
            await sync_shop_public_panels(shop)


@bot.tree.command(name="comprar_produto", description="Faz um pedido manualmente e cria um ticket privado.")
@app_commands.describe(id_produto="ID do produto", quantidade="Quantidade desejada", detalhes="Observacoes do pedido")
async def buy_product(
    interaction: discord.Interaction,
    id_produto: int,
    quantidade: app_commands.Range[int, 1, 99] = 1,
    detalhes: str = "",
) -> None:
    guild_id = guild_only_interaction(interaction)
    product = store_db.get_product(guild_id, id_produto)
    if product is None:
        await interaction.response.send_message("Produto nao encontrado.", ephemeral=True)
        return

    shop = store_db.get_shop(guild_id, int(product["store_id"]))
    if shop is None:
        await interaction.response.send_message("A loja desse produto nao foi encontrada.", ephemeral=True)
        return
    if shop.terms_text:
        await interaction.response.send_message(
            f"**Termos da loja {shop_title(shop.name, shop.shop_emoji)}**\n\n{shop.terms_text}",
            ephemeral=True,
            view=TermsAcceptanceView(shop, [product], interaction.user.id),
        )
        return

    _, total_price_cents, ticket_channel = await create_order_and_ticket(
        interaction=interaction,
        shop=shop,
        product=product,
        quantity=quantidade,
        details=detalhes,
    )
    ticket_text = build_ticket_creation_notice(ticket_channel)
    await interaction.response.send_message(
        f"Pedido enviado com sucesso por {format_price(total_price_cents)}.\nTicket: {ticket_text}",
        ephemeral=True,
    )


@bot.tree.command(name="meus_pedidos", description="Mostra os pedidos que voce ja fez.")
async def my_orders(interaction: discord.Interaction) -> None:
    guild_id = guild_only_interaction(interaction)
    orders = store_db.list_orders_for_buyer(guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_orders_embed("Meus pedidos", "Resumo dos seus pedidos mais recentes.", orders, False),
        ephemeral=True,
    )


@bot.tree.command(name="pedidos_loja", description="Mostra os pedidos recebidos pelas suas lojas.")
async def store_orders(interaction: discord.Interaction) -> None:
    guild_id = guild_only_interaction(interaction)
    ensure_lojista_member(interaction)
    orders = store_db.list_orders_for_owner(guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_orders_embed("Pedidos recebidos", "Resumo dos pedidos mais recentes das suas lojas.", orders, True),
        ephemeral=True,
    )


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Configure DISCORD_TOKEN no arquivo .env antes de iniciar o bot.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    bot.run(DISCORD_TOKEN)
