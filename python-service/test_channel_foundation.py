"""PostgreSQL-only integrity checks. No provider, webhook or send operation."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

DB = os.getenv("TEST_DATABASE_URL", "").strip()
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class ChannelFoundationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB) as conn:
            for path in sorted((ROOT / "database/migrations").glob("*.sql")):
                conn.execute(path.read_text(), prepare=False)

    def setUp(self):
        self.conn = psycopg.connect(DB)
        self.committed = False
        self.workspaces = [
            self.insert("workspaces", slug="ci-channel-" + uuid4().hex, nome="CI")
            for _ in range(2)
        ]
        self.workspace = self.workspaces[0]
        self.canal = self.channel()
        self.conversa = self.conversation()

    def tearDown(self):
        self.conn.rollback()
        if self.committed:
            for table in [
                "crm_eventos_canal",
                "crm_mensagens_canal",
                "crm_conversas_canal",
                "crm_canais",
                "crm_clientes",
            ]:
                self.conn.execute(
                    sql.SQL(
                        "DELETE FROM socialmei.{} WHERE workspace_id = ANY(%s)"
                    ).format(sql.Identifier(table)),
                    (self.workspaces,),
                )
            self.conn.execute(
                "DELETE FROM socialmei.workspaces WHERE id = ANY(%s)",
                (self.workspaces,),
            )
            self.conn.commit()
        self.conn.close()

    def insert(self, table, **fields):
        query = sql.SQL(
            "INSERT INTO socialmei.{} ({}) VALUES ({}) RETURNING id"
        ).format(
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, fields)),
            sql.SQL(", ").join(sql.Placeholder() for _ in fields),
        )
        return self.conn.execute(query, list(fields.values())).fetchone()[0]

    def channel(self, **changes):
        return self.insert(
            "crm_canais",
            **{
                "workspace_id": self.workspace,
                "instancia": "ci-" + uuid4().hex,
                "sessao": "default",
                **changes,
            },
        )

    def conversation(self, **changes):
        return self.insert(
            "crm_conversas_canal",
            **{
                "workspace_id": self.workspace,
                "canal_id": self.canal,
                "identificador_externo": "chat-" + uuid4().hex + "@c.us",
                **changes,
            },
        )

    def message(self, **changes):
        return self.insert(
            "crm_mensagens_canal",
            **{
                "workspace_id": self.workspace,
                "canal_id": self.canal,
                "conversa_id": self.conversa,
                "identificador_externo": "message-" + uuid4().hex,
                "direcao": "entrada",
                "conteudo": "Mensagem ficticia",
                "status": "recebida",
                **changes,
            },
        )

    def event(self, **changes):
        return self.insert(
            "crm_eventos_canal",
            **{
                "workspace_id": self.workspace,
                "canal_id": self.canal,
                "chave_evento": "event-" + uuid4().hex,
                "tipo": "message",
                "fingerprint": "a" * 64,
                **changes,
            },
        )

    def rejects(self, error, action):
        with self.assertRaises(error), self.conn.transaction():
            action()

    def test_channels_are_disabled_and_session_cannot_belong_to_two_workspaces(self):
        self.assertEqual(
            self.conn.execute(
                "SELECT ativo, envio_habilitado, estado_provedor FROM socialmei.crm_canais WHERE id=%s",
                (self.canal,),
            ).fetchone(),
            (False, False, None),
        )
        self.rejects(
            psycopg.errors.CheckViolation, lambda: self.channel(envio_habilitado=True)
        )
        instance = self.conn.execute(
            "SELECT instancia FROM socialmei.crm_canais WHERE id=%s", (self.canal,)
        ).fetchone()[0]
        self.rejects(
            psycopg.errors.UniqueViolation,
            lambda: self.channel(instancia=instance, workspace_id=self.workspaces[1]),
        )

    def test_external_chat_identity_is_scoped_to_channel_and_workspace(self):
        chat = self.conn.execute(
            "SELECT identificador_externo FROM socialmei.crm_conversas_canal WHERE id=%s",
            (self.conversa,),
        ).fetchone()[0]
        self.rejects(
            psycopg.errors.UniqueViolation,
            lambda: self.conversation(identificador_externo=chat),
        )
        other = self.channel(workspace_id=self.workspaces[1])
        self.conversation(
            workspace_id=self.workspaces[1], canal_id=other, identificador_externo=chat
        )
        self.rejects(
            psycopg.errors.ForeignKeyViolation,
            lambda: self.conversation(workspace_id=self.workspaces[1]),
        )

    def test_client_links_never_cross_workspace_and_group_is_not_one_client(self):
        foreign = self.insert(
            "crm_clientes", workspace_id=self.workspaces[1], nome="Mesmo nome"
        )
        self.rejects(
            psycopg.errors.ForeignKeyViolation,
            lambda: self.conversation(cliente_id=foreign),
        )
        own = self.insert(
            "crm_clientes", workspace_id=self.workspace, nome="Mesmo nome"
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.conversation(cliente_id=own, tipo="grupo"),
        )

    def test_client_deletion_preserves_conversation_and_message_history(self):
        client = self.insert(
            "crm_clientes", workspace_id=self.workspace, nome="Mesmo nome"
        )
        self.conn.execute(
            "UPDATE socialmei.crm_conversas_canal SET cliente_id=%s, nome='Nome historico' WHERE id=%s",
            (client, self.conversa),
        )
        message = self.message()
        self.conn.execute("DELETE FROM socialmei.crm_clientes WHERE id=%s", (client,))
        self.assertEqual(
            self.conn.execute(
                "SELECT workspace_id, cliente_id, nome FROM socialmei.crm_conversas_canal WHERE id=%s",
                (self.conversa,),
            ).fetchone(),
            (self.workspace, None, "Nome historico"),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT conversa_id FROM socialmei.crm_mensagens_canal WHERE id=%s",
                (message,),
            ).fetchone()[0],
            self.conversa,
        )
        self.rejects(
            psycopg.errors.ForeignKeyViolation,
            lambda: self.conn.execute(
                "DELETE FROM socialmei.crm_conversas_canal WHERE id=%s",
                (self.conversa,),
            ),
        )

    def test_message_deduplication_is_per_channel_even_across_conversations(self):
        self.message(identificador_externo="provider-message")
        another_chat = self.conversation()
        self.rejects(
            psycopg.errors.UniqueViolation,
            lambda: self.message(
                identificador_externo="provider-message", conversa_id=another_chat
            ),
        )
        other = self.channel()
        other_chat = self.conversation(canal_id=other)
        self.message(
            canal_id=other,
            conversa_id=other_chat,
            identificador_externo="provider-message",
        )
        # Provider identifiers are opaque and case-sensitive.
        self.message(identificador_externo="PROVIDER-message")
        self.rejects(
            psycopg.errors.ForeignKeyViolation, lambda: self.message(canal_id=other)
        )

    def test_outbound_identity_and_uncertain_result_are_retained_without_fake_delivery(
        self,
    ):
        operation = uuid4()
        draft = {
            "direcao": "saida",
            "status": "rascunho",
            "identificador_externo": None,
            "operation_id": operation,
            "operation_fingerprint": "b" * 64,
        }
        message = self.message(**draft)
        self.rejects(
            psycopg.errors.UniqueViolation,
            lambda: self.message(**{**draft, "conteudo": "Outro destino ou texto"}),
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.message(
                direcao="saida", status="pendente", identificador_externo=None
            ),
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.message(
                **{**draft, "operation_id": uuid4(), "operation_fingerprint": None}
            ),
        )
        self.conn.execute(
            "UPDATE socialmei.crm_mensagens_canal SET status='incerta' WHERE id=%s",
            (message,),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT status, identificador_externo, enviada_em, operation_id FROM socialmei.crm_mensagens_canal WHERE id=%s",
                (message,),
            ).fetchone(),
            ("incerta", None, None, operation),
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.conn.execute(
                "UPDATE socialmei.crm_mensagens_canal SET status='enviada' WHERE id=%s",
                (message,),
            ),
        )
        self.conn.execute(
            "UPDATE socialmei.crm_mensagens_canal SET status='enviada', identificador_externo='confirmed-send', enviada_em=NOW() WHERE id=%s",
            (message,),
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.conn.execute(
                "UPDATE socialmei.crm_mensagens_canal SET status='entregue' WHERE id=%s",
                (message,),
            ),
        )

    def test_messages_sent_on_phone_are_observable_without_app_operation(self):
        message = self.message(
            direcao="saida", status="enviada", enviada_em="2026-10-12T12:00:00Z"
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT operation_id FROM socialmei.crm_mensagens_canal WHERE id=%s",
                (message,),
            ).fetchone()[0]
        )

    def test_ack_can_arrive_before_message_and_event_dedup_does_not_drop_later_ack(
        self,
    ):
        event = self.event(
            tipo="message.ack",
            chave_evento="ack-message-READ",
            mensagem_externa_id="later-message",
        )
        self.rejects(
            psycopg.errors.UniqueViolation,
            lambda: self.event(chave_evento="ack-message-READ"),
        )
        self.event(
            tipo="message.ack",
            chave_evento="ack-message-DEVICE",
            mensagem_externa_id="later-message",
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT mensagem_id FROM socialmei.crm_eventos_canal WHERE id=%s",
                (event,),
            ).fetchone()[0]
        )
        message = self.message(identificador_externo="later-message")
        self.conn.execute(
            "UPDATE socialmei.crm_eventos_canal SET mensagem_id=%s WHERE id=%s",
            (message, event),
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.conn.execute(
                "UPDATE socialmei.crm_eventos_canal SET status='processado' WHERE id=%s",
                (event,),
            ),
        )
        self.conn.execute(
            "UPDATE socialmei.crm_eventos_canal SET status='processado', processado_em=NOW() WHERE id=%s",
            (event,),
        )
        other = self.channel()
        self.rejects(
            psycopg.errors.ForeignKeyViolation,
            lambda: self.event(canal_id=other, mensagem_id=message),
        )

    def test_invalid_payload_identity_and_counters_are_rejected(self):
        for changes in [
            {"fingerprint": "invalid"},
            {"tentativas": -1},
            {"dados_normalizados": "[]"},
            {"chave_evento": " "},
        ]:
            self.rejects(
                psycopg.errors.CheckViolation,
                lambda changes=changes: self.event(**changes),
            )
        self.rejects(
            psycopg.errors.CheckViolation, lambda: self.conversation(nao_lidas=-1)
        )
        self.rejects(
            psycopg.errors.CheckViolation,
            lambda: self.message(identificador_externo=None),
        )

    def test_migration_replay_preserves_existing_crm_and_legacy_history(self):
        client = self.insert(
            "crm_clientes",
            workspace_id=self.workspace,
            nome="Preservado",
            tags='["MEI"]',
        )
        legacy = self.insert("clientes", nome="Historico antigo")
        old_conversation = self.insert("conversas", cliente_id=legacy, canal="whatsapp")
        old_message = self.insert(
            "mensagens", conversa_id=old_conversation, conteudo="Nao alterar"
        )
        self.message()
        self.conn.execute(
            (
                ROOT / "database/migrations/009_shared_channel_foundation.sql"
            ).read_text(),
            prepare=False,
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT nome, tags, versao FROM socialmei.crm_clientes WHERE id=%s",
                (client,),
            ).fetchone(),
            ("Preservado", ["MEI"], 1),
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT conteudo FROM socialmei.mensagens WHERE id=%s", (old_message,)
            ).fetchone()[0],
            "Nao alterar",
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM socialmei.crm_mensagens_canal WHERE workspace_id=%s",
                (self.workspace,),
            ).fetchone()[0],
            1,
        )

    def test_failed_message_rolls_back_new_conversation_in_same_transaction(self):
        chat = "rollback-chat"
        with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
            conversation = self.conversation(identificador_externo=chat)
            self.message(conversa_id=conversation, identificador_externo=None)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM socialmei.crm_conversas_canal WHERE workspace_id=%s AND identificador_externo=%s",
                (self.workspace, chat),
            ).fetchone()[0],
            0,
        )

    def test_concurrent_replays_insert_only_one_message(self):
        self.conn.commit()
        self.committed = True

        def receive(_):
            with psycopg.connect(DB) as conn:
                return conn.execute(
                    "INSERT INTO socialmei.crm_mensagens_canal (workspace_id, canal_id, conversa_id, identificador_externo, direcao, conteudo, status) VALUES (%s, %s, %s, 'concurrent-message', 'entrada', 'Teste', 'recebida') ON CONFLICT (workspace_id, canal_id, identificador_externo) DO NOTHING RETURNING id",
                    (self.workspace, self.canal, self.conversa),
                ).fetchone()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(receive, range(2)))
        self.assertEqual(sum(row is not None for row in results), 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM socialmei.crm_mensagens_canal WHERE workspace_id=%s AND identificador_externo='concurrent-message'",
                (self.workspace,),
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
