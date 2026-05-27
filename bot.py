import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv


load_dotenv()


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
ADMIN_TESTER_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_TESTER_IDS", "").split(",")
    if value.strip().isdigit()
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
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    ticket_channel_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
                )
                """
            )
            self._ensure_column(db, "orders", "public_id", "INTEGER")
            self._ensure_column(db, "orders", "status", "TEXT NOT NULL DEFAULT 'pendente'")
            self._ensure_column(db, "orders", "started_at", "TIMESTAMP")
            self._ensure_column(db, "orders", "completed_at", "TIMESTAMP")
            self._ensure_column(db, "orders", "ticket_channel_id", "INTEGER")
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
            self._resequence_shop_public_ids(db)
            self._resequence_order_public_ids(db)

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
                       COUNT(p.id) AS product_count
                FROM shops s
                LEFT JOIN products p ON p.shop_id = s.id AND p.active = 1
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
            cursor = db.execute(
                "DELETE FROM shops WHERE guild_id = ? AND public_id = ? AND owner_id = ?",
                (guild_id, shop_id, owner_id),
            )
            self._resequence_shop_public_ids(db)
            return cursor.rowcount > 0

    def list_shops_for_owner(self, guild_id: int, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT s.id AS db_id, s.public_id AS id, s.name, s.description, s.owner_id, s.shop_emoji, s.theme_name, s.buy_button_text,
                       s.headline, s.subtitle, s.highlights, s.terms_text, s.is_open, s.availability_status,
                       s.accent_color, s.image_url, s.banner_url,
                       COUNT(p.id) AS product_count
                FROM shops s
                LEFT JOIN products p ON p.shop_id = s.id AND p.active = 1
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
    ) -> int:
        with self.connect() as db:
            public_id = self._next_order_public_id(db, guild_id)
            cursor = db.execute(
                """
                INSERT INTO orders (
                    guild_id, public_id, shop_id, product_id, buyer_id, quantity, details, total_price_cents
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (guild_id, public_id, shop_id, product_id, buyer_id, quantity, details, total_price_cents),
            )
            return int(cursor.lastrowid)

    def update_order_ticket_channel(self, order_id: int, channel_id: int) -> None:
        with self.connect() as db:
            db.execute("UPDATE orders SET ticket_channel_id = ? WHERE id = ?", (channel_id, order_id))

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
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (status, order_id),
                )
            else:
                db.execute(
                    """
                    UPDATE orders
                    SET status = ?, completed_at = NULL
                    WHERE id = ?
                    """,
                    (status, order_id),
                )

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
                       o.total_price_cents, o.status, o.ticket_channel_id, o.created_at, o.started_at, o.completed_at,
                       p.name AS product_name,
                       s.name AS shop_name, s.public_id AS shop_public_id, s.owner_id AS shop_owner_id
                FROM orders o
                JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.id = ?
                """,
                (order_id,),
            ).fetchone()

    def list_orders_for_buyer(self, guild_id: int, buyer_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.quantity, o.details, o.total_price_cents, o.status, o.created_at, o.started_at, o.completed_at, o.ticket_channel_id,
                       p.name AS product_name, s.name AS shop_name
                FROM orders o
                JOIN products p ON p.id = o.product_id
                JOIN shops s ON s.id = o.shop_id
                WHERE o.guild_id = ? AND o.buyer_id = ? AND o.status NOT IN ('concluido', 'fechado')
                ORDER BY o.id DESC
                LIMIT 15
                """,
                (guild_id, buyer_id),
            ).fetchall()

    def list_orders_for_owner(self, guild_id: int, owner_id: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """
                SELECT o.id AS db_id, o.public_id AS id, o.quantity, o.details, o.total_price_cents, o.status, o.created_at, o.started_at, o.completed_at, o.ticket_channel_id,
                       p.name AS product_name, s.name AS shop_name, o.buyer_id
                FROM orders o
                JOIN products p ON p.id = o.product_id
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
                SELECT o.id AS db_id, o.public_id AS id, o.buyer_id, o.status, o.ticket_channel_id, s.owner_id AS shop_owner_id
                FROM orders o
                JOIN shops s ON s.id = o.shop_id
                WHERE o.ticket_channel_id IS NOT NULL
                """
            ).fetchall()


