#!/usr/bin/env python3
"""Read-only identity gate for the reviewed 033 and additive 035 schemas."""
import argparse
import hashlib
import json
from pathlib import Path
import re

# LF-canonical SQL hashes; no SQL, ordering or whitespace changes are permitted.
MIGRATIONS = {
    "001_initial_socialmei_schema.sql": "aba3211de08dbf1277f4e1b729f5cfc48759aacad11e0acd08fa32b11f7f3beb",
    "002_shared_crm_foundation.sql": "f9f6bac993034f68ca138930dbaaefe1bbe5365939a2526729fc289f99d6f047",
    "003_client_contract.sql": "6ccd53cbc183a1524d04de88b446fbb5143fab5d42d9b8794482c1cd89e737f6",
    "004_client_import.sql": "2f8c6ad4ba3b6a0f7d5c48dbaa1849db7adac898603eaf4982ad95f680628af6",
    "005_shared_catalog.sql": "cb975af2ba727bd210ddf554fa29cdd0f5ef441e531404724f385873a030c339",
    "006_shared_sales.sql": "90bba9f0919612898cfcc8bbdeeef738c8dbf3268d0fe93d9f97f944b44a1912",
    "007_shared_finance.sql": "0afaf3edd839524973b564a6378a4d32050d91e09f414aaab2bb0795538e00c8",
    "008_workspace_transfer.sql": "8869f6191548478992259e885cea9806cf95c804e9e104ed5fb75d4c365bb106",
    "009_shared_channel_foundation.sql": "963a59bbf43f0e6f74e2d698134ac0985423c93cb3bdf105c627a6b7e82e8d16",
    "010_account_authentication.sql": "164ebd0cfcd1792362b10cb80fbcdfda87c2cc3b06178c23ddb48c7d31668169",
    "011_crm_workspace_links.sql": "12277b77470496f8f2820c2bfd980b61f0a1be7c5411162c9ccba097223662e2",
    "012_instagram_simulation.sql": "c415720340ac0076cd531183607e429f001148ed12a382045339d7fe79e1a983",
    "013_workspace_profile_sync.sql": "455353e23485c9dfa52f5c5785cbec6483b75e967846e0bcd70fef92bb56f776",
    "014_message_enrichment.sql": "65ce8ffa6501325ed62d8a423bcae91f6a6a5ba86c725439e0f6dae08108053e",
    "015_content_preparation.sql": "80483bf7ae8ce656ad05f7303046858b4aecb6ab9bf9ae2e9c9c878bd3762632",
    "016_opportunity_lifecycle.sql": "c6e78b3e2b1a521dec66f2b505d75bc8d9383c5e67aa38097cf3d27031bddd9b",
    "017_integration_setup.sql": "c6c8cf593a2bc00c0674e0ef542f935c75b194c50e73dfdec17e6cbc0bce7e5a",
    "018_instagram_provider_lab.sql": "aa3264dbb080f264b1d70c967eeff8cf61132eb362d890b3335b6de53ad81cf2",
    "019_instagram_persistent_oauth.sql": "2648933497bd481c5a13261f1d6cf6e88eace26eaf0ebc9ef3247875a03296c4",
    "020_instagram_durable_webhook.sql": "63916f6995def12fbf2e0ed106ffb08b9bdd5acd5a5c632700217711ba63523a",
    "021_instagram_direct_outbox.sql": "104ca122708d1046f8329272109ffd3dcdca7fa2acd5f432b3dcd9291ba74872",
    "022_opportunity_planning.sql": "c6cf8b7ba1f28e2f7b0fbb73da3dc1ec342555e50558ded655bf2799bc4b50d9",
    "023_waha_durable_ingress.sql": "c6d28813f415f73d9a380461fb72142c5ac243c18ef3cfb4a6da2e2182702d89",
    "024_account_recovery.sql": "c89bf75be86b756c03ed8e281cf0afc02c87a6581ae2e9ad33a7e9cff34d1265",
    "025_session_management.sql": "0454186cf44b64a6127f73dbd714047b4aabb6df56db3e1d93bd6ba8a4417fe3",
    "026_recovery_delivery_queue.sql": "0a8fcbf706854d81970100e87681550df03798fc6ca4adcf30d1f7bcbbd28469",
    "027_instagram_image_publications.sql": "a87a88bb542c07bdf01a6fce6033bdf16f671442c0d763ec79f2033cb78b49a5",
    "028_instagram_temporary_media.sql": "10e3f4353394c8befd4460d1c16fcc85d19e2432a21fec5b1cc6736a8508b63f",
    "029_workspace_pdf_knowledge.sql": "28e249ba388d7d282d79e796f29d99e924a08c3f9fa0c802af5b29434a0de017",
    "030_whatsapp_catalog_access.sql": "f28a28ef3b52c88f7698283001811778ca7a7bd87dc5f5ac976020c540b4a703",
    "031_report_viewer_role.sql": "fa3531211eb0ac43cb5aecdb4e40de869123968dd2d4c1798c4432414b8ad7c0",
    "032_whatsapp_bot_conversations.sql": "ddcb196647dd5d0876aa3fe9a482342f2c2f2cfaff2a8bcebc2909f4662a732f",
    "033_provider_sentiment_jobs.sql": "3dabb55641313d04a9772b4c3ccea0ff13e7db54146023b3c8ac482298688286",
    "034_workspace_agenda.sql": "a3c6558208a2e0398b5c6c0dd71c53ee811c813f1b0a0137c79dc46bd5dab190",
    "035_whatsapp_human_outbox.sql": "1c319f7da8d94257493d2359b5cb07789598aa3da00ddaaee03476343a4e654b",
}

