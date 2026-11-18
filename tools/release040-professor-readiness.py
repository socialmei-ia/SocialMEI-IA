"""Somente leitura: preparo do workspace da API040 para demonstração.
Execução dentro do container team-api (com acesso ao PostgreSQL já configurado).
Nunca imprime nomes, telefones, mensagens, tokens ou credenciais.
"""
import argparse
import json
import os
from psycopg.rows import dict_row
from database import connect


def preparar(workspace_id=1):
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION READ ONLY")
        row = conn.execute(
            "SELECT configuracao FROM socialmei.workspaces WHERE id=%s", (workspace_id,)
        ).fetchone()
        if not row:
            return {"resultado": "workspace_nao_encontrado", "workspace_id": workspace_id}

        configuracao = row["configuracao"] if isinstance(row["configuracao"], dict) else {}
        politica = configuracao.get("channel_booking") or {}
        politica = politica.get("policy") if isinstance(politica, dict) else {}
        politica = politica if isinstance(politica, dict) else {}
        publicacao = configuracao.get("public_booking") or {}
        publicacao = publicacao.get("policy") if isinstance(publicacao, dict) else {}
        publicacao = publicacao if isinstance(publicacao, dict) else {}

        def contar(tabela, extra=""):
            # Tabela e cláusula sempre vêm de constantes locais, não de entrada do usuário.
            return conn.execute(
                f"SELECT COUNT(*) AS n FROM socialmei.{tabela} WHERE workspace_id=%s {extra}",
                (workspace_id,),
            ).fetchone()["n"]

        counts = {
            "produtos_ativos": contar("crm_produtos", "AND tipo='Produto' AND status='Ativo'"),
            "servicos_ativos_com_duracao": contar(
                "crm_produtos", "AND tipo='Serviço' AND status='Ativo' AND duracao_minutos IS NOT NULL"
            ),
            "recursos_ativos": contar("agenda_resources", "AND ativo"),
            "clientes": contar("crm_clientes"),
            "agendamentos_nao_cancelados": contar("agenda_appointments", "AND status!='cancelled'"),
            "vendas_validas": contar("crm_vendas", "AND NOT excluida AND status IN ('Pago','Pendente')"),
        }
        channel = conn.execute(
            "SELECT COUNT(*) AS n FROM socialmei.crm_canais "
            "WHERE workspace_id=%s AND provedor='waha' AND ativo AND ingress_provisioned",
            (workspace_id,),
        ).fetchone()["n"]
        profile = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM socialmei.workspace_profiles "
            "WHERE workspace_id=%s) AS ok", (workspace_id,)
        ).fetchone()["ok"]
        decisions = conn.execute(
            "SELECT status,COUNT(*) AS n FROM socialmei.wa_bot_decisions "
            "WHERE workspace_id=%s AND created_at>=NOW()-INTERVAL '24 hours' "
            "AND status IN ('confirmed','uncertain','planned','claimed') GROUP BY status",
            (workspace_id,),
        ).fetchall()
        statuses = {r["status"]: r["n"] for r in decisions}
        received = conn.execute(
            "SELECT COUNT(*) AS n FROM socialmei.crm_eventos_canal "
            "WHERE workspace_id=%s AND tipo='message' AND status='processado' "
            "AND recebido_em>=NOW()-INTERVAL '24 hours'",
            (workspace_id,),
        ).fetchone()["n"]

        hours = politica.get("hours", [])
        service_ids = publicacao.get("service_ids", [])
        resource_ids = publicacao.get("resource_ids", [])
        booking_enabled = politica.get("enabled") is True
        public_enabled = publicacao.get("enabled") is True
        public_server = os.getenv("SOCIALMEI_PUBLIC_BOOKING_ENABLED") == "true"
        whatsapp_public = os.getenv("SOCIALMEI_WHATSAPP_BOT_PUBLIC_INBOUND_ENABLED") == "true"
        whatsapp_bot = os.getenv("SOCIALMEI_WHATSAPP_BOT_ENABLED") == "true"
        interactive = os.getenv("SOCIALMEI_WHATSAPP_GOWS_PUBLIC_LISTS_ENABLED") == "YES"

        pendencias = []
        if not profile:
            pendencias.append("conferir_perfil_empresa")
        if counts["produtos_ativos"] == 0:
            pendencias.append("cadastrar_produtos")
        if counts["servicos_ativos_com_duracao"] == 0:
            pendencias.append("cadastrar_servicos_com_duracao")
        if counts["recursos_ativos"] == 0:
            pendencias.append("cadastrar_profissional_ou_recurso")
        if not booking_enabled or not isinstance(hours, list) or not hours:
            pendencias.append("configurar_politica_e_horarios_agendamento")
        if not public_enabled or not service_ids or not resource_ids or not public_server:
            pendencias.append("publicar_agendamento_site")
        if not channel or not whatsapp_bot or not whatsapp_public:
            pendencias.append("verificar_canal_whatsapp_e_flags")
        if not interactive:
            pendencias.append("persistir_flag_listas_publicas_na_imagem_nova")
        if statuses.get("uncertain", 0):
            pendencias.append("conciliar_envios_whatsapp_incerto_sem_reenviar")

        return {
            "resultado": "auditoria_somente_leitura",
            "workspace_id": workspace_id,
            "dados": counts,
            "perfil_cadastrado": bool(profile),
            "whatsapp": {
                "canal_ativo": bool(channel),
                "bot_publico_habilitado": whatsapp_bot and whatsapp_public,
                "listas_publicas_por_flag": interactive,
                "eventos_processados_24h": received,
                "decisoes_24h": statuses,
            },
            "agenda": {
                "politica_habilitada": booking_enabled,
                "janelas_semanais": len(hours) if isinstance(hours, list) else 0,
                "fuso_configurado": bool(politica.get("timezone")),
                "publicacao_site_habilitada": public_enabled,
                "publicacao_backend_habilitada": public_server,
                "servicos_publicados": len(service_ids) if isinstance(service_ids, list) else 0,
                "recursos_publicados": len(resource_ids) if isinstance(resource_ids, list) else 0,
            },
            "pendencias_para_demonstracao": pendencias,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=int, default=1)
    args = parser.parse_args()
    if args.workspace < 1:
        parser.error("workspace inválido")
    try:
        print(json.dumps(preparar(args.workspace), ensure_ascii=False, sort_keys=True, indent=2))
    except Exception as error:
        # Evita vazar DSN, SQL, mensagens e dados de clientes em exceções.
        print(json.dumps({"resultado": "falha_somente_leitura", "tipo": type(error).__name__}))
        raise SystemExit(1)