store_db = StoreDatabase(DATABASE_PATH)

intents = discord.Intents.default()
intents.guilds = True
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
    if normalized in {"disponivel", "aberta", "livre"}:
        return "disponivel"
    if normalized in {"ocupado", "busy"}:
        return "ocupado"
    raise app_commands.AppCommandError("Status invalido. Use `disponivel` ou `ocupado`.")


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


def shop_status_text(shop: Shop) -> str:
    open_text = "Aberta" if shop.is_open else "Fechada"
    availability = "Disponivel" if shop.availability_status == "disponivel" else "Ocupado"
    return f"{open_text} • {availability}"


def build_row_shop_intro_text(shop: sqlite3.Row) -> str:
    parts: list[str] = []
    if shop["headline"]:
        parts.append(f"**{shop['headline']}**")
    if shop["subtitle"]:
        parts.append(str(shop["subtitle"]))
    if shop["description"]:
        parts.append(str(shop["description"]))
    return "\n\n".join(parts) if parts else "Sem descricao cadastrada."


def row_shop_status_text(shop: sqlite3.Row) -> str:
    open_text = "Aberta" if bool(shop["is_open"]) else "Fechada"
    availability = "Disponivel" if str(shop["availability_status"]) == "disponivel" else "Ocupado"
    return f"{open_text} • {availability}"


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


def build_ticket_creation_notice(ticket_channel: Optional[discord.TextChannel]) -> str:
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


def render_order_card(order: sqlite3.Row, owner_view: bool) -> str:
    lines = [
        f"• Status: {format_status(str(order['status']))}",
        f"• Total: **{format_price(int(order['total_price_cents']))}**",
        f"• Quantidade: `{order['quantity']}`",
        f"• Ticket: {build_ticket_reference(order['ticket_channel_id'])}",
        f"• Tempo: {format_delivery_duration(order['started_at'], order['completed_at'])}",
    ]
    if owner_view:
        lines.insert(1, f"• Cliente: <@{order['buyer_id']}>")
    else:
        lines.insert(1, f"• Loja: **{order['shop_name']}**")
    lines.append("")
    lines.append(f"Resumo: {short_order_details(str(order['details'] or ''))}")
    return "\n".join(lines)


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
            "`Gerenciar lojas` para cuidar do visual e do catalogo."
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
    embed = discord.Embed(
        title=f"{shop_title(shop.name, shop.shop_emoji)} • painel da loja",
        description=build_shop_intro_text(shop),
        color=shop_color_value(shop),
    )
    embed.add_field(name="Resumo", value=build_stat_block("Loja", f"#{shop.id}"), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Itens", str(len(products))), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Tema", shop_theme_label(shop)), inline=True)
    embed.add_field(name="Vendedor", value=f"<@{shop.owner_id}>", inline=False)
    embed.add_field(name="Acao principal", value=shop_buy_button_text(shop), inline=False)
    if shop.highlights:
        embed.add_field(name="Vantagens", value=shop.highlights, inline=False)
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


def build_owner_shop_embed(shops: list[sqlite3.Row]) -> discord.Embed:
    embed = discord.Embed(
        title="Painel do Vendedor",
        description="Sua área de gestão para manter vitrines, catálogo e identidade visual com aparência profissional.",
        color=EMBED_COLORS["panel"],
    )
    if not shops:
        embed.add_field(name="Lojas", value="Voce ainda nao criou nenhuma loja.", inline=False)
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