# Explicit future profile. Legacy verify()/rehearsal() and MIGRATIONS stay 035-only.
MIGRATIONS038 = {**MIGRATIONS,
    '036_service_appointments.sql': 'be5c0138c5663a9d6ed99789d4c5c84052e38a8658bc7a4ada70661b4a9ec893',
    '037_catalog_details.sql': 'b3b032226da31c4fed40415d565d28250d24fe65918698cb7d52b1a230846b47',
    '038_inbox_customer_link.sql': '4442c3d48eb7b7b9cfee16ceae078e9515c94623d81011635be7598410ebbb99',
}



# Opt-in 039 profile for Instagram menu state; never relax 035/038 verifiers.
MIGRATIONS039 = {**MIGRATIONS038,
    '039_instagram_auto_menu.sql': '8be6abe3ed84c5ded1a5312944ad9e6b67fad913ffeba97ea7d9855b58b41638',
}


MIGRATIONS040 = {**MIGRATIONS039,
    '040_identity_activation.sql': 'ae44733cc8ea29febe360fb2482034db93d81bda76f0bc8dc8df92cd5e59087a',
}


def verify040(names, read):
    require(names == list(MIGRATIONS040), 'perfil_040_nao_revisado')
    hashes = {name: hashlib.sha256(read(name).replace(b'\r\n', b'\n')).hexdigest() for name in names}
    require(hashes == MIGRATIONS040, 'conteudo_de_migration040_divergente')
    return {'profile': '040', 'migrations': hashes}


def rehearsal040(receipt, sha):
    require(isinstance(receipt, dict) and receipt.get('profile') == '040'
            and receipt.get('baseline') == '039' and receipt.get('source_sha') == sha
            and receipt.get('source_dirty') is False, 'prova_040_de_origem_invalida')
    require(re.fullmatch(r'[0-9a-f]{40}', str(sha)), 'source_sha_invalido')
    require(receipt.get('source_migrations') == MIGRATIONS040
            and receipt.get('baseline_migrations') == MIGRATIONS039,
            'prova_040_migrations_divergentes')
    require(all(receipt.get(key) is True for key in (
        'isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
        'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
        'original_migrations_unchanged', 'incompatible_state_rejected',
        'backwards_compatible_reads_verified', 'sequences_preserved',
        'isolated_cleanup_verified', 'upgraded_backup_restore_verified',
    )), 'ensaio_040_incompleto')
    require(all(receipt.get(key) is False for key in (
        'production_data_used', 'production_runtime_changed', 'provider_messages_sent',
    )), 'ensaio_040_ambiente_invalido')
    require(all(re.fullmatch(r'[0-9a-f]{64}', str(receipt.get(key))) for key in (
        'backup_sha256', 'upgraded_backup_sha256')), 'ensaio_040_backup_invalido')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('api_image_id')))
            and receipt.get('api_image_revision') == sha, 'ensaio_040_imagem_invalida')
    return receipt


def verify039(names, read):
    require(names == list(MIGRATIONS039), 'perfil_039_nao_revisado')
    hashes = {name: hashlib.sha256(read(name).replace(b'\r\n', b'\n')).hexdigest() for name in names}
    require(hashes == MIGRATIONS039, 'conteudo_de_migration039_divergente')
    return {'profile': '039', 'migrations': hashes}


def rehearsal039(receipt, sha):
    require(isinstance(receipt, dict) and receipt.get('profile') == '039'
            and receipt.get('baseline') == '035' and receipt.get('source_sha') == sha
            and receipt.get('source_dirty') is False, 'prova_039_de_origem_invalida')
    require(re.fullmatch(r'[0-9a-f]{40}', str(sha)), 'source_sha_invalido')
    require(receipt.get('source_migrations') == MIGRATIONS039
            and receipt.get('baseline_migrations') == MIGRATIONS,
            'prova_039_migrations_divergentes')
    require(all(receipt.get(key) is True for key in (
        'isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
        'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
        'original_migrations_unchanged', 'incompatible_state_rejected',
        'backwards_compatible_reads_verified', 'sequences_preserved',
        'isolated_cleanup_verified', 'upgraded_backup_restore_verified',
    )), 'ensaio_039_incompleto')
    require(all(receipt.get(key) is False for key in (
        'production_data_used', 'production_runtime_changed', 'provider_messages_sent',
    )), 'ensaio_039_ambiente_invalido')
    require(all(re.fullmatch(r'[0-9a-f]{64}', str(receipt.get(key))) for key in (
        'backup_sha256', 'upgraded_backup_sha256')), 'ensaio_039_backup_invalido')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('api_image_id')))
            and receipt.get('api_image_revision') == sha, 'ensaio_039_imagem_invalida')
    return receipt


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def profile(names):
    require(isinstance(names, list), 'perfil_de_migrations_invalido')
    for version in ('033', '035'):
        if names == list(MIGRATIONS)[:int(version)]:
            return version
    raise RuntimeError('perfil_de_migrations_nao_revisado')


