# whatsapp/service.py

from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from typing import Optional

import pyperclip

from diagnostics.audit import registrar_erro, registrar_etapa
from playwright.async_api import (
    Browser,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from whatsapp.config import (
    TEMPO_ABRIR_GRUPO,
    TEMPO_CONEXAO,
    WHATSAPP_CDP_URL,
)


class WhatsAppService:
    """Controla o WhatsApp Web pelo Chrome aberto via CDP."""

    def __init__(self, cdp_url: str = WHATSAPP_CDP_URL) -> None:
        self.cdp_url = cdp_url
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.pagina: Optional[Page] = None
        self.grupo_aberto: Optional[str] = None
        self._lock_envio = asyncio.Lock()
        self._lock_conexao = asyncio.Lock()
        self._lock_watchdog = asyncio.Lock()

    async def conectar(self) -> bool:
        async with self._lock_conexao:
            if (
                self.pagina is not None
                and not self.pagina.is_closed()
                and self.browser is not None
                and self.browser.is_connected()
            ):
                return True

            try:
                if self.playwright is None:
                    self.playwright = await async_playwright().start()

                self.browser = await self.playwright.chromium.connect_over_cdp(
                    self.cdp_url,
                    timeout=TEMPO_CONEXAO,
                )
                self.pagina = await self._encontrar_pagina_whatsapp()

                if self.pagina is None:
                    raise RuntimeError(
                        "Nenhuma aba do WhatsApp Web foi encontrada no Chrome."
                    )

                await self.pagina.bring_to_front()

                if not await self.esta_conectado():
                    raise RuntimeError(
                        "O WhatsApp Web foi encontrado, mas não está conectado."
                    )

                return True
            except Exception:
                await self._limpar_conexao()
                raise


    async def verificar_saude(self) -> tuple[bool, str]:
        """Verifica se Chrome, aba e sessão do WhatsApp continuam utilizáveis."""
        if self.browser is None:
            return False, "Chrome ainda não conectado ao serviço."

        try:
            if not self.browser.is_connected():
                return False, "A conexão CDP com o Chrome foi encerrada."
        except Exception as erro:
            return False, f"Não foi possível validar o Chrome: {erro}"

        if self.pagina is None:
            return False, "A aba do WhatsApp não está registrada no serviço."

        try:
            if self.pagina.is_closed():
                return False, "A aba do WhatsApp foi fechada."
        except Exception as erro:
            return False, f"Não foi possível validar a aba do WhatsApp: {erro}"

        try:
            if not await self.esta_conectado():
                return False, "A sessão do WhatsApp Web não está pronta."
        except Exception as erro:
            return False, f"Falha ao validar a sessão do WhatsApp: {erro}"

        return True, "WhatsApp conectado."

    async def watchdog_verificar_e_recuperar(self) -> tuple[str, str]:
        """Executa uma verificação do watchdog sem interromper um envio ativo."""
        if self._lock_envio.locked():
            return "OCUPADO", "Envio em andamento; verificação adiada."

        async with self._lock_watchdog:
            saudavel, motivo = await self.verificar_saude()
            if saudavel:
                return "ONLINE", motivo

            await self._limpar_conexao()
            try:
                await self.conectar()
            except Exception as erro:
                return "OFFLINE", f"{motivo} Recuperação falhou: {erro}"

            saudavel, motivo_final = await self.verificar_saude()
            if saudavel:
                return "RECUPERADO", motivo_final
            return "OFFLINE", motivo_final

    async def preparar_nova_tentativa(
        self,
        audit_id: str = "",
        grupo: str = "",
        tentativa: int = 0,
    ) -> None:
        """Descarta referências antigas e reconecta antes de um retry."""
        inicio = perf_counter()

        if audit_id:
            registrar_etapa(
                audit_id,
                "WHATSAPP_RECUPERACAO",
                codigo="RECUPERACAO_INICIADA",
                grupo=grupo,
                tentativa=tentativa,
            )

        await self._limpar_conexao()
        await asyncio.sleep(1)
        await self.conectar()

        if audit_id:
            registrar_etapa(
                audit_id,
                "WHATSAPP_RECUPERACAO",
                codigo="RECUPERACAO_CONCLUIDA",
                grupo=grupo,
                tentativa=tentativa,
                duracao_ms=(perf_counter() - inicio) * 1000,
            )

    async def _encontrar_pagina_whatsapp(self) -> Optional[Page]:
        if self.browser is None:
            return None

        for contexto in self.browser.contexts:
            for pagina in contexto.pages:
                if "web.whatsapp.com" in pagina.url.lower():
                    return pagina
        return None

    async def esta_conectado(self) -> bool:
        if self.pagina is None:
            return False

        # O WhatsApp altera com frequência a estrutura da busca. Para validar
        # a sessão, procuramos elementos estáveis da tela principal, e não
        # somente o antigo campo <input> de pesquisa.
        seletores = [
            '#side',
            '#pane-side',
            'div[aria-label="Lista de conversas"]',
            'div[aria-label*="lista de conversas" i]',
            'header',
        ]

        for seletor in seletores:
            try:
                await self.pagina.locator(seletor).first.wait_for(
                    state="visible",
                    timeout=3_000,
                )
                return True
            except Exception:
                continue
        return False

    async def _fechar_pesquisa_interna_conversa(self) -> None:
        """Fecha a pesquisa da conversa aberta, sem mexer na busca lateral."""
        if self.pagina is None:
            return

        # A pesquisa dentro da conversa normalmente cria um painel no lado
        # direito ou altera o cabeçalho da conversa. Pressionar Escape fecha
        # esse modo sem trocar de chat.
        seletores = [
            '#main button[aria-label*="Fechar pesquisa" i]',
            '#main div[role="button"][aria-label*="Fechar pesquisa" i]',
            '#main [data-icon="x-alt"]',
            '#main [data-icon="back"]',
        ]
        for seletor in seletores:
            candidatos = self.pagina.locator(seletor)
            for indice in range(await candidatos.count()):
                candidato = candidatos.nth(indice)
                try:
                    if await candidato.is_visible():
                        await candidato.click()
                        await self.pagina.wait_for_timeout(250)
                        return
                except Exception:
                    continue

        try:
            await self.pagina.keyboard.press("Escape")
            await self.pagina.wait_for_timeout(150)
        except Exception:
            pass

    async def _encontrar_caixa_pesquisa(self) -> Locator:
        if self.pagina is None:
            raise RuntimeError("O WhatsApp ainda não está conectado.")

        await self._fechar_pesquisa_interna_conversa()

        # O WhatsApp e o WhatsApp Business mudam com frequência a posição e
        # os atributos da busca. Primeiro tentamos o painel lateral tradicional.
        painel_lateral = self.pagina.locator("#side").first
        try:
            await painel_lateral.wait_for(state="visible", timeout=5_000)
        except Exception as erro:
            raise RuntimeError(
                "O painel lateral de conversas do WhatsApp não foi encontrado."
            ) from erro

        seletores_laterais = [
            'div[contenteditable="true"][role="textbox"][aria-label*="Pesquisar" i]',
            'div[contenteditable="true"][role="textbox"][aria-label*="iniciar" i]',
            'div[contenteditable="true"][aria-placeholder*="Pesquisar" i]',
            'div[contenteditable="true"][aria-placeholder*="iniciar" i]',
            'div[contenteditable="true"][data-tab="3"]',
            'div[contenteditable="true"][data-lexical-editor="true"]',
            'input[aria-label*="Pesquisar" i]',
            'input[placeholder*="Pesquisar" i]',
        ]

        async def caixa_valida(caixa: Locator) -> bool:
            try:
                if not await caixa.is_visible():
                    return False
                if not await caixa.is_editable():
                    return False

                # Nunca permite a caixa de pesquisa de mensagens dentro do chat.
                dentro_do_main = await caixa.evaluate(
                    "elemento => Boolean(elemento.closest('#main'))"
                )
                if dentro_do_main:
                    return False

                # Confirma que o elemento está no lado esquerdo da tela. Isso
                # cobre o WhatsApp Business mesmo quando a busca não está
                # tecnicamente aninhada em #side.
                caixa_posicao = await caixa.bounding_box()
                viewport = self.pagina.viewport_size
                if caixa_posicao and viewport:
                    if caixa_posicao["x"] > viewport["width"] * 0.55:
                        return False

                return True
            except Exception:
                return False

        # Primeira tentativa: somente dentro do painel lateral.
        for seletor in seletores_laterais:
            candidatos = painel_lateral.locator(seletor)
            for indice in range(await candidatos.count()):
                caixa = candidatos.nth(indice)
                if await caixa_valida(caixa):
                    return caixa

        # Algumas versões exibem um botão antes de montar o campo de busca.
        botoes_laterais = [
            'button[aria-label*="Pesquisar" i]',
            'div[role="button"][aria-label*="Pesquisar" i]',
            '[data-icon="search"]',
            'span[data-icon="search"]',
        ]
        for seletor in botoes_laterais:
            candidatos = painel_lateral.locator(seletor)
            for indice in range(await candidatos.count()):
                botao = candidatos.nth(indice)
                try:
                    if await botao.is_visible():
                        await botao.click()
                        await self.pagina.wait_for_timeout(500)
                        break
                except Exception:
                    continue

        # Segunda tentativa após o clique.
        for seletor in seletores_laterais:
            candidatos = painel_lateral.locator(seletor)
            for indice in range(await candidatos.count()):
                caixa = candidatos.nth(indice)
                if await caixa_valida(caixa):
                    return caixa

        # Fallback específico para versões novas/Business: procura em toda a
        # página, mas rejeita qualquer elemento dentro de #main e qualquer
        # caixa posicionada no lado direito. Assim o fluxo não volta a pesquisar
        # mensagens dentro do grupo aberto.
        seletores_fallback = [
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"][aria-placeholder]',
            'div[contenteditable="true"][data-tab]',
            'div[contenteditable="true"]',
            'input[type="text"]',
            'input:not([type])',
        ]
        for seletor in seletores_fallback:
            candidatos = self.pagina.locator(seletor)
            for indice in range(await candidatos.count()):
                caixa = candidatos.nth(indice)
                if await caixa_valida(caixa):
                    return caixa

        url_atual = self.pagina.url
        titulo = await self.pagina.title()
        raise RuntimeError(
            "A caixa de pesquisa da lista de conversas não foi encontrada. "
            "Foram verificadas as estruturas do WhatsApp comum e Business, "
            "sem usar a pesquisa interna da conversa. "
            f"Página atual: {titulo!r} — {url_atual}"
        )

    async def _grupo_ja_esta_aberto(self, nome_grupo: str) -> bool:
        if self.pagina is None:
            return False

        titulo = self.pagina.locator(
            f'header span[title="{nome_grupo}"], header div[title="{nome_grupo}"]'
        ).first
        try:
            if await titulo.is_visible():
                self.grupo_aberto = nome_grupo
                return True
        except Exception:
            pass
        return False

    async def abrir_grupo(self, nome_grupo: str) -> bool:
        nome_grupo = (nome_grupo or "").strip()
        if not nome_grupo:
            raise ValueError("O nome do grupo não pode ficar vazio.")

        await self.conectar()
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        if await self._grupo_ja_esta_aberto(nome_grupo):
            return True

        caixa = await self._encontrar_caixa_pesquisa()
        await caixa.click()

        # Funciona tanto para INPUT quanto para DIV contenteditable.
        try:
            await caixa.fill("")
            await caixa.fill(nome_grupo)
        except Exception:
            await self.pagina.keyboard.press("Control+A")
            await self.pagina.keyboard.press("Backspace")
            await self.pagina.keyboard.type(nome_grupo, delay=25)

        await self.pagina.wait_for_timeout(1_500)

        resultado = await self._encontrar_resultado_grupo(nome_grupo)
        if resultado is None:
            try:
                await caixa.fill("")
            except Exception:
                await caixa.click()
                await self.pagina.keyboard.press("Control+A")
                await self.pagina.keyboard.press("Backspace")
            raise RuntimeError(
                f'O grupo "{nome_grupo}" não apareceu nos resultados.'
            )

        await resultado.click()
        await self._aguardar_grupo_aberto(nome_grupo)
        self.grupo_aberto = nome_grupo
        return True

    async def _encontrar_resultado_grupo(
        self, nome_grupo: str
    ) -> Optional[Locator]:
        if self.pagina is None:
            return None

        # Os resultados válidos ficam na lista lateral. Limitar a busca evita
        # clicar no título do grupo já aberto ou em textos dentro da conversa.
        areas_resultado = [
            self.pagina.locator('#pane-side').first,
            self.pagina.locator('#side').first,
        ]

        for area in areas_resultado:
            try:
                if not await area.is_visible():
                    continue
            except Exception:
                continue

            candidatos = area.locator(
                f'span[title="{nome_grupo}"], div[title="{nome_grupo}"]'
            )
            for indice in range(await candidatos.count()):
                candidato = candidatos.nth(indice)
                try:
                    if await candidato.is_visible():
                        return candidato
                except Exception:
                    continue

            textos = area.get_by_text(nome_grupo, exact=True)
            for indice in range(await textos.count()):
                candidato = textos.nth(indice)
                try:
                    if await candidato.is_visible():
                        return candidato
                except Exception:
                    continue

        return None

    async def _aguardar_grupo_aberto(self, nome_grupo: str) -> None:
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        try:
            await self.pagina.locator(
                'footer div[contenteditable="true"][role="textbox"]'
            ).first.wait_for(state="visible", timeout=TEMPO_ABRIR_GRUPO)
        except PlaywrightTimeoutError as erro:
            raise RuntimeError(
                f'O grupo "{nome_grupo}" abriu, mas a caixa de mensagem não apareceu.'
            ) from erro

    async def obter_caixa_mensagem(
        self, nome_grupo: Optional[str] = None
    ) -> Locator:
        if self.pagina is None:
            raise RuntimeError("O WhatsApp ainda não está conectado.")

        caixa = self.pagina.locator(
            'footer div[contenteditable="true"][role="textbox"]'
        ).first
        await caixa.wait_for(state="visible", timeout=5_000)
        return caixa

    async def enviar_texto(self, nome_grupo: str, mensagem: str) -> None:
        mensagem = (mensagem or "").strip()
        if not mensagem:
            raise ValueError("A mensagem do WhatsApp está vazia.")

        await self.abrir_grupo(nome_grupo)
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        caixa = await self.obter_caixa_mensagem(nome_grupo)
        await caixa.click()
        pyperclip.copy(mensagem)
        await self.pagina.keyboard.press("Control+V")
        await self.pagina.wait_for_timeout(300)
        await self.pagina.keyboard.press("Enter")

        # Depois do Enter, uma falha apenas durante a espera não deve provocar
        # retry, pois isso poderia duplicar uma mensagem que já foi enviada.
        try:
            await self.pagina.wait_for_timeout(1_000)
        except Exception:
            pass

    async def enviar_imagem_com_legenda(
        self,
        nome_grupo: str,
        caminho_imagem: str,
        legenda: str,
    ) -> None:
        """
        Fluxo propositalmente simples:
        1. abre o anexo;
        2. escolhe a imagem;
        3. o WhatsApp deixa o campo da legenda focado;
        4. cola a mensagem com Ctrl+V;
        5. envia com Enter.
        """
        caminho = Path(caminho_imagem).resolve()
        if not caminho.is_file():
            raise FileNotFoundError(f"A imagem não foi encontrada: {caminho}")

        legenda = (legenda or "").strip()
        if not legenda:
            raise ValueError("A legenda da imagem está vazia.")

        await self.abrir_grupo(nome_grupo)
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        await self._clicar_botao_anexar()

        try:
            async with self.pagina.expect_file_chooser(timeout=10_000) as info:
                await self._clicar_fotos_e_videos()
            seletor = await info.value
            await seletor.set_files(str(caminho))
        except PlaywrightTimeoutError as erro:
            raise RuntimeError(
                'O seletor de arquivos não abriu após clicar em "Fotos e vídeos".'
            ) from erro

        print("WhatsApp.......... ⏳ AGUARDANDO PRÉVIA DA IMAGEM")
        await self.pagina.wait_for_timeout(3_000)

        # Não procura campo, não clica no campo e não usa seletores da prévia.
        # O texto é colocado na área de transferência e colado no foco atual.
        pyperclip.copy(legenda)
        await self.pagina.keyboard.press("Control+V")
        print("WhatsApp.......... ✅ MENSAGEM COLADA")

        await self.pagina.wait_for_timeout(700)
        await self.pagina.keyboard.press("Enter")
        print("WhatsApp.......... ⏳ COMANDO DE ENVIO REALIZADO")

        # O comando de envio já foi executado. Não transformamos uma falha
        # posterior de espera em retry para não publicar a mesma promoção duas vezes.
        try:
            await self.pagina.wait_for_timeout(2_500)
        except Exception:
            pass
        print("WhatsApp.......... ✅ FLUXO DE IMAGEM FINALIZADO")

    async def _clicar_botao_anexar(self) -> None:
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        seletores = [
            'button[aria-label="Anexar"]',
            'div[role="button"][aria-label="Anexar"]',
            'span[data-icon="plus-rounded"]',
            '[data-icon="clip"]',
        ]
        for seletor in seletores:
            candidatos = self.pagina.locator(seletor)
            for indice in range(await candidatos.count()):
                candidato = candidatos.nth(indice)
                try:
                    if await candidato.is_visible():
                        await candidato.click()
                        return
                except Exception:
                    continue
        raise RuntimeError("O botão de anexar não foi encontrado.")

    async def _clicar_fotos_e_videos(self) -> None:
        if self.pagina is None:
            raise RuntimeError("A página do WhatsApp não está disponível.")

        seletores = [
            'text="Fotos e vídeos"',
            '[aria-label="Fotos e vídeos"]',
            '[title="Fotos e vídeos"]',
            'div[role="button"]:has-text("Fotos e vídeos")',
            'li:has-text("Fotos e vídeos")',
        ]
        for seletor in seletores:
            candidatos = self.pagina.locator(seletor)
            for indice in range(await candidatos.count()):
                candidato = candidatos.nth(indice)
                try:
                    if await candidato.is_visible():
                        await candidato.click()
                        return
                except Exception:
                    continue
        raise RuntimeError('A opção "Fotos e vídeos" não foi encontrada.')

    async def enviar_promocao(
        self,
        nome_grupo: str,
        mensagem: str,
        imagem: Optional[str] = None,
        audit_id: str = "",
    ) -> str:
        inicio_total = perf_counter()

        if audit_id:
            registrar_etapa(
                audit_id,
                "WHATSAPP_SERVICO",
                codigo="ENVIO_GRUPO_INICIADO",
                grupo=nome_grupo,
                possui_imagem=bool(imagem),
            )

        async with self._lock_envio:
            try:
                inicio = perf_counter()
                await self.abrir_grupo(nome_grupo)
                if audit_id:
                    registrar_etapa(
                        audit_id,
                        "WHATSAPP_ABRIR_GRUPO",
                        codigo="GRUPO_ABERTO",
                        grupo=nome_grupo,
                        duracao_ms=(perf_counter() - inicio) * 1000,
                    )

                if imagem:
                    caminho = Path(str(imagem)).resolve()
                    if caminho.is_file():
                        inicio = perf_counter()
                        await self.enviar_imagem_com_legenda(
                            nome_grupo=nome_grupo,
                            caminho_imagem=str(caminho),
                            legenda=mensagem,
                        )
                        if audit_id:
                            registrar_etapa(
                                audit_id,
                                "WHATSAPP_ENVIO_CONTEUDO",
                                codigo="IMAGEM_COM_LEGENDA_ENVIADA",
                                grupo=nome_grupo,
                                caminho_imagem=str(caminho),
                                duracao_ms=(perf_counter() - inicio) * 1000,
                                duracao_total_ms=(perf_counter() - inicio_total) * 1000,
                            )
                        return "imagem_com_legenda"

                    print(
                        "⚠ A imagem informada não existe. "
                        "A promoção será enviada somente como texto."
                    )
                    if audit_id:
                        registrar_etapa(
                            audit_id,
                            "WHATSAPP_ENVIO_CONTEUDO",
                            status="ALERTA",
                            codigo="IMAGEM_NAO_ENCONTRADA_USANDO_TEXTO",
                            grupo=nome_grupo,
                            caminho_imagem=str(caminho),
                        )

                inicio = perf_counter()
                await self.enviar_texto(nome_grupo, mensagem)
                if audit_id:
                    registrar_etapa(
                        audit_id,
                        "WHATSAPP_ENVIO_CONTEUDO",
                        codigo="TEXTO_ENVIADO",
                        grupo=nome_grupo,
                        duracao_ms=(perf_counter() - inicio) * 1000,
                        duracao_total_ms=(perf_counter() - inicio_total) * 1000,
                    )
                return "texto"

            except Exception as erro:
                if audit_id:
                    registrar_erro(
                        audit_id,
                        "WHATSAPP_SERVICO",
                        erro,
                        codigo="FALHA_ENVIO_PROMOCAO",
                        grupo=nome_grupo,
                        possui_imagem=bool(imagem),
                        duracao_ms=(perf_counter() - inicio_total) * 1000,
                    )
                raise

    async def fechar(self) -> None:
        await self._limpar_conexao()

    async def _limpar_conexao(self) -> None:
        self.pagina = None
        self.browser = None
        self.grupo_aberto = None

        if self.playwright is not None:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.playwright = None