def build_order_embed_from_row(order: sqlite3.Row) -> discord.Embed:
    meta = get_status_meta(str(order["status"]))
    embed = discord.Embed(
        title=f"Pedido #{order['id']}",
        description=f"{meta['emoji']} **{meta['label']}** • **{order['shop_name']}**",
        color=meta["color"],
    )
    embed.add_field(name="Cliente", value=f"<@{order['buyer_id']}>", inline=True)
    embed.add_field(name="Produto", value=f"**{order['product_name']}**", inline=True)
    embed.add_field(name="Quantidade", value=f"`{order['quantity']}`", inline=True)
    embed.add_field(name="Total", value=f"**{format_price(int(order['total_price_cents']))}**", inline=True)
    embed.add_field(name="Status", value=format_status(str(order["status"])), inline=True)
    embed.add_field(name="Ticket", value=build_ticket_reference(order["ticket_channel_id"]), inline=True)
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
    embed.add_field(name="Resumo", value=build_stat_block("Total", str(len(orders))), inline=True)
    embed.add_field(name=" ", value=build_stat_block("Pendentes", str(pending_count)), inline=True)
    embed.add_field(name="  ", value=build_stat_block("Finalizados", str(closed_count)), inline=True)
    embed.add_field(name="Atendimento", value=build_stat_block("Em andamento", str(in_progress_count)), inline=False)

    for order in orders[:10]:
        embed.add_field(
            name=f"Pedido #{order['id']} | {order['product_name']}",
            value=render_order_card(order, owner_view),
            inline=False,
        )
    embed.set_footer(text="Os pedidos mais recentes aparecem primeiro")
    return embed


def build_product_preview_embed(shop: Shop, product: sqlite3.Row) -> discord.Embed:
    average_rating, total_ratings = store_db.get_shop_rating_summary(shop.db_id)
    embed = discord.Embed(
        title=f"{shop_title(shop.name, shop.shop_emoji)} • {product['name']}",
        description=truncate_text(product["description"] or "Sem descricao cadastrada.", 300),
        color=shop_color_value(shop),
    )
    embed.add_field(name=build_section_title("🗂️", "Categoria"), value=str(product["category"]), inline=True)
    embed.add_field(name=build_section_title("💰", "Preço"), value=format_price(int(product["price_cents"])), inline=True)
    embed.add_field(name=build_section_title("🚀", "Próximo passo"), value=shop_buy_button_text(shop), inline=True)
    embed.add_field(name=build_section_title("🟢", "Status"), value=shop_status_text(shop), inline=False)
    embed.add_field(name=build_section_title("⭐", "Avaliações"), value=format_rating_summary(average_rating, total_ratings), inline=False)

    if shop.terms_text:
        embed.add_field(
            name=build_section_title("📜", "Aceite necessário"),
            value="Leia e aceite os termos antes de continuar.",
            inline=False
        )

    if shop.highlights:
        embed.add_field(
            name=build_section_title("⭐", "Diferenciais da loja"),
            value=format_shop_highlights(shop.highlights),
            inline=False
        )

    if shop.image_url:
        embed.set_thumbnail(url=shop.image_url)

    if shop.banner_url:
        embed.set_image(url=shop.banner_url)

    embed.set_footer(text="Use o botão abaixo para abrir seu atendimento")
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
    ticket_channel: Optional[discord.TextChannel],
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
        pass


async def create_ticket_channel(
    interaction: discord.Interaction,
    shop: Shop,
    order_public_id: int,
    product_name: str,
) -> Optional[discord.TextChannel]:
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

    category = await get_or_create_owner_ticket_category(guild, owner_member, bot_member, interaction.channel)
    buyer_name = interaction.user.display_name if isinstance(interaction.user, discord.Member) else interaction.user.name
    channel_name = build_ticket_channel_name(
        buyer_name=buyer_name,
        buyer_id=interaction.user.id,
        product_name=product_name,
        order_public_id=order_public_id,
    )

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
) -> tuple[int, int, Optional[discord.TextChannel]]:
    guild_id = guild_only_interaction(interaction)
    if interaction.user.id == shop.owner_id and not is_admin_tester(interaction.user.id):
        raise app_commands.AppCommandError(
            "Voce nao pode comprar um produto da sua propria loja. "
            "Se este perfil for de teste, adicione seu ID em `ADMIN_TESTER_IDS` no arquivo `.env`."
        )
    if not shop.is_open:
        raise app_commands.AppCommandError("Esta loja esta fechada no momento.")

    total_price_cents = int(product["price_cents"]) * quantity
    order_id = store_db.create_order(
        guild_id=guild_id,
        shop_id=shop.db_id,
        product_id=int(product["id"]),
        buyer_id=interaction.user.id,
        quantity=quantity,
        details=details[:400],
        total_price_cents=total_price_cents,
    )

    order = store_db.get_order_details(order_id)
    if order is None:
        raise app_commands.AppCommandError("Nao foi possivel finalizar o pedido.")

    ticket_channel = await create_ticket_channel(interaction, shop, int(order["id"]), str(product["name"]))
    if ticket_channel is not None:
        store_db.update_order_ticket_channel(order_id, ticket_channel.id)
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
        await sync_ticket_message(ticket_message, order_id)

    await send_owner_notification(interaction.guild, shop.owner_id, build_order_embed_from_row(order), ticket_channel)
    return order_id, total_price_cents, ticket_channel


