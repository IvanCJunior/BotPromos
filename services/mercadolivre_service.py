import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from time import perf_counter
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from browser.browser_manager import browser_manager
from diagnostics.audit import registrar_erro, registrar_etapa
from config.settings import DIAGNOSTICOS_DETALHADOS


PASTA_PROJETO = Path(__file__).resolve().parents[1]
PASTA_CAPTURAS = PASTA_PROJETO / "diagnostics" / "screenshots" / "mercadolivre"
PASTA_EVIDENCIAS = PASTA_PROJETO / "diagnostics" / "evidencias" / "mercadolivre"

GERADOR_URL = (
    "https://www.mercadolivre.com.br/afiliados/linkbuilder#hub"
)


def normalizar_para_comparacao(url: str) -> str:
    return (url or "").strip().rstrip("/")



class MercadoLivreService:
    def __init__(self) -> None:
        self.pagina: Page | None = None
        self.trava = asyncio.Lock()
        self._diagnostico_atual: dict[str, object] = {}


    def _reiniciar_diagnostico(self, *, link_recebido: str, audit_id: str) -> None:
        self._diagnostico_atual = {
            "audit_id": audit_id,
            "link_recebido": link_recebido,
            "etapa_atual": "INICIO",
            "historico_etapas": [],
            "tentativas_captura": [],
        }

    def _marcar_diagnostico(self, etapa: str, **dados: object) -> None:
        registro = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "etapa": etapa,
            **dados,
        }
        historico = self._diagnostico_atual.setdefault("historico_etapas", [])
        if isinstance(historico, list):
            historico.append(registro)
        self._diagnostico_atual["etapa_atual"] = etapa
        self._diagnostico_atual.update(dados)

    async def _obter_estado_pagina(self) -> dict[str, object]:
        if self.pagina is None or self.pagina.is_closed():
            return {"pagina_disponivel": False}

        estado: dict[str, object] = {
            "pagina_disponivel": True,
            "pagina_url": self.pagina.url,
        }
        try:
            estado["pagina_titulo"] = await self.pagina.title()
        except Exception as erro:
            estado["erro_titulo"] = str(erro)

        contagens: dict[str, int] = {}
        for nome, seletor in {
            "textareas": "textarea",
            "inputs": "input",
            "botoes": "button",
            "links": "a[href]",
            "editaveis": "[contenteditable='true']",
        }.items():
            try:
                contagens[nome] = await self.pagina.locator(seletor).count()
            except Exception:
                contagens[nome] = -1
        estado["contagens_elementos"] = contagens

        try:
            estado["document_ready_state"] = await self.pagina.evaluate("document.readyState")
        except Exception as erro:
            estado["erro_ready_state"] = str(erro)

        try:
            estado["texto_pagina_inicio"] = (await self.pagina.locator("body").inner_text())[:3000]
        except Exception as erro:
            estado["erro_texto_pagina"] = str(erro)

        return estado

    async def _salvar_evidencias_falha(self, audit_id: str = "") -> dict[str, str]:
        evidencias = {"screenshot": "", "html": "", "json": ""}

        # Em produção, evita screenshot full-page, HTML e JSON extensos.
        # O erro resumido continua sendo registrado pela auditoria normal.
        if not DIAGNOSTICOS_DETALHADOS:
            return evidencias

        if self.pagina is None or self.pagina.is_closed():
            return evidencias

        PASTA_CAPTURAS.mkdir(parents=True, exist_ok=True)
        PASTA_EVIDENCIAS.mkdir(parents=True, exist_ok=True)
        sufixo = audit_id[:8] if audit_id else "sem_audit"
        base = f"ml_{datetime.now():%Y%m%d_%H%M%S_%f}_{sufixo}"

        caminho_png = PASTA_CAPTURAS / f"{base}.png"
        try:
            await self.pagina.screenshot(path=str(caminho_png), full_page=True)
            evidencias["screenshot"] = str(caminho_png)
        except Exception as erro:
            self._diagnostico_atual["erro_screenshot"] = str(erro)

        caminho_html = PASTA_EVIDENCIAS / f"{base}.html"
        try:
            caminho_html.write_text(await self.pagina.content(), encoding="utf-8")
            evidencias["html"] = str(caminho_html)
        except Exception as erro:
            self._diagnostico_atual["erro_html"] = str(erro)

        caminho_json = PASTA_EVIDENCIAS / f"{base}.json"
        try:
            self._diagnostico_atual["estado_pagina_final"] = await self._obter_estado_pagina()
            caminho_json.write_text(
                json.dumps(self._diagnostico_atual, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            evidencias["json"] = str(caminho_json)
        except Exception as erro:
            self._diagnostico_atual["erro_json"] = str(erro)

        return evidencias

    async def conectar(self) -> None:
        """
        Localiza ou abre uma aba com o gerador oficial de links.
        """

        if self.pagina is not None and not self.pagina.is_closed():
            return

        self.pagina = await browser_manager.obter_ou_abrir_pagina(
            trecho_url="afiliados/linkbuilder",
            url=GERADOR_URL,
        )

        print("MercadoLivreService conectado.")
        print("Página:", self.pagina.url)

    @staticmethod
    def _limpar_url(url: str) -> str:
        """
        Remove fragmentos iniciados por #, mantendo o restante da URL.
        """

        if not url:
            return ""

        partes = urlsplit(url)

        return urlunsplit(
            (
                partes.scheme,
                partes.netloc,
                partes.path,
                partes.query,
                "",
            )
        )

    @staticmethod
    def _parece_pagina_de_produto(url: str) -> bool:
        """
        Verifica se a URL parece apontar para uma página de produto.
        """

        if not url:
            return False

        url_minuscula = url.lower()

        dominios_validos = (
            "mercadolivre.com.br",
            "produto.mercadolivre.com.br",
        )

        if not any(
            dominio in url_minuscula
            for dominio in dominios_validos
        ):
            return False

        sinais_de_produto = (
            "/p/mlb",
            "/mlb-",
            "wid=mlb",
            "produto.mercadolivre.com.br/mlb-",
        )

        return any(
            sinal in url_minuscula
            for sinal in sinais_de_produto
        )

    @classmethod
    def _extrair_url_produto_de_url(cls, url: str) -> str:
        """
        Extrai a URL DIRETA mais interna do produto.

        Também trata links quebrados ou aninhados, por exemplo:
        ddnf.adj.st/webview/?url=ddnf.adj.st/webview/?...&url=https://produto...

        A regra principal é: nunca devolver ddnf.adj.st, meli.la ou outro
        redirecionador. A função devolve somente mercadolivre.com.br.
        """
        bruto = unquote((url or "").strip())
        if not bruto:
            return ""

        # Procura TODAS as URLs diretas do Mercado Livre que estejam embutidas.
        # Escolhemos a última porque, em redirecionamentos aninhados, ela é a
        # URL mais interna e corresponde ao produto real.
        padroes_produto = (
            r'https?://(?:www\.|produto\.)?mercadolivre\.com\.br/[^\s"\'<>]+?/p/MLB\d+(?:[^\s"\'<>]*?)(?=https?://ddnf\.adj\.st/|$)',
            r'https?://produto\.mercadolivre\.com\.br/MLB-\d+-[^\s"\'<>?]+_JM(?:\?[^\s"\'<>]*?)?(?=https?://ddnf\.adj\.st/|$)',
            r'https?://(?:www\.)?mercadolivre\.com\.br/[^\s"\'<>?]+/MLB-\d+-[^\s"\'<>?]+_JM(?:\?[^\s"\'<>]*?)?(?=https?://ddnf\.adj\.st/|$)',
        )

        encontrados: list[str] = []
        texto_busca = bruto
        for _ in range(5):
            for padrao in padroes_produto:
                encontrados.extend(
                    m.group(0) for m in re.finditer(padrao, texto_busca, re.I)
                )
            novo = unquote(texto_busca)
            if novo == texto_busca:
                break
            texto_busca = novo

        # Limpa resíduos de outro URL concatenado depois da URL válida.
        limpos: list[str] = []
        for encontrado in encontrados:
            encontrado = re.split(r"https?://ddnf\.adj\.st/", encontrado, maxsplit=1, flags=re.I)[0]
            encontrado = encontrado.rstrip(".,);]}")
            encontrado = cls._limpar_url(encontrado)
            if cls._parece_pagina_de_produto(encontrado):
                limpos.append(encontrado)

        if limpos:
            return limpos[-1]

        # Fallback recursivo para parâmetros url=, deeplink= etc. Em vez de
        # confiar apenas em parse_qs, também localizamos cada ocorrência de
        # "url=https://" porque alguns links chegam sem codificação correta.
        candidatos: list[str] = [bruto]
        parametros_redirecionamento = {
            "url", "link", "target", "redirect", "redirect_url",
            "deeplink", "deep_link", "fallback", "fallback_url",
        }

        for _ in range(8):
            novos: list[str] = []
            for candidato in candidatos:
                candidato = unquote(candidato).strip()
                if cls._parece_pagina_de_produto(candidato):
                    return cls._limpar_url(candidato)

                try:
                    parametros = parse_qs(urlsplit(candidato).query, keep_blank_values=True)
                except Exception:
                    parametros = {}

                for nome, valores in parametros.items():
                    if nome.lower() in parametros_redirecionamento:
                        novos.extend(unquote(v).strip() for v in valores if v)

                # Captura manual de parâmetros aninhados malformados.
                for achado in re.finditer(
                    r"(?:^|[?&])(?:url|link|target|redirect_url|deeplink|deep_link)=(https?://.+?)(?=(?:[?&](?:adj_[a-z_]+|url|link|target|redirect_url|deeplink|deep_link)=)|$)",
                    candidato,
                    re.I,
                ):
                    novos.append(unquote(achado.group(1)).strip())

            if not novos:
                break
            candidatos = novos

        return ""

    async def _resolver_url_do_produto(
        self,
        link_recebido: str,
    ) -> str:
        """
        Resolve primeiro o link recebido e devolve somente uma URL direta
        de produto do Mercado Livre. O link curto/de outro afiliado nunca é
        enviado diretamente ao gerador.
        """
        if not link_recebido:
            return ""

        # Se já for uma página direta de produto, não há redirecionamento.
        direto = self._extrair_url_produto_de_url(link_recebido)
        if direto:
            return direto

        pagina_temporaria = await browser_manager.nova_pagina()
        urls_observadas: list[str] = []

        def registrar_url(url: str) -> None:
            url = (url or "").strip()
            if url and url not in urls_observadas:
                urls_observadas.append(url)

        pagina_temporaria.on("request", lambda req: registrar_url(req.url))
        pagina_temporaria.on("response", lambda resp: registrar_url(resp.url))

        try:
            print()
            print("=" * 60)
            print("RESOLVENDO PRODUTO DO MERCADO LIVRE")
            print("=" * 60)
            print("Link recebido:", link_recebido)

            try:
                await pagina_temporaria.goto(
                    link_recebido,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
            except PlaywrightTimeoutError:
                # Mesmo com timeout, a cadeia de redirecionamentos já pode
                # ter revelado a URL real do produto.
                pass

            await pagina_temporaria.wait_for_timeout(2_000)
            registrar_url(pagina_temporaria.url)

            # Procura primeiro em toda a cadeia de navegação. Isso captura a
            # URL do produto mesmo quando o redirecionamento termina na Play
            # Store ou tenta abrir o aplicativo do Mercado Livre.
            for url in reversed(urls_observadas):
                produto = self._extrair_url_produto_de_url(url)
                if produto:
                    print("URL direta encontrada na navegação:", produto)
                    return produto

            # Algumas páginas intermediárias exibem um botão para continuar.
            candidatos = [
                pagina_temporaria.get_by_role(
                    "link",
                    name=re.compile(r"ir\s+para\s+(o\s+)?produto", re.IGNORECASE),
                ),
                pagina_temporaria.get_by_role(
                    "button",
                    name=re.compile(r"ir\s+para\s+(o\s+)?produto", re.IGNORECASE),
                ),
                pagina_temporaria.get_by_text(
                    re.compile(r"ir\s+para\s+(o\s+)?produto", re.IGNORECASE),
                ),
            ]

            for candidato in candidatos:
                try:
                    for indice in range(await candidato.count()):
                        elemento = candidato.nth(indice)
                        if not await elemento.is_visible():
                            continue
                        await elemento.click()
                        await pagina_temporaria.wait_for_timeout(2_000)
                        registrar_url(pagina_temporaria.url)
                        for url in reversed(urls_observadas):
                            produto = self._extrair_url_produto_de_url(url)
                            if produto:
                                print("URL direta encontrada após continuar:", produto)
                                return produto
                except Exception:
                    continue

            # Último recurso: procura links diretos presentes no HTML.
            links = pagina_temporaria.locator("a[href]")
            for indice in range(await links.count()):
                href = await links.nth(indice).get_attribute("href") or ""
                produto = self._extrair_url_produto_de_url(href)
                if produto:
                    print("URL direta encontrada na página:", produto)
                    return produto

            raise RuntimeError(
                "Não foi possível descobrir a URL direta do produto. "
                f"Página final: {pagina_temporaria.url}"
            )

        except Exception as erro:
            print("Erro ao resolver a URL direta do produto:", erro)
            try:
                await pagina_temporaria.screenshot(
                    path="tests/erro_resolver_produto_ml.png",
                    full_page=True,
                )
            except Exception:
                pass
            return ""

        finally:
            if not pagina_temporaria.is_closed():
                await pagina_temporaria.close()

    async def _localizar_campo_link(self):
        """
        Localiza exclusivamente o campo da esquerda do Link Builder.

        O gerador possui mais de um textbox/textarea. Depois da primeira
        conversão, o campo de resultado da direita também pode conter um link.
        Por isso, nunca usamos um seletor genérico de textbox como primeira
        opção.
        """
        if self.pagina is None:
            raise RuntimeError("O serviço ainda não foi conectado.")

        # 1) Procura o textarea associado ao texto da coluna esquerda.
        rotulo = self.pagina.get_by_text(
            re.compile(
                r"insira\s+1\s+ou\s+mais\s+urls?\s+separados?\s+por\s+1\s+linha",
                re.IGNORECASE,
            ),
            exact=False,
        ).first

        try:
            if await rotulo.is_visible():
                # Sobe na árvore até um bloco que contenha um textarea.
                bloco = rotulo.locator(
                    "xpath=ancestor::*[.//textarea][1]"
                )
                campo = bloco.locator("textarea").first
                if await campo.is_visible():
                    return campo
        except Exception:
            pass

        # 2) Fallback por posição: campo editável visível no lado esquerdo.
        textareas = self.pagina.locator("textarea")
        largura = await self.pagina.evaluate("window.innerWidth")

        for indice in range(await textareas.count()):
            campo = textareas.nth(indice)
            try:
                if not await campo.is_visible():
                    continue
                if await campo.is_disabled():
                    continue
                caixa = await campo.bounding_box()
                if caixa and caixa["x"] < largura * 0.60:
                    return campo
            except Exception:
                continue

        raise RuntimeError(
            "Não encontrei o campo esquerdo para inserir a URL do produto."
        )

    async def _localizar_area_resultado(self):
        """Localiza apenas a área da direita onde o novo link é exibido."""
        if self.pagina is None:
            raise RuntimeError("O serviço ainda não foi conectado.")

        titulo = self.pagina.get_by_text(
            re.compile(r"copie\s+o\s+link", re.IGNORECASE),
            exact=False,
        ).first

        try:
            if await titulo.is_visible():
                bloco = titulo.locator(
                    "xpath=ancestor::*[.//textarea or .//input][1]"
                )
                return bloco
        except Exception:
            pass

        # Fallback: usa elementos visíveis no lado direito da página.
        return self.pagina.locator("body")

    async def _localizar_botao_gerar(self):
        if self.pagina is None:
            raise RuntimeError(
                "O serviço ainda não foi conectado."
            )

        candidatos = [
            self.pagina.get_by_role(
                "button",
                name=re.compile(
                    r"^gerar$|gerar link",
                    re.IGNORECASE,
                ),
            ),
            self.pagina.locator("button").filter(
                has_text=re.compile(
                    r"gerar",
                    re.IGNORECASE,
                )
            ),
        ]

        for candidato in candidatos:
            try:
                quantidade = await candidato.count()

                for indice in range(quantidade):
                    botao = candidato.nth(indice)

                    if (
                        await botao.is_visible()
                        and await botao.is_enabled()
                    ):
                        return botao

            except Exception:
                continue

        raise RuntimeError(
            "Não encontrei o botão Gerar."
        )

    async def _ler_clipboard(self) -> str:
        """Tenta ler o texto copiado pelo botão do Link Builder."""
        if self.pagina is None:
            return ""

        try:
            await self.pagina.context.grant_permissions(
                ["clipboard-read", "clipboard-write"],
                origin="https://www.mercadolivre.com.br",
            )
        except Exception:
            pass

        try:
            valor = await self.pagina.evaluate(
                "async () => await navigator.clipboard.readText()"
            )
            return (valor or "").strip()
        except Exception:
            return ""

    async def _extrair_links_de_elementos(self, raiz) -> list[str]:
        """Coleta URLs de campos, links e elementos editáveis da interface."""
        candidatos: list[str] = []
        elementos = raiz.locator(
            "textarea, input, a[href], [contenteditable='true'], "
            "[data-testid], [title], [aria-label]"
        )

        try:
            quantidade = await elementos.count()
        except Exception:
            quantidade = 0

        for indice in range(quantidade):
            elemento = elementos.nth(indice)
            try:
                if not await elemento.is_visible():
                    continue

                dados = await elemento.evaluate(
                    """el => ({
                        value: typeof el.value === 'string' ? el.value : '',
                        href: el.href || el.getAttribute('href') || '',
                        text: el.innerText || el.textContent || '',
                        title: el.getAttribute('title') || '',
                        aria: el.getAttribute('aria-label') || ''
                    })"""
                )
            except Exception:
                continue

            for valor in dados.values():
                valor = (valor or "").strip()
                if not valor:
                    continue
                candidatos.extend(re.findall(r"https?://[^\s\"'<>]+", valor))

        try:
            texto = await raiz.inner_text()
        except Exception:
            texto = ""

        candidatos.extend(re.findall(r"https?://[^\s\"'<>]+", texto))
        return candidatos

    async def _tentar_copiar_resultado(self, area) -> str:
        """Clica no botão Copiar do resultado e devolve o clipboard."""
        if self.pagina is None:
            return ""

        candidatos = [
            area.get_by_role(
                "button",
                name=re.compile(r"copiar(?:\s+link)?", re.IGNORECASE),
            ),
            area.locator("button").filter(
                has_text=re.compile(r"copiar", re.IGNORECASE)
            ),
            self.pagina.get_by_role(
                "button",
                name=re.compile(r"copiar(?:\s+link)?", re.IGNORECASE),
            ),
        ]

        for conjunto in candidatos:
            try:
                quantidade = await conjunto.count()
            except Exception:
                continue

            # O botão mais à direita costuma pertencer ao resultado gerado.
            botoes = []
            for indice in range(quantidade):
                botao = conjunto.nth(indice)
                try:
                    if not await botao.is_visible() or not await botao.is_enabled():
                        continue
                    caixa = await botao.bounding_box()
                    botoes.append((caixa["x"] if caixa else -1, botao))
                except Exception:
                    continue

            for _, botao in sorted(botoes, key=lambda item: item[0], reverse=True):
                try:
                    await botao.click()
                    await self.pagina.wait_for_timeout(300)
                    valor = await self._ler_clipboard()
                    if self._parece_link_afiliado(valor):
                        return valor
                except Exception:
                    continue

        return ""

    async def _capturar_link_gerado(
        self,
        links_anteriores: set[str],
        link_produto: str,
    ) -> str:
        if self.pagina is None:
            raise RuntimeError("O serviço ainda não foi conectado.")

        area = await self._localizar_area_resultado()
        for tentativa in range(8):
            self._marcar_diagnostico("CAPTURA_RESULTADO", tentativa=tentativa + 1)
            candidatos = await self._extrair_links_de_elementos(area)

            try:
                largura = await self.pagina.evaluate("window.innerWidth")
                elementos = self.pagina.locator(
                    "textarea, input, a[href], [contenteditable='true'], "
                    "[data-testid], [title], [aria-label]"
                )
                for indice in range(await elementos.count()):
                    elemento = elementos.nth(indice)
                    try:
                        if not await elemento.is_visible():
                            continue
                        caixa = await elemento.bounding_box()
                        if not caixa or caixa["x"] < largura * 0.45:
                            continue
                        dados = await elemento.evaluate(
                            """el => [
                                typeof el.value === 'string' ? el.value : '',
                                el.href || el.getAttribute('href') || '',
                                el.innerText || el.textContent || '',
                                el.getAttribute('title') || '',
                                el.getAttribute('aria-label') || ''
                            ]"""
                        )
                        for valor in dados:
                            candidatos.extend(re.findall(r"https?://[^\s\"'<>]+", valor or ""))
                    except Exception:
                        continue
            except Exception:
                pass

            link_copiado = ""
            if tentativa in (1, 4, 7):
                link_copiado = await self._tentar_copiar_resultado(area)

            tentativas = self._diagnostico_atual.setdefault("tentativas_captura", [])
            if isinstance(tentativas, list):
                tentativas.append({
                    "tentativa": tentativa + 1,
                    "quantidade_candidatos": len(candidatos),
                    "candidatos_amostra": candidatos[:20],
                    "clipboard": link_copiado,
                })

            for candidato in candidatos:
                candidato = candidato.rstrip(".,);]}").strip()
                normalizado = normalizar_para_comparacao(candidato)
                if not self._parece_link_afiliado(candidato):
                    continue
                if normalizado == normalizar_para_comparacao(link_produto):
                    continue
                if normalizado in links_anteriores:
                    continue
                self._marcar_diagnostico("LINK_CAPTURADO_NA_PAGINA", link_afiliado=candidato)
                return candidato

            normalizado_copiado = normalizar_para_comparacao(link_copiado)
            if (
                self._parece_link_afiliado(link_copiado)
                and normalizado_copiado != normalizar_para_comparacao(link_produto)
                and normalizado_copiado not in links_anteriores
            ):
                self._marcar_diagnostico("LINK_CAPTURADO_CLIPBOARD", link_afiliado=link_copiado)
                return link_copiado

            await self.pagina.wait_for_timeout(1_000)

        self._marcar_diagnostico("RESULTADO_NAO_APRESENTADO", total_tentativas=8)
        raise RuntimeError(
            "O Mercado Livre não apresentou um novo link de afiliado após "
            "8 segundos e 3 tentativas de cópia."
        )

    async def _coletar_links_resultado(self) -> set[str]:
        """Guarda os links já existentes para não reutilizá-los."""
        if self.pagina is None:
            return set()

        area = await self._localizar_area_resultado()
        encontrados: set[str] = set()
        elementos = area.locator("textarea, input, a[href]")

        for indice in range(await elementos.count()):
            elemento = elementos.nth(indice)
            try:
                tag = await elemento.evaluate("el => el.tagName")
                if tag in ("TEXTAREA", "INPUT"):
                    valor = await elemento.input_value()
                else:
                    valor = await elemento.get_attribute("href") or ""
            except Exception:
                continue

            valor = (valor or "").strip()
            if self._parece_link_afiliado(valor):
                encontrados.add(normalizar_para_comparacao(valor))

        return encontrados

    @staticmethod
    def _parece_link_afiliado(link: str) -> bool:
        if not link:
            return False

        link_minusculo = link.lower()

        indicadores = (
            "mercadolivre.com/sec/",
            "mercadolivre.com.br/sec/",
            "meli.la/",
        )

        return any(
            indicador in link_minusculo
            for indicador in indicadores
        )

    async def _limpar_campo_link(self, campo) -> None:
        """Apaga completamente qualquer link deixado no gerador."""
        await campo.click()
        await campo.press("Control+A")
        await campo.press("Backspace")
        try:
            await campo.fill("")
        except Exception:
            pass

        valor = (await campo.input_value()).strip()
        if valor:
            await campo.evaluate(
                "el => { el.value = ''; el.dispatchEvent(new Event('input', {bubbles:true})); }"
            )

    async def _gerar_no_linkbuilder(self, link: str) -> str:
        self._marcar_diagnostico("CONECTANDO_LINK_BUILDER")
        await self.conectar()
        if self.pagina is None:
            return ""

        self._marcar_diagnostico("ABRINDO_ABA_LINK_BUILDER", pagina_url=self.pagina.url)
        await self.pagina.bring_to_front()

        self._marcar_diagnostico("CARREGANDO_LINK_BUILDER")
        await self.pagina.goto(
            GERADOR_URL,
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        await self.pagina.wait_for_timeout(1_500)
        self._marcar_diagnostico(
            "LINK_BUILDER_CARREGADO",
            pagina_url=self.pagina.url,
            estado_pagina=await self._obter_estado_pagina(),
        )

        if not self._parece_pagina_de_produto(link):
            raise ValueError(
                "O gerador recebeu um link que não é uma página direta de produto."
            )

        self._marcar_diagnostico("COLETANDO_RESULTADOS_ANTERIORES")
        links_anteriores = await self._coletar_links_resultado()
        self._marcar_diagnostico(
            "RESULTADOS_ANTERIORES_COLETADOS",
            links_anteriores=sorted(links_anteriores),
        )

        self._marcar_diagnostico("LOCALIZANDO_CAMPO_LINK")
        campo = await self._localizar_campo_link()
        self._marcar_diagnostico("CAMPO_LINK_LOCALIZADO")

        self._marcar_diagnostico("LIMPANDO_CAMPO_LINK")
        await self._limpar_campo_link(campo)

        self._marcar_diagnostico("PREENCHENDO_CAMPO_LINK", link_resolvido=link)
        await campo.fill(link)
        valor_colado = (await campo.input_value()).strip()
        self._diagnostico_atual["valor_campo_apos_preenchimento"] = valor_colado

        if normalizar_para_comparacao(valor_colado) != normalizar_para_comparacao(link):
            raise RuntimeError(
                "O campo do gerador não recebeu exatamente a URL resolvida do produto."
            )

        print("Link resolvido inserido no gerador:", valor_colado)

        self._marcar_diagnostico("LOCALIZANDO_BOTAO_GERAR")
        botao = await self._localizar_botao_gerar()
        self._marcar_diagnostico("BOTAO_GERAR_LOCALIZADO")

        self._marcar_diagnostico("CLICANDO_BOTAO_GERAR")
        await botao.click()
        self._marcar_diagnostico("BOTAO_GERAR_CLICADO")
        print("Gerando seu link de afiliado...")

        self._marcar_diagnostico("AGUARDANDO_LINK_GERADO")
        return await self._capturar_link_gerado(
            links_anteriores=links_anteriores,
            link_produto=link,
        )

    async def _salvar_captura_falha(self, audit_id: str = "") -> str:
        evidencias = await self._salvar_evidencias_falha(audit_id)
        return evidencias.get("screenshot", "")

    async def gerar_link_afiliado(
        self,
        link_produto: str,
        audit_id: str = "",
    ) -> str:
        """Resolve o produto e gera o link, registrando a causa real das falhas."""
        inicio_total = perf_counter()
        link_produto = (link_produto or "").strip()
        self._reiniciar_diagnostico(link_recebido=link_produto, audit_id=audit_id)
        if not link_produto:
            return ""

        async with self.trava:
            inicio_resolucao = perf_counter()
            self._marcar_diagnostico("RESOLVENDO_URL_PRODUTO")
            link_resolvido = await self._resolver_url_do_produto(link_produto)
            self._marcar_diagnostico(
                "URL_PRODUTO_RESOLVIDA" if link_resolvido else "URL_PRODUTO_NAO_RESOLVIDA",
                link_resolvido=link_resolvido,
                duracao_resolucao_ms=(perf_counter() - inicio_resolucao) * 1000,
            )
            if audit_id:
                registrar_etapa(
                    audit_id,
                    "ML_RESOLUCAO_PRODUTO",
                    status="OK" if link_resolvido else "ERRO",
                    codigo="URL_PRODUTO_RESOLVIDA" if link_resolvido else "URL_PRODUTO_NAO_RESOLVIDA",
                    link_recebido=link_produto,
                    link_resolvido=link_resolvido,
                    duracao_ms=(perf_counter() - inicio_resolucao) * 1000,
                )
            if not link_resolvido:
                print("Promoção cancelada: não foi possível resolver a página do produto.")
                return ""

            try:
                inicio_geracao = perf_counter()
                link_afiliado = await self._gerar_no_linkbuilder(link_resolvido)
                if audit_id:
                    registrar_etapa(
                        audit_id,
                        "ML_LINK_BUILDER",
                        status="OK" if link_afiliado else "ERRO",
                        codigo="LINK_AFILIADO_GERADO" if link_afiliado else "LINK_AFILIADO_VAZIO",
                        link_resolvido=link_resolvido,
                        link_afiliado=link_afiliado,
                        pagina_url=self.pagina.url if self.pagina else "",
                        duracao_ms=(perf_counter() - inicio_geracao) * 1000,
                    )
                if link_afiliado:
                    print("Seu link foi gerado:", link_afiliado)
                    return link_afiliado
            except Exception as erro:
                self._marcar_diagnostico(
                    "FALHA_LINK_BUILDER",
                    tipo_erro=type(erro).__name__,
                    mensagem_erro=str(erro),
                    duracao_total_ms=(perf_counter() - inicio_total) * 1000,
                )
                evidencias = await self._salvar_evidencias_falha(audit_id)
                captura = evidencias.get("screenshot", "")
                pagina_url = ""
                pagina_titulo = ""
                if self.pagina is not None and not self.pagina.is_closed():
                    pagina_url = self.pagina.url
                    try:
                        pagina_titulo = await self.pagina.title()
                    except Exception:
                        pass
                if audit_id:
                    registrar_erro(
                        audit_id,
                        "ML_LINK_BUILDER",
                        erro,
                        codigo="FALHA_DETALHADA_LINK_BUILDER",
                        link_recebido=link_produto,
                        link_resolvido=link_resolvido,
                        pagina_url=pagina_url,
                        pagina_titulo=pagina_titulo,
                        screenshot=captura,
                        html=evidencias.get("html", ""),
                        diagnostico_json=evidencias.get("json", ""),
                        etapa_exata=self._diagnostico_atual.get("etapa_atual", ""),
                        diagnostico=self._diagnostico_atual,
                        duracao_ms=(perf_counter() - inicio_total) * 1000,
                    )
                print("Não foi possível gerar o link de afiliado do Mercado Livre:", erro)
                if captura:
                    print("Captura da falha:", captura)
                if evidencias.get("html"):
                    print("HTML da falha:", evidencias["html"])
                if evidencias.get("json"):
                    print("Diagnóstico da falha:", evidencias["json"])

            return ""
