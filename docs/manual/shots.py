import asyncio, json
from playwright.async_api import async_playwright
B="http://127.0.0.1:8000"; T=json.load(open('/home/claude/manual/tokens.json'))
D='/home/claude/manual/img/'
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--lang=pt-BR"])
        ctx=await b.new_context(viewport={"width":1366,"height":820},locale="pt-BR",device_scale_factor=1)
        pg=await ctx.new_page()
        erros=[]; pg.on("pageerror",lambda e: erros.append(str(e)))
        async def shot(nome, full=False, clip_modal=False):
            await pg.wait_for_timeout(900)
            if clip_modal:
                el=pg.locator("#modal"); await el.screenshot(path=D+nome+".jpg", type="jpeg", quality=82)
            else:
                await pg.screenshot(path=D+nome+".jpg", type="jpeg", quality=82, full_page=full)
        async def fechar():
            await pg.evaluate("UI.fecharModal()"); await pg.wait_for_timeout(300)
        async def ir(h):
            await pg.evaluate(f"location.hash='{h}'"); await pg.wait_for_timeout(1500)
        # site
        await pg.goto(B+"/"); await pg.wait_for_timeout(1500); await shot("01-site")
        await pg.evaluate("Site.formularioCadastro('SEMESTRAL')"); await shot("02-criar-conta", clip_modal=True); await fechar()
        await pg.evaluate("Site.formularioLogin()"); await shot("03-entrar", clip_modal=True); await fechar()
        # cliente
        await pg.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await pg.goto(B+"/#/painel"); await pg.reload(); await pg.wait_for_timeout(2500); await shot("04-painel")
        await ir("#/cadastros/parceiros"); await shot("05-clientes")
        await pg.click("#btn-novo"); await shot("06-cliente-form", clip_modal=True); await fechar()
        btn=pg.locator("[data-acao]").filter(has_text="Pagamento").first
        if await btn.count()==0: btn=pg.locator("[data-acao]").first
        # linha da Rosalina
        linha=pg.locator("tr", has_text="ROSALINA").locator("[data-acao]").first
        await linha.click(); await shot("07-formas-pagamento", clip_modal=True); await fechar()
        for aba in ("produtos","unidades","bancos","empresas","usuarios","icms"):
            await ir(f"#/cadastros/{aba}"); await shot(f"08-cad-{aba}")
        await pg.click("#btn-novo"); await pg.wait_for_timeout(400)
        await pg.select_option("#modal select[name=uf_origem]","MG"); await pg.select_option("#modal select[name=uf_destino]","SP")
        await pg.fill("#modal input[name=aliquota]","12"); await pg.select_option("#modal select[name=produto_id]", index=1)
        await pg.fill("#modal input[name=observacao]","Café cru em grão — conferido com o contador")
        await shot("08b-icms-novo", clip_modal=True); await fechar()
        await pg.locator("[data-extra='0']").click(); await shot("08c-icms-gerar", clip_modal=True); await fechar()
        await ir("#/contratos"); await shot("09-contratos")
        await pg.click("#btn-novo-contrato"); await pg.wait_for_timeout(800); await shot("10-contrato-etapa1", clip_modal=True)
        await fechar()
        await pg.evaluate("(async()=>{const l=await Api.get('/api/contratos',{empresa_id:Estado.empresaId}); const c=(l.linhas||l.contratos||l)[0]; const full=await Api.get('/api/contratos/'+c.id); Contratos.formulario(full);})()")
        await pg.wait_for_timeout(1500)
        for i,n in ((1,"partes"),(2,"quantidade"),(3,"corretagem")):
            await pg.locator(f"#barra-etapas [data-etapa='{i}']").first.click(); await shot(f"11-contrato-{n}", clip_modal=True)
        await fechar()
        # faixa de cotações no rodapé
        await ir("#/painel"); await pg.wait_for_timeout(1500)
        await pg.evaluate("document.querySelector('.faixa-conteudo').style.animation='none'")
        await pg.screenshot(path=D+"27-faixa.jpg", type="jpeg", quality=85, clip={"x":0,"y":820-110,"width":1366,"height":110})
        await ir("#/receber"); await shot("12-receber")
        await pg.locator("[data-baixar]").first.click(); await shot("13-baixa", clip_modal=True); await fechar()
        await ir("#/pagar"); await pg.click("#btn-novo-titulo"); await shot("14-novo-titulo", clip_modal=True); await fechar()
        await ir("#/caixa"); await shot("15-caixa")
        await ir("#/relatorios"); await shot("16-relatorios")
        await pg.evaluate("Relatorios.abaAtual='contratos'; Relatorios.tela()"); await pg.wait_for_timeout(1500); await shot("17-rel-contratos")
        await ir("#/assinatura"); await shot("18-minha-assinatura", full=True)
        # mobile
        mob=await b.new_context(viewport={"width":390,"height":780},locale="pt-BR",device_scale_factor=1,is_mobile=True,has_touch=True)
        m=await mob.new_page(); await m.goto(B+"/")
        await m.evaluate(f"localStorage.setItem('fin_token','{T['t']}');localStorage.setItem('fin_empresa','{T['eid']}')")
        await m.goto(B+"/#/contratos"); await m.reload(); await m.wait_for_timeout(2500)
        await m.screenshot(path=D+"19-celular-contratos.jpg",type="jpeg",quality=82)
        await m.click("#btn-abrir-menu"); await m.wait_for_timeout(600)
        await m.screenshot(path=D+"20-celular-menu.jpg",type="jpeg",quality=82)
        # admin
        await pg.evaluate("Api.sair()"); await pg.wait_for_timeout(500)
        await pg.evaluate(f"localStorage.setItem('fin_token','{T['tm']}')")
        await pg.goto(B+"/#/admin-empresas"); await pg.reload(); await pg.wait_for_timeout(2500); await shot("21-admin-empresas")
        await pg.locator("tr", has_text="Brascafé").locator("[data-liberar]").first.click(); await shot("22-admin-liberar", clip_modal=True); await fechar()
        await pg.locator("tr", has_text="Brascafé").locator("[data-limite]").first.click(); await shot("23-admin-limite", clip_modal=True); await fechar()
        await pg.locator("tr", has_text="Brascafé").locator("[data-usuarios]").first.click(); await shot("24-admin-usuarios", clip_modal=True); await fechar()
        await ir("#/admin-assinaturas"); await shot("25-admin-assinaturas")
        await ir("#/configuracoes"); await shot("26-config")
        # painel Mercado do Café
        mc=await ctx.new_page()
        await mc.goto(B+"/mercado"); await mc.wait_for_timeout(2500)
        await mc.click(".mc-periodos button[data-dias='90']"); await mc.wait_for_timeout(1200)
        caixa=await mc.locator("#g-grafico svg").bounding_box()
        await mc.mouse.move(caixa["x"]+caixa["width"]*0.62, caixa["y"]+120); await mc.wait_for_timeout(300)
        await mc.screenshot(path=D+"28-mercado-bolsas.jpg", type="jpeg", quality=82)
        await mc.click("button[data-aba='cidades']"); await mc.wait_for_timeout(1000)
        await mc.screenshot(path=D+"29-mercado-cidades.jpg", type="jpeg", quality=82)
        await mc.click("button[data-aba='noticias']"); await mc.wait_for_timeout(1500)
        await mc.screenshot(path=D+"30-mercado-noticias.jpg", type="jpeg", quality=82)
        print("erros:", erros)
        await b.close()
asyncio.run(main())
