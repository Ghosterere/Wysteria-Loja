import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

_import_directory = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(_import_directory.name) / "import.db")
os.environ["DISCORD_TOKEN"] = ""

import bot


def tearDownModule() -> None:
    _import_directory.cleanup()


class LojaDCTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "test.db"
        self.database = bot.StoreDatabase(self.database_path)
        self.guild_id = 123456789012345678
        self.owner_id = 223456789012345678
        self.buyer_id = 323456789012345678

    def tearDown(self) -> None:
        self.directory.cleanup()

    def create_shop_and_products(self) -> tuple[bot.Shop, int, int]:
        public_id = self.database.create_shop(
            self.guild_id, self.owner_id, "Loja teste", "Descrição"
        )
        shop = self.database.get_shop(self.guild_id, public_id)
        self.assertIsNotNone(shop)
        assert shop is not None
        product_a = self.database.add_product(
            shop.db_id, "Produto A", "Geral", 1250, ""
        )
        product_b = self.database.add_product(
            shop.db_id, "Produto B", "Geral", 3000, ""
        )
        return shop, product_a, product_b

    def create_order(self, status: str = "pendente") -> tuple[int, sqlite3.Row]:
        shop, product_a, product_b = self.create_shop_and_products()
        items = [
            {
                "product_id": product_a,
                "quantity": 2,
                "unit_price_cents": 1250,
                "line_total_cents": 2500,
            },
            {
                "product_id": product_b,
                "quantity": 1,
                "unit_price_cents": 3000,
                "line_total_cents": 3000,
            },
        ]
        order_id = self.database.create_order(
            guild_id=self.guild_id,
            shop_id=shop.db_id,
            product_id=product_a,
            buyer_id=self.buyer_id,
            quantity=3,
            details="Briefing",
            total_price_cents=5500,
            assigned_editor_id=self.owner_id,
            items=items,
        )
        if status != "pendente":
            self.assertTrue(
                self.database.update_order_status(order_id, status, {"pendente"})
            )
        order = self.database.get_order_details(order_id)
        self.assertIsNotNone(order)
        assert order is not None
        return order_id, order


class PriceTests(LojaDCTestCase):
    def test_price_parser_is_decimal_and_rounds_half_up(self) -> None:
        self.assertEqual(bot.parse_price_to_cents("R$ 25,50"), 2550)
        self.assertEqual(bot.parse_price_to_cents("0.005"), 1)

    def test_price_parser_rejects_non_finite_and_excessive_values(self) -> None:
        for value in ("nan", "inf", "-1", "0", "1000000.01"):
            with (
                self.subTest(value=value),
                self.assertRaises(bot.app_commands.AppCommandError),
            ):
                bot.parse_price_to_cents(value)


