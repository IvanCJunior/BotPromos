import requests


def resolver_link(link):

    if not link:
        return ""

    try:

        resposta = requests.get(

            link,

            allow_redirects=True,

            timeout=10,

            headers={
                "User-Agent": "Mozilla/5.0"
            }

        )

        return resposta.url

    except Exception:

        return link