def verify(names, read):
    version = profile(names)
    hashes = {name: hashlib.sha256(read(name).replace(b'\r\n', b'\n')).hexdigest() for name in names}
    require(hashes == {name: MIGRATIONS[name] for name in names}, 'conteudo_de_migration_divergente')
    return {'profile': version, 'migrations': hashes}


def verify038(names, read):
    require(names == list(MIGRATIONS038), 'perfil_038_nao_revisado')
    hashes = {name: hashlib.sha256(read(name).replace(b'\r\n', b'\n')).hexdigest() for name in names}
    require(hashes == MIGRATIONS038, 'conteudo_de_migration_divergente')
    return {'profile': '038', 'migrations': hashes}


def rehearsal038(receipt, sha):
    require(isinstance(receipt, dict) and receipt.get('profile') == '038'
            and receipt.get('baseline') == '035' and receipt.get('source_sha') == sha
            and receipt.get('source_dirty') is False, 'prova_038_de_origem_invalida')
    require(re.fullmatch(r'[0-9a-f]{40}', str(sha)), 'source_sha_invalido')
    require(receipt.get('source_migrations') == MIGRATIONS038
            and receipt.get('baseline_migrations') == MIGRATIONS, 'prova_038_migrations_divergentes')
    require(all(receipt.get(key) is True for key in (
        'isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
        'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
        'original_migrations_unchanged', 'incompatible_state_rejected',
        'backwards_compatible_reads_verified', 'sequences_preserved',
        'isolated_cleanup_verified', 'upgraded_backup_restore_verified',
    )), 'ensaio_038_incompleto')
    require(all(receipt.get(key) is False for key in (
        'production_data_used', 'production_runtime_changed', 'provider_messages_sent',
    )), 'ensaio_038_ambiente_invalido')
    require(all(re.fullmatch(r'[0-9a-f]{64}', str(receipt.get(key))) for key in (
        'backup_sha256', 'upgraded_backup_sha256')), 'ensaio_038_backup_invalido')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('api_image_id')))
            and receipt.get('api_image_revision') == sha, 'ensaio_038_imagem_invalida')
    return receipt


def rehearsal(receipt, sha):
    require(isinstance(receipt, dict) and receipt.get('profile') == '035'
            and receipt.get('baseline') == '033' and receipt.get('source_sha') == sha
            and receipt.get('source_dirty') is False, 'prova_035_de_origem_invalida')
    require(re.fullmatch(r'[0-9a-f]{40}', str(sha)), 'source_sha_invalido')
    require(receipt.get('source_migrations') == MIGRATIONS
            and receipt.get('baseline_migrations') == dict(list(MIGRATIONS.items())[:33]),
            'prova_035_migrations_divergentes')
    require(all(receipt.get(key) is True for key in (
        'isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
        'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
        'original_migrations_unchanged',
        'incompatible_state_rejected', 'backwards_compatible_reads_verified',
        'sequences_preserved', 'isolated_cleanup_verified',
    )), 'ensaio_035_incompleto')
    require(all(receipt.get(key) is False for key in (
        'production_data_used', 'production_runtime_changed', 'provider_messages_sent',
    )), 'ensaio_035_ambiente_invalido')
    require(re.fullmatch(r'[0-9a-f]{64}', str(receipt.get('backup_sha256'))), 'ensaio_035_backup_invalido')
    require(re.fullmatch(r'sha256:[0-9a-f]{64}', str(receipt.get('api_image_id')))
            and receipt.get('api_image_revision') == sha, 'ensaio_035_imagem_invalida')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profile', choices=('033', '035', '038', '039', '040'), default='035')
    args = parser.parse_args()
    folder = args.source / 'database/migrations'
    require(folder.is_dir() and not folder.is_symlink(), 'pasta_de_migrations_invalida')
    files = sorted(folder.rglob('*.sql'))
    require(all(not file.is_symlink() for file in files), 'migration_simbolica_invalida')
    validator = (verify040 if args.profile == '040' else verify039 if args.profile == '039'
                 else verify038 if args.profile == '038' else verify)
    result = validator([file.relative_to(folder).as_posix() for file in files], lambda name: (folder / name).read_bytes())
    require(result['profile'] == args.profile, 'perfil_de_migrations_divergente')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