class HeaderButton(discord.ui.Button):
    def __init__(self, label: str) -> None:
        super().__init__(label=truncate_text(label, 30), style=discord.ButtonStyle.secondary, disabled=True, row=0)


class BasePanelView(discord.ui.View):
    def __init__(self, viewer_id: int) -> None:
        super().__init__(timeout=600)
        self.viewer_id = viewer_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.viewer_id:
            await interaction.response.send_message("Esse painel pertence a outra pessoa.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[discord.ui.View]) -> None:
        print(f"Erro na view {self.__class__.__name__} item={item.__class__.__name__}: {error}")
        if interaction.response.is_done():
            await interaction.followup.send(f"Erro ao processar a acao: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Erro ao processar a acao: {error}", ephemeral=True)


class HomeActionSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="🛍 Explorar lojas", description="Abrir vitrines e selecionar produtos", value="shops"),
            discord.SelectOption(label="📦 Meus pedidos", description="Ver tickets e pedidos que voce abriu", value="my_orders"),
            discord.SelectOption(label="🎨 Gerenciar lojas", description="Personalizar e administrar suas vitrines", value="manage_shops"),
            discord.SelectOption(label="🧾 Pedidos recebidos", description="Ver pedidos feitos nas suas lojas", value="owner_orders"),
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
        super().__init__(placeholder="Escolha o produto para abrir o pedido...", min_values=1, max_values=1, options=options, disabled=not products, row=1)
        self.shop = shop

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        product = store_db.get_product(guild_id, int(self.values[0]))
        if product is None:
            await interaction.response.send_message("Esse produto nao esta mais disponivel.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=build_product_preview_embed(self.shop, product),
            view=ProductPurchaseView(interaction.user.id, self.shop, product),
            ephemeral=True,
        )


class OpenPurchaseButton(discord.ui.Button):
    def __init__(self, shop: Shop, product: sqlite3.Row) -> None:
        super().__init__(
            label=shop_buy_button_text(shop),
            style=discord.ButtonStyle.success,
            disabled=not shop.is_open,
        )
        self.shop = shop
        self.product = product

    async def callback(self, interaction: discord.Interaction) -> None:
        guild_id = guild_only_interaction(interaction)
        if not self.shop.is_open:
            await interaction.response.send_message("Esta loja esta fechada no momento.", ephemeral=True)
            return
        if self.shop.terms_text:
            store_db.record_term_acceptance(guild_id, self.shop.db_id, interaction.user.id, self.shop.terms_text)
        await interaction.response.send_modal(PurchaseModal(self.shop, self.product))


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
    def __init__(self, viewer_id: int, shop: Shop, product: sqlite3.Row) -> None:
        super().__init__(viewer_id)
        self.add_item(ViewTermsButton(shop))
        self.add_item(OpenPurchaseButton(shop, product))


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


