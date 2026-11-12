"""Workspace-scoped catalog navigation; no provider calls, writes or new state."""
import re
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

TOKEN = re.compile(r'sm:([0-9a-f]{32}):([0-9])\Z')
PAGE_SIZE = 6


def configured_contacts(environment):
    raw=environment.get('SOCIALMEI_MENU_GOWS_LIST_CONTACTS_JSON','')
    if raw:
        try:contacts=json.loads(raw)
        except (ValueError,TypeError):return frozenset()
        if not isinstance(contacts,list) or not 1<=len(contacts)<=20:return frozenset()
    else:
        contacts=[environment.get('SOCIALMEI_MENU_GOWS_LIST_CANARY_CONTACT','')]
    if any(not isinstance(c,str) or not re.fullmatch(r'waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)',c) for c in contacts):
        return frozenset()
    return frozenset(contacts) if len(contacts)==len(set(contacts)) else frozenset()


def valid_token(value):
    return isinstance(value, str) and TOKEN.fullmatch(value) is not None


def clean(value, limit):
    text = ' '.join(str(value or '').split())
    text = ''.join(c for c in text if ord(c) >= 32 and not 0x7f <= ord(c) <= 0x9f)
    return text if len(text) <= limit else text[:limit-1].rstrip() + '…'


def option(title, target, description=None):
    return {'id':'nav', 'title':clean(title,24), 'description':clean(description,72) or None,
            'target':target}


def result(action, text, choices, items=None, handoff=False):
    assert 0 < len(choices) <= 10
    return ('human' if handoff else 'menu'), dict(action=action,text=text[:1024],choices=choices,
        items=items or [],handoff=handoff,catalog_navigation=True)


def main():
    return result('menu','*Como podemos ajudar?*\nEscolha uma opção para continuar.',[
        option('Explorar produtos',{'route':'browse','kind':'Produto'},'Catálogo, preços e disponibilidade'),
        option('Preço e disponibilidade',{'route':'browse','kind':'Produto'},'Escolha o produto que procura'),
        option('Conhecer serviços',{'route':'browse','kind':'Serviço'},'Veja os serviços cadastrados'),
        option('Solicitar orçamento',{'route':'quote'},'Continue com nossa equipe'),
        option('Falar com a equipe',{'route':'human'},'Atendimento nesta conversa'),
        option('Encerrar consulta',{'route':'close'},'Volte ao menu quando precisar')])


def navigation(back=None):
    rows=[]
    if back:rows.append(option('Voltar',back))
    rows.append(option('Menu principal',{'route':'main'}))
    return rows


def money(value):
    return 'R$ ' + format(Decimal(value), ',.2f').replace(',','_').replace('.',',').replace('_','.')


def availability(row):
    if row['tipo']=='Serviço':
        duration=row.get('duracao_minutos')
        unit='minuto' if duration==1 else 'minutos'
        details='Duração: '+str(duration)+' '+unit+'.\n' if duration else ''
        return details+'Condições e agenda: confirme com a equipe.'
    if row['estoque'] is not None and row['estoque']>0:return 'Estoque informado: '+str(row['estoque'])+' un.'
    if row['estoque']==0:return 'Sem estoque no momento. Para reposição, confirme com a equipe.'
    return 'Disponibilidade: confirme com a equipe.'


def item_summary(row):
    if row['tipo']=='Serviço':
        duration=row.get('duracao_minutos')
        detail=str(duration)+' min' if duration else 'Duração a confirmar'
    elif row['estoque'] is not None and row['estoque']>0:
        detail='Estoque: '+str(row['estoque'])
    else:
        detail='Sem estoque no momento'
    parts=[money(row['preco']),detail]
    if row['descricao']:parts.append(row['descricao'])
    return ' · '.join(parts)


def browse(conn, workspace, target):
    kind=target.get('kind','Produto')
    if kind not in {'Produto','Serviço'}:return main()
    page=target.get('page',0)
    if type(page) is not int or not 0<=page<=10000:return main()
    category=target.get('category')
    query=clean(target.get('query',''),160)
    summary=conn.execute("SELECT count(*) AS total,count(DISTINCT categoria) AS categories "
        "FROM socialmei.crm_produtos WHERE workspace_id=%s AND status='Ativo' AND tipo=%s",
        (workspace,kind)).fetchone()
    grouped=category is None and not target.get('all') and not query and summary['total']>PAGE_SIZE and summary['categories']>1
    base={'route':'browse','kind':kind}
    if grouped:
        rows=conn.execute("SELECT categoria,count(*) AS total FROM socialmei.crm_produtos "
            "WHERE workspace_id=%s AND status='Ativo' AND tipo=%s GROUP BY categoria "
            "ORDER BY lower(categoria),categoria LIMIT %s OFFSET %s",(workspace,kind,PAGE_SIZE+1,page*PAGE_SIZE)).fetchall()
        choices=[option(r['categoria'] or 'Sem categoria',{**base,'category':r['categoria']},
                        str(r['total'])+' itens cadastrados') for r in rows[:PAGE_SIZE]]
        if page:choices.append(option('Página anterior',{**base,'page':page-1}))
        if len(rows)>PAGE_SIZE:choices.append(option('Próxima página',{**base,'page':page+1}))
        choices+=navigation()
        if not rows:return result('categories','Esta página mudou. Volte ao início do catálogo.',navigation(base))
        return result('categories','*Explore por categoria*\nEscolha uma categoria para ver os itens.',choices)
    if category is not None and (not isinstance(category,str) or len(category)>80):return main()
    rows=conn.execute("SELECT id,nome,tipo,preco,estoque,categoria,descricao,duracao_minutos FROM socialmei.crm_produtos "
        "WHERE workspace_id=%s AND status='Ativo' AND tipo=%s AND (%s::text IS NULL OR categoria=%s) "
        "AND (%s='' OR strpos(lower(nome),lower(%s))>0) ORDER BY lower(nome),id LIMIT %s OFFSET %s",
        (workspace,kind,category,category,query,query,PAGE_SIZE+1,page*PAGE_SIZE)).fetchall()
    back={**base,'category':category,'all':bool(target.get('all')),'query':query,'page':page}
    choices=[option(r['nome'],{'route':'item','id':r['id'],'back':back},item_summary(r))
        for r in rows[:PAGE_SIZE]]
    if page:choices.append(option('Página anterior',{**back,'page':page-1}))
    if len(rows)>PAGE_SIZE:choices.append(option('Próxima página',{**back,'page':page+1}))
    if category is not None:choices.append(option('Todas as categorias',base))
    choices+=navigation()
    if not rows:
        label='serviços' if kind=='Serviço' else 'produtos'
        return result('catalog_empty','Ainda não há '+label+' disponíveis nesta seleção.\nNossa equipe pode ajudar você.',
            [option('Falar com a equipe',{'route':'human'})]+navigation(base if page or category is not None else None))
    title='Serviços' if kind=='Serviço' else 'Produtos'
    return result('services' if kind=='Serviço' else 'products','*'+title+'*\nEscolha um item para ver detalhes.\nPreços e estoque consultados no cadastro atual.',choices)


