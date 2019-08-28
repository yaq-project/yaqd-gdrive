import asyncio
import functools
import time
import webbrowser

import aiohttp
import aiohttp.web
import yaqd_core


def refresh_oauth(func):
    @functools.wraps(func)
    async def inner(self, *args, **kwargs):
        res = await func(self, *args, **kwargs)
        if res.status_code == 200:
            return res
        self._authorized = False
        try:
            await self._refresh_token()
        except aiohttp.HTTPError:
            await self._authorize()

        return await func(self, *args, **kwargs)


class GDriveDaemon(yaqd_core.BaseDaemon):
    _kind = "gdrive"
    defaults = {
        "scopes": ["https://www.googleapis.com/auth/drive.file"],
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://www.googleapis.com/oauth2/v4/token",
        "create_file_url": "https://www.googleapis.com/upload/drive/v3/files",
        "generate_ids_url": "https://www.googleapis.com/drive/v3/files/generateIds",
        "update_file_url": "https://www.googleapis.com/upload/drive/v3/files/",  # Needs fileId
    }

    def __init__(self, name, config, config_filepath):
        self._http_session = aiohttp.ClientSession()
        self._upload_queue = {}
        self._id_mapping = {}
        self._free_ids = []
        self._access_token = None
        self._refresh_token = None
        super().__init__(name, config, config_filepath)
        self._client_secret = config["client_secret"]
        self._client_id = config["client_id"]
        self._root_folder_id = config["root_folder_id"]
        self._scopes = config["scopes"]
        self._authorization_url = config["authorization_url"]
        self._token_url = config["token_url"]
        self._create_file_url = config["create_file_url"]
        self._generate_ids_url = config["generate_ids_url"]
        self._update_file_url = config["update_file_url"]

    async def _authorize(self):
        code = asyncio.Future()
        port=9004
        url = f"{self._authorization_url}?scope={'%20'.join(self._scopes)}&response_type=code&redirect_uri=http://127.0.0.1:{port}&client_id={self._client_id}"
        print(url)

        app = aiohttp.web.Application()

        async def complete_auth(request):
            nonlocal code, url
            if "code" in request.query:
                code.set_result(request.query["code"])
                return aiohttp.web.Response(text="Authorization complete")
            else:
                return aiohttp.web.Response(
                    text=f"Authorization failed\n{request.query.get('error', '')}\n{url}"
                )

        app.add_routes([aiohttp.web.get("/", complete_auth)])

        webbrowser.open(url)

        runner = aiohttp.web.AppRunner(app)
        await runner.setup()
        site = aiohttp.web.TCPSite(runner, "localhost", port)
        await site.start()
        code = await code
        await runner.cleanup()
        print(code)

        await self._obtain_token(code)

    async def _obtain_token(self, code):
        async with self._http_session.post(
            self._token_url,
            json={
                "code": code,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "redirect_uri": "http://127.0.0.1:9004",
                "grant_type": "authorization_code",
            },
        ) as res:
            print(await res.text())
            res.raise_for_status()
            json = await res.json()
            self._access_token = json["access_token"]
            self._refresh_token = json["refresh_token"]
        # TODO: Auto refresh using "expires_in"?

    async def _refresh_token(self):
        async with self._http_session.post(
            self._token_url,
            params={
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "refresh_token",
            },
        ) as res:
            res.raise_for_status()
            self._access_token = await res.json()["access_token"]
        # TODO: Auto refresh using "expires_in"?

    @refresh_oauth
    async def _create_file(self, id_=None):
        pass

    @refresh_oauth
    async def _create_folder(self, id_=None):
        pass

    @refresh_oauth
    async def _update_file(self, id_):
        pass

    @refresh_oauth
    async def _generate_ids(self, count=128):
        pass

if __name__ == "__main__":
    GDriveDaemon.defaults.update({"client_id":"943700362860-7fmktmg2rjrblt4v2qh86141l6vg7qju.apps.googleusercontent.com", "client_secret":"pKIjNEasosRswlt4xWOxQCpD", "root_folder_id":"1oZOabPMoTO2XPE5mWOC_9XOR9PsUgepC"})
    gdrive = GDriveDaemon("test",GDriveDaemon.defaults, "")
    loop = asyncio.get_event_loop()

    loop.run_until_complete(gdrive._authorize())