class OwnerShopBrowserView(BasePanelView):
    def __init__(self, viewer_id: int, shops: list[sqlite3.Row]) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToHomeButton())
        self.add_item(HeaderButton("Gerenciar Lojas"))
        self.add_item(OwnerShopSelect(shops))
        self.add_item(OwnerShopRefreshButton())


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
        deleted = store_db.delete_product(guild_id, self.product_id, interaction.user.id)
        if not deleted:
            await interaction.response.send_message("Nao consegui excluir esse produto.", ephemeral=True)
            return
        products = store_db.list_products(guild_id, self.shop.id)
        await interaction.response.edit_message(
            content="Produto excluido com sucesso.",
            embed=build_owner_product_embed(self.shop, products),
            view=OwnerProductManageView(interaction.user.id, self.shop, products),
        )


class DeleteShopConfirmView(discord.ui.View):
    def __init__(self, owner_id: int, shop_id: int) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.shop_id = shop_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Somente o dono pode confirmar essa exclusao.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar exclusao", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        guild_id = guild_only_interaction(interaction)
        deleted = store_db.delete_shop(guild_id, self.shop_id, interaction.user.id)
        if not deleted:
            await interaction.response.send_message("Nao consegui excluir a loja.", ephemeral=True)
            return
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
            f"Tem certeza que deseja excluir **{self.shop.name}**? Isso apaga produtos e pedidos ligados a ela.",
            view=DeleteShopConfirmView(interaction.user.id, self.shop.id),
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
        products = store_db.list_products(guild_id, self.shop.id)
        await interaction.response.edit_message(
            embed=build_shop_panel_embed(self.shop, products),
            view=OwnerShopManageView(interaction.user.id, self.shop, products),
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


class OwnerShopManageView(BasePanelView):
    def __init__(self, viewer_id: int, shop: Shop, products: list[sqlite3.Row]) -> None:
        super().__init__(viewer_id)
        self.add_item(BackToOwnerShopsButton())
        self.add_item(HeaderButton("Gestão da loja"))
        self.add_item(OpenCustomizeButton(shop))
        self.add_item(OpenProductModalButton(shop))
        self.add_item(OpenManageProductsButton(shop))
        self.add_item(OpenBioButton(shop))
        self.add_item(DeleteShopButton(shop))
        self.add_item(ShopDetailRefreshButton(shop.id, "Todos", 0))


class PurchaseModal(discord.ui.Modal):
    def __init__(self, shop: Shop, product: sqlite3.Row) -> None:
        super().__init__(title=f"Comprar {truncate_text(str(product['name']), 35)}")
        self.shop = shop
        self.product = product

        self.quantity = discord.ui.TextInput(label="Quantidade", placeholder="Ex: 1", default="1", max_length=3)
        self.details = discord.ui.TextInput(
            label="Briefing do pedido",
            placeholder="Explique o que voce precisa, prazo, referências e observações...",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=400,
        )
        self.add_item(self.quantity)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            quantity = int(str(self.quantity).strip())
        except ValueError:
            await interaction.response.send_message("Digite uma quantidade valida.", ephemeral=True)
            return

        if quantity <= 0 or quantity > 99:
            await interaction.response.send_message("A quantidade precisa ficar entre 1 e 99.", ephemeral=True)
            return

        _, total_price_cents, ticket_channel = await create_order_and_ticket(
            interaction=interaction,
            shop=self.shop,
            product=self.product,
            quantity=quantity,
            details=str(self.details).strip(),
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

        if interaction.channel and isinstance(interaction.channel, discord.TextChannel):
            channel = interaction.channel
            buyer = interaction.guild.get_member(buyer_id) if interaction.guild else None
            owner = interaction.guild.get_member(owner_id) if interaction.guild else None
            if buyer is not None and owner is not None:
                try:
                    if next_status in {"concluido", "fechado"}:
                        await set_ticket_participants_visibility(channel, buyer, owner, buyer_visible=True, buyer_can_send=False, owner_can_send=True)
                    else:
                        await set_ticket_participants_visibility(channel, buyer, owner, buyer_visible=True, buyer_can_send=True, owner_can_send=True)
                except discord.Forbidden:
                    pass
            if next_status in {"concluido", "fechado"} and interaction.guild:
                archive_category = resolve_ticket_archive_category(interaction.guild)
                if archive_category is not None:
                    try:
                        await channel.edit(category=archive_category, reason=f"Ticket #{updated['id']} arquivado")
                    except discord.Forbidden:
                        pass

        await interaction.response.edit_message(
            embed=build_order_embed_from_row(updated),
            view=TicketControlsView.from_order(updated),
        )
        if self.action == "reopen" and interaction.channel and isinstance(interaction.channel, discord.TextChannel):
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


@bot.event
async def on_ready() -> None:
    print(f"Bot conectado como {bot.user}.")


@bot.event
async def setup_hook() -> None:
    for order in store_db.list_ticket_orders():
        view = TicketControlsView.from_order(order)
        if not view.is_persistent():
            print(f"Aviso: ticket #{order['id']} nao foi registrado como view persistente.")
            continue
        bot.add_view(view)

    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Comandos sincronizados no servidor {GUILD_ID}.")
    else:
        print("GUILD_ID nao configurado. Comandos globais podem demorar para aparecer no Discord.")
        await bot.tree.sync()
        print("Comandos globais sincronizados.")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: Exception) -> None:
    message = str(error) or "Ocorreu um erro ao executar o comando."
    print(f"Erro em comando: {error}")
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
    shops = store_db.list_shops_for_owner(guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_owner_shop_embed(shops),
        view=OwnerShopBrowserView(interaction.user.id, shops),
        ephemeral=True,
    )


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


@bot.tree.command(name="termos_loja", description="Configura os termos que o cliente deve ler antes da compra.")
@app_commands.describe(id_loja="ID da sua loja", termos="Texto dos termos. Use 'remover' para limpar")
async def set_shop_terms(interaction: discord.Interaction, id_loja: int, termos: str) -> None:
    guild_id = guild_only_interaction(interaction)
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


@bot.tree.command(name="excluir_loja", description="Remove uma loja sua e tudo ligado a ela.")
@app_commands.describe(id_loja="ID da loja que voce deseja excluir")
async def delete_shop_command(interaction: discord.Interaction, id_loja: int) -> None:
    guild_id = guild_only_interaction(interaction)
    shop = store_db.get_shop(guild_id, id_loja)
    if shop is None:
        await interaction.response.send_message("Loja nao encontrada.", ephemeral=True)
        return
    if shop.owner_id != interaction.user.id:
        await interaction.response.send_message("Apenas o dono da loja pode exclui-la.", ephemeral=True)
        return
    deleted = store_db.delete_shop(guild_id, id_loja, interaction.user.id)
    if not deleted:
        await interaction.response.send_message("Nao consegui excluir a loja.", ephemeral=True)
        return
    await interaction.response.send_message(f"Loja **{shop.name}** excluida com sucesso.", ephemeral=True)


@bot.tree.command(name="alterar_preco", description="Altera o preco de um produto da sua loja.")
@app_commands.describe(id_produto="ID do produto", novo_preco="Novo preco, ex: 40,00")
async def update_price(interaction: discord.Interaction, id_produto: int, novo_preco: str) -> None:
    guild_id = guild_only_interaction(interaction)
    if not store_db.product_belongs_to_owner(guild_id, id_produto, interaction.user.id):
        await interaction.response.send_message("Produto nao encontrado ou voce nao e o dono da loja desse produto.", ephemeral=True)
        return

    price_cents = parse_price_to_cents(novo_preco)
    store_db.update_product_price(id_produto, price_cents)
    await interaction.response.send_message(f"Preco do produto `#{id_produto}` alterado para {format_price(price_cents)}.", ephemeral=True)


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
    orders = store_db.list_orders_for_owner(guild_id, interaction.user.id)
    await interaction.response.send_message(
        embed=build_orders_embed("Pedidos recebidos", "Resumo dos pedidos mais recentes das suas lojas.", orders, True),
        ephemeral=True,
    )


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("Configure DISCORD_TOKEN no arquivo .env antes de iniciar o bot.")
    bot.run(DISCORD_TOKEN)