class DatabaseFlowTests(LojaDCTestCase):
    def test_shop_and_product_names_cannot_be_blank(self) -> None:
        with self.assertRaises(ValueError):
            self.database.create_shop(self.guild_id, self.owner_id, "   ", "")
        shop, _, _ = self.create_shop_and_products()
        with self.assertRaises(ValueError):
            self.database.add_product(shop.db_id, "   ", "Geral", 100, "")

    def test_multi_product_order_preserves_items_and_total(self) -> None:
        order_id, order = self.create_order()
        self.assertEqual(int(order["quantity"]), 3)
        self.assertEqual(int(order["total_price_cents"]), 5500)
        items = self.database.list_order_items(order_id)
        self.assertEqual(
            [int(item["line_total_cents"]) for item in items], [2500, 3000]
        )

    def test_inactive_product_is_hidden_from_buyers_and_can_be_reactivated(
        self,
    ) -> None:
        shop, product_a, _ = self.create_shop_and_products()
        self.assertTrue(
            self.database.set_product_active(
                self.guild_id, product_a, self.owner_id, False
            )
        )
        self.assertIsNone(self.database.get_product(self.guild_id, product_a))
        active_ids = {
            int(product["id"])
            for product in self.database.list_products(self.guild_id, shop.id)
        }
        self.assertNotIn(product_a, active_ids)
        management_ids = {
            int(product["id"])
            for product in self.database.list_products(
                self.guild_id, shop.id, include_inactive=True
            )
        }
        self.assertIn(product_a, management_ids)
        self.assertTrue(
            self.database.set_product_active(
                self.guild_id, product_a, self.owner_id, True
            )
        )
        self.assertIsNotNone(self.database.get_product(self.guild_id, product_a))

    def test_owner_product_panel_exposes_activation_control(self) -> None:
        shop, product_a, _ = self.create_shop_and_products()
        self.database.set_product_active(self.guild_id, product_a, self.owner_id, False)
        products = self.database.list_products(
            self.guild_id, shop.id, include_inactive=True
        )
        view = bot.OwnerProductManageView(
            self.owner_id, shop, products, selected_product_id=product_a
        )
        labels = {getattr(item, "label", None) for item in view.children}
        self.assertIn("Ativar serviço", labels)
        embed = bot.build_owner_product_embed(shop, products, product_a)
        self.assertIn("Desativado", embed.fields[3].value)

    def test_order_rejects_inconsistent_totals_and_duplicate_products(self) -> None:
        shop, product_a, _ = self.create_shop_and_products()
        invalid_items = [
            {
                "product_id": product_a,
                "quantity": 1,
                "unit_price_cents": 1250,
                "line_total_cents": 1250,
            },
            {
                "product_id": product_a,
                "quantity": 1,
                "unit_price_cents": 1250,
                "line_total_cents": 1250,
            },
        ]
        with self.assertRaises(ValueError):
            self.database.create_order(
                self.guild_id,
                shop.db_id,
                product_a,
                self.buyer_id,
                2,
                "",
                2500,
                items=invalid_items,
            )

    def test_status_transitions_are_atomic_and_reject_stale_actions(self) -> None:
        order_id, _ = self.create_order()
        self.assertTrue(
            self.database.update_order_status(order_id, "em_andamento", {"pendente"})
        )
        self.assertFalse(
            self.database.update_order_status(order_id, "em_andamento", {"pendente"})
        )
        self.assertTrue(
            self.database.update_order_status(order_id, "concluido", {"em_andamento"})
        )
        self.assertTrue(
            self.database.update_order_status(order_id, "fechado", {"concluido"})
        )
        self.assertTrue(
            self.database.update_order_status(order_id, "pendente", {"fechado"})
        )
        order = self.database.get_order_details(order_id)
        assert order is not None
        self.assertEqual(str(order["status"]), "pendente")
        self.assertIsNone(order["completed_at"])
        self.assertIsNone(order["closed_at"])

    def test_rating_revalidates_buyer_status_and_uniqueness(self) -> None:
        order_id, _ = self.create_order()
        self.assertEqual(
            self.database.create_rating(order_id, self.buyer_id, 5, "Ótimo"),
            "invalid_status",
        )
        self.assertTrue(
            self.database.update_order_status(order_id, "concluido", {"pendente"})
        )
        self.assertEqual(self.database.create_rating(order_id, 999, 5, ""), "forbidden")
        self.assertEqual(
            self.database.create_rating(order_id, self.buyer_id, 5, "Ótimo"), "created"
        )
        self.assertEqual(
            self.database.create_rating(order_id, self.buyer_id, 4, "Outra"),
            "duplicate",
        )

    def test_seller_application_allows_new_history_but_only_one_pending(self) -> None:
        first_id, created = self.database.create_seller_application(
            self.guild_id, self.buyer_id, "Portfólio", "Design"
        )
        self.assertTrue(created)
        duplicate_id, duplicate_created = self.database.create_seller_application(
            self.guild_id, self.buyer_id, "Outro", "Outro"
        )
        self.assertFalse(duplicate_created)
        self.assertEqual(first_id, duplicate_id)
        self.assertTrue(
            self.database.review_seller_application(
                first_id, "aprovado", self.owner_id, ""
            )
        )
        second_id, second_created = self.database.create_seller_application(
            self.guild_id, self.buyer_id, "Novo", "Novo"
        )
        self.assertTrue(second_created)
        self.assertNotEqual(first_id, second_id)
        self.assertTrue(
            self.database.review_seller_application(
                second_id, "aprovado", self.owner_id, ""
            )
        )
        third_id, third_created = self.database.create_seller_application(
            self.guild_id, self.buyer_id, "Terceiro", "Terceiro"
        )
        self.assertTrue(third_created)
        self.assertTrue(self.database.claim_seller_application(third_id))
        self.assertFalse(self.database.claim_seller_application(third_id))
        processing_id, processing_created = self.database.create_seller_application(
            self.guild_id, self.buyer_id, "Duplicado", "Duplicado"
        )
        self.assertFalse(processing_created)
        self.assertEqual(processing_id, third_id)
        self.assertTrue(
            self.database.review_seller_application(
                third_id,
                "aprovado",
                self.owner_id,
                "",
                expected_status="processando",
            )
        )

    def test_ticket_controls_are_persistent(self) -> None:
        _, order = self.create_order()
        view = bot.TicketControlsView.from_order(order)
        self.assertTrue(view.is_persistent())
        self.assertTrue(all(item.custom_id for item in view.children))

    def test_startup_repairs_removed_product_references_without_losing_history(
        self,
    ) -> None:
        order_id, _ = self.create_order()
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("DELETE FROM products")
            connection.commit()
        with closing(sqlite3.connect(self.database_path)) as connection:
            self.assertGreater(
                len(connection.execute("PRAGMA foreign_key_check").fetchall()), 0
            )

        repaired_database = bot.StoreDatabase(self.database_path)
        repaired_order = repaired_database.get_order_details(order_id)
        self.assertIsNotNone(repaired_order)
        with repaired_database.connection() as connection:
            self.assertEqual(
                connection.execute("PRAGMA foreign_key_check").fetchall(), []
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM orders WHERE product_id IS NULL"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM order_items WHERE product_id IS NULL"
                ).fetchone()[0],
                2,
            )


if __name__ == "__main__":
    unittest.main()