def respond(conn, workspace, target):
    if not isinstance(target,dict):return main()
    route=target.get('route')
    if route in {'main','resume'}:return main()
    if route=='close':
        return result('catalog_closed','Tudo certo. Encerramos esta consulta.\nQuando precisar, abra o menu para continuar.',navigation())
    if route=='expired':return result('navigation_expired','Esta lista foi atualizada. Abra o menu para continuar.',navigation())
    if route=='browse':return browse(conn,workspace,target)
    if route in {'item','stock','quote','info','human'}:
        item=None;item_id=target.get('id')
        if item_id is not None:
            if type(item_id) is not int or item_id<1:return main()
            item=conn.execute("SELECT id,nome,tipo,preco,estoque,categoria,descricao,duracao_minutos FROM socialmei.crm_produtos "
                "WHERE workspace_id=%s AND id=%s AND status='Ativo'",(workspace,item_id)).fetchone()
            if not item:
                back=target.get('back')
                if not isinstance(back,dict):back={'route':'browse','kind':'Produto'}
                return result('item_unavailable','Este item não está mais disponível no catálogo. Escolha outra opção.',navigation(back))
        if route in {'quote','info','human'}:
            title='Pedido de orçamento' if route=='quote' else 'Atendimento com a equipe'
            text='*'+title+'*\n'+('Sobre: '+clean(item['nome'],160)+'\n' if item else '')+'Um atendente pode continuar por aqui. O atendimento automático fica pausado.'
            return result('quote_handoff' if route=='quote' else 'human_handoff',text,
                [option('Retomar automático',{'route':'resume'},'Voltar ao menu nesta conversa')],handoff=True)
        if not item:return main()
        back=target.get('back') if isinstance(target.get('back'),dict) else {'route':'browse','kind':item['tipo']}
        product={'id':item['id'],'back':back}
        text='*'+clean(item['nome'],160)+'*\n'+money(item['preco'])+'\n'+availability(item)
        if route=='item' and item['descricao']:text+='\n\n'+clean(item['descricao'],550)
        choices=[]
        if route=='item':choices.append(option('Consultar disponibilidade',{'route':'stock',**product}))
        else:choices.append(option('Detalhes do item',{'route':'item',**product}))
        choices += [option('Pedir informações',{'route':'info',**product}),option('Solicitar orçamento',{'route':'quote',**product}),
                    option('Falar com a equipe',{'route':'human',**product})]+navigation(back)
        return result('availability' if route=='stock' else 'product_detail',text,choices)
    return main()


def resolve(conn, channel, conversation, token):
    match=TOKEN.fullmatch(token) if isinstance(token,str) else None
    if not match:return {'route':'expired'}
    row=conn.execute("SELECT id,result FROM socialmei.wa_bot_decisions WHERE workspace_id=%s AND channel_id=%s "
        "AND conversation_id=%s AND binding_hash=%s AND status='confirmed' "
        "AND created_at>=%s AND result->>'catalog_navigation'='true' ORDER BY created_at DESC,id DESC LIMIT 1",
        (channel['workspace_id'],channel['channel_id'],conversation,channel['binding_hash'],datetime.now(timezone.utc)-timedelta(hours=24))).fetchone()
    if not row or row['id']!=UUID(hex=match[1]):return {'route':'expired'}
    choices=row['result'].get('choices',[]);index=int(match[2])
    if index>=len(choices) or not isinstance(choices[index].get('target'),dict):return {'route':'expired'}
    return choices[index]['target']


def offered_choices(decision):
    return [{**c,'id':'sm:'+UUID(str(decision['id'])).hex+':'+str(i)} for i,c in enumerate(decision['result']['choices'])]


def history_text(result):
    labels = ['• '+c['title'] for c in result.get('choices', [])]
    return result['text'] + ('\n\n'+'\n'.join(labels) if labels else '')
